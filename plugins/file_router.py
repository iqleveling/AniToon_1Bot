"""High-priority file intake router.

Telegram sends ordinary uploaded files as ``document`` updates, while
videos/audio may arrive as their dedicated media types. This router makes
sure the existing AniToon job pipeline receives every supported file once.
"""

import logging

from pyrogram import Client, StopPropagation, filters

log = logging.getLogger("AniToon.file_router")


async def _force_sub_ok(client, user_id: int) -> bool:
    """Return True only when all required channels are verified."""
    try:
        from plugins.start import (
            get_force_sub_status,
            make_force_sub_text,
            make_force_sub_keyboard,
            FORCE_SUB_CHANNELS,
        )

        joined, missing, failed = await get_force_sub_status(client, user_id)
        if joined == len(FORCE_SUB_CHANNELS) and not missing and not failed:
            return True
        return False
    except Exception:
        # Do not silently bypass ForceSub when its verification fails.
        log.exception("Force-sub check failed before file intake")
        return False


@Client.on_message(
    filters.private & (filters.document | filters.video | filters.audio),
    group=-90,
)
async def route_file_to_pipeline(client, message):
    """Send every private document/video/audio into the existing pipeline."""
    user_id = getattr(getattr(message, "from_user", None), "id", None)
    try:
        if not user_id:
            return

        # File messages must obey the same ForceSub requirement as /start.
        if not await _force_sub_ok(client, int(user_id)):
            from plugins.start import (
                get_force_sub_status,
                make_force_sub_text,
                make_force_sub_keyboard,
            )

            joined, missing, failed = await get_force_sub_status(client, int(user_id))
            await message.reply_text(
                make_force_sub_text(joined, len(missing), len(failed)),
                reply_markup=make_force_sub_keyboard(missing, failed),
            )
            return

        from plugins.rename import auto_detect

        media_type = (
            "document" if message.document
            else "video" if message.video
            else "audio"
        )
        log.info(
            "File received: bot_id=%s user_id=%s message_id=%s type=%s",
            getattr(client, "bot_id", 0),
            user_id,
            getattr(message, "id", "unknown"),
            media_type,
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
        # rename.py also has a document/video/audio handler at group 0.
        # Stop propagation so the same file is never downloaded twice.
        raise StopPropagation
