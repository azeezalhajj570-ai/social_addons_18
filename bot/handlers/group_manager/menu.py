from __future__ import annotations

from aiogram import F, Router, types
from aiogram.filters import Command

router = Router(name="group_manager_menu")


def _menu_keyboard() -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="👮 أوامر المشرفين", callback_data="gm:admin")],
            [types.InlineKeyboardButton(text="👥 أوامر المستخدمين", callback_data="gm:user")],
            [types.InlineKeyboardButton(text="🎉 أوامر ترفيهية", callback_data="gm:fun")],
            [types.InlineKeyboardButton(text="⚙️ الإعدادات", callback_data="gm:settings")],
        ],
    )


@router.message(Command("daisy"))
async def daisy_menu(message: types.Message) -> None:
    await message.answer("اختر القسم المطلوب:", reply_markup=_menu_keyboard())


@router.callback_query(F.data.startswith("gm:"))
async def daisy_callbacks(query: types.CallbackQuery) -> None:
    data = query.data
    await query.answer()
    if data == "gm:admin":
        text = "المشرفون: /ban /unban /kick /mute /unmute /warn /unwarn /promote /demote /purge /filter /stop /filterlist /gban /lockall /unlockall /dwarn /dmute"
    elif data == "gm:user":
        text = "المستخدمون: /info /id /rules /help"
    elif data == "gm:fun":
        text = "ترفيهي: /roll_dice /flip_coin /random_number /quote"
    else:
        text = "الإعدادات: /settings /set_welcome /set_goodbye /set_rules /set_antispam /set_antiflood"

    await query.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="رجوع", callback_data="gm:home")]]))


@router.callback_query(F.data == "gm:home")
async def daisy_home(query: types.CallbackQuery) -> None:
    await query.answer()
    await query.message.edit_text("اختر القسم المطلوب:", reply_markup=_menu_keyboard())
