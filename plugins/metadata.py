from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ForceReply,
)

from helper.database import db


# --- METADATA SETTINGS ---
@Client.on_message(
    filters.private & filters.command("metadata")
)
async def metadata_settings(
    client: Client,
    message: Message,
):
    """
    Displays the current metadata branding settings.
    """

    user_id = message.from_user.id

    user_data = await db.get_user_data(user_id)

    if not user_data:
        await db.add_user(user_id)
        user_data = await db.get_user_data(user_id)

    audio_pref = user_data.get(
        "audio_name",
        "AniToon Official",
    )

    sub_pref = user_data.get(
        "sub_name",
        "AniToon Official",
    )

    keyboard = InlineKeyboardMarkup(
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
        ]
    )

    await message.reply_text(
        "🏷️ **AniToon Metadata Branding**\n\n"
        "Your current internal track names:\n\n"
        f"🎵 **Audio Track:** `{audio_pref}`\n"
        f"📜 **Subtitle Track:** `{sub_pref}`\n\n"
        "These names can be applied to media during "
        "the FFmpeg processing stage.",
        reply_markup=keyboard,
    )


# --- SET AUDIO TRACK NAME ---
@Client.on_callback_query(
    filters.regex("^set_audio_meta$")
)
async def cb_set_audio(
    client: Client,
    cb,
):
    """
    Opens the Audio Track Name input prompt.
    """

    await cb.answer()

    await cb.message.delete()

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


# --- SET SUBTITLE TRACK NAME ---
@Client.on_callback_query(
    filters.regex("^set_sub_meta$")
)
async def cb_set_sub(
    client: Client,
    cb,
):
    """
    Opens the Subtitle Track Name input prompt.
    """

    await cb.answer()

    await cb.message.delete()

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


# --- RESET METADATA ---
@Client.on_callback_query(
    filters.regex("^reset_metadata$")
)
async def cb_reset_meta(
    client: Client,
    cb,
):
    """
    Resets the user's metadata names to the default values.
    """

    await db.col.update_one(
        {"id": cb.from_user.id},
        {
            "$set": {
                "audio_name": "AniToon Official",
                "sub_name": "AniToon Official",
            }
        },
        upsert=True,
    )

    await cb.answer(
        "Metadata Reset Successfully! ✅",
        show_alert=True,
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "⚙️ Open Metadata",
                    callback_data="metadata_settings",
                )
            ]
        ]
    )

    await cb.message.edit_text(
        "🔄 **Metadata branding reset to default.**\n\n"
        "🎵 Audio: `AniToon Official`\n"
        "📜 Subtitle: `AniToon Official`",
        reply_markup=keyboard,
    )


# --- PROCESS METADATA REPLIES ---
@Client.on_message(
    filters.private
    & filters.reply
    & filters.text
)
async def handle_meta_replies(
    client: Client,
    message: Message,
):
    """
    Processes replies to the Audio/Subtitle ForceReply prompts.
    """

    reply = message.reply_to_message

    if not reply or not reply.text:
        return

    prompt_text = reply.text.lower()
    new_value = message.text.strip()

    if not new_value:
        return await message.reply_text(
            "❌ **Metadata name cannot be empty.**"
        )

    # Audio Track
    if "audio track name" in prompt_text:
        await db.col.update_one(
            {"id": message.from_user.id},
            {
                "$set": {
                    "audio_name": new_value
                }
            },
            upsert=True,
        )

        await message.reply_text(
            "✅ **Audio Track Name Updated!**\n\n"
            f"🎵 `{new_value}`"
        )

    # Subtitle Track
    elif "subtitle track name" in prompt_text:
        await db.col.update_one(
            {"id": message.from_user.id},
            {
                "$set": {
                    "sub_name": new_value
                }
            },
            upsert=True,
        )

        await message.reply_text(
            "✅ **Subtitle Track Name Updated!**\n\n"
            f"📜 `{new_value}`"
        )
