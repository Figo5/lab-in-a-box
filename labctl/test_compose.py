"""Unit tests for labctl.compose — the docker compose wrapper + reachability.

Deterministic: `subprocess.run` (docker) and `socket.connect` (reachability)
are stubbed so no Docker and no network are required.
"""
import socket
import subprocess
import unittest
from unittest import mock

from labctl import compose
from labctl.config import ConfigError, LabConfig, Target


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=["docker", "compose"], returncode=returncode,
        stdout=stdout, stderr=stderr,
    )


class ComposeRunTests(unittest.TestCase):
    @mock.patch("labctl.compose.subprocess.run")
    def test_up_invokes_compose_up_d(self, run):
        run.return_value = _completed(0, "", "")
        compose.up()
        args, kwargs = run.call_args
        self.assertEqual(args[0][:3], ["docker", "compose", "up"])
        self.assertIn("-d", args[0])
        self.assertTrue(kwargs["capture_output"])
        self.assertTrue(kwargs["check"])

    @mock.patch("labctl.compose.subprocess.run")
    def test_up_raises_on_nonzero_returncode(self, run):
        run.return_value = _completed(1, "", "compose up failed: boom")
        with self.assertRaises(ConfigError) as cm:
            compose.up()
        self.assertIn("boom", str(cm.exception))

    @mock.patch("labctl.compose.subprocess.run")
    def test_up_translates_missing_docker_to_config_error(self, run):
        run.side_effect = FileNotFoundError("docker")
        with self.assertRaises(ConfigError) as cm:
            compose.up()
        self.assertIn("docker not found", str(cm.exception))

    @mock.patch("labctl.compose.subprocess.run")
    def test_down_without_purge(self, run):
        run.return_value = _completed(0, "", "")
        compose.down(purge=False)
        args, _ = run.call_args
        self.assertEqual(args[0], ["docker", "compose", "down"])

    @mock.patch("labctl.compose.subprocess.run")
    def test_down_with_purge_adds_v_flag(self, run):
        run.return_value = _completed(0, "", "")
        compose.down(purge=True)
        args, _ = run.call_args
        self.assertEqual(args[0], ["docker", "compose", "down", "-v"])

    @mock.patch("labctl.compose.subprocess.run")
    def test_exec_in_passes_dash_T_service_and_argv(self, run):
        run.return_value = _completed(0, "", "")
        compose.exec_in("ssh-lab", ["python3", "-c", "print(1)"])
        args, _ = run.call_args
        self.assertEqual(args[0],
                         ["docker", "compose", "exec", "-T", "ssh-lab", "python3", "-c", "print(1)"])


class PsTests(unittest.TestCase):
    @mock.patch("labctl.compose.subprocess.run")
    def test_ps_parses_json_array(self, run):
        run.return_value = _completed(
            0,
            '[{"Service":"dvwa","State":"running","Status":"Up (healthy)","Health":"healthy"}]',
            "",
        )
        result = compose.ps()
        self.assertEqual(result, {"dvwa": {"state": "running", "health": "healthy",
                                            "status": "Up (healthy)"}})

    @mock.patch("labctl.compose.subprocess.run")
    def test_ps_parses_ndjson_one_object_per_line(self, run):
        run.return_value = _completed(
            0,
            '{"Service":"a","State":"running","Status":"Up"}\n'
            '{"Service":"b","State":"exited","Status":"Exited (0)"}\n',
            "",
        )
        result = compose.ps()
        self.assertEqual(set(result), {"a", "b"})
        self.assertEqual(result["b"]["health"], "exited")

    @mock.patch("labctl.compose.subprocess.run")
    def test_ps_infers_health_from_status_when_health_absent(self, run):
        run.return_value = _completed(
            0, '[{"Service":"x","State":"running","Status":"Up (unhealthy)"}]', "",
        )
        result = compose.ps()
        self.assertEqual(result["x"]["health"], "unhealthy")

    @mock.patch("labctl.compose.subprocess.run")
    def test_ps_empty_stdout_returns_empty_dict(self, run):
        run.return_value = _completed(0, "", "")
        self.assertEqual(compose.ps(), {})

    @mock.patch("labctl.compose.subprocess.run")
    def test_ps_nonzero_returncode_returns_empty_dict(self, run):
        run.return_value = _completed(1, "", "error")
        self.assertEqual(compose.ps(), {})


class ReachableTests(unittest.TestCase):
    def test_reachable_false_for_nonpositive_port(self):
        self.assertFalse(compose.reachable("127.0.0.1", 0))
        self.assertFalse(compose.reachable("127.0.0.1", -1))

    @mock.patch("labctl.compose.socket.socket")
    def test_reachable_true_when_connect_succeeds(self, sock_cls):
        # `socket.socket(...)` is used as a context manager, so the object the
        # `with` block binds is __enter__'s return value. Make it the instance.
        instance = sock_cls.return_value
        instance.__enter__.return_value = instance
        instance.connect.return_value = None
        self.assertTrue(compose.reachable("127.0.0.1", 2222, timeout=1))
        instance.connect.assert_called_once_with(("127.0.0.1", 2222))
        instance.settimeout.assert_called_with(1)

    @mock.patch("labctl.compose.socket.socket")
    def test_reachable_false_on_oserror(self, sock_cls):
        instance = sock_cls.return_value
        instance.__enter__.return_value = instance
        instance.connect.side_effect = OSError("refused")
        self.assertFalse(compose.reachable("127.0.0.1", 2222, timeout=1))


class WaitUntilReadyTests(unittest.TestCase):
    def _cfg(self):
        return LabConfig(targets={"a": Target(name="a", port=2222)})

    @mock.patch("labctl.compose.reachable", return_value=True)
    @mock.patch("labctl.compose.ps")
    def test_returns_when_all_healthy_and_reachable(self, ps, reachable):
        ps.return_value = {"a": {"health": "healthy"}}
        cfg = self._cfg()
        out = compose.wait_until_ready(cfg, timeout=5)
        self.assertEqual(out["a"]["health"], "healthy")

    @mock.patch("labctl.compose.reachable", return_value=False)
    @mock.patch("labctl.compose.ps")
    @mock.patch("labctl.compose.time.sleep", return_value=None)
    def test_times_out_returning_last_snapshot(self, sleep, ps, reachable):
        # `timeout` of 0 is falsy, so wait_until_ready falls back to
        # config.boot_timeout_seconds (300) -- to terminate fast we drive
        # time.time() past the deadline on the first check by returning a
        # monotonic sequence that immediately exceeds it.
        ps.return_value = {"a": {"health": "healthy"}}
        cfg = self._cfg()
        # Fake clock: first call sets the deadline, every later call is far
        # past it, so the loop body runs at most once then exits.
        clock = iter([1_000_000.0, 1_000_000.0, 9_999_999.0])
        with mock.patch("labctl.compose.time.time", side_effect=lambda: next(clock)):
            out = compose.wait_until_ready(cfg, timeout=5)
        # reachable=False keeps the loop from returning early; the last ps()
        # snapshot is what's returned when the deadline is hit.
        self.assertEqual(out, {"a": {"health": "healthy"}})

    @mock.patch("labctl.compose.reachable", return_value=True)
    @mock.patch("labctl.compose.ps")
    @mock.patch("labctl.compose.time.sleep", return_value=None)
    def test_none_timeout_falls_back_to_boot_timeout_seconds(self, sleep, ps, reachable):
        # timeout=None -> `None or config.boot_timeout_seconds` uses the cfg's
        # boot_timeout_seconds; a one-shot clock keeps the loop from spinning.
        ps.return_value = {"a": {"health": "healthy"}}
        cfg = self._cfg()
        cfg.boot_timeout_seconds = 42
        clock = iter([1000.0, 1000.0, 10_000_000.0])
        with mock.patch("labctl.compose.time.time", side_effect=lambda: next(clock)):
            out = compose.wait_until_ready(cfg, timeout=None)
        self.assertEqual(out, {"a": {"health": "healthy"}})


if __name__ == "__main__":
    unittest.main()