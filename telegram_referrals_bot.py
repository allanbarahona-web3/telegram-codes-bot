# -*- coding: utf-8 -*-

# 1) Cargar envs (QA/Prod y luego DEV si existe)
from dotenv import load_dotenv
load_dotenv(".env")                     # QA/Prod
load_dotenv(".env.dev", override=True)  # DEV (si existe)

# 2) Imports estándar
import os
import re
import json
import asyncio
import secrets
from typing import Optional, Tuple, List
from datetime import datetime as dt
import logging
import sqlite3  # solo for error annotation (sqlite3.Row)
from datetime import datetime, timedelta

# 3) Aiogram
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ForceReply
)

# 4) Terceros
import phonenumbers  # phone number normalization

# 5) Capa de datos (dual: sqlite/postgres)
from db_repo import (
    init_db,
    upsert_user,
    get_existing_code_by_user,
    find_user_by_code,
    referee_already_referred,
    is_reciprocal_referral,
    insert_referral,
    get_user_points,
    compute_balances,
    get_code_by_phone,
    DB_BACKEND,
)

# 6) Logging básico + confirma backend
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.info(f"DB_BACKEND={DB_BACKEND}  DATABASE_URL={'set' if os.getenv('DATABASE_URL') else 'unset'}")




# ================== Config ==================
load_dotenv(".env.dev")

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = os.getenv("DB_PATH", "codes.db")
ADMIN_USER_IDS = [x.strip() for x in os.getenv("ADMIN_USER_IDS", "").split(",") if x.strip()]

DEFAULT_REGION = os.getenv("DEFAULT_REGION", "CR")   # fallback region for parsing phone numbers
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")           # group chat id (e.g., -1001234567890)
INVITE_TTL_HOURS = int(os.getenv("INVITE_TTL_HOURS", "12"))  # invite link validity in hours

# Earnings config
COMMISSION_PER_APPROVED_CENTS = int(os.getenv("COMMISSION_PER_APPROVED_CENTS", "100"))
CURRENCY = os.getenv("CURRENCY", "USD")
BOT_USERNAME = os.getenv("BOT_USERNAME", "BarmentechDEVbot")  # Bot username for DeepLink

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not configured (.env)")

# Aiogram dispatcher
dp = Dispatcher()
ACTIVE_CAMPAIGN_ID = 1

# ================== Utilities ==================

# Helper: Get ISO country code from E.164 phone number
def country_code_from_phone(phone_e164: str) -> str | None:
    try:
        num = phonenumbers.parse(phone_e164, None)
        return phonenumbers.region_code_for_number(num)
    except Exception:
        return None

# Helper to create one-time invite links with expiration
async def create_one_time_invite(bot: Bot, chat_id: str, user_id: int, ttl_hours: int = 12) -> Optional[str]:
    """
    Requires the bot to be admin of the group with invite link creation permissions.
    """
    try:
        expires_at = int((datetime.utcnow() + timedelta(hours=ttl_hours)).timestamp())
        link = await bot.create_chat_invite_link(
            chat_id=chat_id,
            name=f"one-use-{user_id}",
            expire_date=expires_at,
            member_limit=1
        )
        return link.invite_link
    except Exception as e:
        logging.error(f"Failed to create invite link: {e}")
        return None


ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # excluding 0/O/1/I for readability


def build_random_code(prefix: str = "RF", length: int = 8) -> str:
    """Readable random referral code without PII. Format: RF-XXXX-XXXX"""
    body = "".join(secrets.choice(ALPHABET) for _ in range(length))
    return f"{prefix}-{body[:4]}-{body[4:]}"


def utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# Normalize phone number to E.164 and extract country

def e164(phone_raw: str, default_region: str = DEFAULT_REGION) -> Optional[str]:
    try:
        raw = (phone_raw or "").strip()
        # Si empieza con +, no usamos región; si no, usamos DEFAULT_REGION (CR/ZZ)
        parsed = phonenumbers.parse(raw, None if raw.startswith("+") else default_region)

        # 1) Validación estricta
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

        # 2) Fallback: números "posibles" (a veces metadatos de carrier faltan)
        if phonenumbers.is_possible_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

        # 3) Último recurso: conservar + y dígitos (longitud razonable)
        digits_only = re.sub(r"[^0-9]", "", raw)
        candidate = "+" + digits_only if not raw.startswith("+") else "+" + digits_only
        if 8 <= len(digits_only) <= 15:
            return candidate
        return None
    except Exception:
        # Último recurso si parsea mal: sanitizar agresivo
        digits_only = re.sub(r"[^0-9]", "", phone_raw or "")
        candidate = "+" + digits_only if digits_only else None
        if candidate and 8 <= len(digits_only) <= 15:
            return candidate
        return None



    """
    Returns 'es' if the user's Telegram app language is Spanish, otherwise 'en'.
    """
    code = (user.language_code or "en").lower()
    return "es" if code.startswith("es") else "en"


TEXTS = {
    "your_affiliate_link": {
        "en": "🔗 Your affiliate link: {link}",
        "es": "🔗 Tu link de afiliado: {link}"
    },
    "affiliate_link_button": {
        "en": "🔗 Get my affiliate link",
        "es": "🔗 Obtener mi link de afiliado"
    },
    "already_has_code": {
        "en": "You already have a code assigned. Tap the button to see it or enter a referral code:",
        "es": "Ya tienes un código asignado. Toca el botón para verlo o ingresa un código de referido:"
    },
    "start": {
        "en": "Hello 👋\nTo get your unique code, tap the button and share your phone number.",
        "es": "Hola 👋\nPara obtener tu código único, toca el botón y comparte tu número de teléfono."
    },
    "start_mobile_only": {
        "en": "To continue, tap *📱 Share phone* from your mobile Telegram app.",
        "es": "Para continuar, toca *📱 Compartir teléfono* desde tu app móvil de Telegram."
    },
    "share_own_number_mobile": {
        "en": "You must share *your* number from the mobile Telegram app using the button.",
        "es": "Debes compartir *tu* número desde la app móvil de Telegram usando el botón."
    },
    "optional_enter_code": {
        "en": "Optional: if someone invited you, enter their code below 👇",
        "es": "Opcional: si alguien te invitó, ingresa su código aquí 👇"
    },
    "group_ready": {
        "en": "Ready to join the group?",
        "es": "¿Listo para entrar al grupo?"
    },
    "share_own_number": {
        "en": "⚠️ Please tap **Share my phone number**. Do not send an address-book contact.",
        "es": "⚠️ Toca **Compartir mi número de teléfono**. No envíes un contacto de tu agenda."
    },
    "invalid_number": {
        "en": "⚠️ Invalid number. Tap the button again and share your phone.",
        "es": "⚠️ Número inválido. Toca el botón de nuevo y comparte tu teléfono."
    },
    "phone_verified": {
        "en": "✅ Phone verified.\n🌎 Country detected: {region}\n🔑 Your unique code: {code}",
        "es": "✅ Teléfono verificado.\n🌎 País detectado: {region}\n🔑 Tu código único: {code}"
    },
    "remember_offer": {
        "en": "Do you want to remember it quickly later?",
        "es": "¿Quieres recordarlo rápidamente más tarde?"
    },
    "enter_inviter_code": {
        "en": "If you were invited, enter your inviter's code:",
        "es": "Si te invitaron, ingresa el código de quien te refirió:"
    },
    "group_access": {
        "en": "🟢 Group access (expires in {hours}h, 1 use):\n{link}",
        "es": "🟢 Acceso al grupo (vence en {hours}h, 1 uso):\n{link}"
    },
    "group_invite_fail": {
        "en": "ℹ️ Could not create an invite link. Check that the bot is **admin** of the group and `GROUP_CHAT_ID` is correct.",
        "es": "ℹ️ No pude crear un enlace de invitación. Verifica que el bot sea **admin** del grupo y que `GROUP_CHAT_ID` sea correcto."
    },
    "mycode_has": {
        "en": "🔑 Your code is: {code}",
        "es": "🔑 Tu código es: {code}"
    },
    "remember_button": {
        "en": "🔑 Remember my code",
        "es": "🔑 Recordar mi código"
    },
    "referral_button": {
        "en": "🎁 Enter referral code",
        "es": "🎁 Ingresar código de referido"
    },
    "group_link_button": {
        "en": "🟢 Get group link",
        "es": "🟢 Obtener enlace del grupo"
    },
    "share_phone_button": {
        "en": "📱 Share my phone number",
        "es": "📱 Compartir mi número"
    },
    "mycode_missing": {
        "en": "You don't have a code yet. Use /start and share your phone.",
        "es": "Aún no tienes código. Usa /start y comparte tu teléfono."
    },
    "referral_prompt": {
        "en": "Enter the *code of the person who invited you* (e.g. `CR-AB12-CD34`):",
        "es": "Escribe el *código de quien te invitó* (ej. `CR-AB12-CD34`):"
    },
    "invalid_referral": {
        "en": "❌ Invalid code. Check and try again.",
        "es": "❌ Código inválido. Verifica y vuelve a intentarlo."
    },
    "self_referral": {
        "en": "❌ You cannot use your own code.",
        "es": "❌ No puedes usar tu propio código."
    },
    "already_referred": {
        "en": "ℹ️ You already registered a referral code in this campaign.",
        "es": "ℹ️ Ya registraste un código de referido en esta campaña."
    },
    "reciprocal_blocked": {
        "en": "❌ Reciprocal referrals are not allowed in this campaign.",
        "es": "❌ Los referidos recíprocos no están permitidos en esta campaña."
    },
    "referral_done": {
        "en": "🎉 Done! Your referral has been registered. Thanks for participating.",
        "es": "🎉 ¡Listo! Tu referido fue registrado. Gracias por participar."
    },
    "group_missing_env": {
        "en": "ℹ️ Missing GROUP_CHAT_ID in .env",
        "es": "ℹ️ Falta configurar GROUP_CHAT_ID en el .env"
    },
    "banned_message": {
        "en": "🚫 You are banned from this group. Please contact an administrator.",
        "es": "🚫 Estás baneado del grupo. Por favor contacta a un administrador."
    },
    "group_link": {
        "en": "🟢 Group link (expires in {hours}h, 1 use):\n{link}",
        "es": "🟢 Enlace al grupo (vence en {hours}h, 1 uso):\n{link}"
    },
    "group_invite_fail_short": {
        "en": "ℹ️ Could not create invite link. Make sure the bot is an admin.",
        "es": "ℹ️ No pude crear un enlace. Asegúrate de que el bot sea admin."
    },
    "working": {
        "en": "⏳ Working…",
        "es": "⏳ Trabajando…"
    },
    "unauthorized": {
        "en": "❌ Unauthorized",
        "es": "❌ No autorizado"
    },
    "csv_exported": {
        "en": "📤 CSV exported:\n- `{file}`",
        "es": "📤 CSV exportado:\n- `{file}`"
    },
    "error": {
        "en": "⚠️ Error: {err}",
        "es": "⚠️ Error: {err}"
    },
    # NEW i18n keys
    "your_points": {"en": "Your points", "es": "Tus puntos"},
    "balance_header": {
        "en": "💼 Your balance",
        "es": "💼 Tu balance"
    },
    "balance_body": {
        "en": (
            "Approved referrals: {approved}\n"
            "Commission per referral: {commission}\n"
            "Gross earned: {gross}\n"
            "Paid out: {paid}\n"
            "Pending withdrawals: {pending}\n"
            "\nAvailable now: {available}"
        ),
        "es": (
            "Referidos aprobados: {approved}\n"
            "Comisión por referido: {commission}\n"
            "Bruto ganado: {gross}\n"
            "Pagado: {paid}\n"
            "Retiros pendientes: {pending}\n"
            "\nDisponible ahora: {available}"
        ),
    },
    "no_balance": {
        "en": "You have no earnings yet.",
        "es": "Aún no tienes ganancias."
    },
    "no_methods": {
        "en": "You don't have a payout method yet. Let's add one.",
        "es": "No tienes un método de cobro aún. Vamos a agregar uno."
    },
    "choose_method": {
        "en": "Choose a payout method:",
        "es": "Elige un método de cobro:"
    },
    "enter_method_details": {
        "en": "Send the details for **{method}** (e.g., email, ID, or account).",
        "es": "Envía los datos para **{method}** (por ejemplo, correo, ID o cuenta)."
    },
    "method_saved": {
        "en": "✅ Method saved and set as default.",
        "es": "✅ Método guardado y establecido como predeterminado."
    },
    "withdraw_created": {
        "en": "✅ Withdrawal request created for {amount}. We will notify admins to process it.",
        "es": "✅ Solicitud de retiro creada por {amount}. Notificaremos a los admins para procesarlo."
    },
    "insufficient_funds": {
        "en": "Insufficient available balance.",
        "es": "Saldo disponible insuficiente."
    },
    "invalid_amount": {
        "en": "Please provide a valid amount.",
        "es": "Por favor indica un monto válido."
    },
    "admin_withdraw_notice": {
        "en": (
            "📥 New withdrawal request\n"
            "User: {user_id} (@{username})\n"
            "Amount: {amount}\n"
            "Method: {method} {details}\n"
            "Payment ID: {pid}"
        ),
        "es": (
            "📥 Nueva solicitud de retiro\n"
            "Usuario: {user_id} (@{username})\n"
            "Monto: {amount}\n"
            "Método: {method} {details}\n"
            "ID de pago: {pid}"
        ),
    },
    "marked_paid": {
        "en": "✅ Payment #{pid} marked as PAID.",
        "es": "✅ Pago #{pid} marcado como PAID."
    },
}


def t(key: str, lang: str, **kwargs) -> str:
    """
    Translate a message by key and language, formatting with kwargs.
    Falls back to English if missing.
    """
    entry = TEXTS.get(key, {})
    msg = entry.get(lang) or entry.get("en") or ""
    return msg.format(**kwargs)


# ================== DB: Schema ==================
CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    user_id      INTEGER PRIMARY KEY,
    phone        TEXT UNIQUE,
    code         TEXT UNIQUE,
    assigned_at  TEXT,
    country_code TEXT,
    total_points  INTEGER NOT NULL DEFAULT 0
);
"""

ALTER_USERS_ADD_COUNTRY = "ALTER TABLE users ADD COLUMN country_code TEXT;"
ALTER_REFERRALS_ADD_APPROVED = "ALTER TABLE referrals ADD COLUMN approved INTEGER NOT NULL DEFAULT 0;"
ALTER_REFERRALS_ADD_POINTS = "ALTER TABLE referrals ADD COLUMN points_awarded INTEGER NOT NULL DEFAULT 0;"
ALTER_USERS_ADD_TOTAL_POINTS = "ALTER TABLE users ADD COLUMN total_points INTEGER NOT NULL DEFAULT 0;"

CREATE_IDX_USERS_CODE_UNIQUE = "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_code_unique ON users(code);"
CREATE_IDX_USERS_PHONE = "CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);"
CREATE_IDX_USERS_ASSIGNED_AT = "CREATE INDEX IF NOT EXISTS idx_users_assigned_at ON users(assigned_at);"
CREATE_IDX_USERS_COUNTRY = "CREATE INDEX IF NOT EXISTS idx_users_country ON users(country_code);"
CREATE_IDX_REFERRALS_REFERRER = "CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_user_id);"
CREATE_IDX_REFERRALS_REFEREE  = "CREATE INDEX IF NOT EXISTS idx_referrals_referee  ON referrals(referee_user_id);"
CREATE_IDX_REFERRALS_CAMPAIGN = "CREATE INDEX IF NOT EXISTS idx_referrals_campaign ON referrals(campaign_id);"

CREATE_CAMPAIGNS = """
CREATE TABLE IF NOT EXISTS campaigns (
  id            INTEGER PRIMARY KEY,
  name          TEXT NOT NULL,
  starts_at     TEXT,
  ends_at       TEXT,
  reward_type   TEXT,
  reward_value  INTEGER,
  is_active     INTEGER
);
"""

CREATE_REFERRALS = """
CREATE TABLE IF NOT EXISTS referrals (
  id                INTEGER PRIMARY KEY,
  campaign_id       INTEGER NOT NULL,
  referrer_user_id  INTEGER NOT NULL,
  referee_user_id   INTEGER NOT NULL,
  code_used         TEXT NOT NULL,
  created_at        TEXT NOT NULL,
  status            TEXT NOT NULL,              -- PENDING/APPROVED/REJECTED
  approved          INTEGER NOT NULL DEFAULT 0, -- NEW
  points_awarded    INTEGER NOT NULL DEFAULT 0, -- NEW
  UNIQUE(campaign_id, referee_user_id),
  FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
);
"""

CREATE_POINTS_HISTORY = """
CREATE TABLE IF NOT EXISTS points_history (
  id           INTEGER PRIMARY KEY,
  user_id      INTEGER NOT NULL,
  referral_id  INTEGER,
  points       INTEGER NOT NULL,
  reason       TEXT,
  created_at   TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(user_id),
  FOREIGN KEY (referral_id) REFERENCES referrals(id)
);
"""

# NEW: payout methods & payments
CREATE_PAYOUT_METHODS = """
CREATE TABLE IF NOT EXISTS payout_methods (
  id           INTEGER PRIMARY KEY,
  user_id      INTEGER NOT NULL,
  method_type  TEXT NOT NULL,      -- e.g., Paypal, BinancePay, Bank, SINPE
  details_json TEXT NOT NULL,      -- JSON payload with the specific fields
  is_default   INTEGER NOT NULL DEFAULT 0,
  created_at   TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(user_id)
);
"""

CREATE_PAYMENTS = """
CREATE TABLE IF NOT EXISTS payments (
  id             INTEGER PRIMARY KEY,
  user_id        INTEGER NOT NULL,
  amount_cents   INTEGER NOT NULL,
  status         TEXT NOT NULL,    -- REQUESTED/APPROVED/PAID/REJECTED/CANCELED
  method_id      INTEGER,
  requested_at   TEXT NOT NULL,
  processed_at   TEXT,
  note           TEXT,
  FOREIGN KEY (user_id) REFERENCES users(user_id),
  FOREIGN KEY (method_id) REFERENCES payout_methods(id)
);
"""

CREATE_IDX_PAYMENTS_USER = "CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id);"
CREATE_IDX_PAYMENTS_STATUS = "CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);"
CREATE_IDX_METHODS_USER = "CREATE INDEX IF NOT EXISTS idx_methods_user ON payout_methods(user_id);"

SEED_DEFAULT_CAMPAIGN = """
INSERT INTO campaigns (id, name, starts_at, ends_at, reward_type, reward_value, is_active)
VALUES (1, 'Default Referral Campaign', NULL, NULL, 'points', 1, 1)
ON CONFLICT(id) DO NOTHING;
"""


# ================== DB: Initialization ==================


# ================== Code Assignment ==================
async def assign_or_get_code(user_id: int, phone_e164: str, prefix_override: str, country_code: str) -> Optional[str]:
    existing = await get_existing_code_by_user(user_id)
    if existing:
        return existing

    phone_owner = await get_code_by_phone(phone_e164)
    if phone_owner:
        _, code = phone_owner
        return code

    # Try up to 5 times to generate a unique code
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


# ================== UI ==================
def build_affiliate_link_for_code(code: str) -> str:
    return f"https://t.me/{BOT_USERNAME}?start={code}"

def share_phone_kb(lang: str):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=TEXTS["share_phone_button"][lang], request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )



def remember_kb(lang: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=TEXTS["remember_button"][lang], callback_data="remember_code")],
            [InlineKeyboardButton(text=TEXTS["affiliate_link_button"][lang], callback_data="get_affiliate_link")],
            [InlineKeyboardButton(text=TEXTS["group_link_button"][lang], callback_data="get_group_link")]
        ]
    )


def referral_button(lang: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=TEXTS["referral_button"][lang], callback_data="enter_referral")]]
    )


def group_link_button(lang: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=TEXTS["group_link_button"][lang], callback_data="get_group_link")]]
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


# ================== Handlers ==================
# ======= Get group link on demand =======
@dp.message(Command("group"))
@dp.message(Command("grupo"))
async def cmd_group(message: Message):
    lang = get_lang(message.from_user)
    if not GROUP_CHAT_ID:
        await message.answer(t("group_missing_env", lang)); return
    try:
        member = await message.bot.get_chat_member(GROUP_CHAT_ID, message.from_user.id)
        if getattr(member, "status", None) == "kicked":
            await message.answer(t("banned_message", lang))
            return
    except Exception:
        pass
    invite = await create_one_time_invite(message.bot, GROUP_CHAT_ID, message.from_user.id, INVITE_TTL_HOURS)
    if invite:
        await message.answer(t("group_access", lang, hours=INVITE_TTL_HOURS, link=invite))
    else:
        await message.answer(t("group_invite_fail", lang))
@dp.callback_query(F.data == "get_affiliate_link")
async def cb_get_affiliate_link(q: CallbackQuery):
    lang = get_lang(q.from_user)
    code = await get_existing_code_by_user(q.from_user.id)
    if not code:
        await q.message.answer(t("mycode_missing", lang))
        await q.answer()
        return
    aff = build_affiliate_link_for_code(code)
    await q.message.answer(t("your_affiliate_link", lang, link=aff))
    await q.answer()
@dp.message(Command("mylink"))
@dp.message(Command("milink"))
async def mylink_cmd(message: Message):
    lang = get_lang(message.from_user)
    code = await get_existing_code_by_user(message.from_user.id)
    if not code:
        await message.answer(t("mycode_missing", lang))
        return
    aff = build_affiliate_link_for_code(code)
    await message.answer(t("your_affiliate_link", lang, link=aff))
def get_lang(user: types.User) -> str:
    code = (user.language_code or "en").lower()
    return "es" if code.startswith("es") else "en"

@dp.message(CommandStart())
async def on_start(message: Message):
    lang = get_lang(message.from_user)
    referrer_code = None
    # Detect DeepLink: /start <code>
    if message.text and message.text.startswith("/start"):
        parts = message.text.split()
        if len(parts) == 2:
            referrer_code = parts[1].strip()

    existing = await get_existing_code_by_user(message.from_user.id)
    if existing:
        await message.answer(t("already_has_code", lang), reply_markup=remember_kb(lang))
        await message.answer(t("optional_enter_code", lang), reply_markup=referral_button(lang))
        if GROUP_CHAT_ID:
            await message.answer(t("group_ready", lang), reply_markup=group_link_button(lang))
        return

    # Si llegó por DeepLink, guardar el referrer_code en el state (o en la DB si lo prefieres)
    if referrer_code:
        # Guardar en el objeto message para usarlo en el registro (ForceReply o phone handler)
        message.referrer_code = referrer_code

    await message.answer(t("start_mobile_only", lang), reply_markup=share_phone_kb(lang))


@dp.message(F.contact)
async def on_contact(message: Message):
    lang = get_lang(message.from_user)
    c = message.contact

    logging.info("[DEBUG contact] from_user.id=%s contact.user_id=%s phone=%s",
                 message.from_user.id,
                 getattr(c, "user_id", None),
                 c.phone_number)

    if not getattr(c, "user_id", None) or c.user_id != message.from_user.id:
        await message.answer(t("share_own_number_mobile", lang))
        return

    phone_e164 = e164(c.phone_number)
    country_iso = country_code_from_phone(phone_e164) or "ZZ"
    if not phone_e164:
        await message.answer(t("invalid_number", lang))
        return
    region = country_from_e164(phone_e164)

    code = await assign_or_get_code(message.from_user.id, phone_e164, prefix_override=region, country_code=region)
    await upsert_user(message.from_user.id, code, phone_e164)
    if not code:
        await message.answer(t("error", lang, err="Could not generate your code. Try again."))
        return

    affiliate_link = f"https://t.me/{BOT_USERNAME}?start={code}"
    msg_affiliate = t("your_affiliate_link", lang, link=affiliate_link)

    # Send verified phone, code, and affiliate link
    await message.answer(t("phone_verified", lang, region=region, code=code), reply_markup=ReplyKeyboardRemove())
    await message.answer(msg_affiliate, parse_mode="Markdown")
    await message.answer(t("mycode_has", lang, code=code))
    await message.answer(t("remember_offer", lang), reply_markup=remember_kb(lang))
    await message.answer(t("enter_inviter_code", lang), reply_markup=referral_button(lang))

    # Always send group invite link after registration
    if GROUP_CHAT_ID:
        invite = await create_one_time_invite(message.bot, GROUP_CHAT_ID, message.from_user.id, INVITE_TTL_HOURS)
        if invite:
            await message.answer(t("group_access", lang, hours=INVITE_TTL_HOURS, link=invite))
        else:
            await message.answer(t("group_invite_fail", lang))


@dp.message(Command("mycode"))
@dp.message(Command("micodigo"))
async def cmd_micodigo(message: Message):
    lang = get_lang(message.from_user)
    code = await get_existing_code_by_user(message.from_user.id)
    if code:
        await message.answer(t("mycode_has", lang, code=code))
    else:
        await message.answer(t("mycode_missing", lang))


@dp.callback_query(F.data == "remember_code")
async def cb_remember(callback: CallbackQuery):
    lang = get_lang(callback.from_user)
    code = await get_existing_code_by_user(callback.from_user.id)
    if code:
        await callback.message.answer(t("mycode_has", lang, code=code))
    else:
        await callback.message.answer(t("mycode_missing", lang))
    await callback.answer()


# ======= Referrals Flow (ForceReply) =======
@dp.callback_query(F.data == "enter_referral")
async def cb_enter_referral(q: CallbackQuery):
    lang = get_lang(q.from_user)
    prompt = t("referral_prompt", lang) + "\n\n#REFERRAL_PROMPT"
    await q.message.answer(prompt, reply_markup=ForceReply(selective=True))
    await q.answer()


@dp.message(F.reply_to_message, F.text)
async def on_force_reply_inputs(message: Message):
    """
    Handles both referral code input and payout method details via ForceReply markers.
    """
    lang = get_lang(message.from_user)
    if not message.reply_to_message or not message.reply_to_message.text:
        return

    ref_lower = message.reply_to_message.text.lower()

    # Referral code input
    if "#referral_prompt" in ref_lower:
        referee_id = message.from_user.id
        raw = message.text.strip().upper()
        code = (
            raw.replace(" ", "")
               .replace("_", "")
               .replace("—", "-")
               .replace("–", "-")
        )
        referrer_id = await find_user_by_code(code)
        if not referrer_id:
            await message.answer(t("invalid_referral", lang)); return
        if referrer_id == referee_id:
            await message.answer(t("self_referral", lang)); return
        campaign_id = str(ACTIVE_CAMPAIGN_ID)
        if await referee_already_referred(campaign_id, referee_id):
            await message.answer(t("already_referred", lang)); return
        if await is_reciprocal_referral(campaign_id, referee_id, referrer_id):
            await message.answer(t("reciprocal_blocked", lang)); return
        try:
            await insert_referral(campaign_id, referrer_id, referee_id, code)
        except sqlite3.IntegrityError:
            await message.answer(t("already_referred", lang)); return
        await message.answer(t("referral_done", lang))
        return

    # Payout method details input
    m = re.search(r"#ADD_METHOD_DETAILS:([A-Za-z0-9_]+)(?::(\d+))?", message.reply_to_message.text)
    if m:
        method_type = m.group(1)
        amount_cents = int(m.group(2) or 0)
        details_text = message.text.strip()
        # Store as {"value": details_text}
        method_id = await add_payout_method(message.from_user.id, method_type, {"value": details_text}, set_default=True)
        await message.answer(t("method_saved", lang))
        if amount_cents > 0:
            pid = await create_withdraw_request(message.from_user.id, amount_cents, method_id)
            pretty = format_money(amount_cents)
            await message.answer(t("withdraw_created", lang, amount=pretty))
            await notify_withdraw(message.bot, message.from_user, pid, amount_cents, method_type, details_text, lang)
        return


# ======= Get group link on demand =======
@dp.callback_query(F.data == "get_group_link")
async def cb_get_group_link(q: CallbackQuery):
    lang = get_lang(q.from_user)
    if not GROUP_CHAT_ID:
        await q.message.answer(t("group_missing_env", lang)); await q.answer(); return

    # Check ban
    try:
        member = await q.bot.get_chat_member(GROUP_CHAT_ID, q.from_user.id)
        if getattr(member, "status", None) == "kicked":
            await q.message.answer(t("banned_message", lang))
            await q.answer()
            return
    except Exception:
        pass

    # Create one-time invite link
    invite = await create_one_time_invite(q.bot, GROUP_CHAT_ID, q.from_user.id, INVITE_TTL_HOURS)
    if invite:
        await q.message.answer(t("group_link", lang, hours=INVITE_TTL_HOURS, link=invite))
    else:
        await q.message.answer(t("group_invite_fail_short", lang))
    await q.answer()


# ======= Export CSV (admin only) =======
@dp.message(Command("exportcsv"))
@dp.message(F.text.startswith("/exportcsv"))
async def export_csv(message: Message):
    lang = get_lang(message.from_user)
    try:
        await message.answer(t("working", lang))

        if str(message.from_user.id) not in ADMIN_USER_IDS:
            return await message.answer(t("unauthorized", lang))

        os.makedirs("exports", exist_ok=True)
        ts = dt.utcnow().strftime("%Y%m%d-%H%M%S")

        users_file = f"exports/users-{ts}.csv"
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT user_id, phone, code, assigned_at, country_code FROM users") as cur:
                rows = await cur.fetchall()
        with open(users_file, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["user_id","phone","code","assigned_at","country_code"]); w.writerows(rows)

        base = os.path.basename(users_file)
        return await message.answer(t("csv_exported", lang, file=base), parse_mode="Markdown")

    except Exception as e:
        return await message.answer(t("error", lang, err=str(e)))


# ======= Admin: Approve referral and add points =======
@dp.message(Command("approve_referral"))
async def approve_referral_cmd(message: Message):
    lang = get_lang(message.from_user)

    if str(message.from_user.id) not in ADMIN_USER_IDS:
        await message.answer(t("unauthorized", lang))
        return

    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer(
            "Uso / Usage:\n"
            "`/approve_referral <referral_id> <points>`\n"
            "Ej: `/approve_referral 42 10`\n"
            "Ex: `/approve_referral 42 10`",
            parse_mode="Markdown"
        )
        return

    try:
        referral_id = int(args[1])
        points = int(args[2])
    except ValueError:
        await message.answer("❌ Parámetros inválidos. Deben ser números.\n❌ Invalid parameters. Must be integers.")
        return

    ok = await approve_referral_and_award_points(referral_id, points)
    if not ok:
        await message.answer(
            "❌ No se pudo aprobar (no existe, ya aprobado o puntos inválidos).\n"
            "❌ Could not approve (not found, already approved, or invalid points)."
        )
        return

    await message.answer(
        f"✅ Referral #{referral_id} aprobado. +{points} pts al referrer.\n"
        f"✅ Approved. +{points} pts to referrer."
    )


# ======= Points quick check =======
@dp.message(Command("mypoints"))
@dp.message(Command("mispuntos"))
async def mypoints_cmd(message: Message):
    lang = get_lang(message.from_user)
    pts = await get_user_points(message.from_user.id)
    await message.answer(
        f"🏅 {t('your_points', lang)}: {pts}"
    )


# ======= Balance (money) =======
@dp.message(Command("balance"))
@dp.message(Command("misganancias"))
async def balance_cmd(message: Message):
    lang = get_lang(message.from_user)
    approved, gross, paid, pending = await compute_balances(message.from_user.id)
    available = max(0, gross - paid)
    if approved == 0 and gross == 0:
        await message.answer(t("no_balance", lang))
        return
    msg = [t("balance_header", lang)]
    msg.append(t("balance_body", lang,
                 approved=approved,
                 commission=format_money(COMMISSION_PER_APPROVED_CENTS),
                 gross=format_money(gross),
                 paid=format_money(paid),
                 pending=format_money(pending),
                 available=format_money(available)))
    await message.answer("\n".join(msg))


# ======= Withdraw flow =======
@dp.message(Command("withdraw"))
@dp.message(Command("cobrar"))
async def withdraw_cmd(message: Message):
    lang = get_lang(message.from_user)

    # Parse optional amount
    args = message.text.split(maxsplit=1)
    requested_cents = None
    if len(args) == 2:
        amount_text = args[1].strip().replace(",", ".")
        try:
            # Support decimal like 10.50
            if "." in amount_text:
                requested_cents = int(round(float(amount_text) * 100))
            else:
                requested_cents = int(amount_text) * 100
        except Exception:
            await message.answer(t("invalid_amount", lang))
            return

    approved, gross, paid, _pending = await compute_balances(message.from_user.id)
    available = max(0, gross - paid)

    if available <= 0:
        await message.answer(t("insufficient_funds", lang))
        return

    if requested_cents is None:
        requested_cents = available

    if requested_cents <= 0 or requested_cents > available:
        await message.answer(t("insufficient_funds", lang))
        return

    # Check for default method
    default_m = await get_default_method(message.from_user.id)
    if not default_m:
        await message.answer(t("no_methods", lang))
        await message.answer(t("choose_method", lang), reply_markup=payout_methods_kb())
        # Store requested amount in a hidden marker using next ForceReply
        marker = f"#ADD_METHOD_DETAILS:{{method}}:{requested_cents}"
        await message.answer(t("enter_method_details", lang, method="…"), reply_markup=ForceReply(selective=True))
        # We will re-send the ForceReply once method is chosen (callback handler below)
        # Save marker in a message so that next reply uses it. We'll edit later on callback.
        return

    # Create withdrawal immediately using default method
    pid = await create_withdraw_request(message.from_user.id, requested_cents, default_m["id"])
    pretty = format_money(requested_cents)
    await message.answer(t("withdraw_created", lang, amount=pretty))
    details = json.loads(default_m["details_json"]) if default_m else {}
    await notify_withdraw(message.bot, message.from_user, pid, requested_cents, default_m["method_type"], details.get("value", ""), lang)


@dp.callback_query(F.data.startswith("pm:"))
async def cb_pick_method(cb: CallbackQuery):
    """User picked a payout method type; ask for details via ForceReply."""
    await cb.answer()
    lang = get_lang(cb.from_user)
    method_type = cb.data.split(":",1)[1]
    prompt = t("enter_method_details", lang, method=method_type) + f"\n\n#ADD_METHOD_DETAILS:{method_type}"
    await cb.message.answer(prompt, reply_markup=ForceReply(selective=True))


# ======= Admin: mark payment as PAID =======
@dp.message(Command("mark_paid"))
async def mark_paid_cmd(message: Message):
    lang = get_lang(message.from_user)
    if str(message.from_user.id) not in ADMIN_USER_IDS:
        await message.answer(t("unauthorized", lang))
        return

    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        await message.answer("Usage: /mark_paid <payment_id> [note]")
        return
    try:
        pid = int(args[1])
    except Exception:
        await message.answer("Invalid payment id")
        return
    note = args[2] if len(args) >= 3 else None

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE payments SET status='PAID', processed_at=?, note=COALESCE(note, '') || ? WHERE id=?",
                         (utcnow_iso(), ("\n" + note) if note else "", pid))
        await db.commit()
    await message.answer(t("marked_paid", lang, pid=pid))

@dp.message(Command("id"))
async def cmd_id(m: Message):
    await m.answer(f"chat_id={m.chat.id}\ntype={m.chat.type}\ntitle={m.chat.title}")

# ======= Notifications =======
async def notify_withdraw(bot: Bot, user: types.User, pid: int, amount_cents: int, method_type: str, details: str, lang: str):
    username = f"@{user.username}" if user.username else "(no username)"
    msg = t("admin_withdraw_notice", lang,
            user_id=user.id,
            username=user.username or "",
            amount=format_money(amount_cents),
            method=method_type,
            details=f"[{details}]" if details else "",
            pid=pid)
    await notify_admins(bot, msg)


# ======= Helpers =======

def format_money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(int(cents))
    major = cents // 100
    minor = cents % 100
    return f"{sign}{CURRENCY} {major}.{minor:02d}"

def country_from_e164(phone_e164: str) -> str:
    try:
        num = phonenumbers.parse(phone_e164, None)  # E.164: debe empezar con '+'
        return phonenumbers.region_code_for_number(num) or "ZZ"
    except phonenumbers.NumberParseException:
        return "ZZ"

# === HELP (/help y botón "❓ Ayuda") ===

## Duplicate imports removed

def _help_text(lang: str) -> str:
    if str(lang).lower().startswith("es"):
        return (
            "*¿Cómo funciona?*\n"
            "1) Comparte tu teléfono (móvil) para verificarlo.\n"
            "2) Te damos tu *código único* y podrás invitar referidos.\n"
            "3) Mira tus puntos/ganancias y solicita retiro cuando corresponda.\n\n"
            "*Comandos útiles*\n"
            "• /micodigo — Mostrar mi código\n"
            "• /mispuntos — Ver mis puntos\n"
            "• /misganancias — Ver mis ganancias/balance\n"
            "• /cobrar — Solicitar retiro\n\n"
            "*Privacidad*\n"
            "Guardamos tu ID de Telegram, teléfono (E.164), país (por prefijo) y tu código. No compartimos datos con terceros."
        )
    else:
        return (
            "*How it works*\n"
            "1) Share your phone (mobile) to verify it.\n"
            "2) We issue your *unique code* so you can invite referrals.\n"
            "3) Check your points/earnings and request withdrawals when eligible.\n\n"
            "*Useful commands*\n"
            "• /mycode — Show my code\n"
            "• /mypoints — Show my points\n"
            "• /balance — Show balance\n"
            "• /withdraw — Request withdrawal\n\n"
            "*Privacy*\n"
            "We store your Telegram ID, phone (E.164), country (by prefix) and your code. We don't share data with third parties."
        )

def _help_kb(lang: str) -> InlineKeyboardMarkup:
    btns = [[InlineKeyboardButton(text="⬅️ " + ("Volver al menú" if str(lang).lower().startswith("es") else "Back to menu"),
                                  callback_data="back_to_menu")]]
    return InlineKeyboardMarkup(inline_keyboard=btns)

@dp.message(Command("help"))
async def cmd_help(message: Message):
    lang = get_lang(message.from_user)
    await message.answer(_help_text(lang), parse_mode="Markdown", reply_markup=_help_kb(lang))

@dp.callback_query(F.data == "help")
async def cb_help(q: CallbackQuery):
    lang = get_lang(q.from_user)
    await q.message.answer(_help_text(lang), parse_mode="Markdown", reply_markup=_help_kb(lang))
    await q.answer()

@dp.callback_query(F.data == "back_to_menu")
async def cb_back_to_menu(q: CallbackQuery):
    lang = get_lang(q.from_user)
    # Reutiliza tus teclados existentes:
    await q.message.answer(t("remember_offer", lang), reply_markup=remember_kb(lang))
    await q.message.answer(t("enter_inviter_code", lang), reply_markup=referral_button(lang))
    if GROUP_CHAT_ID:
        await q.message.answer(t("group_ready", lang), reply_markup=group_link_button(lang))
    await q.answer()

    # === /HELP ===


# ================== Main ==================
async def main():
    await init_db()
    bot = Bot(BOT_TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

