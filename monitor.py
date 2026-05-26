#!/usr/bin/env python3
"""DEBUG — find navigation from main.jsf to exam page"""

import os
import re
import json
import gzip
import urllib.request
import urllib.parse
from datetime import datetime

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TARGET_DATE = os.environ.get("TARGET_DATE", "2026-07-01")
SESSION_COOKIE = os.environ.get("SESSION_COOKIE", "")

BASE_URL = "https://eteenindus.mnt.ee"
MAIN_URL = f"{BASE_URL}/main.jsf"

def fetch(url, data=None, ajax=False, referer=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "et-EE,et;q=0.9,en;q=0.8",
        "Cookie": SESSION_COOKIE,
        "Referer": referer or MAIN_URL,
        "Origin": BASE_URL,
    }
    if data:
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        if ajax:
            headers["Faces-Request"] = "partial/ajax"
            headers["X-Requested-With"] = "XMLHttpRequest"
            headers["Accept"] = "application/xml, text/xml, */*; q=0.01"
        else:
            headers["Accept"] = "text/html,application/xhtml+xml,*/*;q=0.8"
        payload = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(url, data=payload, headers=headers)
    else:
        headers["Accept"] = "text/html,application/xhtml+xml,*/*;q=0.8"
        req = urllib.request.Request(url, headers=headers)

    with urllib.request.urlopen(req, timeout=15) as resp:
        content = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            content = gzip.decompress(content)
        return content.decode("utf-8", errors="replace"), resp.geturl()

def get_viewstate(html):
    m = re.search(r'id="javax\.faces\.ViewState"[^>]*value="([^"]+)"', html)
    if not m:
        m = re.search(r'javax\.faces\.ViewState[^>]*value="([^"]+)"', html)
    return m.group(1) if m else ""

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Loading main.jsf...")

    html, url = fetch(MAIN_URL)
    print(f"Loaded: {url} ({len(html)} chars)")

    vs = get_viewstate(html)
    print(f"ViewState: {vs[:60]}")

    # Dump ALL links and form actions
    print("\n=== ALL HREFS ===")
    hrefs = re.findall(r'href="([^"]{3,})"', html)
    for h in hrefs[:30]:
        print(f"  {h}")

    # Find menu/navigation elements — look for onclick with jsf navigation
    print("\n=== ALL ONCLICK ===")
    onclicks = re.findall(r'onclick="([^"]{10,})"', html)
    for o in onclicks[:20]:
        print(f"  {o[:150]}")

    # Find all <a> tags with text
    print("\n=== ALL LINKS WITH TEXT ===")
    atags = re.findall(r'<a[^>]+>([^<]{3,50})</a>', html)
    for a in atags[:30]:
        print(f"  {a.strip()}")

    # Find forms and their submit buttons
    print("\n=== FORMS AND BUTTONS ===")
    form_blocks = re.findall(r'<form[^>]*id="([^"]*)"[^>]*action="([^"]*)"[^>]*>(.*?)</form>', html, re.DOTALL)
    for form_id, action, content in form_blocks:
        buttons = re.findall(r'(?:input|button)[^>]*(?:value|id)="([^"]{3,50})"', content)
        if buttons:
            print(f"  Form '{form_id}' -> {action}: buttons={buttons[:5]}")

    # Look for navigation specifically to juhiloo/eksam
    print("\n=== SECTION 1000 chars around 'juht' ===")
    for m in re.finditer(r'.{0,200}[Jj]uht.{0,200}', html):
        print(m.group()[:300])
        print("---")

    # Print a large chunk of the body
    body_start = html.find("<body")
    if body_start > 0:
        print(f"\n=== BODY START (first 2000 chars) ===")
        print(html[body_start:body_start+2000])

if __name__ == "__main__":
    main()
