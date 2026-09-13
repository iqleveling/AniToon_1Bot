"""
High-priority /start dispatcher.

This runs before the normal plugin group so a broad private-message
handler can never swallow /start. The existing start implementation
remains the single source of truth.
"""

from pyrogram import Client, filters


@Client.on_message(
    filters.private & filters.command("start"),
    group=-100,
)
async def priority_start(client, message):
    from plugins.start import start

    await start(client, message)
    message.stop_propagation()
