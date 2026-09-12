from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
)

from config import Config
from helper.database import db
from helper.plans import get_plan
from helper.utils import humanbytes


def main_menu():
    return InlineKeyboardMarkup(
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


@Client.on_message(
    filters.private
    & filters.command("start")
)
async def start(
    client: Client,
    message: Message,
):
    user_id = message.from_user.id
    bot_id = getattr(
        client,
        "bot_id",
        0,
    )

    if not await db.is_user_exist(
        user_id
    ):
        await db.add_user(
            user_id
        )

    # ========================================================
    # CLONE -> MAIN BOT PLAN PAGE
    # ========================================================

    if (
        getattr(
            client,
            "is_main_bot",
            False,
        )
        and len(message.command) > 1
        and message.command[1].startswith(
            "plans_"
        )
    ):
        try:
            target_bot_id = int(
                message.command[1].split(
                    "_",
                    1,
                )[1]
            )
        except ValueError:
            target_bot_id = bot_id

        from helper.plans import all_paid_plans

        buttons = []

        for plan in all_paid_plans():
            buttons.append(
                [
                    InlineKeyboardButton(
                        (
                            f"{plan.name} — "
                            f"{plan.stars} ⭐"
                        ),
                        callback_data=(
                            f"buy:{plan.key}:"
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
            "Choose your 30-day plan:\n\n"
            "🆓 **Free** — 0 ⭐ — 10 GB/day\n"
            "⚡ **Pro** — 10 ⭐ — 20 GB/day\n"
            "💎 **Premium** — 20 ⭐ — 40 GB/day\n"
            "👑 **Ultra** — 30 ⭐ — 60 GB/day\n\n"
            "⭐ Payment is handled by AniToon_1Bot.",
            reply_markup=InlineKeyboardMarkup(
                buttons
            ),
        )

        return

    # ========================================================
    # FORCE SUBSCRIBE
    # ========================================================

    if Config.FORCE_SUB:
        try:
            member = (
                await client.get_chat_member(
                    Config.FORCE_SUB,
                    user_id,
                )
            )

            if member.status == "kicked":
                return await message.reply_text(
                    "🚫 **Access Denied**"
                )

        except Exception:
            pass

    # ========================================================
    # PLAN STATUS
    # ========================================================

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

    # ========================================================
    # WELCOME
    # ========================================================

    text = (
        "🔥 **Welcome to AniToon Bot** 🔥\n\n"
        f"Hi **{message.from_user.first_name}**!\n\n"
        "📂 Send me a file or video to rename it.\n\n"
        f"💎 **Plan:** {plan.name}\n"
        f"🚀 **Used Today:** "
        f"`{humanbytes(used)}`\n"
        f"⏳ **Remaining:** "
        f"`{humanbytes(remaining)}`\n\n"
        "✂️ Large files are automatically split "
        "into parts when necessary."
    )

    if getattr(
        Config,
        "START_PIC",
        "",
    ):
        await message.reply_photo(
            photo=Config.START_PIC,
            caption=text,
            reply_markup=main_menu(),
        )
    else:
        await message.reply_text(
            text,
            reply_markup=main_menu(),
        )
