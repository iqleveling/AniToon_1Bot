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

FORCE_SUB_CHANNELS = [
    {"name": "Channel 1", "chat": "@Anitoon_edit", "link": "https://t.me/Anitoon_edit"},
    {"name": "Channel 2", "chat": "@anitoons_ani", "link": "https://t.me/anitoons_ani"},
    {"name": "Channel 3", "chat": "@mangauniverse_ani", "link": "https://t.me/mangauniverse_ani"},
    {"name": "Channel 4", "chat": -1002732670564, "link": Config.FORCE_SUB_PRIVATE_LINK},
]
PRIVATE_FORCE_SUB_CHAT_ID = -1002732670564


def _force_sub_client(client: Client) -> Client:
    """Use the main bot for force-sub checks when this handler runs on a clone."""
    return getattr(client, "force_sub_client", None) or client


def _valid_join_link(value) -> bool:
    value = str(value or "").strip()
    return value.startswith(("https://t.me/", "http://t.me/", "https://telegram.me/", "http://telegram.me/", "tg://"))


async def _ensure_private_force_sub_link(client: Client) -> str:
    client = _force_sub_client(client)
    channel = next(c for c in FORCE_SUB_CHANNELS if c["chat"] == PRIVATE_FORCE_SUB_CHAT_ID)
    configured = str(channel.get("link") or "").strip()

    if configured and _valid_join_link(configured):
        return configured

    if configured and not _valid_join_link(configured):
        log.warning("Force-sub: invalid FORCE_SUB_PRIVATE_LINK configured; generating a valid invite")
        channel["link"] = ""

    try:
        invite = await client.create_chat_invite_link(
            PRIVATE_FORCE_SUB_CHAT_ID,
            name="AniToon Force Sub",
            creates_join_request=True,
        )
        channel["link"] = invite.invite_link
        log.info("Force-sub: created private invite link for Channel 4")
        return channel["link"]
    except Exception:
        log.exception("Force-sub: could not create private invite link")
        return ""


@Client.on_chat_join_request(filters.chat(PRIVATE_FORCE_SUB_CHAT_ID), group=-100)
async def private_force_sub_join_request(client: Client, request):
    """Automatically approve private-channel join requests using the main bot."""
    user = getattr(request, "from_user", None)
    if not user:
        return
    try:
        approval_client = _force_sub_client(client)
        await approval_client.approve_chat_join_request(PRIVATE_FORCE_SUB_CHAT_ID, user.id)
        await db.clear_force_sub_request(user.id, PRIVATE_FORCE_SUB_CHAT_ID)
        log.info("Force-sub: automatically approved private-channel request user=%s", user.id)
    except Exception:
        log.exception("Force-sub: failed to approve private-channel request user=%s", user.id)
        try:
            await db.mark_force_sub_request(user.id, PRIVATE_FORCE_SUB_CHAT_ID)
        except Exception:
            pass


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
    try:
        member = await client.get_chat_member(chat_id=channel["chat"], user_id=user_id)
        status = _normalize_status(getattr(member, "status", None))
        if status in {"owner", "administrator", "member", "restricted"}:
            if channel["chat"] == PRIVATE_FORCE_SUB_CHAT_ID:
                try:
                    await db.clear_force_sub_request(user_id, PRIVATE_FORCE_SUB_CHAT_ID)
                except Exception:
                    pass
            return True
        if status in {"left", "kicked", "banned"}:
            return False
        return None
    except UserNotParticipant:
        return False
    except Exception:
        log.exception("Force-sub verification failed user=%s channel=%s", user_id, channel["name"])
        return None


async def get_force_sub_status(client: Client, user_id: int):
    """Return force-sub status for both main bot and clone bots.

    Clone bots delegate membership checks to the main bot because the required
    channels are configured and administered by the main AniToon bot. This
    prevents every clone owner from having to add their clone as an admin to
    all force-sub channels.
    """
    checker = _force_sub_client(client)
    await _ensure_private_force_sub_link(checker)
    results = await asyncio.gather(*[_check_one_channel(checker, user_id, channel) for channel in FORCE_SUB_CHANNELS])
    joined_count = 0
    missing_channels = []
    failed_channels = []
    for channel, result in zip(FORCE_SUB_CHANNELS, results):
        if result is True:
            joined_count += 1
        elif result is False:
            missing_channels.append(channel)
        else:
            failed_channels.append(channel)
    return joined_count, missing_channels, failed_channels


def make_force_sub_text(joined_count: int, missing_count: int, failed_count: int = 0):
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
            "\n⚠️ I could not verify one or more channels right now. "
            "The join buttons are still shown below."
        )
    return text + "\n\nTap the remaining channel buttons, join them, then press **🔄 Check & Retry**."


def make_force_sub_keyboard(missing_channels, failed_channels=None):
    failed_channels = failed_channels or []
    rows = []
    seen = set()
    channels = list(missing_channels) + [c for c in failed_channels if c not in missing_channels]
    for channel in channels:
        name = str(channel.get("name") or "Required Channel")
        link = str(channel.get("link") or "").strip()
        if _valid_join_link(link) and link not in seen:
            rows.append([InlineKeyboardButton(f"📢 {name}", url=link)])
            seen.add(link)
    rows.append([InlineKeyboardButton("🔄 Check & Retry", callback_data="check_force_sub")])
    return InlineKeyboardMarkup(rows)


def _force_sub_error_keyboard():
    rows = []
    for channel in FORCE_SUB_CHANNELS:
        link = str(channel.get("link") or "").strip()
        if _valid_join_link(link):
            rows.append([InlineKeyboardButton(f"📢 {channel['name']}", url=link)])
    rows.append([InlineKeyboardButton("🔄 Check & Retry", callback_data="check_force_sub")])
    return InlineKeyboardMarkup(rows)


async def send_force_sub_message(client: Client, message: Message):
    try:
        joined_count, missing_channels, failed_channels = await get_force_sub_status(client, message.from_user.id)
    except Exception:
        log.exception("Force-sub status check failed for user %s", message.from_user.id)
        await message.reply_text(
            "⚠️ **Channel verification is temporarily unavailable.**\n\n"
            "Please use the channel buttons below, then press **🔄 Check & Retry**.",
            reply_markup=_force_sub_error_keyboard(),
        )
        return False

    if joined_count == len(FORCE_SUB_CHANNELS) and not missing_channels and not failed_channels:
        return True
    await message.reply_text(
        make_force_sub_text(joined_count, len(missing_channels), len(failed_channels)),
        reply_markup=make_force_sub_keyboard(missing_channels, failed_channels),
    )
    return False


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
                "⚠️ **Channel verification is temporarily unavailable.**\n\n"
                "Please join the required channels using the buttons below, then press **🔄 Check & Retry**.",
                reply_markup=_force_sub_error_keyboard(),
            )
            return

        if joined_count != len(FORCE_SUB_CHANNELS) or missing_channels or failed_channels:
            await message.reply_text(
                make_force_sub_text(joined_count, len(missing_channels), len(failed_channels)),
                reply_markup=make_force_sub_keyboard(missing_channels, failed_channels),
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
