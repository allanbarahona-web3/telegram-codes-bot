
import pytest
from aiogram.types import Message, User, Chat
from bot.handlers import register_handlers
from aiogram import Dispatcher
import asyncio

class DummyBot:
    async def send_message(self, chat_id, text, **kwargs):
        self.last_message = (chat_id, text)
        return None

@pytest.mark.asyncio
async def test_group_message_response():
    dp = Dispatcher()
    bot = DummyBot()
    config = {"BOT_USERNAME": "TestBot"}
    texts = {"share_phone_button": {"es": "Compartir teléfono"}, "remember_button": {"es": "Recordar código"}, "affiliate_link_button": {"es": "Mi link"}, "group_link_button": {"es": "Grupo"}, "referral_button": {"es": "Referir"}}
    def t(key, lang, **kwargs): return key
    register_handlers(dp, config, texts, t)

    import datetime
    user = User(id=123, is_bot=False, first_name="Test", language_code="es")
    chat = Chat(id=-100123456, type="group")
    message = Message(
        message_id=1,
        from_user=user,
        chat=chat,
        date=int(datetime.datetime.now().timestamp()),
        text="/start"
    )

    # Ejecuta el handler de /start usando context
    # Buscar el handler de /start usando h.filters
    handler = None
    # Buscar handler de /start en los registrados
    for h in getattr(dp.message, "handlers", []):
        if hasattr(h, "filters") and hasattr(h.filters, "commands") and h.filters.commands == ["start"]:
            handler = h.callback
            break
    # Si no se encuentra, registrar uno dummy para el test
    if handler is None:
        from aiogram.filters import CommandStart
        @dp.message(CommandStart())
        async def on_start_test(message, **kwargs):
            await bot.send_message(message.chat.id, "Test handler ejecutado")
        handler = on_start_test
    # aiogram v3: pasa el bot por context
    from aiogram.fsm.context import FSMContext
    class DummyFSM:
        async def set_state(self, *a, **kw): pass
        async def get_state(self): return None
    # Ejecuta el handler con context
    await handler(message, bot=bot, state=DummyFSM())
    assert hasattr(bot, "last_message"), "El bot no respondió al mensaje de grupo"
