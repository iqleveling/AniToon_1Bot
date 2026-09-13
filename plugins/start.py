from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import Config


# ============================================================
# FORCE-SUB CHANNEL CONFIG
# ============================================================

def get_force_sub_channels():
    """
    Returns:
        [
            {
                "chat": "@channel",
                "name": "Channel 1",
                "link": "https://t.me/channel",
            },
            ...
        ]
    """

    raw_channels = [
        item.strip()
        for item in Config.FORCE_SUB.split(",")
        if item.strip()
    ]

    raw_links = [
        item.strip()
        for item in Config.FORCE_SUB_LINKS.split(",")
        if item.strip()
    ]

    # Your current four required channels.
    default_names = [
        "Channel 1",
        "Channel 2",
        "Channel 3",
        "Channel 4",
    ]

    channels = []

    for index, chat in enumerate(raw_channels[:4]):
        link = (
            raw_links[index]
            if index < len(raw_links)
            else ""
        )

        # Public username automatically gets a Telegram URL.
        if (
            not link
            and chat.startswith("@")
        ):
            link = (
                f"https://t.me/"
                f"{chat.lstrip('@')}"
            )

        channels.append(
            {
                "chat": chat,
                "name": (
                    default_names[index]
                    if index < len(default_names)
                    else f"Channel {index + 1}"
                ),
                "link": link,
            }
        )

    return channels


async def check_channel_membership(
    client: Client,
    user_id: int,
    chat,
) -> bool:
    """
    Returns True when the user is considered
    joined/member of the channel.

    Bot must be an administrator in the
    required channels for reliable checks.
    """

    try:
        member = await client.get_chat_member(
            chat_id=chat,
            user_id=user_id,
        )

        status = getattr(
            member,
            "status",
            "",
        )

        # These statuses mean the user has access.
        return status in {
            "owner",
            "administrator",
            "member",
            "restricted",
        }

    except Exception:
        # Private/deleted/inaccessible channel:
        # treat as not verified.
        return False


async def get_membership_status(
    client: Client,
    user_id: int,
):
    """
    Returns:
        joined_channels,
        missing_channels
    """

    channels = get_force_sub_channels()

    joined = []
    missing = []

    for channel in channels:
        is_joined = await check_channel_membership(
            client,
            user_id,
            channel["chat"],
        )

        if is_joined:
            joined.append(channel)
        else:
            missing.append(channel)

    return joined, missing


def build_force_sub_keyboard(
    missing_channels,
):
    """
    IMPORTANT:
    Only unjoined channels are displayed.
    Check & Retry is always at the bottom.
    """

    rows = []

    for channel in missing_channels:
        link = channel["link"]

        # Do not create a broken button.
        if not link:
            continue

        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📢 {channel['name']}",
                    url=link,
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="🔄 Check & Retry",
                callback_data="check_force_sub",
            )
        ]
    )

    return InlineKeyboardMarkup(rows)


def force_sub_text(
    joined_count: int,
    total_count: int,
):
    remaining = max(
        total_count - joined_count,
        0,
    )

    return (
        "🔒 **Join Required Channels**\n\n"
        "Please join all required channels "
        "below to use AniToon.\n\n"
        f"📊 **Joined:** {joined_count}/{total_count}\n"
        f"❗ **Remaining:** {remaining}\n\n"
        "After joining the remaining channels, "
        "press **🔄 Check & Retry**."
    )


async def show_force_sub(
    client: Client,
    message_or_query,
):
    """
    Checks membership and shows only missing
    channels.
    """

    if hasattr(
        message_or_query,
        "from_user",
    ):
        user = message_or_query.from_user
    else:
        user = None

    if not user:
        return False

    joined, missing = (
        await get_membership_status(
            client,
            user.id,
        )
    )

    total = len(
        joined
    ) + len(
        missing
    )

    # All required channels joined.
    if not missing:
        return True

    text = force_sub_text(
        len(joined),
        total,
    )

    markup = build_force_sub_keyboard(
        missing
    )

    # CallbackQuery
    if hasattr(
        message_or_query,
        "message",
    ):
        query = message_or_query

        await query.answer()

        try:
            await query.message.edit_text(
                text,
                reply_markup=markup,
            )
        except Exception:
            try:
                await query.message.edit_caption(
                    caption=text,
                    reply_markup=markup,
                )
            except Exception:
                await query.message.reply_text(
                    text,
                    reply_markup=markup,
                )

    # Message
    else:
        await message_or_query.reply_text(
            text,
            reply_markup=markup,
        )

    return False


# ============================================================
# /START
# ============================================================

@Client.on_message(
    filters.private
    & filters.command("start"),
    group=-100,
)
async def start(client: Client, message):
    user_id = message.from_user.id

    # --------------------------------------------------------
    # FORCE SUB
    # --------------------------------------------------------

    joined, missing = (
        await get_membership_status(
            client,
            user_id,
        )
    )

    if missing:
        text = force_sub_text(
            len(joined),
            len(joined) + len(missing),
        )

        markup = build_force_sub_keyboard(
            missing
        )

        await message.reply_text(
            text,
            reply_markup=markup,
        )

        return

    # --------------------------------------------------------
    # NORMAL START
    #
    # Keep your existing normal AniToon
    # start/menu code below this point.
    # --------------------------------------------------------

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🛠 Help & Usage",
                    callback_data="help",
                ),
                InlineKeyboardButton(
                    "ℹ️ About",
                    callback_data="about",
                ),
            ],
            [
                InlineKeyboardButton(
                    "⚙️ Settings",
                    callback_data="settings",
                ),
            ],
            [
                InlineKeyboardButton(
                    "💎 Buy Premium",
                    callback_data="upgrade",
                ),
            ],
        ]
    )

    await message.reply_text(
        "👋 **Welcome to AniToon!**\n\n"
        "Send me a file to get started.",
        reply_markup=keyboard,
    )
