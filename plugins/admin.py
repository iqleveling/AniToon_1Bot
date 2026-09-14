import os
import sys
import asyncio

from pyrogram import Client, filters

from config import Config
from helper.database import db
from helper.plans import PLANS, get_plan
from helper.admin_access import is_admin, is_owner


ADMIN_IDS = sorted(set(int(x) for x in Config.ADMIN) | ({int(Config.OWNER_ID)} if Config.OWNER_ID else set()))


def main_bot_only(client):
    return getattr(client, "is_main_bot", False)


@Client.on_message(filters.private & filters.command(["admin", "owner"]) & filters.user(ADMIN_IDS), group=-120)
async def admin_panel(client, message):
    if not main_bot_only(client):
        return
    role = "Owner" if is_owner(message.from_user.id) else "Admin"
    await message.reply_text(
        f"👑 **AniToon {role} Panel**\n\n"
        "📊 `/users` — total users\n"
        "👤 `/user <user_id>` — user details\n"
        "💎 `/setplan <user_id> <free|pro|premium|ultra>` — change plan\n"
        "🚫 `/ban <user_id>` — ban user\n"
        "✅ `/unban <user_id>` — unban user\n"
        "📣 `/broadcast` — broadcast a replied message\n"
        "🔄 `/restart` — restart bot\n\n"
        "⚡ Admin accounts are intended to have unrestricted bot access."
    )


@Client.on_message(filters.private & filters.command("users") & filters.user(ADMIN_IDS), group=-120)
async def users_stats(client, message):
    if not main_bot_only(client):
        return
    count = await db.total_users_count()
    await message.reply_text(f"📊 **AniToon Statistics**\n\n👥 Users: `{count}`")


@Client.on_message(filters.private & filters.command("user") & filters.user(ADMIN_IDS), group=-120)
async def user_lookup(client, message):
    if not main_bot_only(client):
        return
    if len(message.command) < 2:
        return await message.reply_text("❌ Usage: `/user <user_id>`")
    try:
        user_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("❌ Invalid user ID.")
    user = await db.get_user_data(user_id)
    if not user:
        return await message.reply_text("❌ User not found.")
    sub = await db.get_subscription(user_id, client.bot_id)
    plan = get_plan(sub.get("plan", "free"))
    usage = await db.get_usage(user_id, client.bot_id)
    await message.reply_text(
        "👤 **User Information**\n\n"
        f"🆔 ID: `{user_id}`\n"
        f"💎 Plan: {plan.name}\n"
        f"📦 Usage today: `{usage}` bytes\n"
        f"🚫 Banned: `{bool(user.get('is_banned'))}`"
    )


@Client.on_message(filters.private & filters.command("setplan") & filters.user(ADMIN_IDS), group=-120)
async def set_user_plan(client, message):
    if not main_bot_only(client):
        return
    if len(message.command) < 3:
        return await message.reply_text("❌ Usage: `/setplan <user_id> <free|pro|premium|ultra>`")
    try:
        user_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("❌ Invalid user ID.")
    plan_key = message.command[2].lower()
    if plan_key not in PLANS or plan_key == "owner":
        return await message.reply_text("❌ Plan must be `free`, `pro`, `premium`, or `ultra`.")
    await db.add_user(user_id)
    await db.set_plan(user_id, client.bot_id, plan_key, 0, "admin")
    await message.reply_text(f"✅ User `{user_id}` is now on **{get_plan(plan_key).name}**.")


@Client.on_message(filters.private & filters.command("ban") & filters.user(ADMIN_IDS), group=-120)
async def ban(client, message):
    if not main_bot_only(client):
        return
    if len(message.command) < 2:
        return await message.reply_text("❌ Usage: `/ban <user_id>`")
    try:
        user_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("❌ Invalid user ID.")
    if is_owner(user_id):
        return await message.reply_text("⛔ The owner cannot be banned.")
    await db.ban_user(user_id)
    await message.reply_text(f"🚫 User `{user_id}` banned.")


@Client.on_message(filters.private & filters.command("unban") & filters.user(ADMIN_IDS), group=-120)
async def unban(client, message):
    if not main_bot_only(client):
        return
    if len(message.command) < 2:
        return await message.reply_text("❌ Usage: `/unban <user_id>`")
    try:
        user_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("❌ Invalid user ID.")
    await db.unban_user(user_id)
    await message.reply_text(f"✅ User `{user_id}` unbanned.")


@Client.on_message(filters.private & filters.command("broadcast") & filters.user(ADMIN_IDS), group=-120)
async def broadcast(client, message):
    if not main_bot_only(client):
        return
    if not message.reply_to_message:
        return await message.reply_text("❌ Reply to the message you want to broadcast.")
    status = await message.reply_text("📣 **Broadcast Started...**")
    success = failed = 0
    async for user in db.get_all_users():
        user_id = user.get("id")
        if not user_id:
            continue
        try:
            await message.reply_to_message.copy(chat_id=user_id)
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1
    await status.edit_text(f"📣 **Broadcast Complete**\n\n✅ Sent: `{success}`\n❌ Failed: `{failed}`")


@Client.on_message(filters.private & filters.command("restart") & filters.user(ADMIN_IDS), group=-120)
async def restart(client, message):
    if not main_bot_only(client):
        return
    await message.reply_text("🔄 **AniToon_1Bot restarting...**")
    await asyncio.sleep(1)
    os.execl(sys.executable, sys.executable, *sys.argv)
