"""Flag-contract tests for dvwa_brute.py's argument parser.

Verifies parse_args(argv) accepts the flags labctl/brute.py._run_real
actually constructs (see labctl/brute.py) without executing the tool.
"""
import unittest

import dvwa_brute


class ParseArgsTests(unittest.TestCase):
    def test_accepts_labctl_generated_flags(self):
        ns = dvwa_brute.parse_args([
            '--host', '127.0.0.1',
            '--port', '8081',
            '--usernames', 'wordlists/usernames.txt',
            '--passwords', 'wordlists/common.txt',
            '--threads', '4',
            '--delay', '0.05',
            '--timeout', '10',
        ])
        self.assertEqual(ns.host, '127.0.0.1')
        self.assertEqual(ns.port, 8081)
        self.assertEqual(ns.usernames, 'wordlists/usernames.txt')
        self.assertEqual(ns.passwords, 'wordlists/common.txt')
        self.assertEqual(ns.threads, 4)
        self.assertEqual(ns.delay, 0.05)
        self.assertEqual(ns.timeout, 10.0)

    def test_host_usernames_passwords_are_required(self):
        with self.assertRaises(SystemExit):
            dvwa_brute.parse_args(['--usernames', 'u.txt', '--passwords', 'p.txt'])
        with self.assertRaises(SystemExit):
            dvwa_brute.parse_args(['--host', 'x', '--passwords', 'p.txt'])
        with self.assertRaises(SystemExit):
            dvwa_brute.parse_args(['--host', 'x', '--usernames', 'u.txt'])

    def test_port_and_numeric_flags_have_documented_defaults(self):
        ns = dvwa_brute.parse_args([
            '--host', 'x', '--usernames', 'u.txt', '--passwords', 'p.txt',
        ])
        self.assertEqual(ns.port, 80)
        self.assertEqual(ns.threads, 1)
        self.assertEqual(ns.delay, 0.5)
        self.assertEqual(ns.timeout, 10.0)
        self.assertEqual(ns.retries, 1)

    def test_retries_flag_is_accepted(self):
        ns = dvwa_brute.parse_args([
            '--host', 'x', '--usernames', 'u.txt', '--passwords', 'p.txt',
            '--retries', '3',
        ])
        self.assertEqual(ns.retries, 3)


if __name__ == '__main__':
    unittest.main()
