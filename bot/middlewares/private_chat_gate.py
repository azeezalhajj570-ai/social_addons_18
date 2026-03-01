from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aiogram import BaseMiddleware, Bot, types
from aiogram.enums import ChatType
from loguru import logger

from bot.core.config import settings
from bot.services import moderation
from bot.utils.telegram import is_member_of_chat

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from aiogram.types import CallbackQuery, Message, TelegramObject, User
    from sqlalchemy.ext.asyncio import AsyncSession


class PrivateChatGateMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = getattr(event, "from_user", None)
        if not user:
            return await handler(event, data)

        if settings.OWNER_ID and user.id == settings.OWNER_ID:
            return await handler(event, data)

        chat = getattr(event, "chat", None)
        if chat is None:
            message: Message | None = getattr(event, "message", None)
            chat = message.chat if message else None
        if chat is None or chat.type != ChatType.PRIVATE:
            return await handler(event, data)

        session: AsyncSession | None = data.get("session")
        if session is None:
            return await handler(event, data)
        bot: Bot = data["bot"]

        gates = await moderation.list_enabled_participation_gates_global(session)
        if not gates:
            return await handler(event, data)

        missing: list[tuple[str, str]] = []
        for gate in gates:
            try:
                joined = await is_member_of_chat(bot, gate.gate_group_id, user.id)
            except Exception as exc:
                logger.warning(
                    "private gate membership check failed user={} gate={} err={}",
                    user.id,
                    gate.gate_group_id,
                    exc,
                )
                joined = False
            if not joined:
                missing.append((gate.gate_title, gate.join_url))

        if not missing:
            return await handler(event, data)

        logger.info(
            "private gate blocked user={} missing_gates={}",
            user.id,
            [title for title, _ in missing],
        )
        await self._send_gate_prompt(event, bot, chat.id, missing)
        return None

    async def _send_gate_prompt(
        self,
        event: TelegramObject,
        bot: Bot,
        user_id: int,
        missing: list[tuple[str, str]],
    ) -> None:
        buttons = [[types.InlineKeyboardButton(text=title[:32], url=url)] for title, url in missing]
        text = "لا يمكنك استخدام البوت في الخاص قبل الانضمام إلى المجموعات المطلوبة:"
        message: Message | None = getattr(event, "message", None)
        callback: CallbackQuery | None = getattr(event, "callback_query", None)
        if message is not None:
            await message.answer(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
            return
        if callback is not None and callback.message is not None:
            await callback.message.answer(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
            return
        await bot.send_message(user_id, text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
