from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.raw.types import UpdateBotPrecheckoutQuery
from pyrogram.raw.functions.messages import SetBotPrecheckoutResults

from config import Config
from helper.database import db
from helper.plans import all_paid_plans, get_plan, PLANS
from helper.utils import humanbytes
from plugins.ui import edit_callback_message


def is_main_bot(client):
    return bool(getattr(client, "is_main_bot", False))


def get_bot_id(client):
    return int(getattr(client, "bot_id", 0))


async def send_plan_menu(client, chat_id, target_bot_id):
    buttons = []
    for plan in all_paid_plans():
        buttons.append([InlineKeyboardButton(f"{plan.name} • {plan.stars} ⭐", callback_data=f"buy:{plan.key}:{int(target_bot_id)}")])
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="start")])
    text = (
        "💎 **AniToon Premium Plans**\n\nChoose your plan for 30 days:\n\n"
        "🆓 **Free**\n⭐ 0 Stars\n📊 10 GB/day\n\n"
        "⚡ **Pro**\n⭐ 10 Stars / 30 days\n📊 20 GB/day\n\n"
        "💎 **Premium**\n⭐ 20 Stars / 30 days\n📊 40 GB/day\n\n"
        "👑 **Ultra**\n⭐ 30 Stars / 30 days\n📊 60 GB/day\n\n"
        "✂️ Large files are split into parts when required."
    )
    await client.send_message(chat_id=chat_id, text=text, reply_markup=InlineKeyboardMarkup(buttons))


@Client.on_message(filters.private & filters.command(["plan", "myplan", "status"]))
async def user_plan_status(client, message):
    user_id = message.from_user.id
    bot_id = get_bot_id(client)
    if not await db.is_user_exist(user_id):
        await db.add_user(user_id)
    subscription = await db.get_subscription(user_id, bot_id)
    plan = get_plan(subscription.get("plan", "free"))
    used = await db.get_usage(user_id, bot_id)
    remaining = max(plan.daily_limit - used, 0)
    expires_at = subscription.get("expires_at")
    expiry_text = expires_at.strftime("%d %b %Y, %H:%M") if expires_at else "No expiry"
    text = (
        "📊 **AniToon Plan Status**\n\n"
        f"👤 **User:** `{message.from_user.first_name}`\n"
        f"🆔 **ID:** `{user_id}`\n\n"
        f"💎 **Plan:** {plan.name}\n"
        f"⭐ **Price:** `{plan.stars} Stars`\n"
        f"📈 **Used Today:** `{humanbytes(used)}`\n"
        f"⏳ **Remaining:** `{humanbytes(remaining)}`\n"
        f"📅 **Expires:** `{expiry_text}`"
    )
    if is_main_bot(client):
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("💎 View Plans", callback_data="upgrade")]])
    elif Config.MAIN_BOT_USERNAME:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("💎 Buy / Upgrade", url=f"https://t.me/{Config.MAIN_BOT_USERNAME}?start=plans_{bot_id}")
        ]])
    else:
        keyboard = None
    await message.reply_text(text, reply_markup=keyboard)


@Client.on_callback_query(filters.regex("^upgrade$"))
async def upgrade_button(client, callback_query):
    await callback_query.answer()
    bot_id = get_bot_id(client)
    if not is_main_bot(client):
        if not Config.MAIN_BOT_USERNAME:
            return await edit_callback_message(callback_query, "❌ **Main payment bot is not configured.**")
        return await edit_callback_message(
            callback_query,
            "💎 **AniToon Premium**\n\nPremium purchases are handled by **AniToon_1Bot**.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐ Open Main Payment Bot", url=f"https://t.me/{Config.MAIN_BOT_USERNAME}?start=plans_{bot_id}")],
                [InlineKeyboardButton("⬅️ Back", callback_data="start")],
            ]),
        )
    await send_plan_menu(client, callback_query.from_user.id, bot_id)


async def _bot_api(method: str, params: dict) -> dict:
    """Call the Bot API directly; this avoids Pyrogram MTProto peer resolution for invoices."""
    token = Config.BOT_TOKEN
    if not token:
        raise RuntimeError("BOT_TOKEN is not configured")
    url = f"https://api.telegram.org/bot{token}/{method}"
    body = urllib.parse.urlencode(params).encode("utf-8")

    def request():
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
        return json.loads(raw)

    result = await asyncio.to_thread(request)
    if not result.get("ok"):
        description = result.get("description") or "Telegram Bot API request failed"
        raise RuntimeError(description)
    return result


async def _send_stars_invoice(client, user_id: int, plan, payload: str):
    params = {
        "chat_id": int(user_id),
        "title": f"AniToon {plan.name}"[:32],
        "description": f"{plan.name} plan for 30 days. Daily limit: {humanbytes(plan.daily_limit)}."[:255],
        "payload": payload,
        "provider_token": "",
        "currency": "XTR",
        "prices": json.dumps([{"label": plan.name[:32], "amount": int(plan.stars)}], separators=(",", ":")),
    }
    return await _bot_api("sendInvoice", params)


@Client.on_callback_query(filters.regex(r"^buy:(pro|premium|ultra):(\d+)$"))
async def buy_plan(client, callback_query):
    if not is_main_bot(client):
        return await callback_query.answer("Payment must be completed through AniToon_1Bot.", show_alert=True)
    await callback_query.answer()
    match = callback_query.matches[0]
    plan_key = match.group(1)
    target_bot_id = int(match.group(2))
    plan = get_plan(plan_key)
    payload = f"anitoon|{plan_key}|{target_bot_id}|{callback_query.from_user.id}"
    try:
        await _send_stars_invoice(client, callback_query.from_user.id, plan, payload)
    except Exception as exc:
        await client.send_message(
            callback_query.from_user.id,
            "❌ **Payment Error**\n\nThe Stars invoice could not be created.\n\n"
            f"`{str(exc)[:1000]}`",
        )


async def _answer_precheckout(client, update, success: bool, error: str | None = None):
    await client.invoke(SetBotPrecheckoutResults(
        query_id=update.query_id,
        success=success,
        error=error,
    ))


@Client.on_raw_update()
async def pre_checkout_handler(client, update, users, chats):
    if not is_main_bot(client) or not isinstance(update, UpdateBotPrecheckoutQuery):
        return
    try:
        payload = update.payload.decode("utf-8") if isinstance(update.payload, (bytes, bytearray)) else str(update.payload)
        parts = payload.split("|")
        if len(parts) != 4 or parts[0] != "anitoon" or parts[1] not in PLANS:
            return await _answer_precheckout(client, update, False, "Invalid payment information.")
        plan = get_plan(parts[1])
        buyer_id = int(parts[3])
        if int(update.user_id) != buyer_id:
            return await _answer_precheckout(client, update, False, "This invoice belongs to another user.")
        if update.currency != "XTR":
            return await _answer_precheckout(client, update, False, "Telegram Stars payments only.")
        if int(update.total_amount) != int(plan.stars):
            return await _answer_precheckout(client, update, False, "Invalid payment amount.")
        await _answer_precheckout(client, update, True)
    except Exception:
        try:
            await _answer_precheckout(client, update, False, "Payment validation failed.")
        except Exception:
            pass


def _successful_payment_filter(_, __, message):
    return bool(getattr(message, "successful_payment", None))


SUCCESSFUL_PAYMENT_FILTER = filters.create(_successful_payment_filter)


@Client.on_message(filters.private & SUCCESSFUL_PAYMENT_FILTER)
async def payment_message_handler(client, message):
    if not is_main_bot(client):
        return
    payment = getattr(message, "successful_payment", None)
    if not payment:
        return
    try:
        parts = str(payment.invoice_payload).split("|")
        if len(parts) != 4 or parts[0] != "anitoon":
            return await message.reply_text("❌ Invalid payment information.")
        plan_key = parts[1]
        target_bot_id = int(parts[2])
        buyer_id = int(parts[3])
        if buyer_id != message.from_user.id or plan_key not in PLANS:
            return await message.reply_text("❌ Invalid payment information.")
        plan = get_plan(plan_key)
        if payment.currency != "XTR" or int(payment.total_amount) != int(plan.stars):
            return await message.reply_text("❌ Invalid Stars payment.")
        charge_id = str(payment.telegram_payment_charge_id)
        recorded = await db.record_payment(
            user_id=message.from_user.id,
            bot_id=target_bot_id,
            plan_key=plan_key,
            stars=int(payment.total_amount),
            charge_id=charge_id,
        )
        if not recorded:
            return await message.reply_text("ℹ️ This payment was already processed.")
        await db.set_plan(
            user_id=message.from_user.id,
            bot_id=target_bot_id,
            plan_key=plan_key,
            stars_paid=int(payment.total_amount),
            payment_id=charge_id,
        )
        subscription = await db.get_subscription(message.from_user.id, target_bot_id)
        expires_at = subscription.get("expires_at")
        expiry_text = expires_at.strftime("%d %b %Y, %H:%M") if expires_at else "No expiry"
        await message.reply_text(
            "✅ **Payment Successful!**\n\n"
            f"💎 **Plan:** {plan.name}\n"
            f"⭐ **Paid:** `{payment.total_amount} Stars`\n"
            "📅 **Duration:** `30 days`\n"
            f"⏳ **Expires:** `{expiry_text}`\n\n"
            "🎉 Your plan is now active."
        )
    except Exception:
        await message.reply_text("⚠️ **Payment received, but activation failed.**\n\nPlease use `/paysupport`.")


@Client.on_message(filters.private & filters.command("paysupport"))
async def payment_support(client, message):
    await message.reply_text(
        "💳 **Payment Support**\n\nFor Stars payment or Premium activation problems, contact @AniToon_Official."
    )
