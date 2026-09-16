"""Compatibility module for AniToon's in-memory FIFO job manager.

The canonical queue lives in ``helper.job_state.JobManager``. This module is
kept for the existing startup import and deliberately does not monkey-patch
methods at import time.
"""

from helper.job_state import jobs

__all__ = ["jobs"]
