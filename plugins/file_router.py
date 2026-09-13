"""High-priority file intake router.

Telegram can deliver normal files as documents, while videos and audio
arrive as their dedicated media types. This router guarantees that the
existing AniToon download/job pipeline gets the update before any other
plugin can accidentally consume it.
"""

import logging

from pyrogram import Client, StopPropagation, filters

log = logging.getLogger("AniToon.file_router")


@Client.on_message(
    filters.private & (filters.document | filters.video | filters.audio),
    group=-90,
)
async def route_file_to_pipeline(client, message):
    """Send every private document/video/audio into the existing pipeline."""
    try:
        from plugins.rename import auto_detect

        log.info(
            "File received: bot_id=%s user_id=%s message_id=%s type=%s",
            getattr(client, "bot_id", 0),
            getattr(getattr(message, "from_user", None), "id", "unknown"),
            getattr(message, "id", "unknown"),
            "document" if message.document else "video" if message.video else "audio",
        )

        await auto_detect(client, message)
    except Exception as exc:
        log.exception("File intake failed")
        try:
            await message.reply_text(
                "❌ **AniToon could not start this file job.**\n\n"
                f"`{str(exc)[:800]}`"
            )
        except Exception:
            pass
    finally:
        # The original handler in rename.py is group 0. Stop propagation so
        # a file is never downloaded twice after this router has handled it.
        raise StopPropagation
