# 🔎 PageProbe

**An authorized form & endpoint inspector for your browser.** Point it at a page,
see every form, field, hidden input, link, and query parameter — and copy a
ready-to-run command for your authorized-testing toolkit.

## Authorized use only

**PageProbe generates commands for testing your own systems, lab/CTF
environments, or targets you have written permission to test.** Unauthorized use
against systems you do not own is illegal.

The extension reinforces this at the point of use: when it finds a **login form
on a non-local host** (anywhere outside `localhost`, `*.local`, and the private
RFC1918 ranges), it shows a warning banner in the popup. Nothing is ever blocked
— the copy buttons always work — but the rule is impossible to miss while you
use it.

## What it does

- **Form survey** — every form's method and resolved action, all fields (type,
  default value, hidden fields marked), plus **login detection** and **CSRF
  token detection**.
- **Endpoint survey** — deduplicated outbound links (host + path), the current
  page's query parameters, and any cookies visible to page scripts.
- **Copy as commands** — one click each to copy:
  - a `python test.py` (login brute-force) command, pre-wired with the form's
    URL, method, user/pass field names, CSRF field + URL, static fields, and
    cookies;
  - a `python form_enum.py` command for the page;
  - the full survey as JSON.

## Install (unpacked, no build)

1. Clone this repo.
2. Open `chrome://extensions`.
3. Enable **Developer mode** (top right).
4. Click **Load unpacked** and select the `pageprobe/` directory.
5. Pin PageProbe, open any page, and click the icon.

Works on Chromium browsers (Chrome, Edge, Brave, …).

## Usage

Open any page and click the PageProbe icon. Each login form's **Copy test.py
cmd** gives you something like:

```
python test.py --url 'http://dvwa.local/login.php' --method POST \
  --usernames usernames.txt --passwords passwords.txt \
  --user-field username --pass-field password \
  --csrf-field user_token --csrf-url 'http://dvwa.local/login.php' \
  --extra-field 'form_id=1' \
  --cookie 'PHPSESSID=abc123; security=low' --dry-run
```

Adjust the wordlist paths (and add `--success-text` / `--fail-text` if you know
them), then drop `--dry-run` to run for real.

## Generated command reference

Maps to the [security-testing-lab](https://github.com/Figo5/security-testing-lab)
toolkit's `test.py` and `form_enum.py`:

| Flag | When PageProbe adds it |
|---|---|
| `--url` | always (resolved form action) |
| `--method` | always (GET / POST / …) |
| `--usernames` / `--passwords` | always (placeholder wordlist paths) |
| `--user-field` / `--pass-field` | login form detected |
| `--csrf-field` / `--csrf-url` | token field detected |
| `--extra-field` | each static field with a value (excl. user/pass/csrf) |
| `--cookie` | any cookies visible to page scripts |

Note: `document.cookie` does **not** expose `httpOnly` cookies — add those to
`--cookie` by hand when a session needs them.

## License

MIT.
