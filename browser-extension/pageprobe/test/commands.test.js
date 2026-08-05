/* PageProbe — dependency-free tests for lib/commands.js.
 * Run: node test/commands.test.js
 */
'use strict';

const assert = require('node:assert');
const C = require('../lib/commands.js');

let pass = 0;
function check(name, fn) {
  fn();
  pass++;
  process.stdout.write('ok ' + pass + ' - ' + name + '\n');
}

/* shellQuote */
check('shellQuote wraps in single quotes', () => {
  assert.strictEqual(C.shellQuote('hello'), "'hello'");
});
check('shellQuote escapes embedded quotes', () => {
  assert.strictEqual(C.shellQuote("it's"), "'it'\\''s'");
  assert.strictEqual(C.shellQuote('a"b'), "'a\"b'");
});

/* buildWebLoginBruteCommand */
const loginForm = {
  action: 'http://dvwa.local/login.php',
  method: 'POST',
  isLogin: true,
  loginUserField: 'username',
  csrfFields: ['user_token'],
  samePageAction: false,
  hasFile: false,
  submitText: 'Login',
  fields: [
    { name: 'username', type: 'text', value: '', hidden: false },
    { name: 'password', type: 'password', value: '', hidden: false },
    { name: 'user_token', type: 'hidden', value: 'abc123', hidden: true },
    { name: 'form_id', type: 'hidden', value: '1', hidden: true },
  ],
};

check('web_login_brute.py command wires url/method/wordlists', () => {
  const cmd = C.buildWebLoginBruteCommand(loginForm, {});
  assert.ok(cmd.startsWith('python tools/web_login_brute.py'), cmd);
  assert.ok(cmd.includes("--url 'http://dvwa.local/login.php'"), cmd);
  assert.ok(cmd.includes('--method POST'), cmd);
  assert.ok(cmd.includes('--usernames wordlists/usernames.txt'), cmd);
  assert.ok(cmd.includes('--passwords wordlists/common.txt'), cmd);
});

check('web_login_brute.py command wires login + csrf fields', () => {
  const cmd = C.buildWebLoginBruteCommand(loginForm, {});
  assert.ok(cmd.includes("--user-field 'username'"), cmd);
  assert.ok(cmd.includes("--pass-field 'password'"), cmd);
  assert.ok(cmd.includes("--csrf-field 'user_token'"), cmd);
  assert.ok(cmd.includes("--csrf-url 'http://dvwa.local/login.php'"), cmd);
});

check('web_login_brute.py command sends only static fields as --extra-field', () => {
  const cmd = C.buildWebLoginBruteCommand(loginForm, {});
  // form_id has a value and is not user/pass/csrf → included.
  assert.ok(cmd.includes("--extra-field 'form_id=1'"), cmd);
  // user/pass/csrf/empty-value fields must NOT appear as extra fields.
  assert.ok(!cmd.includes("--extra-field 'username"), cmd);
  assert.ok(!cmd.includes("--extra-field 'password"), cmd);
  assert.ok(!cmd.includes("--extra-field 'user_token"), cmd);
});

check('web_login_brute.py command adds cookie and dry-run when requested', () => {
  const cmd = C.buildWebLoginBruteCommand(loginForm, { cookies: 'PHPSESSID=abc; security=low', dryRun: true });
  assert.ok(cmd.includes("--cookie 'PHPSESSID=abc; security=low'"), cmd);
  assert.ok(cmd.includes('--dry-run'), cmd);
});

check('web_login_brute.py command for a plain GET form omits login/csrf flags', () => {
  const cmd = C.buildWebLoginBruteCommand({
    action: 'http://example.com/search',
    method: 'GET',
    isLogin: false,
    loginUserField: '',
    csrfFields: [],
    fields: [{ name: 'q', type: 'search', value: 'hello world', hidden: false }],
  }, {});
  assert.ok(cmd.includes("--extra-field 'q=hello world'"), cmd);
  assert.ok(!cmd.includes('--user-field'), cmd);
  assert.ok(!cmd.includes('--csrf-field'), cmd);
});

check('web_login_brute.py command clamps non-GET/POST methods to POST', () => {
  const cmd = C.buildWebLoginBruteCommand({
    action: 'http://example.com/endpoint',
    method: 'PUT',
    isLogin: false,
    loginUserField: '',
    csrfFields: [],
    fields: [],
  }, {});
  assert.ok(cmd.includes('--method POST'), cmd);
  assert.ok(!cmd.includes('--method PUT'), cmd);
});

check('web_login_brute.py command includes named submit/button controls with values', () => {
  const cmd = C.buildWebLoginBruteCommand({
    action: 'http://127.0.0.1:8081/vulnerabilities/brute/index.php',
    method: 'GET',
    isLogin: true,
    loginUserField: 'username',
    csrfFields: ['user_token'],
    fields: [
      { name: 'username', type: 'text', value: '', hidden: false },
      { name: 'password', type: 'password', value: '', hidden: false },
      { name: 'user_token', type: 'hidden', value: 'abc123', hidden: true },
      { name: 'Login', type: 'submit', value: 'Login', hidden: false },
      { name: 'Go', type: 'submit', value: '', hidden: false },
      { name: '', type: 'submit', value: 'x', hidden: false },
      { name: 'upload', type: 'file', value: '', hidden: false },
    ],
  }, {});
  assert.ok(cmd.includes("--extra-field 'Login=Login'"), cmd);
  assert.ok(!cmd.includes('Go='), cmd);
  assert.ok(!cmd.includes("--extra-field '=x'"), cmd);
  assert.ok(!cmd.includes('upload'), cmd);
});

/* buildFormEnumCommand */
check('form_enum.py command wires url and json report', () => {
  const cmd = C.buildFormEnumCommand('http://example.com/page.php', {});
  assert.ok(cmd.startsWith('python tools/form_enum.py'), cmd);
  assert.ok(cmd.includes("--url 'http://example.com/page.php'"), cmd);
  assert.ok(cmd.includes('--json report.json'), cmd);
});

/* isLocalHost */
check('isLocalHost recognizes localhost and private ranges', () => {
  for (const h of ['localhost', '127.0.0.1', '::1', '10.0.0.5', '172.16.0.1', '172.31.9.9', '192.168.1.1', 'dev.local', 'foo.localhost']) {
    assert.ok(C.isLocalHost(h), 'expected local: ' + h);
  }
  for (const h of ['example.com', '172.32.0.1', '8.8.8.8', '1.2.3.4']) {
    assert.ok(!C.isLocalHost(h), 'expected external: ' + h);
  }
});

/* shouldWarn */
check('shouldWarn shows banner for login on external host', () => {
  const w = C.shouldWarn({
    url: 'https://example.com/login',
    forms: [{ isLogin: true }],
  });
  assert.deepStrictEqual(w, { show: true, host: 'example.com' });
});
check('shouldWarn stays quiet on localhost or without login', () => {
  assert.strictEqual(C.shouldWarn({ url: 'http://localhost:8081/login.php', forms: [{ isLogin: true }] }).show, false);
  assert.strictEqual(C.shouldWarn({ url: 'https://example.com', forms: [{ isLogin: false }] }).show, false);
});

/* buildPageJson */
check('buildPageJson round-trips a survey', () => {
  const payload = { url: 'http://x.test', forms: [], links: [] };
  assert.deepStrictEqual(JSON.parse(C.buildPageJson(payload)), payload);
});

console.log('\n' + pass + ' assertions passed.');
