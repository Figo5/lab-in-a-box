#!/usr/bin/env python3
"""Form and endpoint enumerator, driven by PageProbe.

Fetches a page server-side and reports the forms and fields found on it --
a server-side re-check of what PageProbe already surveyed client-side (in
the browser DOM), useful for confirming what an unauthenticated/anonymous
request actually sees versus what the logged-in browser session saw. This
is the tool `browser-extension/pageprobe/lib/commands.js`'s
`buildFormEnumCommand()` generates a ready-to-run command line for -- see
that function for the exact flag contract this parser must accept.

Usage:
    python form_enum.py --url URL [--cookie COOKIE] [--json report.json]
"""
import argparse
import json
import re
import sys

import requests

FORM_RE = re.compile(r'<form\b[^>]*>(.*?)</form>', re.IGNORECASE | re.DOTALL)
FORM_ATTR_RE = re.compile(r'<form\b([^>]*)>', re.IGNORECASE)
INPUT_RE = re.compile(r'<(input|select|textarea|button)\b([^>]*)/?>', re.IGNORECASE)
ATTR_RE = re.compile(r'(\w[\w-]*)\s*=\s*"([^"]*)"|(\w[\w-]*)\s*=\s*\'([^\']*)\'')


def build_parser():
    parser = argparse.ArgumentParser(
        description='Form and endpoint enumerator (authorized testing only)')
    parser.add_argument('--url', required=True, help='page URL to fetch and inspect')
    parser.add_argument('--cookie', default=None, help='Cookie header value, e.g. "a=1; b=2"')
    parser.add_argument('--json', default=None, metavar='PATH',
                        help='write the full report as JSON to this path')
    parser.add_argument('--timeout', type=float, default=10.0)
    return parser


def parse_args(argv=None):
    return build_parser().parse_args(argv)


def _parse_attrs(attr_str):
    attrs = {}
    for m in ATTR_RE.finditer(attr_str):
        if m.group(1) is not None:
            attrs[m.group(1).lower()] = m.group(2)
        else:
            attrs[m.group(3).lower()] = m.group(4)
    return attrs


def _field_name(attrs):
    return attrs.get('name') or attrs.get('id') or ''


def parse_forms(html):
    """Best-effort regex form parser (no external HTML-parsing dependency)."""
    forms = []
    for form_attr_match in FORM_ATTR_RE.finditer(html):
        start = form_attr_match.end()
        close = html.find('</form>', start)
        body = html[start:close] if close != -1 else html[start:]
        attrs = _parse_attrs(form_attr_match.group(1))

        fields = []
        for tag_match in INPUT_RE.finditer(body):
            tag = tag_match.group(1).lower()
            field_attrs = _parse_attrs(tag_match.group(2))
            name = _field_name(field_attrs)
            if not name:
                continue
            field_type = field_attrs.get('type', 'text' if tag == 'input' else tag).lower()
            fields.append({
                'name': name,
                'type': field_type,
                'value': field_attrs.get('value', ''),
            })

        forms.append({
            'action': attrs.get('action', ''),
            'method': attrs.get('method', 'GET').upper(),
            'fields': fields,
        })
    return forms


def parse_cookie_header(cookie):
    jar = {}
    if not cookie:
        return jar
    for part in cookie.split(';'):
        if '=' not in part:
            continue
        k, v = part.split('=', 1)
        jar[k.strip()] = v.strip()
    return jar


def enumerate_page(url, cookie=None, timeout=10.0):
    session = requests.Session()
    for k, v in parse_cookie_header(cookie).items():
        session.cookies.set(k, v)
    r = session.get(url, timeout=timeout)
    forms = parse_forms(r.text)
    return {
        'url': url,
        'status': r.status_code,
        'forms': forms,
        'form_count': len(forms),
    }


if __name__ == '__main__':
    a = parse_args()
    report = enumerate_page(a.url, cookie=a.cookie, timeout=a.timeout)

    print(f"[*] {report['url']} -> HTTP {report['status']}")
    print(f"[*] {report['form_count']} form(s) found")
    for i, form in enumerate(report['forms']):
        field_names = ', '.join(f['name'] for f in form['fields']) or '(none)'
        print(f"  [{i}] {form['method']} {form['action'] or '(same page)'} :: {field_names}")

    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
        print(f"[*] wrote {a.json}")
