"""Invisible automatic FIFO queue for user file jobs.

This module extends the existing JobManager instance without adding any queue
buttons or queue commands. Multiple files from the same user can coexist and
are kept in arrival order. Existing callers can continue using jobs.get(),
jobs.update(), jobs.remove(), and jobs.get_user_job().
"""

from __future__ import annotations

import asyncio
from types import MethodType

from helper.job_state import jobs


if not getattr(jobs, "_auto_queue_enabled", False):
    jobs._user_jobs = {}
    jobs._auto_user_locks = {}

    async def _register(self, job):
        async with self._lock:
            if len(self._jobs) >= self.max_active:
                return False
            self._jobs[job.job_id] = job
            self._user_jobs.setdefault(int(job.user_id), []).append(job.job_id)
            return True

    async def _get_user_job(self, user_id):
        async with self._lock:
            queue = self._user_jobs.get(int(user_id), [])
            for job_id in queue:
                job = self._jobs.get(job_id)
                if job:
                    return job
            return None

    async def _get_user_jobs(self, user_id):
        async with self._lock:
            return [
                self._jobs[job_id]
                for job_id in self._user_jobs.get(int(user_id), [])
                if job_id in self._jobs
            ]

    async def _remove(self, job_id):
        async with self._lock:
            job = self._jobs.pop(job_id, None)
            if not job:
                return
            queue = self._user_jobs.get(int(job.user_id), [])
            try:
                queue.remove(job_id)
            except ValueError:
                pass
            if queue:
                self._user_jobs[int(job.user_id)] = queue
            else:
                self._user_jobs.pop(int(job.user_id), None)

    async def _user_position(self, job_id):
        async with self._lock:
            target = self._jobs.get(job_id)
            if not target:
                return 0
            queue = self._user_jobs.get(int(target.user_id), [])
            try:
                return queue.index(job_id) + 1
            except ValueError:
                return 0

    async def _has_earlier_user_job(self, job_id):
        return (await _user_position(self, job_id)) > 1

    async def _acquire_user(self, user_id):
        lock = self._auto_user_locks.setdefault(int(user_id), asyncio.Lock())
        await lock.acquire()
        return lock

    jobs.register = MethodType(_register, jobs)
    jobs.get_user_job = MethodType(_get_user_job, jobs)
    jobs.get_user_jobs = MethodType(_get_user_jobs, jobs)
    jobs.remove = MethodType(_remove, jobs)
    jobs.user_position = MethodType(_user_position, jobs)
    jobs.has_earlier_user_job = MethodType(_has_earlier_user_job, jobs)
    jobs.acquire_user = MethodType(_acquire_user, jobs)
    jobs._auto_queue_enabled = True
