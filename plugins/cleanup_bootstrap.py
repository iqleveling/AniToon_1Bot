from pyrogram import Client, filters

from helper.message_cleanup import install_auto_cleanup, remember_user_message


@Client.on_message(filters.private, group=-100000)
async def initialize_private_cleanup(client, message):
    """Start selective cleanup while preserving commands and protected results."""
    install_auto_cleanup(client)
    try:
        await remember_user_message(message)
    except Exception:
        pass
