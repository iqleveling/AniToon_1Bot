from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ForceReply,
)

from helper.database import db
from plugins.ui import edit_callback_message


DEFAULT_METADATA_NAME = "AniToon Official"


def metadata_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🎵 Set Audio Name",
                    callback_data="set_audio_meta",
                )
            ],
            [
                InlineKeyboardButton(
                    "📜 Set Subtitle Name",
                    callback_data="set_sub_meta",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔄 Reset to Default",
                    callback_data="reset_metadata",
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


async def show_metadata(
    client: Client,
    chat_id: int,
    message=None,
):
    user_id = int(chat_id)

    if not await db.is_user_exist(user_id):
        await db.add_user(user_id)

    user = await db.get_user_data(user_id) or {}

    audio_name = user.get(
        "audio_name",
        DEFAULT_METADATA_NAME,
    )
    subtitle_name = user.get(
        "sub_name",
        DEFAULT_METADATA_NAME,
    )

    text = (
        "🏷️ **AniToon Metadata Branding**\n\n"
        f"🎵 **Audio Track:** `{audio_name}`\n"
        f"📜 **Subtitle Track:** `{subtitle_name}`\n\n"
        "These names are applied during FFmpeg processing."
    )

    if message is not None:
        await message.reply_text(
            text,
            reply_markup=metadata_keyboard(),
        )
    else:
        await client.send_message(
            user_id,
            text,
            reply_markup=metadata_keyboard(),
        )


@Client.on_message(
    filters.private
    & filters.command(
        [
            "metadata",
            "metasettings",
        ]
    )
)
async def metadata_settings(
    client: Client,
    message: Message,
):
    await show_metadata(
        client,
        message.from_user.id,
        message=message,
    )


@Client.on_callback_query(
    filters.regex(r"^set_audio_meta$")
)
async def cb_set_audio(
    client: Client,
    cb,
):
    await cb.answer()

    await client.send_message(
        chat_id=cb.from_user.id,
        text=(
            "⌨️ **Enter the NEW Audio Track Name:**\n\n"
            "Example:\n"
            "`[AniToon] Dual Audio`"
        ),
        reply_markup=ForceReply(
            selective=True
        ),
    )


@Client.on_callback_query(
    filters.regex(r"^set_sub_meta$")
)
async def cb_set_sub(
    client: Client,
    cb,
):
    await cb.answer()

    await client.send_message(
        chat_id=cb.from_user.id,
        text=(
            "⌨️ **Enter the NEW Subtitle Track Name:**\n\n"
            "Example:\n"
            "`AniToon Softsubs`"
        ),
        reply_markup=ForceReply(
            selective=True
        ),
    )


@Client.on_callback_query(
    filters.regex(r"^reset_metadata$")
)
async def cb_reset_meta(
    client: Client,
    cb,
):
    await db.set_metadata(
        cb.from_user.id,
        DEFAULT_METADATA_NAME,
        DEFAULT_METADATA_NAME,
    )

    await cb.answer(
        "Metadata reset successfully ✅",
        show_alert=True,
    )

    await cb.message.edit_text(
        "🔄 **Metadata branding reset to default.**\n\n"
        "🎵 Audio: `AniToon Official`\n"
        "📜 Subtitle: `AniToon Official`",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🏷 Open Metadata",
                        callback_data="metadata_settings",
                    )
                ]
            ]
        ),
    )


@Client.on_message(
    filters.private
    & filters.reply
    & filters.text
)
async def handle_meta_replies(
    client: Client,
    message: Message,
):
    reply = message.reply_to_message

    if not reply or not reply.text:
        return

    prompt_text = reply.text.lower()
    new_value = message.text.strip()

    if not new_value:
        return await message.reply_text(
            "❌ **Metadata name cannot be empty.**"
        )

    if "audio track name" in prompt_text:
        await db.set_audio_name(
            message.from_user.id,
            new_value,
        )

        await message.reply_text(
            "✅ **Audio Track Name Updated!**\n\n"
            f"🎵 `{new_value}`"
        )

    elif "subtitle track name" in prompt_text:
        await db.set_subtitle_name(
            message.from_user.id,
            new_value,
        )

        await message.reply_text(
            "✅ **Subtitle Track Name Updated!**\n\n"
            f"📜 `{new_value}`"
        )
