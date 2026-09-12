import os
import sys
import asyncio

from pyrogram import Client, filters

from config import Config
from helper.database import db
from helper.plans import PLANS, get_plan


def main_bot_only(client):
    return getattr(
        client,
        "is_main_bot",
        False,
    )


@Client.on_message(
    filters.private
    & filters.command("users")
    & filters.user(Config.ADMIN)
)
async def users_stats(
    client,
    message,
):
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
    & filters.user(Config.ADMIN)
)
async def set_user_plan(
    client,
    message,
):
    if not main_bot_only(client):
        return

    if len(message.command) < 3:
        return await message.reply_text(
            "❌ **Usage:**\n"
            "`/setplan <user_id> <free|pro|premium|ultra>`"
        )

    try:
        user_id = int(
            message.command[1]
        )
    except ValueError:
        return await message.reply_text(
            "❌ Invalid user ID."
        )

    plan_key = (
        message.command[2]
        .lower()
    )

    if plan_key not in PLANS:
        return await message.reply_text(
            "❌ Invalid plan.\n\n"
            "Available:\n"
            "`free`\n"
            "`pro`\n"
            "`premium`\n"
            "`ultra`"
        )

    if not await db.is_user_exist(
        user_id
    ):
        await db.add_user(
            user_id
        )

    await db.set_plan(
        user_id=user_id,
        bot_id=client.bot_id,
        plan_key=plan_key,
        stars_paid=0,
        payment_id="admin",
    )

    plan = get_plan(
        plan_key
    )

    await message.reply_text(
        "✅ **Plan Updated**\n\n"
        f"👤 User: `{user_id}`\n"
        f"💎 Plan: {plan.name}\n"
        f"📊 Daily Limit: "
        f"`{plan.daily_limit}` bytes"
    )


@Client.on_message(
    filters.private
    & filters.command("broadcast")
    & filters.user(Config.ADMIN)
)
async def broadcast(
    client,
    message,
):
    if not main_bot_only(client):
        return

    if not message.reply_to_message:
        return await message.reply_text(
            "❌ Reply to the message you want to broadcast."
        )

    status = await message.reply_text(
        "📣 **Broadcast Started...**"
    )

    success = 0
    failed = 0

    cursor = await db.get_all_users()

    async for user in cursor:
        user_id = user.get(
            "id"
        )

        if not user_id:
            continue

        try:
            await message.reply_to_message.copy(
                chat_id=user_id
            )

            success += 1

            await asyncio.sleep(
                0.05
            )

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
    & filters.user(Config.ADMIN)
)
async def ban(
    client,
    message,
):
    if not main_bot_only(client):
        return

    if len(message.command) < 2:
        return await message.reply_text(
            "`/ban <user_id>`"
        )

    try:
        user_id = int(
            message.command[1]
        )
    except ValueError:
        return await message.reply_text(
            "❌ Invalid user ID."
        )

    await db.ban_user(
        user_id
    )

    await message.reply_text(
        f"🚫 User `{user_id}` banned."
    )


@Client.on_message(
    filters.private
    & filters.command("unban")
    & filters.user(Config.ADMIN)
)
async def unban(
    client,
    message,
):
    if not main_bot_only(client):
        return

    if len(message.command) < 2:
        return await message.reply_text(
            "`/unban <user_id>`"
        )

    try:
        user_id = int(
            message.command[1]
        )
    except ValueError:
        return await message.reply_text(
            "❌ Invalid user ID."
        )

    await db.unban_user(
        user_id
    )

    await message.reply_text(
        f"✅ User `{user_id}` unbanned."
    )


@Client.on_message(
    filters.private
    & filters.command("restart")
    & filters.user(Config.ADMIN)
)
async def restart(
    client,
    message,
):
    if not main_bot_only(client):
        return

    await message.reply_text(
        "🔄 **AniToon_1Bot restarting...**"
    )

    await asyncio.sleep(
        1
    )

    os.execl(
        sys.executable,
        sys.executable,
        *sys.argv,
    )
