/* PageProbe collector.
 *
 * Injected into the page's isolated world via
 *   chrome.scripting.executeScript({ files: ['collector.js'] })
 * The script's last expression is its return value — see collectPageData()
 * at the bottom. All returned data is plain, JSON-serializable objects.
 */
'use strict';

function resolveUrl(href) {
  try {
    return new URL(href, document.baseURI || location.href).href;
  } catch (e) {
    return href;
  }
}

function isCsrfField(field) {
  if (/(csrf|xsrf|token)/i.test(field.name)) return true;
  // Known cross-framework token names that skip the /token/ pattern.
  return field.hidden && /(_nonce|authenticity|requestverification)/i.test(field.name);
}

function formSubmitText(form) {
  const sub = form.querySelector('input[type="submit"], button[type="submit"], button:not([type])');
  if (!sub) return '';
  if (sub.value && sub.tagName === 'INPUT') return sub.value;
  return (sub.textContent || '').trim().slice(0, 40);
}

function collectForms() {
  const out = [];
  for (const form of document.forms) {
    const fields = [];
    const seen = new Set();
    for (const el of form.elements) {
      if (el.disabled) continue;
      const name = (el.name || el.id || '').trim();
      if (!name || seen.has(name)) continue;
      seen.add(name);
      let type = (el.getAttribute('type') || el.type || 'text').toLowerCase();
      if (el.tagName !== 'INPUT') type = el.tagName.toLowerCase();
      const hidden = el.tagName === 'INPUT' && type === 'hidden';
      let value = '';
      try { value = el.value != null ? String(el.value) : ''; } catch (e) { /* cross-origin frame guard */ }
      fields.push({ name, type, value, hidden });
    }

    const rawAction = (form.getAttribute('action') || '').trim();
    const action = rawAction ? resolveUrl(rawAction) : location.href;
    let method = (form.method || 'GET').toUpperCase();
    if (!['GET', 'POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) method = 'GET';

    const passwordFields = fields.filter((f) => f.type === 'password');
    const isLogin = passwordFields.length > 0;
    const loginUserField = isLogin
      ? (fields.find((f) => ['text', 'email', 'tel', 'username', 'search'].includes(f.type)) || {}).name || ''
      : '';
    const csrfFields = fields.filter(isCsrfField).map((f) => f.name);

    out.push({
      action,
      method,
      fields,
      hasFile: fields.some((f) => f.type === 'file'),
      isLogin,
      loginUserField,
      csrfFields,
      submitText: formSubmitText(form),
      samePageAction: rawAction === '',
    });
  }
  return out;
}

function collectLinks() {
  const seen = new Set();
  const links = [];
  const skipped = ['javascript:', 'mailto:', 'tel:', 'data:', 'about:', 'chrome:', 'blob:'];
  for (const a of document.querySelectorAll('a[href]')) {
    const href = a.href;
    if (!href || seen.has(href)) continue;
    if (skipped.some((p) => href.startsWith(p))) continue;
    seen.add(href);
    links.push({ href, text: (a.textContent || '').trim().slice(0, 60) });
    if (links.length >= 500) break;
  }
  return links;
}

function collectQueryParams() {
  try {
    return [...new URLSearchParams(location.search).entries()].map(([name, value]) => ({ name, value }));
  } catch (e) {
    return [];
  }
}

function collectHosts(links, forms) {
  const hosts = new Set();
  const add = (u) => {
    try { hosts.add(new URL(u).host); } catch (e) { /* skip malformed */ }
  };
  links.forEach((l) => add(l.href));
  forms.forEach((f) => add(f.action));
  return [...hosts];
}

function collectPageData() {
  const forms = collectForms();
  const links = collectLinks();
  return {
    url: location.href,
    title: document.title || '',
    forms,
    links,
    hosts: collectHosts(links, forms),
    queryParams: collectQueryParams(),
    cookies: document.cookie || '',
    collectedAt: Date.now(),
  };
}

collectPageData();
