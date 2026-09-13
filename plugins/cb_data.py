from pyrogram import Client, filters


@Client.on_callback_query(
    filters.regex("^check_force_sub$")
)
async def cb_check_force_sub(
    client,
    callback_query,
):
    from plugins.start import (
        get_membership_status,
        force_sub_text,
        build_force_sub_keyboard,
    )

    user_id = callback_query.from_user.id

    joined, missing = (
        await get_membership_status(
            client,
            user_id,
        )
    )

    # --------------------------------------------------------
    # ALL FOUR JOINED
    # --------------------------------------------------------

    if not missing:
        await callback_query.answer(
            "✅ All 4 channels joined!",
            show_alert=True,
        )

        # Show your normal home menu.
        try:
            await callback_query.message.edit_text(
                "👋 **Welcome to AniToon!**\n\n"
                "You have successfully joined all "
                "required channels.\n\n"
                "Send me a file to get started.",
            )
        except Exception:
            try:
                await callback_query.message.edit_caption(
                    caption=(
                        "👋 **Welcome to AniToon!**\n\n"
                        "You have successfully joined all "
                        "required channels.\n\n"
                        "Send me a file to get started."
                    )
                )
            except Exception:
                await callback_query.message.reply_text(
                    "👋 **Welcome to AniToon!**\n\n"
                    "You have successfully joined all "
                    "required channels.\n\n"
                    "Send me a file to get started."
                )

        return

    # --------------------------------------------------------
    # STILL MISSING CHANNELS
    # --------------------------------------------------------

    await callback_query.answer(
        f"Joined {len(joined)}/4",
        show_alert=True,
    )

    text = force_sub_text(
        len(joined),
        len(joined) + len(missing),
    )

    markup = build_force_sub_keyboard(
        missing
    )

    try:
        await callback_query.message.edit_text(
            text,
            reply_markup=markup,
        )
    except Exception:
        try:
            await callback_query.message.edit_caption(
                caption=text,
                reply_markup=markup,
            )
        except Exception:
            await callback_query.message.reply_text(
                text,
                reply_markup=markup,
            )
