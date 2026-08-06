"""Unit tests for labctl.seed — idempotent account creation per target.

Deterministic: HTTP `requests.post` and `compose.exec_in` are stubbed so no
live lab / Docker / network is required.
"""
import unittest
from unittest import mock

from labctl import seed
from labctl.config import LabConfig, Target


def _target(name, seed_user="labuser", seed_pass="labpass123", port=8080, **kw):
    return Target(name=name, seed_user=seed_user, seed_pass=seed_pass, port=port, **kw)


def _cfg(target):
    return LabConfig(targets={target.name: target})


class _Resp:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


class SeedAllTests(unittest.TestCase):
    def test_skipped_when_no_seed_user(self):
        t = _target("dvwa", seed_user=None)
        out = seed.seed_all(_cfg(t))
        self.assertEqual(out["dvwa"]["status"], "skipped")

    def test_unsupported_target_falls_through(self):
        t = _target("unknown-target")
        out = seed.seed_all(_cfg(t))
        self.assertEqual(out["unknown-target"]["status"], "skipped")
        self.assertIn("not implemented", out["unknown-target"]["detail"])

    def test_error_is_caught_and_per_target(self):
        t = _target("vuln-api")
        with mock.patch("labctl.seed._dispatch") as d:
            d.return_value = lambda cfg, t: (_ for _ in ()).throw(RuntimeError("boom"))
            out = seed.seed_all(_cfg(t))
        self.assertEqual(out["vuln-api"]["status"], "error")
        self.assertIn("boom", out["vuln-api"]["detail"])


class VulnApiTests(unittest.TestCase):
    def test_created_on_201(self):
        t = _target("vuln-api", port=8083)
        with mock.patch("labctl.seed.requests.post", return_value=_Resp(201)):
            out = seed._seed_vuln_api(_cfg(t), t)
        self.assertEqual(out, {"status": "created", "user": "labuser"})

    def test_exists_on_409(self):
        t = _target("vuln-api", port=8083)
        with mock.patch("labctl.seed.requests.post", return_value=_Resp(409)):
            out = seed._seed_vuln_api(_cfg(t), t)
        self.assertEqual(out, {"status": "exists", "user": "labuser"})

    def test_error_on_unexpected_status(self):
        t = _target("vuln-api", port=8083)
        with mock.patch("labctl.seed.requests.post", return_value=_Resp(500, "server down")):
            out = seed._seed_vuln_api(_cfg(t), t)
        self.assertEqual(out["status"], "error")
        self.assertIn("HTTP 500", out["detail"])

    def test_request_exception_returns_error(self):
        import requests
        t = _target("vuln-api", port=8083)
        with mock.patch("labctl.seed.requests.post",
                       side_effect=requests.RequestException("nope")):
            out = seed._seed_vuln_api(_cfg(t), t)
        self.assertEqual(out["status"], "error")
        self.assertIn("nope", out["detail"])


class JuiceShopTests(unittest.TestCase):
    def test_created_on_201(self):
        t = _target("juice-shop", port=8082)
        with mock.patch("labctl.seed.requests.post", return_value=_Resp(201)):
            out = seed._seed_juice_shop(_cfg(t), t)
        self.assertEqual(out["status"], "created")
        self.assertEqual(out["user"], "labuser@lab.local")

    def test_exists_on_400_or_409_or_already_text(self):
        t = _target("juice-shop", port=8082)
        with mock.patch("labctl.seed.requests.post",
                       return_value=_Resp(409, "user already exists")):
            out = seed._seed_juice_shop(_cfg(t), t)
        self.assertEqual(out["status"], "exists")


class SshLabTests(unittest.TestCase):
    def test_mismatch_when_env_differs_from_lab_yaml(self):
        t = _target("ssh-lab", seed_user="labuser", seed_pass="labpass123", port=2222)
        with mock.patch.dict("labctl.seed.os.environ",
                            {"SSH_SEED_USER": "other", "SSH_SEED_PASS": "x"}, clear=False):
            out = seed._seed_ssh_lab(_cfg(t), t)
        self.assertEqual(out["status"], "mismatch")
        self.assertIn("other/x", out["detail"])

    @mock.patch("labctl.seed.compose.exec_in")
    def test_ok_when_env_matches_and_volume_seeded(self, exec_in):
        t = _target("ssh-lab", seed_user="labuser", seed_pass="labpass123", port=2222)
        with mock.patch.dict("labctl.seed.os.environ",
                            {"SSH_SEED_USER": "labuser", "SSH_SEED_PASS": "labpass123"},
                            clear=False):
            out = seed._seed_ssh_lab(_cfg(t), t)
        self.assertEqual(out["status"], "ok")
        self.assertIn("env matched", out["detail"])
        exec_in.assert_called_once()

    @mock.patch("labctl.seed.compose.exec_in", side_effect=Exception("container down"))
    def test_ok_when_env_matches_but_container_down(self, exec_in):
        t = _target("ssh-lab", seed_user="labuser", seed_pass="labpass123", port=2222)
        with mock.patch.dict("labctl.seed.os.environ",
                            {"SSH_SEED_USER": "labuser", "SSH_SEED_PASS": "labpass123"},
                            clear=False):
            out = seed._seed_ssh_lab(_cfg(t), t)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["detail"], "env matched")


class DvwaTests(unittest.TestCase):
    @mock.patch("labctl.seed.compose.exec_in")
    def test_created_when_first_mysql_succeeds(self, exec_in):
        import subprocess
        t = _target("dvwa", port=8081)
        exec_in.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        out = seed._seed_dvwa(_cfg(t), t)
        self.assertEqual(out["status"], "created")
        self.assertEqual(out["user"], "labuser")
        exec_in.assert_called_once()  # short-circuits on first success

    @mock.patch("labctl.seed.compose.exec_in")
    def test_unsupported_when_all_mysql_attempts_fail(self, exec_in):
        import subprocess
        t = _target("dvwa", port=8081)
        exec_in.return_value = subprocess.CompletedProcess(args=[], returncode=1)
        out = seed._seed_dvwa(_cfg(t), t)
        self.assertEqual(out["status"], "unsupported")
        self.assertEqual(exec_in.call_count, 3)  # tried all three mysql arg sets
        self.assertIn("admin/password", out["detail"])


if __name__ == "__main__":
    unittest.main()