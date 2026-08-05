#!/usr/bin/env python3
"""PLACEHOLDER vulnerable SSH server — Lab-in-a-Box lab target.

Accepts the seeded credentials and logs every authentication attempt to stdout
(visible via `docker compose logs ssh-lab`). No real shell is executed: exec
requests get a canned "command logged" reply, which is enough for a credential
tester to confirm a hit without running anything on the host.

Credentials are read from:
  1. SSH_SEED_USER / SSH_SEED_PASS env vars (set by docker-compose.yml), plus
  2. /labdata/users.json written by `labctl seed` into the shared volume.

Authorized-use-only: this exists to be attacked in your own lab.
"""

import json
import logging
import os
import socket
import threading
from pathlib import Path

import paramiko

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
LOG = logging.getLogger("ssh-lab")

HOST_KEY = paramiko.RSAKey.generate(2048)
USERS_FILE = Path("/labdata/users.json")


def _allowed_creds() -> dict:
    creds = {
        os.environ.get("SSH_SEED_USER", "labuser"): os.environ.get("SSH_SEED_PASS", "labpass123")
    }
    try:
        data = json.loads(USERS_FILE.read_text())
        creds.update(data.get("users", {}))
    except Exception:
        pass
    return creds


class Server(paramiko.ServerInterface):
    def __init__(self):
        self.username = None

    def check_auth_password(self, username, password):
        self.username = username
        ok = _allowed_creds().get(username) == password
        LOG.info("AUTH attempt user=%r ok=%s", username, ok)
        return paramiko.AUTH_SUCCESSFUL if ok else paramiko.AUTH_FAILED

    def check_channel_request(self, kind, chanid):
        if kind == "session":
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_shell_request(self, channel):
        return True

    def check_channel_exec_request(self, channel, command):
        LOG.info("EXEC user=%r command=%r", self.username, command.decode(errors="replace"))
        channel.send(b"command logged; nothing executed in this placeholder lab server\r\n")
        channel.send_exit_status(0)
        channel.close()
        return True


def handle(conn):
    try:
        transport = paramiko.Transport(conn)
        transport.add_server_key(HOST_KEY)
        server = Server()
        transport.start_server(server=server)
        channel = transport.accept(60)
        if channel:
            channel.send(b"lab-ssh placeholder ready\r\n")
        while transport.is_active():
            transport.join(1)
    except Exception as e:  # keep serving through bad/partial handshakes
        LOG.info("connection error: %s", e)
    finally:
        conn.close()


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", 22))
    sock.listen(16)
    LOG.info("listening on :22")
    while True:
        conn, _ = sock.accept()
        threading.Thread(target=handle, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    main()
