import os
import sys
import asyncio

from pyrogram import Client, filters
from pyrogram.types import Message

from config import Config
from helper.database import db


# ============================================================
# MAIN BOT CHECK
# ============================================================

def main_bot_only(client):
    return getattr(
        client,
        "is_main_bot",
        False,
    )


# ============================================================
# USERS
# ============================================================

@Client.on_message(
    filters.private
    & filters.command("users")
    & filters.user(Config.ADMIN)
)
async def users_stats(
    client: Client,
    message: Message,
):
    if not main_bot_only(client):
        return

    count = await db.total_users_count()

    await message.reply_text(
        "📊 **AniToon Owner Statistics**\n\n"
        f"👥 **Total Users:** `{count}`"
    )


# ============================================================
# BROADCAST
# ============================================================

@Client.on_message(
    filters.private
    & filters.command("broadcast")
    & filters.user(Config.ADMIN)
)
async def broadcast_handler(
    client: Client,
    message: Message,
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

    async for user in await db.get_all_users():
        user_id = user.get("id")

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
        f"✅ **Sent:** `{success}`\n"
        f"❌ **Failed:** `{failed}`"
    )


# ============================================================
# PREMIUM
# ============================================================

@Client.on_message(
    filters.private
    & filters.command("addpremium")
    & filters.user(Config.ADMIN)
)
async def upgrade_user(
    client: Client,
    message: Message,
):
    if not main_bot_only(client):
        return

    if len(message.command) < 2:
        return await message.reply_text(
            "❌ **Usage:**\n"
            "`/addpremium <user_id>`"
        )

    try:
        user_id = int(
            message.command[1]
        )
    except ValueError:
        return await message.reply_text(
            "❌ Invalid user ID."
        )

    if not await db.is_user_exist(
        user_id
    ):
        return await message.reply_text(
            "❌ User is not registered."
        )

    await db.set_premium(
        user_id,
        True,
    )

    await message.reply_text(
        f"💎 User `{user_id}` "
        "**upgraded to Premium.**"
    )


@Client.on_message(
    filters.private
    & filters.command("remove_premium")
    & filters.user(Config.ADMIN)
)
async def downgrade_user(
    client: Client,
    message: Message,
):
    if not main_bot_only(client):
        return

    if len(message.command) < 2:
        return await message.reply_text(
            "❌ **Usage:**\n"
            "`/remove_premium <user_id>`"
        )

    try:
        user_id = int(
            message.command[1]
        )
    except ValueError:
        return await message.reply_text(
            "❌ Invalid user ID."
        )

    await db.set_premium(
        user_id,
        False,
    )

    await message.reply_text(
        f"🆓 User `{user_id}` "
        "returned to Free Tier."
    )


# ============================================================
# BAN
# ============================================================

@Client.on_message(
    filters.private
    & filters.command("ban")
    & filters.user(Config.ADMIN)
)
async def ban_handler(
    client: Client,
    message: Message,
):
    if not main_bot_only(client):
        return

    if len(message.command) < 2:
        return await message.reply_text(
            "❌ **Usage:**\n"
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
        f"🚫 User `{user_id}` **banned**."
    )


# ============================================================
# UNBAN
# ============================================================

@Client.on_message(
    filters.private
    & filters.command("unban")
    & filters.user(Config.ADMIN)
)
async def unban_handler(
    client: Client,
    message: Message,
):
    if not main_bot_only(client):
        return

    if len(message.command) < 2:
        return await message.reply_text(
            "❌ **Usage:**\n"
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
        f"✅ User `{user_id}` **unbanned**."
    )


# ============================================================
# RESTART MAIN BOT
# ============================================================

@Client.on_message(
    filters.private
    & filters.command("restart")
    & filters.user(Config.ADMIN)
)
async def restart_bot(
    client: Client,
    message: Message,
):
    if not main_bot_only(client):
        return

    await message.reply_text(
        "🔄 **AniToon_1Bot is restarting...**"
    )

    await asyncio.sleep(1)

    os.execl(
        sys.executable,
        sys.executable,
        *sys.argv,
    )
