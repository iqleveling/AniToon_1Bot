import os
import sys
import asyncio

from pyrogram import Client, filters
from pyrogram.types import Message

from config import Config
from helper.database import db


# --- Choice 7-B: ADMIN AUTHENTICATION ---
# All commands in this file are restricted to Config.ADMIN.


@Client.on_message(
    filters.private
    & filters.command("users")
    & filters.user(Config.ADMIN)
)
async def users_stats(
    client: Client,
    message: Message,
):
    """Shows the total number of registered users."""

    count = await db.total_users_count()

    await message.reply_text(
        "📊 **AniToon Stats**\n\n"
        f"👥 **Total Registered Users:** `{count}`"
    )


# --- Choice 13-B: BROADCAST ---

@Client.on_message(
    filters.private
    & filters.command("broadcast")
    & filters.user(Config.ADMIN)
)
async def broadcast_handler(
    client: Client,
    message: Message,
):
    """
    Broadcasts a replied message to all registered users.
    """

    if not message.reply_to_message:
        return await message.reply_text(
            "❌ **Error**\n\n"
            "Reply to the message you want to broadcast, "
            "then use `/broadcast`."
        )

    status = await message.reply_text(
        "📣 **Broadcast Initialized...**\n\n"
        "Please wait..."
    )

    all_users = await db.get_all_users()

    success = 0
    failed = 0

    async for user in all_users:
        user_id = user.get("id")

        if not user_id:
            continue

        try:
            await message.reply_to_message.copy(
                chat_id=user_id
            )

            success += 1

            # Small delay for flood protection
            await asyncio.sleep(0.05)

        except Exception:
            failed += 1

    await status.edit_text(
        "📣 **Broadcast Results**\n\n"
        f"✅ **Sent:** `{success}`\n"
        f"❌ **Failed:** `{failed}`"
    )


# --- Choice 10-B: PREMIUM MANAGEMENT ---

@Client.on_message(
    filters.private
    & filters.command("addpremium")
    & filters.user(Config.ADMIN)
)
async def upgrade_user(
    client: Client,
    message: Message,
):
    """
    Upgrades a user to Premium.
    """

    if len(message.command) < 2:
        return await message.reply_text(
            "❌ **Usage:**\n"
            "`/addpremium <user_id>`"
        )

    try:
        user_id = int(message.command[1])
    except ValueError:
        return await message.reply_text(
            "❌ **Invalid user ID.**"
        )

    if not await db.is_user_exist(user_id):
        return await message.reply_text(
            f"❌ User `{user_id}` is not registered."
        )

    await db.set_premium(
        user_id,
        True
    )

    try:
        await client.send_message(
            user_id,
            "✨ **Plan Upgraded!**\n\n"
            "You are now a **Premium** user.\n\n"
            "💎 Premium benefits are now enabled."
        )
    except Exception:
        pass

    await message.reply_text(
        f"💎 User `{user_id}` upgraded to **Premium Tier**."
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
    """
    Removes Premium status from a user.
    """

    if len(message.command) < 2:
        return await message.reply_text(
            "❌ **Usage:**\n"
            "`/remove_premium <user_id>`"
        )

    try:
        user_id = int(message.command[1])
    except ValueError:
        return await message.reply_text(
            "❌ **Invalid user ID.**"
        )

    if not await db.is_user_exist(user_id):
        return await message.reply_text(
            f"❌ User `{user_id}` is not registered."
        )

    await db.set_premium(
        user_id,
        False
    )

    await message.reply_text(
        f"🆓 User `{user_id}` downgraded to **Free Tier**."
    )


# --- Choice 7-B: BAN MANAGEMENT ---

@Client.on_message(
    filters.private
    & filters.command("ban")
    & filters.user(Config.ADMIN)
)
async def ban_handler(
    client: Client,
    message: Message,
):
    """Bans a registered user."""

    if len(message.command) < 2:
        return await message.reply_text(
            "❌ **Usage:**\n"
            "`/ban <user_id>`"
        )

    try:
        user_id = int(message.command[1])
    except ValueError:
        return await message.reply_text(
            "❌ **Invalid user ID.**"
        )

    if not await db.is_user_exist(user_id):
        return await message.reply_text(
            f"❌ User `{user_id}` is not registered."
        )

    await db.ban_user(user_id)

    await message.reply_text(
        f"🚫 User `{user_id}` has been **Banned**."
    )


@Client.on_message(
    filters.private
    & filters.command("unban")
    & filters.user(Config.ADMIN)
)
async def unban_handler(
    client: Client,
    message: Message,
):
    """Unbans a registered user."""

    if len(message.command) < 2:
        return await message.reply_text(
            "❌ **Usage:**\n"
            "`/unban <user_id>`"
        )

    try:
        user_id = int(message.command[1])
    except ValueError:
        return await message.reply_text(
            "❌ **Invalid user ID.**"
        )

    if not await db.is_user_exist(user_id):
        return await message.reply_text(
            f"❌ User `{user_id}` is not registered."
        )

    await db.unban_user(user_id)

    await message.reply_text(
        f"✅ User `{user_id}` has been **Unbanned**."
    )


# --- BOT RESTART ---

@Client.on_message(
    filters.private
    & filters.command("restart")
    & filters.user(Config.ADMIN)
)
async def restart_bot(
    client: Client,
    message: Message,
):
    """
    Restarts the current Python process.
    """

    await message.reply_text(
        "🔄 **AniToon Bot is restarting...**"
    )

    await asyncio.sleep(1)

    os.execl(
        sys.executable,
        sys.executable,
        *sys.argv
    )
