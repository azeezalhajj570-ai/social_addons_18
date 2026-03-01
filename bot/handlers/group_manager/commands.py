from __future__ import annotations

import html
import random
import time

from aiogram import Bot, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import ChatPermissions
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.core.config import settings
from bot.services import moderation
from bot.utils.telegram import bot_can_ban, bot_can_delete, is_member_of_chat

from .helpers import admin_guard, is_owner, resolve_gate_group, resolve_target_group

router = Router(name="group_manager_commands")


def _cmd_args(message: types.Message) -> list[str]:
    return message.text.split()[1:] if message.text else []


@router.message(Command("settings"))
async def settings_cmd(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    resolved = await resolve_target_group(message, bot, _cmd_args(message))
    if resolved is None:
        return
    chat_id, _ = resolved
    await moderation.ensure_group(session, chat_id)
    meta = await moderation.get_group_meta(session, chat_id)

    anti_links = await moderation.get_setting(session, chat_id, "anti_links")
    anti_bots = await moderation.get_setting(session, chat_id, "anti_bots")
    hide_system = await moderation.get_setting(session, chat_id, "hide_system")
    warn_in_dm = await moderation.get_setting(session, chat_id, "warn_in_dm")
    warn_in_group = await moderation.get_setting(session, chat_id, "warn_in_group")
    temp_ban = await moderation.get_setting(session, chat_id, "temp_ban_before_remove")
    temp_ban_seconds = await moderation.get_int_setting(session, chat_id, "temp_ban_seconds", 600)

    await message.answer(
        "إعدادات المجموعة:\n"
        f"- anti_links: {anti_links}\n"
        f"- anti_bots: {anti_bots}\n"
        f"- hide_system: {hide_system}\n"
        f"- warn_in_dm: {warn_in_dm}\n"
        f"- warn_in_group: {warn_in_group}\n"
        f"- temp_ban_before_remove: {temp_ban}\n"
        f"- temp_ban_seconds: {temp_ban_seconds}\n"
        f"- antispam: {meta.antispam_limit}/{meta.antispam_window}\n"
        f"- antiflood: {meta.antiflood_limit}/{meta.antiflood_window}\n\n"
        "أوامر التبديل:\n"
        "/toggle_anti_links /toggle_anti_bots /toggle_hide_system\n"
        "/toggle_warn_in_dm /toggle_warn_in_group /toggle_temp_ban",
    )


async def _toggle(message: types.Message, bot: Bot, session: AsyncSession, key: str) -> None:
    resolved = await resolve_target_group(message, bot, _cmd_args(message))
    if resolved is None:
        return
    chat_id, _ = resolved
    value = await moderation.toggle_setting(session, chat_id, key)
    await message.answer(f"{key}: {value}")


@router.message(Command("toggle_anti_links"))
async def toggle_anti_links(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    await _toggle(message, bot, session, "anti_links")


@router.message(Command("toggle_anti_bots"))
async def toggle_anti_bots(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    await _toggle(message, bot, session, "anti_bots")


@router.message(Command("toggle_hide_system"))
async def toggle_hide_system(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    await _toggle(message, bot, session, "hide_system")


@router.message(Command("toggle_warn_in_dm"))
async def toggle_warn_dm(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    await _toggle(message, bot, session, "warn_in_dm")


@router.message(Command("toggle_warn_in_group"))
async def toggle_warn_group(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    await _toggle(message, bot, session, "warn_in_group")


@router.message(Command("toggle_temp_ban"))
async def toggle_temp_ban(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    await _toggle(message, bot, session, "temp_ban_before_remove")


@router.message(Command("set_temp_ban_seconds"))
async def set_temp_ban_seconds(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    resolved = await resolve_target_group(message, bot, _cmd_args(message))
    if resolved is None:
        return
    chat_id, cmd_args = resolved
    if not cmd_args:
        await message.answer("الاستخدام: /set_temp_ban_seconds seconds")
        return
    try:
        seconds = max(60, int(cmd_args[0]))
    except ValueError:
        await message.answer("قيمة الثواني يجب أن تكون رقمًا صحيحًا")
        return
    await moderation.set_int_setting(session, chat_id, "temp_ban_seconds", seconds)
    await message.answer(f"تم تحديث temp_ban_seconds إلى: {seconds}")


@router.message(Command("addrule"))
async def add_rule(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    resolved = await resolve_target_group(message, bot, _cmd_args(message))
    if resolved is None:
        return
    chat_id, cmd_args = resolved
    pattern = " ".join(cmd_args).strip()
    if not pattern:
        await message.answer("الاستخدام: /addrule regex")
        return
    rid = await moderation.add_dynamic_rule(session, chat_id, pattern)
    await message.answer(f"تمت إضافة القاعدة برقم id={rid}")


@router.message(Command("delrule"))
async def del_rule(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    resolved = await resolve_target_group(message, bot, _cmd_args(message))
    if resolved is None:
        return
    chat_id, cmd_args = resolved
    if not cmd_args:
        await message.answer("الاستخدام: /delrule id")
        return
    try:
        rid = int(cmd_args[0])
    except ValueError:
        await message.answer("المعرف id يجب أن يكون رقمًا صحيحًا")
        return
    deleted = await moderation.delete_dynamic_rule(session, chat_id, rid)
    await message.answer("تم حذف القاعدة" if deleted else "القاعدة غير موجودة")


@router.message(Command("listrules"))
async def list_rules(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    resolved = await resolve_target_group(message, bot, _cmd_args(message))
    if resolved is None:
        return
    chat_id, _ = resolved
    rules = await moderation.list_dynamic_rules(session, chat_id)
    if not rules:
        await message.answer("لا توجد قواعد")
        return
    await message.answer("القواعد الديناميكية:\n" + "\n".join(f"{r.id}) `{r.pattern}`" for r in rules), parse_mode=ParseMode.MARKDOWN)


@router.message(Command("addroute"))
async def add_route(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    resolved = await resolve_target_group(message, bot, _cmd_args(message))
    if resolved is None:
        return
    chat_id, cmd_args = resolved
    if len(cmd_args) < 2:
        await message.answer("الاستخدام: /addroute keyword destination [gate_group_id]")
        return
    gate_group_id = None
    if len(cmd_args) > 2:
        try:
            gate_group_id = int(cmd_args[2])
        except ValueError:
            await message.answer("gate_group_id يجب أن يكون رقمًا صحيحًا")
            return
    await moderation.upsert_link_route(session, chat_id, cmd_args[0], cmd_args[1], gate_group_id)
    await message.answer("تم حفظ المسار")


@router.message(Command("delroute"))
async def del_route(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    resolved = await resolve_target_group(message, bot, _cmd_args(message))
    if resolved is None:
        return
    chat_id, cmd_args = resolved
    if not cmd_args:
        await message.answer("الاستخدام: /delroute keyword")
        return
    deleted = await moderation.delete_link_route(session, chat_id, cmd_args[0])
    await message.answer("تم حذف المسار" if deleted else "المسار غير موجود")


@router.message(Command("listroutes"))
async def list_routes(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    resolved = await resolve_target_group(message, bot, _cmd_args(message))
    if resolved is None:
        return
    chat_id, _ = resolved
    routes = await moderation.list_link_routes(session, chat_id)
    if not routes:
        await message.answer("لا توجد مسارات")
        return
    lines = []
    for item in routes:
        suffix = f" gate={item.gate_group_id}" if item.gate_group_id else ""
        lines.append(f"- `{item.keyword}` -> {item.destination}{suffix}")
    await message.answer("المسارات:\n" + "\n".join(lines), parse_mode=ParseMode.MARKDOWN)


@router.message(Command("addgate"))
async def add_gate(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    resolved = await resolve_target_group(message, bot, _cmd_args(message))
    if resolved is None:
        return
    chat_id, cmd_args = resolved
    if not cmd_args:
        await message.answer("الاستخدام: /addgate @required_group_or_link [join_url]")
        return
    gate = await resolve_gate_group(bot, cmd_args[0])
    if gate is None:
        await message.answer("لم يتم العثور على المجموعة المطلوبة")
        return
    gate_group_id, gate_title, auto_join = gate
    join_url = cmd_args[1] if len(cmd_args) > 1 else auto_join
    if not join_url:
        await message.answer("أدخل join_url للمجموعات الخاصة")
        return
    await moderation.upsert_participation_gate(session, chat_id, gate_group_id, gate_title, join_url)
    await message.answer("تم حفظ بوابة المشاركة")


@router.message(Command("delgate"))
async def del_gate(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    resolved = await resolve_target_group(message, bot, _cmd_args(message))
    if resolved is None:
        return
    chat_id, cmd_args = resolved
    if not cmd_args:
        await message.answer("الاستخدام: /delgate gate_group_id")
        return

    gid: int
    try:
        gid = int(cmd_args[0])
    except ValueError:
        gate = await resolve_gate_group(bot, cmd_args[0])
        if gate is None:
            await message.answer("gate_group_id يجب أن يكون رقمًا صحيحًا أو @group/link صحيح")
            return
        gid = gate[0]

    deleted = await moderation.delete_participation_gate(session, chat_id, gid)
    await message.answer("تم حذف البوابة" if deleted else "البوابة غير موجودة")


@router.message(Command("listgates"))
async def list_gates(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    resolved = await resolve_target_group(message, bot, _cmd_args(message))
    if resolved is None:
        return
    chat_id, _ = resolved
    gates = await moderation.list_participation_gates(session, chat_id)
    if not gates:
        await message.answer("لا توجد بوابات مشاركة")
        return
    await message.answer(
        "بوابات المشاركة:\n" + "\n".join(f"- `{g.gate_group_id}` {g.gate_title} -> {g.join_url}" for g in gates),
        parse_mode=ParseMode.MARKDOWN,
    )


@router.message(Command("gatehealth"))
async def gate_health(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    resolved = await resolve_target_group(message, bot, _cmd_args(message))
    if resolved is None:
        return
    chat_id, cmd_args = resolved
    gates = await moderation.list_participation_gates(session, chat_id)
    if not gates:
        await message.answer("لا توجد بوابات مشاركة في هذه المجموعة")
        return

    inspect_user_id = message.from_user.id if message.from_user else 0
    if message.reply_to_message and message.reply_to_message.from_user:
        inspect_user_id = message.reply_to_message.from_user.id
    elif cmd_args:
        try:
            inspect_user_id = int(cmd_args[0])
        except ValueError:
            pass

    can_delete = await bot_can_delete(bot, chat_id)
    can_ban = await bot_can_ban(bot, chat_id)
    lines = [
        f"Gate health for chat `{chat_id}`",
        f"- inspect_user_id: `{inspect_user_id}`",
        f"- bot_can_delete: `{can_delete}`",
        f"- bot_can_ban: `{can_ban}`",
        "- gates:",
    ]
    for gate in gates:
        try:
            member = await bot.get_chat_member(gate.gate_group_id, inspect_user_id)
            joined = await is_member_of_chat(bot, gate.gate_group_id, inspect_user_id)
            status = "joined" if joined else "missing"
            raw_status = getattr(member, "status", "unknown")
            raw_is_member = getattr(member, "is_member", None)
            status = f"{status} (raw_status={raw_status}, is_member={raw_is_member})"
        except Exception as exc:
            status = f"check_error: {type(exc).__name__}"
        lines.append(f"  - `{gate.gate_group_id}` {gate.gate_title} => {status}")

    await message.answer("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


@router.message(Command("addschedule"))
@admin_guard
async def addschedule_cmd(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    del bot
    args = _cmd_args(message)
    if len(args) < 2:
        await message.answer("الاستخدام: /addschedule interval_minutes [target_chat_id] message_text")
        return
    try:
        interval_minutes = max(1, int(args[0]))
    except ValueError:
        await message.answer("interval_minutes يجب أن يكون رقمًا صحيحًا")
        return

    target_chat_id: int | None = None
    message_start_index = 1
    if len(args) >= 3:
        try:
            target_chat_id = int(args[1])
            message_start_index = 2
        except ValueError:
            target_chat_id = message.chat.id
    else:
        target_chat_id = message.chat.id

    schedule_text = " ".join(args[message_start_index:]).strip()
    if not schedule_text:
        await message.answer("نص الرسالة message_text مطلوب")
        return
    schedule_id = await moderation.add_scheduled_message(
        session,
        message.chat.id,
        target_chat_id,
        schedule_text,
        interval_minutes,
    )
    await message.answer(f"تم إنشاء رسالة مجدولة id={schedule_id} إلى الهدف {target_chat_id}")


@router.message(Command("listschedules"))
@admin_guard
async def listschedules_cmd(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    del bot
    schedules = await moderation.list_scheduled_messages(session, message.chat.id)
    if not schedules:
        await message.answer("لا توجد رسائل مجدولة")
        return
    lines = []
    for item in schedules:
        status = "مفعلة" if item.enabled else "معطلة"
        target = item.target_chat_id if item.target_chat_id is not None else item.chat_id
        preview = html.escape(item.text.replace("\n", " ")[:120])
        lines.append(
            f"{item.id}) كل {item.interval_seconds // 60} دقيقة | الهدف={target} | التشغيل القادم={item.next_run_at.isoformat()} | {status}\n"
            f"   {preview}",
        )
    await message.answer("الرسائل المجدولة:\n" + "\n".join(lines))


@router.message(Command("delschedule"))
@admin_guard
async def delschedule_cmd(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    del bot
    args = _cmd_args(message)
    if not args:
        await message.answer("الاستخدام: /delschedule id")
        return
    try:
        schedule_id = int(args[0])
    except ValueError:
        await message.answer("المعرف id يجب أن يكون رقمًا صحيحًا")
        return
    deleted = await moderation.delete_scheduled_message(session, message.chat.id, schedule_id)
    await message.answer("تم حذف الرسالة المجدولة" if deleted else "الجدولة غير موجودة")


@router.message(Command("toggleschedule"))
@admin_guard
async def toggleschedule_cmd(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    del bot
    args = _cmd_args(message)
    if not args:
        await message.answer("الاستخدام: /toggleschedule id")
        return
    try:
        schedule_id = int(args[0])
    except ValueError:
        await message.answer("المعرف id يجب أن يكون رقمًا صحيحًا")
        return
    state = await moderation.toggle_scheduled_message(session, message.chat.id, schedule_id)
    if state is None:
        await message.answer("الجدولة غير موجودة")
        return
    await message.answer(f"الجدولة الآن {'مفعلة' if state else 'معطلة'}")


@router.message(Command("filter"))
@admin_guard
async def add_filter(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    del bot
    args = _cmd_args(message)
    if not args:
        await message.answer("الاستخدام: /filter keyword (بالرد على الرسالة المستهدفة)")
        return
    if not message.reply_to_message:
        await message.answer("قم بالرد على رسالة لحفظها كفلتر")
        return
    src = message.reply_to_message
    await moderation.upsert_filter(
        session,
        message.chat.id,
        args[0],
        text=src.text,
        caption=src.caption,
        photo=src.photo[-1].file_id if src.photo else None,
        document=src.document.file_id if src.document else None,
        sticker=src.sticker.file_id if src.sticker else None,
        animation=src.animation.file_id if src.animation else None,
        video=src.video.file_id if src.video else None,
        voice=src.voice.file_id if src.voice else None,
        audio=src.audio.file_id if src.audio else None,
    )
    await message.answer(f"تم حفظ الفلتر `{args[0].lower()}`", parse_mode=ParseMode.MARKDOWN)


@router.message(Command("stop"))
@admin_guard
async def stop_filter(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    del bot
    args = _cmd_args(message)
    if not args:
        await message.answer("الاستخدام: /stop keyword")
        return
    deleted = await moderation.delete_filter(session, message.chat.id, args[0])
    await message.answer("تم حذف الفلتر" if deleted else "الفلتر غير موجود")


@router.message(Command("filterlist"))
@admin_guard
async def filterlist(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    del bot
    items = await moderation.list_filters(session, message.chat.id)
    if not items:
        await message.answer("لا توجد فلاتر نشطة")
        return
    await message.answer("الفلاتر النشطة:\n" + "\n".join(f"- {f.keyword}" for f in items))


@router.message(Command("warn"))
@admin_guard
async def warn_cmd(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer("رد على رسالة المستخدم")
        return
    user = message.reply_to_message.from_user
    warns = await moderation.add_warn(session, message.chat.id, user.id)
    await message.answer(f"⚠️ {user.mention_html()} تم تحذيره. العدد: {warns}", parse_mode=ParseMode.HTML)
    if warns >= settings.MAX_WARNS and await bot_can_ban(bot, message.chat.id):
        await bot.ban_chat_member(message.chat.id, user.id)
        await message.answer(f"🚫 {user.mention_html()} تم حظره بسبب كثرة التحذيرات", parse_mode=ParseMode.HTML)


@router.message(Command("unwarn"))
@admin_guard
async def unwarn_cmd(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    del bot
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer("رد على رسالة المستخدم")
        return
    user = message.reply_to_message.from_user
    current = await moderation.get_warns(session, message.chat.id, user.id)
    new_count = max(0, current - 1)
    await moderation.set_warns(session, message.chat.id, user.id, new_count)
    await message.answer(f"🔄 تمت إزالة تحذير. الحالي: {new_count}")


@router.message(Command("resetwarns"))
@admin_guard
async def resetwarns_cmd(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    del bot
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer("رد على رسالة المستخدم")
        return
    await moderation.reset_warns(session, message.chat.id, message.reply_to_message.from_user.id)
    await message.answer("تمت إعادة تعيين التحذيرات")


async def _target_user(message: types.Message) -> int | None:
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id
    args = _cmd_args(message)
    if args:
        try:
            return int(args[0])
        except ValueError:
            return None
    return None


@router.message(Command("ban"))
@admin_guard
async def ban_cmd(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    del session
    user_id = await _target_user(message)
    if user_id is None:
        await message.answer("رد على المستخدم أو أدخل user_id")
        return
    if not await bot_can_ban(bot, message.chat.id):
        await message.answer("أحتاج صلاحية الحظر/التقييد")
        return
    await bot.ban_chat_member(message.chat.id, user_id)
    await message.answer(f"🚫 تم حظر: {user_id}")


@router.message(Command("unban"))
@admin_guard
async def unban_cmd(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    del session
    user_id = await _target_user(message)
    if user_id is None:
        await message.answer("أدخل user_id")
        return
    await bot.unban_chat_member(message.chat.id, user_id)
    await message.answer(f"✅ تم فك الحظر: {user_id}")


@router.message(Command("kick"))
@admin_guard
async def kick_cmd(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    del session
    user_id = await _target_user(message)
    if user_id is None:
        await message.answer("رد على المستخدم أو أدخل user_id")
        return
    if not await bot_can_ban(bot, message.chat.id):
        await message.answer("أحتاج صلاحية الحظر/التقييد")
        return
    await bot.ban_chat_member(message.chat.id, user_id)
    await bot.unban_chat_member(message.chat.id, user_id)
    await message.answer(f"👢 تم طرد: {user_id}")


@router.message(Command("mute"))
@admin_guard
async def mute_cmd(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    del session
    user_id = await _target_user(message)
    if user_id is None:
        await message.answer("رد على المستخدم أو أدخل user_id")
        return
    if not await bot_can_ban(bot, message.chat.id):
        await message.answer("أحتاج صلاحية التقييد")
        return
    until = int(time.time()) + settings.MUTE_SECONDS
    await bot.restrict_chat_member(
        message.chat.id,
        user_id,
        permissions=ChatPermissions(can_send_messages=False),
        until_date=until,
    )
    await message.answer(f"🔇 تم كتم: {user_id}")


@router.message(Command("unmute"))
@admin_guard
async def unmute_cmd(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    del session
    user_id = await _target_user(message)
    if user_id is None:
        await message.answer("رد على المستخدم أو أدخل user_id")
        return
    await bot.restrict_chat_member(
        message.chat.id,
        user_id,
        permissions=ChatPermissions(can_send_messages=True, can_send_other_messages=True, can_add_web_page_previews=True),
    )
    await message.answer(f"🔊 تم فك الكتم: {user_id}")


@router.message(Command("promote"))
@admin_guard
async def promote_cmd(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    del session
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer("رد على المستخدم لترقيته")
        return
    user_id = message.reply_to_message.from_user.id
    custom_title = " ".join(_cmd_args(message)) or "مشرف"
    await bot.promote_chat_member(
        message.chat.id,
        user_id,
        can_manage_chat=True,
        can_delete_messages=True,
        can_restrict_members=True,
        can_invite_users=True,
        can_pin_messages=True,
    )
    await bot.set_chat_administrator_custom_title(message.chat.id, user_id, custom_title[:16])
    await message.answer(f"🎖️ تمت ترقية: {user_id}")


@router.message(Command("demote"))
@admin_guard
async def demote_cmd(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    del session
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer("رد على المستخدم لتنزيله")
        return
    user_id = message.reply_to_message.from_user.id
    await bot.promote_chat_member(
        message.chat.id,
        user_id,
        can_manage_chat=False,
        can_delete_messages=False,
        can_restrict_members=False,
        can_invite_users=False,
        can_pin_messages=False,
        can_promote_members=False,
    )
    await message.answer(f"⬇️ تم تنزيل: {user_id}")


@router.message(Command("purge"))
@admin_guard
async def purge_cmd(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    del session
    args = _cmd_args(message)
    if not args:
        await message.answer("الاستخدام: /purge count")
        return
    try:
        count = max(1, min(200, int(args[0])))
    except ValueError:
        await message.answer("count يجب أن يكون رقمًا صحيحًا")
        return
    if not await bot_can_delete(bot, message.chat.id):
        await message.answer("أحتاج صلاحية حذف الرسائل")
        return
    deleted = 0
    start_id = message.reply_to_message.message_id if message.reply_to_message else message.message_id
    for mid in range(start_id, max(0, start_id - count), -1):
        try:
            await bot.delete_message(message.chat.id, mid)
            deleted += 1
        except Exception:
            continue
    await message.answer(f"🧹 تم حذف {deleted} رسالة")


@router.message(Command("lockall"))
@admin_guard
async def lockall_cmd(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    del session
    await bot.set_chat_permissions(message.chat.id, ChatPermissions(can_send_messages=False))
    await message.answer("🔒 تم قفل الدردشة")


@router.message(Command("unlockall"))
@admin_guard
async def unlockall_cmd(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    del session
    await bot.set_chat_permissions(
        message.chat.id,
        ChatPermissions(can_send_messages=True, can_send_other_messages=True, can_add_web_page_previews=True),
    )
    await message.answer("🔓 تم فتح الدردشة")


@router.message(Command("dwarn"))
@admin_guard
async def dwarn_cmd(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer("رد على الرسالة")
        return
    if await bot_can_delete(bot, message.chat.id):
        await bot.delete_message(message.chat.id, message.reply_to_message.message_id)
    warns = await moderation.add_warn(session, message.chat.id, message.reply_to_message.from_user.id)
    await message.answer(f"🗑️⚠️ تم الحذف والتحذير. العدد: {warns}")


@router.message(Command("dmute"))
@admin_guard
async def dmute_cmd(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    del session
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer("رد على الرسالة")
        return
    user_id = message.reply_to_message.from_user.id
    if await bot_can_delete(bot, message.chat.id):
        await bot.delete_message(message.chat.id, message.reply_to_message.message_id)
    if await bot_can_ban(bot, message.chat.id):
        until = int(time.time()) + settings.MUTE_SECONDS
        await bot.restrict_chat_member(message.chat.id, user_id, permissions=ChatPermissions(can_send_messages=False), until_date=until)
    await message.answer("🗑️🔇 تم الحذف والكتم")


@router.message(Command("set_welcome"))
@admin_guard
async def set_welcome(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    del bot
    if not _cmd_args(message):
        await message.answer("الاستخدام: /set_welcome text")
        return
    await moderation.set_welcome_message(session, message.chat.id, " ".join(_cmd_args(message)))
    await message.answer("تم حفظ رسالة الترحيب")


@router.message(Command("set_goodbye"))
@admin_guard
async def set_goodbye(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    del bot
    if not _cmd_args(message):
        await message.answer("الاستخدام: /set_goodbye text")
        return
    await moderation.set_goodbye_message(session, message.chat.id, " ".join(_cmd_args(message)))
    await message.answer("تم حفظ رسالة الوداع")


@router.message(Command("set_rules"))
@admin_guard
async def set_rules(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    del bot
    if not _cmd_args(message):
        await message.answer("الاستخدام: /set_rules text")
        return
    await moderation.set_rules_text(session, message.chat.id, " ".join(_cmd_args(message)))
    await message.answer("تم حفظ القوانين")


@router.message(Command("set_antispam"))
@admin_guard
async def set_antispam(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    del bot
    args = _cmd_args(message)
    if len(args) != 2:
        await message.answer("الاستخدام: /set_antispam limit window_seconds")
        return
    try:
        limit = int(args[0])
        window = int(args[1])
    except ValueError:
        await message.answer("limit/window يجب أن تكون أرقامًا صحيحة")
        return
    await moderation.set_antispam(session, message.chat.id, limit, window)
    await message.answer(f"تم تحديث مكافحة السبام: {limit}/{window}ث")


@router.message(Command("set_antiflood"))
@admin_guard
async def set_antiflood(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    del bot
    args = _cmd_args(message)
    if len(args) != 2:
        await message.answer("الاستخدام: /set_antiflood limit window_seconds")
        return
    try:
        limit = int(args[0])
        window = int(args[1])
    except ValueError:
        await message.answer("limit/window يجب أن تكون أرقامًا صحيحة")
        return
    await moderation.set_antiflood(session, message.chat.id, limit, window)
    await message.answer(f"تم تحديث مكافحة الفلود: {limit}/{window}ث")


@router.message(Command("rules"))
async def rules_cmd(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    del bot
    meta = await moderation.get_group_meta(session, message.chat.id)
    await message.answer(meta.rules_text or "لا توجد قوانين مضبوطة")


@router.message(Command("id"))
async def id_cmd(message: types.Message) -> None:
    text = f"معرّف المستخدم: `{message.from_user.id if message.from_user else 0}`"
    if message.chat.type != "private":
        text += f"\nمعرّف الدردشة: `{message.chat.id}`"
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)


@router.message(Command("roll_dice"))
async def roll_dice_cmd(message: types.Message) -> None:
    await message.answer(f"🎲 نتيجتك: {random.randint(1, 6)}")


@router.message(Command("flip_coin"))
async def flip_coin_cmd(message: types.Message) -> None:
    await message.answer(f"🪙 {random.choice(['وجه', 'كتابة'])}")


@router.message(Command("random_number"))
async def random_number_cmd(message: types.Message) -> None:
    await message.answer(f"🔢 الرقم العشوائي: {random.randint(1, 100)}")


@router.message(Command("quote"))
async def quote_cmd(message: types.Message) -> None:
    quotes = [
        "كن أنت التغيير الذي تريد أن تراه في العالم.",
        "ابقَ طموحًا وابقَ متعلمًا.",
        "الطريق للعمل العظيم أن تحب ما تعمله.",
        "الحياة تحدث بينما أنت مشغول بخطط أخرى.",
    ]
    await message.answer(f"📜 {random.choice(quotes)}")


@router.message(Command("announcement"))
async def announcement_cmd(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    if not is_owner(message.from_user.id if message.from_user else None):
        await message.answer("هذا الأمر متاح للمالك فقط")
        return
    text = " ".join(_cmd_args(message)).strip()
    if not text and message.reply_to_message:
        text = message.reply_to_message.text or message.reply_to_message.caption or ""
    if not text:
        await message.answer("الاستخدام: /announcement نص أو بالرد على رسالة")
        return

    groups = await moderation.list_groups(session)
    sent = 0
    failed = 0
    for chat_id in groups:
        try:
            await bot.send_message(chat_id, text)
            sent += 1
        except Exception as exc:
            failed += 1
            logger.warning("announcement failed chat={} err={}", chat_id, exc)
    await message.answer(f"تم إرسال الإعلان: {sent} | فشل: {failed}")


@router.message(Command("gban"))
async def gban_cmd(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    if not is_owner(message.from_user.id if message.from_user else None):
        await message.answer("هذا الأمر متاح للمالك فقط")
        return
    target = await _target_user(message)
    if target is None:
        await message.answer("رد على المستخدم أو أدخل user_id")
        return

    groups = await moderation.list_groups(session)
    banned = 0
    for chat_id in groups:
        try:
            await bot.ban_chat_member(chat_id, target)
            banned += 1
        except Exception:
            continue
    await message.answer(f"تمت محاولة الحظر العام في {banned} مجموعة")
