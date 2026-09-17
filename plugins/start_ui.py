"""Clean AniToon /start experience and start-page actions."""

from pyrogram import Client, StopPropagation, filters

from helper.database import db
from helper.message_cleanup import protect_start_page, register_rename_start_prompt
from helper.plans import get_plan
from helper.utils import humanbytes
from plugins.start import get_force_sub_status, make_force_sub_text, make_force_sub_keyboard
from plugins.ui import main_menu


async def _require_force_sub(client, user_id: int, message=None) -> bool:
    """Return True only when every configured channel is confirmed joined."""
    joined, missing, failed = await get_force_sub_status(client, user_id)
    if missing or failed:
        text = make_force_sub_text(joined, len(missing), len(failed))
        keyboard = make_force_sub_keyboard(missing)
        if message is not None:
            sent = await message.reply_text(text, reply_markup=keyboard)
            await protect_start_page(sent)
        return False
    return True


@Client.on_message(filters.private & filters.command("start"), group=-200)
async def clean_start(client, message):
    user_id = message.from_user.id
    bot_id = int(getattr(client, "bot_id", 0))
    try:
        await db.add_user(user_id)
    except Exception:
        pass

    try:
        if not await _require_force_sub(client, user_id, message):
            raise StopPropagation
    except StopPropagation:
        raise
    except Exception:
        await message.reply_text("⚠️ **Channel verification failed.** Please try `/start` again.")
        raise StopPropagation

    plan_name, used, remaining = "🆓 Free", 0, 10 * 1024 * 1024 * 1024
    try:
        subscription = await db.get_subscription(user_id, bot_id)
        plan = get_plan(subscription.get("plan", "free"))
        used = await db.get_usage(user_id, bot_id)
        plan_name = plan.name
        remaining = max(plan.daily_limit - used, 0)
    except Exception:
        pass
    text = "🔥 **Welcome to AniToon Bot** 🔥\n\n" f"👋 Hello **{message.from_user.first_name}**!\n\n" f"💎 **Plan:** {plan_name}\n" f"📊 **Used today:** `{humanbytes(used)}`\n" f"📦 **Remaining:** `{humanbytes(remaining)}`\n\n" "⚡ Fast processing • Clean filenames • Advanced media tools"
    sent = await message.reply_text(text, reply_markup=main_menu(getattr(client, "is_main_bot", False)))
    await protect_start_page(sent)
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^start_rename$"), group=-200)
async def start_rename_action(client, callback_query):
    await callback_query.answer()
    try:
        if not await _require_force_sub(client, callback_query.from_user.id, callback_query.message):
            raise StopPropagation
    except StopPropagation:
        raise
    except Exception:
        await callback_query.message.reply_text("⚠️ **Channel verification failed.** Please try again.")
        raise StopPropagation
    sent = await callback_query.message.reply_text("✏️ **Rename:**\nSend me the file you want to rename.")
    await register_rename_start_prompt(callback_query.from_user.id, sent)
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^start_convert$"), group=-200)
async def start_convert_action(client, callback_query):
    await callback_query.answer()
    try:
        if not await _require_force_sub(client, callback_query.from_user.id, callback_query.message):
            raise StopPropagation
    except StopPropagation:
        raise
    except Exception:
        await callback_query.message.reply_text("⚠️ **Channel verification failed.** Please try again.")
        raise StopPropagation
    await callback_query.message.reply_text("🔄 **Convert**\n\nSend me the video, audio, or document you want to convert.\n\nAfter the file is received, choose **Convert** and select the output format.")
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^start$"), group=-200)
async def start_from_button(client, callback_query):
    await callback_query.answer()
    user = callback_query.from_user
    bot_id = int(getattr(client, "bot_id", 0))
    try:
        if not await _require_force_sub(client, user.id, callback_query.message):
            raise StopPropagation
    except StopPropagation:
        raise
    except Exception:
        await callback_query.message.reply_text("⚠️ **Channel verification failed.** Please try again.")
        raise StopPropagation
    plan_name, used, remaining = "🆓 Free", 0, 10 * 1024 * 1024 * 1024
    try:
        subscription = await db.get_subscription(user.id, bot_id)
        plan = get_plan(subscription.get("plan", "free"))
        used = await db.get_usage(user.id, bot_id)
        plan_name, remaining = plan.name, max(plan.daily_limit - used, 0)
    except Exception:
        pass
    text = "🔥 **Welcome to AniToon Bot** 🔥\n\n" f"👋 Hello **{user.first_name}**!\n\n" f"💎 **Plan:** {plan_name}\n" f"📊 **Used today:** `{humanbytes(used)}`\n" f"📦 **Remaining:** `{humanbytes(remaining)}`\n\n" "⚡ Fast processing • Clean filenames • Advanced media tools"
    try:
        await callback_query.message.edit_text(text, reply_markup=main_menu(getattr(client, "is_main_bot", False)))
    except Exception:
        sent = await callback_query.message.reply_text(text, reply_markup=main_menu(getattr(client, "is_main_bot", False)))
        await protect_start_page(sent)
    else:
        await protect_start_page(callback_query.message)
    raise StopPropagation
