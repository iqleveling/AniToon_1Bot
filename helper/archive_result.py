from __future__ import annotations

import logging

from config import Config

log = logging.getLogger("AniToon.archive")


async def archive_message(client, message):
    """Copy a successfully delivered result into the configured private archive."""
    channel_id = int(getattr(Config, "ARCHIVE_CHANNEL_ID", 0) or 0)
    if not channel_id or message is None:
        return None
    try:
        return await client.copy_message(channel_id, message.chat.id, message.id)
    except Exception as exc:
        # Archive failure must never turn a successful user delivery into a
        # failed processing job. The exact Telegram error is logged for Render.
        log.exception("Could not archive message %s to %s: %s", getattr(message, "id", 0), channel_id, exc)
        return None
