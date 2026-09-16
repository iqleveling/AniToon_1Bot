"""Supervise the health server and Telegram bot as one deployment."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

children: list[subprocess.Popen] = []
_stopping = False


def _terminate_all() -> None:
    global _stopping
    if _stopping:
        return
    _stopping = True
    for process in reversed(children):
        if process.poll() is None:
            try: process.terminate()
            except OSError: pass
    deadline = time.time() + 10
    for process in reversed(children):
        if process.poll() is None:
            try: process.wait(timeout=max(0.1, deadline - time.time()))
            except subprocess.TimeoutExpired:
                try: process.kill()
                except OSError: pass


def _signal_handler(signum, _frame) -> None:
    _terminate_all()
    raise SystemExit(128 + signum)


def main() -> int:
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    env = os.environ.copy()
    children.append(subprocess.Popen([sys.executable, "app.py"], env=env))
    children.append(subprocess.Popen([sys.executable, "bot.py"], env=env))
    try:
        while True:
            for process in children:
                code = process.poll()
                if code is not None:
                    _terminate_all()
                    return int(code) if code else 1
            time.sleep(1)
    finally:
        _terminate_all()


if __name__ == "__main__":
    raise SystemExit(main())
