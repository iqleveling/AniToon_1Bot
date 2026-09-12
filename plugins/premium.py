from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ForceReply,
)

from config import Config
from helper.database import db
from helper.utils import humanbytes


# ============================================================
# USER PLAN
# ============================================================

@Client.on_message(
    filters.private
    & filters.command(
        ["myplan", "plan", "status"]
    )
)
async def user_plan_status(
    client: Client,
    message: Message,
):
    user_id = message.from_user.id

    if not await db.is_user_exist(
        user_id
    ):
        await db.add_user(
            user_id
        )

    user_data = await db.get_user_data(
        user_id
    )

    if not user_data:
        return await message.reply_text(
            "❌ Unable to load your account."
        )

    used = await db.get_usage(
        user_id
    )

    is_premium = user_data.get(
        "is_premium",
        False,
    )

    if is_premium:
        remaining = "♾️ Unlimited"
        tier = "PROMAX PREMIUM"
    else:
        remaining = humanbytes(
            max(
                Config.DAILY_LIMIT - used,
                0,
            )
        )
        tier = "FREE TIER"

    text = (
        "📊 **AniToon Subscription**\n\n"
        f"👤 **User:** "
        f"`{message.from_user.first_name}`\n"
        f"🆔 **ID:** `{user_id}`\n\n"
        f"💎 **Tier:** `{tier}`\n"
        f"📈 **Used Today:** "
        f"`{humanbytes(used)}`\n"
        f"⏳ **Remaining:** "
        f"`{remaining}`"
    )

    keyboard = None

    if not is_premium:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "💎 Upgrade",
                        callback_data="upgrade",
                    )
                ]
            ]
        )

    await message.reply_text(
        text,
        reply_markup=keyboard,
    )


# ============================================================
# CLONE BUTTON / COMMAND
# MAIN BOT ONLY
# ============================================================

@Client.on_message(
    filters.private
    & filters.command("clone")
)
async def initiate_clone(
    client: Client,
    message: Message,
):
    if not getattr(
        client,
        "is_main_bot",
        False,
    ):
        return await message.reply_text(
            "❌ Clone creation is available "
            "only from the main AniToon bot."
        )

    if not Config.IS_CLONE_ALLOWED:
        return await message.reply_text(
            "❌ **Clone Engine Disabled**"
        )

    user_id = message.from_user.id

    if not await db.is_user_exist(
        user_id
    ):
        await db.add_user(
            user_id
        )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "❌ Cancel",
                    callback_data="start",
                )
            ]
        ]
    )

    await message.reply_text(
        "🤖 **Create Your AniToon Clone**\n\n"
        "1️⃣ Open **@BotFather**.\n"
        "2️⃣ Create a new Telegram bot.\n"
        "3️⃣ Copy the Bot Token.\n"
        "4️⃣ Reply to this message with the token.\n\n"
        "Your clone will run as a normal Telegram bot "
        "and use the AniToon features.\n\n"
        "⚠️ Keep your bot token private.",
        reply_markup=ForceReply(
            selective=True
        ),
    )


# ============================================================
# PROCESS BOT TOKEN
# MAIN BOT ONLY
# ============================================================

@Client.on_message(
    filters.private
    & filters.reply
    & filters.text
)
async def process_clone_token(
    client: Client,
    message: Message,
):
    if not getattr(
        client,
        "is_main_bot",
        False,
    ):
        return

    reply = message.reply_to_message

    if not reply:
        return

    if not reply.text:
        return

    if (
        "Create Your AniToon Clone"
        not in reply.text
    ):
        return

    token = message.text.strip()
    owner_id = message.from_user.id

    if (
        ":" not in token
        or len(token) < 20
    ):
        return await message.reply_text(
            "❌ **Invalid Bot Token**\n\n"
            "Please send the token generated "
            "by @BotFather."
        )

    status = await message.reply_text(
        "🔄 **Verifying your bot token...**"
    )

    try:
        test_client = Client(
            name=(
                f"verify_"
                f"{owner_id}"
            ),
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=token,
            in_memory=True,
        )

        await test_client.start()

        bot_info = (
            await test_client.get_me()
        )

        await test_client.stop()

        # --------------------------------------------------------
        # CHECK EXISTING CLONE
        # --------------------------------------------------------

        existing = (
            await db.get_clone_by_bot_id(
                bot_info.id
            )
        )

        if existing:
            return await status.edit_text(
                "⚠️ **This bot is already connected.**"
            )

        # --------------------------------------------------------
        # START REAL CLONE
        # --------------------------------------------------------

        if not client.clone_manager:
            return await status.edit_text(
                "❌ **Clone Manager is unavailable.**"
            )

        clone = (
            await client.clone_manager.add_clone(
                owner_id,
                token,
            )
        )

        if not clone:
            return await status.edit_text(
                "❌ **Clone could not be started.**"
            )

        await status.edit_text(
            "✅ **Clone Created Successfully!**\n\n"
            f"🤖 **Bot:** "
            f"@{bot_info.username}\n"
            f"🆔 **Bot ID:** "
            f"`{bot_info.id}`\n\n"
            "🟢 **Status:** Online\n\n"
            "Your clone now runs as an "
            "AniToon-style bot."
        )

    except Exception as e:
        try:
            await test_client.stop()
        except Exception:
            pass

        await status.edit_text(
            "❌ **Clone Creation Failed**\n\n"
            f"`{str(e)[:1000]}`"
        )
