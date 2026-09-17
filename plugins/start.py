import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.errors import UserNotParticipant
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Config
from helper.database import db
from helper.plans import get_plan, all_paid_plans
from helper.utils import humanbytes
from plugins.ui import main_menu

log = logging.getLogger(__name__)


def _force_sub_client(client: Client) -> Client:
    """Use the main bot for force-sub checks when this handler runs on a clone."""
    return getattr(client, "force_sub_client", None) or client


def _split_csv(value: str) -> list[str]:
    return [part.strip().lstrip("@") for part in str(value or "").split(",") if part.strip()]


def _configured_force_sub_channels() -> list[dict]:
    """Build the force-sub list from the public channel environment variables."""
    usernames = _split_csv(Config.FORCE_SUB)
    links = [part.strip() for part in str(Config.FORCE_SUB_LINKS or "").split(",") if part.strip()]

    channels = []
    for index, username in enumerate(usernames):
        link = links[index] if index < len(links) else f"https://t.me/{username}"
        channels.append({
            "name": username,
            "chat": f"@{username}",
            "link": link,
        })

    if not channels:
        defaults = ["Anitoon_edit", "anitoons_ani", "mangauniverse_ani", "ani_seas"]
        channels = [
            {"name": username, "chat": f"@{username}", "link": f"https://t.me/{username}"}
            for username in defaults
        ]
    return channels


# Public force-sub channels only.
FORCE_SUB_CHANNELS = _configured_force_sub_channels()


def _valid_join_link(value) -> bool:
    value = str(value or "").strip()
    return value.startswith((
        "https://t.me/",
        "http://t.me/",
        "https://telegram.me/",
        "http://telegram.me/",
        "tg://",
    ))


def _normalize_status(status) -> str:
    if status is None:
        return ""
    if isinstance(status, str):
        return status.strip().lower()
    value = getattr(status, "value", None)
    if value is not None:
        return str(value).strip().lower()
    name = getattr(status, "name", None)
    if name is not None:
        return str(name).strip().lower()
    return str(status).strip().lower()


async def _check_one_channel(client: Client, user_id: int, channel: dict):
    """Return True=joined, False=confirmed missing, None=verification error."""
    try:
        member = await client.get_chat_member(chat_id=channel["chat"], user_id=user_id)
        status = _normalize_status(getattr(member, "status", None))
        if status in {"owner", "administrator", "member"}:
            return True
        if status == "restricted":
            return bool(getattr(member, "is_member", False))
        if status in {"left", "kicked", "banned"}:
            return False
        return None
    except UserNotParticipant:
        return False
    except Exception:
        log.exception("Force-sub verification failed user=%s channel=%s", user_id, channel.get("name"))
        return None


async def get_force_sub_status(client: Client, user_id: int):
    """Check every public channel and return only channels the user has not joined."""
    checker = _force_sub_client(client)
    channels = _configured_force_sub_channels()
    FORCE_SUB_CHANNELS.clear()
    FORCE_SUB_CHANNELS.extend(channels)

    results = await asyncio.gather(
        *[_check_one_channel(checker, user_id, channel) for channel in channels]
    )

    joined_count = 0
    missing_channels = []
    failed_channels = []
    for channel, result in zip(channels, results):
        if result is True:
            joined_count += 1
        elif result is False:
            # Only confirmed non-members are shown a Join button.
            missing_channels.append(channel)
        else:
            failed_channels.append(channel)

    return joined_count, missing_channels, failed_channels


def make_force_sub_text(joined_count: int = 0, missing_count: int = 0, failed_count: int = 0):
    """Minimal force-sub text; membership counts and verification details are hidden."""
    return "🔒 **Join Required Channels**\n\nJoin the required channels below, then press **🔄 Check & Retry**."


def make_force_sub_keyboard(missing_channels, failed_channels=None, refresh_callback="check_force_sub"):
    """Show Join buttons ONLY for confirmed missing channels, plus one refresh button."""
    rows = []
    seen = set()
    for channel in missing_channels or []:
        name = str(channel.get("name") or "Required Channel")
        link = str(channel.get("link") or "").strip()
        if _valid_join_link(link) and link not in seen:
            rows.append([InlineKeyboardButton(f"📢 {name}", url=link)])
            seen.add(link)
    rows.append([InlineKeyboardButton("🔄 Check & Retry", callback_data=refresh_callback)])
    return InlineKeyboardMarkup(rows)


def _force_sub_error_keyboard():
    """When Telegram cannot verify membership, show only Refresh (never false Join buttons)."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Check & Retry", callback_data="check_force_sub")]
    ])


async def send_force_sub_message(client: Client, message: Message):
    try:
        joined_count, missing_channels, failed_channels = await get_force_sub_status(client, message.from_user.id)
    except Exception:
        log.exception("Force-sub status check failed for user %s", message.from_user.id)
        await message.reply_text(
            "🔒 **Join Required Channels**\n\nPlease press **🔄 Check & Retry**.",
            reply_markup=_force_sub_error_keyboard(),
        )
        return False

    total = len(FORCE_SUB_CHANNELS)
    if joined_count == total and not missing_channels and not failed_channels:
        return True

    await message.reply_text(
        make_force_sub_text(),
        reply_markup=make_force_sub_keyboard(missing_channels),
    )
    return False


@Client.on_callback_query(filters.regex(r"^check_force_sub$"), group=-100)
async def check_force_sub_callback(client: Client, callback_query):
    """Refresh public-channel membership and open Home when all channels are joined."""
    if not callback_query.from_user:
        return await callback_query.answer()
    try:
        await callback_query.answer("Checking…")
        joined_count, missing_channels, failed_channels = await get_force_sub_status(
            client, callback_query.from_user.id
        )
        if not missing_channels and not failed_channels and joined_count == len(FORCE_SUB_CHANNELS):
            try:
                await callback_query.message.delete()
            except Exception:
                pass
            await callback_query.message.reply_text(
                "🔥 **Welcome to AniToon Bot** 🔥",
                reply_markup=main_menu(getattr(client, "is_main_bot", False)),
            )
            return

        text = make_force_sub_text()
        keyboard = make_force_sub_keyboard(missing_channels)
        try:
            await callback_query.message.edit_text(text, reply_markup=keyboard)
        except Exception:
            await callback_query.message.reply_text(text, reply_markup=keyboard)
    except Exception:
        log.exception("Force-sub callback failed for user %s", callback_query.from_user.id)
        await callback_query.answer("Please try again.", show_alert=True)


@Client.on_message(filters.private & filters.command("start"))
async def start(client: Client, message: Message):
    user_id = message.from_user.id
    bot_id = int(getattr(client, "bot_id", 0))
    try:
        try:
            await db.add_user(user_id)
        except Exception:
            log.exception("Could not create/find user %s", user_id)

        try:
            joined_count, missing_channels, failed_channels = await get_force_sub_status(client, user_id)
        except Exception:
            log.exception("Start: force-sub verification crashed for user %s", user_id)
            await message.reply_text(
                "🔒 **Join Required Channels**\n\nPlease press **🔄 Check & Retry**.",
                reply_markup=_force_sub_error_keyboard(),
            )
            return

        if missing_channels or failed_channels:
            await message.reply_text(
                make_force_sub_text(),
                reply_markup=make_force_sub_keyboard(missing_channels),
            )
            return

        if len(message.command) > 1 and message.command[1].startswith("plans_"):
            try:
                target_bot_id = int(message.command[1].split("_", 1)[1])
            except (ValueError, IndexError):
                target_bot_id = bot_id
            buttons = [[InlineKeyboardButton(f"{plan.name} — {plan.stars} ⭐", callback_data=f"buy:{plan.key}:{target_bot_id}")] for plan in all_paid_plans()]
            buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="start")])
            await message.reply_text(
                "💎 **AniToon Premium Plans**\n\nChoose a plan for 30 days:\n\n"
                "🆓 **Free** — 0 ⭐ — 10 GB/day\n⚡ **Pro** — 10 ⭐ — 20 GB/day\n"
                "💎 **Premium** — 20 ⭐ — 40 GB/day\n👑 **Ultra** — 30 ⭐ — 60 GB/day\n\n"
                "⭐ Payment is handled by AniToon_1Bot.",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            return

        plan_name, used, remaining = "🆓 Free", 0, 10 * 1024 * 1024 * 1024
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
            f"💎 **Plan:** {plan_name}\n🚀 **Used Today:** `{humanbytes(used)}`\n"
            f"⏳ **Remaining:** `{humanbytes(remaining)}`\n\n"
            "🖼 Send an image to save a custom thumbnail.\n📝 Use `/setcaption` for a custom caption.\n"
            "🏷 Use `/metadata` for audio/subtitle track names."
        )
        keyboard = main_menu(getattr(client, "is_main_bot", False))
        if Config.START_PIC:
            try:
                await message.reply_photo(Config.START_PIC, caption=welcome_text, reply_markup=keyboard)
                return
            except Exception:
                pass
        await message.reply_text(welcome_text, reply_markup=keyboard)
    except Exception:
        log.exception("Start handler failed for user %s", user_id)
        await message.reply_text("❌ Something went wrong. Please try `/start` again.")
