import logging

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Config
from helper.database import db
from helper.plans import get_plan, all_paid_plans
from helper.utils import humanbytes
from plugins.ui import main_menu, force_sub_menu

log = logging.getLogger(__name__)


async def _force_sub_ok(client, user_id: int) -> bool:
    """Return True only when the user is a member of all four required chats."""
    channels = Config.FORCE_SUB[:4]
    if len(channels) < 4:
        log.error("FORCE_SUB must contain exactly 4 channels; found %s", len(channels))
        return False

    for channel in channels:
        try:
            member = await client.get_chat_member(channel, user_id)
            status = str(getattr(member, "status", "")).lower()
            if status in {"left", "kicked", "banned"}:
                return False
        except Exception:
            # A force-sub check failure must fail closed.
            log.exception("Force-sub check failed for %s", channel)
            return False
    return True


async def _force_sub_links(client):
    """Resolve display links for the four required chats."""
    channels = Config.FORCE_SUB[:4]
    configured = Config.FORCE_SUB_LINKS[:4]
    links = []

    for i, channel in enumerate(channels):
        link = configured[i] if i < len(configured) else ""
        if link:
            links.append(link)
            continue

        try:
            chat = await client.get_chat(channel)
            username = getattr(chat, "username", None)
            invite_link = getattr(chat, "invite_link", None)
            if username:
                link = f"https://t.me/{username}"
            elif invite_link:
                link = invite_link
        except Exception:
            log.exception("Could not resolve force-sub link for %s", channel)

        links.append(link)

    return links


async def _send_force_sub(client, message: Message):
    links = await _force_sub_links(client)
    await message.reply_text(
        "🔒 **Join Required Channels**\n\n"
        "To use AniToon, please join all 4 required channels below.\n\n"
        "1️⃣ Channel 1\n"
        "2️⃣ Channel 2\n"
        "3️⃣ Channel 3\n"
        "4️⃣ Channel 4\n\n"
        "After joining all four channels, press **🔄 Check & Retry**.",
        reply_markup=force_sub_menu(links),
    )


async def _reply_start(client, message: Message, user_override=None):
    actor = user_override or message.from_user
    user_id = actor.id
    bot_id = int(getattr(client, "bot_id", 0))

    # Always make a DB user record, but don't make a temporary Mongo outage
    # make /start completely silent.
    try:
        await db.add_user(user_id)
    except Exception:
        log.exception("Could not create/find user %s", user_id)

    # Main-bot deep link for clone purchases.
    if (
        getattr(client, "is_main_bot", False)
        and len(message.command) > 1
        and message.command[1].startswith("plans_")
    ):
        try:
            target_bot_id = int(message.command[1].split("_", 1)[1])
        except (ValueError, IndexError):
            target_bot_id = bot_id

        buttons = [
            [InlineKeyboardButton(
                f"{plan.name} — {plan.stars} ⭐",
                callback_data=f"buy:{plan.key}:{target_bot_id}",
            )]
            for plan in all_paid_plans()
        ]
        buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="start")])
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

    if not await _force_sub_ok(client, user_id):
        await _send_force_sub(client, message)
        return

    # Defaults let the bot still answer if MongoDB is temporarily unavailable.
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
        f"👋 Hello **{actor.first_name}**!\n\n"
        "📂 Send me any file, video or audio to rename and process it.\n\n"
        f"💎 **Plan:** {plan_name}\n"
        f"🚀 **Used Today:** `{humanbytes(used)}`\n"
        f"⏳ **Remaining:** `{humanbytes(remaining)}`\n\n"
        "🖼 Send an image to save a custom thumbnail.\n"
        "📝 Use `/setcaption` for a custom caption.\n"
        "🏷 Use `/metadata` for audio/subtitle track names."
    )

    keyboard = main_menu(getattr(client, "is_main_bot", False))
    start_pic = Config.START_PIC

    if start_pic:
        try:
            await message.reply_photo(
                photo=start_pic,
                caption=welcome_text,
                reply_markup=keyboard,
            )
            return
        except Exception:
            log.exception("START_PIC failed; falling back to text")

    await message.reply_text(welcome_text, reply_markup=keyboard)


@Client.on_message(filters.private & filters.command("start"))
async def start(client: Client, message: Message):
    try:
        await _reply_start(client, message)
    except Exception:
        # /start must never be silent because a secondary feature failed.
        log.exception("/start handler failed")
        try:
            await message.reply_text(
                "⚠️ AniToon is online, but a temporary setup error occurred. "
                "Please send `/start` again in a few seconds."
            )
        except Exception:
            pass


@Client.on_callback_query(filters.regex(r"^check_fsub$"))
async def check_force_subscription(client: Client, callback_query):
    user_id = callback_query.from_user.id

    if await _force_sub_ok(client, user_id):
        await callback_query.answer("✅ All required channels joined.", show_alert=False)
        # Re-enter the normal start flow using the callback user's identity.
        try:
            await callback_query.message.delete()
        except Exception:
            pass
        await _reply_start(
            client,
            callback_query.message,
            user_override=callback_query.from_user,
        )
        return

    await callback_query.answer(
        "❌ Please join all 4 channels first.",
        show_alert=True,
    )
    links = await _force_sub_links(client)
    try:
        await callback_query.message.edit_text(
            "🔒 **Join Required Channels**\n\n"
            "Please join all 4 required channels, then press **🔄 Check & Retry**.",
            reply_markup=force_sub_menu(links),
        )
    except Exception:
        try:
            await callback_query.message.edit_caption(
                "🔒 **Join Required Channels**\n\n"
                "Please join all 4 required channels, then press **🔄 Check & Retry**.",
                reply_markup=force_sub_menu(links),
            )
        except Exception:
            pass
