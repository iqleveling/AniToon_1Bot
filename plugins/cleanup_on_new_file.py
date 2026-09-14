from pyrogram import Client, filters

from helper.message_cleanup import clear_last_cycle


@Client.on_message(filters.private & (filters.document | filters.video | filters.audio), group=-2100)
async def cleanup_previous_cycle(client, message):
    """When a new file arrives, remove the previous bot/user processing cycle."""
    try:
        await clear_last_cycle(client, message.from_user.id)
    except Exception:
        pass
