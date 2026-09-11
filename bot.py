from pyrogram import Client
from config import Config
import logging

# Set up logging to track internal errors and performance
logging.basicConfig(level=logging.ERROR)


class Bot(Client):
    def __init__(self):
        super().__init__(
            name="AniToon_1Bot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,

            # Promax: Increased workers for high-speed concurrent tasks
            workers=100,

            # Modular: Automatically loads every file in the /plugins folder
            plugins=dict(root="plugins")
        )

    async def start(self):
        await super().start()

        me = await self.get_me()
        print(f"✅ {me.first_name} [Promax Edition] Started Successfully!")

        # Choice 1-B: Initialize the Premium Client for 4GB Support
        if Config.STRING_SESSION:
            print("💎 Initializing Premium Client for 4GB Support...")

            self.USER = Client(
                name="Premium_User",
                session_string=Config.STRING_SESSION,
                api_id=Config.API_ID,
                api_hash=Config.API_HASH
            )

            await self.USER.start()
            print("✅ Premium Session Active!")

    async def stop(self, *args):
        await super().stop()

        # Ensure the Premium session also disconnects safely
        if hasattr(self, "USER"):
            await self.USER.stop()

        print("❌ Bot Stopped.")


if __name__ == "__main__":
    Bot().run()
