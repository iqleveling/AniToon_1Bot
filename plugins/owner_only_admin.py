from pyrogram import Client, StopPropagation, filters

from config import Config


SENSITIVE_COMMANDS = [
    "admin",
    "owner",
    "users",
    "user",
    "setplan",
    "ban",
    "unban",
    "broadcast",
    "restart",
]


def is_owner(user_id: int) -> bool:
    return bool(Config.OWNER_ID and int(user_id) == int(Config.OWNER_ID))


def is_configured_admin(user_id: int) -> bool:
    return int(user_id) in {int(x) for x in Config.ADMIN}


@Client.on_message(filters.private & filters.command(SENSITIVE_COMMANDS), group=-130)
async def owner_only_admin_commands(client, message):
    if not getattr(client, "is_main_bot", False):
        return
    user_id = int(message.from_user.id)
    if is_owner(user_id):
        return
    if not is_configured_admin(user_id):
        return
    await message.reply_text("⛔ **Owner only.**\n\nThis management command is restricted to the bot owner.")
    raise StopPropagation
