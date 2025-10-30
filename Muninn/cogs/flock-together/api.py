import discord  # type:ignore
import discord.ext.commands as commands  # type:ignore
import sqlite3

class API(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.get_cog("Database")

## USER
    async def get_user(self, user_id: int):
        await self.db.get("User", user_id)

    async def get_users(self):
        await self.db.get("User")

    async def post_user(self, user_data: dict):
        await self.db.post("User", user_data)
        
    async def delete_user(self, user_id: int):
        await self.db.delete("User", "id = ?", user_id)
    
    async def patch_user(self, user_id: int, user_data: dict):
        await self.db.patch("User", user_data, user_id)
        
## BIRD
    async def get_bird(self, bird_id: int):
        await self.db.get("Bird", bird_id)

    async def post_bird(self, bird_data: dict):
        await self.db.post("Bird", bird_data)

    async def delete_bird(self, bird_id: int):
        await self.db.delete("Bird", bird_id)

    async def patch_bird(self, bird_id: int, bird_data: dict):
        await self.db.patch("Bird", bird_data, bird_id)

async def setup(bot):
    api = API(bot)
    await bot.add_cog(api)