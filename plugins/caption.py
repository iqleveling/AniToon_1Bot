from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
    ForceReply,
)

from helper.database import db


# ============================================================
# SET CAPTION
# ============================================================

@Client.on_message(
    filters.private
    & filters.command(
        [
            "set_caption",
            "setcaption",
        ]
    )
)
async def set_caption(
    client: Client,
    message: Message,
):
    if len(message.command) < 2:
        return await message.reply_text(
            "❌ **No caption provided.**\n\n"
            "**Usage:**\n"
            "`/setcaption 🎥 File: {filename}`\n\n"
            "**Placeholders:**\n"
            "`{filename}` — file name\n"
            "`{filesize}` — file size\n"
            "`{duration}` — video duration"
        )

    caption = message.text.split(" ", 1)[1].strip()

    if not caption:
        return await message.reply_text(
            "❌ **Caption cannot be empty.**"
        )

    await db.set_caption(
        message.from_user.id,
        caption,
    )

    await message.reply_text(
        "✅ **Custom Caption Saved!**\n\n"
        f"**Template:**\n`{caption}`\n\n"
        "Use `/seecaption` to view it or `/delcaption` to remove it."
    )


# ============================================================
# VIEW CAPTION
# ============================================================

@Client.on_message(
    filters.private
    & filters.command(
        [
            "see_caption",
            "seecaption",
            "view_caption",
            "show_caption",
        ]
    )
)
async def see_caption(
    client: Client,
    message: Message,
):
    caption = await db.get_caption(
        message.from_user.id
    )

    if not caption:
        return await message.reply_text(
            "❌ **No custom caption is set.**\n\n"
            "Use `/setcaption` to create one."
        )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "⚙️ Change",
                    callback_data="help_caption",
                ),
                InlineKeyboardButton(
                    "🗑 Delete",
                    callback_data="del_caption",
                ),
            ]
        ]
    )

    await message.reply_text(
        "📝 **Your Current Caption Template:**\n\n"
        f"`{caption}`",
        reply_markup=keyboard,
    )


# ============================================================
# DELETE CAPTION COMMAND
# ============================================================

@Client.on_message(
    filters.private
    & filters.command(
        [
            "del_caption",
            "delcaption",
            "delete_caption",
            "deletecaption",
        ]
    )
)
async def delete_caption(
    client: Client,
    message: Message,
):
    await db.set_caption(
        message.from_user.id,
        None,
    )

    await message.reply_text(
        "🗑️ **Custom Caption Deleted.**"
    )


# ============================================================
# DELETE BUTTON
# ============================================================

@Client.on_callback_query(
    filters.regex(r"^del_caption$")
)
async def cb_del_caption(
    client: Client,
    callback_query,
):
    await db.set_caption(
        callback_query.from_user.id,
        None,
    )

    await callback_query.answer(
        "Caption deleted 🗑️",
        show_alert=True,
    )

    from plugins.ui import edit_callback_message

    await edit_callback_message(
        callback_query,
        "🗑️ **Custom Caption has been removed.**",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "⚙️ Settings",
                        callback_data="settings",
                    )
                ]
            ]
        ),
    )


# ============================================================
# CAPTION HELP BUTTON
# ============================================================

@Client.on_callback_query(
    filters.regex(r"^help_caption$")
)
async def cb_help_caption(
    client: Client,
    callback_query,
):
    await callback_query.answer()

    await callback_query.message.edit_text(
        "💡 **Custom Caption Help**\n\n"
        "**Available placeholders:**\n\n"
        "• `{filename}` — File name\n"
        "• `{filesize}` — File size\n"
        "• `{duration}` — Video duration\n\n"
        "**Example:**\n"
        "`🎥 File: {filename}`\n"
        "`📦 Size: {filesize}`\n"
        "`⏱️ Duration: {duration}`",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📝 Set Caption",
                        callback_data="set_caption_help",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔙 Back",
                        callback_data="settings_caption",
                    )
                ],
            ]
        ),
    )
