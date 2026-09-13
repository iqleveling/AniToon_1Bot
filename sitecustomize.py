"""Startup performance tuning for the AniToon deployment."""

import os


def _patch_pyrogram_transmissions():
    try:
        from pyrogram import Client
    except Exception:
        return

    if getattr(Client.__init__, "_anitoon_fast", False):
        return

    original_init = Client.__init__

    def fast_init(self, *args, **kwargs):
        kwargs.setdefault(
            "max_concurrent_transmissions",
            max(1, int(os.getenv("MAX_CONCURRENT_TRANSMISSIONS", "4"))),
        )
        return original_init(self, *args, **kwargs)

    fast_init._anitoon_fast = True
    Client.__init__ = fast_init


_patch_pyrogram_transmissions()
