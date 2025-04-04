import sqlite3
import discord
from discord.ext import commands
from discord.ui import View, Button


class ModTools(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.search = bot.get_cog('Search')
        self.list_manager = self.bot.get_cog("ListManager") # For Item and Expedition Info

    @commands.command()
    async def give_item(self, ctx, type: str, item: str, user: str):
        if user is None:
            user = ctx.author
        else:
            user = await self.search.find_user(user, ctx.guild)
            if not user:
                await ctx.send("No profile found.")
                return
            
        item = await self.list_manager.find_item(type, item)

        # Query StatsManager to add the item to the inventory
    
    @commands.command()
    async def find_data(self, ctx, type: str, item: str):
        item = await self.list_manager.find_data(type, item)
        await ctx.send(item)

async def setup(bot):
    await bot.add_cog(ModTools(bot))
