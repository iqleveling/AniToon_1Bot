import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import Config
from helper.database import db
from helper.plans import get_plan, all_paid_plans
from helper.utils import humanbytes
from plugins.ui import main_menu

log = logging.getLogger(__name__)


# ============================================================
# FORCE SUBSCRIBE CHANNELS
# ============================================================

FORCE_SUB_CHANNELS = [
    {
        "name": "Channel 1",
        "chat": "@Anitoon_edit",
        "link": "https://t.me/Anitoon_edit",
    },
    {
        "name": "Channel 2",
        "chat": "@anitoons_ani",
        "link": "https://t.me/anitoons_ani",
    },
    {
        "name": "Channel 3",
        "chat": "@mangauniverse_ani",
        "link": "https://t.me/mangauniverse_ani",
    },
    {
        "name": "Channel 4",
        "chat": -1002732670564,
        "link": "",  # Put your private-channel invite link here.
    },
]


# ============================================================
# STATUS NORMALIZER
# ============================================================

def _normalize_status(status) -> str:
    """
    Pyrogram status can be represented differently depending
    on the returned object/version. Normalize everything to a
    simple lowercase string.
    """

    if status is None:
        return ""

    # Plain string
    if isinstance(status, str):
        return status.strip().lower()

    # Enum-like object
    value = getattr(status, "value", None)
    if value is not None:
        return str(value).strip().lower()

    name = getattr(status, "name", None)
    if name is not None:
        return str(name).strip().lower()

    return str(status).strip().lower()


# ============================================================
# CHECK ONE CHANNEL
# ============================================================

async def _check_one_channel(
    client: Client,
    user_id: int,
    channel: dict,
):
    """
    Returns:
        True   -> definitely joined
        False  -> definitely not joined
        None   -> bot could not verify channel
    """

    try:
        member = await client.get_chat_member(
            chat_id=channel["chat"],
            user_id=user_id,
        )

        status = _normalize_status(
            getattr(member, "status", None)
        )

        log.info(
            "Force-sub: user=%s channel=%s status=%s",
            user_id,
            channel["name"],
            status,
        )

        # Joined/allowed states.
        if status in {
            "owner",
            "administrator",
            "member",
            "restricted",
        }:
            return True

        # Definitely not joined.
        if status in {
            "left",
            "kicked",
            "banned",
        }:
            return False

        # Unknown status should not silently be treated as
        # "not joined".
        log.warning(
            "Force-sub unknown status: user=%s channel=%s status=%r",
            user_id,
            channel["name"],
            status,
        )
        return None

    except Exception:
        log.exception(
            "Force-sub verification failed: user=%s channel=%s chat=%s",
            user_id,
            channel["name"],
            channel["chat"],
        )
        return None


# ============================================================
# CHECK ALL 4 CHANNELS
# ============================================================

async def get_force_sub_status(
    client: Client,
    user_id: int,
):
    """
    Returns:
        joined_count,
        missing_channels,
        failed_channels
    """

    results = await asyncio.gather(
        *[
            _check_one_channel(
                client,
                user_id,
                channel,
            )
            for channel in FORCE_SUB_CHANNELS
        ]
    )

    joined_count = 0
    missing_channels = []
    failed_channels = []

    for channel, result in zip(
        FORCE_SUB_CHANNELS,
        results,
    ):
        if result is True:
            joined_count += 1

        elif result is False:
            missing_channels.append(channel)

        else:
            failed_channels.append(channel)

    return (
        joined_count,
        missing_channels,
        failed_channels,
    )


# ============================================================
# FORCE SUBSCRIBE TEXT
# ============================================================

def make_force_sub_text(
    joined_count: int,
    missing_count: int,
    failed_count: int = 0,
):
    total = len(FORCE_SUB_CHANNELS)
    remaining = missing_count + failed_count

    text = (
        "🔒 **Join Required Channels**\n\n"
        "To use AniToon, please join all required channels.\n\n"
        f"📊 **Joined:** `{joined_count}/{total}`\n"
        f"❗ **Remaining:** `{remaining}`\n"
    )

    if failed_count:
        text += (
            "\n⚠️ I could not verify one or more channels. "
            "Please try again in a moment."
        )

    text += (
        "\n\n"
        "Tap the remaining channel buttons below, "
        "join them, then press **🔄 Check & Retry**."
    )

    return text


# ============================================================
# FORCE SUBSCRIBE KEYBOARD
# ============================================================

def make_force_sub_keyboard(
    missing_channels,
    failed_channels=None,
):
    """
    ONLY unjoined/unverified channels are displayed.

    Check & Retry is always at the bottom.
    """

    failed_channels = failed_channels or []

    rows = []

    # Display unjoined channels first.
    for channel in missing_channels:
        if channel["link"]:
            rows.append(
                [
                    InlineKeyboardButton(
                        f"📢 {channel['name']}",
                        url=channel["link"],
                    )
                ]
            )

    # If a channel could not be checked and has a link,
    # show it so the user can open it and retry.
    for channel in failed_channels:
        if channel not in missing_channels and channel["link"]:
            rows.append(
                [
                    InlineKeyboardButton(
                        f"📢 {channel['name']}",
                        url=channel["link"],
                    )
                ]
            )

    rows.append(
        [
            InlineKeyboardButton(
                "🔄 Check & Retry",
                callback_data="check_force_sub",
            )
        ]
    )

    return InlineKeyboardMarkup(rows)


# ============================================================
# SHOW FORCE SUB MESSAGE
# ============================================================

async def send_force_sub_message(
    client: Client,
    message: Message,
):
    (
        joined_count,
        missing_channels,
        failed_channels,
    ) = await get_force_sub_status(
        client,
        message.from_user.id,
    )

    total = len(FORCE_SUB_CHANNELS)

    # All four verified.
    if (
        joined_count == total
        and not missing_channels
        and not failed_channels
    ):
        return True

    text = make_force_sub_text(
        joined_count,
        len(missing_channels),
        len(failed_channels),
    )

    keyboard = make_force_sub_keyboard(
        missing_channels,
        failed_channels,
    )

    await message.reply_text(
        text,
        reply_markup=keyboard,
    )

    return False


# ============================================================
# /START
# ============================================================

@Client.on_message(
    filters.private & filters.command("start")
)
async def start(
    client: Client,
    message: Message,
):
    user_id = message.from_user.id
    bot_id = int(
        getattr(
            client,
            "bot_id",
            0,
        )
    )

    try:
        # ----------------------------------------------------
        # REGISTER USER
        # ----------------------------------------------------

        try:
            await db.add_user(user_id)
        except Exception:
            log.exception(
                "Could not create/find user %s",
                user_id,
            )

        # ----------------------------------------------------
        # FORCE SUBSCRIBE
        # ----------------------------------------------------

        (
            joined_count,
            missing_channels,
            failed_channels,
        ) = await get_force_sub_status(
            client,
            user_id,
        )

        total = len(FORCE_SUB_CHANNELS)

        if (
            joined_count != total
            or missing_channels
            or failed_channels
        ):
            text = make_force_sub_text(
                joined_count,
                len(missing_channels),
                len(failed_channels),
            )

            keyboard = make_force_sub_keyboard(
                missing_channels,
                failed_channels,
            )

            await message.reply_text(
                text,
                reply_markup=keyboard,
            )
            return

        # ----------------------------------------------------
        # PREMIUM DEEP LINK
        # ----------------------------------------------------

        if (
            len(message.command) > 1
            and message.command[1].startswith("plans_")
        ):
            try:
                target_bot_id = int(
                    message.command[1].split(
                        "_",
                        1,
                    )[1]
                )
            except (
                ValueError,
                IndexError,
            ):
                target_bot_id = bot_id

            buttons = [
                [
                    InlineKeyboardButton(
                        f"{plan.name} — {plan.stars} ⭐",
                        callback_data=(
                            f"buy:{plan.key}:{target_bot_id}"
                        ),
                    )
                ]
                for plan in all_paid_plans()
            ]

            buttons.append(
                [
                    InlineKeyboardButton(
                        "⬅️ Back",
                        callback_data="start",
                    )
                ]
            )

            await message.reply_text(
                "💎 **AniToon Premium Plans**\n\n"
                "Choose a plan for 30 days:\n\n"
                "🆓 **Free** — 0 ⭐ — 10 GB/day\n"
                "⚡ **Pro** — 10 ⭐ — 20 GB/day\n"
                "💎 **Premium** — 20 ⭐ — 40 GB/day\n"
                "👑 **Ultra** — 30 ⭐ — 60 GB/day\n\n"
                "⭐ Payment is handled by AniToon_1Bot.",
                reply_markup=InlineKeyboardMarkup(
                    buttons
                ),
            )
            return

        # ----------------------------------------------------
        # LOAD USER PLAN
        # ----------------------------------------------------

        plan_name = "🆓 Free"
        used = 0
        remaining = (
            10
            * 1024
            * 1024
            * 1024
        )

        try:
            subscription = (
                await db.get_subscription(
                    user_id,
                    bot_id,
                )
            )

            plan = get_plan(
                subscription.get(
                    "plan",
                    "free",
                )
            )

            used = await db.get_usage(
                user_id,
                bot_id,
            )

            plan_name = plan.name

            remaining = max(
                plan.daily_limit - used,
                0,
            )

        except Exception:
            log.exception(
                "Database read failed during /start"
            )

        # ----------------------------------------------------
        # WELCOME
        # ----------------------------------------------------

        welcome_text = (
            "🔥 **Welcome to AniToon Bot** 🔥\n\n"
            f"👋 Hello **{message.from_user.first_name}**!\n\n"
            "📂 Send me any file, video or audio "
            "to rename and process it.\n\n"
            f"💎 **Plan:** {plan_name}\n"
            f"🚀 **Used Today:** `{humanbytes(used)}`\n"
            f"⏳ **Remaining:** `{humanbytes(remaining)}`\n\n"
            "🖼 Send an image to save a custom thumbnail.\n"
            "📝 Use `/setcaption` for a custom caption.\n"
            "🏷 Use `/metadata` for audio/subtitle track names."
        )

        keyboard = main_menu(
            getattr(
                client,
                "is_main_bot",
                False,
            )
        )

        if Config.START_PIC:
            try:
                await message.reply_photo(
                    photo=Config.START_PIC,
                    caption=welcome_text,
                    reply_markup=keyboard,
                )
                return
            except Exception:
                log.exception(
                    "START_PIC failed; sending text instead"
                )

        await message.reply_text(
            welcome_text,
            reply_markup=keyboard,
        )

    except Exception:
        log.exception(
            "Unhandled /start error for user %s",
            user_id,
        )

        try:
            await message.reply_text(
                "⚠️ A temporary error occurred.\n\n"
                "Please send `/start` again.",
            )
        except Exception:
            pass
