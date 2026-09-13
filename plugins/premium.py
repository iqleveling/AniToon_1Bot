from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ForceReply,
)
from pyrogram.raw.types import (
    LabeledPrice,
    UpdateBotPrecheckoutQuery,
)
from pyrogram.raw.functions.messages import (
    SetBotPrecheckoutResults,
)

from config import Config
from helper.database import db
from helper.plans import (
    PLANS,
    all_paid_plans,
    get_plan,
)
from helper.utils import humanbytes
from plugins.ui import edit_callback_message


# ============================================================
# HELPERS
# ============================================================

def is_main_bot(client):
    return getattr(
        client,
        "is_main_bot",
        False,
    )


def get_bot_id(client):
    return int(
        getattr(
            client,
            "bot_id",
            0,
        )
    )


# ============================================================
# PLAN MENU
# ============================================================

async def send_plan_menu(
    client,
    chat_id,
    target_bot_id,
):
    buttons = []

    for plan in all_paid_plans():
        buttons.append(
            [
                InlineKeyboardButton(
                    f"{plan.name} • {plan.stars} ⭐",
                    callback_data=(
                        f"buy:{plan.key}:"
                        f"{int(target_bot_id)}"
                    ),
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                "⬅️ Back",
                callback_data="start",
            )
        ]
    )

    text = (
        "💎 **AniToon Premium Plans**\n\n"
        "Choose your plan for 30 days:\n\n"
        "🆓 **Free**\n"
        "⭐ 0 Stars\n"
        "📊 10 GB/day\n\n"
        "⚡ **Pro**\n"
        "⭐ 10 Stars / 30 days\n"
        "📊 20 GB/day\n\n"
        "💎 **Premium**\n"
        "⭐ 20 Stars / 30 days\n"
        "📊 40 GB/day\n\n"
        "👑 **Ultra**\n"
        "⭐ 30 Stars / 30 days\n"
        "📊 60 GB/day\n\n"
        "✂️ Large files are split into parts "
        "when required."
    )

    await client.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(
            buttons
        ),
    )


# ============================================================
# /PLAN
# ============================================================

@Client.on_message(
    filters.private
    & filters.command(
        [
            "plan",
            "myplan",
            "status",
        ]
    )
)
async def user_plan_status(
    client,
    message,
):
    user_id = message.from_user.id
    bot_id = get_bot_id(client)

    if not await db.is_user_exist(
        user_id
    ):
        await db.add_user(
            user_id
        )

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

    remaining = max(
        plan.daily_limit - used,
        0,
    )

    expires_at = subscription.get(
        "expires_at"
    )

    expiry_text = (
        expires_at.strftime(
            "%d %b %Y, %H:%M"
        )
        if expires_at
        else "No expiry"
    )

    text = (
        "📊 **AniToon Plan Status**\n\n"
        f"👤 **User:** "
        f"`{message.from_user.first_name}`\n"
        f"🆔 **ID:** `{user_id}`\n\n"
        f"💎 **Plan:** {plan.name}\n"
        f"⭐ **Price:** "
        f"`{plan.stars} Stars`\n"
        f"📈 **Used Today:** "
        f"`{humanbytes(used)}`\n"
        f"⏳ **Remaining:** "
        f"`{humanbytes(remaining)}`\n"
        f"📅 **Expires:** "
        f"`{expiry_text}`"
    )

    if is_main_bot(client):
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "💎 View Plans",
                        callback_data="upgrade",
                    )
                ]
            ]
        )
    elif Config.MAIN_BOT_USERNAME:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "💎 Buy / Upgrade",
                        url=(
                            "https://t.me/"
                            f"{Config.MAIN_BOT_USERNAME}"
                            f"?start=plans_{bot_id}"
                        ),
                    )
                ]
            ]
        )
    else:
        keyboard = None

    await message.reply_text(
        text,
        reply_markup=keyboard,
    )


# ============================================================
# UPGRADE BUTTON
# ============================================================

@Client.on_callback_query(
    filters.regex("^upgrade$")
)
async def upgrade_button(
    client,
    callback_query,
):
    await callback_query.answer()

    bot_id = get_bot_id(client)

    if not is_main_bot(client):
        if not Config.MAIN_BOT_USERNAME:
            return await edit_callback_message(
                callback_query,
                "❌ **Main payment bot is not configured.**",
            )

        await edit_callback_message(
            callback_query,
            "💎 **AniToon Premium**\n\n"
            "Premium purchases are handled by "
            "**AniToon_1Bot**.\n\n"
            "Tap below to continue.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "⭐ Open Main Payment Bot",
                            url=(
                                "https://t.me/"
                                f"{Config.MAIN_BOT_USERNAME}"
                                f"?start=plans_{bot_id}"
                            ),
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "⬅️ Back",
                            callback_data="start",
                        )
                    ],
                ]
            ),
        )

        return

    await send_plan_menu(
        client,
        callback_query.from_user.id,
        bot_id,
    )


# ============================================================
# BUY PLAN
# ============================================================

@Client.on_callback_query(
    filters.regex(
        r"^buy:(pro|premium|ultra):(\d+)$"
    )
)
async def buy_plan(
    client,
    callback_query,
):
    if not is_main_bot(client):
        return await callback_query.answer(
            "Payment must be completed through AniToon_1Bot.",
            show_alert=True,
        )

    await callback_query.answer()

    match = callback_query.matches[0]

    plan_key = match.group(1)

    target_bot_id = int(
        match.group(2)
    )

    plan = get_plan(
        plan_key
    )

    payload = (
        "anitoon|"
        f"{plan_key}|"
        f"{target_bot_id}"
    )

    try:
        await client.send_invoice(
            chat_id=callback_query.from_user.id,
            title=f"AniToon {plan.name}",
            description=(
                f"{plan.name} plan for 30 days. "
                f"Daily limit: "
                f"{humanbytes(plan.daily_limit)}."
            ),
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=[
                LabeledPrice(
                    label=plan.name,
                    amount=plan.stars,
                )
            ],
        )

    except Exception as e:
        await client.send_message(
            callback_query.from_user.id,
            (
                "❌ **Payment Error**\n\n"
                f"`{str(e)[:1000]}`"
            ),
        )


# ============================================================
# PRE-CHECKOUT
# ============================================================

@Client.on_raw_update()
async def pre_checkout_handler(
    client,
    update,
    users,
    chats,
):
    if not is_main_bot(client):
        return

    if not isinstance(
        update,
        UpdateBotPrecheckoutQuery,
    ):
        return

    try:
        payload = update.payload.decode(
            "utf-8"
        )

        parts = payload.split("|")

        if len(parts) != 3:
            await client.invoke(
                SetBotPrecheckoutResults(
                    query_id=update.query_id,
                    success=False,
                    error=(
                        "Invalid payment information."
                    ),
                )
            )
            return

        prefix = parts[0]
        plan_key = parts[1]

        if prefix != "anitoon":
            await client.invoke(
                SetBotPrecheckoutResults(
                    query_id=update.query_id,
                    success=False,
                    error="Invalid payment.",
                )
            )
            return

        if plan_key not in PLANS:
            await client.invoke(
                SetBotPrecheckoutResults(
                    query_id=update.query_id,
                    success=False,
                    error="Invalid plan.",
                )
            )
            return

        plan = get_plan(
            plan_key
        )

        if update.currency != "XTR":
            await client.invoke(
                SetBotPrecheckoutResults(
                    query_id=update.query_id,
                    success=False,
                    error=(
                        "Invalid payment currency."
                    ),
                )
            )
            return

        if (
            update.total_amount
            != plan.stars
        ):
            await client.invoke(
                SetBotPrecheckoutResults(
                    query_id=update.query_id,
                    success=False,
                    error=(
                        "Invalid payment amount."
                    ),
                )
            )
            return

        await client.invoke(
            SetBotPrecheckoutResults(
                query_id=update.query_id,
                success=True,
            )
        )

    except Exception as e:
        print(
            f"Pre-checkout error: {e}"
        )

        try:
            await client.invoke(
                SetBotPrecheckoutResults(
                    query_id=update.query_id,
                    success=False,
                    error=(
                        "Payment validation failed."
                    ),
                )
            )
        except Exception:
            pass


# ============================================================
# SUCCESSFUL PAYMENT
# ============================================================

@Client.on_message(
    filters.private
    & filters.incoming
)
async def payment_message_handler(
    client,
    message,
):
    if not is_main_bot(client):
        return

    payment = getattr(
        message,
        "successful_payment",
        None,
    )

    if not payment:
        return

    try:
        payload = (
            payment.invoice_payload
        )

        parts = payload.split("|")

        if len(parts) != 3:
            return await message.reply_text(
                "❌ Invalid payment information."
            )

        prefix = parts[0]
        plan_key = parts[1]

        target_bot_id = int(
            parts[2]
        )

        if prefix != "anitoon":
            return

        if plan_key not in PLANS:
            return await message.reply_text(
                "❌ Invalid plan."
            )

        plan = get_plan(
            plan_key
        )

        if payment.currency != "XTR":
            return await message.reply_text(
                "❌ Invalid payment currency."
            )

        if (
            payment.total_amount
            != plan.stars
        ):
            return await message.reply_text(
                "❌ Invalid payment amount."
            )

        charge_id = (
            payment.telegram_payment_charge_id
        )

        recorded = (
            await db.record_payment(
                user_id=message.from_user.id,
                bot_id=target_bot_id,
                plan_key=plan_key,
                stars=payment.total_amount,
                charge_id=charge_id,
            )
        )

        if not recorded:
            return await message.reply_text(
                "ℹ️ This payment was already processed."
            )

        await db.set_plan(
            user_id=message.from_user.id,
            bot_id=target_bot_id,
            plan_key=plan_key,
            stars_paid=payment.total_amount,
            payment_id=charge_id,
        )

        subscription = (
            await db.get_subscription(
                message.from_user.id,
                target_bot_id,
            )
        )

        expires_at = (
            subscription.get(
                "expires_at"
            )
        )

        expiry_text = (
            expires_at.strftime(
                "%d %b %Y, %H:%M"
            )
            if expires_at
            else "No expiry"
        )

        await message.reply_text(
            "✅ **Payment Successful!**\n\n"
            f"💎 **Plan:** {plan.name}\n"
            f"⭐ **Paid:** "
            f"`{payment.total_amount} Stars`\n"
            "📅 **Duration:** `30 days`\n"
            f"⏳ **Expires:** "
            f"`{expiry_text}`\n\n"
            "🎉 Your plan is now active."
        )

    except Exception as e:
        print(
            f"Payment processing error: {e}"
        )

        await message.reply_text(
            "⚠️ **Payment received, "
            "but activation failed.**\n\n"
            "Please use `/paysupport`."
        )


# ============================================================
# PAYMENT SUPPORT
# ============================================================

@Client.on_message(
    filters.private
    & filters.command("paysupport")
)
async def payment_support(
    client,
    message,
):
    await message.reply_text(
        "💳 **Payment Support**\n\n"
        "For Stars payment or Premium "
        "activation problems, contact "
        "@AniToon_Official."
    )


# ============================================================
# CLONE CREATION
# ============================================================

@Client.on_message(
    filters.private
    & filters.command("clone")
)
async def initiate_clone(
    client,
    message,
):
    if not is_main_bot(client):
        return await message.reply_text(
            "❌ Clone creation is available "
            "only from the main AniToon bot."
        )

    if not Config.IS_CLONE_ALLOWED:
        return await message.reply_text(
            "❌ **Clone Engine is disabled.**"
        )

    user_id = message.from_user.id

    if not await db.is_user_exist(
        user_id
    ):
        await db.add_user(
            user_id
        )

    await message.reply_text(
        "🤖 **Create Your AniToon Clone**\n\n"
        "1️⃣ Open @BotFather.\n"
        "2️⃣ Create a new bot.\n"
        "3️⃣ Copy the Bot Token.\n"
        "4️⃣ Reply to this message with the token.\n\n"
        "Your clone will have the normal "
        "AniToon features.\n\n"
        "⚠️ Never share your BotFather token "
        "publicly.",
        reply_markup=ForceReply(
            selective=True
        ),
    )


# ============================================================
# PROCESS CLONE TOKEN
# ============================================================

@Client.on_message(
    filters.private
    & filters.reply
    & filters.text
)
async def process_clone_token(
    client,
    message,
):
    if not is_main_bot(client):
        return

    reply = message.reply_to_message

    if not reply or not reply.text:
        return

    if (
        "Create Your AniToon Clone"
        not in reply.text
    ):
        return

    token = message.text.strip()

    if (
        ":" not in token
        or len(token) < 20
    ):
        return await message.reply_text(
            "❌ **Invalid Bot Token.**"
        )

    status = await message.reply_text(
        "🔄 **Verifying your BotFather token...**"
    )

    test_client = None

    try:
        test_client = Client(
            name=(
                f"verify_"
                f"{message.from_user.id}"
            ),
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=token,
            in_memory=True,
        )

        await test_client.start()

        bot_info = (
            await test_client.get_me()
        )

        await test_client.stop()

        test_client = None

        existing = (
            await db.get_clone_by_bot_id(
                bot_info.id
            )
        )

        if existing:
            return await status.edit_text(
                "⚠️ **This bot is already connected.**"
            )

        if not client.clone_manager:
            return await status.edit_text(
                "❌ **Clone Manager is unavailable.**"
            )

        clone = (
            await client.clone_manager.add_clone(
                message.from_user.id,
                token,
            )
        )

        if not clone:
            return await status.edit_text(
                "❌ **Unable to start the clone.**"
            )

        await status.edit_text(
            "✅ **Clone Created Successfully!**\n\n"
            f"🤖 **Bot:** "
            f"@{bot_info.username}\n"
            f"🆔 **Bot ID:** "
            f"`{bot_info.id}`\n\n"
            "🟢 **Status:** Online\n\n"
            "✅ Normal AniToon features are enabled.\n"
            "❌ Owner dashboard is only available "
            "on the main AniToon bot.\n\n"
            "⭐ Premium payments are handled "
            "through AniToon_1Bot."
        )

    except Exception as e:
        if test_client:
            try:
                await test_client.stop()
            except Exception:
                pass

        await status.edit_text(
            "❌ **Clone Creation Failed**\n\n"
            f"`{str(e)[:1000]}`"
        )
