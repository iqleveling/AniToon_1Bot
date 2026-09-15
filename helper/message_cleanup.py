from __future__ import annotations

import asyncio
import re
import types
from collections import defaultdict
from typing import Any

# Temporary interaction messages are cleaned when the bot sends a new message.
# Commands, the /start page, source files that are still being processed, and
# successful result files are explicitly protected.
_last_user_messages: dict[int, set[int]] = defaultdict(set)
_last_bot_temporary: dict[int, set[int]] = defaultdict(set)
_protected: dict[int, set[int]] = defaultdict(set)
_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
_state_lock = asyncio.Lock()

_COMMAND_RE = re.compile(r"^/[A-Za-z0-9_]+(?:@\w+)?(?:\s|$)")


def _is_command(message: Any) -> bool:
    text = getattr(message, "text", None) or getattr(message, "caption", None) or ""
    return bool(_COMMAND_RE.match(str(text).strip()))


async def delete_messages(client, chat_id: int, message_ids=None):
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
    """Explicitly remove the user's source/rename messages after success."""
    ids = [int(x) for x in (message_ids or []) if x]
    if not ids:
        return
    async with _state_lock:
        protected = _protected.get(int(chat_id), set())
        for message_id in ids:
            protected.discard(message_id)
        _last_user_messages[int(chat_id)].difference_update(ids)
    await delete_messages(client, int(chat_id), ids)


async def remember_user_message(message: Any, message_id: int | None = None):
    """Track user messages, but never schedule commands for deletion."""
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
    """Track a bot-created message unless it is explicitly protected."""
    results = result if isinstance(result, (list, tuple)) else [result]
    async with _state_lock:
        protected = _protected[int(chat_id)]
        for item in results:
            message_id = getattr(item, "id", None)
            if message_id and int(message_id) not in protected:
                _last_bot_temporary[int(chat_id)].add(int(message_id))


async def clear_last_cycle(client, user_id: int):
    return None


async def remember_cycle(user_id: int, *message_ids: int | None):
    return None


async def _cleanup_before_new_bot_message(client, chat_id: int):
    if not chat_id or chat_id < 0:
        return
    async with _state_lock:
        protected = _protected.get(chat_id, set())
        bot_ids = [x for x in _last_bot_temporary.get(chat_id, set()) if x not in protected]
        user_ids = [x for x in _last_user_messages.get(chat_id, set()) if x not in protected]
        _last_bot_temporary[chat_id].clear()
        _last_user_messages[chat_id].clear()
    await delete_messages(client, chat_id, bot_ids + user_ids)


_AUTOCLEAN_METHODS = (
    "send_message", "send_document", "send_video", "send_audio", "send_photo",
    "send_animation", "send_voice", "send_video_note", "send_sticker",
    "send_contact", "send_location", "send_poll", "send_dice", "send_media_group",
    "copy_message", "copy_media_group",
)


def install_auto_cleanup(client):
    """Delete only temporary interaction messages when a new bot message is sent."""
    if getattr(client, "_anitoon_auto_cleanup", False):
        return

    for method_name in _AUTOCLEAN_METHODS:
        original = getattr(client, method_name, None)
        if original is None:
            continue

        async def wrapped(self, *args, __original=original, **kwargs):
            chat_id = kwargs.get("chat_id")
            if chat_id is None and args:
                chat_id = args[0]
            try:
                chat_id = int(chat_id)
            except (TypeError, ValueError):
                chat_id = None
            if chat_id and chat_id > 0:
                lock = _locks[chat_id]
                async with lock:
                    await _cleanup_before_new_bot_message(self, chat_id)
                    result = await __original(*args, **kwargs)
                    await remember_bot_temporary(chat_id, result)
                    return result
            return await __original(*args, **kwargs)

        setattr(client, method_name, types.MethodType(wrapped, client))

    client._anitoon_auto_cleanup = True
