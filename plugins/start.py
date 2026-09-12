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


# ============================================================
# MAIN MENU
# ============================================================

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
            [
                InlineKeyboardButton(
                    "🤖 Create Clone",
                    callback_data="create_clone",
                )
            ],
        ]
    )


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

    # ========================================================
    # REGISTER USER
    # ========================================================

    if not await db.is_user_exist(
        user_id
    ):
        await db.add_user(
            user_id
        )

    # ========================================================
    # CLONE PAYMENT DEEP LINK
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
        except (
            ValueError,
            IndexError,
        ):
            target_bot_id = bot_id

        buttons = [
            [
                InlineKeyboardButton(
                    "⚡ Pro — 10 ⭐",
                    callback_data=(
                        f"buy:pro:"
                        f"{target_bot_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "💎 Premium — 20 ⭐",
                    callback_data=(
                        f"buy:premium:"
                        f"{target_bot_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "👑 Ultra — 30 ⭐",
                    callback_data=(
                        f"buy:ultra:"
                        f"{target_bot_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Back",
                    callback_data="start",
                )
            ],
        ]

        await message.reply_text(
            "💎 **AniToon Premium Plans**\n\n"
            "Choose a plan for 30 days:\n\n"
            "🆓 **Free**\n"
            "⭐ 0 Stars\n"
            "📊 10 GB/day\n\n"
            "⚡ **Pro**\n"
            "⭐ 10 Stars\n"
            "📊 20 GB/day\n\n"
            "💎 **Premium**\n"
            "⭐ 20 Stars\n"
            "📊 40 GB/day\n\n"
            "👑 **Ultra**\n"
            "⭐ 30 Stars\n"
            "📊 60 GB/day\n\n"
            "✂️ Large files are split into parts "
            "when required.",
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
                    "🚫 **Access Denied**\n\n"
                    "You are banned from using this bot."
                )

        except Exception:
            pass

    # ========================================================
    # GET USER PLAN
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
    # WELCOME MESSAGE
    # ========================================================

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

    # ========================================================
    # START IMAGE
    # ========================================================

    if getattr(
        Config,
        "START_PIC",
        "",
    ):
        try:
            await message.reply_photo(
                photo=Config.START_PIC,
                caption=welcome_text,
                reply_markup=main_menu(),
            )

            return

        except Exception as e:
            print(
                f"Start image error: {e}"
            )

    # ========================================================
    # NORMAL START MESSAGE
    # ========================================================

    await message.reply_text(
        welcome_text,
        reply_markup=main_menu(),
    )
