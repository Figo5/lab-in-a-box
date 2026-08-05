"""
INTENTIONALLY VULNERABLE REST API — Lab-in-a-Box lab target only.

Authorized-use-only: this app exists so you can practice finding common API
vulnerabilities. Never deploy it where untrusted users can reach it.

Documented vulnerabilities (practice finding each one):
  1. Broken object-level authorization — GET /api/users/<id> returns ANY user
     (including their plaintext password) with no authentication.
  2. SQL injection                    — /api/search concatenates user input.
  3. Mass assignment                  — /api/register honors `is_admin`.
  4. Plaintext credential storage.
  5. No rate limiting / no auth on admin endpoints.
"""

import sqlite3
import threading
from pathlib import Path

from flask import Flask, jsonify, request

DB = Path("/app/lab.db")
LOCK = threading.Lock()
app = Flask(__name__)

ADMIN_USER = "admin"
ADMIN_PASS = "admin123"  # placeholder lab credential


def _conn():
    return sqlite3.connect(DB)


def _init_db():
    with LOCK, _conn() as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS users ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "username TEXT UNIQUE NOT NULL,"
            "password TEXT NOT NULL,"  # INTENTIONAL: plaintext
            "is_admin INTEGER NOT NULL DEFAULT 0)"
        )
        if c.execute("SELECT COUNT(*) FROM users WHERE username=?", (ADMIN_USER,)).fetchone()[0] == 0:
            c.execute(
                "INSERT INTO users (username, password, is_admin) VALUES (?,?,1)",
                (ADMIN_USER, ADMIN_PASS),
            )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/register")
def register():
    body = request.get_json(silent=True) or {}
    username = body.get("username")
    password = body.get("password")
    if not username or not password:
        return jsonify({"error": "username and password required"}), 400
    # INTENTIONAL (mass assignment): extra JSON fields are merged straight into
    # the row — including `is_admin`.
    is_admin = 1 if body.get("is_admin") else 0
    try:
        with LOCK, _conn() as c:
            c.execute(
                "INSERT INTO users (username, password, is_admin) VALUES (?,?,?)",
                (username, password, is_admin),
            )
    except sqlite3.IntegrityError:
        return jsonify({"error": "username already exists"}), 409
    return jsonify({"registered": username, "is_admin": bool(is_admin)}), 201


@app.post("/api/login")
def login():
    body = request.get_json(silent=True) or {}
    with _conn() as c:
        row = c.execute(
            "SELECT id, username, is_admin FROM users WHERE username=? AND password=?",
            (body.get("username"), body.get("password")),
        ).fetchone()
    if not row:
        return jsonify({"error": "invalid credentials"}), 401
    return jsonify({"token": f"fake-token-{row[0]}", "user": row[1], "is_admin": bool(row[2])})


@app.get("/api/users")
def list_users():
    # INTENTIONAL (BOLA): listing every user requires no authentication.
    with _conn() as c:
        rows = c.execute("SELECT id, username, is_admin FROM users").fetchall()
    return jsonify([{"id": r[0], "username": r[1], "is_admin": bool(r[2])} for r in rows])


@app.get("/api/users/<int:user_id>")
def get_user(user_id):
    # INTENTIONAL (broken object-level authorization): no auth check; any id.
    with _conn() as c:
        row = c.execute(
            "SELECT id, username, password, is_admin FROM users WHERE id=?", (user_id,)
        ).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify({"id": row[0], "username": row[1], "password": row[2], "is_admin": bool(row[3])})


@app.get("/api/search")
def search():
    q = request.args.get("q", "")
    # INTENTIONAL (SQL injection): user input concatenated into SQL.
    #   Try:  q=anything' OR '1'='1
    with _conn() as c:
        rows = c.execute(
            f"SELECT id, username, is_admin FROM users WHERE username LIKE '%{q}%'"
        ).fetchall()
    return jsonify([{"id": r[0], "username": r[1], "is_admin": bool(r[2])} for r in rows])


@app.get("/api/flag")
def flag():
    # INTENTIONAL: an "admin only" endpoint gated by the caller-supplied user id.
    # Chain the mass-assignment register + BOLA read to reach admin and grab it.
    user_id = request.args.get("user_id", type=int)
    with _conn() as c:
        row = c.execute("SELECT username, is_admin FROM users WHERE id=?", (user_id,)).fetchone()
    if not row or not row[1]:
        return jsonify({"error": "admin only"}), 403
    return jsonify({"flag": f"flag{{admin-{row[0]}}}"})


_init_db()

if __name__ == "__main__":
    # 0.0.0.0 inside the container is fine — the only published path is the
    # 127.0.0.1 binding in docker-compose.yml.
    app.run(host="0.0.0.0", port=8080)
