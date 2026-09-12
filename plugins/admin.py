from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

from config import Config
from helper.database import db
from helper.plans import get_plan
from helper.utils import humanbytes


@Client.on_callback_query(
    filters.regex(
        r"^(start|help|about|settings)$"
    )
)
async def navigation(
    client: Client,
    query: CallbackQuery,
):
    data = query.data
    user_id = query.from_user.id

    await query.answer()

    if data == "start":
        bot_id = getattr(
            client,
            "bot_id",
            0,
        )

        subscription = (
            await db.get_subscription(
                user_id,
                bot_id,
            )
        )

        plan = get_plan(
            subscription.get(
                "plan",
                "free",
            )
        )

        used = await db.get_usage(
            user_id,
            bot_id,
        )

        remaining = max(
            plan.daily_limit - used,
            0,
        )

        await query.message.edit_text(
            "🔥 **Welcome to AniToon Bot** 🔥\n\n"
            f"💎 **Plan:** {plan.name}\n"
            f"🚀 **Used Today:** "
            f"`{humanbytes(used)}`\n"
            f"⏳ **Remaining:** "
            f"`{humanbytes(remaining)}`\n\n"
            "Select an option below:",
            reply_markup=InlineKeyboardMarkup(
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
            ),
        )

    elif data == "help":
        await query.message.edit_text(
            "❓ **AniToon Help**\n\n"
            "📂 Send a file or video.\n"
            "✏️ Enter the new filename.\n"
            "🏷️ Metadata is processed automatically.\n"
            "🖼️ Custom thumbnails are supported.\n"
            "📝 Custom captions are supported.\n"
            "✂️ Large files can be split into parts.\n\n"
            "💎 Use **Buy Premium** to view the plans.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🧩 How to Join Parts",
                            callback_data="how_to_join",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "⬅️ Back",
                            callback_data="start",
                        )
                    ],
                ]
            ),
        )

    elif data == "about":
        await query.message.edit_text(
            "🤖 **AniToon Bot**\n\n"
            "📂 File Renaming ✅\n"
            "🏷️ Metadata Processing ✅\n"
            "🖼️ Thumbnail Support ✅\n"
            "📝 Caption Support ✅\n"
            "✂️ File Splitting ✅\n"
            "⭐ Telegram Stars Payments ✅\n\n"
            "👤 **Developer:** @AniToon_Official",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "⬅️ Back",
                            callback_data="start",
                        )
                    ]
                ]
            ),
        )

    elif data == "settings":
        thumb = await db.get_thumbnail(
            user_id
        )

        caption = await db.get_caption(
            user_id
        )

        await query.message.edit_text(
            "⚙️ **AniToon Settings**\n\n"
            f"🖼️ **Thumbnail:** "
            f"{'✅ Saved' if thumb else '❌ Not Set'}\n"
            f"📝 **Caption:** "
            f"{'✅ Saved' if caption else '❌ Not Set'}\n\n"
            "Use the available commands to change "
            "your settings.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "⬅️ Back",
                            callback_data="start",
                        )
                    ]
                ]
            ),
        )


@Client.on_callback_query(
    filters.regex("^how_to_join$")
)
async def how_to_join(
    client,
    query,
):
    await query.answer()

    await query.message.edit_text(
        "🧩 **How to Join Split Parts**\n\n"
        "1️⃣ Download **ALL parts**.\n"
        "2️⃣ Keep them in the same folder.\n"
        "3️⃣ Keep their original numbering.\n\n"
        "🐧 **Linux / macOS:**\n"
        "`cat filename.part* > output_file`\n\n"
        "⚠️ The generated parts are raw binary parts, "
        "not a ZIP/RAR archive.",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "⬅️ Back",
                        callback_data="help",
                    )
                ]
            ]
        ),
    )
