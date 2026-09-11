from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
)

from helper.database import db


# --- SET CAPTION ---
@Client.on_message(
    filters.private
    & filters.command(["set_caption", "setcaption"])
)
async def set_caption(
    client: Client,
    message: Message,
):
    """
    Saves a custom caption template to MongoDB.
    Supported placeholders:
    {filename}
    {filesize}
    {duration}
    """

    if len(message.command) < 2:
        return await message.reply_text(
            "❌ **No caption provided.**\n\n"
            "**Usage:**\n"
            "`/set_caption 🎥 File: {filename}`\n\n"
            "**Available Placeholders:**\n"
            "• `{filename}` - File name\n"
            "• `{filesize}` - File size\n"
            "• `{duration}` - Video duration"
        )

    caption = message.text.split(" ", 1)[1].strip()

    if not caption:
        return await message.reply_text(
            "❌ **Caption cannot be empty.**"
        )

    status = await message.reply_text(
        "🔄 **AniToon: Saving your caption...**"
    )

    await db.set_caption(
        message.from_user.id,
        caption,
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🗑️ Delete Caption",
                    callback_data="del_caption",
                )
            ]
        ]
    )

    await status.edit_text(
        "✅ **Custom Caption Saved!**\n\n"
        "**Template:**\n"
        f"`{caption}`",
        reply_markup=keyboard,
    )


# --- VIEW CAPTION ---
@Client.on_message(
    filters.private
    & filters.command(
        ["see_caption", "view_caption", "show_caption"]
    )
)
async def see_caption(
    client: Client,
    message: Message,
):
    """
    Displays the user's currently saved caption.
    """

    caption = await db.get_caption(
        message.from_user.id
    )

    if caption:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "⚙️ Change",
                        callback_data="help_caption",
                    ),
                    InlineKeyboardButton(
                        "🗑️ Delete",
                        callback_data="del_caption",
                    ),
                ]
            ]
        )

        return await message.reply_text(
            "📝 **Your Current Caption Template:**\n\n"
            f"`{caption}`",
            reply_markup=keyboard,
        )

    await message.reply_text(
        "❌ **You don't have a custom caption set.**\n\n"
        "Use `/set_caption` to create one."
    )


# --- DELETE CAPTION ---
@Client.on_message(
    filters.private
    & filters.command(
        ["del_caption", "delete_caption"]
    )
)
async def delete_caption(
    client: Client,
    message: Message,
):
    """
    Removes the user's saved caption.
    """

    await db.set_caption(
        message.from_user.id,
        None,
    )

    await message.reply_text(
        "🗑️ **Custom Caption Deleted.**\n\n"
        "Your files will now use the default caption."
    )


# --- DELETE BUTTON ---
@Client.on_callback_query(
    filters.regex("^del_caption$")
)
async def cb_del_caption(
    client: Client,
    callback_query,
):
    """
    Handles the Delete Caption button.
    """

    await db.set_caption(
        callback_query.from_user.id,
        None,
    )

    await callback_query.answer(
        "Caption Deleted 🗑️",
        show_alert=True,
    )

    await callback_query.message.edit_text(
        "🗑️ **Custom Caption has been removed.**"
    )


# --- CAPTION HELP / CHANGE ---
@Client.on_callback_query(
    filters.regex("^help_caption$")
)
async def cb_help_caption(
    client: Client,
    callback_query,
):
    """
    Shows instructions for caption placeholders.
    """

    keyboard = InlineKeyboardMarkup(
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
                    callback_data="settings",
                )
            ],
        ]
    )

    await callback_query.message.edit_text(
        "💡 **Custom Caption Help**\n\n"
        "**Available placeholders:**\n\n"
        "• `{filename}` — File name\n"
        "• `{filesize}` — File size\n"
        "• `{duration}` — Video duration\n\n"
        "**Example:**\n"
        "`🎥 File: {filename}`\n"
        "`📦 Size: {filesize}`\n"
        "`⏱️ Duration: {duration}`\n"
        "`📥 Uploaded By : @AniToon_Edit`",
        reply_markup=keyboard,
    )
