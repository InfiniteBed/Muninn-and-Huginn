import ast
import asyncio
import datetime
import json
import math
import random
import sqlite3

import discord
from discord import SelectOption
from discord.ext import commands
from discord.ui import Button, Select, View, TextInput, Modal

from icecream import ic

def get_default_values(ctx):
    
    conn = sqlite3.connect('discord.db')
    cursor = conn.cursor()

    cursor.execute("SELECT user, name, description, items FROM vendors WHERE user = ?", (ctx.author.id, ))
    x = cursor.fetchone()
    
    if not x:
        return "", ""
    
    name = x[1]
    description = x[2]

    return name, description

class StallNameModal(Modal):
    def __init__(self, ctx):
        super().__init__(title="Set Up Your Market Stall")

        # Create input fields first
        self.stall_name = StallName("What is your stall's name?", ctx)
        self.stall_desc = StallDesc("What will you be selling?", ctx)

        # Then add them to the modal
        self.add_item(self.stall_name)
        self.add_item(self.stall_desc)

    async def on_submit(self, interaction: discord.Interaction):
        name = self.stall_name.value
        desc = self.stall_desc.value
        
        conn = sqlite3.connect('discord.db')
        cursor = conn.cursor()
        cursor.execute("SELECT items FROM vendors WHERE user = ?", (interaction.user.id,))
        row = cursor.fetchone()
        items = row[0] if row else None  # Preserve current items, or None if new

        cursor.execute("INSERT OR REPLACE INTO vendors (user, name, description, items) VALUES (?, ?, ?, ?)", (interaction.user.id, name, desc, items))
        conn.commit()
        conn.close()
        
        await interaction.response.edit_message(embed=discord.Embed(title="Market Setup Completed!", 
                                                                    description="We hope you receive much business...", 
                                                                    color=discord.Color.dark_green()), 
                                                view=None)
        
class StallName(TextInput):
    def __init__(self, label, ctx):
        super().__init__(label=label, placeholder="Type here...", default=get_default_values(ctx)[0], required=True)
    
    async def callback(self, interaction: discord.Interaction):
        stall_name = self.value

class StallDesc(TextInput):
    def __init__(self, label, ctx):
        super().__init__(label=label, placeholder="Type here...", default=get_default_values(ctx)[1], required=True)
    
    async def callback(self, interaction: discord.Interaction):
        stall_description = self.value

class GoMarketSetup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "discord.db"
        self.item_generator = bot.get_cog('ItemFetch')
        self.user_manager = self.bot.get_cog("StatsManager")
        self.data_manager = self.bot.get_cog("DataManager")
        
    async def setup_market(self, ctx, interaction):
        modal = StallNameModal(ctx)
        await interaction.response.send_modal(modal)
        
        
        
    
async def setup(bot):
    await bot.add_cog(GoMarketSetup(bot))