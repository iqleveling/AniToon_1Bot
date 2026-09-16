from __future__ import annotations

from pyrogram import Client, StopPropagation, filters

from plugins.rename_reply_responder import reliable_rename_reply


@Client.on_message(filters.private & filters.text, group=-1600)
async def fifo_filename_input(client, message):
    """Compatibility router for queued rename/convert replies.

    All actual download, conversion and upload work lives in one canonical
    processor so old duplicate pipelines cannot process the same file twice.
    """
    if (message.text or "").strip().startswith("/"):
        return
    await reliable_rename_reply(client, message)
    raise StopPropagation
