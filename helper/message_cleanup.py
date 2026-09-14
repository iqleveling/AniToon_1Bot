from __future__ import annotations

import asyncio
import types
from collections import defaultdict
from typing import Any

_last_cycle: dict[int, list[int]] = {}
_last_user_message: dict[int, int] = {}
_last_bot_messages: dict[int, list[int]] = {}
_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
_state_lock = asyncio.Lock()


async def delete_messages(client, chat_id: int, message_ids: list[int] | tuple[int, ...] | None):
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


async def clear_last_cycle(client, user_id: int):
    async with _state_lock:
        ids = _last_cycle.pop(int(user_id), [])
    await delete_messages(client, user_id, ids)


async def remember_cycle(user_id: int, *message_ids: int | None):
    ids = [int(x) for x in message_ids if x]
    async with _state_lock:
        _last_cycle[int(user_id)] = ids


async def remember_user_message(chat_id: int, message_id: int | None):
    if not message_id:
        return
    async with _state_lock:
        _last_user_message[int(chat_id)] = int(message_id)


def _chat_id_from_send(args: tuple[Any, ...], kwargs: dict[str, Any]) -> int | None:
    chat_id = kwargs.get("chat_id")
    if chat_id is None and args:
        chat_id = args[0]
    if chat_id is None:
        return None
    try:
        chat_id = int(chat_id)
    except (TypeError, ValueError):
        return None
    # Only positive numeric IDs are direct private user chats. Channels and
    # groups use negative IDs and must never be included in auto-cleanup.
    return chat_id if chat_id > 0 else None


async def _cleanup_before_new_bot_message(client, chat_id: int):
    if not chat_id:
        return

    async with _state_lock:
        old_bot = list(_last_bot_messages.get(chat_id, []))
        old_user = _last_user_message.get(chat_id)
        _last_bot_messages[chat_id] = []
        _last_user_message.pop(chat_id, None)

    ids = old_bot[:]
    if old_user:
        ids.append(old_user)
    if ids:
        await delete_messages(client, chat_id, ids)


async def _remember_bot_result(chat_id: int, result: Any):
    message_ids: list[int] = []
    if isinstance(result, (list, tuple)):
        for item in result:
            message_id = getattr(item, "id", None)
            if message_id:
                message_ids.append(int(message_id))
    else:
        message_id = getattr(result, "id", None)
        if message_id:
            message_ids.append(int(message_id))

    if not message_ids:
        return
    async with _state_lock:
        _last_bot_messages[int(chat_id)] = message_ids


_AUTOCLEAN_METHODS = (
    "send_message", "send_document", "send_video", "send_audio", "send_photo",
    "send_animation", "send_voice", "send_video_note", "send_sticker",
    "send_contact", "send_location", "send_poll", "send_dice", "send_media_group",
    "copy_message", "copy_media_group",
)


def install_auto_cleanup(client):
    if getattr(client, "_anitoon_auto_cleanup", False):
        return

    for method_name in _AUTOCLEAN_METHODS:
        original = getattr(client, method_name, None)
        if original is None:
            continue

        async def wrapped(self, *args, __original=original, **kwargs):
            chat_id = _chat_id_from_send(args, kwargs)
            if chat_id:
                lock = _locks[chat_id]
                async with lock:
                    await _cleanup_before_new_bot_message(self, chat_id)
                    result = await __original(*args, **kwargs)
                    await _remember_bot_result(chat_id, result)
                    return result
            return await __original(*args, **kwargs)

        setattr(client, method_name, types.MethodType(wrapped, client))

    client._anitoon_auto_cleanup = True
