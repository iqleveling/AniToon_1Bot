from pyrogram import Client, filters

from helper.message_cleanup import remember_user_message


@Client.on_message(filters.private, group=-30000)
async def track_private_user_message(client, message):
    """Remember the latest private user message for the next bot response."""
    try:
        if message.from_user and not message.from_user.is_bot:
            await remember_user_message(message.chat.id, message.id)
    except Exception:
        pass
