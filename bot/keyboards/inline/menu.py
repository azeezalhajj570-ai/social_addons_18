from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_keyboard() -> InlineKeyboardMarkup:
    """Main feature menu (group manager categories)."""
    buttons = [
        [InlineKeyboardButton(text="👮 أوامر المشرفين", callback_data="gm:admin")],
        [InlineKeyboardButton(text="👥 أوامر المستخدمين", callback_data="gm:user")],
        [InlineKeyboardButton(text="🎉 أوامر ترفيهية", callback_data="gm:fun")],
        [InlineKeyboardButton(text="⚙️ الإعدادات", callback_data="gm:settings")],
    ]

    keyboard = InlineKeyboardBuilder(markup=buttons)

    keyboard.adjust(1)

    return keyboard.as_markup()
