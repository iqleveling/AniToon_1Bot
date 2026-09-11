from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

from config import Config
from helper.database import db
from helper.utils import humanbytes


# --- MAIN CALLBACK HANDLER ---
@Client.on_callback_query()
async def cb_handler(
    client: Client,
    query: CallbackQuery,
):
    """
    Handles all interactive menu buttons.
    """

    data = query.data
    user_id = query.from_user.id

    # --- HOME MENU ---
    if data == "start":

        user_data = await db.get_user_data(user_id)

        if not user_data:
            await db.add_user(user_id)
            user_data = await db.get_user_data(user_id)

        used = await db.get_usage(user_id)

        is_premium = user_data.get(
            "is_premium",
            False,
        )

        if is_premium:
            remaining = "♾️ Unlimited"
        else:
            remaining = humanbytes(
                max(
                    Config.DAILY_LIMIT - used,
                    0,
                )
            )

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🛠 Help & Usage",
                        callback_data="help",
                    ),
                    InlineKeyboardButton(
                        "ℹ️ About Bot",
                        callback_data="about",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "⚙️ Settings",
                        callback_data="settings",
                    ),
                    InlineKeyboardButton(
                        "💎 Buy Premium",
                        callback_data="upgrade",
                    ),
                ],
            ]
        )

        await query.message.edit_text(
            "🔥 **Welcome to AniToon Promax Bot** 🔥\n\n"
            f"👤 **User:** {query.from_user.first_name}\n\n"
            f"📊 **Plan:** "
            f"{'💎 Premium' if is_premium else '🆓 Free'}\n"
            f"🚀 **Used Today:** {humanbytes(used)}\n"
            f"⏳ **Remaining:** {remaining}\n\n"
            "Select an option below:",
            reply_markup=keyboard,
        )

    # --- ABOUT MENU ---
    elif data == "about":

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "⬅️ Back",
                        callback_data="start",
                    )
                ]
            ]
        )

        await query.message.edit_text(
            "🤖 **AniToon Promax Bot**\n\n"
            "📂 **File Processing:** Active ✅\n"
            "🏷️ **Metadata Branding:** Active ✅\n"
            "⚡ **Concurrent Processing:** Active ✅\n"
            "🗄️ **MongoDB Database:** Connected ✅\n"
            "📊 **Daily Quota System:** Active ✅\n\n"
            f"👤 **Developer:** @AniToon_Official\n\n"
            "Built with Pyrogram, MongoDB and FFmpeg.",
            reply_markup=keyboard,
        )

    # --- HELP MENU ---
    elif data == "help":

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "⚙️ Settings",
                        callback_data="settings",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⬅️ Back",
                        callback_data="start",
                    )
                ],
            ]
        )

        await query.message.edit_text(
            "❓ **How to Use AniToon Promax**\n\n"
            "1️⃣ Send a document, video or audio file.\n"
            "2️⃣ The bot detects the file automatically.\n"
            "3️⃣ Enter the new filename.\n"
            "4️⃣ FFmpeg processes the media metadata.\n"
            "5️⃣ The renamed file is uploaded back to you.\n\n"
            "🖼️ **Thumbnail:**\n"
            "Use the thumbnail commands to save a permanent thumbnail.\n\n"
            "📝 **Caption:**\n"
            "Use `/set_caption` to save a custom caption.\n\n"
            "💎 **Premium:**\n"
            "Premium accounts can use the higher file-processing limits.",
            reply_markup=keyboard,
        )

    # --- PREMIUM MENU ---
    elif data == "upgrade":

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📩 Contact Admin",
                        url="https://t.me/AniToon_Official",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⬅️ Back",
                        callback_data="start",
                    )
                ],
            ]
        )

        await query.message.edit_text(
            "💎 **AniToon Premium** 💎\n\n"
            "Premium access provides:\n\n"
            "✅ Higher file-processing limits\n"
            "✅ Premium account status\n"
            "✅ Priority processing\n"
            "✅ Advanced bot features\n\n"
            "📩 Contact the administrator for Premium access.",
            reply_markup=keyboard,
        )

    # --- SETTINGS MENU ---
    elif data == "settings":

        thumb = await db.get_thumbnail(user_id)
        caption = await db.get_caption(user_id)

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🖼️ Thumbnail",
                        callback_data="thumb_settings",
                    ),
                    InlineKeyboardButton(
                        "📝 Caption",
                        callback_data="caption_settings",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "⬅️ Back",
                        callback_data="start",
                    )
                ],
            ]
        )

        await query.message.edit_text(
            "⚙️ **AniToon Settings**\n\n"
            f"🖼️ **Thumbnail:** "
            f"{'✅ Saved' if thumb else '❌ Not Set'}\n"
            f"📝 **Caption:** "
            f"{'✅ Saved' if caption else '❌ Not Set'}\n"
            f"🏷️ **Audio Track Name:** "
            f"`{Config.AUDIO_NAME}`\n"
            f"💬 **Subtitle Track Name:** "
            f"`{Config.SUBTITLE_NAME}`",
            reply_markup=keyboard,
        )

    # --- THUMBNAIL SETTINGS ---
    elif data == "thumb_settings":

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🗑️ Delete Thumbnail",
                        callback_data="del_thumb",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⬅️ Back",
                        callback_data="settings",
                    )
                ],
            ]
        )

        thumb = await db.get_thumbnail(user_id)

        await query.message.edit_text(
            "🖼️ **Thumbnail Settings**\n\n"
            f"Current Status: "
            f"{'✅ Thumbnail Saved' if thumb else '❌ No Thumbnail Saved'}\n\n"
            "Send an image to update your permanent thumbnail.",
            reply_markup=keyboard,
        )

    # --- CAPTION SETTINGS ---
    elif data == "caption_settings":

        caption = await db.get_caption(user_id)

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📝 Caption Help",
                        callback_data="help_caption",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🗑️ Delete Caption",
                        callback_data="del_caption",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⬅️ Back",
                        callback_data="settings",
                    )
                ],
            ]
        )

        await query.message.edit_text(
            "📝 **Caption Settings**\n\n"
            f"**Status:** "
            f"{'✅ Saved' if caption else '❌ Not Set'}\n\n"
            f"{'Current Template:' if caption else 'Use `/set_caption` to create one.'}\n"
            f"{'`' + caption + '`' if caption else ''}",
            reply_markup=keyboard,
        )

    # --- DELETE THUMBNAIL ---
    elif data == "del_thumb":

        await db.set_thumbnail(
            user_id,
            None,
        )

        await query.answer(
            "Thumbnail Deleted 🗑️",
            show_alert=True,
        )

        await query.message.edit_text(
            "🗑️ **Permanent Thumbnail Deleted.**\n\n"
            "Send a new image to set another thumbnail.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "⬅️ Back",
                            callback_data="settings",
                        )
                    ]
                ]
            ),
        )

    # --- UNKNOWN CALLBACK ---
    else:
        await query.answer(
            "This option is not available.",
            show_alert=True,
        )
        return

    # Stop Telegram's loading animation.
    await query.answer()
