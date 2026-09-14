"""High-priority file intake router for AniToon_1Bot.

The router deliberately does NOT download, convert, rename, or upload files.
Its only responsibility is to validate the update, enforce ForceSub for the
main bot, and hand the file to the existing deferred job pipeline. This keeps
Telegram update handling responsive and guarantees the UI order:

File Detected -> Rename/Convert/Advanced -> output choice/name -> Download
-> Processing -> Upload -> Complete.
"""

from __future__ import annotations

import logging

from pyrogram import Client, StopPropagation, filters

from config import Config
from helper.job_state import jobs
from helper.utils import humanbytes

log = logging.getLogger("AniToon.file_router")


def _media_info(message):
    """Return the media object and Telegram media type without downloading."""
    if message.document:
        return message.document, "document"
    if message.video:
        return message.video, "video"
    if message.audio:
        return message.audio, "audio"
    return None, None


async def _force_sub_ok(client, user_id: int) -> bool:
    """Verify the three public ForceSub channels on the main bot only."""
    if not getattr(client, "is_main_bot", False):
        return True

    try:
        from plugins.start import FORCE_SUB_CHANNELS, get_force_sub_status

        if not FORCE_SUB_CHANNELS:
            return True

        joined, missing, failed = await get_force_sub_status(client, user_id)
        return joined == len(FORCE_SUB_CHANNELS) and not missing and not failed
    except Exception:
        log.exception("Force-sub check failed before file routing")
        return False


async def _send_force_sub_prompt(client, message) -> None:
    from plugins.start import (
        get_force_sub_status,
        make_force_sub_keyboard,
        make_force_sub_text,
    )

    joined, missing, failed = await get_force_sub_status(client, int(message.from_user.id))
    await message.reply_text(
        make_force_sub_text(joined, len(missing), len(failed)),
        reply_markup=make_force_sub_keyboard(missing, failed),
    )


@Client.on_message(
    filters.private & (filters.document | filters.video | filters.audio),
    group=-50000,
)
async def route_file_to_pipeline(client, message):
    """Fast intake gate; delegate actual workflow to file_action_fix."""
    user = getattr(message, "from_user", None)
    user_id = getattr(user, "id", None)
    if not user_id:
        raise StopPropagation

    media, media_type = _media_info(message)
    if not media:
        raise StopPropagation

    # Main bot uses ForceSub; clones intentionally bypass the main bot's
    # channel requirements and use the same deferred processing UI.
    if not await _force_sub_ok(client, int(user_id)):
        try:
            await _send_force_sub_prompt(client, message)
        except Exception:
            log.exception("Could not send ForceSub prompt")
        raise StopPropagation

    # Reject an additional file while a user's current job is waiting for an
    # operation/name or is already being processed. The existing pipeline also
    # handles this case, but doing it here avoids unnecessary work and database
    # queries before a duplicate update reaches the workflow.
    try:
        existing = await jobs.get_user_job(int(user_id))
        if existing:
            await message.reply_text(
                "⏳ **You already have an active file job.**\n\n"
                "Please finish it or use `/cancel` before sending another file."
            )
            raise StopPropagation
    except StopPropagation:
        raise
    except Exception:
        # A router-side cache failure must not block the real pipeline.
        log.exception("Active-job precheck failed; continuing to pipeline")

    file_size = int(getattr(media, "file_size", 0) or 0)
    file_name = getattr(media, "file_name", None) or f"file_{getattr(message, 'id', 0)}"

    log.info(
        "Routing file: bot_id=%s user_id=%s message_id=%s type=%s name=%s size=%s",
        getattr(client, "bot_id", 0),
        user_id,
        getattr(message, "id", "unknown"),
        media_type,
        file_name,
        humanbytes(file_size),
    )

    # The real deferred pipeline creates the Job, shows File Detected, asks for
    # Rename/Convert/Advanced first, and only downloads after the user chooses.
    try:
        from plugins.file_action_fix import repaired_file_download

        await repaired_file_download(client, message)
    except StopPropagation:
        raise
    except Exception as exc:
        log.exception("Deferred file pipeline failed")
        try:
            await message.reply_text(
                "❌ **AniToon could not start this file job.**\n\n"
                f"`{str(exc)[:800]}`"
            )
        except Exception:
            pass
    finally:
        # This router is the single intake gate. Do not allow the legacy
        # download handlers to process the same Telegram update a second time.
        raise StopPropagation
