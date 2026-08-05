"""Flag-contract tests for test.py's argument parser.

Verifies parse_args(argv) accepts the flags
browser-extension/pageprobe/lib/commands.js's buildTestPyCommand() actually
generates, without executing the tool.
"""
import unittest

import test as test_py  # local tools/test.py, not the stdlib `test` package


class ParseArgsTests(unittest.TestCase):
    def test_accepts_commands_js_generated_flags(self):
        # Mirrors the exact flags buildTestPyCommand() emits for a login
        # form with a CSRF field and a named submit control.
        ns = test_py.parse_args([
            '--url', 'http://dvwa.local/vulnerabilities/brute/index.php',
            '--method', 'GET',
            '--usernames', 'usernames.txt',
            '--passwords', 'passwords.txt',
            '--user-field', 'username',
            '--pass-field', 'password',
            '--csrf-field', 'user_token',
            '--csrf-url', 'http://dvwa.local/vulnerabilities/brute/index.php',
            '--extra-field', 'Login=Login',
            '--cookie', 'PHPSESSID=abc; security=low',
        ])
        self.assertEqual(ns.url, 'http://dvwa.local/vulnerabilities/brute/index.php')
        self.assertEqual(ns.method, 'GET')
        self.assertEqual(ns.user_field, 'username')
        self.assertEqual(ns.pass_field, 'password')
        self.assertEqual(ns.csrf_field, 'user_token')
        self.assertEqual(ns.extra_field, ['Login=Login'])
        self.assertEqual(ns.cookie, 'PHPSESSID=abc; security=low')

    def test_accepts_minimal_command_without_login_or_csrf(self):
        # buildTestPyCommand() always emits --url/--method/--usernames/--passwords;
        # user-field/pass-field/csrf-field/csrf-url/cookie/dry-run are conditional.
        ns = test_py.parse_args([
            '--url', 'http://example.com/search',
            '--method', 'GET',
            '--usernames', 'usernames.txt',
            '--passwords', 'passwords.txt',
        ])
        self.assertIsNone(ns.user_field)
        self.assertIsNone(ns.csrf_field)
        self.assertIsNone(ns.cookie)
        self.assertFalse(ns.dry_run)

    def test_accepts_multiple_extra_fields(self):
        ns = test_py.parse_args([
            '--url', 'http://example.com/f', '--method', 'POST',
            '--usernames', 'u.txt', '--passwords', 'p.txt',
            '--extra-field', 'form_id=1', '--extra-field', 'csrf_extra=x',
        ])
        self.assertEqual(ns.extra_field, ['form_id=1', 'csrf_extra=x'])

    def test_dry_run_flag_is_accepted(self):
        ns = test_py.parse_args([
            '--url', 'http://example.com/f', '--method', 'GET',
            '--usernames', 'u.txt', '--passwords', 'p.txt', '--dry-run',
        ])
        self.assertTrue(ns.dry_run)

    def test_url_usernames_passwords_are_required(self):
        with self.assertRaises(SystemExit):
            test_py.parse_args(['--usernames', 'u.txt', '--passwords', 'p.txt'])
        with self.assertRaises(SystemExit):
            test_py.parse_args(['--url', 'http://x', '--passwords', 'p.txt'])
        with self.assertRaises(SystemExit):
            test_py.parse_args(['--url', 'http://x', '--usernames', 'u.txt'])

    def test_parse_extra_fields_splits_name_value_pairs(self):
        fields = test_py.parse_extra_fields(['a=1', 'b=hello world', 'c='])
        self.assertEqual(fields, {'a': '1', 'b': 'hello world', 'c': ''})


if __name__ == '__main__':
    unittest.main()
