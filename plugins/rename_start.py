from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup


@Client.on_callback_query(filters.regex(r"^start_rename$"), group=-9000)
async def start_rename(client, callback_query):
    """Rename entry point; file intake itself remains automatic."""
    if callback_query.from_user is None:
        return await callback_query.answer()
    await callback_query.answer()
    text = "✏️ **Rename File**\n\n📤 Send me a video, document, or audio file."
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Home", callback_data="start")]])
    try:
        await callback_query.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback_query.message.reply_text(text, reply_markup=keyboard)
