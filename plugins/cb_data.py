from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

from config import Config
from helper.database import db
from helper.utils import humanbytes


# ============================================================
# CALLBACK HANDLER
# ============================================================

@Client.on_callback_query()
async def cb_handler(
    client: Client,
    query: CallbackQuery,
):
    data = query.data
    user_id = query.from_user.id

    # --------------------------------------------------------
    # HOME
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # ABOUT
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # HELP
    # --------------------------------------------------------

    elif data == "help":
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🧩 How to Join Parts",
                        callback_data="how_to_join",
                    )
                ],
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
            "Send an image to save it as your permanent thumbnail.\n\n"
            "📝 **Caption:**\n"
            "Use `/set_caption` to save a custom caption.\n\n"
            "🏷️ **Metadata:**\n"
            "Customize internal audio and subtitle track names.\n\n"
            "✂️ **Large Files:**\n"
            "Files above the split limit can be uploaded in multiple parts.",
            reply_markup=keyboard,
        )

    # --------------------------------------------------------
    # HOW TO JOIN PARTS
    # --------------------------------------------------------

    elif data == "how_to_join":
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "⬅️ Back to Help",
                        callback_data="help",
                    )
                ]
            ]
        )

        tutorial_text = (
            "🧩 **How to Join Split Parts**\n\n"
            "Large files may be divided into multiple parts such as:\n\n"
            "`filename.part001`\n"
            "`filename.part002`\n"
            "`filename.part003`\n\n"
            "📥 **Step 1 — Download ALL Parts**\n"
            "Download every part before joining them.\n"
            "Keep all parts inside the **same folder**.\n\n"
            "🪟 **Windows**\n"
            "Use 7-Zip or WinRAR and open the first part:\n"
            "`filename.part001`\n\n"
            "Choose the extract option and the software will "
            "process the numbered parts in order.\n\n"
            "📱 **Android**\n"
            "Use a file archive application that supports "
            "multi-part archives/files. Select the first part "
            "and follow the application's extraction instructions.\n\n"
            "🐧 **Linux / macOS**\n"
            "For raw binary parts, you can join them with:\n\n"
            "`cat filename.part* > output_file`\n\n"
            "⚠️ **Important**\n"
            "Do not rename the individual parts before joining them.\n"
            "Make sure every part is completely downloaded and "
            "that the numbering is correct."
        )

        await query.message.edit_text(
            tutorial_text,
            reply_markup=keyboard,
        )

    # --------------------------------------------------------
    # PREMIUM / UPGRADE
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # SETTINGS
    # --------------------------------------------------------

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
                        "🏷️ Metadata",
                        callback_data="metadata_settings",
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
            "⚙️ **AniToon Settings**\n\n"
            f"🖼️ **Thumbnail:** "
            f"{'✅ Saved' if thumb else '❌ Not Set'}\n"
            f"📝 **Caption:** "
            f"{'✅ Saved' if caption else '❌ Not Set'}\n\n"
            "Choose a setting below:",
            reply_markup=keyboard,
        )

    # --------------------------------------------------------
    # THUMBNAIL SETTINGS
    # --------------------------------------------------------

    elif data == "thumb_settings":
        thumb = await db.get_thumbnail(user_id)

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

        await query.message.edit_text(
            "🖼️ **Thumbnail Settings**\n\n"
            f"**Status:** "
            f"{'✅ Saved' if thumb else '❌ Not Set'}\n\n"
            "Send an image to set or replace your permanent thumbnail.",
            reply_markup=keyboard,
        )

    # --------------------------------------------------------
    # CAPTION SETTINGS
    # --------------------------------------------------------

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

        current_caption = (
            f"`{caption}`"
            if caption
            else "❌ Not Set"
        )

        await query.message.edit_text(
            "📝 **Caption Settings**\n\n"
            f"**Current Caption:**\n{current_caption}\n\n"
            "Use `/set_caption` to create or change your caption.",
            reply_markup=keyboard,
        )

    # --------------------------------------------------------
    # DELETE THUMBNAIL
    # --------------------------------------------------------

    elif data == "del_thumb":
        await db.set_thumbnail(
            user_id,
            None,
        )

        await query.message.edit_text(
            "🗑️ **Permanent Thumbnail Deleted.**\n\n"
            "Send a new image whenever you want to set another thumbnail.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "⬅️ Back",
                            callback_data="thumb_settings",
                        )
                    ]
                ]
            ),
        )

    # --------------------------------------------------------
    # METADATA SETTINGS
    # --------------------------------------------------------

    elif data == "metadata_settings":
        await query.answer(
            "Use /metadata to manage track names.",
            show_alert=True,
        )
        return

    # --------------------------------------------------------
    # CAPTION HELP
    # --------------------------------------------------------

    elif data == "help_caption":
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "⬅️ Back",
                        callback_data="caption_settings",
                    )
                ]
            ]
        )

        await query.message.edit_text(
            "📝 **Caption Help**\n\n"
            "You can use these placeholders:\n\n"
            "• `{filename}` — File name\n"
            "• `{filesize}` — File size\n"
            "• `{duration}` — Video duration\n\n"
            "**Example:**\n"
            "`🎬 {filename}`\n"
            "`📦 {filesize}`\n"
            "`⏱️ {duration}`",
            reply_markup=keyboard,
        )

    # --------------------------------------------------------
    # DELETE CAPTION
    # --------------------------------------------------------

    elif data == "del_caption":
        await db.set_caption(
            user_id,
            None,
        )

        await query.message.edit_text(
            "🗑️ **Custom Caption Deleted.**\n\n"
            "Your files will now use the default caption.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "⬅️ Back",
                            callback_data="caption_settings",
                        )
                    ]
                ]
            ),
        )

    # --------------------------------------------------------
    # UNKNOWN CALLBACK
    # --------------------------------------------------------

    else:
        await query.answer(
            "This option is not available.",
            show_alert=True,
        )
        return

    await query.answer()
