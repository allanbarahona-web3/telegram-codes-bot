Telegram Codes Bot
A Telegram bot that assigns a **unique code** with the format:
MONTH_ABBR + PHONE + YEAR
Example:
If today is September 2025 and the phone is `88888888`,
the code will be:
SEP888888882025
Features
- Users can only share their own phone number via Telegram’s **Share my phone** button.
- Code is generated **once** and is always the same for that user (stored in SQLite).
- Recovery with `/mycode` command or by pressing the **n Remember my code** button.
- Safe: phone numbers cannot be replaced or reassigned.
Requirements
- Python 3.10+
- pip (Python package manager)
- (Optional) virtualenv
Installation
1. Clone this repository
```bash
git clone https://github.com//telegram-codes-bot.git
cd telegram-codes-bot
```
2. Create virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate
```
3. Install dependencies
```bash
pip install aiogram==3.4 aiosqlite python-dotenv
```
4. Set your bot token in .env
```bash
echo 'BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN' > .env
```
5. Run the bot
```bash
python hello.py
```
Commands
- `/start` ® share your phone number and get your unique code.
- `/mycode` ® retrieve your assigned code.
- **n Remember my code** ® inline button to retrieve the code.
Security
- Phone numbers come only from Telegram (not typed manually).
- Codes are stored in SQLite and are persistent.
- A phone number cannot be reassigned to another user.
License
MIT License
