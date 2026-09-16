from __future__ import annotations

import asyncio
from collections import defaultdict

_tasks: dict[str, set[asyncio.Task]] = defaultdict(set)
_lock = asyncio.Lock()


async def register_task(job_id: str) -> asyncio.Task:
    task = asyncio.current_task()
    if task is None:
        raise RuntimeError("Cancellation registration requires an active asyncio task")
    async with _lock:
        _tasks[str(job_id)].add(task)
    return task


async def unregister_task(job_id: str, task: asyncio.Task | None = None) -> None:
    if not job_id:
        return
    target = task or asyncio.current_task()
    async with _lock:
        bucket = _tasks.get(str(job_id))
        if not bucket:
            return
        if target is not None:
            bucket.discard(target)
        if not bucket:
            _tasks.pop(str(job_id), None)


async def cancel_job_tasks(job_id: str) -> int:
    if not job_id:
        return 0
    async with _lock:
        tasks = list(_tasks.get(str(job_id), set()))
    current = asyncio.current_task()
    count = 0
    for task in tasks:
        if task is current or task.done():
            continue
        task.cancel()
        count += 1
    return count
