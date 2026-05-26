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

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TARGET_DATE = os.environ.get("TARGET_DATE", "2026-07-01")
SESSION_COOKIE = os.environ.get("SESSION_COOKIE", "")

BASE_URL = "https://eteenindus.mnt.ee"
PAGE_URL = f"{BASE_URL}/pages/juht/juhiloataotlus/juhiloaTaotlus.jsf"

HEADERS_BASE = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "et-EE,et;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}

def http_get(url):
    req = urllib.request.Request(url, headers={
        **HEADERS_BASE,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Cookie": SESSION_COOKIE,
    })
    # Don't follow redirects — detect them
    opener = urllib.request.build_opener()
    opener.handler_map = {}
    # Use default opener but catch redirects manually
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read()
            # Decompress if needed
            import gzip
            import io
            enc = resp.headers.get("Content-Encoding", "")
            if enc == "gzip":
                content = gzip.decompress(content)
            return content.decode("utf-8", errors="replace"), resp.geturl(), resp.status
    except urllib.error.HTTPError as e:
        return "", e.headers.get("Location", ""), e.code

def http_post_ajax(url, data, referer=None):
    payload = urllib.parse.urlencode(data).encode()
    headers = {
        **HEADERS_BASE,
        "Accept": "application/xml, text/xml, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Faces-Request": "partial/ajax",
        "X-Requested-With": "XMLHttpRequest",
        "Cookie": SESSION_COOKIE,
        "Referer": referer or url,
        "Origin": BASE_URL,
    }
    req = urllib.request.Request(url, data=payload, headers=headers)
    import gzip
    with urllib.request.urlopen(req, timeout=15) as resp:
        content = resp.read()
        enc = resp.headers.get("Content-Encoding", "")
        if enc == "gzip":
            content = gzip.decompress(content)
        return content.decode("utf-8", errors="replace")

def get_viewstate(html):
    m = re.search(r'id="javax\.faces\.ViewState"[^>]*value="([^"]+)"', html)
    if not m:
        m = re.search(r'javax\.faces\.ViewState[^>]*value="([^"]+)"', html)
    return m.group(1) if m else ""

def find_slots_button(html):
    """Find button ID near 'vabad' or 'varaseimad' text"""
    # Look for onclick or id near these keywords
    patterns = [
        r'id="(form:[^"]+)"[^>]*>[^<]*(?:vabad|kiiremini|varaseimad)',
        r'(?:vabad|kiiremini|varaseimad)[^<]*<[^>]*id="(form:[^"]+)"',
        r'id="([^"]*varaseimad[^"]*)"',
        r'id="([^"]*vabad[^"]*)"',
    ]
    for p in patterns:
        m = re.search(p, html, re.IGNORECASE)
        if m:
            return m.group(1)

    # Fallback: find any button/link in ametikoolitus section
    m = re.search(r'ametikoolitus[^}]{0,2000}?id="(form:j_idt\d+)"', html, re.DOTALL)
    if m:
        return m.group(1)
    return None

def parse_slots_from_xml(xml):
    """Parse slots from AJAX partial response XML"""
    slots = []
    # Extract CDATA or HTML content from partial response
    cdata = re.sub(r'<!\[CDATA\[|\]\]>', '', xml)
    # Also unescape HTML entities
    cdata = cdata.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')

    pattern = r'(\d{2}\.\d{2}\.\d{4})\D+(\d{2}:\d{2})\D{0,50}?([A-ZÕÄÖÜ][a-zõäöü]+(?:\s+[A-ZÕÄÖÜ][a-zõäöü]+)*)\s*[»›]'
    for date_str, time_str, city in re.findall(pattern, cdata):
        try:
            slots.append({
                "date": date_str.strip(),
                "time": time_str.strip(),
                "city": city.strip(),
                "datetime": datetime.strptime(date_str.strip(), "%d.%m.%Y"),
            })
        except ValueError:
            continue
    return slots

def parse_slots_from_html(html):
    """Parse slots from regular HTML"""
    slots = []
    pattern = r'<strong>(\d{2}\.\d{2}\.\d{4})</strong>\s*([\d:]+)\s*<strong>([^»]+)»</strong>'
    for date_str, time_str, city in re.findall(pattern, html):
        try:
            slots.append({
                "date": date_str.strip(),
                "time": time_str.strip(),
                "city": city.strip(),
                "datetime": datetime.strptime(date_str.strip(), "%d.%m.%Y"),
            })
        except ValueError:
            continue
    return slots

def filter_slots_before(slots, before_date_str):
    before = datetime.strptime(before_date_str, "%Y-%m-%d")
    return [s for s in slots if s["datetime"] < before]

def send_telegram(token, chat_id, text):
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Checking exam slots...")

    if not SESSION_COOKIE:
        print("ERROR: SESSION_COOKIE not set"); return
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: Telegram config missing"); return

    # Step 1: Load the main page
    html, final_url, status = http_get(PAGE_URL)
    print(f"Page: {final_url} [{status}] ({len(html)} chars)")

    if not html or len(html) < 1000:
        print("Session expired or empty response")
        send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
            "⚠️ <b>Exam monitor</b>: сессия истекла, нужно обновить cookie")
        return

    # Check session validity
    if "juhiloaTaotlus" not in html and "eksamiBroneerimine" not in html and len(html) < 5000:
        print("Not on the right page — session may be expired")
        send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
            "⚠️ <b>Exam monitor</b>: сессия истекла, нужно обновить cookie")
        return

    # Step 2: Check if slots are already in the HTML
    slots = parse_slots_from_html(html)
    print(f"Slots in main HTML: {len(slots)}")

    # Step 3: If no slots yet, try AJAX call to load the popup
    if not slots:
        vs = get_viewstate(html)
        print(f"ViewState found: {'yes' if vs else 'NO'}")

        btn = find_slots_button(html)
        print(f"Slots button: {btn}")

        # Try known button patterns
        candidates = [btn] if btn else []
        # Also try common IDs from JSF pattern
        candidates += ["form:j_idt441", "form:j_idt442", "form:j_idt440"]

        for btn_id in candidates:
            if not btn_id:
                continue
            print(f"Trying button: {btn_id}")
            try:
                post_data = {
                    "javax.faces.partial.ajax": "true",
                    "javax.faces.source": btn_id,
                    "javax.faces.partial.execute": btn_id,
                    "javax.faces.partial.render": "form:ametikoolitus",
                    btn_id: btn_id,
                    "form": "form",
                    "javax.faces.ViewState": vs,
                }
                xml_resp = http_post_ajax(PAGE_URL, post_data, referer=PAGE_URL)
                print(f"AJAX response ({len(xml_resp)} chars): {xml_resp[:300]}")
                ajax_slots = parse_slots_from_xml(xml_resp)
                slots.extend(ajax_slots)
                if ajax_slots:
                    print(f"Found {len(ajax_slots)} slots via AJAX!")
                    break
            except Exception as e:
                print(f"AJAX error for {btn_id}: {e}")

    # Deduplicate
    seen = set()
    unique = []
    for s in slots:
        k = (s["date"], s["time"], s["city"])
        if k not in seen:
            seen.add(k)
            unique.append(s)

    print(f"Total unique slots: {len(unique)}")
    for s in sorted(unique, key=lambda x: x["datetime"])[:5]:
        print(f"  {s['date']} {s['time']} {s['city']}")

    if not unique:
        print("No slots found — will keep monitoring")
        return

    early = filter_slots_before(unique, TARGET_DATE)
    print(f"Slots before {TARGET_DATE}: {len(early)}")

    if early:
        lines = [f"🚗 <b>Свободные места до {TARGET_DATE}!</b>\n"]
        for s in sorted(early, key=lambda x: x["datetime"]):
            lines.append(f"📅 {s['date']} {s['time']} — <b>{s['city']}</b>")
        lines.append(f"\n🔗 {PAGE_URL}")
        result = send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, "\n".join(lines))
        print("✅ Notification sent!" if result.get("ok") else f"Telegram error: {result}")
    else:
        print(f"No slots before {TARGET_DATE} — nothing to notify")

if __name__ == "__main__":
    main()
