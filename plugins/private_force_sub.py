"""Compatibility handler for the retired private ForceSub channel.

Channel 4 is no longer a required ForceSub channel. The bot must never
block a user because it cannot resolve the old private chat ID. The three
public channels remain the only required channels.
"""

import logging

from pyrogram import Client, StopPropagation, filters

from plugins.start import FORCE_SUB_CHANNELS

log = logging.getLogger("AniToon.private_force_sub")

# Keep the old private-channel code harmlessly out of ForceSub verification.
# Existing start.py callers use this shared list, so removing Channel 4 here
# makes the old private ID completely non-blocking without rewriting start.py.
if len(FORCE_SUB_CHANNELS) > 3:
    del FORCE_SUB_CHANNELS[3:]


@Client.on_chat_join_request(
    filters.chat(-1002732670564),
    group=-200,
)
async def retired_private_force_sub_request(client, request):
    """Ignore old private-channel join requests; they are not required."""
    user = getattr(request, "from_user", None)
    if user:
        log.info(
            "Ignoring retired private ForceSub Channel 4 request for user=%s",
            user.id,
        )
    raise StopPropagation


@Client.on_callback_query(
    filters.regex(r"^check_force_sub$"),
    group=-200,
)
async def retry_force_sub(client, callback_query):
    """Re-check only the three required public channels."""
    try:
        from plugins.start import (
            get_force_sub_status,
            make_force_sub_keyboard,
            make_force_sub_text,
        )
        from plugins.ui import main_menu

        user_id = int(callback_query.from_user.id)
        joined, missing, failed = await get_force_sub_status(client, user_id)
        total = len(FORCE_SUB_CHANNELS)

        try:
            await callback_query.answer("Checking required channels…")
        except Exception:
            pass

        if joined == total and not missing and not failed:
            text = (
                "🔥 **Welcome to AniToon Bot** 🔥\n\n"
                "✅ All required channels are verified.\n\n"
                "📂 Send me any file, video or audio to get started."
            )
            try:
                await callback_query.message.edit_text(
                    text,
                    reply_markup=main_menu(
                        getattr(client, "is_main_bot", False)
                    ),
                )
            except Exception as exc:
                if "MESSAGE_NOT_MODIFIED" not in str(exc):
                    raise
            raise StopPropagation

        text = make_force_sub_text(
            joined,
            len(missing),
            len(failed),
        )
        markup = make_force_sub_keyboard(missing, failed)

        try:
            await callback_query.message.edit_text(
                text,
                reply_markup=markup,
            )
        except Exception as exc:
            if "MESSAGE_NOT_MODIFIED" not in str(exc):
                raise
    except Exception:
        log.exception(
            "ForceSub retry failed for user=%s",
            callback_query.from_user.id,
        )
        try:
            await callback_query.answer(
                "⚠️ Please try again in a moment.",
                show_alert=True,
            )
        except Exception:
            pass
    finally:
        raise StopPropagation
