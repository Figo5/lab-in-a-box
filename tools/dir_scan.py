#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 The lab-in-a-box authors
#
# Wordlist-based path/endpoint enumerator — authorized testing only.
# See LICENSE at the repo root for the full notice.
"""Wordlist-based path/endpoint enumerator for authorized security testing.

Reads a wordlist of candidate paths and GETs each one against a base URL,
reporting which paths return a "found" response (status < 400 by default, or
a caller-configured status set). It works against any HTTP target you own or
have written permission to test — including a local lab target or a staging
host.

This tool only ever requests the URL it is given. Do not point it at
systems you do not own or lack written permission to test. It is the
directory-scan analogue of form_enum.py: a server-side re-check using a plain
wordlist rather than a page parser.

Output contract (matches the other tools/ scripts):
  * `[+] <path> HTTP <status> (<n> bytes)`   for each found path
  * `[*] attempts=N confirmed=N failures=N errors=N` summary line

Usage:
    python dir_scan.py --url URL --wordlist FILE [--status STATUS] [--json PATH]
                       [--cookie COOKIE] [--threads N] [--delay S] [--timeout S]
"""
import argparse
import json
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


class DirScanner:
    def __init__(self, base_url, wordlist_file, statuses=None, cookie=None,
                 threads=1, delay=0.5, timeout=10.0, retries=1):
        self.base_url = base_url.rstrip('/')
        self.wordlist_file = wordlist_file
        self.statuses = statuses or {200, 301, 302, 401, 403}
        self.cookie = cookie
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

    def _cookies(self):
        jar = {}
        if not self.cookie:
            return jar
        for part in self.cookie.split(';'):
            if '=' not in part:
                continue
            k, v = part.split('=', 1)
            jar[k.strip()] = v.strip()
        return jar

    def attempt(self, path):
        """Return (ok, path, status, length) where ok True means the path was
        found (status in self.statuses), False means not found (e.g. 404), and
        None means a transient request error after retries were exhausted."""
        self._count('attempts')
        url = f"{self.base_url}/{path.lstrip('/')}"
        cookies = self._cookies()
        for n in range(1 + self.retries):
            try:
                r = requests.get(url, cookies=cookies, timeout=self.timeout,
                                  allow_redirects=False)
            except requests.RequestException as exc:
                if n == self.retries:
                    self._count('errors')
                    print(f"[!] {path}: {exc}")
                    return None, path, None, 0
                time.sleep(min(0.5 * 2 ** n, 8))
                continue
            if r.status_code in self.statuses:
                self._count('confirmed')
                return True, path, r.status_code, len(r.content)
            self._count('failures')
            return False, path, r.status_code, len(r.content)
        return None, path, None, 0

    def scan(self):
        found = []
        words = self.read_wordlist(self.wordlist_file)
        with ThreadPoolExecutor(max_workers=self.threads) as pool:
            futures = {pool.submit(self.attempt, w): w for w in words}
            for future in as_completed(futures):
                if self.delay:
                    time.sleep(self.delay * random.uniform(0.5, 1.5))
                ok, path, status, length = future.result()
                if ok:
                    found.append({'path': path, 'status': status, 'length': length})
                    print(f"[+] {path} HTTP {status} ({length} bytes)")
        return found

    def run(self):
        found = self.scan()
        with self.lock:
            c = self.counters
            print(f"[*] attempts={c['attempts']} confirmed={c['confirmed']} "
                  f"failures={c['failures']} errors={c['errors']}")
        print(f"Found {len(found)} path(s):" if found else "No paths found.")
        for f in found:
            print(f"  {f['path']} HTTP {f['status']} ({f['length']} bytes)")
        return found


def build_parser():
    parser = argparse.ArgumentParser(
        description='Wordlist-based path/endpoint enumerator (authorized testing only)')
    parser.add_argument('--url', required=True, help='base URL to scan (e.g. http://127.0.0.1:8081)')
    parser.add_argument('--wordlist', required=True, help='file of candidate paths, one per line')
    parser.add_argument('--status', action='append', type=int, default=None,
                        metavar='CODE',
                        help='HTTP status counted as "found" (repeatable); '
                             'default: 200,301,302,401,403')
    parser.add_argument('--cookie', default=None, help='Cookie header value, e.g. "a=1; b=2"')
    parser.add_argument('--threads', type=int, default=1)
    parser.add_argument('--delay', type=float, default=0.5)
    parser.add_argument('--timeout', type=float, default=10.0)
    parser.add_argument('--retries', type=int, default=1)
    parser.add_argument('--json', default=None, metavar='PATH',
                        help='write the full report as JSON to this path')
    return parser


def parse_args(argv=None):
    return build_parser().parse_args(argv)


def _report(base_url, found, counters):
    return {
        'url': base_url,
        'found': found,
        'found_count': len(found),
        'attempts': counters['attempts'],
        'confirmed': counters['confirmed'],
        'failures': counters['failures'],
        'errors': counters['errors'],
    }


if __name__ == '__main__':
    a = parse_args()
    scanner = DirScanner(
        base_url=a.url, wordlist_file=a.wordlist, statuses=set(a.status) if a.status else None,
        cookie=a.cookie, threads=a.threads, delay=a.delay, timeout=a.timeout, retries=a.retries,
    )
    found = scanner.run()
    if a.json:
        report = _report(a.url, found, scanner.counters)
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
        print(f"[*] wrote {a.json}")