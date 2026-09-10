import motor.motor_asyncio
from config import Config


class Database:
    def __init__(self, uri, database_name):
        # Establish connection to the MongoDB cluster
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.col = self.db.user

    def new_user(self, id):
        # Create a basic structure for a new user
        return dict(
            id=id,
            thumb=None,
            caption=None
        )

    async def add_user(self, id):
        # Add user to database if they don't already exist
        user = self.new_user(id)
        await self.col.insert_one(user)

    async def is_user_exist(self, id):
        # Check if a user is already registered in our DB
        user = await self.col.find_one({'id': int(id)})
        return True if user else False

    async def set_thumbnail(self, id, file_id):
        # Save the File ID of an image to use as a permanent thumbnail
        await self.col.update_one(
            {'id': int(id)},
            {'$set': {'thumb': file_id}}
        )

    async def get_thumbnail(self, id):
        # Retrieve the saved thumbnail for a user
        user = await self.col.find_one({'id': int(id)})
        return user.get('thumb', None)


# Initialize the database object using variables from config.py
db = Database(Config.DATABASE_URL, "AniToon_1Bot")
