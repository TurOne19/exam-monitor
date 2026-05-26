#!/usr/bin/env python3
"""
Transpordiamet driving exam slot monitor
Sends Telegram notification when slots appear before target date
"""

import os
import re
import json
import urllib.request
import urllib.error
from datetime import datetime

# ─── CONFIG ────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TARGET_DATE = os.environ.get("TARGET_DATE", "2026-07-01")
SESSION_COOKIE = os.environ.get("SESSION_COOKIE", "")
# ───────────────────────────────────────────────────────────────────

URL = "https://eteenindus.mnt.ee/pages/juht/juhiloataotlus/juhiloaTaotlus.jsf"

def fetch_page(session_cookie: str) -> str:
    req = urllib.request.Request(
        URL,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Cookie": session_cookie,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "et-EE,et;q=0.9,en;q=0.8",
            "Referer": URL,
        }
    )
    opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
    with opener.open(req, timeout=15) as resp:
        final_url = resp.geturl()
        print(f"Final URL: {final_url}")
        return resp.read().decode("utf-8", errors="replace")

def parse_slots(html: str) -> list:
    slots = []
    pattern = r'<strong>(\d{2}\.\d{2}\.\d{4})</strong>\s*([\d:]+)\s*<strong>([^»]+)»</strong>'
    matches = re.findall(pattern, html)
    for date_str, time_str, city in matches:
        try:
            slot_date = datetime.strptime(date_str.strip(), "%d.%m.%Y")
            slots.append({
                "date": date_str.strip(),
                "time": time_str.strip(),
                "city": city.strip(),
                "datetime": slot_date,
            })
        except ValueError:
            continue
    return slots

def filter_slots_before(slots: list, before_date_str: str) -> list:
    before = datetime.strptime(before_date_str, "%Y-%m-%d")
    return [s for s in slots if s["datetime"] < before]

def send_telegram(token: str, chat_id: str, text: str):
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Checking exam slots...")

    if not SESSION_COOKIE:
        print("ERROR: SESSION_COOKIE not set")
        return
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not set")
        return

    try:
        html = fetch_page(SESSION_COOKIE)
    except urllib.error.HTTPError as e:
        print(f"HTTP error: {e.code}")
        if e.code in (302, 401, 403):
            send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
                "⚠️ <b>Exam monitor</b>: сессия истекла, нужно обновить cookie")
        return
    except Exception as e:
        print(f"Fetch error: {e}")
        return

    # Check if we're actually on the right page (not redirected to login)
    if "juhiloaTaotlus" not in html and "eksamiBroneerimine" not in html:
        print("Login page detected — session expired")
        send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
            "⚠️ <b>Exam monitor</b>: сессия истекла, нужно обновить cookie")
        return

    print("Session OK — page loaded successfully")

    all_slots = parse_slots(html)
    print(f"Found {len(all_slots)} total slots")

    if not all_slots:
        print("No slots parsed — slots may not be visible on this page yet")
        return

    early_slots = filter_slots_before(all_slots, TARGET_DATE)
    print(f"Slots before {TARGET_DATE}: {len(early_slots)}")

    if early_slots:
        lines = [f"🚗 <b>Свободные места на экзамен до {TARGET_DATE}!</b>\n"]
        for s in sorted(early_slots, key=lambda x: x["datetime"]):
            lines.append(f"📅 {s['date']} {s['time']} — <b>{s['city']}</b>")
        lines.append(f"\n🔗 {URL}")
        message = "\n".join(lines)
        result = send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, message)
        if result.get("ok"):
            print("✅ Telegram notification sent!")
        else:
            print(f"Telegram error: {result}")
    else:
        print(f"No slots before {TARGET_DATE} — nothing to notify")

if __name__ == "__main__":
    main()
