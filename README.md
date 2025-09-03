Telegram Codes Bot
A Telegram bot that assigns each user a **unique referral code** based on their verified phone number.
It also supports **referral campaigns** and provides **invite links to groups** that are one-time use and
expire automatically.
n Features
- **Unique user codes**: each user receives a random, unique code with a country prefix (e.g.,
`CR-AB12-CD34`).
- **Phone verification**: users must share their phone number via Telegram’s native contact button (no
manual typing).
- **Code recovery**: retrieve your code anytime with `/mycode` or the inline button **n Remember my
code**.
- **Referral campaigns**:
- Users share their codes with friends.
- New users enter the code of the inviter.
- The bot stores relationships in the database (`referrals` table).
- **Group access control**:
- Only users who verify their phone and get a code can receive a group invite.
- Invite links are **single-use** and **expire automatically** after a set number of hours.
nn Requirements
- Python 3.10+
- pip
- virtualenv (optional)
n Installation
git clone https://github.com//telegram-codes-bot.git
cd telegram-codes-bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
n Configuration
Create a `.env` file in the root folder with the following variables:
BOT_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxx
DEFAULT_REGION=UNKN
GROUP_CHAT_ID=-1001234567890
INVITE_TTL_HOURS=12
- **BOT_TOKEN** ® your bot token from BotFather.
- **DEFAULT_REGION** ® fallback country prefix if a phone number does not include `+code`.
- **GROUP_CHAT_ID** ® the target group’s chat_id (starts with `-100…`) where the bot is admin.
- **INVITE_TTL_HOURS** ® how many hours the group invite link remains valid.
nn Running the bot
python hello.py
nn Database schema
- `users` table:
- `user_id`, `phone`, `code`, `assigned_at`, `country_code`.
- `referrals` table:
- Tracks referral relationships between inviter (referrer) and invited (referee).
- `campaigns` table:
- Allows multiple referral campaigns with different reward rules.
n Analytics
- Codes include the **country prefix** (`CR`, `MX`, `US`) or `UNKN` if not detected.
- The `users` table stores `country_code`, useful for country-based reporting.
- The `referrals` table enables queries to count how many referrals each user has.
n License
MIT

