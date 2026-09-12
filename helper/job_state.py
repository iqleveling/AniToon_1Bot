from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Job:
    job_id: str
    user_id: int
    bot_id: int
    source_message_id: int
    work_dir: str
    input_path: str
    original_name: str
    mime_type: str | None = None
    detected_name: str | None = None
    selected_action: str | None = None
    output_ext: str | None = None
    active: bool = True
    queued_at: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)
    extra: dict[str, Any] = field(default_factory=dict)


class JobManager:
    def __init__(self, max_active: int = 20):
        self.max_active = max(1, int(max_active))
        self._semaphore = asyncio.Semaphore(self.max_active)
        self._jobs: dict[str, Job] = {}
        self._user_jobs: dict[int, str] = {}
        self._lock = asyncio.Lock()

    async def register(self, job: Job) -> bool:
        async with self._lock:
            old = self._user_jobs.get(job.user_id)
            if old and old in self._jobs:
                return False
            self._jobs[job.job_id] = job
            self._user_jobs[job.user_id] = job.job_id
            return True

    async def get(self, job_id: str) -> Job | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def get_user_job(self, user_id: int) -> Job | None:
        async with self._lock:
            job_id = self._user_jobs.get(int(user_id))
            return self._jobs.get(job_id) if job_id else None

    async def update(self, job_id: str, **values: Any) -> Job | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            for key, value in values.items():
                setattr(job, key, value)
            return job

    async def remove(self, job_id: str) -> None:
        async with self._lock:
            job = self._jobs.pop(job_id, None)
            if job:
                self._user_jobs.pop(job.user_id, None)

    async def position(self, job_id: str) -> int:
        # Queue position is approximate but stable and does not block handlers.
        async with self._lock:
            waiting = [j for j in self._jobs.values() if j.active]
            waiting.sort(key=lambda x: x.queued_at)
            for index, job in enumerate(waiting, start=1):
                if job.job_id == job_id:
                    return index
        return 0

    async def acquire(self):
        await self._semaphore.acquire()

    def release(self):
        self._semaphore.release()


jobs = JobManager(max_active=20)
