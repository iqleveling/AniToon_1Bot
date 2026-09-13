"""Clean AniToon /start experience and start-page actions."""

import shutil

from pyrogram import Client, StopPropagation, filters

from helper.database import db
from helper.job_state import jobs
from helper.plans import get_plan
from helper.utils import humanbytes
from plugins.rename import _download_job
from plugins.start import get_force_sub_status, make_force_sub_text, make_force_sub_keyboard
from plugins.ui import main_menu


@Client.on_message(
    filters.private & (filters.document | filters.video | filters.audio),
    group=-2000,
)
async def replace_waiting_file_job(client, message):
    """Clear an abandoned rename/convert prompt and let the normal intake handle the new file."""
    job = await jobs.get_user_job(message.from_user.id)
    if not job or job.selected_action not in {"rename_format", "custom_name", "convert_name"}:
        return

    shutil.rmtree(job.work_dir, ignore_errors=True)
    await jobs.remove(job.job_id)
    await message.reply_text("🔄 **Previous rename request cleared. Starting the new file...**")
    # Do NOT call _download_job here. Allow the high-priority verified intake
    # handler in file_action_fix.py to process this same message exactly once.
    return


@Client.on_message(
    filters.private & filters.command("start"),
    group=-200,
)
async def clean_start(client, message):
    """Render the clean start page while preserving ForceSub checks."""
    user_id = message.from_user.id
    bot_id = int(getattr(client, "bot_id", 0))

    try:
        await db.add_user(user_id)
    except Exception:
        pass

    if getattr(client, "is_main_bot", False):
        joined, missing, failed = await get_force_sub_status(client, user_id)
        total = len(missing) + joined + len(failed)
        if joined != total or missing or failed:
            await message.reply_text(
                make_force_sub_text(joined, len(missing), len(failed)),
                reply_markup=make_force_sub_keyboard(missing, failed),
            )
            raise StopPropagation

    plan_name = "🆓 Free"
    used = 0
    remaining = 10 * 1024 * 1024 * 1024

    try:
        subscription = await db.get_subscription(user_id, bot_id)
        plan = get_plan(subscription.get("plan", "free"))
        used = await db.get_usage(user_id, bot_id)
        plan_name = plan.name
        remaining = max(plan.daily_limit - used, 0)
    except Exception:
        pass

    text = (
        "🔥 **Welcome to AniToon Bot** 🔥\n\n"
        f"👋 Hello **{message.from_user.first_name}**!\n\n"
        f"💎 **Plan:** {plan_name}\n"
        f"📊 **Used today:** `{humanbytes(used)}`\n"
        f"📦 **Remaining:** `{humanbytes(remaining)}`\n\n"
        "⚡ Fast processing • Clean filenames • Advanced media tools"
    )

    await message.reply_text(
        text,
        reply_markup=main_menu(getattr(client, "is_main_bot", False)),
    )
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^start_rename$"), group=-200)
async def start_rename_action(client, callback_query):
    await callback_query.answer()
    await callback_query.message.reply_text(
        "✏️ **Rename:**\n"
        "Send me the file you want to rename."
    )
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^start_convert$"), group=-200)
async def start_convert_action(client, callback_query):
    await callback_query.answer()
    await callback_query.message.reply_text(
        "🔄 **Convert**\n\nSend me the video, audio, or document you want to convert.\n\n"
        "After the file is received, choose **Convert** and select the output format."
    )
    raise StopPropagation


@Client.on_callback_query(filters.regex(r"^start$"), group=-200)
async def start_from_button(client, callback_query):
    await callback_query.answer()
    user = callback_query.from_user
    bot_id = int(getattr(client, "bot_id", 0))

    if getattr(client, "is_main_bot", False):
        joined, missing, failed = await get_force_sub_status(client, user.id)
        total = len(missing) + joined + len(failed)
        if joined != total or missing or failed:
            await callback_query.message.edit_text(
                make_force_sub_text(joined, len(missing), len(failed)),
                reply_markup=make_force_sub_keyboard(missing, failed),
            )
            raise StopPropagation

    plan_name = "🆓 Free"
    used = 0
    remaining = 10 * 1024 * 1024 * 1024
    try:
        subscription = await db.get_subscription(user.id, bot_id)
        plan = get_plan(subscription.get("plan", "free"))
        used = await db.get_usage(user.id, bot_id)
        plan_name = plan.name
        remaining = max(plan.daily_limit - used, 0)
    except Exception:
        pass

    text = (
        "🔥 **Welcome to AniToon Bot** 🔥\n\n"
        f"👋 Hello **{user.first_name}**!\n\n"
        f"💎 **Plan:** {plan_name}\n"
        f"📊 **Used today:** `{humanbytes(used)}`\n"
        f"📦 **Remaining:** `{humanbytes(remaining)}`\n\n"
        "⚡ Fast processing • Clean filenames • Advanced media tools"
    )
    try:
        await callback_query.message.edit_text(
            text,
            reply_markup=main_menu(getattr(client, "is_main_bot", False)),
        )
    except Exception:
        await callback_query.message.reply_text(
            text,
            reply_markup=main_menu(getattr(client, "is_main_bot", False)),
        )
    raise StopPropagation
