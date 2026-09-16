from pyrogram import Client, filters

from helper.message_cleanup import install_auto_cleanup, prepare_incoming_message_cleanup, remember_user_message


@Client.on_message(filters.private, group=-100000)
async def initialize_private_cleanup(client, message):
    """Clean only the current user's active rename/convert flow messages.

    This runs before normal handlers. It never scans chat history and never
    deletes unrelated user messages, bot results, commands, or source files.
    """
    install_auto_cleanup(client)
    try:
        await prepare_incoming_message_cleanup(client, message)
        await remember_user_message(message)
    except Exception:
        pass
