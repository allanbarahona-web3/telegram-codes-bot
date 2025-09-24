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
	# Diccionario de textos traducidos
	return {
		"your_points": {"es": "Tus puntos", "en": "Your points"},
		"balance_header": {"es": "💰 Tu balance:", "en": "💰 Your balance:"},
		"balance_body": {
			"es": (
				"Referidos aprobados: {approved}\n"
				"Comisión por referido: {commission}\n"
				"Bruto ganado: {gross}\n"
				"Pagado: {paid}\n"
				"Retiros pendientes: {pending}\n"
				"\nDisponible ahora: {available}"
			),
			"en": (
				"Approved referrals: {approved}\n"
				"Commission per referral: {commission}\n"
				"Gross earned: {gross}\n"
				"Paid out: {paid}\n"
				"Pending withdrawals: {pending}\n"
				"\nAvailable now: {available}"
			)
		},
		   "withdraw_created": {
			   "es": "✅ Su retiro se está procesando. Le contactaremos pronto.",
			   "en": "✅ Your withdrawal is being processed. We will contact you soon."
		   },
		   "confirm_account": {
			   "es": "¿Confirmas que este es tu dato de {method}: {account}?",
			   "en": "Do you confirm this {method} account: {account}?"
		   },
		"mycode_has": {"es": "Tu código de referido es:", "en": "Your referral code is:"},
		"mycode_missing": {"es": "No tienes código asignado.", "en": "You have no code assigned."},
		"start_mobile_only": {"es": "¡Bienvenido! Usa los comandos para interactuar con el bot.", "en": "Welcome! Use the commands to interact with the bot."},
		"group_access": {"es": "Acceso al grupo: {link}", "en": "Group access: {link}"},
		"your_affiliate_link": {"es": "Tu link de referido: {link}", "en": "Your affiliate link: {link}"},
		"help": {"es": "Comandos disponibles:\n/mypoints - Ver tus puntos\n/balance - Ver tu balance\n/withdraw - Retirar\n/mycode - Ver tu código\n/mylink - Ver tu link de referido\n/group - Acceso al grupo", "en": "Available commands:\n/mypoints - See your points\n/balance - See your balance\n/withdraw - Withdraw\n/mycode - See your code\n/mylink - See your affiliate link\n/group - Group access"}
	}

def t(key, lang, **kwargs):
	texts = get_texts()
	value = texts.get(key, {}).get(lang, key)
	if kwargs:
		try:
			return value.format(**kwargs)
		except Exception as e:
			missing = ', '.join([k for k in value.split('{')[1:] if '}' in k and k.split('}')[0] not in kwargs])
			return f"[ERROR: Missing params: {missing}] {value}"
	return value

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
