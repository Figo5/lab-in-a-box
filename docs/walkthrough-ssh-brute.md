# Walkthrough: brute-forcing the SSH lab

`ssh-lab` is a placeholder SSH server in this lab (`127.0.0.1:2222`). It accepts
the seeded credentials and logs every attempt, so you can watch a credential
tester find a weak password without touching a real host. It never runs a shell.

> Authorized-use-only. This points only at the local lab target. Never run a
> credential tester against a host you do not own or have written permission to test.

## 1. Bring the lab up and seed it

```bash
labctl up
labctl seed          # sets labuser / labpass123 on each target
```

## 2. Run the credential tester

The lab ships `tools/ssh_brute.py`. Point it at the SSH target with the bundled
wordlists:

```bash
python tools/ssh_brute.py \
  --host 127.0.0.1 --port 2222 \
  --usernames wordlists/usernames.txt \
  --passwords wordlists/common.txt \
  --threads 4
```

It prints each confirmed login, then a summary:

```
[+] labuser:labpass123
[*] attempts=12 confirmed=1 failures=11 errors=0
Found credentials:
  labuser:labpass123
```

(`labctl run-brute --target ssh-lab` runs the same tool through the lab config.)

## 3. See it from the target's side

Every attempt is logged by the server:

```bash
docker compose logs ssh-lab | grep AUTH
# ... AUTH attempt user='root' ok=False
# ... AUTH attempt user='labuser' ok=True
```

A real server under this attack would show the same flood of failures ending in
one success — which is exactly what an intrusion-detection rule watches for.

## Why it works, and the fixes

| Weakness | Fix |
| --- | --- |
| Password authentication with a guessable password | Require SSH **keys** and set `PasswordAuthentication no` in `sshd_config`. |
| Unlimited attempts | Rate-limit with `fail2ban` or firewall throttling; lock accounts after repeated failures. |
| No visibility | Ship auth logs somewhere and alert on a burst of failures followed by a success. |

The point of the lab is step 3: a brute-force attack is loud. The defense is
less about any single login and more about removing passwords and noticing the
noise.

Every command above was run against the lab's own `ssh-lab` server on localhost.
