from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def force_sub_menu():
    """Four channel buttons followed by one Check & Retry button."""
    links = list(getattr(__import__("config").Config, "FORCE_SUB_LINKS", []))[:4]
    rows = []

    for index in range(4):
        link = links[index] if index < len(links) else None
        if link:
            rows.append([
                InlineKeyboardButton(
                    f"📢 Channel {index + 1}",
                    url=link,
                )
            ])
        else:
            # Callback fallback keeps the button visible even if a link is
            # missing. The membership check still protects access.
            rows.append([
                InlineKeyboardButton(
                    f"📢 Channel {index + 1}",
                    callback_data=f"force_missing:{index + 1}",
                )
            ])

    rows.append([
        InlineKeyboardButton(
            "🔄 Check & Retry",
            callback_data="force_retry",
        )
    ])
    return InlineKeyboardMarkup(rows)


def main_menu(is_main_bot: bool = True):
    rows = [
        [
            InlineKeyboardButton("🛠 Help & Usage", callback_data="help"),
            InlineKeyboardButton("ℹ️ About Bot", callback_data="about"),
        ],
        [
            InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
            InlineKeyboardButton("💎 Buy Premium", callback_data="upgrade"),
        ],
    ]
    if is_main_bot:
        rows.append([
            InlineKeyboardButton(
                "🤖 Create Clone",
                callback_data="create_clone",
            )
        ])
    return InlineKeyboardMarkup(rows)


def settings_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📝 Caption", callback_data="settings_caption"),
            InlineKeyboardButton("🖼 Thumbnail", callback_data="settings_thumb"),
        ],
        [
            InlineKeyboardButton("🏷 Metadata", callback_data="metadata_settings"),
            InlineKeyboardButton("💎 Plan", callback_data="upgrade"),
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="start")],
    ])


def help_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
            InlineKeyboardButton("💎 Plans", callback_data="upgrade"),
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="start")],
    ])


def thumbnail_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👁 View Thumbnail", callback_data="view_thumb")],
        [InlineKeyboardButton("🗑 Delete Thumbnail", callback_data="delete_thumb")],
        [InlineKeyboardButton("🔙 Back", callback_data="settings")],
    ])


def file_action_menu(job_id: str):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✏️ Custom Rename",
                callback_data=f"job:rename:{job_id}",
            ),
            InlineKeyboardButton(
                "🤖 Auto Rename",
                callback_data=f"job:auto:{job_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                "🔄 Convert",
                callback_data=f"job:convert:{job_id}",
            ),
            InlineKeyboardButton(
                "🛠 Advanced Rename",
                callback_data=f"job:advanced:{job_id}",
            ),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data=f"job:cancel:{job_id}")],
    ])


def auto_preview_menu(job_id: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm", callback_data=f"job:confirmauto:{job_id}")],
        [
            InlineKeyboardButton(
                "✏️ Custom Rename",
                callback_data=f"job:rename:{job_id}",
            ),
            InlineKeyboardButton(
                "🔙 Back",
                callback_data=f"job:back:{job_id}",
            ),
        ],
    ])


def convert_menu(job_id: str):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎬 MP4", callback_data=f"job:format:{job_id}:mp4"),
            InlineKeyboardButton("🎞 MKV", callback_data=f"job:format:{job_id}:mkv"),
        ],
        [
            InlineKeyboardButton("🌐 WEBM", callback_data=f"job:format:{job_id}:webm"),
            InlineKeyboardButton("🎬 MOV", callback_data=f"job:format:{job_id}:mov"),
        ],
        [
            InlineKeyboardButton("🎵 MP3", callback_data=f"job:format:{job_id}:mp3"),
            InlineKeyboardButton("🎵 M4A", callback_data=f"job:format:{job_id}:m4a"),
        ],
        [InlineKeyboardButton("🔙 Back", callback_data=f"job:back:{job_id}")],
    ])


def advanced_menu(job_id: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Rename File", callback_data=f"job:advancedfile:{job_id}")],
        [InlineKeyboardButton("🎵 Rename Audio Tracks", callback_data=f"job:audio:{job_id}")],
        [InlineKeyboardButton("📜 Rename Subtitle Tracks", callback_data=f"job:subtitle:{job_id}")],
        [InlineKeyboardButton("✅ Process & Upload", callback_data=f"job:finishadvanced:{job_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"job:back:{job_id}")],
    ])


async def edit_callback_message(callback_query, text, reply_markup=None):
    message = callback_query.message
    try:
        return await message.edit_text(
            text,
            reply_markup=reply_markup,
        )
    except Exception:
        pass
    try:
        return await message.edit_caption(
            caption=text,
            reply_markup=reply_markup,
        )
    except Exception:
        pass
    return await message.reply_text(
        text,
        reply_markup=reply_markup,
    )
