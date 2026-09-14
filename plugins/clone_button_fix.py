from __future__ import annotations

import re
from typing import Dict

from pyrogram import Client, StopPropagation, filters
from pyrogram.types import ForceReply, Message

from config import Config

# Pending clone prompts are intentionally kept in memory. Bot tokens are never
# persisted here; clone_manager persists only the token after successful login.
_PENDING: Dict[int, int] = {}

_TOKEN_RE = re.compile(r"^\d{5,12}:[A-Za-z0-9_-]{20,}$")


def _valid_token(value: str) -> bool:
    return bool(_TOKEN_RE.fullmatch((value or "").strip()))


async def _prompt_token(client: Client, user_id: int, old_message_id: int | None = None):
    if old_message_id:
        try:
            await client.delete_messages(user_id, old_message_id)
        except Exception:
            pass

    prompt = await client.send_message(
        user_id,
        "🤖 **Create AniToon Clone**\n\n"
        "Send the **Bot Token** you got from @BotFather.\n\n"
        "You do **not** need to send your API ID or API Hash. "
        "The clone engine uses the main bot's configured Telegram API credentials.\n\n"
        "Example format:\n"
        "`123456789:AA...`\n\n"
        "⚠️ Send the token only here in this private chat. Do not post it publicly.",
        reply_markup=ForceReply(selective=True),
    )
    _PENDING[user_id] = prompt.id
    return prompt


@Client.on_callback_query(filters.regex(r"^create_clone$"), group=-1600)
async def clone_button(client: Client, callback_query):
    """Authoritative Create Clone button handler."""
    if not getattr(client, "is_main_bot", False):
        await callback_query.answer(
            "Clone creation is available only on the main bot.",
            show_alert=True,
        )
        raise StopPropagation

    if not Config.IS_CLONE_ALLOWED:
        await callback_query.answer("Clone Engine is disabled.", show_alert=True)
        raise StopPropagation

    if not getattr(client, "clone_manager", None):
        await callback_query.answer("Clone Engine is still starting. Try again shortly.", show_alert=True)
        raise StopPropagation

    await callback_query.answer("Opening clone setup…")
    await _prompt_token(client, callback_query.from_user.id, callback_query.message.id)
    raise StopPropagation


@Client.on_message(
    filters.private & filters.text & ~filters.command("clone"),
    group=-1600,
)
async def clone_token_reply(client: Client, message: Message):
    """Accept the token from the ForceReply prompt and start the clone."""
    user_id = message.from_user.id
    prompt_id = _PENDING.get(user_id)
    if not prompt_id:
        return

    reply = message.reply_to_message
    if not reply or reply.id != prompt_id:
        return

    token = (message.text or "").strip()

    # Some older clone screens asked for API ID first. Do not leave the user
    # stuck if they follow that old prompt: explain that only the BotFather
    # token is needed and keep the wizard alive.
    if token.isdigit() and len(token) >= 5:
        await message.reply_text(
            "ℹ️ **API ID received, but it is not required here.**\n\n"
            "Please send the **Bot Token from @BotFather** as the next reply.",
            reply_markup=ForceReply(selective=True),
        )
        return

    if not _valid_token(token):
        await message.reply_text(
            "❌ **Invalid Bot Token.**\n\n"
            "Please send the token exactly as provided by @BotFather.\n"
            "Example: `123456789:AA...`",
            reply_markup=ForceReply(selective=True),
        )
        return

    _PENDING.pop(user_id, None)
    status = await message.reply_text("⏳ **Starting your clone…**")

    try:
        manager = getattr(client, "clone_manager", None)
        if not manager:
            raise RuntimeError("Clone Engine is not ready.")

        clone = await manager.add_clone(user_id, token)
        if not clone:
            raise RuntimeError(
                "Telegram rejected the bot token or the clone could not be started. "
                "Check the token with @BotFather and try again."
            )

        me = await clone.get_me()
        await status.edit_text(
            "✅ **Clone Bot Created Successfully!**\n\n"
            f"🤖 **Bot:** @{me.username or me.id}\n"
            f"🆔 **ID:** `{me.id}`\n\n"
            "🟢 Your clone is online and ready to use."
        )

        try:
            await message.delete()
        except Exception:
            pass

    except Exception as exc:
        _PENDING.pop(user_id, None)
        await status.edit_text(
            "❌ **Clone creation failed**\n\n"
            f"`{str(exc)[:1200]}`\n\n"
            "Please verify the BotFather token and try **Create Clone** again."
        )

    raise StopPropagation
