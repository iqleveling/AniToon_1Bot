from __future__ import annotations

# Message history is intentionally preserved.
# These helpers remain available for compatibility with existing plugins, but
# installing the old automatic cleanup must never delete user commands, files,
# bot menus, transfer status messages, or completed results.


async def delete_messages(client, chat_id: int, message_ids=None):
    # Kept as an explicit helper for callers that intentionally request a
    # deletion. Automatic cleanup never calls this helper anymore.
    return None


async def clear_last_cycle(client, user_id: int):
    return None


async def remember_cycle(user_id: int, *message_ids):
    return None


async def remember_user_message(chat_id: int, message_id=None):
    return None


def install_auto_cleanup(client):
    """Disable the legacy auto-cleanup system permanently.

    We deliberately do not monkey-patch any Pyrogram send/copy method. This
    guarantees that normal bot replies, commands, source files, menus,
    progress messages, uploaded files, archived files and completed messages
    remain in Telegram chat history.
    """
    client._anitoon_auto_cleanup = False
    return client
