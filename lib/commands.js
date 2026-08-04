/* PageProbe command builders.
 *
 * Pure functions that turn a page survey into ready-to-run commands for the
 * security-testing-lab CLI tools. Exposed as `window.PageProbeCommands` in the
 * extension and via `module.exports` under Node for the test harness.
 */
'use strict';

/* Wrap a value in single quotes, shell-safe: ' -> '\''  */
function shellQuote(value) {
  return "'" + String(value).replace(/'/g, "'\\''") + "'";
}

function excludeFromExtra(field, excluded) {
  if (excluded.has(field.name)) return true;
  if (['file', 'submit', 'button', 'reset', 'image'].includes(field.type)) return true;
  return field.value === '';
}

/* Build a `python test.py ...` command for one form. */
function buildTestPyCommand(form, opts) {
  opts = opts || {};
  const parts = [
    'python', 'test.py',
    '--url', shellQuote(form.action),
    '--method', form.method,
    '--usernames', 'usernames.txt',
    '--passwords', 'passwords.txt',
  ];

  const excluded = new Set();
  const passField = form.isLogin ? (form.fields.find((f) => f.type === 'password') || {}).name : null;

  if (form.isLogin && form.loginUserField && passField) {
    parts.push('--user-field', shellQuote(form.loginUserField));
    parts.push('--pass-field', shellQuote(passField));
    excluded.add(form.loginUserField);
    excluded.add(passField);
  }

  if (form.csrfFields && form.csrfFields.length) {
    parts.push('--csrf-field', shellQuote(form.csrfFields[0]));
    parts.push('--csrf-url', shellQuote(form.action));
    excluded.add(form.csrfFields[0]);
  }

  for (const f of form.fields) {
    if (excludeFromExtra(f, excluded)) continue;
    parts.push('--extra-field', shellQuote(f.name + '=' + f.value));
  }

  if (opts.cookies) {
    parts.push('--cookie', shellQuote(opts.cookies));
  }
  if (opts.dryRun) {
    parts.push('--dry-run');
  }

  return parts.join(' ');
}

/* Build a `python form_enum.py ...` command for a page. */
function buildFormEnumCommand(pageUrl, opts) {
  opts = opts || {};
  const parts = ['python', 'form_enum.py', '--url', shellQuote(pageUrl)];
  if (opts.cookies) {
    parts.push('--cookie', shellQuote(opts.cookies));
  }
  parts.push('--json', 'report.json');
  return parts.join(' ');
}

/* Pretty-print the full survey. */
function buildPageJson(payload) {
  return JSON.stringify(payload, null, 2);
}

/* Local / private-lab hostnames are the only hosts we treat as "ours". */
function isLocalHost(hostname) {
  const h = String(hostname || '').toLowerCase().replace(/\.$/, '');
  if (h === 'localhost' || h === '127.0.0.1' || h === '::1' || h === '0.0.0.0') return true;
  if (h.endsWith('.localhost') || h.endsWith('.local')) return true;
  const v4 = h.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (!v4) return false;
  const a = +v4[1];
  const b = +v4[2];
  return a === 10 || a === 127 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168);
}

/* Decide whether to show the authorized-use banner: a login form on a
 * non-local host. Returns { show, host } where host is the offending host. */
function shouldWarn(payload) {
  if (!payload || !payload.forms || !payload.forms.some((f) => f.isLogin)) {
    return { show: false, host: '' };
  }
  let host = '';
  try { host = new URL(payload.url).hostname; } catch (e) { /* keep '' */ }
  return { show: host !== '' && !isLocalHost(host), host };
}

const api = {
  shellQuote,
  buildTestPyCommand,
  buildFormEnumCommand,
  buildPageJson,
  isLocalHost,
  shouldWarn,
};

if (typeof window !== 'undefined') {
  window.PageProbeCommands = api;
}
if (typeof module !== 'undefined' && module.exports) {
  module.exports = api;
}
