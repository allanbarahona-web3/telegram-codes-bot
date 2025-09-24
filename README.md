# Telegram Codes Bot

A production-ready Telegram referral bot for campaigns, with unique codes, group access control, multi-method withdrawals, and robust admin features.

---

## ✨ Main Features

- **Unique user codes:** Automatic generation with country prefix (e.g., `CR-AB12-CD34`).
- **Referral campaigns:** Track invitations and points per campaign.
- **Group access control:** One-time, expiring invite links.
- **Withdrawals and balance:** Request withdrawals, view history, and balance validations.
- **Multi-method payouts:** PayPal and Binance Pay supported, with exact account/ID recorded per withdrawal.
- **CSV export (admin):** `/exportcsv` for users, referrals, and campaigns.
- **Multilanguage support:** English and Spanish.
- **Flexible configuration:** Environment variables for region, currency, commissions, etc.

---

## ⚙️ Requirements

- Python 3.10+
- pip
- PostgreSQL (recommended for production)
- virtualenv (optional)

---

## 🚀 Installation & Configuration

```bash
git clone https://github.com/<your-username>/telegram-codes-bot.git
cd telegram-codes-bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the root folder with:

```
TELEGRAM_BOT_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxx
DEFAULT_REGION=UNKN
GROUP_CHAT_ID=-1001265465465412321654
INVITE_TTL_HOURS=12
ADMIN_USER_IDS=123456789
DATABASE_URL=postgresql+psycopg://user:pass@host:port/dbname
CURRENCY=USD
COMMISSION_PER_APPROVED_CENTS=100
MIN_WITHDRAW_CENTS=2500
```

---

## ▶️ Running the Bot

```bash
python main.py
```

---

## 🗂️ Database Schema

- **users:** id, phone, code, email, total_points, created_at, country_code
- **referrals:** campaign_id, referrer_id, referee_id, ref_code, created_at, status
- **campaigns:** id, client_id, name, status, created_at
- **points_history:** id, user_id, campaign_id, points, reason, created_at
- **payments:** id, user_id, amount_cents, status, method_id, requested_at, paid_at, processed_at, note, account
- **payout_methods:** id, user_id, method_type, details, is_default

---

## 💸 Withdrawals & Payouts

- Users can request withdrawals via `/withdraw` or `/cobrar`.
- Supported payout methods: **PayPal** and **Binance Pay**.
- Each withdrawal records the exact PayPal email or Binance Pay ID used at the time of request.
- Admins can approve and mark withdrawals as paid.
- Full audit trail: see to which account/ID each payment was sent.

---

## 📊 Analytics & Export

- Codes include country prefix (CR, MX, US, UNKN).
- CSV export for users, referrals, and campaigns.
- Balance and referral queries per campaign.

---

## 🧪 Testing & QA

- Automated test coverage for business logic, edge cases, concurrency, security, and resource limits.
- See details and checklist in CHANGELOG.md.

---

## 📝 Notes

- Do not include sensitive data or QA/production environment references in this file.
- For deployment, review environment variables and database configuration.

---

## License

MIT

---

## Version

Current QA Freeze: qa-20250923-1

---
