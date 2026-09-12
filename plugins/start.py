import logging

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Config
from helper.database import db
from helper.plans import get_plan, all_paid_plans
from helper.utils import humanbytes
from plugins.ui import main_menu

log = logging.getLogger(__name__)


async def _force_sub_ok(client, user_id: int) -> bool:
    for channel in Config.FORCE_SUB:
        try:
            member = await client.get_chat_member(channel, user_id)
            if str(member.status).lower() in {"left", "kicked", "banned"}:
                return False
        except Exception:
            # A bad/missing force-sub channel must not kill /start.
            log.warning("Force-sub check failed for %s", channel, exc_info=True)
    return True


async def _reply_start(client, message: Message):
    user_id = message.from_user.id
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
        await message.reply_text(
            "🚫 **Access Denied**\n\n"
            "Please join the required channel(s) and send `/start` again."
        )
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
