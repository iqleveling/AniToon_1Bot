from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ForceReply,
)

from config import Config
from helper.database import db
from helper.plans import get_plan
from helper.utils import humanbytes
from plugins.ui import (
    main_menu,
    settings_menu,
    help_menu,
    thumbnail_menu,
    edit_callback_message,
)


# ============================================================
# HOME
# ============================================================

@Client.on_callback_query(
    filters.regex(r"^start$")
)
async def cb_start(
    client: Client,
    callback_query,
):
    await callback_query.answer()

    user_id = callback_query.from_user.id
    bot_id = int(getattr(client, "bot_id", 0))

    if not await db.is_user_exist(user_id):
        await db.add_user(user_id)

    subscription = await db.get_subscription(
        user_id,
        bot_id,
    )

    plan = get_plan(
        subscription.get("plan", "free")
    )

    used = await db.get_usage(
        user_id,
        bot_id,
    )

    remaining = max(
        plan.daily_limit - used,
        0,
    )

    text = (
        "🔥 **Welcome to AniToon Bot** 🔥\n\n"
        f"👋 Hello **{callback_query.from_user.first_name}**!\n\n"
        "📂 Send me any file, video or audio "
        "to rename and process it.\n\n"
        f"💎 **Plan:** {plan.name}\n"
        f"🚀 **Used Today:** `{humanbytes(used)}`\n"
        f"⏳ **Remaining:** `{humanbytes(remaining)}`\n\n"
        "✂️ Large files are automatically split "
        "when required."
    )

    try:
        await edit_callback_message(
            callback_query,
            text,
            reply_markup=main_menu(
                getattr(
                    client,
                    "is_main_bot",
                    False,
                )
            ),
        )
    except Exception:
        # A start image message cannot be converted to text.
        await client.send_message(
            user_id,
            text,
            reply_markup=main_menu(
                getattr(
                    client,
                    "is_main_bot",
                    False,
                )
            ),
        )


# ============================================================
# HELP
# ============================================================

@Client.on_callback_query(
    filters.regex(r"^help$")
)
async def cb_help(
    client: Client,
    callback_query,
):
    await callback_query.answer()

    await edit_callback_message(
        callback_query,
        "🛠 **AniToon Help & Usage**\n\n"
        "📂 **Rename:** Send a document, video or audio file "
        "and reply with the new filename.\n\n"
        "🖼 **Thumbnail:** Send an image to save it as your "
        "custom thumbnail.\n\n"
        "📝 **Caption:** Use `/setcaption` or the Settings menu "
        "to save a caption template.\n\n"
        "🏷 **Metadata:** Use `/metadata` to change audio and "
        "subtitle track names.\n\n"
        "💎 **Premium:** Use `/plan` or the Plans button to "
        "view your daily quota and upgrade.\n\n"
        "🤖 **Clone:** The main bot owner can create clone bots "
        "with `/clone`.",
        reply_markup=help_menu(),
    )


# ============================================================
# ABOUT
# ============================================================

@Client.on_callback_query(
    filters.regex(r"^about$")
)
async def cb_about(
    client: Client,
    callback_query,
):
    await callback_query.answer()

    await edit_callback_message(
        callback_query,
        "ℹ️ **About AniToon Promax**\n\n"
        "AniToon Promax Edition is a Telegram file "
        "rename and media-processing bot.\n\n"
        "✅ File renaming\n"
        "✅ Custom captions\n"
        "✅ Custom thumbnails\n"
        "✅ Metadata branding\n"
        "✅ Daily usage limits\n"
        "✅ Telegram Stars Premium plans\n"
        "✅ Clone bot system\n\n"
        "Built for Python 3.11 + Pyrogram 2.0.106 + MongoDB.",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔙 Back",
                        callback_data="start",
                    )
                ]
            ]
        ),
    )


# ============================================================
# SETTINGS
# ============================================================

@Client.on_callback_query(
    filters.regex(r"^settings$")
)
async def cb_settings(
    client: Client,
    callback_query,
):
    await callback_query.answer()

    user_id = callback_query.from_user.id

    await edit_callback_message(
        callback_query,
        "⚙️ **AniToon Settings**\n\n"
        "Choose what you want to manage:",
        reply_markup=settings_menu(),
    )


# ============================================================
# CAPTION SETTINGS
# ============================================================

@Client.on_callback_query(
    filters.regex(r"^settings_caption$")
)
async def cb_settings_caption(
    client: Client,
    callback_query,
):
    await callback_query.answer()

    caption = await db.get_caption(
        callback_query.from_user.id
    )

    if caption:
        text = (
            "📝 **Caption Settings**\n\n"
            "Current template:\n"
            f"`{caption}`\n\n"
            "Placeholders:\n"
            "`{filename}`  `{filesize}`  `{duration}`"
        )
    else:
        text = (
            "📝 **Caption Settings**\n\n"
            "No custom caption is currently saved."
        )

    await edit_callback_message(
        callback_query,
        text,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📝 Set / Change",
                        callback_data="set_caption_help",
                    ),
                    InlineKeyboardButton(
                        "🗑 Delete",
                        callback_data="del_caption",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "🔙 Back",
                        callback_data="settings",
                    )
                ],
            ]
        ),
    )


# ============================================================
# THUMBNAIL SETTINGS
# ============================================================

@Client.on_callback_query(
    filters.regex(r"^settings_thumb$")
)
async def cb_settings_thumb(
    client: Client,
    callback_query,
):
    await callback_query.answer()

    thumb = await db.get_thumbnail(
        callback_query.from_user.id
    )

    if thumb:
        text = (
            "🖼 **Thumbnail Settings**\n\n"
            "✅ A custom thumbnail is currently saved.\n\n"
            "Send a new image at any time to replace it."
        )
    else:
        text = (
            "🖼 **Thumbnail Settings**\n\n"
            "❌ No custom thumbnail is saved.\n\n"
            "Send an image to save one."
        )

    await edit_callback_message(
        callback_query,
        text,
        reply_markup=thumbnail_menu(),
    )


@Client.on_callback_query(
    filters.regex(r"^view_thumb$")
)
async def cb_view_thumb(
    client: Client,
    callback_query,
):
    await callback_query.answer()

    thumb = await db.get_thumbnail(
        callback_query.from_user.id
    )

    if not thumb:
        return await edit_callback_message(
            callback_query,
            "❌ **No custom thumbnail is saved.**\n\nSend an image to save one.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Back", callback_data="settings")]]
            ),
        )

    try:
        await client.send_photo(
            callback_query.from_user.id,
            thumb,
            caption="🖼 **Your current custom thumbnail.**",
        )
    except Exception:
        await callback_query.message.reply_text(
            "❌ Unable to display the saved thumbnail."
        )


@Client.on_callback_query(
    filters.regex(r"^delete_thumb$")
)
async def cb_delete_thumb(
    client: Client,
    callback_query,
):
    await db.set_thumbnail(
        callback_query.from_user.id,
        None,
    )

    await callback_query.answer(
        "Thumbnail deleted 🗑️",
        show_alert=True,
    )

    await edit_callback_message(
        callback_query,
        "🗑️ **Custom thumbnail deleted.**",
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
# CREATE CLONE BUTTON
# ============================================================

@Client.on_callback_query(
    filters.regex(r"^create_clone$")
)
async def cb_create_clone(
    client: Client,
    callback_query,
):
    if not getattr(
        client,
        "is_main_bot",
        False,
    ):
        return await callback_query.answer(
            "Clone creation is available only on the main bot.",
            show_alert=True,
        )

    if not Config.IS_CLONE_ALLOWED:
        return await callback_query.answer(
            "Clone Engine is disabled.",
            show_alert=True,
        )

    await callback_query.answer()

    await client.send_message(
        callback_query.from_user.id,
        "🤖 **Create Your AniToon Clone**\n\n"
        "1️⃣ Open @BotFather.\n"
        "2️⃣ Create a new bot.\n"
        "3️⃣ Copy the Bot Token.\n"
        "4️⃣ Reply to this message with the token.\n\n"
        "Your clone will have the normal AniToon features.\n\n"
        "⚠️ Never share your BotFather token publicly.",
        reply_markup=ForceReply(
            selective=True
        ),
    )


# ============================================================
# CAPTION HELP / SET
# ============================================================

@Client.on_callback_query(
    filters.regex(r"^set_caption_help$")
)
async def cb_set_caption_help(
    client: Client,
    callback_query,
):
    await callback_query.answer()

    await client.send_message(
        callback_query.from_user.id,
        "📝 **Enter your caption template.**\n\n"
        "Supported placeholders:\n"
        "`{filename}` — file name\n"
        "`{filesize}` — final file size\n"
        "`{duration}` — video duration\n\n"
        "Example:\n"
        "`🎥 {filename}\\n📦 {filesize}\\n⏱️ {duration}`",
        reply_markup=ForceReply(
            selective=True
        ),
    )


# ============================================================
# METADATA SETTINGS PAGE
# ============================================================

@Client.on_callback_query(
    filters.regex(r"^metadata_settings$")
)
async def cb_metadata_settings(
    client: Client,
    callback_query,
):
    await callback_query.answer()

    user = await db.get_user_data(
        callback_query.from_user.id
    )

    if not user:
        await db.add_user(
            callback_query.from_user.id
        )
        user = await db.get_user_data(
            callback_query.from_user.id
        )

    audio_name = user.get(
        "audio_name",
        "AniToon Official",
    )
    subtitle_name = user.get(
        "sub_name",
        "AniToon Official",
    )

    await edit_callback_message(
        callback_query,
        "🏷️ **AniToon Metadata Branding**\n\n"
        f"🎵 **Audio:** `{audio_name}`\n"
        f"📜 **Subtitle:** `{subtitle_name}`\n\n"
        "Choose an option:",
        reply_markup=InlineKeyboardMarkup(
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
                        "🔄 Reset",
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
        ),
    )
