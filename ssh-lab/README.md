# ssh-lab (placeholder)

A minimal paramiko SSH server that makes the lab's SSH target work out of the
box: it accepts the seeded credentials, logs every auth attempt, and never
executes real commands.

## Swap in your existing server

If you already have a vulnerable SSH server (e.g. a native paramiko server
that runs commands on login), replace this directory's `Dockerfile` and
`server.py` with yours. Two things to keep:

1. **Expose port 22** in the Dockerfile (`EXPOSE 22` / CMD that binds :22).
2. **Read the seeded creds** from `SSH_SEED_USER` / `SSH_SEED_PASS` env vars
   (docker-compose.yml passes them in) or from `/labdata/users.json` after
   `labctl seed` runs. `labctl` expects the server to authenticate the
   `labuser` / `labpass123` placeholder account.

## macOS note (Docker published-port proxy)

On Docker Desktop, the published-port proxy can wedge under high SSH
concurrency (this is why your existing lab ran the server natively). If
`labctl run-brute --target ssh-lab` with a real tool stalls, either:

- lower threads (`brute.py` uses `--threads 4` — reduce to 1), or
- run your native server on the host instead and point `brute.tool` at it.
