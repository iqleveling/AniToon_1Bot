"""Legacy cleanup hook intentionally disabled.

The authoritative private-message cleanup is implemented by
``helper.message_cleanup``.  This module used to scan recent Telegram history
and delete bot-authored messages, which could incorrectly remove completed
result files.  It remains as a no-op module so older imports/plugin discovery
stay compatible without deleting any messages.
"""

from pyrogram import Client  # noqa: F401
