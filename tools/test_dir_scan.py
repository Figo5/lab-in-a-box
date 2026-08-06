"""Flag-contract + behavior tests for dir_scan.py.

Verifies parse_args(argv) accepts the flags a generated `python dir_scan.py`
command line uses (shell-quoting style consistent with
browser-extension/pageprobe/lib/commands.js), that the default status set
matches the documented one, and that the cookie-parsing and path-joining
helpers behave correctly -- all without touching the network.
"""
import unittest

import dir_scan


class ParseArgsTests(unittest.TestCase):
    def test_accepts_minimal_command(self):
        ns = dir_scan.parse_args([
            '--url', 'http://127.0.0.1:8081',
            '--wordlist', 'wordlists/paths.txt',
        ])
        self.assertEqual(ns.url, 'http://127.0.0.1:8081')
        self.assertEqual(ns.wordlist, 'wordlists/paths.txt')
        self.assertIsNone(ns.status)        # default set applied in DirScanner
        self.assertIsNone(ns.cookie)
        self.assertIsNone(ns.json)

    def test_accepts_full_command_with_options(self):
        ns = dir_scan.parse_args([
            '--url', 'http://127.0.0.1:8081',
            '--wordlist', 'wordlists/paths.txt',
            '--status', '200',
            '--status', '403',
            '--cookie', 'PHPSESSID=abc; foo=bar',
            '--threads', '4',
            '--delay', '0.05',
            '--timeout', '10',
            '--json', 'report.json',
        ])
        self.assertEqual(ns.status, [200, 403])
        self.assertEqual(ns.cookie, 'PHPSESSID=abc; foo=bar')
        self.assertEqual(ns.threads, 4)
        self.assertEqual(ns.delay, 0.05)
        self.assertEqual(ns.timeout, 10.0)
        self.assertEqual(ns.json, 'report.json')

    def test_url_and_wordlist_are_required(self):
        with self.assertRaises(SystemExit):
            dir_scan.parse_args(['--wordlist', 'w.txt'])
        with self.assertRaises(SystemExit):
            dir_scan.parse_args(['--url', 'http://x'])

    def test_numeric_flags_have_documented_defaults(self):
        ns = dir_scan.parse_args(['--url', 'http://x', '--wordlist', 'w.txt'])
        self.assertEqual(ns.threads, 1)
        self.assertEqual(ns.delay, 0.5)
        self.assertEqual(ns.timeout, 10.0)
        self.assertEqual(ns.retries, 1)

    def test_status_flag_is_repeatable(self):
        ns = dir_scan.parse_args([
            '--url', 'http://x', '--wordlist', 'w.txt',
            '--status', '200', '--status', '301', '--status', '401',
        ])
        self.assertEqual(ns.status, [200, 301, 401])


class DefaultsAndHelpersTests(unittest.TestCase):
    def test_default_status_set_is_documented(self):
        scanner = dir_scan.DirScanner('http://x', 'w.txt')
        self.assertEqual(scanner.statuses, {200, 301, 302, 401, 403})

    def test_explicit_status_set_overrides_default(self):
        scanner = dir_scan.DirScanner('http://x', 'w.txt', statuses={200})
        self.assertEqual(scanner.statuses, {200})

    def test_base_url_trailing_slash_stripped(self):
        scanner = dir_scan.DirScanner('http://x:8081/', 'w.txt')
        self.assertEqual(scanner.base_url, 'http://x:8081')

    def test_cookie_parser_splits_pairs(self):
        scanner = dir_scan.DirScanner('http://x', 'w.txt', cookie='a=1; b=2')
        self.assertEqual(scanner._cookies(), {'a': '1', 'b': '2'})

    def test_cookie_parser_ignores_parts_without_equals(self):
        scanner = dir_scan.DirScanner('http://x', 'w.txt', cookie='a=1; junk; b=2')
        self.assertEqual(scanner._cookies(), {'a': '1', 'b': '2'})

    def test_no_cookie_yields_empty_jar(self):
        scanner = dir_scan.DirScanner('http://x', 'w.txt', cookie=None)
        self.assertEqual(scanner._cookies(), {})


class AttemptLogicTests(unittest.TestCase):
    """Exercises the counter/return-value logic of DirScanner.attempt using a
    stubbed requests.get so no network is touched."""
    def setUp(self):
        import contextlib

        class _FakeResp:
            def __init__(self, status_code, length):
                self.status_code = status_code
                self.content = b'x' * length

        self._fake_resp = _FakeResp
        self._real_get = dir_scan.requests.get

        def fake_get(url, cookies=None, timeout=None, allow_redirects=False):
            # Map the requested path to a canned status by suffix.
            if url.endswith('/admin'):
                return _FakeResp(200, 50)
            if url.endswith('/secret'):
                return _FakeResp(403, 10)
            return _FakeResp(404, 0)

        dir_scan.requests.get = fake_get
        self._scanner = dir_scan.DirScanner('http://x', 'w.txt', delay=0,
                                            threads=1, retries=0)

    def tearDown(self):
        dir_scan.requests.get = self._real_get

    def test_found_path_is_confirmed(self):
        ok, path, status, length = self._scanner.attempt('admin')
        self.assertTrue(ok)
        self.assertEqual(path, 'admin')
        self.assertEqual(status, 200)
        self.assertEqual(length, 50)
        self.assertEqual(self._scanner.counters['confirmed'], 1)
        self.assertEqual(self._scanner.counters['attempts'], 1)

    def test_404_is_a_failure_not_an_error(self):
        ok, path, status, length = self._scanner.attempt('nope')
        self.assertFalse(ok)
        self.assertEqual(status, 404)
        self.assertEqual(self._scanner.counters['failures'], 1)
        self.assertEqual(self._scanner.counters['errors'], 0)

    def test_403_counts_as_found_by_default(self):
        ok, path, status, length = self._scanner.attempt('secret')
        self.assertTrue(ok)
        self.assertEqual(status, 403)
        self.assertEqual(self._scanner.counters['confirmed'], 1)


if __name__ == '__main__':
    unittest.main()