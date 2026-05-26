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
import urllib.parse
from datetime import datetime

# ─── CONFIG ────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TARGET_DATE = os.environ.get("TARGET_DATE", "2026-07-01")
SESSION_COOKIE = os.environ.get("SESSION_COOKIE", "")
# ───────────────────────────────────────────────────────────────────

BASE_URL = "https://eteenindus.mnt.ee"
MAIN_URL = f"{BASE_URL}/pages/juht/juhiloataotlus/juhiloaTaotlus.jsf"
EXAM_URL = f"{BASE_URL}/pages/juht/juhiloataotlus/eksamiBroneerimine.jsf"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "et-EE,et;q=0.9,en;q=0.8",
}

def get(url: str) -> str:
    req = urllib.request.Request(url, headers={**HEADERS, "Cookie": SESSION_COOKIE})
    opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
    with opener.open(req, timeout=15) as resp:
        print(f"GET {url} -> {resp.geturl()} [{resp.status}]")
        return resp.read().decode("utf-8", errors="replace")

def post(url: str, data: dict, referer: str = None) -> str:
    payload = urllib.parse.urlencode(data).encode()
    headers = {
        **HEADERS,
        "Cookie": SESSION_COOKIE,
        "Content-Type": "application/x-www-form-urlencoded",
        "Faces-Request": "partial/ajax",
        "X-Requested-With": "XMLHttpRequest",
    }
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, data=payload, headers=headers)
    opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
    with opener.open(req, timeout=15) as resp:
        print(f"POST {url} -> [{resp.status}]")
        return resp.read().decode("utf-8", errors="replace")

def extract_viewstate(html: str) -> str:
    m = re.search(r'id="javax\.faces\.ViewState"[^>]*value="([^"]+)"', html)
    if m:
        return m.group(1)
    m = re.search(r'javax\.faces\.ViewState["\s:=]+([A-Za-z0-9+/=_\-:]+)', html)
    return m.group(1) if m else ""

def extract_form_id(html: str) -> str:
    """Find the main form id"""
    m = re.search(r'<form[^>]+id="([^"]+)"', html)
    return m.group(1) if m else "juhiloaTaotlusForm"

def find_free_slots_button(html: str) -> str:
    """Find the id of the 'Kus saab kõige kiiremini eksamile' button/link"""
    m = re.search(r'id="([^"]+)"[^>]*>\s*Kus saab k', html)
    if m:
        return m.group(1)
    # Try finding onclick with varaseimad
    m = re.search(r'id="([^"]+varaseimad[^"]*)"', html, re.IGNORECASE)
    if m:
        return m.group(1)
    return None

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

    # Step 1: Load main page
    try:
        main_html = get(MAIN_URL)
    except Exception as e:
        print(f"Fetch error: {e}")
        return

    if "juhiloaTaotlus" not in main_html and "eksamiBroneerimine" not in main_html:
        print("Session expired")
        send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
            "⚠️ <b>Exam monitor</b>: сессия истекла, нужно обновить cookie")
        return

    print("Session OK")

    # Step 2: Extract ViewState and form info
    viewstate = extract_viewstate(main_html)
    form_id = extract_form_id(main_html)
    print(f"ViewState: {viewstate[:30]}..." if viewstate else "ViewState: NOT FOUND")
    print(f"Form ID: {form_id}")

    # Debug: find the button
    btn_id = find_free_slots_button(main_html)
    print(f"Free slots button ID: {btn_id}")

    # Also print relevant snippet around varaseimad
    snippet_match = re.search(r'.{0,200}varaseimad.{0,200}', main_html, re.IGNORECASE)
    if snippet_match:
        print(f"Varaseimad context: {snippet_match.group()[:300]}")

    # Step 3: Try to trigger the free slots popup via AJAX POST
    slots_html = ""

    if viewstate and btn_id:
        try:
            post_data = {
                "javax.faces.partial.ajax": "true",
                "javax.faces.source": btn_id,
                "javax.faces.partial.execute": "@all",
                "javax.faces.partial.render": "@all",
                btn_id: btn_id,
                form_id: form_id,
                "javax.faces.ViewState": viewstate,
            }
            slots_html = post(MAIN_URL, post_data, referer=MAIN_URL)
            print(f"POST response length: {len(slots_html)}")
            print(f"POST preview: {slots_html[:500]}")
        except Exception as e:
            print(f"POST error: {e}")

    # Step 4: Also try fetching eksamiBroneerimine.jsf directly
    try:
        exam_html = get(EXAM_URL)
        print(f"eksamiBroneerimine.jsf length: {len(exam_html)}")
        # Try to find slots there too
        extra_slots = parse_slots(exam_html)
        if extra_slots:
            print(f"Found {len(extra_slots)} slots in eksamiBroneerimine.jsf")
    except Exception as e:
        print(f"Exam URL fetch error: {e}")
        exam_html = ""

    # Step 5: Parse slots from all sources
    all_slots = parse_slots(main_html) + parse_slots(slots_html) + parse_slots(exam_html if 'exam_html' in dir() else "")
    # Deduplicate
    seen = set()
    unique_slots = []
    for s in all_slots:
        key = (s["date"], s["time"], s["city"])
        if key not in seen:
            seen.add(key)
            unique_slots.append(s)

    print(f"Found {len(unique_slots)} total unique slots")

    if not unique_slots:
        print("No slots found — will keep monitoring")
        return

    early_slots = filter_slots_before(unique_slots, TARGET_DATE)
    print(f"Slots before {TARGET_DATE}: {len(early_slots)}")

    if early_slots:
        lines = [f"🚗 <b>Свободные места на экзамен до {TARGET_DATE}!</b>\n"]
        for s in sorted(early_slots, key=lambda x: x["datetime"]):
            lines.append(f"📅 {s['date']} {s['time']} — <b>{s['city']}</b>")
        lines.append(f"\n🔗 {MAIN_URL}")
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
