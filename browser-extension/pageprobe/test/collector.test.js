/* PageProbe — dependency-free tests for collector.js's pure heuristics.
 * Run: node test/collector.test.js
 */
'use strict';

const assert = require('node:assert');
const Coll = require('../collector.js');

let pass = 0;
function check(name, fn) {
  fn();
  pass++;
  process.stdout.write('ok ' + pass + ' - ' + name + '\n');
}

/* isCsrfField */
check('isCsrfField matches csrf/xsrf/token in the field name', () => {
  for (const name of ['csrf_token', 'user_token', 'xsrf-token', 'CSRFToken', '_token']) {
    assert.ok(Coll.isCsrfField({ name, hidden: false }), 'expected csrf match: ' + name);
  }
});

check('isCsrfField matches known cross-framework hidden token names', () => {
  for (const name of ['_nonce', 'authenticity_token', '__RequestVerificationToken']) {
    assert.ok(Coll.isCsrfField({ name, hidden: true }), 'expected csrf match: ' + name);
  }
});

check('isCsrfField requires hidden=true for the non-/token/-pattern names', () => {
  // "authenticity" and "_nonce" alone don't match /csrf|xsrf|token/, so they
  // only qualify via the hidden-only branch.
  assert.ok(!Coll.isCsrfField({ name: 'authenticity', hidden: false }));
  assert.ok(!Coll.isCsrfField({ name: '_nonce', hidden: false }));
  assert.ok(Coll.isCsrfField({ name: 'authenticity', hidden: true }));
  assert.ok(Coll.isCsrfField({ name: '_nonce', hidden: true }));
});

check('isCsrfField does not match ordinary field names', () => {
  for (const name of ['username', 'password', 'email', 'q']) {
    assert.ok(!Coll.isCsrfField({ name, hidden: false }), 'unexpected csrf match: ' + name);
  }
});

/* formSubmitText — depends on document.querySelector, so stub a minimal DOM. */
function withStubbedForm(matchedEl, fn) {
  const form = {
    querySelector(sel) {
      return matchedEl;
    },
  };
  fn(form);
}

check('formSubmitText reads the value of an <input type="submit">', () => {
  withStubbedForm({ tagName: 'INPUT', value: 'Log In', textContent: '' }, (form) => {
    assert.strictEqual(Coll.formSubmitText(form), 'Log In');
  });
});

check('formSubmitText falls back to textContent for a <button>', () => {
  withStubbedForm({ tagName: 'BUTTON', value: '', textContent: '  Sign in now  ' }, (form) => {
    assert.strictEqual(Coll.formSubmitText(form), 'Sign in now');
  });
});

check('formSubmitText truncates long button text to 40 chars', () => {
  const long = 'x'.repeat(80);
  withStubbedForm({ tagName: 'BUTTON', value: '', textContent: long }, (form) => {
    assert.strictEqual(Coll.formSubmitText(form).length, 40);
  });
});

check('formSubmitText returns empty string when no submit control is found', () => {
  withStubbedForm(null, (form) => {
    assert.strictEqual(Coll.formSubmitText(form), '');
  });
});

console.log('\n' + pass + ' assertions passed.');
