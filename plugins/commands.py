"""Public and useful user command helpers."""

from pyrogram import Client, filters

from helper.admin_access import is_admin
from helper.database import db
from helper.plans import get_plan


@Client.on_message(filters.private & filters.command("help"), group=-90)
async def command_help(client, message):
    text = (
        "🛠 **AniToon Help**\n\n"
        "📂 **File processing**\n"
        "• Send a document, video or audio to start.\n"
        "• Choose Rename, Convert or Advanced.\n"
        "• `/cancel` — cancel your active/waiting job.\n\n"
        "⚙️ **Useful commands**\n"
        "• `/start` — open the main menu\n"
        "• `/help` — show this help\n"
        "• `/plan` — view available plans\n"
        "• `/status` — view your current plan and usage\n"
        "• `/cancel` — cancel current processing\n"
        "• `/clone` — create your own clone bot\n"
        "• `/setcaption` — manage your default caption\n"
        "• `/metadata` — manage audio/subtitle names\n"
        "• `/paysupport` — payment support\n\n"
        "🖼 Send an image to save a custom thumbnail.\n\n"
        "Send a file after joining all required channels."
    )
    if is_admin(message.from_user.id):
        text += (
            "\n\n👑 **Admin commands**\n"
            "• `/admin` — open admin controls\n"
            "• `/users` — user statistics\n"
            "• `/user <user_id>` — inspect a user\n"
            "• `/setplan <user_id> <plan>` — set a plan\n"
            "• `/ban <user_id>` — ban a user\n"
            "• `/unban <user_id>` — unban a user\n"
            "• `/broadcast` — broadcast a replied message\n"
            "• `/restart` — restart the bot"
        )
    await message.reply_text(text)


@Client.on_message(filters.private & filters.command("user"), group=-90)
async def user_lookup(client, message):
    if not is_admin(message.from_user.id):
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
