from pyrogram import Client, filters
from pyrogram.types import Message

from config import Config
from helper.database import db
from helper.plans import get_plan
from helper.utils import humanbytes
from plugins.ui import main_menu


# ============================================================
# /START
# ============================================================

@Client.on_message(
    filters.private
    & filters.command("start")
)
async def start(
    client: Client,
    message: Message,
):
    user_id = message.from_user.id

    bot_id = int(
        getattr(
            client,
            "bot_id",
            0,
        )
    )

    # Register user once.
    if not await db.is_user_exist(user_id):
        await db.add_user(user_id)

    # --------------------------------------------------------
    # Main bot deep-link from clone payment button.
    # Example: /start plans_123456
    # --------------------------------------------------------
    if (
        getattr(client, "is_main_bot", False)
        and len(message.command) > 1
        and message.command[1].startswith("plans_")
    ):
        try:
            target_bot_id = int(
                message.command[1].split("_", 1)[1]
            )
        except (ValueError, IndexError):
            target_bot_id = bot_id

        from helper.plans import all_paid_plans
        from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        buttons = []

        for plan_option in all_paid_plans():
            buttons.append(
                [
                    InlineKeyboardButton(
                        f"{plan_option.name} — {plan_option.stars} ⭐",
                        callback_data=(
                            f"buy:{plan_option.key}:"
                            f"{target_bot_id}"
                        ),
                    )
                ]
            )

        buttons.append(
            [
                InlineKeyboardButton(
                    "⬅️ Back",
                    callback_data="start",
                )
            ]
        )

        await message.reply_text(
            "💎 **AniToon Premium Plans**\n\n"
            "Choose a plan for 30 days:\n\n"
            "🆓 **Free** — 0 ⭐ — 10 GB/day\n"
            "⚡ **Pro** — 10 ⭐ — 20 GB/day\n"
            "💎 **Premium** — 20 ⭐ — 40 GB/day\n"
            "👑 **Ultra** — 30 ⭐ — 60 GB/day\n\n"
            "⭐ Payment is handled by AniToon_1Bot.",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

        return

    # --------------------------------------------------------
    # Force-subscription check.
    # We only block when Telegram positively reports the user
    # is not a member. If the bot cannot inspect the channel,
    # do not break normal bot operation.
    # --------------------------------------------------------
    if Config.FORCE_SUB:
        try:
            member = await client.get_chat_member(
                Config.FORCE_SUB,
                user_id,
            )

            blocked_statuses = {
                "left",
                "kicked",
            }

            if str(member.status).lower() in blocked_statuses:
                await message.reply_text(
                    "🚫 **Access Denied**\n\n"
                    "Please join the required channel and then "
                    "send `/start` again."
                )
                return

        except Exception:
            pass

    subscription = await db.get_subscription(
        user_id,
        bot_id,
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

    welcome_text = (
        "🔥 **Welcome to AniToon Bot** 🔥\n\n"
        f"👋 Hello **{message.from_user.first_name}**!\n\n"
        "📂 Send me any file, video or audio "
        "to rename and process it.\n\n"
        f"💎 **Plan:** {plan.name}\n"
        f"🚀 **Used Today:** "
        f"`{humanbytes(used)}`\n"
        f"⏳ **Remaining:** "
        f"`{humanbytes(remaining)}`\n\n"
        "✂️ Large files are automatically split "
        "into smaller parts when required."
    )

    is_main = getattr(
        client,
        "is_main_bot",
        False,
    )

    keyboard = main_menu(is_main)

    start_pic = getattr(
        Config,
        "START_PIC",
        "",
    )

    if start_pic:
        try:
            await message.reply_photo(
                photo=start_pic,
                caption=welcome_text,
                reply_markup=keyboard,
            )
            return
        except Exception:
            pass

    await message.reply_text(
        welcome_text,
        reply_markup=keyboard,
    )
