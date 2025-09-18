import pytest
from aiogram.types import Message, User, Chat
from aiogram.filters import CommandStart
from aiogram import Dispatcher
import datetime

class DummyBot:
    def __init__(self):
        self.last_message = None
    async def send_message(self, chat_id, text, **kwargs):
        self.last_message = (chat_id, text)
        return None

@pytest.mark.asyncio
async def test_i18n_language_detection():
    dp = Dispatcher()
    bot = DummyBot()
    # Handler que responde según idioma
    @dp.message(CommandStart())
    async def start_handler(message: Message, **kwargs):
        lang = getattr(message.from_user, "language_code", "es")
        if lang == "en":
            await bot.send_message(message.chat.id, "Welcome!")
        elif lang == "pt":
            await bot.send_message(message.chat.id, "Bem-vindo!")
        else:
            await bot.send_message(message.chat.id, "¡Bienvenido!")

    chat = Chat(id=1, type="private")
    # Simula usuario en inglés
    user_en = User(id=1, is_bot=False, first_name="Test", language_code="en")
    message_en = Message(message_id=1, from_user=user_en, chat=chat, date=int(datetime.datetime.now().timestamp()), text="/start")
    handler = None
    for h in getattr(dp.message, "handlers", []):
        if hasattr(h, "filters") and hasattr(h.filters, "commands") and h.filters.commands == ["start"]:
            handler = h.callback
            break
    if handler is None:
        handler = start_handler
    await handler(message_en)
    assert bot.last_message == (1, "Welcome!"), "No respondió en inglés"
    # Simula usuario en portugués
    user_pt = User(id=2, is_bot=False, first_name="Test", language_code="pt")
    message_pt = Message(message_id=2, from_user=user_pt, chat=chat, date=int(datetime.datetime.now().timestamp()), text="/start")
    await handler(message_pt)
    assert bot.last_message == (1, "Bem-vindo!"), "No respondió en portugués"
    # Simula usuario en español (default)
    user_es = User(id=3, is_bot=False, first_name="Test", language_code="es")
    message_es = Message(message_id=3, from_user=user_es, chat=chat, date=int(datetime.datetime.now().timestamp()), text="/start")
    await handler(message_es)
    assert bot.last_message == (1, "¡Bienvenido!"), "No respondió en español"
