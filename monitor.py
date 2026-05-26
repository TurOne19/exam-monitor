#!/usr/bin/env python3
"""
Transpordiamet driving exam slot monitor
Navigation: main.jsf -> juht.jsf -> juhiloaTaotlus.jsf -> slots popup
"""

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

def find_btn_near(html, keywords):
    """Find PrimeFaces button id near given keywords"""
    for kw in keywords:
        idx = html.lower().find(kw.lower())
        if idx < 0:
            continue
        # Search backwards for nearest button id
        chunk_before = html[max(0, idx-1500):idx]
        chunk_after = html[idx:idx+1500]
        for chunk in [chunk_after, chunk_before]:
            m = re.search(r's:&quot;([\w:]+)&quot;', chunk)
            if m:
                return m.group(1)
    return None

def find_form_for_btn(html, btn_id):
    """Find the form that contains this button"""
    idx = html.find(btn_id)
    if idx < 0:
        return "form"
    chunk = html[max(0, idx-3000):idx]
    forms = re.findall(r'<form[^>]*id="([^"]+)"', chunk)
    return forms[-1] if forms else "form"

def parse_slots(text):
    text = text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    slots = []
    for date_str, time_str, city in re.findall(
        r'<strong>(\d{2}\.\d{2}\.\d{4})</strong>\s*([\d:]+)\s*<strong>([^»<]+)', text):
        try:
            slots.append({
                "date": date_str.strip(), "time": time_str.strip(),
                "city": city.strip().rstrip('»').strip(),
                "datetime": datetime.strptime(date_str.strip(), "%d.%m.%Y")
            })
        except ValueError:
            continue
    return slots

def dedup(slots):
    seen, out = set(), []
    for s in slots:
        k = (s["date"], s["time"], s["city"])
        if k not in seen:
            seen.add(k); out.append(s)
    return out

def send_telegram(text):
    payload = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Checking exam slots...")

    if not SESSION_COOKIE or not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: missing config"); return

    # Step 1: Load main.jsf, POST to navigate to juht.jsf
    print("Step 1: Loading main.jsf...")
    html, url = fetch(MAIN_URL)
    print(f"  {url} ({len(html)} chars)")
    vs = get_viewstate(html)
    if not vs:
        print("No ViewState — session expired")
        send_telegram("⚠️ <b>Exam monitor</b>: сессия истекла, нужно обновить cookie")
        return

    # Navigate to juht.jsf via POST (like clicking Juht menu)
    print("Step 2: Navigating to juht.jsf...")
    juht_html, juht_url = fetch(MAIN_URL, data={
        "j_idt87": "j_idt87",
        "j_idt87:j_idt90": "j_idt87:j_idt90",
        "javax.faces.ViewState": vs,
    }, ajax=False, referer=MAIN_URL)
    print(f"  {juht_url} ({len(juht_html)} chars)")

    # If we got redirected, follow it
    if "juht.jsf" not in juht_url:
        juht_html, juht_url = fetch(JUHT_URL, referer=MAIN_URL)
        print(f"  Fetched directly: {juht_url} ({len(juht_html)} chars)")

    vs2 = get_viewstate(juht_html) or vs
    print(f"  ViewState: {vs2[:40]}")

    # Show juht.jsf links/buttons for debugging
    print("  Links on juht.jsf:")
    for m in re.finditer(r's:&quot;([\w:]+)&quot;[^}]*\}[^<]*</[^>]+>\s*(?:<[^>]+>\s*)*([^<]{3,50})', juht_html):
        print(f"    {m.group(1)} → '{m.group(2).strip()}'")

    # Step 3: Find and click link to juhiloaTaotlus
    print("Step 3: Finding juhiloaTaotlus link...")

    # Look for button near "juhiluba" or "eksam" or "registreeri"
    taotlus_btn = find_btn_near(juht_html, ["juhiluba", "registreeri eksam", "sõidueksam", "juhiloaTaotlus"])
    print(f"  Found button: {taotlus_btn}")

    # Try all forms for navigation
    taotlus_html = ""
    taotlus_url = ""

    # Try clicking the button if found
    if taotlus_btn:
        form_id = find_form_for_btn(juht_html, taotlus_btn)
        print(f"  Form: {form_id}")
        try:
            taotlus_html, taotlus_url = fetch(JUHT_URL, data={
                form_id: form_id,
                taotlus_btn: taotlus_btn,
                "javax.faces.ViewState": vs2,
            }, ajax=False, referer=JUHT_URL)
            print(f"  Nav result: {taotlus_url} ({len(taotlus_html)} chars)")
        except Exception as e:
            print(f"  Error: {e}")

    # If still not on juhiloaTaotlus, try direct GET
    if "juhiloaTaotlus" not in taotlus_url:
        PAGE_URL = f"{BASE_URL}/pages/juht/juhiloataotlus/juhiloaTaotlus.jsf"
        try:
            taotlus_html, taotlus_url = fetch(PAGE_URL, referer=JUHT_URL)
            print(f"  Direct GET: {taotlus_url} ({len(taotlus_html)} chars)")
        except Exception as e:
            print(f"  Direct GET error: {e}")

    if not taotlus_html:
        taotlus_html = juht_html

    vs3 = get_viewstate(taotlus_html) or vs2
    print(f"  ViewState: {vs3[:40]}")

    # Step 4: Trigger slots popup
    print("Step 4: Triggering slots popup...")

    slots_btn = find_btn_near(taotlus_html, ["vabad", "kiiremini", "varaseimad", "eksamiBroneerimine"])
    print(f"  Slots button: {slots_btn}")

    all_slots = []

    if slots_btn:
        form_id = find_form_for_btn(taotlus_html, slots_btn)
        current_url = taotlus_url.split("?")[0]
        try:
            slots_resp, _ = fetch(current_url, data={
                "javax.faces.partial.ajax": "true",
                "javax.faces.source": slots_btn,
                "javax.faces.partial.execute": slots_btn,
                "javax.faces.partial.render": "form:ametikoolitus",
                slots_btn: slots_btn,
                form_id: form_id,
                "javax.faces.ViewState": vs3,
            }, ajax=True, referer=current_url)
            print(f"  Slots response ({len(slots_resp)} chars): {slots_resp[:400]}")
            all_slots = parse_slots(slots_resp)
        except Exception as e:
            print(f"  Error: {e}")

    # Also try parsing from pages directly
    for page in [taotlus_html, juht_html]:
        s = parse_slots(page)
        if s:
            all_slots.extend(s)

    unique = dedup(all_slots)
    print(f"\nTotal unique slots: {len(unique)}")
    for s in sorted(unique, key=lambda x: x["datetime"])[:10]:
        print(f"  {s['date']} {s['time']} — {s['city']}")

    early = [s for s in unique if s["datetime"] < datetime.strptime(TARGET_DATE, "%Y-%m-%d")]
    print(f"Slots before {TARGET_DATE}: {len(early)}")

    if early:
        lines = [f"🚗 <b>Свободные места до {TARGET_DATE}!</b>\n"]
        for s in sorted(early, key=lambda x: x["datetime"]):
            lines.append(f"📅 {s['date']} {s['time']} — <b>{s['city']}</b>")
        lines.append(f"\n🔗 https://eteenindus.mnt.ee/pages/juht/juhiloataotlus/juhiloaTaotlus.jsf")
        result = send_telegram("\n".join(lines))
        print("✅ Sent!" if result.get("ok") else f"Error: {result}")
    else:
        print("No early slots — keep monitoring")

if __name__ == "__main__":
    main()
