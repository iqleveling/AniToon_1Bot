from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup


@Client.on_callback_query(filters.regex(r"^start_rename$"), group=-9000)
async def start_rename(client, callback_query):
    """Rename entry point; enforce force-sub before accepting a new file."""
    if callback_query.from_user is None:
        return await callback_query.answer()
    await callback_query.answer()

    try:
        from plugins.start import FORCE_SUB_CHANNELS, get_force_sub_status, make_force_sub_text, make_force_sub_keyboard
        joined_count, missing, failed = await get_force_sub_status(client, callback_query.from_user.id)
        if missing or failed or joined_count != len(FORCE_SUB_CHANNELS):
            text = make_force_sub_text(joined_count, len(missing), len(failed))
            keyboard = make_force_sub_keyboard(missing, failed)
            try:
                await callback_query.message.edit_text(text, reply_markup=keyboard)
            except Exception:
                await callback_query.message.reply_text(text, reply_markup=keyboard)
            return
    except Exception:
        try:
            await callback_query.message.reply_text("⚠️ **Channel verification failed.** Please try again in a moment.")
        except Exception:
            pass
        return

    text = "✏️ **Rename File**\n\n📤 Send me a video, document, or audio file."
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Home", callback_data="start")]])
    try:
        await callback_query.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        await callback_query.message.reply_text(text, reply_markup=keyboard)
