"""Thin wrapper around `docker compose` plus host-level reachability checks."""

from __future__ import annotations

import json
import socket
import subprocess
import time

from .config import PROJECT_ROOT, ConfigError, LabConfig

HEALTH_INTERVAL = 3


def _compose(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["docker", "compose", *args],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=check,
        )
    except FileNotFoundError as e:
        raise ConfigError(
            "docker not found on PATH — is Docker installed and running?"
        ) from e


def up() -> None:
    """docker compose up -d (builds local images, pulls remote ones)."""
    proc = _compose("up", "-d")
    if proc.returncode != 0:
        raise ConfigError(f"docker compose up failed:\n{proc.stderr.strip()}")


def down(purge: bool = False) -> None:
    args = ["down"]
    if purge:
        args.append("-v")
    proc = _compose(*args)
    if proc.returncode != 0:
        raise ConfigError(f"docker compose down failed:\n{proc.stderr.strip()}")


def ps() -> dict:
    """Return {service: {state, health, status}} from `docker compose ps --format json`."""
    proc = _compose("ps", "--format", "json", check=False)
    out = proc.stdout.strip()
    if proc.returncode != 0 or not out:
        return {}
    records: list = []
    try:
        parsed = json.loads(out)
        records = parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        # Some compose versions emit NDJSON — one object per line.
        for line in out.splitlines():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    result: dict = {}
    for r in records:
        service = r.get("Service") or r.get("Name")
        if not service:
            continue
        state = r.get("State") or ""
        status = r.get("Status") or ""
        health = r.get("Health")
        if health is None:
            if "(healthy)" in status:
                health = "healthy"
            elif "(unhealthy)" in status:
                health = "unhealthy"
            elif "exited" in status.lower():
                health = "exited"
        result[service] = {"state": state, "health": health, "status": status}
    return result


def reachable(host: str, port: int, timeout: float = 2.0) -> bool:
    if not port or port <= 0:
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except OSError:
            return False


def wait_until_ready(config: LabConfig, timeout: int | None = None) -> dict:
    """Poll until every target container is healthy AND its port is reachable.

    Returns the last snapshot of `ps()` (containers may still be warming up if
    the timeout is hit — the caller decides whether that is fatal).
    """
    deadline = time.time() + (timeout or config.boot_timeout_seconds)
    latest: dict = {}
    while time.time() < deadline:
        latest = ps()
        if latest and all(
            (latest.get(t.name, {}).get("health") == "healthy")
            and reachable(t.host, t.port)
            for t in config.targets.values()
        ):
            return latest
        time.sleep(HEALTH_INTERVAL)
    return latest


def exec_in(service: str, argv: list, check: bool = True) -> subprocess.CompletedProcess:
    """`docker compose exec` a command inside a running service container."""
    return _compose("exec", "-T", service, *argv, check=check)
