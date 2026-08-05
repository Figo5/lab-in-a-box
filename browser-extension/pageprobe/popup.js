/* PageProbe popup controller. */
'use strict';

const C = window.PageProbeCommands;

let pageData = null;
let pageCookies = '';

function $(id) { return document.getElementById(id); }

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
}

function showStatus(msg, isError) {
  const s = $('pp-status');
  s.textContent = msg;
  s.className = 'pp-status' + (isError ? ' pp-status-error' : '');
  $('pp-content').hidden = true;
}

async function copyText(text, btn) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (e) {
    // Clipboard API unavailable (older Chrome / permissions): fall back.
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    ta.remove();
  }
  flashCopied(btn);
}

function flashCopied(btn) {
  if (!btn) return;
  const old = btn.textContent;
  btn.textContent = 'Copied ✓';
  btn.classList.add('pp-btn-copied');
  setTimeout(() => {
    btn.textContent = old;
    btn.classList.remove('pp-btn-copied');
  }, 1200);
}

function renderBanner(data) {
  const banner = $('pp-banner');
  const w = C.shouldWarn(data);
  if (!w.show) {
    banner.hidden = true;
    return;
  }
  banner.replaceChildren();
  banner.appendChild(el('span', 'pp-banner-title', 'Authorized targets only'));
  banner.appendChild(document.createTextNode(
    'Login form on ' + w.host + ' — external site. Only probe targets you own or have ' +
    'written permission to test.'));
  banner.hidden = false;
}

function renderFormCard(form) {
  const card = el('div', 'pp-form-card');

  const head = el('div', 'pp-form-head');
  head.appendChild(el('span',
    'pp-method' + (form.method === 'GET' ? ' pp-method-get' : ' pp-method-post'),
    form.method));
  head.appendChild(el('span', 'pp-form-action', form.action));
  const badges = el('div', 'pp-badges');
  if (form.isLogin) badges.appendChild(el('span', 'pp-badge pp-badge-login', 'login'));
  if (form.csrfFields.length) badges.appendChild(el('span', 'pp-badge pp-badge-csrf', 'csrf'));
  if (form.samePageAction) badges.appendChild(el('span', 'pp-badge', 'same-page'));
  head.appendChild(badges);
  card.appendChild(head);

  const fields = el('div', 'pp-form-fields');
  for (const f of form.fields) {
    const chip = el('span', 'pp-field-chip' + (f.hidden ? ' pp-field-hidden' : ''));
    chip.appendChild(el('span', 'pp-field-name', f.name));
    chip.appendChild(document.createTextNode(' ' + f.type));
    if (f.value !== '') {
      chip.appendChild(document.createTextNode(' = ' + (f.value.length > 24 ? f.value.slice(0, 24) + '…' : f.value)));
    }
    fields.appendChild(chip);
  }
  card.appendChild(fields);

  const actions = el('div', 'pp-form-actions');
  const copyCmd = el('button', 'pp-btn', 'Copy test.py cmd');
  copyCmd.type = 'button';
  copyCmd.addEventListener('click', () => {
    copyText(C.buildTestPyCommand(form, { cookies: pageCookies }), copyCmd);
  });
  const copyJson = el('button', 'pp-btn', 'Copy JSON');
  copyJson.type = 'button';
  copyJson.addEventListener('click', () => copyText(C.buildPageJson(form), copyJson));
  actions.appendChild(copyCmd);
  actions.appendChild(copyJson);
  card.appendChild(actions);

  return card;
}

function renderForms(forms) {
  const container = $('pp-forms');
  container.replaceChildren();
  if (!forms.length) {
    container.appendChild(el('div', 'pp-empty-note', 'No forms found on this page.'));
    return;
  }
  for (const form of forms) {
    container.appendChild(renderFormCard(form));
  }
}

function renderEndpoints(links) {
  const body = $('pp-endpoints-body');
  body.replaceChildren();
  $('pp-endpoints-count').textContent = '(' + links.length + ')';
  if (!links.length) {
    body.appendChild(el('div', 'pp-empty-note', 'No outbound links found.'));
    return;
  }
  const sorted = links.slice().sort((a, b) => a.href.localeCompare(b.href));
  for (const l of sorted.slice(0, 200)) {
    const row = el('div', 'pp-endpoint');
    let host = '';
    let path = l.href;
    try {
      const u = new URL(l.href);
      host = u.host;
      path = u.pathname + u.search;
    } catch (e) { /* keep raw href */ }
    row.appendChild(el('span', 'pp-endpoint-host', host));
    row.appendChild(el('span', 'pp-endpoint-path', path + (l.text ? ' — ' + l.text : '')));
    body.appendChild(row);
  }
}

function renderParams(params) {
  const container = $('pp-params');
  container.replaceChildren();
  if (!params.length) {
    container.appendChild(el('div', 'pp-empty-note', 'None'));
    return;
  }
  for (const p of params) {
    const row = el('div', 'pp-param');
    row.appendChild(el('span', 'pp-param-name', p.name));
    row.appendChild(el('span', 'pp-param-value', p.value));
    container.appendChild(row);
  }
}

function renderCookies(cookies) {
  pageCookies = cookies || '';
  $('pp-cookies').textContent = pageCookies
    ? pageCookies
    : 'No cookies (httpOnly cookies are not visible to page scripts).';
}

function render(data) {
  pageData = data;

  $('pp-url').textContent = data.url;
  $('pp-url').title = data.url;
  $('pp-stats').textContent =
    data.forms.length + ' forms · ' + data.hosts.length + ' hosts · ' + data.links.length + ' endpoints';
  const t = new Date(data.collectedAt || Date.now());
  $('pp-timestamp').textContent = 'collected ' + t.toLocaleTimeString();

  renderBanner(data);
  renderForms(data.forms);
  renderEndpoints(data.links);
  renderParams(data.queryParams);
  renderCookies(data.cookies);

  $('pp-status').hidden = true;
  $('pp-content').hidden = false;
}

function wireToolbar() {
  $('pp-copy-json').addEventListener('click', (e) => {
    copyText(C.buildPageJson(pageData), e.currentTarget);
  });
  $('pp-copy-formenum').addEventListener('click', (e) => {
    copyText(C.buildFormEnumCommand(pageData.url, { cookies: pageCookies }), e.currentTarget);
  });
  $('pp-copy-cookies').addEventListener('click', (e) => {
    copyText(pageCookies, e.currentTarget);
  });
  $('pp-endpoints-toggle').addEventListener('click', (e) => {
    const open = $('pp-endpoints-body').hidden;
    $('pp-endpoints-body').hidden = !open;
    e.currentTarget.classList.toggle('pp-open', open);
  });
}

async function main() {
  let tabs;
  try {
    tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  } catch (e) {
    showStatus('Could not read the active tab.', true);
    return;
  }
  const tab = tabs && tabs[0];
  if (!tab || !tab.id || !tab.url) {
    showStatus('No active web tab.', true);
    return;
  }

  let protocol = '';
  try { protocol = new URL(tab.url).protocol; } catch (e) { /* fall through */ }
  if (protocol !== 'http:' && protocol !== 'https:') {
    showStatus('PageProbe inspects http(s) pages. This tab is not a web page.', true);
    return;
  }

  let result;
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ['collector.js'],
    });
    result = results && results[0] && results[0].result;
  } catch (err) {
    showStatus('Cannot inspect this page: ' + (err && err.message ? err.message : 'injection failed') + '.', true);
    return;
  }

  if (!result) {
    showStatus('Nothing collected from this page.', true);
    return;
  }

  render(result);
}

document.addEventListener('DOMContentLoaded', () => {
  wireToolbar();
  main();
});
