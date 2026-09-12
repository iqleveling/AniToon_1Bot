import motor.motor_asyncio

from datetime import datetime

from config import Config


class Database:
    def __init__(
        self,
        uri,
        database_name,
    ):
        self._client = (
            motor.motor_asyncio.AsyncIOMotorClient(
                uri
            )
        )

        self.db = self._client[
            database_name
        ]

        self.col = self.db.user

        self.clones = self.db.clones


    # ============================================================
    # USER
    # ============================================================

    def new_user(self, user_id):
        return {
            "id": int(user_id),
            "join_date": datetime.now(),
            "thumb": None,
            "caption": None,
            "daily_usage": 0,
            "last_used": (
                datetime.now()
                .date()
                .isoformat()
            ),
            "is_premium": False,
            "is_banned": False,
            "metadata_pref": "AniToon",
        }


    async def add_user(self, user_id):
        await self.col.update_one(
            {"id": int(user_id)},
            {
                "$setOnInsert": self.new_user(
                    user_id
                )
            },
            upsert=True,
        )


    async def is_user_exist(self, user_id):
        user = await self.col.find_one(
            {"id": int(user_id)}
        )

        return bool(user)


    async def get_user_data(self, user_id):
        return await self.col.find_one(
            {"id": int(user_id)}
        )


    # ============================================================
    # DAILY USAGE
    # ============================================================

    async def get_usage(self, user_id):
        user = await self.col.find_one(
            {"id": int(user_id)}
        )

        if not user:
            return 0

        today = (
            datetime.now()
            .date()
            .isoformat()
        )

        if user.get(
            "last_used"
        ) != today:
            await self.col.update_one(
                {"id": int(user_id)},
                {
                    "$set": {
                        "daily_usage": 0,
                        "last_used": today,
                    }
                },
            )

            return 0

        return user.get(
            "daily_usage",
            0,
        )


    async def update_usage(
        self,
        user_id,
        bytes_count,
    ):
        await self.col.update_one(
            {"id": int(user_id)},
            {
                "$inc": {
                    "daily_usage": int(
                        bytes_count
                    )
                },
                "$set": {
                    "last_used": (
                        datetime.now()
                        .date()
                        .isoformat()
                    )
                },
            },
        )


    # ============================================================
    # THUMBNAIL
    # ============================================================

    async def set_thumbnail(
        self,
        user_id,
        file_id,
    ):
        await self.col.update_one(
            {"id": int(user_id)},
            {
                "$set": {
                    "thumb": file_id
                }
            },
        )


    async def get_thumbnail(
        self,
        user_id,
    ):
        user = await self.col.find_one(
            {"id": int(user_id)}
        )

        return (
            user.get("thumb")
            if user
            else None
        )


    # ============================================================
    # CAPTION
    # ============================================================

    async def set_caption(
        self,
        user_id,
        caption,
    ):
        await self.col.update_one(
            {"id": int(user_id)},
            {
                "$set": {
                    "caption": caption
                }
            },
        )


    async def get_caption(
        self,
        user_id,
    ):
        user = await self.col.find_one(
            {"id": int(user_id)}
        )

        return (
            user.get("caption")
            if user
            else None
        )


    # ============================================================
    # BAN
    # ============================================================

    async def ban_user(
        self,
        user_id,
    ):
        await self.col.update_one(
            {"id": int(user_id)},
            {
                "$set": {
                    "is_banned": True
                }
            },
        )


    async def unban_user(
        self,
        user_id,
    ):
        await self.col.update_one(
            {"id": int(user_id)},
            {
                "$set": {
                    "is_banned": False
                }
            },
        )


    # ============================================================
    # PREMIUM
    # ============================================================

    async def set_premium(
        self,
        user_id,
        status,
    ):
        await self.col.update_one(
            {"id": int(user_id)},
            {
                "$set": {
                    "is_premium": bool(
                        status
                    )
                }
            },
        )


    # ============================================================
    # USERS
    # ============================================================

    async def get_all_users(self):
        return self.col.find({})


    async def total_users_count(self):
        return await self.col.count_documents({})


    # ============================================================
    # CLONES
    # ============================================================

    async def add_clone(
        self,
        owner_id,
        bot_id,
        bot_username,
        bot_name,
        bot_token,
    ):
        await self.clones.update_one(
            {
                "bot_id": int(bot_id)
            },
            {
                "$set": {
                    "owner_id": int(owner_id),
                    "bot_id": int(bot_id),
                    "bot_username": bot_username,
                    "bot_name": bot_name,
                    "bot_token": bot_token,
                    "status": "online",
                    "updated_at": datetime.now(),
                },
                "$setOnInsert": {
                    "created_at": datetime.now(),
                },
            },
            upsert=True,
        )


    async def get_clone(
        self,
        owner_id,
    ):
        return await self.clones.find_one(
            {
                "owner_id": int(owner_id)
            }
        )


    async def get_clone_by_bot_id(
        self,
        bot_id,
    ):
        return await self.clones.find_one(
            {
                "bot_id": int(bot_id)
            }
        )


    async def get_all_clones(self):
        return self.clones.find({})


    async def set_clone_status(
        self,
        bot_id,
        status,
    ):
        await self.clones.update_one(
            {
                "bot_id": int(bot_id)
            },
            {
                "$set": {
                    "status": status,
                    "updated_at": datetime.now(),
                }
            },
        )


    async def remove_clone(
        self,
        bot_id,
    ):
        await self.clones.delete_one(
            {
                "bot_id": int(bot_id)
            }
        )


# ============================================================
# DATABASE INSTANCE
# ============================================================

db = Database(
    Config.DATABASE_URL,
    "AniToon_Promax_DB",
)
