from __future__ import annotations
from collections import defaultdict
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select

from bot.database.database import sessionmaker
from bot.database.models.moderation import BotCommandModel
from aiogram.types import BotCommand, BotCommandScopeAllChatAdministrators, BotCommandScopeAllPrivateChats

if TYPE_CHECKING:
    from aiogram import Bot

arabic_commands: dict[str, str] = {
    "help": "المساعدة",
    "support": "جهات التواصل والدعم",
    "menu": "القائمة الرئيسية",
    "settings": "إعدادات إدارة المجموعة",
    "resetwarns": "تصفير تحذيرات المستخدم المحدد",
    "addrule": "إضافة قاعدة Regex للحذف التلقائي",
    "delrule": "حذف قاعدة ديناميكية بالمعرف",
    "listrules": "عرض القواعد الديناميكية",
    "addroute": "إضافة مسار لكلمة مفتاحية",
    "delroute": "حذف مسار كلمة مفتاحية",
    "listroutes": "عرض مسارات الكلمات المفتاحية",
    "addgate": "إضافة بوابة تحقق بالمجموعات",
    "delgate": "حذف بوابة تحقق بالمعرف",
    "listgates": "عرض بوابات التحقق",
    "toggle_anti_links": "تفعيل/إيقاف منع الروابط",
    "toggle_anti_bots": "تفعيل/إيقاف منع البوتات",
    "toggle_hide_system": "تفعيل/إيقاف إخفاء رسائل النظام",
    "toggle_warn_in_dm": "تفعيل/إيقاف التحذير في الخاص",
    "toggle_warn_in_group": "تفعيل/إيقاف التحذير في المجموعة",
    "toggle_temp_ban": "تفعيل/إيقاف وضع التقييد المؤقت",
    "set_temp_ban_seconds": "تحديد مدة التقييد المؤقت",
    "ban": "حظر مستخدم (رد أو معرف)",
    "unban": "فك حظر مستخدم",
    "kick": "طرد مستخدم",
    "mute": "كتم مستخدم",
    "unmute": "فك كتم مستخدم",
    "warn": "تحذير مستخدم",
    "unwarn": "إزالة تحذير واحد",
    "promote": "ترقية المستخدم المردود عليه",
    "demote": "تنزيل المستخدم المردود عليه",
    "purge": "حذف مجموعة رسائل",
    "filter": "حفظ الرد كفلتر",
    "stop": "حذف فلتر بكلمة مفتاحية",
    "filterlist": "عرض الفلاتر",
    "gban": "حظر عام (للمالك فقط)",
    "lockall": "قفل صلاحيات المجموعة",
    "unlockall": "فتح صلاحيات المجموعة",
    "dwarn": "حذف الرسالة وتحذير المستخدم",
    "dmute": "حذف الرسالة وكتم المستخدم",
    "id": "عرض معرفات المستخدم/الدردشة",
    "rules": "عرض قوانين المجموعة",
    "roll_dice": "رمي النرد",
    "flip_coin": "رمي العملة",
    "random_number": "توليد رقم عشوائي",
    "quote": "اقتباس عشوائي",
    "set_welcome": "تعيين رسالة ترحيب",
    "set_goodbye": "تعيين رسالة وداع",
    "set_rules": "تعيين قوانين المجموعة",
    "set_antispam": "ضبط حدود مكافحة السبام",
    "set_antiflood": "ضبط حدود مكافحة الفلود",
    "announcement": "إرسال إعلان عام (للمالك)",
    "daisy": "فتح قائمة الإدارة",
    "addschedule": "إضافة رسالة مجدولة",
    "listschedules": "عرض الرسائل المجدولة",
    "delschedule": "حذف رسالة مجدولة",
    "toggleschedule": "تفعيل/تعطيل الجدولة",
}

users_commands: dict[str, dict[str, str]] = {
    "ar": arabic_commands,
    "en": arabic_commands,
    "uk": arabic_commands,
    "ru": arabic_commands,
}

admins_commands: dict[str, dict[str, str]] = {
    "ar": {
        "ping": "فحص استجابة البوت",
        "stats": "عرض إحصائيات البوت",
    },
    "en": {
        "ping": "فحص استجابة البوت",
        "stats": "عرض إحصائيات البوت",
    },
    "uk": {
        "ping": "فحص استجابة البوت",
        "stats": "عرض إحصائيات البوت",
    },
    "ru": {
        "ping": "فحص استجابة البوت",
        "stats": "عرض إحصائيات البوت",
    },
}


async def set_default_commands(bot: Bot) -> None:
    await _seed_db_commands_if_empty()

    await remove_default_commands(bot)

    db_commands = await _get_commands_from_db()
    commands_map = db_commands or users_commands

    # Scope policy:
    # - Direct messages: ON
    # - Group administrators: ON
    # - Group chats (all members): OFF
    fallback_lang = "en" if "en" in commands_map else next(iter(commands_map))
    fallback_commands = commands_map[fallback_lang]
    await bot.set_my_commands(
        [BotCommand(command=command, description=description) for command, description in fallback_commands.items()],
        scope=BotCommandScopeAllPrivateChats(),
    )
    await bot.set_my_commands(
        [BotCommand(command=command, description=description) for command, description in fallback_commands.items()],
        scope=BotCommandScopeAllChatAdministrators(),
    )

    for language_code, commands in commands_map.items():
        await bot.set_my_commands(
            [BotCommand(command=command, description=description) for command, description in commands.items()],
            scope=BotCommandScopeAllPrivateChats(),
            language_code=language_code,
        )
        await bot.set_my_commands(
            [BotCommand(command=command, description=description) for command, description in commands.items()],
            scope=BotCommandScopeAllChatAdministrators(),
            language_code=language_code,
        )

        """ Commands for admins
        for admin_id in await admin_ids():
            await bot.set_my_commands(
                [
                    BotCommand(command=command, description=description)
                    for command, description in admins_commands[language_code].items()
                ],
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        """


async def remove_default_commands(bot: Bot) -> None:
    await bot.delete_my_commands(scope=BotCommandScopeAllPrivateChats())
    await bot.delete_my_commands(scope=BotCommandScopeAllChatAdministrators())


async def _get_commands_from_db() -> dict[str, dict[str, str]]:
    try:
        async with sessionmaker() as session:
            result = await session.execute(
                select(BotCommandModel)
                .where(BotCommandModel.enabled.is_(True))
                .order_by(BotCommandModel.language_code.asc(), BotCommandModel.sort_order.asc(), BotCommandModel.id.asc()),
            )
            rows = result.scalars().all()
    except Exception as exc:
        logger.warning("Failed to load bot commands from DB, using static defaults. err={}", exc)
        return {}

    if not rows:
        return {}

    commands_by_lang: dict[str, dict[str, str]] = defaultdict(dict)
    for row in rows:
        language_code = row.language_code.strip() if row.language_code else "en"
        commands_by_lang[language_code][row.command] = row.description
    return dict(commands_by_lang)


async def _seed_db_commands_if_empty() -> None:
    """Backfill missing default commands into bot_commands without overwriting existing rows."""
    try:
        async with sessionmaker() as session:
            sort_order = 10
            for language_code, commands in users_commands.items():
                for command, description in commands.items():
                    stmt = (
                        insert(BotCommandModel)
                        .values(
                            language_code=language_code,
                            command=command,
                            description=description,
                            enabled=True,
                            sort_order=sort_order,
                        )
                        .on_conflict_do_update(
                            constraint="uq_bot_commands_lang_command",
                            set_={
                                "description": description,
                                "enabled": True,
                                "sort_order": sort_order,
                            },
                        )
                    )
                    await session.execute(stmt)
                    sort_order += 10
            await session.commit()
            logger.info("Backfilled missing default commands into bot_commands table")
    except Exception as exc:
        logger.warning("Could not seed bot_commands table: {}", exc)
