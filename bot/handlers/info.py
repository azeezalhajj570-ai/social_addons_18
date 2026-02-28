from aiogram import Bot, Router, types
from aiogram.enums import ChatType
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services import moderation

router = Router(name="info")


@router.message(Command(commands=["info", "help", "about"]))
async def info_handler(message: types.Message, bot: Bot, session: AsyncSession) -> None:
    """Comprehensive help and quick stats."""
    user_id = message.from_user.id if message.from_user else 0
    lines: list[str] = [
        "✨ المميزات",
        "🛡️ الإشراف: حظر/فك حظر/طرد/كتم/فك كتم، نظام التحذيرات، ترقية/تنزيل، قفل/فتح، تنظيف، dwarn/dmute",
        "🎯 ذكي: فلاتر، مكافحة سبام، مكافحة فلود، قواعد Regex ديناميكية، بوابات/مسارات، حظر عام، إعلانات",
        "🎮 ترفيهي: /roll_dice /flip_coin /random_number /quote",
        "⚙️ التخصيص: /set_welcome /set_goodbye /set_rules /set_antispam /set_antiflood",
        "📱 الواجهة: /daisy لفتح قائمة مصنفة بالأزرار",
        "",
        "أوامر المشرفين:",
        "/ban /unban /kick /mute /unmute /warn /unwarn /resetwarns /promote /demote",
        "/purge /lockall /unlockall /dwarn /dmute",
        "/filter /stop /filterlist",
        "/settings /toggle_anti_links /toggle_anti_bots /toggle_hide_system",
        "/toggle_warn_in_dm /toggle_warn_in_group /toggle_temp_ban /set_temp_ban_seconds",
        "/addrule /delrule /listrules /addroute /delroute /listroutes /addgate /delgate /listgates",
        "/addschedule /listschedules /delschedule /toggleschedule",
        "",
        "أوامر المستخدمين:",
        "/info /help /id /rules /support /menu /daisy",
    ]

    if message.chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}:
        await moderation.ensure_group(session, message.chat.id)
        warns = await moderation.get_warns(session, message.chat.id, user_id)
        members = await bot.get_chat_member_count(message.chat.id)
        lines.extend(
            [
                "",
                "إحصائيات سريعة:",
                f"- chat_id: {message.chat.id}",
                f"- الأعضاء: {members}",
                f"- تحذيراتك: {warns}",
            ],
        )
    else:
        lines.extend(["", "إحصائيات سريعة:", f"- user_id: {user_id}"])

    await message.answer("\n".join(lines), disable_web_page_preview=True)
