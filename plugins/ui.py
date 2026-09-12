from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu(is_main_bot: bool = True):
    rows = [
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

    if is_main_bot:
        rows.append(
            [
                InlineKeyboardButton(
                    "🤖 Create Clone",
                    callback_data="create_clone",
                )
            ]
        )

    return InlineKeyboardMarkup(rows)


def settings_menu():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📝 Caption",
                    callback_data="settings_caption",
                ),
                InlineKeyboardButton(
                    "🖼 Thumbnail",
                    callback_data="settings_thumb",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🏷 Metadata",
                    callback_data="metadata_settings",
                ),
                InlineKeyboardButton(
                    "💎 Plan",
                    callback_data="upgrade",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔙 Back",
                    callback_data="start",
                )
            ],
        ]
    )


def help_menu():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "⚙️ Settings",
                    callback_data="settings",
                ),
                InlineKeyboardButton(
                    "💎 Plans",
                    callback_data="upgrade",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔙 Back",
                    callback_data="start",
                )
            ],
        ]
    )


def thumbnail_menu():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "👁 View Thumbnail",
                    callback_data="view_thumb",
                )
            ],
            [
                InlineKeyboardButton(
                    "🗑 Delete Thumbnail",
                    callback_data="delete_thumb",
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


async def edit_callback_message(
    callback_query,
    text,
    reply_markup=None,
):
    """
    Update a message created by the bot.

    Start screens can be either text or photo messages, so
    edit_text() is attempted first and edit_caption() is used
    for photo messages.
    """
    try:
        return await callback_query.message.edit_text(
            text,
            reply_markup=reply_markup,
        )
    except Exception:
        try:
            return await callback_query.message.edit_caption(
                caption=text,
                reply_markup=reply_markup,
            )
        except Exception:
            return await callback_query.message.reply_text(
                text,
                reply_markup=reply_markup,
            )
