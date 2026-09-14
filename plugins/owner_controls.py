from pyrogram import Client, filters

from config import Config
from helper.database import db
from helper.plans import PLANS, Plan
from helper.utils import humanbytes


def owner_only(user_id: int) -> bool:
    return bool(Config.OWNER_ID and int(user_id) == int(Config.OWNER_ID))


@Client.on_message(filters.private & filters.command("ownerplans"), group=-300)
async def owner_plans(client, message):
    if not getattr(client, "is_main_bot", False) or not owner_only(message.from_user.id):
        return
    lines = ["💎 **Current Plans**", ""]
    for key in ("pro", "premium", "ultra"):
        plan = PLANS[key]
        lines.append(f"**{key}** — {plan.name} — `{plan.stars} ⭐` — `{humanbytes(plan.daily_limit)}/day` — `{plan.days} days`")
    lines.append("")
    lines.append("Edit with `/ownerstars <plan> <stars>` or `/ownerlimit <plan> <gb>`.")
    await message.reply_text("\n".join(lines))


@Client.on_message(filters.private & filters.command("ownerstars"), group=-300)
async def owner_stars(client, message):
    if not getattr(client, "is_main_bot", False) or not owner_only(message.from_user.id):
        return
    if len(message.command) != 3 or message.command[1] not in {"pro", "premium", "ultra"}:
        await message.reply_text("Usage: `/ownerstars <pro|premium|ultra> <stars>`")
        return
    key = message.command[1]
    try:
        stars = int(message.command[2])
        if not 1 <= stars <= 100000:
            raise ValueError
    except ValueError:
        await message.reply_text("❌ Invalid Stars value.")
        return
    old = PLANS[key]
    PLANS[key] = Plan(key=old.key, name=old.name, stars=stars, daily_limit=old.daily_limit, days=old.days)
    await message.reply_text(f"✅ {old.name} is now `{stars} ⭐` for this running bot process.")


@Client.on_message(filters.private & filters.command("ownerlimit"), group=-300)
async def owner_limit(client, message):
    if not getattr(client, "is_main_bot", False) or not owner_only(message.from_user.id):
        return
    if len(message.command) != 3 or message.command[1] not in {"pro", "premium", "ultra"}:
        await message.reply_text("Usage: `/ownerlimit <pro|premium|ultra> <gb>`")
        return
    key = message.command[1]
    try:
        gb = float(message.command[2])
        if not 0 < gb <= 100000:
            raise ValueError
    except ValueError:
        await message.reply_text("❌ Invalid GB value.")
        return
    old = PLANS[key]
    PLANS[key] = Plan(key=old.key, name=old.name, stars=old.stars, daily_limit=int(gb * 1024**3), days=old.days)
    await message.reply_text(f"✅ {old.name} daily limit is now `{gb:g} GB` for this running bot process.")


@Client.on_message(filters.private & filters.command("ownerbots"), group=-300)
async def owner_bots(client, message):
    if not getattr(client, "is_main_bot", False) or not owner_only(message.from_user.id):
        return
    lines = ["🤖 **Registered Clone Bots**", ""]
    async for clone in db.get_all_clones():
        lines.append(f"• @{clone.get('bot_username') or 'unknown'} — `{clone.get('bot_id')}` — `{clone.get('status', 'unknown')}`")
    if len(lines) == 2:
        lines.append("No clone bots are registered.")
    await message.reply_text("\n".join(lines))
