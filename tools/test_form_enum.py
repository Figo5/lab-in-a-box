"""Flag-contract tests for form_enum.py's argument parser and HTML parsing.

Verifies parse_args(argv) accepts the flags
browser-extension/pageprobe/lib/commands.js's buildFormEnumCommand() actually
generates, and that parse_forms() extracts fields from simple form markup.
"""
import unittest

import form_enum


class ParseArgsTests(unittest.TestCase):
    def test_accepts_commands_js_generated_flags(self):
        ns = form_enum.parse_args([
            '--url', 'http://dvwa.local/vulnerabilities/brute/index.php',
            '--cookie', 'PHPSESSID=abc',
            '--json', 'report.json',
        ])
        self.assertEqual(ns.url, 'http://dvwa.local/vulnerabilities/brute/index.php')
        self.assertEqual(ns.cookie, 'PHPSESSID=abc')
        self.assertEqual(ns.json, 'report.json')

    def test_accepts_minimal_command_without_cookie(self):
        # buildFormEnumCommand() always emits --url and --json; --cookie is conditional.
        ns = form_enum.parse_args(['--url', 'http://example.com/page.php', '--json', 'report.json'])
        self.assertIsNone(ns.cookie)

    def test_url_is_required(self):
        with self.assertRaises(SystemExit):
            form_enum.parse_args(['--json', 'report.json'])


class ParseFormsTests(unittest.TestCase):
    def test_parses_a_simple_login_form(self):
        html = '''
        <form action="/login.php" method="POST">
          <input type="text" name="username" value="">
          <input type="password" name="password" value="">
          <input type="hidden" name="user_token" value="abc123">
          <input type="submit" name="Login" value="Login">
        </form>
        '''
        forms = form_enum.parse_forms(html)
        self.assertEqual(len(forms), 1)
        self.assertEqual(forms[0]['action'], '/login.php')
        self.assertEqual(forms[0]['method'], 'POST')
        names = [f['name'] for f in forms[0]['fields']]
        self.assertEqual(names, ['username', 'password', 'user_token', 'Login'])

    def test_defaults_method_to_get_when_absent(self):
        html = '<form action="/search"><input type="text" name="q"></form>'
        forms = form_enum.parse_forms(html)
        self.assertEqual(forms[0]['method'], 'GET')

    def test_no_forms_on_a_page_without_any(self):
        self.assertEqual(form_enum.parse_forms('<html><body>hello</body></html>'), [])

    def test_parses_multiple_forms(self):
        html = '<form action="/a"><input name="x"></form><form action="/b"><input name="y"></form>'
        forms = form_enum.parse_forms(html)
        self.assertEqual(len(forms), 2)
        self.assertEqual(forms[0]['action'], '/a')
        self.assertEqual(forms[1]['action'], '/b')


if __name__ == '__main__':
    unittest.main()
