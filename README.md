# Telegram Codes Bot

A Telegram bot that assigns each user a unique referral code based on their verified phone number.  
It supports referral campaigns, provides invite links to groups that are one-time use and expire automatically, and includes **CSV export** for admins.

---

## ✨ Features
- **Unique user codes:** each user receives a random, unique code with a country prefix (e.g., `CR-AB12-CD34`).
- **Phone verification:** users must share their phone number via Telegram’s native contact button.
- **Code recovery:** retrieve your code anytime with `/mycode` or the inline button 🔑 *Remember my code*.
- **Referral campaigns:** track inviter/invitee relationships in the database.
- **Group access control:** invite links are single-use and expire after a defined TTL.
- **CSV Export (admin only):** `/exportcsv` generates three CSVs in the `exports/` folder (`users-<ts>.csv`, `referrals-<ts>.csv`, `campaigns-<ts>.csv`).

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

Create a .env file in the root folder with:

TELEGRAM_BOT_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxx
DEFAULT_REGION=UNKN
GROUP_CHAT_ID=-1001234567890
INVITE_TTL_HOURS=12
ADMIN_USER_IDS=123456789


TELEGRAM_BOT_TOKEN: your bot token from BotFather

DEFAULT_REGION: fallback prefix if number has no country code

GROUP_CHAT_ID: target group’s chat_id (bot must be admin)

INVITE_TTL_HOURS: invite link lifetime (hours)

ADMIN_USER_IDS: comma-separated Telegram IDs with admin rights

▶️ Running the bot
python telegram_referrals_bot.py

🗃️ Database schema

users

user_id, phone, code, assigned_at, country_code


referrals

referrer_user_id, referee_user_id


campaigns

id, name, rules...

📊 Analytics

Codes include country prefix (CR, MX, US) or UNKN.

users table stores country_code for reporting.

referrals table enables queries for referral counts.

CSV export = quick reporting + migration bridge to SaaS.

📄 License

MIT

🧪 QA Freeze / Version

Current QA Freeze: v0.1.0 (QA – do not modify)

Tester: Karen (Qase, device testing)

Scope: referrals core, balance/payouts, admin, ES/EN

Run locally for QA:

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python telegram_referrals_bot.py


Environment variables:

TELEGRAM_BOT_TOKEN (required)

DATABASE_URL (optional, default: local codes.db)

DEFAULT_LOCALE (es|en)
