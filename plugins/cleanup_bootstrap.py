from pyrogram import Client, filters

from helper.message_cleanup import install_auto_cleanup


@Client.on_message(filters.private, group=-100000)
async def initialize_private_cleanup(client, message):
    """Install cleanup before normal private-chat handlers send their replies."""
    install_auto_cleanup(client)
