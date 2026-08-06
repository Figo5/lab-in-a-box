"""Unit tests for labctl.cli — the click command line.

Deterministic: `compose`, `seed`, `brute`, `security_level`, and `report`
internals are stubbed so no Docker / network / live lab is required. Uses
click's CliRunner to drive the group as a real CLI would.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import click
from click.testing import CliRunner

import labctl
from labctl import cli
from labctl.config import ConfigError, LabConfig, Target


def _cfg():
    return LabConfig(targets={
        "dvwa": Target(name="dvwa", port=8081, security_level="medium",
                       seed_user="labuser", seed_pass="labpass123"),
        "ssh-lab": Target(name="ssh-lab", port=2222,
                          seed_user="labuser", seed_pass="labpass123"),
    })


class _GroupTest(unittest.TestCase):
    """Base that builds a `cli` group whose config is the fixed _cfg() above,
    bypassing the real load()."""
    def _runner(self):
        cfg = _cfg()
        # Re-declare the group so the ctx.obj["config"] is the fixed config.
        @click.group()
        @click.pass_context
        def fixed_cli(ctx):
            ctx.ensure_object(dict)
            ctx.obj["config"] = cfg
        fixed_cli.add_command(cli.up)
        fixed_cli.add_command(cli.down)
        fixed_cli.add_command(cli.status)
        fixed_cli.add_command(cli.set_level)
        fixed_cli.add_command(cli.seed)
        fixed_cli.add_command(cli.run_brute)
        fixed_cli.add_command(cli.report)
        return CliRunner(), fixed_cli


class StatusTests(_GroupTest):
    def test_status_prints_target_table(self):
        runner, grp = self._runner()
        with mock.patch("labctl.cli.compose.ps", return_value={
                "dvwa": {"state": "running", "health": "healthy", "status": "Up"},
        }), mock.patch("labctl.cli.compose.reachable", return_value=True):
            r = runner.invoke(grp, ["status"])
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("dvwa", r.output)
        self.assertIn("healthy", r.output)
        self.assertIn("yes", r.output)


class UpTests(_GroupTest):
    def test_up_success_writes_meta_and_reports_ready(self):
        runner, grp = self._runner()
        # wait_until_ready must report every target as healthy, or the
        # all(...)==ready gate in cli.up trips and exits nonzero.
        with mock.patch("labctl.cli.compose.up") as up, \
             mock.patch("labctl.cli.compose.wait_until_ready",
                       return_value={"dvwa": {"health": "healthy"},
                                      "ssh-lab": {"health": "healthy"}}) as wait, \
             mock.patch("labctl.cli.compose.reachable", return_value=True):
            r = runner.invoke(grp, ["up"])
        self.assertEqual(r.exit_code, 0, r.output)
        up.assert_called_once()
        wait.assert_called_once()
        self.assertIn("All targets ready", r.output)

    def test_up_exits_nonzero_when_not_ready(self):
        runner, grp = self._runner()
        with mock.patch("labctl.cli.compose.up"), \
             mock.patch("labctl.cli.compose.wait_until_ready",
                       return_value={"dvwa": {"health": "starting"}}), \
             mock.patch("labctl.cli.compose.reachable", return_value=False):
            r = runner.invoke(grp, ["up"])
        self.assertNotEqual(r.exit_code, 0)
        self.assertIn("not ready", r.output.lower())


class SetLevelTests(_GroupTest):
    def test_set_level_unknown_target_errors(self):
        runner, grp = self._runner()
        r = runner.invoke(grp, ["set-level", "nope", "low"])
        self.assertNotEqual(r.exit_code, 0)
        # cfg.get("nope") raises ConfigError; only main() converts that to a
        # ClickException, so under the CliRunner it surfaces as r.exception.
        self.assertIsInstance(r.exception, ConfigError)

    def test_set_level_applies_and_records(self):
        runner, grp = self._runner()
        with mock.patch("labctl.cli.security_level.apply",
                       return_value={"ok": True, "level": "low"}) as apply:
            r = runner.invoke(grp, ["set-level", "dvwa", "low"])
        self.assertEqual(r.exit_code, 0, r.output)
        apply.assert_called_once()
        self.assertIn("set to low", r.output)

    def test_set_level_invalid_choice_rejected(self):
        runner, grp = self._runner()
        r = runner.invoke(grp, ["set-level", "dvwa", "banana"])
        self.assertNotEqual(r.exit_code, 0)


class SeedTests(_GroupTest):
    def test_seed_writes_seeds_json_and_table(self):
        runner, grp = self._runner()
        with mock.patch("labctl.cli.seed_mod.seed_all",
                       return_value={"ssh-lab": {"user": "labuser", "status": "created",
                                                  "detail": ""}}):
            r = runner.invoke(grp, ["seed"])
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("labuser", r.output)
        self.assertIn("created", r.output)


class RunBruteTests(_GroupTest):
    def test_run_brute_unknown_target_errors(self):
        runner, grp = self._runner()
        r = runner.invoke(grp, ["run-brute", "--target", "nope"])
        self.assertNotEqual(r.exit_code, 0)
        self.assertIsInstance(r.exception, ConfigError)

    def test_run_brute_writes_result_json(self):
        runner, grp = self._runner()
        wordlist = Path(tempfile.gettempdir()) / "wl.txt"
        wordlist.write_text("labpass123\n")
        with mock.patch("labctl.cli.brute_mod.run", return_value={
                "attempts": 1, "successes": [{"username": "labuser", "password": "labpass123"}],
                "mock": True, "started": "s", "ended": "e", "host": "127.0.0.1",
                "port": 2222, "target": "ssh-lab", "wordlist": str(wordlist),
        }), mock.patch.object(LabConfig, "resolve_wordlist", return_value=wordlist), \
             mock.patch.object(LabConfig, "resolve_usernames", return_value=wordlist), \
             mock.patch("labctl.cli._active_run_dir", return_value=Path(tempfile.gettempdir())):
            r = runner.invoke(grp, ["run-brute", "--target", "ssh-lab"])
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("attempts=1", r.output)
        self.assertIn("la******23", r.output)  # masked password


class ReportTests(_GroupTest):
    def test_report_invokes_render(self):
        runner, grp = self._runner()
        with mock.patch("labctl.cli.report_mod.render", return_value=Path("/tmp/report.md")) as render, \
             mock.patch("labctl.cli._latest_run_dir", return_value=Path(tempfile.gettempdir())):
            # make the dir "exist" for the existence check
            with mock.patch.object(Path, "exists", return_value=True):
                r = runner.invoke(grp, ["report"])
        self.assertEqual(r.exit_code, 0, r.output)
        render.assert_called_once()
        self.assertIn("Report written", r.output)

    def test_report_no_run_errors(self):
        runner, grp = self._runner()
        with mock.patch("labctl.cli._latest_run_dir", return_value=None):
            r = runner.invoke(grp, ["report"])
        self.assertNotEqual(r.exit_code, 0)
        self.assertIn("no run to report", r.output)


if __name__ == "__main__":
    unittest.main()