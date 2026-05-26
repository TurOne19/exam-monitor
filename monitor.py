#!/usr/bin/env python3
"""
Transpordiamet driving exam slot monitor
Navigates: main.jsf → Juht menu → juhiloaTaotlus → slots popup
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

def ab_post(url, source, form, vs, render="@all", extra=None):
    """Simulate PrimeFaces.ab() call"""
    data = {
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": source,
        "javax.faces.partial.execute": "@all",
        "javax.faces.partial.render": render,
        source: source,
        form: form,
        "javax.faces.ViewState": vs,
    }
    if extra:
        data.update(extra)
    return fetch(url, data=data, ajax=True, referer=url)

def find_slots_btn(html):
    """Find the button that triggers the slots popup"""
    # Look for button near 'vabad' or 'kiiremini' or 'varaseimad'
    m = re.search(
        r'PrimeFaces\.ab\(\{s:&quot;(form:[^&]+)&quot;[^}]*\}\)[^<]*</[^>]+>\s*(?:[^<]*<[^>]+>\s*)*[^<]*(?:vabad|kiiremini|varaseimad)',
        html, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1)
    # Reverse: text then button
    m = re.search(
        r'(?:vabad|kiiremini|varaseimad)[^<]{0,500}?PrimeFaces\.ab\(\{s:&quot;(form:[^&]+)&quot;',
        html, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1)
    # Try finding any onclick near eksamiBroneerimine container
    idx = html.find("eksamiBroneerimineVaraseimad")
    if idx > 0:
        chunk = html[max(0, idx-1000):idx+200]
        m = re.search(r's:&quot;(form:[^&]+)&quot;', chunk)
        if m:
            return m.group(1)
    return None

def parse_slots(text):
    slots = []
    # Unescape XML entities
    text = text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    # Strong tag pattern
    for date_str, time_str, city in re.findall(
        r'<strong>(\d{2}\.\d{2}\.\d{4})</strong>\s*([\d:]+)\s*<strong>([^»<]+)', text):
        try:
            slots.append({
                "date": date_str.strip(), "time": time_str.strip(),
                "city": city.strip(), "datetime": datetime.strptime(date_str.strip(), "%d.%m.%Y")
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

    # Step 1: Load main.jsf
    html, url = fetch(MAIN_URL)
    print(f"Step 1 main.jsf: {url} ({len(html)} chars)")
    vs = get_viewstate(html)
    print(f"ViewState: {vs[:40]}")

    if not vs:
        print("No ViewState — session expired")
        send_telegram("⚠️ <b>Exam monitor</b>: сессия истекла, нужно обновить cookie")
        return

    # Step 2: Click "Juht" menu (j_idt87:j_idt90 with form j_idt87)
    print("Step 2: clicking Juht menu...")
    resp2, url2 = ab_post(MAIN_URL, "j_idt87:j_idt90", "j_idt87", vs)
    print(f"  Response: {url2} ({len(resp2)} chars)")
    print(f"  Preview: {resp2[:300]}")

    # Extract new ViewState if available
    vs2 = get_viewstate(resp2) or vs
    print(f"  New ViewState: {vs2[:40]}")

    # Step 3: Click "Juhtimisõigus »" (j_idt125:j_idt142)
    print("Step 3: clicking Juhtimisõigus...")
    resp3, url3 = ab_post(MAIN_URL, "j_idt125:j_idt142", "j_idt125", vs2)
    print(f"  Response: {url3} ({len(resp3)} chars)")
    print(f"  Preview: {resp3[:500]}")

    vs3 = get_viewstate(resp3) or vs2

    # Also try non-ajax POST for navigation
    print("Step 3b: trying full POST navigation...")
    try:
        resp3b, url3b = fetch(MAIN_URL, data={
            "j_idt125": "j_idt125",
            "j_idt125:j_idt142": "j_idt125:j_idt142",
            "javax.faces.ViewState": vs2,
        }, ajax=False, referer=MAIN_URL)
        print(f"  Response: {url3b} ({len(resp3b)} chars)")
        if "juhiloaTaotlus" in resp3b or "eksamiBroneerimine" in resp3b:
            print("  ✅ Got juhiloaTaotlus page!")
            html = resp3b
            vs3 = get_viewstate(resp3b) or vs3
        else:
            print(f"  Preview: {resp3b[:300]}")
    except Exception as e:
        print(f"  Error: {e}")

    # Step 4: Find and click slots button
    btn = find_slots_btn(html)
    print(f"Step 4: slots button = {btn}")

    all_slots = []

    if btn:
        print(f"Triggering slots popup with {btn}...")
        try:
            slots_resp, _ = ab_post(MAIN_URL, btn, "form", vs3,
                                    render="form:ametikoolitus")
            print(f"Slots response ({len(slots_resp)} chars): {slots_resp[:400]}")
            all_slots = parse_slots(slots_resp)
        except Exception as e:
            print(f"Error: {e}")

    # Also try to parse from any response we got
    for resp in [resp3, resp3b if 'resp3b' in dir() else "", html]:
        if resp:
            s = parse_slots(resp)
            if s:
                all_slots.extend(s)
                break

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
