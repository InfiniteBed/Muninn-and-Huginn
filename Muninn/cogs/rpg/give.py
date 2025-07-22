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

class Give(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.stats_manager = self.bot.get_cog("StatsManager")
        self.data_manager = self.bot.get_cog("DataManager")
        self.list_manager = self.bot.get_cog("ListManager")
        
    @commands.hybrid_command(name="give", description="Hand an item to another player")
    async def give(self, ctx, target: discord.User):
        
        def remove_from_user_inv(item_data):
            self.stats_manager.remove_from_user_inventory(ctx.author.id, item_data)
            
        def add_to_target_inv(item_data):
            self.stats_manager.add_to_user_inventory(target.id, item_data)
            
        async def choice_embed_view(target):
            user_stats = await self.stats_manager.fetch_user_stats(ctx.author)
            target_stats = await self.stats_manager.fetch_user_stats(target)
            
            embed = discord.Embed(title=f"What would you like to give to {target_stats['profile_name']}?",
                                  color=0x9e3e74)
            
            class VendorDropdown(Select):
                def __init__(self, options):
                    super().__init__(
                        placeholder="Select an item to put up for sale...",
                        options=options,
                        min_values=1,
                        max_values=1
                    )

                @classmethod
                async def create(cls):
                    options = []
                    
                    for index, item in enumerate(user_stats['inventory'][:25]):
                        item_data = await self.data_manager.find_data(item['type'], item['name'])
                        description = item_data.get('description')[:100] if item_data.get('description') else None
                        prefix = item.get('prefix', '')  # Get the prefix if available
                        heal_info = f" (heals {item.get('base_heal')} HP)" if item.get('base_heal') else ""
                        label = f"{prefix} {item['name']} {heal_info}".strip()
                        options.append(SelectOption(label=label, description=description, value=str(index)))

                    return cls(options)

                async def callback(self, interaction: discord.Interaction):
                    if interaction.user.id != ctx.author.id:
                        await interaction.response.send_message("Sorry, this menu isn't for you.", ephemeral=True)
                        return
                    
                    index = int(self.values[0])           
                    item_data = user_stats['inventory'][index]

                    embed = discord.Embed(title=f"{user_stats['profile_name']} gave the {item_data['name']} to {target_stats['profile_name']}!", 
                                        color=0xFF8250, 
                                        description="I'm sure he will appreciate it very much :)")
                    
                    add_to_target_inv(item_data)
                    
                    remove_from_user_inv(item_data)
                
                    await interaction.response.edit_message(embed=embed, view=None)

            class VendorDropdownView(View):
                def __init__(self, dropdown: VendorDropdown):
                    super().__init__(timeout=60)
                    self.add_item(dropdown)
                    
            dropdown = await VendorDropdown.create()

            view = VendorDropdownView(dropdown)

            return embed, view
        
        embed, view = await choice_embed_view(target)
        
        await ctx.send(embed=embed, view=view)    
    
async def setup(bot):
    await bot.add_cog(Give(bot))
