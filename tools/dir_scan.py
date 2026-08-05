#!/usr/bin/env python3
"""HTTP path/content discovery (gobuster-lite) for authorized testing.

Sends a wordlist of paths to a base URL, classifies each response by status
code and content length, filters soft-404s, and reports interesting hits.
Useful for mapping a lab target's attack surface, e.g. a DVWA instance:

    python dir_scan.py --url http://127.0.0.1:8081/ --wordlist wordlists/paths.txt

Output:
  * `[<status>] <url> (len=<bytes>)`   for each hit, redirects annotated `-> loc`
  * `[*] 404 baseline: status=... len=...` and `[*] scan complete: N path(s)`
"""
import argparse
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

DEFAULT_STATUS = {200, 201, 204, 301, 302, 307, 308, 401, 403, 500, 501}


class DirScanner:
    def __init__(self, url, wordlist, extensions=None, threads=10, delay=0.0,
                 timeout=10.0, cookie=None, user_agent=None, proxy=None,
                 status_filter=None, soft404=True):
        self.base = url.rstrip("/") + "/"
        self.paths = [p.strip() for p in wordlist if p.strip()]
        self.extensions = extensions or []
        self.threads = threads
        self.delay = delay
        self.timeout = timeout
        self.headers = {}
        if user_agent:
            self.headers["User-Agent"] = user_agent
        if cookie:
            self.headers["Cookie"] = cookie
        self.proxies = {"http": proxy, "https": proxy} if proxy else None
        self.status_filter = set(status_filter) if status_filter else DEFAULT_STATUS
        self.soft404 = soft404
        self.lock = threading.Lock()
        self.found = []
        self.not_found_baseline = None

    def _get(self, path):
        return requests.get(self.base + path.lstrip("/"),
                            headers=self.headers, timeout=self.timeout,
                            proxies=self.proxies, allow_redirects=False)

    def baseline_404(self):
        probe = f"__no_such_path_{random.randint(0, 10**9)}__"
        try:
            r = self._get(probe)
        except requests.RequestException as exc:
            print(f"[!] could not reach target for 404 baseline: {exc}")
            return
        self.not_found_baseline = (r.status_code, len(r.content))
        print(f"[*] 404 baseline: status={r.status_code} len={self.not_found_baseline[1]}")

    def candidates(self):
        seen = set()
        for path in self.paths:
            if path in seen:
                continue
            seen.add(path)
            yield path
            leaf = path.split("/")[-1]
            if self.extensions and "." not in leaf:
                for ext in self.extensions:
                    yield path + ext

    def probe(self, path):
        try:
            r = self._get(path)
        except requests.RequestException as exc:
            print(f"[!] {path}: {exc}")
            return None
        status, length = r.status_code, len(r.content)
        if self.soft404 and self.not_found_baseline and \
                (status, length) == self.not_found_baseline:
            return None
        if status in self.status_filter:
            loc = ""
            if status in (301, 302, 307, 308):
                loc = f" -> {r.headers.get('location', '')}"
            return status, length, path, loc
        return None

    def scan(self):
        self.baseline_404()
        with ThreadPoolExecutor(max_workers=self.threads) as pool:
            futures = {pool.submit(self.probe, p): p for p in self.candidates()}
            for future in as_completed(futures):
                if self.delay:
                    time.sleep(self.delay * random.uniform(0.5, 1.5))
                res = future.result()
                if res:
                    status, length, path, loc = res
                    with self.lock:
                        self.found.append((status, length, path))
                    print(f"[{status}] {self.base}{path.lstrip('/')} (len={length}){loc}")
        print(f"[*] scan complete: {len(self.found)} interesting path(s)")
        return self.found


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="HTTP path/content discovery (authorized testing only)")
    parser.add_argument("--url", required=True, help="Base URL, e.g. http://127.0.0.1:8081/")
    parser.add_argument("--wordlist", required=True, help="File of paths, one per line")
    parser.add_argument("--extensions", help="Comma-separated extensions to try, e.g. .php,.txt,.bak")
    parser.add_argument("--threads", type=int, default=10)
    parser.add_argument("--delay", type=float, default=0.0, help="Jittered delay between requests (seconds)")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--cookie", help="Cookie header, e.g. PHPSESSID=abc (for authenticated scans)")
    parser.add_argument("--user-agent")
    parser.add_argument("--proxy")
    parser.add_argument("--status", help="Comma-separated status codes to report, e.g. 200,301,403")
    parser.add_argument("--no-soft404", action="store_true", help="Disable soft-404 filtering")

    a = parser.parse_args()
    exts = [e.strip() for e in a.extensions.split(",")] if a.extensions else None
    statuses = None
    if a.status:
        statuses = {int(s.strip()) for s in a.status.split(",") if s.strip()}
    with open(a.wordlist, "r", encoding="utf-8", errors="replace") as f:
        wordlist = f.readlines()
    DirScanner(url=a.url, wordlist=wordlist, extensions=exts, threads=a.threads,
               delay=a.delay, timeout=a.timeout, cookie=a.cookie,
               user_agent=a.user_agent, proxy=a.proxy, status_filter=statuses,
               soft404=not a.no_soft404).scan()
