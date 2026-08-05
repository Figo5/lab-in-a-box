"""Apply per-target security levels.

Only DVWA exposes a level setting (low/medium/high/impossible). Other targets
return a clear "not applicable" result so `labctl set-level` is honest about
what it can and cannot do.

DVWA specifics handled here (verified against the stock `vulnerables/web-dvwa`
image, DVWA v1.10):
  * On first boot the image does NOT create the database — setup.php must be
    POSTed once (create_db) before any login works. We detect that (login
    302s to setup.php) and run it automatically.
  * Login success is a 302 to index.php; failure is a 200 with "Login failed".
  * The active level is shown on security.php as `currently: <em>level</em>`.
"""

from __future__ import annotations

import os
import re

import requests

from .config import SECURITY_LEVELS, LabConfig

_USER_TOKEN_RE = re.compile(r"name=['\"]user_token['\"]\s+value=['\"]([^'\"]+)['\"]", re.I)
_CURRENT_LEVEL_RE = re.compile(r"currently:\s*<em>([^<]+)</em>", re.I)


def apply(cfg: LabConfig, target: str, level: str) -> dict:
    """Return {"ok": bool, "reason"/"level": ...} for a target."""
    if level not in SECURITY_LEVELS:
        return {"ok": False, "reason": f"invalid level {level!r}"}
    if target == "dvwa":
        return _apply_dvwa(cfg, level)
    return {
        "ok": False,
        "reason": (
            f"{target} does not expose a security-level setting. "
            "Supported: dvwa (low/medium/high/impossible). "
            "juice-shop difficulty is set in-app; ssh-lab and vuln-api have no levels."
        ),
    }


def ensure_dvwa_setup(cfg: LabConfig) -> bool:
    """Make sure the DVWA database exists (runs setup.php create_db if needed).

    Used by both `set-level` and `seed`. Returns True when the DB is ready.
    """
    t = cfg.get("dvwa")
    base = f"http://{t.host}:{t.port}"
    session = requests.Session()
    try:
        r = session.get(f"{base}/setup.php", timeout=10)
        token = _user_token(r.text)
        if not token:
            # No setup form at all — the app is probably already set up.
            return True
        r = session.post(
            f"{base}/setup.php",
            data={"create_db": "Create / Reset Database", "user_token": token},
            timeout=60,
        )
        return "Setup successful" in r.text or "reset" in r.text.lower()
    except requests.RequestException:
        return False


def _apply_dvwa(cfg: LabConfig, level: str) -> dict:
    t = cfg.get("dvwa")
    base = f"http://{t.host}:{t.port}"
    admin_user = os.environ.get("DVWA_ADMIN_USER", "admin")
    admin_pass = os.environ.get("DVWA_ADMIN_PASS", "password")

    session = requests.Session()
    try:
        if not _login(session, base, admin_user, admin_pass):
            # The stock image ships without a database on first boot.
            if not ensure_dvwa_setup(cfg):
                return {"ok": False,
                        "reason": f"DVWA database setup failed at {base}"}
            if not _login(session, base, admin_user, admin_pass):
                return {"ok": False,
                        "reason": "DVWA login failed (default admin/password — see .env.example)"}

        r = session.get(f"{base}/security.php", timeout=10)
        token = _user_token(r.text)
        if not token:
            return {"ok": False, "reason": "could not find CSRF token on /security.php"}
        r = session.post(
            f"{base}/security.php",
            data={"security": level, "seclev_submit": "Submit", "user_token": token},
            timeout=10,
        )
        current = _current_level(r.text) or _current_level(session.get(f"{base}/security.php", timeout=10).text)
        if current != level:
            return {"ok": False, "level": level,
                    "reason": f"DVWA reports level {current!r}, not {level!r}"}
        return {"ok": True, "level": level}
    except requests.RequestException as e:
        return {"ok": False, "reason": f"DVWA not reachable at {base}: {e}"}


def _login(session, base, user, pw) -> bool:
    r = session.get(f"{base}/login.php", timeout=10)
    token = _user_token(r.text)
    if not token:
        return False
    r = session.post(
        f"{base}/login.php",
        data={"username": user, "password": pw, "Login": "Login", "user_token": token},
        timeout=10,
        allow_redirects=False,
    )
    return "index.php" in (r.headers.get("Location", ""))


def _user_token(html: str) -> str | None:
    m = _USER_TOKEN_RE.search(html)
    return m.group(1) if m else None


def _current_level(html: str) -> str | None:
    m = _CURRENT_LEVEL_RE.search(html)
    return m.group(1).strip() if m else None
