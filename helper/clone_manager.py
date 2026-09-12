import asyncio

from pyrogram import Client
from pyrogram.errors import RPCError

from config import Config
from helper.database import db


class CloneManager:
    def __init__(
        self,
        main_client,
    ):
        self.main_client = main_client
        self.clones = {}


    # ============================================================
    # START ONE CLONE
    # ============================================================

    async def start_clone(
        self,
        bot_token,
    ):
        try:
            client = Client(
                name=f"clone_{bot_token.split(':')[0]}",
                api_id=Config.API_ID,
                api_hash=Config.API_HASH,
                bot_token=bot_token,
                in_memory=True,
                plugins={
                    "root": "plugins"
                },
            )

            client.is_main_bot = False
            client.is_clone_bot = True

            await client.start()

            me = await client.get_me()

            self.clones[me.id] = client

            await db.set_clone_status(
                me.id,
                "online",
            )

            print(
                f"✅ Clone started: "
                f"@{me.username}"
            )

            return client

        except Exception as e:
            print(
                f"❌ Clone startup failed: {e}"
            )

            return None


    # ============================================================
    # START ALL SAVED CLONES
    # ============================================================

    async def start_all(self):
        async for clone in (
            await db.get_all_clones()
        ):
            token = clone.get(
                "bot_token"
            )

            if not token:
                continue

            await self.start_clone(
                token
            )


    # ============================================================
    # ADD NEW CLONE
    # ============================================================

    async def add_clone(
        self,
        owner_id,
        bot_token,
    ):
        client = await self.start_clone(
            bot_token
        )

        if not client:
            return None

        me = await client.get_me()

        await db.add_clone(
            owner_id=owner_id,
            bot_id=me.id,
            bot_username=me.username,
            bot_name=me.first_name,
            bot_token=bot_token,
        )

        return client


    # ============================================================
    # STOP ALL CLONES
    # ============================================================

    async def stop_all(self):
        for bot_id, client in list(
            self.clones.items()
        ):
            try:
                await client.stop()

                await db.set_clone_status(
                    bot_id,
                    "offline",
                )

            except Exception as e:
                print(
                    f"Clone stop error: {e}"
                )

        self.clones.clear()
