from __future__ import annotations
import asyncio, json, urllib.error, urllib.parse, urllib.request
from pyrogram import Client, filters, StopPropagation
from pyrogram.raw.types import UpdateBotPrecheckoutQuery
from pyrogram.raw.functions.messages import SetBotPrecheckoutResults
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config import Config
from helper.database import db
from helper.plans import PLANS, all_paid_plans, get_plan
from helper.utils import humanbytes


def _api(method, params):
    token = Config.BOT_TOKEN
    if not token: raise RuntimeError("BOT_TOKEN is missing")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}", data=urllib.parse.urlencode(params).encode(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r: result = json.loads(r.read().decode())
    except urllib.error.HTTPError as e: result = json.loads(e.read().decode())
    if not result.get("ok"): raise RuntimeError(result.get("description", "Telegram Bot API error"))
    return result

async def _api_async(method, params): return await asyncio.to_thread(_api, method, params)

@Client.on_callback_query(filters.regex(r"^upgrade$"), group=-1500)
async def payment_upgrade(client, cb):
    await cb.answer()
    rows = [[InlineKeyboardButton(f"{p.name} • {p.stars} ⭐", callback_data=f"payfix:{p.key}")] for p in all_paid_plans()]
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="start")])
    await cb.message.edit_text("💎 **AniToon Premium Plans**\n\nChoose a plan:", reply_markup=InlineKeyboardMarkup(rows))
    raise StopPropagation

@Client.on_callback_query(filters.regex(r"^payfix:(pro|premium|ultra)$"), group=-1500)
async def payment_buy(client, cb):
    await cb.answer("Creating Stars invoice...")
    plan = get_plan(cb.matches[0].group(1))
    payload = f"anitoon|{plan.key}|{int(getattr(client, 'bot_id', 0))}|{cb.from_user.id}"
    try:
        await _api_async("sendInvoice", {"chat_id": cb.from_user.id, "title": f"AniToon {plan.name}"[:32], "description": f"{plan.name} for 30 days. Daily limit {humanbytes(plan.daily_limit)}."[:255], "payload": payload, "currency": "XTR", "prices": json.dumps([{"label": plan.name[:32], "amount": int(plan.stars)}], separators=(",", ":"))})
    except Exception as e:
        await cb.message.reply_text(f"❌ **Payment Error**\n\n`{str(e)[:1200]}`")
    raise StopPropagation

@Client.on_raw_update()
async def payment_precheckout(client, update, users, chats):
    if not getattr(client, "is_main_bot", False) or not isinstance(update, UpdateBotPrecheckoutQuery): return
    try:
        parts = (update.payload.decode() if isinstance(update.payload, bytes) else str(update.payload)).split("|")
        if len(parts) != 4 or parts[0] != "anitoon" or parts[1] not in PLANS: raise ValueError("Invalid payment payload")
        plan = get_plan(parts[1])
        if int(update.user_id) != int(parts[3]) or update.currency != "XTR" or int(update.total_amount) != plan.stars: raise ValueError("Invalid payment")
        await client.invoke(SetBotPrecheckoutResults(query_id=update.query_id, success=True))
    except Exception as e:
        try: await client.invoke(SetBotPrecheckoutResults(query_id=update.query_id, success=False, error=str(e)[:200]))
        except Exception: pass

def _payment_filter(_, __, message): return getattr(message, "successful_payment", None) is not None

@Client.on_message(filters.private & filters.create(_payment_filter), group=-1500)
async def payment_success(client, message):
    payment = message.successful_payment
    try:
        parts = str(payment.invoice_payload).split("|")
        if len(parts) != 4 or parts[0] != "anitoon": raise ValueError("Invalid payment payload")
        plan = get_plan(parts[1]); target_bot = int(parts[2])
        if int(parts[3]) != message.from_user.id or payment.currency != "XTR" or int(payment.total_amount) != plan.stars: raise ValueError("Invalid Stars payment")
        charge = str(payment.telegram_payment_charge_id)
        if await db.record_payment(message.from_user.id, target_bot, plan.key, payment.total_amount, charge):
            await db.set_plan(message.from_user.id, target_bot, plan.key, payment.total_amount, charge)
            await message.reply_text(f"✅ **Payment Successful!**\n\n💎 {plan.name}\n⭐ `{payment.total_amount} Stars`\n📅 30 days")
        else: await message.reply_text("ℹ️ This Stars payment was already processed.")
    except Exception as e:
        await message.reply_text(f"⚠️ **Payment received but activation failed.**\n\n`{str(e)[:800]}`")
    raise StopPropagation
