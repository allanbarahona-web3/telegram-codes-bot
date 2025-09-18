import re
import secrets
import phonenumbers
from datetime import datetime, timedelta, timezone
from typing import Optional

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # excluding 0/O/1/I for readability

def build_random_code(prefix: str = "RF", length: int = 8) -> str:
	"""Readable random referral code without PII. Format: RF-XXXX-XXXX"""
	body = "".join(secrets.choice(ALPHABET) for _ in range(length))
	return f"{prefix}-{body[:4]}-{body[4:]}"

def utcnow_iso() -> str:
	return datetime.now(timezone.utc).isoformat()

def e164(phone_raw: str, default_region: str = "CR") -> Optional[str]:
	try:
		raw = (phone_raw or "").strip()
		parsed = phonenumbers.parse(raw, None if raw.startswith("+") else default_region)
		if phonenumbers.is_valid_number(parsed):
			return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
		if phonenumbers.is_possible_number(parsed):
			return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
		digits_only = re.sub(r"[^0-9]", "", raw)
		candidate = "+" + digits_only if not raw.startswith("+") else "+" + digits_only
		if 8 <= len(digits_only) <= 15:
			return candidate
		return None
	except Exception:
		digits_only = re.sub(r"[^0-9]", "", phone_raw or "")
		candidate = "+" + digits_only if digits_only else None
		if candidate and 8 <= len(digits_only) <= 15:
			return candidate
		return None

def country_code_from_phone(phone_e164: str) -> Optional[str]:
	try:
		num = phonenumbers.parse(phone_e164, None)
		return phonenumbers.region_code_for_number(num)
	except Exception:
		return None

def get_lang(user) -> str:
	code = (getattr(user, 'language_code', None) or "en").lower()
	return "es" if code.startswith("es") else "en"
# This module will contain utility functions (validation, formatting, etc) for the SaaS bot.
# Move reusable helpers from telegram_referrals_bot.py here.
