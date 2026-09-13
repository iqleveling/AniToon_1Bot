"""Robust Channel 4 join-request handling.

A pending join request to the private ForceSub channel is approved
automatically. This avoids USER_NOT_PARTICIPANT blocking /start while
Telegram has not yet converted the request into normal membership.
"""

import asyncio
import logging

from pyrogram import Client, StopPropagation, filters

from helper.database import db
from plugins.start import (
    FORCE_SUB_CHANNELS,
    PRIVATE_FORCE_SUB_CHAT_ID,
    get_force_sub_status,
    make_force_sub_keyboard,
    make_force_sub_text,
)
from plugins.ui import main_menu

log = logging.getLogger(__name__)


@Client.on_chat_join_request(
    filters.chat(PRIVATE_FORCE_SUB_CHAT_ID),
    group=-200,
)
async def approve_private_force_sub_request(client: Client, request):
    """Approve Channel 4 requests immediately and record them as verified."""
    user = getattr(request, "from_user", None)
    if not user:
        return

    user_id = int(user.id)

    try:
        await db.mark_force_sub_request(
            user_id,
            PRIVATE_FORCE_SUB_CHAT_ID,
        )

        try:
            await client.approve_chat_join_request(
                PRIVATE_FORCE_SUB_CHAT_ID,
                user_id,
            )
            await db.clear_force_sub_request(
                user_id,
                PRIVATE_FORCE_SUB_CHAT_ID,
            )
            log.info(
                "Force-sub: Channel 4 join request approved for user=%s",
                user_id,
            )
        except Exception:
            # Keep the Mongo marker. /start and Check & Retry can use
            # it as a safe fallback if Telegram approval is delayed.
            log.exception(
                "Force-sub: could not auto-approve Channel 4 request for user=%s",
                user_id,
            )
    finally:
        # Prevent the older Channel 4 handler in plugins.start from
        # processing the same update a second time.
        raise StopPropagation


@Client.on_callback_query(
    filters.regex(r"^check_force_sub$"),
    group=-200,
)
async def retry_private_force_sub(client: Client, callback_query):
    """Approve a pending Channel 4 request when the user taps Retry."""
    user_id = int(callback_query.from_user.id)

    try:
        # If a request is still pending, approving it here also handles
        # deployments where the ChatJoinRequest update was missed.
        try:
            await client.approve_chat_join_request(
                PRIVATE_FORCE_SUB_CHAT_ID,
                user_id,
            )
            await db.clear_force_sub_request(
                user_id,
                PRIVATE_FORCE_SUB_CHAT_ID,
            )
            log.info(
                "Force-sub: Channel 4 request approved from Retry for user=%s",
                user_id,
            )
        except Exception:
            # It may already have been approved. Continue with the normal
            # membership/request-marker verification below.
            pass

        # Give Telegram a moment to expose the new membership state.
        await asyncio.sleep(0.5)

        joined_count, missing_channels, failed_channels = await get_force_sub_status(
            client,
            user_id,
        )
        total = len(FORCE_SUB_CHANNELS)

        await callback_query.answer("Checking required channels…")

        if joined_count == total and not missing_channels and not failed_channels:
            await callback_query.message.edit_text(
                "🔥 **Welcome to AniToon Bot** 🔥\n\n"
                "✅ All required channels are verified.\n\n"
                "📂 Send me any file, video or audio to get started.",
                reply_markup=main_menu(
                    getattr(client, "is_main_bot", False)
                ),
            )
            raise StopPropagation

        await callback_query.message.edit_text(
            make_force_sub_text(
                joined_count,
                len(missing_channels),
                len(failed_channels),
            ),
            reply_markup=make_force_sub_keyboard(
                missing_channels,
                failed_channels,
            ),
        )
    except Exception:
        log.exception(
            "Force-sub Retry failed for user=%s",
            user_id,
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
