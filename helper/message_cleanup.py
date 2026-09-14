from __future__ import annotations

import asyncio

_last_cycle: dict[int, list[int]] = {}
_lock = asyncio.Lock()


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
    async with _lock:
        ids = _last_cycle.pop(int(user_id), [])
    await delete_messages(client, user_id, ids)


async def remember_cycle(user_id: int, *message_ids: int | None):
    ids = [int(x) for x in message_ids if x]
    async with _lock:
        _last_cycle[int(user_id)] = ids
