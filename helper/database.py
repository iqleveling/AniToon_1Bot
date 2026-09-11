import motor.motor_asyncio
from datetime import datetime
from config import Config


class Database:
    def __init__(self, uri, database_name):
        # Initialize the asynchronous MongoDB client
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)

        self.db = self._client[database_name]

        # Main users collection
        self.col = self.db.user

        # Clone bot collection
        self.clones = self.db.clones

    def new_user(self, id):
        """
        Defines the default schema for a new user.
        """
        return {
            "id": int(id),
            "join_date": datetime.now(),
            "thumb": None,
            "caption": None,
            "daily_usage": 0,
            "last_used": datetime.now().date().isoformat(),
            "is_premium": False,
            "is_banned": False,
            "metadata_pref": "AniToon",
        }

    # --- USER CORE LOGIC ---

    async def add_user(self, id):
        user = self.new_user(id)
        await self.col.insert_one(user)

    async def is_user_exist(self, id):
        user = await self.col.find_one({"id": int(id)})
        return bool(user)

    async def get_user_data(self, id):
        return await self.col.find_one({"id": int(id)})

    # --- DAILY QUOTA ---

    async def get_usage(self, id):
        user = await self.col.find_one({"id": int(id)})

        if not user:
            return 0

        today = datetime.now().date().isoformat()

        # Reset usage when a new day begins
        if user.get("last_used") != today:
            await self.col.update_one(
                {"id": int(id)},
                {
                    "$set": {
                        "daily_usage": 0,
                        "last_used": today,
                    }
                },
            )
            return 0

        return user.get("daily_usage", 0)

    async def update_usage(self, id, bytes_count):
        """
        Adds processed file size to the user's daily usage.
        """
        await self.col.update_one(
            {"id": int(id)},
            {
                "$inc": {
                    "daily_usage": int(bytes_count)
                },
                "$set": {
                    "last_used": datetime.now().date().isoformat()
                },
            },
        )

    # --- THUMBNAIL ---

    async def set_thumbnail(self, id, file_id):
        await self.col.update_one(
            {"id": int(id)},
            {
                "$set": {
                    "thumb": file_id
                }
            },
        )

    async def get_thumbnail(self, id):
        user = await self.col.find_one({"id": int(id)})
        return user.get("thumb") if user else None

    # --- CAPTION ---

    async def set_caption(self, id, caption):
        await self.col.update_one(
            {"id": int(id)},
            {
                "$set": {
                    "caption": caption
                }
            },
        )

    async def get_caption(self, id):
        user = await self.col.find_one({"id": int(id)})
        return user.get("caption") if user else None

    # --- BAN / PREMIUM ---

    async def ban_user(self, id):
        await self.col.update_one(
            {"id": int(id)},
            {
                "$set": {
                    "is_banned": True
                }
            },
        )

    async def unban_user(self, id):
        await self.col.update_one(
            {"id": int(id)},
            {
                "$set": {
                    "is_banned": False
                }
            },
        )

    async def set_premium(self, id, status: bool):
        await self.col.update_one(
            {"id": int(id)},
            {
                "$set": {
                    "is_premium": bool(status)
                }
            },
        )

    # --- USER LIST / COUNT ---

    async def get_all_users(self):
        return self.col.find({})

    async def total_users_count(self):
        return await self.col.count_documents({})

    # --- CLONE ENGINE ---

    async def add_clone(self, user_id, bot_token):
        await self.clones.update_one(
            {"user_id": int(user_id)},
            {
                "$set": {
                    "token": bot_token
                }
            },
            upsert=True,
        )

    async def get_clone(self, user_id):
        return await self.clones.find_one(
            {"user_id": int(user_id)}
        )

    async def remove_clone(self, user_id):
        await self.clones.delete_one(
            {"user_id": int(user_id)}
        )


# Initialize the database
db = Database(
    Config.DATABASE_URL,
    "AniToon_Promax_DB"
)
