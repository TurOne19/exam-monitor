#!/usr/bin/env python3
"""DEBUG — dump juht.jsf buttons to find juhiloaTaotlus navigation"""

import os, re, gzip, json, urllib.request, urllib.parse
from datetime import datetime

SESSION_COOKIE = os.environ.get("SESSION_COOKIE", "")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
BASE_URL = "https://eteenindus.mnt.ee"
MAIN_URL = f"{BASE_URL}/main.jsf"
JUHT_URL = f"{BASE_URL}/juht.jsf?lang=et"

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

def main():
    # Navigate to juht.jsf
    html, _ = fetch(MAIN_URL)
    vs = get_viewstate(html)
    juht_html, juht_url = fetch(MAIN_URL, data={
        "j_idt87": "j_idt87",
        "j_idt87:j_idt90": "j_idt87:j_idt90",
        "javax.faces.ViewState": vs,
    }, referer=MAIN_URL)
    vs2 = get_viewstate(juht_html) or vs
    print(f"juht.jsf: {juht_url} ({len(juht_html)} chars)")

    # ALL onclick buttons with surrounding text
    print("\n=== ALL BUTTONS WITH CONTEXT ===")
    for m in re.finditer(r's:&quot;([^&]+)&quot;([^)]*)\)', juht_html):
        btn_id = m.group(1)
        pos = m.start()
        # Get text around this button
        chunk = juht_html[max(0,pos-200):pos+400]
        # Extract readable text
        text = re.sub(r'<[^>]+>', ' ', chunk)
        text = re.sub(r'\s+', ' ', text).strip()[:120]
        print(f"  [{btn_id}] → {text}")

    # Look for eksam/juhiluba/taotlus keywords
    print("\n=== CONTEXT AROUND EXAM KEYWORDS ===")
    for kw in ["eksam", "juhiluba", "taotlus", "registreeri", "juhiloaTaotlus", "sõidueksam"]:
        for m in re.finditer(kw, juht_html, re.IGNORECASE):
            start = max(0, m.start()-200)
            end = min(len(juht_html), m.end()+200)
            snippet = re.sub(r'<[^>]+>', ' ', juht_html[start:end])
            snippet = re.sub(r'\s+', ' ', snippet).strip()
            print(f"\n-- '{kw}' --")
            print(snippet[:300])

    # Try each j_idt127:* button to see where it goes
    print("\n=== TRYING ALL j_idt127 BUTTONS ===")
    btns = re.findall(r's:&quot;(j_idt127:[^&]+)&quot;', juht_html)
    print(f"Found: {btns}")
    for btn in btns[:8]:
        try:
            resp, rurl = fetch(JUHT_URL, data={
                "j_idt127": "j_idt127",
                btn: btn,
                "javax.faces.ViewState": vs2,
            }, referer=JUHT_URL)
            print(f"  {btn} → {rurl} ({len(resp)} chars)")
            if "juhiloaTaotlus" in rurl or "eksam" in rurl.lower():
                print(f"  *** FOUND IT! ***")
        except Exception as e:
            print(f"  {btn} → ERROR: {e}")

if __name__ == "__main__":
    main()
