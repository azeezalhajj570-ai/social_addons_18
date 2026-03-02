from __future__ import annotations

import contextlib
import html
import re
import time
from collections import defaultdict, deque

from aiogram import Bot, F, Router, types
from aiogram.enums import ChatType, ParseMode
from aiogram.types import ChatPermissions
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.core.config import settings
from bot.services import ai_moderation
from bot.services import moderation
from bot.utils.telegram import bot_can_ban, bot_can_delete, is_admin, is_member_of_chat

router = Router(name="group_manager_automod")

SPAM_BUCKETS: dict[tuple[int, int], deque[float]] = defaultdict(deque)
FLOOD_BUCKETS: dict[tuple[int, int], deque[float]] = defaultdict(deque)


async def _send_filter_response(message: types.Message, item: moderation.SavedFilter) -> None:
    if item.text:
        await message.answer(item.text)
    if item.photo:
        await message.answer_photo(item.photo, caption=item.caption)
    if item.document:
        await message.answer_document(item.document, caption=item.caption)
    if item.sticker:
        await message.answer_sticker(item.sticker)
    if item.animation:
        await message.answer_animation(item.animation, caption=item.caption)
    if item.video:
        await message.answer_video(item.video, caption=item.caption)
    if item.voice:
        await message.answer_voice(item.voice, caption=item.caption)
    if item.audio:
        await message.answer_audio(item.audio, caption=item.caption)


def _hit_bucket(bucket: dict[tuple[int, int], deque[float]], key: tuple[int, int], limit: int, window: int) -> bool:
    now = time.time()
    q = bucket[key]
    q.append(now)
    while q and now - q[0] > window:
        q.popleft()
    return len(q) > limit


async def _missing_gates(
    bot: Bot,
    session: AsyncSession,
    chat_id: int,
    user_id: int,
) -> list[tuple[str, str]]:
    missing: list[tuple[str, str]] = []
    gates = [gate for gate in await moderation.list_participation_gates(session, chat_id) if gate.enabled]
    if not gates:
        return missing

    for gate in gates:
        try:
            in_gate = await is_member_of_chat(bot, gate.gate_group_id, user_id)
        except Exception as exc:
            logger.warning(
                "gate membership check failed chat={} gate={} user={} err={}",
                chat_id,
                gate.gate_group_id,
                user_id,
                exc,
            )
            in_gate = False
        if not in_gate:
            missing.append((gate.gate_title, gate.join_url))
    return missing


async def _send_gate_prompt(chat_id: int, bot: Bot, missing: list[tuple[str, str]]) -> None:
    buttons = [[types.InlineKeyboardButton(text=title[:32], url=url)] for title, url in missing]
    await bot.send_message(
        chat_id,
        "يرجى الانضمام إلى المجموعات المطلوبة قبل إرسال الرسائل هنا.",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}) & F.new_chat_members)
async def anti_bots(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    await moderation.ensure_group(session, message.chat.id)
    enabled = await moderation.get_setting(session, message.chat.id, "anti_bots")
    if not enabled or not await bot_can_ban(bot, message.chat.id):
        return
    for member in message.new_chat_members:
        if not member.is_bot:
            continue
        try:
            await bot.ban_chat_member(message.chat.id, member.id)
            logger.info("auto-banned joining bot chat={} user={}", message.chat.id, member.id)
        except Exception as exc:
            logger.warning("anti_bots failed chat={} user={} err={}", message.chat.id, member.id, exc)


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}) & (F.new_chat_members | F.left_chat_member))
async def welcome_goodbye_and_hide_system(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    await moderation.ensure_group(session, message.chat.id)
    meta = await moderation.get_group_meta(session, message.chat.id)
    hide_system = await moderation.get_setting(session, message.chat.id, "hide_system")

    if message.new_chat_members and meta.welcome_message:
        for member in message.new_chat_members:
            text = meta.welcome_message.replace("{user}", member.mention_html())
            await message.answer(text, parse_mode=ParseMode.HTML)

    if message.left_chat_member and meta.goodbye_message:
        text = meta.goodbye_message.replace("{user}", message.left_chat_member.full_name)
        await message.answer(text)

    if hide_system and await bot_can_delete(bot, message.chat.id):
        try:
            await message.delete()
        except Exception:
            pass

    if not message.new_chat_members:
        return

    if not await bot_can_ban(bot, message.chat.id):
        return

    for member in message.new_chat_members:
        if member.is_bot:
            continue
        missing = await _missing_gates(bot, session, message.chat.id, member.id)
        if not missing:
            continue
        try:
            await bot.ban_chat_member(message.chat.id, member.id)
            await bot.unban_chat_member(message.chat.id, member.id, only_if_banned=True)
        except Exception as exc:
            logger.warning("gate kick failed chat={} user={} err={}", message.chat.id, member.id, exc)
            continue
        try:
            await _send_gate_prompt(message.chat.id, bot, missing)
        except Exception:
            pass


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def moderation_pipeline(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    if not message.from_user:
        return

    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = html.escape(message.from_user.full_name)
    text = (message.text or message.caption or "").strip()

    await moderation.ensure_group(session, chat_id)

    if message.from_user.is_bot:
        return

    if await is_admin(bot, chat_id, user_id):
        return

    missing = await _missing_gates(bot, session, chat_id, user_id)
    if missing:
        logger.info(
            "gate enforcement triggered chat={} user={} missing_gates={}",
            chat_id,
            user_id,
            [title for title, _ in missing],
        )
        if await bot_can_delete(bot, chat_id):
            with contextlib.suppress(Exception):
                await message.delete()
        await _send_gate_prompt(chat_id, bot, missing)
        return

    # Filters and anti-abuse should not touch commands.
    if not text or (message.text and message.text.startswith("/")):
        return

    meta = await moderation.get_group_meta(session, chat_id)
    if meta.antispam_limit and meta.antispam_window:
        if _hit_bucket(SPAM_BUCKETS, (chat_id, user_id), meta.antispam_limit, meta.antispam_window):
            warns = await moderation.add_warn(session, chat_id, user_id)
            await message.answer(f"⚠️ تم اكتشاف سبام. التحذيرات: {warns}/{settings.MAX_WARNS}")

    if meta.antiflood_limit and meta.antiflood_window:
        if _hit_bucket(FLOOD_BUCKETS, (chat_id, user_id), meta.antiflood_limit, meta.antiflood_window):
            if await bot_can_ban(bot, chat_id):
                until = int(time.time()) + settings.MUTE_SECONDS
                await bot.restrict_chat_member(chat_id, user_id, permissions=ChatPermissions(can_send_messages=False), until_date=until)
                await message.answer("🌊 تم اكتشاف فلود. تم كتم المستخدم.")

    saved_filters = await moderation.list_filters(session, chat_id)
    lowered = text.lower()
    for item in saved_filters:
        if item.keyword in lowered:
            decision = await ai_moderation.evaluate_filter_hit(
                message_text=text,
                matched_keyword=item.keyword,
                chat_id=chat_id,
                user_id=user_id,
            )
            if decision.should_delete and await bot_can_delete(bot, chat_id):
                with contextlib.suppress(Exception):
                    await message.delete()
                logger.info(
                    "ai moderation deleted message chat={} user={} keyword={} confidence={} category={} reason={}",
                    chat_id,
                    user_id,
                    item.keyword,
                    decision.confidence,
                    decision.category,
                    decision.reason,
                )
                return
            await _send_filter_response(message, item)
            break

    routes = await moderation.list_link_routes(session, chat_id)
    for route in routes:
        if not route.enabled or route.keyword not in lowered:
            continue
        allowed = True
        if route.gate_group_id is not None:
            try:
                allowed = await is_member_of_chat(bot, route.gate_group_id, user_id)
            except Exception:
                allowed = False
        if allowed:
            await message.answer(route.destination, disable_web_page_preview=True)
            break

    for rule in await moderation.list_dynamic_rules(session, chat_id):
        if not rule.enabled:
            continue
        try:
            matched = bool(re.search(rule.pattern, text, re.IGNORECASE))
        except re.error:
            logger.warning("Invalid regex rule id={} chat={}", rule.id, chat_id)
            continue
        if not matched:
            continue
        if await bot_can_delete(bot, chat_id):
            with contextlib.suppress(Exception):
                await message.delete()
        if await bot_can_ban(bot, chat_id):
            temp_ban = await moderation.get_setting(session, chat_id, "temp_ban_before_remove")
            seconds = (
                await moderation.get_int_setting(session, chat_id, "temp_ban_seconds", 600)
                if temp_ban
                else settings.MUTE_SECONDS
            )
            mute_seconds = max(60, seconds)
            until = int(time.time()) + mute_seconds
            await bot.restrict_chat_member(
                chat_id,
                user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until,
            )
            await bot.send_message(
                chat_id,
                f"{user_name} تم حذف الرسالة وكتمه لمدة {mute_seconds} ثانية.",
                parse_mode=ParseMode.HTML,
            )
        return

    anti_links = await moderation.get_setting(session, chat_id, "anti_links")
    if not anti_links or not settings.link_pattern.search(text):
        return
    if not await bot_can_delete(bot, chat_id):
        return

    await message.delete()
    warns = await moderation.add_warn(session, chat_id, user_id)

    if warns < settings.MAX_WARNS:
        warn_in_dm = await moderation.get_setting(session, chat_id, "warn_in_dm")
        warn_in_group = await moderation.get_setting(session, chat_id, "warn_in_group")
        warn_text = f"الروابط غير مسموحة. التحذيرات: {warns}/{settings.MAX_WARNS}"
        if warn_in_dm:
            try:
                await bot.send_message(user_id, warn_text)
            except Exception:
                warn_in_group = True
        if warn_in_group:
            await bot.send_message(chat_id, f"{user_name} {warn_text}", parse_mode=ParseMode.HTML)
        return

    if not await bot_can_ban(bot, chat_id):
        await bot.send_message(chat_id, f"المستخدم وصل للحد الأقصى من التحذيرات: {warns}/{settings.MAX_WARNS}")
        return

    temp_ban = await moderation.get_setting(session, chat_id, "temp_ban_before_remove")
    seconds = await moderation.get_int_setting(session, chat_id, "temp_ban_seconds", 600) if temp_ban else settings.MUTE_SECONDS
    until = int(time.time()) + max(60, seconds)
    await bot.restrict_chat_member(chat_id, user_id, permissions=ChatPermissions(can_send_messages=False), until_date=until)
    await bot.send_message(chat_id, f"{user_name} تم كتمه لمدة {max(60, seconds)} ثانية.", parse_mode=ParseMode.HTML)
