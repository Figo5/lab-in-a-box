"""Integration test: labctl/brute.py's constructed command line -> tool's own parser.

Verifies that for every real lab.yaml target/tool_args combination,
labctl.brute._build_command() produces a command line that the target
tool's own parse_args(argv) accepts without an argparse error. No
subprocess is spawned and no live target is required -- this only proves
the generated flags are syntactically valid for that tool's parser.
"""
import pathlib
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))

from labctl.brute import _build_command  # noqa: E402
from labctl.config import BruteConfig, LabConfig, Target  # noqa: E402

import dvwa_brute  # noqa: E402
import http_login_brute  # noqa: E402


def _make_cfg():
    return LabConfig(brute=BruteConfig())


def _argv_for(target, tool):
    """Build the argv _run_real would pass to `tool`, minus the interpreter
    and script path (elements 0 and 1 of _build_command's output)."""
    cmd = _build_command(
        cfg=_make_cfg(),
        t=target,
        wordlist=REPO_ROOT / "wordlists" / "common.txt",
        usernames=REPO_ROOT / "wordlists" / "usernames.txt",
        tool=tool,
    )
    return cmd[2:]


class LabctlToToolFlagContractTests(unittest.TestCase):
    def test_dvwa_no_tool_args(self):
        # lab.yaml dvwa target: tool: ./tools/dvwa_brute.py, no tool_args.
        t = Target(name="dvwa", tool="./tools/dvwa_brute.py", tool_args=[])
        argv = _argv_for(t, "./tools/dvwa_brute.py")
        ns = dvwa_brute.parse_args(argv)  # must not raise SystemExit
        self.assertEqual(ns.host, t.host)

    def test_dvwa_tool_args_none(self):
        # Guards the `t.tool_args or []` fallback in _build_command.
        t = Target(name="dvwa", tool="./tools/dvwa_brute.py", tool_args=None)
        argv = _argv_for(t, "./tools/dvwa_brute.py")
        dvwa_brute.parse_args(argv)  # must not raise SystemExit

    def test_juice_shop_tool_args(self):
        # lab.yaml juice-shop target.
        t = Target(
            name="juice-shop",
            tool="./tools/http_login_brute.py",
            tool_args=["--path=/rest/user/login", "--user-field=email", "--user-suffix=@lab.local"],
        )
        argv = _argv_for(t, "./tools/http_login_brute.py")
        ns = http_login_brute.parse_args(argv)  # must not raise SystemExit
        self.assertEqual(ns.path, "/rest/user/login")
        self.assertEqual(ns.user_field, "email")
        self.assertEqual(ns.user_suffix, "@lab.local")

    def test_vuln_api_tool_args(self):
        # lab.yaml vuln-api target.
        t = Target(
            name="vuln-api",
            tool="./tools/http_login_brute.py",
            tool_args=["--path=/api/login", "--user-field=username"],
        )
        argv = _argv_for(t, "./tools/http_login_brute.py")
        ns = http_login_brute.parse_args(argv)  # must not raise SystemExit
        self.assertEqual(ns.path, "/api/login")
        self.assertEqual(ns.user_field, "username")
        self.assertEqual(ns.user_suffix, "")

    def test_unrecognized_flag_is_rejected(self):
        # Negative case: proves this test actually catches bad flags rather
        # than trivially passing regardless of tool_args content.
        t = Target(
            name="vuln-api",
            tool="./tools/http_login_brute.py",
            tool_args=["--nonexistent-flag"],
        )
        argv = _argv_for(t, "./tools/http_login_brute.py")
        with self.assertRaises(SystemExit):
            http_login_brute.parse_args(argv)


if __name__ == "__main__":
    unittest.main()
