#!/usr/bin/env python3
"""Generic form/login credential tester, driven by PageProbe.

Attacks an arbitrary form (any URL, any field names) using
username/password pairs, optionally refreshing a CSRF token before each
attempt and sending extra static field values alongside the credentials.
This is the tool `browser-extension/pageprobe/lib/commands.js`'s
`buildTestPyCommand()` generates a ready-to-run command line for -- see
that function for the exact flag contract this parser must accept.

Because the target form is arbitrary, this tool cannot infer "login
succeeded" the way the DVWA-specific tools in this directory do (there is
no fixed success string on a page PageProbe has never seen before). Pass
--success-text to enable pass/fail classification; without it, each
attempt is reported by HTTP status/response length only and none are
marked "confirmed" -- the raw output is left for you to review.

Output contract (best-effort, matches the other tools/ scripts when
--success-text is given):
  * `[+] <user>:<password>`   for each attempt matching --success-text
  * `[?] <user>:<password> HTTP <status> (<n> bytes)`  when --success-text
     is not set (status/length only, not a verdict)
  * `[*] attempts=N confirmed=N failures=N errors=N` summary line

Usage:
    python test.py --url URL --method GET|POST \
        --usernames FILE --passwords FILE [options]
"""
import argparse
import time

import requests

TOKEN_RE_TEMPLATE = r"name=['\"]{field}['\"][^>]*value=['\"]([^'\"]*)['\"]"


def build_parser():
    parser = argparse.ArgumentParser(
        description='Generic form/login credential tester (authorized testing only)')
    parser.add_argument('--url', required=True, help='form action URL to submit to')
    parser.add_argument('--method', default='GET', choices=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
    parser.add_argument('--usernames', required=True)
    parser.add_argument('--passwords', required=True)
    parser.add_argument('--user-field', default=None, help='field name carrying the username')
    parser.add_argument('--pass-field', default=None, help='field name carrying the password')
    parser.add_argument('--csrf-field', default=None, help='hidden field name carrying a CSRF token')
    parser.add_argument('--csrf-url', default=None, help='page to fetch a fresh CSRF token from before each attempt')
    parser.add_argument('--extra-field', action='append', default=[], metavar='NAME=VALUE',
                        help='static field to include with every attempt (repeatable)')
    parser.add_argument('--cookie', default=None, help='Cookie header value, e.g. "a=1; b=2"')
    parser.add_argument('--success-text', default=None,
                        help='text present in the response body on a successful login')
    parser.add_argument('--dry-run', action='store_true',
                        help='print the first constructed request and exit without sending anything')
    parser.add_argument('--delay', type=float, default=0.5)
    parser.add_argument('--timeout', type=float, default=10.0)
    return parser


def parse_args(argv=None):
    return build_parser().parse_args(argv)


def read_wordlist(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return [line.strip() for line in f if line.strip()]


def parse_extra_fields(pairs):
    fields = {}
    for pair in pairs:
        name, _, value = pair.partition('=')
        fields[name] = value
    return fields


def parse_cookie_header(cookie):
    jar = {}
    if not cookie:
        return jar
    for part in cookie.split(';'):
        if '=' not in part:
            continue
        k, v = part.split('=', 1)
        jar[k.strip()] = v.strip()
    return jar


class TestRunner:
    def __init__(self, url, method, user_field, pass_field, csrf_field, csrf_url,
                 extra_fields, cookie, success_text, timeout=10.0, delay=0.5):
        self.url = url
        self.method = method
        self.user_field = user_field
        self.pass_field = pass_field
        self.csrf_field = csrf_field
        self.csrf_url = csrf_url
        self.extra_fields = extra_fields
        self.timeout = timeout
        self.delay = delay
        self.success_text = success_text
        self.session = requests.Session()
        for k, v in parse_cookie_header(cookie).items():
            self.session.cookies.set(k, v)
        self.counters = {'attempts': 0, 'confirmed': 0, 'failures': 0, 'errors': 0}

    def _fetch_csrf_token(self):
        if not (self.csrf_field and self.csrf_url):
            return None
        try:
            r = self.session.get(self.csrf_url, timeout=self.timeout)
        except requests.RequestException:
            return None
        import re
        pattern = TOKEN_RE_TEMPLATE.format(field=re.escape(self.csrf_field))
        m = re.search(pattern, r.text)
        return m.group(1) if m else None

    def _build_data(self, username, password):
        data = dict(self.extra_fields)
        if self.user_field:
            data[self.user_field] = username
        if self.pass_field:
            data[self.pass_field] = password
        token = self._fetch_csrf_token()
        if token is not None:
            data[self.csrf_field] = token
        return data

    def dry_run(self, username, password):
        data = self._build_data(username, password)
        print(f"[dry-run] {self.method} {self.url}")
        print(f"[dry-run] data={data}")

    def attempt(self, username, password):
        self.counters['attempts'] += 1
        data = self._build_data(username, password)
        try:
            if self.method == 'GET':
                r = self.session.get(self.url, params=data, timeout=self.timeout)
            else:
                r = self.session.request(self.method, self.url, data=data, timeout=self.timeout)
        except requests.RequestException as exc:
            self.counters['errors'] += 1
            print(f"[!] {username}:{password}: {exc}")
            return

        if self.success_text is not None:
            if self.success_text in r.text:
                self.counters['confirmed'] += 1
                print(f"[+] {username}:{password}")
            else:
                self.counters['failures'] += 1
        else:
            # No success marker configured: report status/length for manual review.
            print(f"[?] {username}:{password} HTTP {r.status_code} ({len(r.content)} bytes)")

    def run(self, usernames, passwords):
        for username in usernames:
            for password in passwords:
                self.attempt(username, password)
                if self.delay:
                    time.sleep(self.delay)
        c = self.counters
        print(f"[*] attempts={c['attempts']} confirmed={c['confirmed']} "
              f"failures={c['failures']} errors={c['errors']}")
        if self.success_text is None:
            print("Note: --success-text not set; attempts above are unclassified (status/length only).")


if __name__ == '__main__':
    a = parse_args()
    extra_fields = parse_extra_fields(a.extra_field)
    runner = TestRunner(
        url=a.url, method=a.method,
        user_field=a.user_field, pass_field=a.pass_field,
        csrf_field=a.csrf_field, csrf_url=a.csrf_url,
        extra_fields=extra_fields, cookie=a.cookie,
        success_text=a.success_text, timeout=a.timeout, delay=a.delay,
    )
    if a.dry_run:
        usernames = read_wordlist(a.usernames)
        passwords = read_wordlist(a.passwords)
        if usernames and passwords:
            runner.dry_run(usernames[0], passwords[0])
    else:
        runner.run(read_wordlist(a.usernames), read_wordlist(a.passwords))
