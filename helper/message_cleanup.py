from __future__ import annotations

import asyncio
import re
from collections import defaultdict
from typing import Any

# Cleanup is intentionally scoped. The bot never scans chat history and never
# deletes arbitrary user/bot messages. Only messages explicitly registered as
# part of the current rename/convert flow are eligible for automatic deletion.
_last_user_messages: dict[int, set[int]] = defaultdict(set)
_last_bot_temporary: dict[int, set[int]] = defaultdict(set)
_protected: dict[int, set[int]] = defaultdict(set)
_transfer_messages: dict[int, set[int]] = defaultdict(set)
_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
_state_lock = asyncio.Lock()

_job_transient: dict[str, set[tuple[int, int]]] = defaultdict(set)
_job_source: dict[str, set[tuple[int, int]]] = defaultdict(set)
_rename_start_prompts: dict[int, set[tuple[int, int]]] = defaultdict(set)

_COMMAND_RE = re.compile(r"^/[A-Za-z0-9_]+(?:@\w+)?(?:\s|$)")
_TRANSFER_TEXT_RE = re.compile(
    r"(?:Download Progress|Upload Progress|Processing\.\.\.|Conversion Complete!|Rename Complete!|Processing cancelled\.|Conversion failed|Processing failed)",
    re.IGNORECASE,
)


def _message_text(message: Any) -> str:
    text = getattr(message, "text", None) or getattr(message, "caption", None) or ""
    return str(text).strip()


def _is_command(message: Any) -> bool:
    return bool(_COMMAND_RE.match(_message_text(message)))


def _looks_like_transfer_status(message: Any) -> bool:
    return bool(_TRANSFER_TEXT_RE.search(_message_text(message)))


async def delete_messages(client, chat_id, message_ids=None):
    # Delete individually so only explicitly selected messages are touched.
    for message_id in [int(x) for x in (message_ids or []) if x]:
        try:
            await client.delete_messages(chat_id, message_id)
        except Exception:
            pass


async def protect_message(chat_id: int, message_id: int | None):
    if not message_id:
        return
    async with _state_lock:
        _protected[int(chat_id)].add(int(message_id))
        _last_user_messages[int(chat_id)].discard(int(message_id))
        _last_bot_temporary[int(chat_id)].discard(int(message_id))


async def protect_transfer_message(message: Any):
    if message is None:
        return
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    message_id = getattr(message, "id", None)
    if chat_id and message_id:
        async with _state_lock:
            _transfer_messages[int(chat_id)].add(int(message_id))
        await protect_message(int(chat_id), int(message_id))


async def delete_transfer_message(client, message: Any):
    if message is None:
        return
    await protect_transfer_message(message)


async def protect_result(message: Any):
    if message is None:
        return
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    message_id = getattr(message, "id", None)
    if chat_id and message_id:
        await protect_message(int(chat_id), int(message_id))


async def protect_start_page(message: Any):
    await protect_result(message)


async def register_job_message(job_id: str, message: Any, *, source: bool = False) -> None:
    if not job_id or message is None:
        return
    chat_id = getattr(getattr(message, "chat", None), "id", None)
    message_id = getattr(message, "id", None)
    if not chat_id or not message_id:
        return
    item = (int(chat_id), int(message_id))
    bucket = _job_source if source else _job_transient
    async with _state_lock:
        bucket[str(job_id)].add(item)


async def register_rename_start_prompt(user_id: int, message: Any) -> None:
    if message is None:
        return
    chat_id = getattr(getattr(message, "chat", None), "id", None)
    message_id = getattr(message, "id", None)
    if not chat_id or not message_id:
        return
    async with _state_lock:
        _rename_start_prompts[int(user_id)].add((int(chat_id), int(message_id)))


async def cleanup_rename_start_prompt(client, user_id: int) -> None:
    async with _state_lock:
        items = list(_rename_start_prompts.pop(int(user_id), set()))
    for chat_id, message_id in items:
        await delete_messages(client, chat_id, [message_id])


async def cleanup_job_transient(client, job_id: str, *, keep_message_id: int | None = None) -> None:
    if not job_id:
        return
    async with _state_lock:
        items = list(_job_transient.pop(str(job_id), set()))
    keep = int(keep_message_id) if keep_message_id else None
    for chat_id, message_id in items:
        if keep is not None and message_id == keep:
            async with _state_lock:
                _job_transient[str(job_id)].add((chat_id, message_id))
            continue
        await delete_messages(client, chat_id, [message_id])


async def cleanup_job_source(client, job_id: str) -> None:
    if not job_id:
        return
    async with _state_lock:
        items = list(_job_source.pop(str(job_id), set()))
    for chat_id, message_id in items:
        await delete_messages(client, chat_id, [message_id])


async def clear_job_cleanup(job_id: str) -> None:
    if not job_id:
        return
    async with _state_lock:
        _job_transient.pop(str(job_id), None)
        _job_source.pop(str(job_id), None)


async def prepare_incoming_message_cleanup(client, message: Any) -> None:
    """Delete only temporary messages belonging to the user's active rename flow."""
    if message is None or not getattr(message, "from_user", None):
        return
    user_id = int(message.from_user.id)
    if _is_command(message):
        return

    # The start-page rename prompt is a separate pre-job message.
    await cleanup_rename_start_prompt(client, user_id)

    try:
        from helper.job_state import jobs
        job = await jobs.get_user_job(user_id)
    except Exception:
        job = None

    if not job or getattr(job, "selected_action", None) not in {
        "rename_output_choice", "rename_format", "custom_name", "convert_name"
    }:
        return

    # Different historical rename handlers use one of these fields. Delete only
    # those exact message IDs; never search or scan the chat.
    extra = getattr(job, "extra", {}) or {}
    ids = {
        extra.get("rename_prompt_message_id"),
        extra.get("prompt_message_id"),
        extra.get("rename_menu_message_id"),
    }
    ids.discard(None)
    for message_id in ids:
        await delete_messages(client, message.chat.id, [message_id])

    await cleanup_job_transient(client, job.job_id)


async def delete_user_job_messages(client, chat_id: int, message_ids):
    ids = [int(x) for x in (message_ids or []) if x]
    if not ids:
        return
    await delete_messages(client, int(chat_id), ids)


async def remember_user_message(message: Any, message_id: int | None = None):
    if message_id is None:
        message_id = getattr(message, "id", None)
    chat_id = getattr(getattr(message, "chat", None), "id", None)
    if not chat_id or not message_id:
        return
    if _is_command(message):
        await protect_message(chat_id, message_id)
        return
    async with _state_lock:
        _last_user_messages[int(chat_id)].add(int(message_id))


async def remember_bot_temporary(chat_id: int, result: Any):
    # Compatibility only. Never classify arbitrary bot messages as deletable.
    return None


async def clear_last_cycle(user_id: int):
    return None


async def remember_cycle(user_id: int, *message_ids: int | None):
    return None


async def _cleanup_before_new_bot_message(client, chat_id: int):
    # Global bot-message cleanup is intentionally disabled.
    return None


_AUTOCLEAN_METHODS = (
    "send_message", "send_document", "send_video", "send_audio", "send_photo",
    "send_animation", "send_voice", "send_video_note", "send_sticker",
    "send_contact", "send_location", "send_poll", "send_dice", "send_media_group",
    "copy_message", "copy_media_group",
)


def install_auto_cleanup(client):
    client._anitoon_auto_cleanup = True
    return None
