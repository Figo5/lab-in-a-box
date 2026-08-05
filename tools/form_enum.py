#!/usr/bin/env python3
"""Form & endpoint enumerator for authorized testing.

Fetches a page and reports its attack surface: every form with its action,
method, and input fields (including hidden CSRF fields), all links on the page,
and the query parameters seen across them. Optionally writes a JSON report.

Usage:
    python form_enum.py --url http://127.0.0.1:8081/login.php
    python form_enum.py --url http://127.0.0.1:8081/vulnerabilities/brute/index.php \
        --cookie "PHPSESSID=..." --json report.json
"""
import argparse
import json
import sys
import urllib.parse
from html.parser import HTMLParser

import requests


class FormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.links = []
        self._form = None
        self._base = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self._form = {
                "action": a.get("action", ""),
                "method": a.get("method", "GET").upper(),
                "inputs": [],
            }
            self.forms.append(self._form)
        elif tag == "input" and self._form is not None:
            self._form["inputs"].append({
                "name": a.get("name", ""),
                "type": a.get("type", "text"),
                "value": a.get("value", ""),
            })
        elif tag in ("select", "textarea") and self._form is not None:
            self._form["inputs"].append({"name": a.get("name", ""), "type": tag, "value": ""})
        elif tag == "a":
            href = a.get("href")
            if href:
                self.links.append(href)
        elif tag == "base":
            self._base = a.get("href", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self._form = None


def fetch(url, cookie=None, user_agent=None, proxy=None, timeout=10.0):
    headers = {}
    if user_agent:
        headers["User-Agent"] = user_agent
    if cookie:
        headers["Cookie"] = cookie
    proxies = {"http": proxy, "https": proxy} if proxy else None
    return requests.get(url, headers=headers, timeout=timeout, proxies=proxies,
                        allow_redirects=True)


def analyze(final_url, resp):
    parser = FormParser()
    parser.feed(resp.text)
    base = urllib.parse.urljoin(final_url, parser._base) or final_url

    forms = []
    for f in parser.forms:
        action = urllib.parse.urljoin(base, f["action"]) if f["action"] else final_url
        forms.append({"action": action, "method": f["method"], "inputs": f["inputs"]})

    seen = set()
    links = []
    for href in parser.links:
        abs_url = urllib.parse.urljoin(base, href)
        if abs_url.startswith(("http://", "https://")) and abs_url not in seen:
            seen.add(abs_url)
            links.append(abs_url)

    params = set()
    for u in links + [f["action"] for f in forms]:
        query = urllib.parse.urlsplit(u).query
        if query:
            params.update(k for k, _ in urllib.parse.parse_qsl(query))

    return {
        "url": final_url,
        "status": resp.status_code,
        "content_length": len(resp.content),
        "forms": forms,
        "links": links,
        "params": sorted(params),
    }


def report(data):
    print(f"Page: {data['url']}  (status={data['status']} len={data['content_length']})")
    if not data["forms"]:
        print("No forms found.")
    for i, f in enumerate(data["forms"], 1):
        print(f"\nForm #{i}: {f['method']} {f['action']}")
        if not f["inputs"]:
            print("  (no input fields)")
        for inp in f["inputs"]:
            val = f" value={inp['value']!r}" if inp.get("value") else ""
            print(f"  - {inp['name'] or '<unnamed>'}  [{inp['type']}]{val}")
    if data["links"]:
        print(f"\nLinks ({len(data['links'])}):")
        for link in data["links"]:
            print(f"  {link}")
    if data["params"]:
        print(f"\nParameters seen ({len(data['params'])}): {', '.join(data['params'])}")


def main():
    ap = argparse.ArgumentParser(
        description="Form & endpoint enumerator (authorized testing only)")
    ap.add_argument("--url", required=True)
    ap.add_argument("--cookie", help="Cookie header, e.g. PHPSESSID=abc")
    ap.add_argument("--user-agent")
    ap.add_argument("--proxy")
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--json", dest="json_out", help="Write a JSON report to this file")
    a = ap.parse_args()

    try:
        resp = fetch(a.url, a.cookie, a.user_agent, a.proxy, a.timeout)
    except requests.RequestException as exc:
        sys.exit(f"[!] request failed: {exc}")

    data = analyze(resp.url, resp)
    report(data)
    if a.json_out:
        with open(a.json_out, "w") as f:
            json.dump(data, f, indent=2)
        print(f"\nJSON report written to {a.json_out}")


if __name__ == "__main__":
    main()
