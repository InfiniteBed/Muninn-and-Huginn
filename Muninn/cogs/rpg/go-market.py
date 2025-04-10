import sqlite3
import json
import datetime
import discord
from discord.ext import commands
import asyncio
import math
import ast
from icecream import ic
from discord.ui import View, Button
import random

class GoMarket(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "discord.db"
        self.item_generator = bot.get_cog('ItemFetch')
        self.user_manager = self.bot.get_cog("StatsManager")
        self.data_manager = self.bot.get_cog("DataManager")
    
        """Create the table in the SQLite database if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''CREATE TABLE IF NOT EXISTS vendors (
                            user NUMERIC PRIMARY KEY,
                            items TEXT
                            )'''        
                        )

        cursor.execute('''CREATE TABLE IF NOT EXISTS inventory (
                            user_id INTEGER PRIMARY KEY,
                            inventory TEXT)''')

        conn.commit()
        conn.close()
        
    async def market_overview_embed(self, ctx):
        user_stats = await self.user_manager.fetch_user_stats(ctx.author)
        
        embed = discord.Embed(title="Eustrox Market", description="shush")
        
        return embed
    
    class ShopOverView(View):
        def __init__(self):
            super().__init__()

        @discord.ui.button(label="Browse Market", style=discord.ButtonStyle.grey)
        async def browse_button(self, interaction: discord.Interaction, button: Button):
            pass
            
        @discord.ui.button(label="Set up Shop Market", style=discord.ButtonStyle.grey)
        async def setup_button(self, interaction: discord.Interaction, button: Button):
            pass
            

    
async def setup(bot):
    await bot.add_cog(GoMarket(bot))