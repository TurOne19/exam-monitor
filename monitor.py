#!/usr/bin/env python3
"""
Transpordiamet driving exam slot monitor
"""

import os
import re
import json
import gzip
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TARGET_DATE = os.environ.get("TARGET_DATE", "2026-07-01")
SESSION_COOKIE = os.environ.get("SESSION_COOKIE", "")

BASE_URL = "https://eteenindus.mnt.ee"
MAIN_URL = f"{BASE_URL}/main.jsf"
PAGE_URL = f"{BASE_URL}/pages/juht/juhiloataotlus/juhiloaTaotlus.jsf"

# No Accept-Encoding — get plain text responses
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "et-EE,et;q=0.9,en;q=0.8",
    "Cookie": SESSION_COOKIE,
}

def decode(content, headers):
    enc = headers.get("Content-Encoding", "")
    if enc == "gzip":
        try:
            content = gzip.decompress(content)
        except Exception:
            pass
    return content.decode("utf-8", errors="replace")

def http_get(url):
    req = urllib.request.Request(url, headers={
        **HEADERS, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return decode(resp.read(), resp.headers), resp.geturl()

def http_post(url, data, ajax=False, referer=None):
    payload = urllib.parse.urlencode(data).encode()
    h = {
        **HEADERS,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": referer or url,
        "Origin": BASE_URL,
    }
    if ajax:
        h["Faces-Request"] = "partial/ajax"
        h["X-Requested-With"] = "XMLHttpRequest"
        h["Accept"] = "application/xml, text/xml, */*; q=0.01"
    else:
        h["Accept"] = "text/html,application/xhtml+xml,*/*;q=0.8"
    req = urllib.request.Request(url, data=payload, headers=h)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return decode(resp.read(), resp.headers), resp.geturl()

def get_viewstate(html):
    m = re.search(r'id="javax\.faces\.ViewState"[^>]*value="([^"]+)"', html)
    if not m:
        m = re.search(r'javax\.faces\.ViewState[^>]*value="([^"]+)"', html)
    return m.group(1) if m else ""

def find_nav_to_exam(html):
    """Find form/button on main.jsf that navigates to juhiloaTaotlus"""
    # Look for links or buttons with juhiluba/sõidek/eksam text
    patterns = [
        r'id="([^"]+)"[^>]*>\s*(?:[^<]*(?:Sõiduk|sõiduk|eksam|Juhiluba|juhiluba)[^<]*)',
        r'(?:Sõiduk|eksam|Juhiluba)[^<]{0,200}?id="([^"]+)"',
    ]
    for p in patterns:
        m = re.search(p, html, re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(1)
    return None

def parse_slots(text):
    slots = []
    # Try multiple patterns
    patterns = [
        r'<strong>(\d{2}\.\d{2}\.\d{4})</strong>\s*([\d:]+)\s*<strong>([^»<]+)',
        r'(\d{2}\.\d{2}\.\d{4})\D{1,20}?(\d{2}:\d{2})\D{1,50}?([A-ZÕÄÖÜ][a-zõäöüa-z]+(?:\s+[A-Za-zÕÄÖÜõäöü]+)*)',
    ]
    for pattern in patterns:
        for date_str, time_str, city in re.findall(pattern, text):
            try:
                dt = datetime.strptime(date_str.strip(), "%d.%m.%Y")
                slots.append({
                    "date": date_str.strip(),
                    "time": time_str.strip(),
                    "city": city.strip().rstrip('»').strip(),
                    "datetime": dt,
                })
            except ValueError:
                continue
        if slots:
            break
    return slots

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

def session_expired():
    send_telegram("⚠️ <b>Exam monitor</b>: сессия истекла, нужно обновить cookie")

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Checking exam slots...")

    if not SESSION_COOKIE or not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: missing config"); return

    # Step 1: Try direct page access
    try:
        html, final_url = http_get(PAGE_URL)
        print(f"Direct URL: {final_url} ({len(html)} chars)")
    except Exception as e:
        print(f"Direct fetch error: {e}")
        html, final_url = "", ""

    # If redirected to main.jsf, navigate through menu
    if "main.jsf" in final_url or len(html) < 5000:
        print("Redirected to main.jsf — navigating through menu...")
        try:
            main_html, _ = http_get(MAIN_URL)
            print(f"main.jsf: {len(main_html)} chars")

            # Show links to find exam navigation
            links = re.findall(r'href="([^"]*(?:juht|eksam|juhiluba)[^"]*)"', main_html, re.IGNORECASE)
            print(f"Exam-related hrefs: {links[:5]}")

            # Find any link to juhiloaTaotlus
            if links:
                nav_url = BASE_URL + links[0] if links[0].startswith("/") else links[0]
                print(f"Navigating to: {nav_url}")
                html, final_url = http_get(nav_url)
                print(f"After nav: {final_url} ({len(html)} chars)")
            else:
                # Try to find a POST-based navigation
                vs = get_viewstate(main_html)
                nav_btn = find_nav_to_exam(main_html)
                print(f"Nav button: {nav_btn}, ViewState: {'yes' if vs else 'NO'}")

                if nav_btn and vs:
                    form_m = re.search(r'<form[^>]*id="([^"]+)"[^>]*>.*?' + re.escape(nav_btn), main_html, re.DOTALL)
                    form_id = form_m.group(1) if form_m else "form"
                    post_data = {
                        "javax.faces.partial.ajax": "true",
                        "javax.faces.source": nav_btn,
                        "javax.faces.partial.execute": "@all",
                        "javax.faces.partial.render": "@all",
                        nav_btn: nav_btn,
                        form_id: form_id,
                        "javax.faces.ViewState": vs,
                    }
                    html, _ = http_post(MAIN_URL, post_data, ajax=True, referer=MAIN_URL)
                    print(f"Nav POST response: {len(html)} chars, preview: {html[:200]}")

        except Exception as e:
            print(f"Navigation error: {e}")

    # Check if we have the right page
    if not html or ("juhiloaTaotlus" not in html and "eksamiBroneerimine" not in html):
        # Last check: is it a very short page = login required?
        if len(html) < 3000:
            print("Session expired")
            session_expired()
            return
        print(f"Page content ({len(html)} chars) — checking for slots anyway")

    print("Page loaded, checking for slots...")

    # Step 2: Try to get slots from current HTML
    all_slots = parse_slots(html)
    print(f"Slots in page HTML: {len(all_slots)}")

    # Step 3: Trigger AJAX popup for slots
    if not all_slots:
        vs = get_viewstate(html)
        print(f"ViewState: {'found' if vs else 'NOT FOUND'}")

        # Try the button IDs we know about from the payload screenshot
        # form:j_idt441 was seen in DevTools
        for btn_id in ["form:j_idt441", "form:j_idt442", "form:j_idt440", "form:j_idt443"]:
            print(f"Trying AJAX with {btn_id}...")
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
                resp, _ = http_post(PAGE_URL, post_data, ajax=True, referer=PAGE_URL)
                print(f"  Response ({len(resp)} chars): {resp[:200]}")
                found = parse_slots(resp)
                if found:
                    all_slots.extend(found)
                    print(f"  Found {len(found)} slots!")
                    break
            except Exception as e:
                print(f"  Error: {e}")

    # Deduplicate
    seen = set()
    unique = []
    for s in all_slots:
        k = (s["date"], s["time"], s["city"])
        if k not in seen:
            seen.add(k); unique.append(s)

    print(f"\nTotal unique slots: {len(unique)}")
    for s in sorted(unique, key=lambda x: x["datetime"])[:10]:
        print(f"  {s['date']} {s['time']} — {s['city']}")

    early = filter_before(unique, TARGET_DATE)
    print(f"Slots before {TARGET_DATE}: {len(early)}")

    if early:
        lines = [f"🚗 <b>Свободные места до {TARGET_DATE}!</b>\n"]
        for s in sorted(early, key=lambda x: x["datetime"]):
            lines.append(f"📅 {s['date']} {s['time']} — <b>{s['city']}</b>")
        lines.append(f"\n🔗 {PAGE_URL}")
        result = send_telegram("\n".join(lines))
        print("✅ Sent!" if result.get("ok") else f"Error: {result}")
    else:
        print("No early slots — keep monitoring")

if __name__ == "__main__":
    main()
