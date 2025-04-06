import sqlite3
import discord
from discord.ext import commands
from discord.ui import View, Button


class ModTools(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.search = bot.get_cog('Search')
        self.data_manager = self.bot.get_cog("DataManager") # For Item and Expedition Info
        self.item_randomizer = self.bot.get_cog("ItemRandomizer") # For Item and Expedition Info
        self.user_manager = self.bot.get_cog("StatsManager") # For Item and Expedition Info

    @commands.command()
    async def give_item(self, ctx, type: str, item: str, user: str = None):
        if user is None:
            user = ctx.author
        else:
            user = await self.search.find_user(user, ctx.guild)
            if not user:
                await ctx.send("No profile found.")
                return
            
        item = await self.item_randomizer.generate_item(ctx, type, item)

        self.user_manager.add_to_user_inventory(user.id, item)

        await ctx.send(f"Added {item['name']} to inventory.")
    
    @commands.command()
    async def find_data(self, ctx, type: str, item: str):
        item = await self.data_manager.find_data(type, item)
        await ctx.send(item)
    
    @commands.command()
    async def gen_item(self, ctx, type: str, item: str):
        item = await self.item_randomizer.generate_item(type, item)
        await ctx.send(item)

    @commands.command()
    async def gen_items_HC(self, ctx):
        hardcoded_list = [
            {
                "name": "katana",
                "weight": 10
            },
            {
                "name": "steel boots",
                "weight": 1
            },
            {
                "name": "steel sword",
                "weight": 1
            },
        ]

        item = await self.item_randomizer.weighted_random_items(ctx, 'equipment', hardcoded_list)
        await ctx.send(item)

async def setup(bot):
    await bot.add_cog(ModTools(bot))
