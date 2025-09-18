from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import (
	Message, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove,
	InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ForceReply
)
from services.db_service import (
	get_existing_code_by_user,
	upsert_user,
	get_user_points,
	compute_balances,
	create_withdraw_request,
)
from services.referral_service import assign_or_get_code, register_referral
from utils.helpers import e164, country_code_from_phone, get_lang
import logging
import re

# UI Helper Functions
def build_affiliate_link_for_code(code: str, bot_username: str) -> str:
	return f"https://t.me/{bot_username}?start={code}"

def share_phone_kb(lang: str, texts):
	return ReplyKeyboardMarkup(
		keyboard=[[KeyboardButton(text=texts["share_phone_button"][lang], request_contact=True)]],
		resize_keyboard=True,
		one_time_keyboard=True
	)

def remember_kb(lang: str, texts):
	return InlineKeyboardMarkup(
		inline_keyboard=[
			[InlineKeyboardButton(text=texts["remember_button"][lang], callback_data="remember_code")],
			[InlineKeyboardButton(text=texts["affiliate_link_button"][lang], callback_data="get_affiliate_link")],
			[InlineKeyboardButton(text=texts["group_link_button"][lang], callback_data="get_group_link")]
		]
	)

def referral_button(lang: str, texts):
	return InlineKeyboardMarkup(
		inline_keyboard=[[InlineKeyboardButton(text=texts["referral_button"][lang], callback_data="enter_referral")]]
	)

def group_link_button(lang: str, texts):
	return InlineKeyboardMarkup(
		inline_keyboard=[[InlineKeyboardButton(text=texts["group_link_button"][lang], callback_data="get_group_link")]]
	)

def payout_methods_kb(lang: str):
	return InlineKeyboardMarkup(
		inline_keyboard=[
			[InlineKeyboardButton(text="PayPal 💵", callback_data="pm:Paypal")],
			[InlineKeyboardButton(text="Binance Pay ID 🚀", callback_data="pm:BinancePay")],
			[InlineKeyboardButton(text="USDT (TRC20) 🪙", callback_data="pm:USDT_TRC20")],
			[InlineKeyboardButton(text="SINPE Móvil 🇨🇷", callback_data="pm:SINPE")],
		]
	)

# Example handler (others should be moved similarly)
def register_handlers(dp: Dispatcher, config, texts, t):
	BOT_USERNAME = config["BOT_USERNAME"]

	@dp.message(CommandStart())
	async def on_start(message: Message):
		lang = get_lang(message.from_user)
		referrer_code = None
		if message.text and message.text.startswith("/start"):
			parts = message.text.split()
			if len(parts) == 2:
				referrer_code = parts[1].strip()
		# ...existing code for campaign, group_chat_id, etc...
		# Use UI helpers from this module
		# ...existing code...
		pass

	# ...move other handlers here...
# This module will contain all Telegram bot handlers and UI logic.
# Move aiogram handlers and UI helpers from telegram_referrals_bot.py here.
