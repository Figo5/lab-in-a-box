"""Unit tests for labctl.report — run-dir aggregation into markdown/HTML.

Deterministic: `compose.ps` and `compose.reachable` are stubbed so no Docker
and no network are required.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from labctl import report
from labctl.config import LabConfig, Target


def _cfg():
    return LabConfig(targets={
        "dvwa": Target(name="dvwa", port=8081, security_level="medium"),
        "ssh-lab": Target(name="ssh-lab", port=2222),
    })


class MaskTests(unittest.TestCase):
    def test_empty_returns_dash(self):
        self.assertEqual(report.mask(""), "-")
        self.assertEqual(report.mask(None), "-")

    def test_short_password_fully_masked(self):
        self.assertEqual(report.mask("ab"), "**")
        self.assertEqual(report.mask("abcd"), "****")

    def test_long_password_keeps_first_two_and_last_two(self):
        self.assertEqual(report.mask("supersecret"), "su*******et")
        # length 11 -> 2 + (11-4)=7 stars + 2
        self.assertEqual(report.mask("labpass123"), "la******23")


class CollectTests(unittest.TestCase):
    def test_collect_reads_run_dir_json_and_status(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = Path(d)
            (run_dir / "meta.json").write_text(json.dumps({"created": "2026-08-05T12:00:00",
                                                            "network": "labnet"}))
            (run_dir / "levels.json").write_text(json.dumps({"dvwa": {"level": "medium",
                                                                       "at": "t"}}))
            (run_dir / "seeds.json").write_text(json.dumps({"dvwa": {"user": "labuser",
                                                                      "status": "created"}}))
            (run_dir / "ssh-lab-brute.json").write_text(json.dumps({
                "attempts": 70, "successes": [{"username": "labuser", "password": "labpass123"}],
                "mock": False, "wordlist": "wordlists/common.txt",
                "started": "s", "ended": "e",
            }))
            with mock.patch("labctl.report.compose.ps", return_value={}), \
                 mock.patch("labctl.report.compose.reachable", return_value=True):
                data = report._collect(_cfg(), run_dir)
        self.assertEqual(data["meta"]["network"], "labnet")
        self.assertEqual(data["levels"]["dvwa"]["level"], "medium")
        self.assertEqual(data["seeds"]["dvwa"]["status"], "created")
        self.assertIn("ssh-lab", data["brute"])
        self.assertEqual(data["brute"]["ssh-lab"]["attempts"], 70)
        self.assertEqual(len(data["status_rows"]), 2)
        self.assertTrue(data["status_rows"][0]["reachable"])
        self.assertEqual(data["configured_levels"]["dvwa"], "medium")

    def test_collect_tolerates_missing_json_files(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = Path(d)
            with mock.patch("labctl.report.compose.ps", return_value={}), \
                 mock.patch("labctl.report.compose.reachable", return_value=False):
                data = report._collect(_cfg(), run_dir)
        self.assertEqual(data["meta"], {})
        self.assertEqual(data["seeds"], {})
        self.assertEqual(data["brute"], {})
        self.assertFalse(data["status_rows"][0]["reachable"])


class RenderTests(unittest.TestCase):
    def test_render_writes_markdown_and_optionally_html(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = Path(d)
            (run_dir / "meta.json").write_text(json.dumps({"created": "c", "network": "labnet"}))
            with mock.patch("labctl.report.compose.ps", return_value={}), \
                 mock.patch("labctl.report.compose.reachable", return_value=True):
                md_path = report.render(_cfg(), run_dir, html=True)
            md = (run_dir / "report.md").read_text()
            self.assertIn("# Lab-in-a-Box — Run Report", md)
            self.assertIn("## Targets", md)
            self.assertIn("## Security levels", md)
            self.assertIn("## Seeded accounts", md)
            self.assertIn("## Brute-force runs", md)
            self.assertTrue((run_dir / "report.html").exists())
            html = (run_dir / "report.html").read_text()
            self.assertIn("Lab-in-a-Box — Run Report", html)
            self.assertIn("<table>", html)

    def test_render_markdown_only_by_default(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = Path(d)
            with mock.patch("labctl.report.compose.ps", return_value={}), \
                 mock.patch("labctl.report.compose.reachable", return_value=False):
                report.render(_cfg(), run_dir, html=False)
            self.assertTrue((run_dir / "report.md").exists())
            self.assertFalse((run_dir / "report.html").exists())

    def test_markdown_masks_passwords_in_successes(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir = Path(d)
            (run_dir / "meta.json").write_text("{}")
            (run_dir / "ssh-lab-brute.json").write_text(json.dumps({
                "attempts": 1, "successes": [{"username": "labuser", "password": "labpass123"}],
                "mock": False, "wordlist": "w", "started": "s", "ended": "e",
            }))
            with mock.patch("labctl.report.compose.ps", return_value={}), \
                 mock.patch("labctl.report.compose.reachable", return_value=True):
                report.render(_cfg(), run_dir, html=False)
            md = (run_dir / "report.md").read_text()
            # Masked form: la******23 (6 stars for a 10-char password), never raw.
            self.assertIn("la******23", md)
            self.assertNotIn("labpass123", md)


if __name__ == "__main__":
    unittest.main()