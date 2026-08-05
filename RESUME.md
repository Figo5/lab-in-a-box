# Lab-in-a-Box — RESUME PROMPT

You are resuming work on **Lab-in-a-Box** at `/Users/giofiore/lab-in-a-box` (not yet a git repo). It is a Docker Compose + Python Click CLI that provisions an authorized-use-only local pentest lab (DVWA, a placeholder paramiko SSH server, OWASP Juice Shop, a custom vulnerable Flask API), configures security levels + seeded accounts, runs a brute-forcer, and emits a consolidated Markdown/HTML report.

The lab is **currently UP** — all 4 containers healthy and reachable. The `labctl` CLI is installed editable in `.venv` (Python 3.9-compatible; pip upgraded; run via `./bin/labctl`).

## Verified working (do NOT redo)
- `labctl up` / `status` — all targets healthy + reachable (ports 8081/2222/8082/8083 on 127.0.0.1).
- `labctl set-level dvwa <level>` — auto-runs DVWA `setup.php create_db` on first boot, logs in, sets level, verifies via `currently: <em>level</em>`.
- `labctl seed` — creates `labuser`/`labpass123` on all 4 targets; idempotent; DVWA upsert heals stale hashes.
- Seeded creds verified: vuln-api login, juice-shop login (`labuser@lab.local`), ssh-lab paramiko AUTH OK, DVWA `labuser` login.
- `labctl run-brute --target ssh-lab` **mock** works (finds `labuser:labpass123`, masked).

## Open issue (the one thing left to finish the pipeline)
`labctl run-brute` with the REAL tool exits 1 with empty stdout, successes=0.
**Hypothesis (high confidence, verified):** `labctl/brute.py::_run_real` invokes `[sys.executable, <tool> ...]` where `sys.executable` is the lab venv, which does NOT have `paramiko` — so `ssh_brute.py` crashes at import (`ModuleNotFoundError`).
**Fix:** make the tool's interpreter configurable (e.g. `brute.python` in `lab.yaml`, or resolve the tool's sibling `.venv/bin/python`), defaulting to the lab venv. The real tool is `/Users/giofiore/Downloads/testing/ssh_brute.py`; its working interpreter is `/Users/giofiore/Downloads/testing/.venv/bin/python`. Re-test with `brute.tool` set in lab.yaml; expect attempts=84 and 1 success `labuser:labpass123`.

## Not yet done
- `labctl report` has never been run — test it (aggregates `runs/<ts>/{meta,levels,seeds,*brute}.json` + live status). Fix typo at `labctl/report.py:98` (`not run_ yet_` → `not run yet`).
- Clean stale run dirs `runs/20260805-075019` and `runs/20260805-080535` (failed internal-network attempts); keep `runs/20260805-082035`.
- Consider `git init` + first commit (user hasn't pushed anything yet).

## Design decisions to PRESERVE (don't "fix" these)
- **`labnet` is a plain bridge, NOT `internal: true`** — Docker Desktop (macOS) silently doesn't publish ports from internal networks (empirically verified); the user explicitly chose "bridge + localhost-only bindings" over a socat relay bastion. Safety model = 127.0.0.1-only port bindings. Documented in README.
- **juice-shop healthcheck is exec-form** `["CMD","/nodejs/bin/node","-e",...]` — image is distroless (no `/bin/sh`) and `node` isn't on PATH.
- **DVWA healthcheck** uses `php -r '...fsockopen...'` via CMD-SHELL with `$$` escaping (Compose interpolates `$`).
- **DVWA v1.10 quirks**: no DB on first boot → POST setup.php create_db; login success = 302→index.php; level shown as `currently: <em>level</em>` (no `<select>`); seed inserts MD5-hashed users via `docker compose exec mysql -u root` (no password).
- **brute.py default is a mock**; the real tool is shelled out, never reimplemented. Passwords masked everywhere.
- Existing tooling lives at `/Users/giofiore/Downloads/testing/` (ssh_brute.py, dvwa_brute.py, native ssh-lab server). macOS Docker proxy can wedge under SSH load — if a real brute run stalls, lower threads or run the server natively.

## Environment
- macOS; Docker 29.6.2; Compose v5.3.1; system Python 3.9.6 only (no homebrew pythons); `.venv` at project root.
- urllib3 `NotOpenSSLWarning` on the venv is harmless (LibreSSL) — filter it from outputs when convenient.
- User's own DVWA runs separately at :4280 — don't touch it.

## Resume commands
```bash
cd /Users/giofiore/lab-in-a-box
./bin/labctl status
# fix brute.py interpreter; set brute.tool in lab.yaml; test real run
./bin/labctl run-brute --target ssh-lab
# fix report.py:98; first-ever report run:
./bin/labctl report --html
./bin/labctl down
```

## Tasks
1. Fix real-tool interpreter in `brute.py`; verify a real run finds `labuser:labpass123`.
2. Fix `report.py:98` typo; run + verify `report.md`/HTML (targets table, levels, masked seeds, brute summary).
3. Clean stale run dirs; README sanity check; `git init` + commit (only if the user wants).
4. Optionally re-verify a fresh `up` → `set-level` → `seed` → `run-brute` → `report` cycle after `down --purge`.
