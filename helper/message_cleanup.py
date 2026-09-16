from __future__ import annotations

import asyncio
import re
import types
from collections import defaultdict
from typing import Any

# Automatic message deletion is intentionally disabled.
# Messages remain in the chat unless another part of the bot explicitly deletes them.
_last_user_messages: dict[int, set[int]] = defaultdict(set)
_last_bot_temporary: dict[int, set[int]] = defaultdict(set)
_protected: dict[int, set[int]] = defaultdict(set)
_transfer_messages: dict[int, set[int]] = defaultdict(set)
_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
_state_lock = asyncio.Lock()

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
    ids = [int(x) for x in (message_ids or []) if x]
    if not ids:
        return
    try:
        await client.delete_messages(chat_id, ids)
    except Exception:
        for message_id in ids:
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
    # Compatibility API only. Transfer messages are intentionally never deleted here.
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


async def delete_user_job_messages(client, chat_id: int, message_ids):
    """Compatibility API for callers that explicitly request job-input deletion."""
    ids = [int(x) for x in (message_ids or []) if x]
    if not ids:
        return
    # Automatic cleanup is disabled, but this explicit helper preserves its
    # historical behavior for code that intentionally invokes it.
    async with _state_lock:
        protected = _protected.get(int(chat_id), set())
        transfer = _transfer_messages.get(int(chat_id), set())
        for message_id in ids:
            protected.discard(message_id)
            transfer.discard(message_id)
        _last_user_messages[int(chat_id)].difference_update(ids)
    await delete_messages(client, int(chat_id), ids)


async def remember_user_message(message: Any, message_id: int | None = None):
    """Record message state without scheduling anything for automatic deletion."""
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
    results = result if isinstance(result, (list, tuple)) else [result]
    async with _state_lock:
        protected = _protected[int(chat_id)]
        transfer = _transfer_messages[int(chat_id)]
        for item in results:
            message_id = getattr(item, "id", None)
            if not message_id:
                continue
            if int(message_id) in protected or int(message_id) in transfer:
                continue
            if _is_command(item) or _looks_like_transfer_status(item):
                protected.add(int(message_id))
                if _looks_like_transfer_status(item):
                    transfer.add(int(message_id))
                continue
            _last_bot_temporary[int(chat_id)].add(int(message_id))


async def clear_last_cycle(client, user_id: int):
    return None


async def remember_cycle(user_id: int, *message_ids: int | None):
    return None


async def _cleanup_before_new_bot_message(client, chat_id: int):
    # Intentionally disabled. Kept as a compatibility function for existing imports.
    return None


_AUTOCLEAN_METHODS = (
    "send_message", "send_document", "send_video", "send_audio", "send_photo",
    "send_animation", "send_voice", "send_video_note", "send_sticker",
    "send_contact", "send_location", "send_poll", "send_dice", "send_media_group",
    "copy_message", "copy_media_group",
)


def install_auto_cleanup(client):
    """Compatibility hook: automatic message deletion is completely disabled."""
    client._anitoon_auto_cleanup = False
    return None
