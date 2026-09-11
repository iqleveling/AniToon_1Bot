from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
)
from pyrogram.errors import UserNotParticipant

from config import Config
from helper.database import db
from helper.utils import humanbytes


# --- /START COMMAND ---
@Client.on_message(
    filters.private & filters.command("start")
)
async def start(client: Client, message: Message):
    """
    Handles /start.
    Checks Force Subscribe, registers the user,
    and displays the main menu.
    """

    # --- Choice 4-B: FORCE SUBSCRIBE ---
    if Config.FORCE_SUB:
        try:
            member = await client.get_chat_member(
                Config.FORCE_SUB,
                message.from_user.id,
            )

            if member.status == "kicked":
                return await message.reply_text(
                    "🚫 **Access Denied**\n\n"
                    "You are banned from using this bot."
                )

        except UserNotParticipant:
            bot_username = (await client.get_me()).username

            join_button = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "📢 Join Channel",
                            url=f"https://t.me/{Config.FORCE_SUB}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🔄 Try Again",
                            url=f"https://t.me/{bot_username}?start=start",
                        )
                    ],
                ]
            )

            return await message.reply_text(
                f"👋 **Hello {message.from_user.first_name}!**\n\n"
                "To use **AniToon Promax Bot**, "
                "please join our updates channel first.\n\n"
                "After joining, tap **Try Again**.",
                reply_markup=join_button,
            )

        except Exception:
            pass

    # --- USER REGISTRATION ---
    user_id = message.from_user.id

    if not await db.is_user_exist(user_id):
        await db.add_user(user_id)

    # --- QUOTA INFORMATION ---
    user_data = await db.get_user_data(user_id)

    if not user_data:
        user_data = db.new_user(user_id)

    used = await db.get_usage(user_id)
    limit = Config.DAILY_LIMIT

    # Premium users do not have the normal free quota limit.
    is_premium = user_data.get("is_premium", False)

    if is_premium:
        remaining = None
    else:
        remaining = max(limit - used, 0)

    # --- MAIN MENU ---
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

    plan_status = (
        "💎 Premium"
        if is_premium
        else "🆓 Free"
    )

    remaining_text = (
        "♾️ Unlimited"
        if is_premium
        else humanbytes(remaining)
    )

    welcome_text = (
        "🔥 **Welcome to AniToon Promax Bot** 🔥\n\n"
        f"Hi **{message.from_user.first_name}**!\n\n"
        "I am your professional file renaming bot.\n"
        "Send me a file or video to get started.\n\n"
        f"📊 **Plan:** {plan_status}\n"
        f"🚀 **Used Today:** {humanbytes(used)}\n"
        f"⏳ **Remaining:** {remaining_text}\n\n"
        "⚡ Fast Processing\n"
        "🎬 Media Support\n"
        "📥 Easy Downloads"
    )

    # --- START IMAGE ---
    if getattr(Config, "START_PIC", ""):
        await message.reply_photo(
            photo=Config.START_PIC,
            caption=welcome_text,
            reply_markup=keyboard,
        )
    else:
        await message.reply_text(
            text=welcome_text,
            reply_markup=keyboard,
        )


# --- ADMIN: USER STATISTICS ---
@Client.on_message(
    filters.private
    & filters.command("users")
    & filters.user(Config.ADMIN)
)
async def users_stats(
    client: Client,
    message: Message,
):
    """
    Shows the total number of registered users.
    Admin only.
    """

    count = await db.total_users_count()

    await message.reply_text(
        "📊 **AniToon Promax Statistics**\n\n"
        f"👥 **Total Registered Users:** `{count}`"
    )
