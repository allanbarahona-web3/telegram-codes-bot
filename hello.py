import os
import re
import asyncio
import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from dotenv import load_dotenv
import aiosqlite

# ================== Config ==================
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = "codes.db"

dp = Dispatcher()

# ================== Utilidades ==================
def normalize_phone(s: str) -> str:
    return re.sub(r'\D', '', s)

def month_abbr_es(m: int) -> str:
    MAP = {1:"ENE",2:"FEB",3:"MAR",4:"ABR",5:"MAY",6:"JUN",7:"JUL",8:"AGO",9:"SET",10:"OCT",11:"NOV",12:"DIC"}
    return MAP.get(m, "MES")

def make_code(phone_digits: str, dt: datetime.datetime) -> str:
    return f"{month_abbr_es(dt.month)}{phone_digits}{dt.year}"

# ================== DB ==================
CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    phone       TEXT UNIQUE,
    code        TEXT,
    assigned_at TEXT
);
"""

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_USERS)
        await db.commit()

async def get_existing_code_by_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT code FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else None

async def get_code_by_phone(phone: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id, code FROM users WHERE phone = ?", (phone,))
        row = await cur.fetchone()
        return row if row else None  # (owner_user_id, code)

async def assign_or_get_code(user_id: int, phone: str) -> str | None:
    # 1) Si el user ya tiene, devolver
    existing = await get_existing_code_by_user(user_id)
    if existing:
        return existing

    # 2) Si ese teléfono ya pertenece a otro user, devolver ese código (NO reasignar dueño)
    phone_owner = await get_code_by_phone(phone)
    if phone_owner:
        _, code = phone_owner
        return code

    # 3) Crear y fijar por primera vez
    now = datetime.datetime.now()
    code = make_code(phone, now)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (user_id, phone, code, assigned_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(phone) DO NOTHING
            """,
            (user_id, phone, code, now.isoformat())
        )
        await db.commit()

    # Si no insertó por conflicto, devolver existente por phone
    phone_owner = await get_code_by_phone(phone)
    if phone_owner:
        _, code = phone_owner
        return code

    return code

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

# ================== Handlers ==================
@dp.message(CommandStart())
async def on_start(message: Message):
    existing = await get_existing_code_by_user(message.from_user.id)
    if existing:
        # Enviar botón inline en el MISMO mensaje con texto visible
        await message.answer("Ya tienes un código asignado. Toca el botón para verlo:", reply_markup=remember_kb())
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

    phone = normalize_phone(c.phone_number)
    if not (6 <= len(phone) <= 15):
        await message.answer("⚠️ Número inválido. Vuelve a tocar el botón y comparte tu número de Telegram.")
        return

    code = await assign_or_get_code(message.from_user.id, phone)
    if not code:
        await message.answer("😕 No pude generar tu código. Intenta de nuevo.")
        return

    # Responder con el código y, en el mismo mensaje, ofrecer el botón "Recordar"
    await message.answer(
        f"✅ Teléfono: {phone}\n🏷️ Código único: {code}\n\nCuando lo necesites de nuevo, usa /micodigo o toca el botón.",
        reply_markup=remember_kb()
    )
    # Ocultar el teclado de compartir contacto
    await message.answer("Teclado ocultado.", reply_markup=ReplyKeyboardRemove())

@dp.message(Command("micodigo"))
async def cmd_micodigo(message: Message):
    code = await get_existing_code_by_user(message.from_user.id)
    if code:
        await message.answer(f"🔑 Tu código es: {code}")
    else:
        await message.answer("Aún no tienes código. Usa /start y comparte tu teléfono.")

@dp.callback_query(F.data == "remember_code")
async def cb_remember(callback: CallbackQuery):
    code = await get_existing_code_by_user(callback.from_user.id)
    if code:
        await callback.message.answer(f"🔑 Tu código es: {code}")
    else:
        await callback.message.answer("Aún no tienes código. Usa /start y comparte tu teléfono.")
    await callback.answer()

async def main():
    await init_db()
    bot = Bot(BOT_TOKEN)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())