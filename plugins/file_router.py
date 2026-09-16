"""High-priority file intake router for AniToon_1Bot."""

from __future__ import annotations

import logging

from pyrogram import Client, StopPropagation, filters

from helper.job_state import jobs
from helper.utils import humanbytes

log = logging.getLogger("AniToon.file_router")


def _media_info(message):
    if message.document: return message.document, "document"
    if message.video: return message.video, "video"
    if message.audio: return message.audio, "audio"
    return None, None


async def _force_sub_ok(client, user_id: int) -> bool:
    if not getattr(client, "is_main_bot", False): return True
    try:
        from plugins.start import FORCE_SUB_CHANNELS, get_force_sub_status
        if not FORCE_SUB_CHANNELS: return True
        joined, missing, failed = await get_force_sub_status(client, user_id)
        return joined == len(FORCE_SUB_CHANNELS) and not missing and not failed
    except Exception:
        log.exception("Force-sub check failed before file routing")
        return False


async def _send_force_sub_prompt(client, message) -> None:
    from plugins.start import get_force_sub_status, make_force_sub_keyboard, make_force_sub_text
    joined, missing, failed = await get_force_sub_status(client, int(message.from_user.id))
    await message.reply_text(make_force_sub_text(joined, len(missing), len(failed)), reply_markup=make_force_sub_keyboard(missing, failed))


@Client.on_message(filters.private & (filters.document | filters.video | filters.audio), group=-50000)
async def route_file_to_pipeline(client, message):
    user = getattr(message, "from_user", None)
    user_id = getattr(user, "id", None)
    if not user_id: raise StopPropagation

    # These files belong to the currently selected Advanced operation and must
    # reach that operation instead of becoming a second normal job.
    active = await jobs.get_user_job(int(user_id))
    if active and active.selected_action in {"advanced_add_audio", "advanced_add_subtitle"}:
        return

    media, media_type = _media_info(message)
    if not media: raise StopPropagation
    if not await _force_sub_ok(client, int(user_id)):
        try: await _send_force_sub_prompt(client, message)
        except Exception: log.exception("Could not send ForceSub prompt")
        raise StopPropagation

    file_size = int(getattr(media, "file_size", 0) or 0)
    file_name = getattr(media, "file_name", None) or f"file_{getattr(message, 'id', 0)}"
    queue_count = 0
    try: queue_count = len(await jobs.get_user_jobs(int(user_id)))
    except Exception: pass
    log.info("Routing file into automatic queue: bot_id=%s user_id=%s message_id=%s type=%s name=%s size=%s user_jobs=%s", getattr(client, "bot_id", 0), user_id, getattr(message, "id", "unknown"), media_type, file_name, humanbytes(file_size), queue_count + 1)

    try:
        from plugins.file_action_fix import repaired_file_download
        await repaired_file_download(client, message)
    except StopPropagation:
        raise
    except Exception as exc:
        log.exception("Deferred file pipeline failed")
        try: await message.reply_text("❌ **AniToon could not start this file job.**\n\n" f"`{str(exc)[:800]}`")
        except Exception: pass
    finally:
        raise StopPropagation
