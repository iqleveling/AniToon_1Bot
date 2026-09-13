"""High-priority /start dispatcher."""

from pyrogram import Client, filters
from pyrogram import StopPropagation


@Client.on_message(
    filters.private & filters.command("start"),
    group=-100,
)
async def priority_start(client, message):
    from plugins.start import start

    await start(client, message)
    raise StopPropagation
