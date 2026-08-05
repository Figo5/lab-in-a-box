"""Run the existing brute-forcer against a lab target.

Two modes:
  * Real   — if lab.yaml `brute.tool` points at an existing brute-forcer, it is
             invoked as a subprocess and stdout is parsed into the results dict.
             The stock integration targets `ssh_brute.py` (host + usernames +
             passwords), which prints `[+] user:pass` lines and a
             `[*] attempts=... confirmed=...` summary.
  * Mock   — otherwise a deterministic stub runs, so the pipeline
             (up -> seed -> run-brute -> report) works end-to-end before your
             tool is plugged in. The stub "finds" the seeded account iff its
             password appears in the wordlist.

Results contract (shared by both modes):
    {
      "target": str, "host": str, "port": int,
      "wordlist": str, "attempts": int,
      "started": str, "ended": str,
      "successes": [{"username": str, "password": str}, ...],
      "mock": bool,
    }
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

from .config import PROJECT_ROOT, LabConfig

_SUMMARY_RE = re.compile(r"attempts=(\d+)\s+confirmed=(\d+)\s+failures=(\d+)\s+errors=(\d+)")
_SUCCESS_RE = re.compile(r"^\[\+\]\s+(\S+):(\S+)\s*$", re.MULTILINE)


def run(
    cfg: LabConfig,
    target: str,
    wordlist: Path,
    usernames: Path | None = None,
    timeout: int = 600,
) -> dict:
    t = cfg.get(target)
    started = time.strftime("%Y-%m-%dT%H:%M:%S")

    # Per-target tool (target spec `tool:`) overrides the global `brute.tool`.
    tool = t.tool or cfg.brute.tool
    tool_path = _resolve_tool(tool) if tool else None
    if tool_path and tool_path.exists():
        result = _run_real(cfg, t, wordlist, usernames, str(tool_path), timeout)
    else:
        result = _run_mock(cfg, t, wordlist)

    result["started"] = started
    result["ended"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    result["host"] = t.host
    result["port"] = t.port
    result["target"] = target
    result["wordlist"] = str(wordlist)
    return result


# --------------------------------------------------------------------------
# Real integration
# --------------------------------------------------------------------------
# Interpreter resolution order for the brute tool (see also README.md):
#   1. `brute.python` in lab.yaml        — explicit override wins.
#   2. <tool dir>/.venv/bin/python       — a sibling venv shipped next to the
#                                          tool (e.g. ssh_brute.py needs
#                                          paramiko from its own venv).
#   3. the lab venv (sys.executable)     — last resort: the tool only needs
#                                          the lab's own deps (requests, ...).
def _resolve_tool(tool: str) -> Path:
    """Resolve a brute tool path relative to the project root if not absolute."""
    p = Path(tool)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p


def _resolve_python(cfg: LabConfig, tool: Path) -> str:
    """Resolve the interpreter to run a brute tool with (see comment above)."""
    if cfg.brute.python:
        return cfg.brute.python
    for candidate in (tool.parent / ".venv" / "bin" / "python",
                      tool.parent / ".venv" / "bin" / "python3"):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _build_command(cfg, t, wordlist, usernames, tool) -> list:
    """Build the tool subprocess command line (split out from _run_real so
    the flag contract can be tested against each tool's own parser without
    spawning a subprocess)."""
    usernames = usernames or cfg.resolve_usernames()
    cmd = [
        _resolve_python(cfg, Path(tool)),
        str(Path(tool)),
        "--host", t.host,
        "--port", str(t.port),
        "--usernames", str(usernames),
        "--passwords", str(wordlist),
        "--threads", "4",
        "--delay", "0.05",
        "--timeout", "10",
    ]
    # Per-target extras (e.g. --path/--user-field/--user-suffix for HTTP tools).
    cmd.extend(t.tool_args or [])
    return cmd


def _run_real(cfg, t, wordlist, usernames, tool, timeout) -> dict:
    cmd = _build_command(cfg, t, wordlist, usernames, tool)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    stdout = proc.stdout
    successes = [{"username": u, "password": p} for u, p in _SUCCESS_RE.findall(stdout)]
    m = _SUMMARY_RE.search(stdout)
    attempts = int(m.group(1)) if m else len(_read_wordlist(wordlist))
    return {
        "attempts": attempts,
        "successes": successes,
        "mock": False,
        "tool": str(tool),
        "exit_code": proc.returncode,
        "tool_stdout": stdout[-2000:],  # tail kept for the report
        "note": "Real brute-forcer run (see tool_stdout for full output).",
    }


# --------------------------------------------------------------------------
# Mock (default)
# --------------------------------------------------------------------------
def _run_mock(cfg, t, wordlist) -> dict:
    passwords = _read_wordlist(wordlist)
    # Deterministic: the seeded account counts as "found" iff its password is
    # present in the wordlist.
    successes = []
    if t.seed_user and t.seed_pass and t.seed_pass in passwords:
        successes.append({"username": t.seed_user, "password": t.seed_pass})
    return {
        "attempts": len(passwords),
        "successes": successes,
        "mock": True,
        "note": (
            "Stub — no brute.tool configured in lab.yaml. "
            "Plug in your brute-forcer (see labctl/brute.py, `# TODO(integrate)`)."
        ),
    }


def _read_wordlist(path: Path) -> list:
    return [ln.strip() for ln in path.read_text().splitlines() if ln.strip()]
