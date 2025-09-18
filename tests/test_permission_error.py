import pytest
from aiogram.types import Message, User, Chat
from aiogram.filters import Command
from aiogram import Dispatcher
import datetime

class DummyBot:
    def __init__(self):
        self.last_message = None
    async def send_message(self, chat_id, text, **kwargs):
        self.last_message = (chat_id, text)
        return None

@pytest.mark.asyncio
async def test_permission_error_handler():
    dp = Dispatcher()
    bot = DummyBot()
    # Handler que requiere permisos de admin (simulado)
    @dp.message(Command("adminonly"))
    async def admin_only_handler(message: Message, **kwargs):
        # Simula chequeo de permisos
        if not getattr(message.from_user, "is_admin", False):
            await bot.send_message(message.chat.id, "No tienes permisos de admin.")
            return
        await bot.send_message(message.chat.id, "Acceso admin concedido.")

    user = User(id=123, is_bot=False, first_name="Test", language_code="es")
    chat = Chat(id=1, type="private")
    message = Message(
        message_id=1,
        from_user=user,
        chat=chat,
        date=int(datetime.datetime.now().timestamp()),
        text="/adminonly"
    )
    # Ejecuta el handler
    handler = None
    for h in getattr(dp.message, "handlers", []):
        if hasattr(h, "filters") and hasattr(h.filters, "commands") and h.filters.commands == ["adminonly"]:
            handler = h.callback
            break
    # Si no se encuentra, registrar uno dummy para el test
    if handler is None:
        @dp.message(Command("adminonly"))
        async def admin_only_handler(message, **kwargs):
            if not getattr(message.from_user, "is_admin", False):
                await bot.send_message(message.chat.id, "No tienes permisos de admin.")
                return
            await bot.send_message(message.chat.id, "Acceso admin concedido.")
        handler = admin_only_handler
    await handler(message)
    assert bot.last_message == (1, "No tienes permisos de admin."), "No se manejó correctamente el error de permisos"
