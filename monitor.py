cat > /mnt/user-data/outputs/monitor.py << 'EOF'
#!/usr/bin/env python3
"""DEBUG VERSION — finds the correct form/button for slot loading"""

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

MAIN_URL = "https://eteenindus.mnt.ee/pages/juht/juhiloataotlus/juhiloaTaotlus.jsf"
EXAM_URL = "https://eteenindus.mnt.ee/pages/juht/juhiloataotlus/eksamiBroneerimine.jsf"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "et-EE,et;q=0.9,en;q=0.8",
}

def get(url):
    req = urllib.request.Request(url, headers={**HEADERS, "Cookie": SESSION_COOKIE})
    opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
    with opener.open(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace"), resp.geturl()

def post(url, data, extra_headers={}):
    payload = urllib.parse.urlencode(data).encode()
    headers = {**HEADERS, "Cookie": SESSION_COOKIE,
               "Content-Type": "application/x-www-form-urlencoded", **extra_headers}
    req = urllib.request.Request(url, data=payload, headers=headers)
    opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
    with opener.open(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")

def send_telegram(token, chat_id, text):
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Checking exam slots...")

    html, final_url = get(MAIN_URL)
    print(f"Main page: {final_url} ({len(html)} chars)")

    # Find ALL ViewState values with their surrounding form context
    vs_matches = list(re.finditer(
        r'<form[^>]*id="([^"]*)"[^>]*>.*?javax\.faces\.ViewState["\s]*[^"]*value="([^"]*)"',
        html, re.DOTALL))
    print(f"\n=== ALL FORMS WITH VIEWSTATE ({len(vs_matches)}) ===")
    for m in vs_matches:
        print(f"  Form '{m.group(1)}': ViewState = {m.group(2)[:60]}")

    # Also find ViewState without form context
    all_vs = re.findall(r'javax\.faces\.ViewState[^>]*value="([^"]+)"', html)
    print(f"\n=== ALL VIEWSTATE VALUES ({len(all_vs)}) ===")
    for i, vs in enumerate(all_vs):
        print(f"  [{i}]: {vs[:80]}")

    # Find all forms
    forms = re.findall(r'<form[^>]*id="([^"]*)"[^>]*action="([^"]*)"', html)
    print(f"\n=== ALL FORMS ({len(forms)}) ===")
    for form_id, action in forms:
        print(f"  id='{form_id}' action='{action}'")

    # Show 800 chars around the varaseimad container
    idx = html.find("eksamiBroneerimineVaraseimadAjadContainer")
    if idx >= 0:
        start = max(0, idx - 400)
        end = min(len(html), idx + 400)
        print(f"\n=== CONTEXT AROUND VARASEIMAD CONTAINER ===")
        print(html[start:end])

    # Find anything with 'vabad' or 'varaseimad' in onclick/id
    triggers = re.findall(r'<[^>]*(vabad|varaseimad|kiireim)[^>]*>', html, re.IGNORECASE)
    print(f"\n=== TRIGGERS (vabad/varaseimad/kiireim) ({len(triggers)}) ===")
    for t in triggers[:10]:
        print(f"  {t[:200]}")

    # Try POST to eksamiBroneerimine.jsf directly (like browser does)
    # First get its ViewState
    exam_html, _ = get(EXAM_URL)
    print(f"\neksamiBroneerimine.jsf: {len(exam_html)} chars")
    print(f"Preview: {exam_html[:600]}")

    exam_vs = re.findall(r'javax\.faces\.ViewState[^>]*value="([^"]+)"', exam_html)
    exam_forms = re.findall(r'<form[^>]*id="([^"]*)"', exam_html)
    print(f"Exam ViewStates: {exam_vs}")
    print(f"Exam Forms: {exam_forms}")

if __name__ == "__main__":
    main()
