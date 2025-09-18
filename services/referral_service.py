from services.db_service import (
	find_user_by_code,
	referee_already_referred,
	is_reciprocal_referral,
	insert_referral,
	upsert_user,
	add_points,
)

async def register_referral(
	campaign_id: str,
	referee_id: int,
	ref_code: str,
	group_chat_id: str,
	points_per_referral: int,
	bot,
	get_lang,
	t,
	message,
):
	lang = get_lang(message.from_user)
	code = (
		ref_code.strip().upper()
		.replace(" ", "")
		.replace("_", "")
		.replace("—", "-")
		.replace("–", "-")
	)
	referrer_id = await find_user_by_code(code)
	if not referrer_id:
		await message.answer(t("invalid_referral", lang)); return
	if referrer_id == referee_id:
		await message.answer(t("self_referral", lang)); return
	if await referee_already_referred(campaign_id, referee_id):
		await message.answer(t("already_referred", lang)); return
	if await is_reciprocal_referral(campaign_id, referee_id, referrer_id):
		await message.answer(t("reciprocal_blocked", lang)); return
	# Check if referee is in the group before awarding points
	is_member = False
	if group_chat_id:
		try:
			member = await bot.get_chat_member(group_chat_id, referee_id)
			is_member = getattr(member, "status", None) in ("member", "administrator", "creator")
		except Exception:
			pass
	if is_member:
		try:
			await insert_referral(campaign_id, referrer_id, referee_id, code)
			points = points_per_referral
			await upsert_user(referee_id)
			await upsert_user(referrer_id)
			await add_points(referee_id, points, reason="joined_group")
			await add_points(referrer_id, points, reason="referral_success")
		except Exception as e:
			await message.answer(t("already_referred", lang) + f"\nError: {e}"); return
		await message.answer(t("referral_done", lang))
		await message.answer(
			"⚠️ If you leave the main group, you will lose your points!\n¡Si sales del grupo principal, perderás tus puntos!"
		)
	else:
		await message.answer(
			"❗️You must join the main group to receive your points.\nDebes unirte al grupo principal para recibir tus puntos."
		)
from services.db_service import (
	get_existing_code_by_user,
	get_code_by_phone,
	upsert_user,
)
from utils.helpers import build_random_code

# Assign or get a unique referral code for a user
async def assign_or_get_code(user_id: int, phone_e164: str, prefix_override: str, country_code: str) -> str | None:
	existing = await get_existing_code_by_user(user_id)
	if existing:
		return existing

	phone_owner = await get_code_by_phone(phone_e164)
	if phone_owner:
		_, code = phone_owner
		return code

	for _ in range(5):
		code = build_random_code(prefix=prefix_override or "RF", length=8)
		try:
			await upsert_user(user_id, code, phone_e164)
			return code
		except Exception as e:
			msg = str(e).lower()
			if "unique" in msg and "code" in msg:
				continue
			if "unique" in msg and "phone" in msg:
				row = await get_code_by_phone(phone_e164)
				if row:
					_, existing_code = row
					return existing_code
			raise
	return None
# This module will contain business logic and service-layer functions for the SaaS bot.
# Use this to coordinate between DB, bot, and other integrations.
