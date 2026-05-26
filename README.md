# Transpordiamet Exam Monitor

Sends Telegram notifications when driving exam slots appear before your target date.

## Setup

### 1. Fork / create this repo on GitHub

### 2. Add these GitHub Secrets (Settings → Secrets → Actions):

| Secret | Value |
|--------|-------|
| `TELEGRAM_TOKEN` | Your bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Your chat ID (e.g. 8146157246) |
| `SESSION_COOKIE` | JSESSIONID value from browser (see below) |
| `TARGET_DATE` | e.g. `2026-07-01` |

### 3. How to get SESSION_COOKIE

1. Login to eteenindus.mnt.ee
2. Open F12 → Application → Cookies → eteenindus.mnt.ee
3. Copy the value of `JSESSIONID`
4. Paste it as the SESSION_COOKIE secret

> ⚠️ Session lasts ~4 hours. You need to refresh it manually.
> The bot will notify you when the session expires.

### 4. Enable GitHub Actions

Go to Actions tab in your repo and enable workflows.
The script runs every 10 minutes automatically (free).
