import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import Config
from helper.database import db
from helper.plans import get_plan, all_paid_plans
from helper.utils import humanbytes
from plugins.ui import main_menu, force_sub_menu

log = logging.getLogger(__name__)


async def _check_one_channel(client: Client, channel, user_id: int) -> bool:
    """Return True only when Telegram confirms the user is a member."""
    try:
        member = await asyncio.wait_for(
            client.get_chat_member(channel, user_id),
            timeout=12,
        )
        status = str(getattr(member, "status", "")).lower()
        return status not in {"left", "kicked", "banned", "restricted"}
    except FloodWait as exc:
        # A membership check must never block /start for Telegram's full wait.
        log.warning(
            "FloodWait during force-sub check for %s: %s seconds",
            channel,
            getattr(exc, "value", "unknown"),
        )
        return False
    except asyncio.TimeoutError:
        log.warning("Force-sub membership check timed out for %s", channel)
        return False
    except Exception:
        # Fail closed. If the bot cannot verify a required channel, the user
        # should not be allowed into the protected bot flow.
        log.exception("Force-sub membership check failed for %s", channel)
        return False


async def is_force_subscribed(client: Client, user_id: int) -> bool:
    channels = list(Config.FORCE_SUB[:4])
    if not channels:
        return True

    results = await asyncio.gather(
        *(_check_one_channel(client, channel, user_id) for channel in channels),
        return_exceptions=False,
    )
    return all(results)


async def _register_user(user_id: int):
    try:
        await db.add_user(user_id)
    except Exception:
        log.exception("Could not add user %s", user_id)


async def _send_force_sub(client: Client, message: Message):
    text = (
        "🔒 **Join Required Channels**\n\n"
        "To use **AniToon**, please join all 4 required channels below.\n\n"
        "📢 Channel 1\n"
        "📢 Channel 2\n"
        "📢 Channel 3\n"
        "📢 Channel 4\n\n"
        "After joining all four channels, press **🔄 Check & Retry**."
    )
    await message.reply_text(
        text,
        reply_markup=force_sub_menu(),
    )


async def _show_force_sub_check(client: Client, callback_query):
    user_id = callback_query.from_user.id
    ok = await is_force_subscribed(client, user_id)

    if ok:
        await callback_query.answer("✅ All required channels joined!", show_alert=False)
        await _reply_start(client, callback_query.message, force_check=True)
        return

    await callback_query.answer(
        "❌ Please join all 4 channels first.",
        show_alert=True,
    )

    text = (
        "🔒 **Join Required Channels**\n\n"
        "You still need to join all 4 required channels.\n\n"
        "📢 Channel 1\n"
        "📢 Channel 2\n"
        "📢 Channel 3\n"
        "📢 Channel 4\n\n"
        "Join them and press **🔄 Check & Retry** again."
    )

    keyboard = force_sub_menu()
    try:
        await callback_query.message.edit_text(
            text,
            reply_markup=keyboard,
        )
    except Exception:
        try:
            await callback_query.message.edit_caption(
                caption=text,
                reply_markup=keyboard,
            )
        except Exception:
            await callback_query.message.reply_text(
                text,
                reply_markup=keyboard,
            )


async def _reply_start(
    client: Client,
    message: Message,
    force_check: bool = False,
):
    if not message.from_user:
        return

    user_id = message.from_user.id
    bot_id = int(getattr(client, "bot_id", 0))

    # Registration is intentionally independent of the UI response.
    asyncio.create_task(_register_user(user_id))

    # Deep link for Premium page. This is kept before the normal start menu.
    command = getattr(message, "command", None) or []
    if (
        getattr(client, "is_main_bot", False)
        and len(command) > 1
        and command[1].startswith("plans_")
    ):
        try:
            target_bot_id = int(command[1].split("_", 1)[1])
        except (ValueError, IndexError):
            target_bot_id = bot_id

        buttons = [
            [
                InlineKeyboardButton(
                    f"{plan.name} — {plan.stars} ⭐",
                    callback_data=f"buy:{plan.key}:{target_bot_id}",
                )
            ]
            for plan in all_paid_plans()
        ]
        buttons.append([
            InlineKeyboardButton("⬅️ Back", callback_data="start")
        ])

        await message.reply_text(
            "💎 **AniToon Premium Plans**\n\n"
            "Choose a plan for 30 days:\n\n"
            "🆓 **Free** — 0 ⭐ — 10 GB/day\n"
            "⚡ **Pro** — 10 ⭐ — 20 GB/day\n"
            "💎 **Premium** — 20 ⭐ — 40 GB/day\n"
            "👑 **Ultra** — 30 ⭐ — 60 GB/day\n\n"
            "⭐ Payment is handled by AniToon_1Bot.",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    # Force-sub is checked for every /start and for Check & Retry.
    # The actual force-sub screen has buttons for exactly the four channels.
    if Config.FORCE_SUB and not await is_force_subscribed(client, user_id):
        await _send_force_sub(client, message)
        return

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
        log.exception("Database read failed during /start")

    welcome_text = (
        "🔥 **Welcome to AniToon Bot** 🔥\n\n"
        f"👋 Hello **{message.from_user.first_name}**!\n\n"
        "📂 Send me any file, video or audio to rename and process it.\n\n"
        f"💎 **Plan:** {plan_name}\n"
        f"🚀 **Used Today:** `{humanbytes(used)}`\n"
        f"⏳ **Remaining:** `{humanbytes(remaining)}`\n\n"
        "🖼 Send an image to save a custom thumbnail.\n"
        "📝 Use `/setcaption` for a custom caption.\n"
        "🏷 Use `/metadata` for audio/subtitle track names."
    )

    keyboard = main_menu(getattr(client, "is_main_bot", False))

    if Config.START_PIC:
        try:
            await message.reply_photo(
                photo=Config.START_PIC,
                caption=welcome_text,
                reply_markup=keyboard,
            )
            return
        except Exception:
            log.exception("START_PIC failed; falling back to text")

    await message.reply_text(
        welcome_text,
        reply_markup=keyboard,
    )


# Negative group guarantees that /start gets priority over broad private-message
# handlers in other plugins.
@Client.on_message(
    filters.private & filters.command("start"),
    group=-100,
)
async def start(client: Client, message: Message):
    try:
        await _reply_start(client, message)
    except Exception:
        log.exception("/start handler failed")
        try:
            await message.reply_text(
                "⚠️ AniToon is online, but `/start` encountered a temporary error.\n\n"
                "Please press /start again."
            )
        except Exception:
            pass


@Client.on_callback_query(
    filters.regex(r"^force_retry$"),
    group=-100,
)
async def force_sub_retry(client: Client, callback_query):
    await _show_force_sub_check(client, callback_query)
