#!/usr/bin/env python3
"""
Transpordiamet driving exam slot monitor
Uses the PUBLIC page — no login required!
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

PUBLIC_URL = "https://eteenindus.mnt.ee/public/vabadSoidueksamiajad.xhtml"

def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "et-EE,et;q=0.9,en;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        content = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            content = gzip.decompress(content)
        return content.decode("utf-8", errors="replace")

def parse_slots(html):
    slots = []
    # Pattern: DD.MM.YYYY HH:MM City
    pattern = r'(\d{2}\.\d{2}\.\d{4})\D{1,10}?(\d{2}:\d{2})\D{1,30}?([A-ZÕÄÖÜ][a-zõäöü]+(?:\s+[A-Za-zÕÄÖÜõäöü]+)*)'
    # Also try strong tag pattern
    pattern2 = r'<strong>(\d{2}\.\d{2}\.\d{4})</strong>\s*([\d:]+)\s*<strong>([^»<]+)'
    
    for p in [pattern2, pattern]:
        for m in re.finditer(p, html):
            date_str, time_str, city = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
            city = city.rstrip('»').strip()
            try:
                dt = datetime.strptime(date_str, "%d.%m.%Y")
                slots.append({"date": date_str, "time": time_str, "city": city, "datetime": dt})
            except ValueError:
                continue
        if slots:
            break
    
    # Deduplicate
    seen = set()
    unique = []
    for s in slots:
        k = (s["date"], s["time"], s["city"])
        if k not in seen:
            seen.add(k); unique.append(s)
    return unique

def filter_before(slots, date_str):
    before = datetime.strptime(date_str, "%Y-%m-%d")
    return [s for s in slots if s["datetime"] < before]

def send_telegram(text):
    payload = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Checking exam slots...")

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: missing Telegram config"); return

    try:
        html = fetch(PUBLIC_URL)
        print(f"Page loaded: {len(html)} chars")
    except Exception as e:
        print(f"Fetch error: {e}"); return

    # Debug: show relevant section
    idx = html.find("2026")
    if idx > 0:
        print(f"Date context: {html[max(0,idx-100):idx+200]}")

    all_slots = parse_slots(html)
    print(f"Total slots found: {len(all_slots)}")
    for s in sorted(all_slots, key=lambda x: x["datetime"])[:10]:
        print(f"  {s['date']} {s['time']} — {s['city']}")

    early = filter_before(all_slots, TARGET_DATE)
    print(f"Slots before {TARGET_DATE}: {len(early)}")

    if early:
        lines = [f"🚗 <b>Свободные места до {TARGET_DATE}!</b>\n"]
        for s in sorted(early, key=lambda x: x["datetime"]):
            lines.append(f"📅 {s['date']} {s['time']} — <b>{s['city']}</b>")
        lines.append(f"\n🔗 {PUBLIC_URL}")
        result = send_telegram("\n".join(lines))
        print("✅ Notification sent!" if result.get("ok") else f"Telegram error: {result}")
    else:
        print(f"No slots before {TARGET_DATE} — keep monitoring")

if __name__ == "__main__":
    main()
