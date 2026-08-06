"""Unit tests for labctl.security_level — DVWA level application.

Deterministic: HTTP `requests` calls are stubbed via a fake session so no
live DVWA / network is required.
"""
import unittest
from unittest import mock

from labctl import security_level
from labctl.config import LabConfig, Target


def _cfg():
    return LabConfig(targets={"dvwa": Target(name="dvwa", port=8081)})


class _Resp:
    def __init__(self, text="", status_code=200, headers=None):
        self.text = text
        self.status_code = status_code
        self.headers = headers or {}


class ApplyTests(unittest.TestCase):
    def test_invalid_level_rejected(self):
        out = security_level.apply(_cfg(), "dvwa", "banana")
        self.assertFalse(out["ok"])
        self.assertIn("invalid level", out["reason"])

    def test_non_dvwa_target_not_applicable(self):
        out = security_level.apply(_cfg(), "ssh-lab", "low")
        self.assertFalse(out["ok"])
        self.assertIn("does not expose a security-level setting", out["reason"])

    def test_apply_dispatches_to_dvwa(self):
        with mock.patch("labctl.security_level._apply_dvwa",
                       return_value={"ok": True, "level": "low"}) as d:
            out = security_level.apply(_cfg(), "dvwa", "low")
        self.assertTrue(out["ok"])
        d.assert_called_once()


class ApplyDvwaTests(unittest.TestCase):
    def _session_seq(self, responses):
        """A fake Session that returns canned responses in order from get/post."""
        class _FakeSession:
            def __init__(self):
                self.cookies = {}
                self._iter = iter(responses)
            def get(self, url, timeout=None, **kw):
                return next(self._iter)
            def post(self, url, data=None, timeout=None, **kw):
                return next(self._iter)
        return _FakeSession()

    def test_success_path_sets_level(self):
        # login GET (token) -> login POST (302 index) -> security GET (token)
        # -> security POST (page showing "low") -> confirmation GET (low)
        responses = [
            _Resp('<input name="user_token" value="T1">', 200),
            _Resp("", 302, headers={"Location": "index.php"}),
            _Resp('<input name="user_token" value="T2">currently: <em>low</em>', 200),
            _Resp("saved", 200),
            _Resp("currently: <em>low</em>", 200),
        ]
        sess = self._session_seq(responses)
        with mock.patch("labctl.security_level.requests.Session", return_value=sess):
            out = security_level._apply_dvwa(_cfg(), "low")
        self.assertTrue(out["ok"])
        self.assertEqual(out["level"], "low")

    def test_login_failure_runs_setup_then_retries(self):
        # 1st login GET (token) -> 1st login POST (no 302) ->
        # ensure_dvwa_setup patched True -> 2nd login GET (token) ->
        # 2nd login POST (302 index) -> security GET (token) -> security POST (low)
        # -> confirmation GET (low)
        responses = [
            _Resp('<input name="user_token" value="T1">', 200),
            _Resp("Login failed", 200, headers={"Location": ""}),
            _Resp('<input name="user_token" value="T2">', 200),
            _Resp("", 302, headers={"Location": "index.php"}),
            _Resp('<input name="user_token" value="T3">', 200),
            _Resp("saved", 200),
            _Resp("currently: <em>low</em>", 200),
        ]
        sess = self._session_seq(responses)
        with mock.patch("labctl.security_level.requests.Session", return_value=sess), \
             mock.patch("labctl.security_level.ensure_dvwa_setup", return_value=True):
            out = security_level._apply_dvwa(_cfg(), "low")
        self.assertTrue(out["ok"])

    def test_login_failure_after_setup_reports_error(self):
        responses = [
            _Resp('<input name="user_token" value="T1">', 200),
            _Resp("Login failed", 200, headers={"Location": ""}),
            _Resp('<input name="user_token" value="T2">', 200),
            _Resp("Login failed", 200, headers={"Location": ""}),
        ]
        sess = self._session_seq(responses)
        with mock.patch("labctl.security_level.requests.Session", return_value=sess), \
             mock.patch("labctl.security_level.ensure_dvwa_setup", return_value=True):
            out = security_level._apply_dvwa(_cfg(), "low")
        self.assertFalse(out["ok"])
        self.assertIn("DVWA login failed", out["reason"])

    def test_setup_failure_reports_error(self):
        responses = [
            _Resp('<input name="user_token" value="T1">', 200),
            _Resp("Login failed", 200, headers={"Location": ""}),
        ]
        sess = self._session_seq(responses)
        with mock.patch("labctl.security_level.requests.Session", return_value=sess), \
             mock.patch("labctl.security_level.ensure_dvwa_setup", return_value=False):
            out = security_level._apply_dvwa(_cfg(), "low")
        self.assertFalse(out["ok"])
        self.assertIn("setup failed", out["reason"])

    def test_missing_csrf_on_security_page_reports_error(self):
        responses = [
            _Resp('<input name="user_token" value="T1">', 200),
            _Resp("", 302, headers={"Location": "index.php"}),
            _Resp("no token here", 200),
        ]
        sess = self._session_seq(responses)
        with mock.patch("labctl.security_level.requests.Session", return_value=sess):
            out = security_level._apply_dvwa(_cfg(), "low")
        self.assertFalse(out["ok"])
        self.assertIn("CSRF token", out["reason"])

    def test_level_mismatch_reports_actual(self):
        responses = [
            _Resp('<input name="user_token" value="T1">', 200),
            _Resp("", 302, headers={"Location": "index.php"}),
            _Resp('<input name="user_token" value="T2">', 200),
            _Resp("currently: <em>high</em>", 200),
            _Resp("currently: <em>high</em>", 200),
        ]
        sess = self._session_seq(responses)
        with mock.patch("labctl.security_level.requests.Session", return_value=sess):
            out = security_level._apply_dvwa(_cfg(), "low")
        self.assertFalse(out["ok"])
        self.assertEqual(out["level"], "low")
        self.assertIn("'high'", out["reason"])

    def test_request_exception_reports_unreachable(self):
        import requests
        class _FakeSession:
            def __init__(self): self.cookies = {}
            def get(self, *a, **k): raise requests.RequestException("nope")
            def post(self, *a, **k): raise requests.RequestException("nope")
        with mock.patch("labctl.security_level.requests.Session", return_value=_FakeSession()):
            out = security_level._apply_dvwa(_cfg(), "low")
        self.assertFalse(out["ok"])
        self.assertIn("not reachable", out["reason"])


class EnsureDvwaSetupTests(unittest.TestCase):
    def test_no_setup_form_means_already_setup(self):
        class _Sess:
            def get(self, url, timeout=None): return _Resp("no form")
        with mock.patch("labctl.security_level.requests.Session", return_value=_Sess()):
            self.assertTrue(security_level.ensure_dvwa_setup(_cfg()))

    def test_posts_create_db_when_token_present(self):
        class _Sess:
            def get(self, url, timeout=None):
                return _Resp('<input name="user_token" value="TKN">')
            def post(self, url, data=None, timeout=None):
                self.last_data = data
                return _Resp("Setup successful")
        s = _Sess()
        with mock.patch("labctl.security_level.requests.Session", return_value=s):
            ok = security_level.ensure_dvwa_setup(_cfg())
        self.assertTrue(ok)
        self.assertEqual(s.last_data["create_db"], "Create / Reset Database")
        self.assertEqual(s.last_data["user_token"], "TKN")

    def test_request_exception_returns_false(self):
        import requests
        class _Sess:
            def get(self, url, timeout=None): raise requests.RequestException("x")
        with mock.patch("labctl.security_level.requests.Session", return_value=_Sess()):
            self.assertFalse(security_level.ensure_dvwa_setup(_cfg()))


class HelperRegexTests(unittest.TestCase):
    def test_user_token_extraction(self):
        self.assertEqual(
            security_level._user_token('<input name="user_token" value="abc123">'),
            "abc123",
        )
        self.assertIsNone(security_level._user_token("no token"))

    def test_current_level_extraction(self):
        self.assertEqual(
            security_level._current_level("currently: <em>medium</em>"),
            "medium",
        )
        self.assertIsNone(security_level._current_level("nothing here"))


if __name__ == "__main__":
    unittest.main()