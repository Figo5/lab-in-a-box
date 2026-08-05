"""Flag-contract tests for http_login_brute.py's argument parser.

Verifies parse_args(argv) accepts the flags labctl/brute.py._run_real
constructs, including the per-target `tool_args` extras from lab.yaml
(juice-shop: --path/--user-field/--user-suffix; vuln-api: --path/--user-field).
"""
import unittest

import http_login_brute


class ParseArgsTests(unittest.TestCase):
    def test_accepts_labctl_generated_base_flags(self):
        ns = http_login_brute.parse_args([
            '--host', '127.0.0.1',
            '--port', '8083',
            '--usernames', 'wordlists/usernames.txt',
            '--passwords', 'wordlists/common.txt',
            '--threads', '4',
            '--delay', '0.05',
            '--timeout', '10',
        ])
        self.assertEqual(ns.host, '127.0.0.1')
        self.assertEqual(ns.port, 8083)
        self.assertEqual(ns.threads, 4)
        self.assertEqual(ns.delay, 0.05)
        self.assertEqual(ns.timeout, 10.0)

    def test_accepts_vuln_api_tool_args(self):
        # lab.yaml vuln-api target: tool_args = [--path=/api/login, --user-field=username]
        ns = http_login_brute.parse_args([
            '--host', '127.0.0.1', '--port', '8083',
            '--usernames', 'u.txt', '--passwords', 'p.txt',
            '--path=/api/login', '--user-field=username',
        ])
        self.assertEqual(ns.path, '/api/login')
        self.assertEqual(ns.user_field, 'username')
        self.assertEqual(ns.user_suffix, '')

    def test_accepts_juice_shop_tool_args(self):
        # lab.yaml juice-shop target: --path=/rest/user/login --user-field=email --user-suffix=@lab.local
        ns = http_login_brute.parse_args([
            '--host', '127.0.0.1', '--port', '8082',
            '--usernames', 'u.txt', '--passwords', 'p.txt',
            '--path=/rest/user/login', '--user-field=email', '--user-suffix=@lab.local',
        ])
        self.assertEqual(ns.path, '/rest/user/login')
        self.assertEqual(ns.user_field, 'email')
        self.assertEqual(ns.user_suffix, '@lab.local')

    def test_host_usernames_passwords_are_required(self):
        with self.assertRaises(SystemExit):
            http_login_brute.parse_args(['--usernames', 'u.txt', '--passwords', 'p.txt'])

    def test_path_and_user_field_have_documented_defaults(self):
        ns = http_login_brute.parse_args([
            '--host', 'x', '--usernames', 'u.txt', '--passwords', 'p.txt',
        ])
        self.assertEqual(ns.path, '/api/login')
        self.assertEqual(ns.user_field, 'username')
        self.assertEqual(ns.user_suffix, '')
        self.assertEqual(ns.port, 80)


if __name__ == '__main__':
    unittest.main()
