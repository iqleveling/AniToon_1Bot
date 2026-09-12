import logging
import asyncio

from pyrogram import Client
from pyrogram.errors import FloodWait

from config import Config


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


class Bot(Client):
    def __init__(self):
        super().__init__(
            name="AniToon_1Bot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            workers=100,
            plugins={
                "root": "plugins"
            },
        )

    async def start(self):
        while True:
            try:
                await super().start()

                me = await self.get_me()

                print(
                    f"✅ {me.first_name} "
                    "[Promax Edition] Started Successfully!"
                )

                # -----------------------------------------
                # PREMIUM USER SESSION
                # -----------------------------------------

                if Config.STRING_SESSION:
                    print(
                        "💎 Initializing Premium Client..."
                    )

                    self.USER = Client(
                        name="Premium_User",
                        session_string=Config.STRING_SESSION,
                        api_id=Config.API_ID,
                        api_hash=Config.API_HASH,
                    )

                    await self.USER.start()

                    print(
                        "✅ Premium Session Active!"
                    )

                return

            except FloodWait as e:
                wait_time = int(e.value)

                print(
                    "⏳ Telegram FloodWait detected."
                )
                print(
                    f"Waiting {wait_time} seconds "
                    "before trying again..."
                )

                await asyncio.sleep(
                    wait_time
                )

            except Exception:
                logging.exception(
                    "Bot startup failed."
                )
                raise

    async def stop(self, *args):
        try:
            if hasattr(self, "USER"):
                await self.USER.stop()
        except Exception:
            logging.exception(
                "Premium session stop error."
            )

        await super().stop()

        print(
            "❌ Bot Stopped."
        )


if __name__ == "__main__":
    Bot().run()
