from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    ForceReply,
)
from services.db_service import (
    get_existing_code_by_user,
    upsert_user,
    get_user_points,
    compute_balances,
    create_withdraw_request,
    add_points,
)
from services.referral_service import assign_or_get_code, register_referral
from utils.helpers import e164, country_code_from_phone, get_lang
import logging
import re

user_requested_withdraw = {}

# UI Helper Functions
def build_affiliate_link_for_code(code: str, bot_username: str) -> str:
    return f"https://t.me/{bot_username}?start={code}"

def payout_methods_kb(lang: str):
    # Por defecto solo PayPal y Binance Pay
    methods = [
        [InlineKeyboardButton(text="PayPal 💵", callback_data="pm:Paypal")],
        [InlineKeyboardButton(text="Binance Pay ID 🚀", callback_data="pm:BinancePay")],
    ]
    # Aquí puedes agregar lógica para añadir métodos según país/usuario
    return InlineKeyboardMarkup(inline_keyboard=methods)

def register_handlers(dp: Dispatcher, config, texts, t):
    from services import db_service as db_repo
    import json

    BOT_USERNAME = config["BOT_USERNAME"]

    # --- START: Inline button handlers ---
    @dp.callback_query(lambda c: c.data == "remember_code")
    async def cb_remember_code(callback: types.CallbackQuery):
        lang = get_lang(callback.from_user)
        code = await get_existing_code_by_user(callback.from_user.id)
        if code:
            await callback.message.answer(f"{t('mycode_has', lang)} {code}")
        else:
            await callback.message.answer(t("mycode_missing", lang))
        await callback.answer()

    @dp.callback_query(lambda c: c.data == "get_affiliate_link")
    async def cb_get_affiliate_link(callback: types.CallbackQuery):
        lang = get_lang(callback.from_user)
        code = await get_existing_code_by_user(callback.from_user.id)
        if not code:
            await callback.message.answer(t("mycode_missing", lang))
            await callback.answer()
            return
        aff = build_affiliate_link_for_code(code, config["BOT_USERNAME"])
        await callback.message.answer(t("your_affiliate_link", lang, link=aff))
        await callback.answer()

    @dp.callback_query(lambda c: c.data == "get_group_link")
    async def cb_get_group_link(callback: types.CallbackQuery):
        lang = get_lang(callback.from_user)
        campaign = await db_repo.get_active_campaign_for_user(callback.from_user.id)
        if not campaign or not campaign.get("group_chat_id"):
            await callback.message.answer(t("group_missing_env", lang))
            await callback.answer()
            return
        group_chat_id = campaign["group_chat_id"]
        try:
            invite = await callback.bot.create_chat_invite_link(
                chat_id=group_chat_id,
                name=f"one-use-{callback.from_user.id}",
                expire_date=None,
            )
            link = invite.invite_link
        except Exception:
            link = None
        if link:
            await callback.message.answer(t("group_access", lang, link=link))
        else:
            await callback.message.answer(t("group_invite_fail_short", lang))
        await callback.answer()
    # --- END: Inline button handlers ---

    # --- START: Métodos de pago y retiro ---
    @dp.message(
        F.reply_to_message,
        F.reply_to_message.text.contains("monto disponible para retirar"),
    )
    async def process_withdraw_amount(message: Message):
        lang = get_lang(message.from_user)
        campaign = await db_repo.get_active_campaign_for_user(message.from_user.id)
        if not campaign:
            await message.answer(t("error", lang, err="No campaign found."))
            return
        commission_cents = campaign.get("commission_per_approved_cents", 0)
        approved, gross, paid, pending = await compute_balances(
            message.from_user.id,
            campaign_id=campaign["id"],
            commission_per_approved_cents=commission_cents,
        )
        available = max(0, gross - paid - pending)
        min_withdraw_cents = campaign.get("min_withdraw_cents", 0)
        currency = campaign.get("currency", "$")

        def fmt(cents):
            sign = "-" if cents < 0 else ""
            cents = abs(int(cents))
            major = cents // 100
            minor = cents % 100
            return f"{sign}{currency} {major}.{minor:02d}"

        amount_text = message.text.strip().replace(",", ".")
        try:
            if "." in amount_text:
                requested_cents = int(round(float(amount_text) * 100))
            else:
                requested_cents = int(amount_text) * 100
        except Exception:
            await message.answer(t("invalid_amount", lang))
            return
        if requested_cents < min_withdraw_cents:
            min_amt = fmt(min_withdraw_cents)
            await message.answer(
                f"❌ El retiro mínimo es {min_amt}.\nMinimum withdrawal is {min_amt}."
            )
            await message.answer(
                f"💸 Tu monto disponible para retirar es {fmt(available)}.\n\n¿Cuánto deseas retirar? Escribe el monto como respuesta a este mensaje.",
                reply_markup=ForceReply(),
            )
            return
        if requested_cents > available:
            await message.answer(
                f"❌ El monto solicitado ({fmt(requested_cents)}) excede tu saldo disponible ({fmt(available)}). Por favor ingresa un monto válido."
            )
            await message.answer(
                f"💸 Tu monto disponible para retirar es {fmt(available)}.\n\n¿Cuánto deseas retirar? Escribe el monto como respuesta a este mensaje.",
                reply_markup=ForceReply(),
            )
            return
        if requested_cents <= 0:
            await message.answer(t("invalid_amount", lang))
            await message.answer(
                f"💸 Tu monto disponible para retirar es {fmt(available)}.\n\n¿Cuánto deseas retirar? Escribe el monto como respuesta a este mensaje.",
                reply_markup=ForceReply(),
            )
            return
        # Mostrar monto y opciones de pago
        user_requested_withdraw[message.from_user.id] = requested_cents
        await message.answer(
            f"¿Cómo quieres recibir tu pago de {fmt(requested_cents)}?",
            reply_markup=payout_methods_kb(lang),
        )

    @dp.callback_query(lambda c: c.data.startswith("pm:"))
    async def cb_select_payout_method(callback: types.CallbackQuery):
        lang = get_lang(callback.from_user)
        campaign = await db_repo.get_active_campaign_for_user(callback.from_user.id)
        if not campaign:
            await callback.answer(
                t("error", lang, err="No campaign found."), show_alert=True
            )
            return
        commission_cents = campaign.get("commission_per_approved_cents", 0)
        approved, gross, paid, pending = await compute_balances(
            callback.from_user.id,
            campaign_id=campaign["id"],
            commission_per_approved_cents=commission_cents,
        )
        available = max(0, gross - paid - pending)
        min_withdraw_cents = campaign.get("min_withdraw_cents", 0)
        requested_cents = available
        if requested_cents < min_withdraw_cents or requested_cents <= 0:
            await callback.answer(t("insufficient_funds", lang), show_alert=True)
            return
        method_name = callback.data[3:]
        # Buscar método existente para el usuario y tipo
        method = await db_repo.get_default_method(callback.from_user.id, method_name)
        # Si existe, mostrar y pedir confirmación
        if (
            method
            and method.get("method_type") == method_name
            and method.get("details")
        ):
            import json

            details = method["details"]
            if isinstance(details, str):
                details = json.loads(details)
            account = details.get("value", "")
            await callback.message.edit_text(
                f"{t('confirm_account', lang, method=method_name, account=account)}\n\n¿Es correcto este dato?",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="✅ Sí, es correcto",
                                callback_data=f"pmc:{method_name}:yes",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text="✏️ Cambiar",
                                callback_data=f"pmc:{method_name}:edit",
                            )
                        ],
                    ]
                ),
            )
            await callback.answer()
            return
        # Si no existe, pedir el dato
        await callback.message.answer(
            f"Por favor ingresa tu {'correo de PayPal' if method_name=='Paypal' else 'Binance Pay ID'} para recibir el pago:",
            reply_markup=ForceReply(),
        )
        await callback.answer()

    @dp.message(
        F.reply_to_message,
        F.reply_to_message.text.contains("PayPal")
        | F.reply_to_message.text.contains("Binance"),
    )
    async def save_account_and_confirm(message: Message):
        lang = get_lang(message.from_user)
        # Detectar método según el mensaje original
        if "PayPal" in message.reply_to_message.text:
            method_type = "Paypal"
        elif "Binance" in message.reply_to_message.text:
            method_type = "BinancePay"
        else:
            method_type = "Paypal"  # fallback
        account = message.text.strip()
        # Guardar en payout_methods (upsert), details como JSONB
        pool = db_repo.get_pool()
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO payout_methods (user_id, method_type, details, is_default)
                VALUES (%s, %s, %s::jsonb, true)
                ON CONFLICT (user_id, method_type) DO UPDATE SET details=EXCLUDED.details, is_default=true;
            """,
                (message.from_user.id, method_type, '{"value": "%s"}' % account),
            )
            await conn.commit()
        # Pedir confirmación
        await message.answer(
            f"¿Confirmas que este es tu {'correo de PayPal' if method_type=='Paypal' else 'Binance Pay ID'}: {account}?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Sí, es correcto",
                            callback_data=f"pmc:{method_type}:yes",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="✏️ Cambiar", callback_data=f"pmc:{method_type}:edit"
                        )
                    ],
                ]
            ),
        )

    @dp.callback_query(lambda c: c.data.startswith("pmc:"))
    async def cb_confirm_account(callback: types.CallbackQuery):
        lang = get_lang(callback.from_user)
        parts = callback.data.split(":")
        method_name = parts[1]
        action = parts[2]
        if action == "yes":
            campaign = await db_repo.get_active_campaign_for_user(callback.from_user.id)
            commission_cents = campaign.get("commission_per_approved_cents", 0)
            approved, gross, paid, pending = await compute_balances(
                callback.from_user.id,
                campaign_id=campaign["id"],
                commission_per_approved_cents=commission_cents,
            )
            available = max(0, gross - paid - pending)
            min_withdraw_cents = campaign.get("min_withdraw_cents", 0)
            requested_cents = user_requested_withdraw.get(callback.from_user.id)
            if not requested_cents:
                requested_cents = available
            if requested_cents <= 0 or requested_cents < min_withdraw_cents:
                await callback.message.edit_text(t("insufficient_funds", lang))
                await callback.answer(t("insufficient_funds", lang), show_alert=True)
                return
            # Buscar método por usuario y tipo
            method = await db_repo.get_default_method(callback.from_user.id, method_name)
            method_id = method["id"] if method else 1
            # Obtener el dato actual del método de pago
            import json
            details = method["details"]
            if isinstance(details, str):
                details = json.loads(details)
            account = details.get("value", "")
            await create_withdraw_request(
                callback.from_user.id,
                requested_cents,
                method_id,
                campaign_id=campaign["id"],
                account=account  # <-- aquí se guarda el dato exacto usado
            )
            # Descontar puntos equivalentes
            if commission_cents > 0:
                points_to_deduct = int(requested_cents // commission_cents)
                if points_to_deduct > 0:
                    await add_points(
                        callback.from_user.id,
                        -points_to_deduct,
                        "withdrawal",
                        campaign_id=campaign["id"],
                    )
            # Limpia el monto solicitado
            user_requested_withdraw.pop(callback.from_user.id, None)
            await callback.message.edit_text(
                t("withdraw_created", lang, amount=f"{requested_cents/100:.2f}")
            )
            await callback.answer(t("withdraw_created", lang), show_alert=True)
        elif action == "edit":
            await callback.message.answer(
                f"Por favor ingresa tu {'correo de PayPal' if method_name=='Paypal' else 'Binance Pay ID'} para recibir el pago:",
                reply_markup=ForceReply(),
            )
            await callback.answer()
    # --- END: Métodos de pago y retiro ---

    @dp.message(CommandStart())
    async def on_start(message: Message):
        lang = get_lang(message.from_user)
        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text="🔑 Remember my code", callback_data="remember_code"
                    )
                ],
                [
                    types.InlineKeyboardButton(
                        text="🔗 Get my affiliate link",
                        callback_data="get_affiliate_link",
                    )
                ],
                [
                    types.InlineKeyboardButton(
                        text="🟢 Get group link", callback_data="get_group_link"
                    )
                ],
            ]
        )
        await message.answer(t("start_mobile_only", lang), reply_markup=keyboard)

    @dp.message(Command("help"))
    async def help_cmd(message: Message):
        lang = get_lang(message.from_user)
        await message.answer(t("help", lang))

    @dp.message(Command("mypoints"))
    @dp.message(Command("mispuntos"))
    async def mypoints_cmd(message: Message):
        lang = get_lang(message.from_user)
        pts = await get_user_points(message.from_user.id)
        await message.answer(f"🏅 {t('your_points', lang)}: {pts}")

    @dp.message(Command("balance"))
    @dp.message(Command("misganancias"))
    async def balance_cmd(message: Message):
        lang = get_lang(message.from_user)
        campaign = await db_repo.get_active_campaign_for_user(message.from_user.id)
        if not campaign:
            await message.answer(t("error", lang, err="No campaign found."))
            return
        commission_cents = campaign.get("commission_per_approved_cents", 0)
        currency = campaign.get("currency", "$")
        approved, gross, paid, pending = await compute_balances(
            message.from_user.id,
            campaign_id=campaign["id"],
            commission_per_approved_cents=commission_cents,
        )
        available = max(0, gross - paid - pending)
        if approved == 0 and gross == 0:
            await message.answer(t("no_balance", lang))
            return

        def fmt(cents):
            sign = "-" if cents < 0 else ""
            cents = abs(int(cents))
            major = cents // 100
            minor = cents % 100
            return f"{sign}{currency} {major}.{minor:02d}"

        msg = [t("balance_header", lang)]
        msg.append(
            t(
                "balance_body",
                lang,
                approved=approved,
                commission=fmt(commission_cents),
                gross=fmt(gross),
                paid=fmt(paid),
                pending=fmt(pending),
                available=fmt(available),
            )
        )
        await message.answer("\n".join(msg))

    @dp.message(Command("withdraw"))
    @dp.message(Command("cobrar"))
    async def withdraw_cmd(message: Message):
        lang = get_lang(message.from_user)
        campaign = await db_repo.get_active_campaign_for_user(message.from_user.id)
        if not campaign:
            await message.answer(t("error", lang, err="No campaign found."))
            return
        commission_cents = campaign.get("commission_per_approved_cents", 0)
        approved, gross, paid, pending = await compute_balances(
            message.from_user.id,
            campaign_id=campaign["id"],
            commission_per_approved_cents=commission_cents,
        )
        available = max(0, gross - paid - pending)
        min_withdraw_cents = campaign.get("min_withdraw_cents", 0)
        currency = campaign.get("currency", "$")
        args = message.text.split(maxsplit=1)
        requested_cents = None

        def fmt(cents):
            sign = "-" if cents < 0 else ""
            cents = abs(int(cents))
            major = cents // 100
            minor = cents % 100
            return f"{sign}{currency} {major}.{minor:02d}"

        if available <= 0:
            await message.answer(t("insufficient_funds", lang))
            return
        if len(args) == 1:
            await message.answer(
                f"💸 Tu monto disponible para retirar es {fmt(available)}.\n\n¿Cuánto deseas retirar? Escribe el monto como respuesta a este mensaje.",
                reply_markup=ForceReply(),
            )
            return
        if len(args) == 2:
            amount_text = args[1].strip().replace(",", ".")
            try:
                if "." in amount_text:
                    requested_cents = int(round(float(amount_text) * 100))
                else:
                    requested_cents = int(amount_text) * 100
            except Exception:
                await message.answer(t("invalid_amount", lang))
                return
        if requested_cents is None:
            requested_cents = available
        if requested_cents < min_withdraw_cents:
            min_amt = fmt(min_withdraw_cents)
            await message.answer(
                f"❌ El retiro mínimo es {min_amt}.\nMinimum withdrawal is {min_amt}."
            )
            return
        if requested_cents <= 0 or requested_cents > available:
            await message.answer(t("insufficient_funds", lang))
            return
        user_requested_withdraw[message.from_user.id] = requested_cents
        # Mostrar monto y opciones de pago
        await message.answer(
            f"¿Cómo quieres recibir tu pago de {fmt(requested_cents)}?",
            reply_markup=payout_methods_kb(lang),
        )
        # Guardar en contexto de usuario el monto solicitado para usarlo al seleccionar método
        # (esto requiere FSM o almacenamiento temporal, aquí solo se deja el comentario)

    @dp.message(Command("mycode"))
    @dp.message(Command("micodigo"))
    async def cmd_micodigo(message: Message):
        lang = get_lang(message.from_user)
        code = await get_existing_code_by_user(message.from_user.id)
        if code:
            await message.answer(f"{t('mycode_has', lang)} {code}")
        else:
            await message.answer(t("mycode_missing", lang))

    @dp.message(Command("mylink"))
    @dp.message(Command("milink"))
    async def mylink_cmd(message: Message):
        lang = get_lang(message.from_user)
        code = await get_existing_code_by_user(message.from_user.id)
        if not code:
            await message.answer(t("mycode_missing", lang))
            return
        aff = build_affiliate_link_for_code(code, BOT_USERNAME)
        await message.answer(t("your_affiliate_link", lang, link=aff))

    @dp.message(Command("group"))
    @dp.message(Command("grupo"))
    async def cmd_group(message: Message):
        lang = get_lang(message.from_user)
        campaign = await db_repo.get_active_campaign_for_user(message.from_user.id)
        if not campaign or not campaign.get("group_chat_id"):
            await message.answer(t("group_missing_env", lang))
            return
        group_chat_id = campaign["group_chat_id"]
        await message.answer(t("group_access", lang, link="https://t.me/+dummy"))

    @dp.message(Command("id"))
    async def id_cmd(message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id
        chat_type = message.chat.type
        text = f"Chat ID: <code>{chat_id}</code>\nUser ID: <code>{user_id}</code>\nChat type: <code>{chat_type}</code>"
        await message.answer(text, parse_mode="HTML")

    # --- Fallback handler ---
    @dp.message()
    async def fallback_handler(message: Message):
        lang = get_lang(message.from_user)
        keyboard = types.ReplyKeyboardMarkup(
            keyboard=[
                [
                    types.KeyboardButton(text="/mypoints"),
                    types.KeyboardButton(text="/balance"),
                ],
                [
                    types.KeyboardButton(text="/withdraw"),
                    types.KeyboardButton(text="/help"),
                ],
            ],
            resize_keyboard=True,
        )
        await message.answer(
            "No entendí eso 🤔. Por favor, usa los botones para continuar.",
            reply_markup=keyboard,
        )

# This module will contain all Telegram bot handlers and UI logic.
# Move aiogram handlers and UI helpers from telegram_referrals_bot.py here.
