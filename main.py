# SaaS-ready main entrypoint for Telegram Codes Bot
import os
from dotenv import load_dotenv
# Carga dotenv ANTES de cualquier otro import
load_dotenv(".env")
load_dotenv(".env.dev", override=True)
print("DEBUG: DATABASE_URL=", os.getenv("DATABASE_URL"))

import logging
from aiogram import Bot, Dispatcher
from bot.handlers import register_handlers

def load_config():
	return {
		"BOT_TOKEN": os.getenv("BOT_TOKEN"),
		"BOT_USERNAME": os.getenv("BOT_USERNAME", "BarmentechDEVbot"),
		"ADMIN_USER_IDS": [x.strip() for x in os.getenv("ADMIN_USER_IDS", "").split(",") if x.strip()],
		"DEFAULT_REGION": os.getenv("DEFAULT_REGION", "CR"),
		"GROUP_CHAT_ID": os.getenv("GROUP_CHAT_ID"),
		"INVITE_TTL_HOURS": int(os.getenv("INVITE_TTL_HOURS", "12")),
		"COMMISSION_PER_APPROVED_CENTS": int(os.getenv("COMMISSION_PER_APPROVED_CENTS", "100")),
		"CURRENCY": os.getenv("CURRENCY", "USD"),
		"POINTS_PER_REFERRAL": int(os.getenv("POINTS_PER_REFERRAL", "1")),
		"MIN_WITHDRAW_CENTS": int(os.getenv("MIN_WITHDRAW_CENTS", "2500")),
		"PAYPAL_PERCENT_FEE": float(os.getenv("PAYPAL_PERCENT_FEE", "5.2")),
		"PAYPAL_FIXED_FEE": float(os.getenv("PAYPAL_FIXED_FEE", "0.30")),
	}

def get_texts():
	# Import or define your TEXTS dict here, or load from a file
	return {}

def t(key, lang, **kwargs):
	# Dummy translation function; replace with your real one
	return key

async def main():
	from services.db_service import open_pool
	await open_pool()
	config = load_config()
	logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
	bot = Bot(token=config["BOT_TOKEN"])
	dp = Dispatcher()
	texts = get_texts()
	register_handlers(dp, config, texts, t)
	print("Bot is starting...")
	await dp.start_polling(bot)

if __name__ == "__main__":
	import asyncio
	asyncio.run(main())
# This file will serve as the main entrypoint for the SaaS app.
# It can launch the bot, API, or both, depending on configuration.
