#!/usr/bin/env python3
"""DEBUG — find slots button on juhiloaTaotlus.jsf"""

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
JUHT_URL = f"{BASE_URL}/juht.jsf?lang=et"
PAGE_URL = f"{BASE_URL}/pages/juht/juhiloataotlus/juhiloaTaotlus.jsf"

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
        req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), headers=headers)
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

def navigate_to_taotlus():
    """Full navigation to juhiloaTaotlus.jsf"""
    html, _ = fetch(MAIN_URL)
    vs = get_viewstate(html)

    juht_html, _ = fetch(MAIN_URL, data={
        "j_idt87": "j_idt87",
        "j_idt87:j_idt90": "j_idt87:j_idt90",
        "javax.faces.ViewState": vs,
    }, referer=MAIN_URL)
    vs2 = get_viewstate(juht_html) or vs

    # Find button to juhiloaTaotlus on juht.jsf
    m = re.search(r's:&quot;(j_idt127:[^&]+)&quot;', juht_html)
    btn = m.group(1) if m else "j_idt127:j_idt217"

    taotlus_html, taotlus_url = fetch(JUHT_URL, data={
        "j_idt127": "j_idt127",
        btn: btn,
        "javax.faces.ViewState": vs2,
    }, referer=JUHT_URL)
    vs3 = get_viewstate(taotlus_html) or vs2
    return taotlus_html, taotlus_url, vs3

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Navigating to juhiloaTaotlus...")
    taotlus_html, taotlus_url, vs = navigate_to_taotlus()
    print(f"Page: {taotlus_url} ({len(taotlus_html)} chars)")
    print(f"ViewState: {vs[:50]}")

    # Dump ALL onclick buttons
    print("\n=== ALL ONCLICK BUTTONS ===")
    for m in re.finditer(r's:&quot;([^&]+)&quot;([^)]*)\)[^<]*(?:</[^>]+>)*([^<]{0,60})', taotlus_html):
        print(f"  {m.group(1)} | {m.group(3).strip()[:50]}")

    # Find everything around 'vabad' 'eksam' 'kiiremini'
    print("\n=== CONTEXT AROUND EXAM KEYWORDS ===")
    for kw in ["vabad", "kiiremini", "varaseimad", "eksamiBroneerimine", "Sõidueksam"]:
        idx = taotlus_html.find(kw)
        if idx >= 0:
            print(f"\n-- '{kw}' at pos {idx} --")
            print(taotlus_html[max(0,idx-300):idx+300])

    # Show all form ids in the page
    print("\n=== FORMS ===")
    for m in re.finditer(r'<form[^>]*id="([^"]+)"', taotlus_html):
        print(f"  {m.group(1)}")

    # Show 2000 chars from middle of page (content area)
    mid = len(taotlus_html) // 2
    print(f"\n=== MIDDLE OF PAGE ({mid-1000} to {mid+1000}) ===")
    print(taotlus_html[mid-1000:mid+1000])

if __name__ == "__main__":
    main()
