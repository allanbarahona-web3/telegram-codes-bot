# Telegram Codes Bot

A Telegram bot that assigns each user a unique referral code based on their verified phone number.  
It also supports referral campaigns, provides invite links to groups that are one-time use and expire automatically, and now includes **CSV export** for admins.

---

## ✨ Features
- **Unique user codes:** each user receives a random, unique code with a country prefix (e.g., `CR-AB12-CD34`).
- **Phone verification:** users must share their phone number via Telegram’s native contact button (no manual typing).
- **Code recovery:** retrieve your code anytime with `/mycode` or the inline button 🔑 *Remember my code*.
- **Referral campaigns:**
  - Users share their codes with friends.
  - New users enter the code of the inviter.
  - The bot stores relationships in the database (`referrals` table).
- **Group access control:**
  - Only users who verify their phone and get a code can receive a group invite.
  - Invite links are single-use and expire automatically after a set number of hours.
- **CSV Export (admin only):**
  - `/exportcsv` generates three CSV files in the `exports/` folder:
    - `users-<timestamp>.csv`
    - `referrals-<timestamp>.csv`
    - `campaigns-<timestamp>.csv`

---

## ⚙️ Requirements
- Python 3.10+
- pip
- virtualenv (optional)

---

## 🔧 Installation
```bash
git clone https://github.com/<your-username>/telegram-codes-bot.git
cd telegram-codes-bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
🔑 Configuration
Create a .env file in the root folder with the following variables:

env
Copiar código
BOT_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxx
DEFAULT_REGION=UNKN
GROUP_CHAT_ID=-1001234567890
INVITE_TTL_HOURS=12
ADMIN_USER_IDS=123456789
BOT_TOKEN → your bot token from BotFather.

DEFAULT_REGION → fallback country prefix if a phone number does not include +code.

GROUP_CHAT_ID → the target group’s chat_id (starts with -100…) where the bot is admin.

INVITE_TTL_HOURS → how many hours the group invite link remains valid.

ADMIN_USER_IDS → comma-separated list of Telegram user IDs with admin permissions (e.g., /exportcsv).

▶️ Running the bot
bash
Copiar código
python hello.py
🗃️ Database schema
users table

user_id, phone, code, assigned_at, country_code

referrals table

Tracks referral relationships between inviter (referrer_user_id) and invited (referee_user_id).

campaigns table

Supports multiple referral campaigns with different reward rules.

📊 Analytics
Codes include the country prefix (CR, MX, US) or UNKN if not detected.

The users table stores country_code, useful for country-based reporting.

The referrals table enables queries to count how many referrals each user has.

CSV export provides quick reporting and is the bridge for future migration to SaaS.

📄 License
MIT

---

## QA Freeze / Version
- **Current QA Freeze:** `v0.1.0` (QA – do not modify)
- Tester: Karen (Qase, device testing)
- Scope: referrals core, balance/payouts, admin, ES/EN.

## Run locally (dev)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python telegram_referrals_bot.py

Environment

TELEGRAM_BOT_TOKEN (required)

DATABASE_URL (optional, default: local codes.db)

DEFAULT_LOCALE (es|en)
