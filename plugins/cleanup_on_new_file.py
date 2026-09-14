from pyrogram import Client, filters

from helper.message_cleanup import clear_last_cycle


async def _delete_recent_bot_messages(client, chat_id: int, keep_message_id: int | None = None):
    """Delete recent bot-authored messages before the new file flow starts.

    This is intentionally limited to private chats and recent history so it
    removes stale UI/status messages without touching the user's older chat.
    """
    try:
        bot = await client.get_me()
        bot_id = int(bot.id)
    except Exception:
        bot_id = int(getattr(client, "bot_id", 0) or 0)

    if not bot_id:
        return

    ids = []
    try:
        async for old in client.get_chat_history(chat_id, limit=50):
            if keep_message_id and old.id == keep_message_id:
                continue
            sender = getattr(old, "from_user", None)
            if sender and int(sender.id) == bot_id:
                ids.append(old.id)
    except Exception:
        return

    if ids:
        try:
            await client.delete_messages(chat_id, ids)
        except Exception:
            for message_id in ids:
                try:
                    await client.delete_messages(chat_id, message_id)
                except Exception:
                    pass


@Client.on_message(
    filters.private & (filters.document | filters.video | filters.audio),
    group=-2100,
)
async def cleanup_previous_cycle(client, message):
    """When a new file arrives, remove the previous bot UI/status messages."""
    try:
        await clear_last_cycle(client, message.from_user.id)
    except Exception:
        pass

    # The new file is the start of a fresh interaction. Remove stale bot
    # messages from the previous interaction, including menus, prompts,
    # queue notices and transfer-status messages.
    await _delete_recent_bot_messages(client, message.chat.id, message.id)
