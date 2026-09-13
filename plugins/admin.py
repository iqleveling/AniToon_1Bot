import os
import sys
import asyncio

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import Config
from helper.database import db
from helper.plans import PLANS, get_plan


# The configured OWNER_ID is always treated as a full bot owner.
# Existing ADMIN users keep their current administrator access.
OWNER_AND_ADMINS = sorted(
    set(
        list(Config.ADMIN)
        + ([Config.OWNER_ID] if Config.OWNER_ID else [])
    )
)


def main_bot_only(client):
    return getattr(client, "is_main_bot", False)


def owner_only(user_id: int) -> bool:
    return bool(Config.OWNER_ID and int(user_id) == int(Config.OWNER_ID))


@Client.on_message(
    filters.private
    & filters.command("owner")
    & filters.user(OWNER_AND_ADMINS)
)
async def owner_panel(client, message):
    """Owner/admin control panel without exposing controls to normal users."""
    if not main_bot_only(client):
        return

    if not owner_only(message.from_user.id):
        return await message.reply_text(
            "⛔ **Owner only.**\n\nYour account is an administrator, but this panel is reserved for the bot creator."
        )

    await message.reply_text(
        "👑 **AniToon Owner Control Panel**\n\n"
        "You have full owner access to the main bot.\n\n"
        "📊 `/users` — user statistics\n"
        "💎 `/setplan <user_id> <plan>` — change a user's plan\n"
        "📣 `/broadcast` — broadcast a replied message\n"
        "🚫 `/ban <user_id>` — ban a user\n"
        "✅ `/unban <user_id>` — unban a user\n"
        "🔄 `/restart` — restart the bot\n"
        "🤖 `/clone` — create a clone bot\n\n"
        "Only the configured `OWNER_ID` can use this owner panel."
    )


@Client.on_message(
    filters.private
    & filters.command("users")
    & filters.user(OWNER_AND_ADMINS)
)
async def users_stats(client, message):
    if not main_bot_only(client):
        return

    count = await db.total_users_count()
    await message.reply_text(
        "📊 **AniToon Statistics**\n\n"
        f"👥 **Users:** `{count}`"
    )


@Client.on_message(
    filters.private
    & filters.command("setplan")
    & filters.user(OWNER_AND_ADMINS)
)
async def set_user_plan(client, message):
    if not main_bot_only(client):
        return

    if len(message.command) < 3:
        return await message.reply_text(
            "❌ **Usage:**\n"
            "`/setplan <user_id> <free|pro|premium|ultra>`"
        )

    try:
        user_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("❌ Invalid user ID.")

    plan_key = message.command[2].lower()
    if plan_key not in PLANS:
        return await message.reply_text(
            "❌ Invalid plan.\n\n"
            "Available:\n"
            "`free`\n`pro`\n`premium`\n`ultra`"
        )

    if not await db.is_user_exist(user_id):
        await db.add_user(user_id)

    await db.set_plan(
        user_id=user_id,
        bot_id=client.bot_id,
        plan_key=plan_key,
        stars_paid=0,
        payment_id="admin",
    )

    plan = get_plan(plan_key)
    await message.reply_text(
        "✅ **Plan Updated**\n\n"
        f"👤 User: `{user_id}`\n"
        f"💎 Plan: {plan.name}\n"
        f"📊 Daily Limit: `{plan.daily_limit}` bytes"
    )


@Client.on_message(
    filters.private
    & filters.command("broadcast")
    & filters.user(OWNER_AND_ADMINS)
)
async def broadcast(client, message):
    if not main_bot_only(client):
        return

    if not message.reply_to_message:
        return await message.reply_text(
            "❌ Reply to the message you want to broadcast."
        )

    status = await message.reply_text("📣 **Broadcast Started...**")
    success = 0
    failed = 0

    cursor = db.get_all_users()
    async for user in cursor:
        user_id = user.get("id")
        if not user_id:
            continue
        try:
            await message.reply_to_message.copy(chat_id=user_id)
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    await status.edit_text(
        "📣 **Broadcast Complete**\n\n"
        f"✅ Sent: `{success}`\n"
        f"❌ Failed: `{failed}`"
    )


@Client.on_message(
    filters.private
    & filters.command("ban")
    & filters.user(OWNER_AND_ADMINS)
)
async def ban(client, message):
    if not main_bot_only(client):
        return

    if len(message.command) < 2:
        return await message.reply_text("`/ban <user_id>`")

    try:
        user_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("❌ Invalid user ID.")

    await db.ban_user(user_id)
    await message.reply_text(f"🚫 User `{user_id}` banned.")


@Client.on_message(
    filters.private
    & filters.command("unban")
    & filters.user(OWNER_AND_ADMINS)
)
async def unban(client, message):
    if not main_bot_only(client):
        return

    if len(message.command) < 2:
        return await message.reply_text("`/unban <user_id>`")

    try:
        user_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("❌ Invalid user ID.")

    await db.unban_user(user_id)
    await message.reply_text(f"✅ User `{user_id}` unbanned.")


@Client.on_message(
    filters.private
    & filters.command("restart")
    & filters.user(OWNER_AND_ADMINS)
)
async def restart(client, message):
    if not main_bot_only(client):
        return

    await message.reply_text("🔄 **AniToon_1Bot restarting...**")
    await asyncio.sleep(1)
    os.execl(sys.executable, sys.executable, *sys.argv)
