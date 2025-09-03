# Hello.py
import os
import re
import asyncio
import datetime
import sqlite3
import secrets
from typing import Optional
import csv
import os
from datetime import datetime


from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ForceReply
)

from dotenv import load_dotenv
import aiosqlite
import phonenumbers   # 🔥 NUEVO

# ================== Config ==================
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = "codes.db"
ADMIN_USER_IDS = [x.strip() for x in os.getenv("ADMIN_USER_IDS", "").split(",") if x.strip()]

DEFAULT_REGION = os.getenv("DEFAULT_REGION", "CR")   # 🔥 NUEVO: fallback región para parsear teléfonos
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")           # 🔥 NUEVO: id del grupo (ej: -1001234567890)
INVITE_TTL_HOURS = int(os.getenv("INVITE_TTL_HOURS", "12"))  # 🔥 NUEVO: horas de validez del enlace

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN no configurado (.env)")

dp = Dispatcher()
ACTIVE_CAMPAIGN_ID = 1

# ================== Utilidades ==================
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O/1/I

def build_random_code(prefix: str = "RF", length: int = 8) -> str:
    """Código aleatorio legible, sin PII. Formato: RF-XXXX-XXXX"""
    body = "".join(secrets.choice(ALPHABET) for _ in range(length))
    return f"{prefix}-{body[:4]}-{body[4:]}"

def utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

# 🔥 NUEVO: normalizar a E.164 y obtener país
def e164(phone_raw: str, default_region: str = DEFAULT_REGION) -> Optional[str]:
    try:
        parsed = phonenumbers.parse(phone_raw, None if phone_raw.strip().startswith("+") else default_region)
        if not phonenumbers.is_valid_number(parsed):
            return None
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        return None

def country_code_from_phone(phone_raw: str, default_region: str = DEFAULT_REGION) -> str:
    try:
        parsed = phonenumbers.parse(phone_raw, None if phone_raw.strip().startswith("+") else default_region)
        region = phonenumbers.region_code_for_number(parsed)
        return region or "UNKN"
    except Exception:
        return "UNKN"

# 🔥 NUEVO: helper para crear enlaces de invitación de 1 uso con expiración
async def create_one_time_invite(bot: Bot, chat_id: str, user_id: int, ttl_hours: int = INVITE_TTL_HOURS) -> Optional[str]:
    """
    Requiere que el bot sea admin del grupo con permiso para crear enlaces de invitación.
    """
    try:
        expires_at = int((datetime.datetime.utcnow() + datetime.timedelta(hours=ttl_hours)).timestamp())
        link = await bot.create_chat_invite_link(
            chat_id=chat_id,
            name=f"one-use-{user_id}",
            expire_date=expires_at,
            member_limit=1
        )
        return link.invite_link
    except Exception as e:
        # Podría fallar si el bot no es admin o el chat_id es incorrecto
        print(f"[WARN] No se pudo crear invite link: {e}")
        return None

# ================== DB: Esquema ==================
CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    user_id      INTEGER PRIMARY KEY,
    phone        TEXT UNIQUE,
    code         TEXT UNIQUE,
    assigned_at  TEXT,
    country_code TEXT
);
"""

ALTER_USERS_ADD_COUNTRY = "ALTER TABLE users ADD COLUMN country_code TEXT;"

CREATE_IDX_USERS_CODE_UNIQUE = "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_code_unique ON users(code);"
CREATE_IDX_USERS_PHONE = "CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);"
CREATE_IDX_USERS_ASSIGNED_AT = "CREATE INDEX IF NOT EXISTS idx_users_assigned_at ON users(assigned_at);"
CREATE_IDX_USERS_COUNTRY = "CREATE INDEX IF NOT EXISTS idx_users_country ON users(country_code);"

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
  status            TEXT NOT NULL,
  UNIQUE(campaign_id, referee_user_id),
  FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
);
"""

SEED_DEFAULT_CAMPAIGN = """
INSERT INTO campaigns (id, name, starts_at, ends_at, reward_type, reward_value, is_active)
VALUES (1, 'Campaña Referidos Default', NULL, NULL, 'points', 1, 1)
ON CONFLICT(id) DO NOTHING;
"""

# ================== DB: Inicialización ==================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")

        await db.execute(CREATE_USERS)

        # Intentar agregar columna country_code si no existía
        try:
            await db.execute(ALTER_USERS_ADD_COUNTRY)
        except Exception:
            pass

        await db.execute(CREATE_CAMPAIGNS)
        await db.execute(CREATE_REFERRALS)

        await db.execute(CREATE_IDX_USERS_CODE_UNIQUE)
        await db.execute(CREATE_IDX_USERS_PHONE)
        await db.execute(CREATE_IDX_USERS_ASSIGNED_AT)
        await db.execute(CREATE_IDX_USERS_COUNTRY)

        await db.execute(SEED_DEFAULT_CAMPAIGN)
        await db.commit()

# ================== DB: Helpers ==================
async def get_existing_code_by_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT code FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else None

async def get_code_by_phone(phone: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id, code FROM users WHERE phone = ?", (phone,))
        row = await cur.fetchone()
        return row if row else None

async def find_user_by_code(code: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM users WHERE code = ?", (code,))
        row = await cur.fetchone()
        return row[0] if row else None

async def referee_already_referred(campaign_id: int, referee_user_id: int) -> bool:  # 🔥 NUEVO
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT 1 FROM referrals WHERE campaign_id=? AND referee_user_id=? LIMIT 1",
            (campaign_id, referee_user_id)
        )
        return bool(await cur.fetchone())

async def insert_referral(campaign_id: int, referrer_user_id: int, referee_user_id: int, code_used: str):  # 🔥 NUEVO
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO referrals (campaign_id, referrer_user_id, referee_user_id, code_used, created_at, status)
            VALUES (?, ?, ?, ?, ?, 'APPROVED')
            """,
            (campaign_id, referrer_user_id, referee_user_id, code_used, utcnow_iso())
        )
        await db.commit()

# ================== Asignación de código ==================
async def assign_or_get_code(user_id: int, phone_e164: str, prefix_override: str, country_code: str) -> Optional[str]:
    existing = await get_existing_code_by_user(user_id)
    if existing:
        return existing

    phone_owner = await get_code_by_phone(phone_e164)
    if phone_owner:
        _, code = phone_owner
        return code
        
    async with aiosqlite.connect(DB_PATH) as db:

        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")

        for _ in range(5):
            code = build_random_code(prefix=prefix_override or "RF", length=8)
            try:
                await db.execute(
                    """
                    INSERT INTO users (user_id, phone, code, assigned_at, country_code)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET 
                        phone=excluded.phone,
                        code=excluded.code,
                        assigned_at=excluded.assigned_at,
                        country_code=excluded.country_code
                    """,
                    (user_id, phone_e164, code, utcnow_iso(), country_code)
                )
                await db.commit()
                return code
            except sqlite3.IntegrityError as e:
                msg = str(e).lower()
                if "unique" in msg and "users(code)" in msg:
                    continue
                if "unique" in msg and "users.phone" in msg:
                    row = await get_code_by_phone(phone_e164)
                    if row:
                        _, existing_code = row
                        return existing_code
                raise
    return None

# ================== UI ==================
def share_phone_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Compartir mi teléfono", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def remember_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔑 Recordar mi código", callback_data="remember_code")]]
    )

def referral_button():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🎁 Ingresar código de referido", callback_data="enter_referral")]]
    )

def group_link_button():  # 🔥 NUEVO
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🟢 Obtener enlace del grupo", callback_data="get_group_link")]]
    )

# ================== Handlers ==================
@dp.message(lambda message: not message.text or not message.text.startswith("/"))
async def debug_all_messages(message: Message):
    print(f"[DEBUG] Received non-command message: text='{message.text}', from_user_id={message.from_user.id}")
@dp.message(CommandStart())
async def on_start(message: Message):
    existing = await get_existing_code_by_user(message.from_user.id)
    if existing:
        await message.answer(
            "Ya tienes un código asignado. Toca el botón para verlo o ingresa un código de referido:",
            reply_markup=remember_kb()
        )
        await message.answer("Opcional: si te invitaron, ingresa su código aquí 👇", reply_markup=referral_button())
        if GROUP_CHAT_ID:  # 🔥 NUEVO
            await message.answer("¿Listo para entrar al grupo?", reply_markup=group_link_button())
        return

    await message.answer(
        "Hola 👋\nPara asignarte tu código único, toca el botón y comparte tu número.",
        reply_markup=share_phone_kb()
    )

@dp.message(F.contact)
async def on_contact(message: Message):
    c = message.contact
    if c.user_id != message.from_user.id:
        await message.answer("⚠️ Comparte tu **propio** número.")
        return

    # Convertir a E.164 y detectar país
    phone_e164 = e164(c.phone_number)
    if not phone_e164:
        await message.answer("⚠️ Número inválido. Vuelve a tocar el botón y comparte tu número.")
        return
    region = country_code_from_phone(c.phone_number)  # ej: 'CR', 'MX', etc.

    code = await assign_or_get_code(message.from_user.id, phone_e164, prefix_override=region, country_code=region)
    if not code:
        await message.answer("😕 No pude generar tu código. Intenta de nuevo.")
        return

    await message.answer(
        f"✅ Teléfono verificado.\n🌎 País detectado: {region}\n🔑 Tu código único: {code}",
        reply_markup=ReplyKeyboardRemove()
    )
    await message.answer("¿Quieres recordarlo rápido más tarde?", reply_markup=remember_kb())
    await message.answer("Si te invitaron, ingresa el código de quien te refirió:", reply_markup=referral_button())

    # 🔥 NUEVO: entregar enlace al grupo (un solo uso, con expiración)
    if GROUP_CHAT_ID:
        bot = message.bot
        invite = await create_one_time_invite(bot, GROUP_CHAT_ID, message.from_user.id, INVITE_TTL_HOURS)
        if invite:
            await message.answer(
                f"🟢 Acceso al grupo (vence en {INVITE_TTL_HOURS}h, 1 uso):\n{invite}"
            )
        else:
            await message.answer(
                "ℹ️ No pude crear un enlace de invitación. Verifica que el bot sea **admin** del grupo y que `GROUP_CHAT_ID` sea correcto."
            )
# ======
@dp.message(Command("mycode"))
@dp.message(Command("micodigo"))
async def cmd_micodigo(message: Message):
    code = await get_existing_code_by_user(message.from_user.id)
    if code:
        await message.answer(f"🔑 Tu código es: {code}")
    else:
        await message.answer("Aún no tienes código. Usa /start y comparte tu teléfono.")
# 👆 importante: este bloque termina aquí SIN indentación pendiente
# ======
@dp.message(Command("exportcsv"))
@dp.message(F.text.startswith("/exportcsv"))
async def export_csv(message: Message):
    try:
        # 1) Confirma que entró
        await message.answer("⏳ Working…")

        # 2) Verifica permisos admin
        if str(message.from_user.id) not in ADMIN_USER_IDS:
            return await message.answer("❌ Unauthorized")

        # 3) Crea carpeta y timestamp
        os.makedirs("exports", exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")

        # 4) Export mínimo viable: users.csv
        users_file = f"exports/users-{ts}.csv"
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT user_id, phone, code, assigned_at, country_code FROM users"
            ) as cur:
                rows = await cur.fetchall()

        with open(users_file, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["user_id", "phone", "code", "assigned_at", "country_code"])
            w.writerows(rows)

        # 5) Respuesta final
        base = os.path.basename(users_file)
        return await message.answer(f"📤 CSV exported:\n- `{base}`", parse_mode="Markdown")

    except Exception as e:
        # Te manda el error al chat para depurar rápido
        return await message.answer(f"⚠️ Error: {e}")

   
@dp.callback_query(F.data == "remember_code")
async def cb_remember(callback: CallbackQuery):
    code = await get_existing_code_by_user(callback.from_user.id)
    if code:
        await callback.message.answer(f"🔑 Tu código es: {code}")
    else:
        await callback.message.answer("Aún no tienes código. Usa /start y comparte tu teléfono.")
    await callback.answer()

#@dp.message()
#async def debug_chat_id(message: Message):
 #   print("Chat ID:", message.chat.id)    


# ======= Flujo de REFERIDOS (ForceReply) =======  🔥 NUEVO
@dp.callback_query(F.data == "enter_referral")
async def cb_enter_referral(q: CallbackQuery):
    await q.message.answer(
        "Escribe el *código de quien te invitó* (ej. `CR-AB12-CD34`):",
        reply_markup=ForceReply(selective=True),
        parse_mode="Markdown"
    )
    await q.answer()

@dp.message(F.reply_to_message, F.text)
async def on_referral_code_input(message: Message):
    # Verifica que realmente está respondiendo a nuestro ForceReply
    if not message.reply_to_message or not message.reply_to_message.text:
        return
    if "código de quien te invitó" not in message.reply_to_message.text.lower():
        return

    referee_id = message.from_user.id
    raw = message.text.strip().upper()
    code = raw.replace(" ", "").replace("_", "").replace("—", "-")

    # 1) Buscar dueño del código
    referrer_id = await find_user_by_code(code)
    if not referrer_id:
        await message.answer("❌ Código inválido. Verifica y vuelve a intentarlo.")
        return

    if referrer_id == referee_id:
        await message.answer("❌ No puedes usar tu propio código.")
        return

    # 2) ¿Ya registró un referido antes en esta campaña?
    if await referee_already_referred(ACTIVE_CAMPAIGN_ID, referee_id):
        await message.answer("ℹ️ Ya registraste un código de referido en esta campaña.")
        return

    # 3) Insertar referral (aprobación automática básica)
    try:
        await insert_referral(ACTIVE_CAMPAIGN_ID, referrer_id, referee_id, code)
    except sqlite3.IntegrityError:
        await message.answer("ℹ️ Ya registraste un código de referido en esta campaña.")
        return

    await message.answer("🎉 ¡Listo! Tu referido fue registrado. Gracias por participar.")

# ======= Obtener enlace del grupo bajo demanda =======  🔥 NUEVO
@dp.callback_query(F.data == "get_group_link")
async def cb_get_group_link(q: CallbackQuery):
    if not GROUP_CHAT_ID:
        await q.message.answer("ℹ️ Falta configurar GROUP_CHAT_ID en el .env")
        await q.answer()
        return
    invite = await create_one_time_invite(q.bot, GROUP_CHAT_ID, q.from_user.id, INVITE_TTL_HOURS)
    if invite:
        await q.message.answer(f"🟢 Enlace al grupo (vence en {INVITE_TTL_HOURS}h, 1 uso):\n{invite}")
    else:
        await q.message.answer("ℹ️ No pude crear un enlace. Asegúrate de que el bot sea admin del grupo.")
        await q.answer()

# ================== Main ==================
async def main():
    await init_db()
    bot = Bot(BOT_TOKEN)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
