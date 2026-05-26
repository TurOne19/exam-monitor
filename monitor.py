#!/usr/bin/env python3
"""DEBUG — dump all buttons on juhiloaTaotlus.jsf"""

import os, re, gzip, json, urllib.request, urllib.parse
from datetime import datetime

SESSION_COOKIE = os.environ.get("SESSION_COOKIE", "")
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
    # Step 1: main.jsf
    html, _ = fetch(MAIN_URL)
    vs = get_viewstate(html)

    # Step 2: juht.jsf
    juht_html, _ = fetch(MAIN_URL, data={
        "j_idt87": "j_idt87", "j_idt87:j_idt90": "j_idt87:j_idt90",
        "javax.faces.ViewState": vs,
    }, referer=MAIN_URL)
    vs2 = get_viewstate(juht_html) or vs

    # Step 3: juhiloaTaotlus.jsf
    taotlus_html, taotlus_url = fetch(JUHT_URL, data={
        "j_idt127": "j_idt127", "j_idt127:j_idt217": "j_idt127:j_idt217",
        "javax.faces.ViewState": vs2,
    }, referer=JUHT_URL)
    vs3 = get_viewstate(taotlus_html) or vs2
    print(f"juhiloaTaotlus: {taotlus_url} ({len(taotlus_html)} chars)")

    # Dump ALL buttons with context
    print("\n=== ALL BUTTONS ON juhiloaTaotlus.jsf ===")
    for m in re.finditer(r's:&quot;([^&]+)&quot;([^)]*)\)', taotlus_html):
        btn_id = m.group(1)
        pos = m.start()
        chunk = taotlus_html[max(0,pos-300):pos+400]
        text = re.sub(r'<[^>]+>', ' ', chunk)
        text = re.sub(r'\s+', ' ', text).strip()[:150]
        print(f"  [{btn_id}] → {text}")

    # Keywords
    print("\n=== KEYWORDS ===")
    for kw in ["vabad", "kiiremini", "varaseimad", "eksamiBroneerimine", "Sõidueksam", "broneeri"]:
        idx = taotlus_html.lower().find(kw.lower())
        if idx >= 0:
            chunk = taotlus_html[max(0,idx-400):idx+400]
            text = re.sub(r'\s+', ' ', chunk).strip()
            print(f"\n-- '{kw}' --")
            print(text[:500])

    # All forms
    print("\n=== FORMS ===")
    for m in re.finditer(r'<form[^>]*id="([^"]+)"', taotlus_html):
        print(f"  {m.group(1)}")

    # Try to trigger AJAX for all "form:*" buttons
    print("\n=== TRYING AJAX ON form:* BUTTONS ===")
    form_btns = re.findall(r's:&quot;(form:[^&]+)&quot;', taotlus_html)
    print(f"form:* buttons: {form_btns}")
    taotlus_base = taotlus_url.split("?")[0]
    for btn in form_btns[:10]:
        try:
            resp, _ = fetch(taotlus_base, data={
                "javax.faces.partial.ajax": "true",
                "javax.faces.source": btn,
                "javax.faces.partial.execute": btn,
                "javax.faces.partial.render": "@all",
                btn: btn,
                "form": "form",
                "javax.faces.ViewState": vs3,
            }, ajax=True, referer=taotlus_url)
            preview = re.sub(r'<[^>]+>', ' ', resp[:500])
            preview = re.sub(r'\s+', ' ', preview).strip()[:200]
            print(f"  {btn} → ({len(resp)} chars) {preview}")
        except Exception as e:
            print(f"  {btn} → ERROR: {e}")

if __name__ == "__main__":
    main()
