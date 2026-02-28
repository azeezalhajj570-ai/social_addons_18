from __future__ import annotations

import re
from collections.abc import Callable
from functools import wraps
from typing import Any

from aiogram import Bot, types
from aiogram.enums import ChatType
from sqlalchemy.ext.asyncio import AsyncSession

from bot.core.config import settings
from bot.services import moderation
from bot.utils.telegram import is_admin


def is_owner(user_id: int | None) -> bool:
    return bool(settings.OWNER_ID and user_id and user_id == settings.OWNER_ID)


def extract_group_username(token: str) -> str:
    value = token.strip()
    match = re.search(r"(?:https?://)?t\.me/([A-Za-z0-9_]{4,})", value, re.IGNORECASE)
    if match:
        return f"@{match.group(1)}"
    return value if value.startswith("@") else f"@{value}"


async def resolve_target_group(message: types.Message, bot: Bot, args: list[str]) -> tuple[int, list[str]] | None:
    if message.chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}:
        if not message.from_user:
            return None
        if not (await is_admin(bot, message.chat.id, message.from_user.id) or is_owner(message.from_user.id)):
            await message.answer("هذا الأمر للمشرفين فقط.")
            return None
        return message.chat.id, args

    if message.chat.type == ChatType.PRIVATE:
        if not args:
            await message.answer("المجموعة المستهدفة غير محددة. استخدم @group_username كأول وسيط.")
            return None
        username = extract_group_username(args[0])
        try:
            chat = await bot.get_chat(username)
        except Exception:
            await message.answer("تعذر العثور على المجموعة أو لا يمكن إدارتها.")
            return None
        if chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
            await message.answer("الهدف يجب أن يكون مجموعة أو سوبرجروب.")
            return None
        if not message.from_user:
            return None
        if not (await is_admin(bot, chat.id, message.from_user.id) or is_owner(message.from_user.id)):
            await message.answer("أنت لست مشرفًا في تلك المجموعة.")
            return None
        return chat.id, args[1:]

    await message.answer("نوع الدردشة غير مدعوم.")
    return None


async def resolve_gate_group(bot: Bot, token: str) -> tuple[int, str, str] | None:
    username = extract_group_username(token)
    try:
        chat = await bot.get_chat(username)
    except Exception:
        return None
    if chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        return None
    title = chat.title or str(chat.id)
    join_url = f"https://t.me/{chat.username}" if chat.username else ""
    return chat.id, title, join_url


def admin_guard(func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(func)
    async def wrapped(message: types.Message, bot: Bot, session: AsyncSession, *args: Any, **kwargs: Any) -> None:
        if not message.from_user:
            return
        if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
            await message.answer("استخدم هذا الأمر داخل مجموعة.")
            return
        if not (await is_admin(bot, message.chat.id, message.from_user.id) or is_owner(message.from_user.id)):
            await message.answer("هذا الأمر للمشرفين فقط.")
            return
        await moderation.ensure_group(session, message.chat.id)
        await func(message, bot, session, *args, **kwargs)

    return wrapped
