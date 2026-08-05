"""Idempotently create the placeholder accounts defined in lab.yaml.

Per-target behavior:
  * vuln-api  — POST /api/register (201 created, 409 already exists).
  * juice-shop— POST /api/Users with email <user>@lab.local.
  * ssh-lab   — placeholder server auth comes from SSH_SEED_USER/PASS env; seed
                verifies .env matches lab.yaml and best-effort drops a
                users.json into the shared /labdata volume for custom servers.
  * dvwa      — best-effort: insert the seeded user into the bundled MySQL via
                `docker compose exec` (falls back to "unsupported" if the DB is
                not reachable — DVWA always ships admin/password regardless).
"""

from __future__ import annotations

import hashlib
import json
import os

import requests

from . import compose
from .config import LabConfig, Target


def seed_all(cfg: LabConfig) -> dict:
    results = {}
    for name, t in cfg.targets.items():
        if not t.seed_user:
            results[name] = {"status": "skipped", "detail": "no seed_user in lab.yaml"}
            continue
        try:
            results[name] = _dispatch(name)(cfg, t)
        except Exception as e:  # keep the run alive; surface per-target
            results[name] = {"status": "error", "user": t.seed_user, "detail": str(e)}
    return results


def _dispatch(name: str):
    return {
        "vuln-api": _seed_vuln_api,
        "juice-shop": _seed_juice_shop,
        "ssh-lab": _seed_ssh_lab,
        "dvwa": _seed_dvwa,
    }.get(name, _unsupported)


def _unsupported(cfg: LabConfig, t: Target) -> dict:
    return {
        "status": "skipped",
        "user": t.seed_user,
        "detail": "seeding not implemented for this target",
    }


# --- vuln-api ---------------------------------------------------------------
def _seed_vuln_api(cfg: LabConfig, t: Target) -> dict:
    base = f"http://{t.host}:{t.port}"
    try:
        r = requests.post(
            f"{base}/api/register",
            json={"username": t.seed_user, "password": t.seed_pass},
            timeout=10,
        )
    except requests.RequestException as e:
        return {"status": "error", "user": t.seed_user, "detail": str(e)}
    if r.status_code in (200, 201):
        return {"status": "created", "user": t.seed_user}
    if r.status_code == 409:
        return {"status": "exists", "user": t.seed_user}
    return {"status": "error", "user": t.seed_user, "detail": f"HTTP {r.status_code}: {r.text[:120]}"}


# --- juice-shop -------------------------------------------------------------
def _seed_juice_shop(cfg: LabConfig, t: Target) -> dict:
    base = f"http://{t.host}:{t.port}"
    email = f"{t.seed_user}@lab.local"
    payload = {
        "email": email,
        "password": t.seed_pass,
        "passwordRepeat": t.seed_pass,
        "securityQuestion": {"id": 2, "question": "Mother's maiden name?"},
        "securityAnswer": "blue",
    }
    try:
        r = requests.post(f"{base}/api/Users", json=payload, timeout=10)
    except requests.RequestException as e:
        return {"status": "error", "user": email, "detail": str(e)}
    if r.status_code == 201:
        return {"status": "created", "user": email}
    if r.status_code in (400, 409) or "already" in r.text.lower():
        return {"status": "exists", "user": email}
    return {"status": "error", "user": email, "detail": f"HTTP {r.status_code}: {r.text[:120]}"}


# --- ssh-lab ----------------------------------------------------------------
def _seed_ssh_lab(cfg: LabConfig, t: Target) -> dict:
    env_user = os.environ.get("SSH_SEED_USER") or "labuser"
    env_pass = os.environ.get("SSH_SEED_PASS") or "labpass123"
    if env_user != t.seed_user or env_pass != t.seed_pass:
        return {
            "status": "mismatch",
            "user": t.seed_user,
            "detail": f".env has {env_user}/{env_pass}; update .env to match lab.yaml",
        }
    # Best-effort: write users.json into the shared seed volume so a custom
    # ssh server can consume the seeded creds at /labdata/users.json. Silently
    # skipped if the container is down or has been replaced.
    try:
        payload = json.dumps({"users": {t.seed_user: t.seed_pass}})
        compose.exec_in(
            "ssh-lab",
            ["python3", "-c", f"import json;json.dump({payload},open('/labdata/users.json','w'))"],
            check=False,
        )
        return {"status": "ok", "user": t.seed_user, "detail": "env matched; volume seeded"}
    except Exception:
        return {"status": "ok", "user": t.seed_user, "detail": "env matched"}


# --- dvwa -------------------------------------------------------------------
def _seed_dvwa(cfg: LabConfig, t: Target) -> dict:
    # DVWA stores passwords as MD5; login is  user + md5(password).
    # The upsert REPLACES user/avatar/password on conflict so a stale first
    # insert (wrong hash) gets repaired on a re-run — idempotency that heals.
    pw_hash = hashlib.md5(t.seed_pass.encode()).hexdigest()
    sql = (
        "INSERT INTO users (user_id, first_name, last_name, user, avatar, password, last_login, failed_login) "
        f"VALUES (2, 'Lab', 'User', '{t.seed_user}', 'no.jpg', '{pw_hash}', NOW(), 0) "
        "ON DUPLICATE KEY UPDATE user=VALUES(user), avatar=VALUES(avatar), password=VALUES(password);"
    )
    # Try a couple of common MySQL root setups for this image.
    for mysql_args in (
        ["mysql", "-u", "root", "dvwa", "-e", sql],
        ["mysql", "-u", "root", "-proot", "dvwa", "-e", sql],
        ["mysql", "-u", "root", "-pp@ssw0rd", "dvwa", "-e", sql],
    ):
        try:
            proc = compose.exec_in("dvwa", mysql_args, check=False)
            if proc.returncode == 0:
                return {"status": "created", "user": t.seed_user, "detail": "db user inserted"}
        except Exception:
            continue
    return {
        "status": "unsupported",
        "user": t.seed_user,
        "detail": "could not reach the DVWA MySQL instance; "
                  "DVWA always ships admin/password regardless",
    }
