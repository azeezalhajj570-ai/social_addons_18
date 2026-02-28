from __future__ import annotations

from aiogram import Bot
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.types import Message


def is_group_chat(message: Message) -> bool:
    return message.chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}


async def is_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    return member.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}


async def bot_can_delete(bot: Bot, chat_id: int) -> bool:
    member = await bot.get_chat_member(chat_id=chat_id, user_id=bot.id)
    if member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
        return False
    return bool(getattr(member, "can_delete_messages", True))


async def bot_can_ban(bot: Bot, chat_id: int) -> bool:
    member = await bot.get_chat_member(chat_id=chat_id, user_id=bot.id)
    if member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
        return False
    return bool(getattr(member, "can_restrict_members", True))


async def is_member_of_chat(bot: Bot, chat_id: int, user_id: int) -> bool:
    member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    return member.status in {
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.RESTRICTED,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR,
    }
