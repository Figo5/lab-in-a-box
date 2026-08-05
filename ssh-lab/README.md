# ssh-lab

A minimal paramiko SSH server that makes the lab's SSH target work out of the
box: it accepts the seeded credentials, logs every auth attempt, and never
executes real commands. The brute tool for this target is
`tools/ssh_brute.py` (see the top-level README's "Tools" section).

Credentials come from the `SSH_SEED_USER` / `SSH_SEED_PASS` env vars
(docker-compose.yml passes them in) or from `/labdata/users.json` written by
`labctl seed`.

## macOS note (Docker published-port proxy)

On Docker Desktop, the published-port proxy can wedge under high SSH
concurrency. If `labctl run-brute --target ssh-lab` stalls, lower the thread
count (`brute.py` invokes the tool with `--threads 4` — reduce to 1).
