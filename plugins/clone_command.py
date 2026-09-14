from __future__ import annotations

from pyrogram import Client, filters

from config import Config


@Client.on_message(filters.private & filters.command("clone"))
async def clone_command(client, message):
    if not getattr(client, "is_main_bot", False):
        return await message.reply_text("❌ Clone creation is available only from the main AniToon bot.")
    if not Config.IS_CLONE_ALLOWED:
        return await message.reply_text("❌ **Clone Engine is disabled.**")
    if not client.clone_manager:
        return await message.reply_text("❌ **Clone Engine is not ready.** Please try again shortly.")
    if len(message.command) < 2:
        return await message.reply_text(
            "🤖 **Create Your AniToon Clone**\n\n"
            "Open @BotFather, create a bot, then send:\n\n"
            "`/clone <BOT_TOKEN>`"
        )
    token = message.command[1].strip()
    if ":" not in token or len(token) < 20:
        return await message.reply_text("❌ Invalid Bot Token format.")
    try:
        clone = await client.clone_manager.add_clone(message.from_user.id, token)
        if not clone:
            return await message.reply_text("❌ Could not start the clone. Check the token and try again.")
        me = await clone.get_me()
        await message.reply_text(
            "✅ **Clone Bot Created!**\n\n"
            f"🤖 **Bot:** @{me.username or me.id}\n"
            f"🆔 **ID:** `{me.id}`\n\n"
            "Your clone is now online."
        )
    except Exception as exc:
        await message.reply_text(f"❌ **Clone creation failed**\n\n`{str(exc)[:1000]}`")
