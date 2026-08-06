# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project does not yet follow a formal version-numbering scheme, so all
history is currently tracked under `[Unreleased]`.

## [Unreleased]

### Added
- `tools/ssh_brute.py` — paramiko-based SSH credential tester, matching the
  same flag/output contract as `dvwa_brute.py`/`http_login_brute.py`, so
  `labctl run-brute` can target `ssh-lab` with a real tool instead of the
  mock. `lab.yaml`'s global `brute.tool` repointed at the in-tree
  `./tools/ssh_brute.py` (was a stale absolute path from another machine);
  the ssh-lab target has no per-target `tool:` so it falls back to this
  global default. (2026-08-05)
- `tools/dir_scan.py` — wordlist-based path/endpoint enumerator with the
  same `build_parser()`/`parse_args(argv)` testability pattern as the other
  `tools/*.py` scripts; flag contract (`--url`, `--wordlist`, `--status`,
  `--cookie`, `--threads`, `--delay`, `--timeout`, `--retries`, `--json`)
  consistent with the shell-quoting conventions in
  `browser-extension/pageprobe/lib/commands.js`. (2026-08-05)
- `wordlists/paths.txt` — curated 27-entry path wordlist for `dir_scan.py`
  (admin, login, .git/config, .env, vulnerabilities/brute, …), sized to stay
  a lightweight, committable text file. (2026-08-05)
- `labctl/` unit tests covering `cli.py`, `compose.py`, `seed.py`,
  `security_level.py`, and `report.py` (65 tests across 5 modules), mocking
  Docker/subprocess/socket/HTTP calls so the suite runs without a live lab.
  Discovery uses `python -m unittest discover -s labctl -t .` so the `labctl`
  package resolves from the repo root. (2026-08-05)
- `tools/test_dir_scan.py` (14 tests) and `tools/test_ssh_brute.py` (3 tests)
  for the new tools' flag contracts, plus a `ssh-lab` case added to
  `tools/test_integration_labctl.py` verifying `labctl.brute._build_command`
  for ssh-lab is accepted by `ssh_brute.parse_args`. (2026-08-05)
- GitHub Actions CI workflow (`.github/workflows/test.yml`) running the full
  JS (`browser-extension/pageprobe/test/*.test.js`) and Python
  (`tools/`, `labctl/`) test suites on push/PR. (2026-08-05)
- `tools/test.py` and `tools/form_enum.py` — the two tools
  `browser-extension/pageprobe/lib/commands.js`'s `buildTestPyCommand()`
  and `buildFormEnumCommand()` generate ready-to-run commands for; neither
  existed anywhere in the repo before, leaving the extension's copy-paste
  commands with nothing to run against. Includes flag-contract and HTML
  form-parsing tests. (`9148a48`)
- Integration test (`tools/test_integration_labctl.py`) verifying
  `labctl/brute.py`'s constructed subprocess command line is accepted by
  each target tool's own `parse_args()`, across every real `lab.yaml`
  target/`tool_args` combination (dvwa, juice-shop, vuln-api). Backed by a
  minimal `_build_command()` extraction in `labctl/brute.py` so the test
  doesn't hand-duplicate the command-building logic. (`91dbb1b`)
- `build_parser()`/`parse_args(argv)` exposed on `tools/dvwa_brute.py` and
  `tools/http_login_brute.py`, making argument parsing importable and
  testable without executing `__main__`; paired with
  `tools/test_dvwa_brute.py` and `tools/test_http_login_brute.py`.
  (`61bbab1`)
- `browser-extension/pageprobe/collector.js` now exposes `isCsrfField()` and
  `formSubmitText()` via the same dual `window`/`module.exports` pattern as
  `lib/commands.js`, with `test/collector.test.js` covering the CSRF
  field-name heuristic and submit-text extraction. (`8a8d077`)
- Test coverage for `buildFormEnumCommand()`'s previously-untested
  `opts.cookies -> --cookie` branch, including shell-quoting of embedded
  quotes. (`8a8d077`)
- PageProbe browser extension merged in from the archived `Figo5/pageprobe`
  repository, at `browser-extension/pageprobe/` (history preserved via
  `git subtree`). (`96ae554`, originally `8f2c986`-`aed3c74`)
- Per-target real brute-force tooling: `tools/dvwa_brute.py` (DVWA
  brute-force page) and `tools/http_login_brute.py` (generic HTTP/JSON
  login endpoints, covering juice-shop and vuln-api). (`a9340e3`)
- Complete `labctl` pipeline: `up`, `status`, `set-level`, `seed`,
  `run-brute` (real + mock dispatch), `report` (Markdown/HTML), with
  per-run state written to `runs/<timestamp>/`. (`71ec585`)
- VHS-recorded demo GIF embedded in README. (`7b36130`, `b345246`)
- Initial PageProbe extension release: `collector.js`/`popup.js`/
  `lib/commands.js`, DVWA-form-aware command generation with CSRF/login-field
  detection and named submit/button control handling. (`8f2c986`, `7c5329a`,
  now part of this repo's history)

### Changed
- `wordlists/common.txt` expanded from 21 to 70 entries;
  `wordlists/usernames.txt` expanded from 4 to 20 entries — still a small,
  curated, readable list rather than a large dictionary dump. (2026-08-05)
- `lab.yaml` `brute.tool` repointed from a stale absolute path
  (`/Users/giofiore/Downloads/testing/ssh_brute.py`) to the in-tree
  `./tools/ssh_brute.py`, so `labctl run-brute --target ssh-lab` uses the
  real tool by default. (2026-08-05)
- README project-title formatting. (`dc0cace`)

### Removed
- `RESUME.md` (stray file, unrelated to the project). (`d97fddb`)
