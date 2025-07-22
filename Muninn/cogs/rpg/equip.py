import sqlite3
import json
import math
import os

from icecream import ic

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button

class Equip(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.user_manager = self.bot.get_cog("StatsManager")
        self.data_manager = self.bot.get_cog("DataManager") 
        self.item_manager = self.bot.get_cog("ItemRandomizer") 

    @commands.hybrid_command(name="equip", description="Equip a weapon or armor piece to your character.")
    async def equip(self, interaction):
        
        async def equip(interaction, user_stats, item_slot, item):
            await self.user_manager.equip_from_inventory(interaction, interaction.user.id, user_stats, item_slot, item)
            
            success_embed = discord.Embed(title=f"{user_stats['profile_name']} placed the equipment at his {item_slot}!",
                                          color=discord.Color.green()) 
            
            return success_embed
        
        async def equip_item_handy(user_stats, item, items):
            if item['slot'] != 'hand':
                embed = await equip(interaction, user_stats, item['slot'], item)
                return embed, None
            else:
                embed = discord.Embed(title=f"Which hand will {user_stats['profile_name']} use to hold the item?", color=0xFE1755)
                
                class Handiness(View):
                    def __init__(self):
                        super().__init__()
                    
                    @discord.ui.button(label="Left Hand", style=discord.ButtonStyle.green)
                    async def left(self, interaction: discord.Interaction, button: Button):
                        embed = await equip(interaction, user_stats, 'hand_left', item)
                        await interaction.response.edit_message(embed=embed, view=None)
                        
                    @discord.ui.button(label="Right Hand", style=discord.ButtonStyle.green)
                    async def right(self, interaction: discord.Interaction, button: Button):
                        embed = await equip(interaction, user_stats, 'hand_right', item)
                        await interaction.response.edit_message(embed=embed, view=None)
                        
                    @discord.ui.button(label="Return", style=discord.ButtonStyle.red)
                    async def back(self, interaction: discord.Interaction, button: Button):
                        embed, view = await build_page_embed(user_stats, 1, items)
                        await interaction.response.edit_message(embed=embed, view=view)
                        
                view = Handiness()
                
                return embed, view
                
                
        async def build_page_embed(user_stats, page, items):
            page_beginning_index = (5 * (page-1))
            total_pages = math.ceil(len(items)/5)
            eval_item_index = page_beginning_index
            description = ""
            page_item_count = 1
            
            for i in range(5):
                if ((i+1)*page) > (len(items)):
                    continue
                item = items[eval_item_index]
                
                item_data = await self.data_manager.find_data(item['type'], item['name'])
                prefix = item.get('prefix', '')  # Get the prefix if available
                ic(description, item['description'])
                description += (f"**{(i+1)*page}. *{prefix}* {item['name']}** - {item['description']}\n")
                
                eval_item_index += 1
                page_item_count += 1
                
            ic(page_item_count)

            embed = discord.Embed(title=f"{user_stats['profile_name']}'s Equippable Items - Page {page}", description=description, color=0xFE1736)
            
            class MarketView(View):
                def __init__(self):
                    super().__init__()
                    self.page = page
                
                @discord.ui.button(label=f"{((page-1)*5)+1}", style=discord.ButtonStyle.blurple)
                async def first_button(self, interaction: discord.Interaction, button: Button):
                    embed, view = await equip_item_handy(user_stats, items[((self.page-1)*5)+0], items)
                    await interaction.response.edit_message(embed=embed, view=view)
            
                @discord.ui.button(label=f"{((page-1)*5)+2}", style=discord.ButtonStyle.blurple)
                async def second_button(self, interaction: discord.Interaction, button: Button):
                    embed, view = await equip_item_handy(user_stats, items[((self.page-1)*5)+1], items)
                    await interaction.response.edit_message(embed=embed, view=view)
            
                @discord.ui.button(label=f"{((page-1)*5)+3}", style=discord.ButtonStyle.blurple)
                async def third_button(self, interaction: discord.Interaction, button: Button):
                    embed, view = await equip_item_handy(user_stats, items[((self.page-1)*5)+2], items)
                    await interaction.response.edit_message(embed=embed, view=view)
            
                @discord.ui.button(label=f"{((page-1)*5)+4}", style=discord.ButtonStyle.blurple)
                async def fourth_button(self, interaction: discord.Interaction, button: Button):
                    embed, view = await equip_item_handy(user_stats, items[((self.page-1)*5)+3], items)
                    await interaction.response.edit_message(embed=embed, view=view)
            
                @discord.ui.button(label=f"{((page-1)*5)+5}", style=discord.ButtonStyle.blurple)
                async def fifth_button(self, interaction: discord.Interaction, button: Button):
                    embed, view = await equip_item_handy(user_stats, items[((self.page-1)*5)+4], items)
                    await interaction.response.edit_message(embed=embed, view=view)
            
                @discord.ui.button(label=f"Previous", style=discord.ButtonStyle.grey)
                async def prev_button(self, interaction: discord.Interaction, button: Button):
                    embed, view = await self.build_page_embed(user_stats, page-1, items)
                    await interaction.response.edit_message(embed=embed, view=view)
            
                @discord.ui.button(label=f"Next", style=discord.ButtonStyle.grey)
                async def next_button(self, interaction: discord.Interaction, button: Button):
                    embed, view = await self.build_page_embed(user_stats, page+1, items)
                    await interaction.response.edit_message(embed=embed, view=view)
                    
            view = MarketView()
            
            buttons = [
                view.first_button,
                view.second_button,
                view.third_button,
                view.fourth_button,
                view.fifth_button
            ]

            # Disable the last `i` buttons
            for btn in buttons[-(page_item_count):]:
                btn.disabled = True
            
            if page == 1:
                view.prev_button.disabled = True
            if page == total_pages:
                view.next_button.disabled = True
        
            return embed, view
        
        datapath = './data/recipes'
        
        user_stats = await self.user_manager.fetch_user_stats(interaction.author)
        sanitized = []
        for item in user_stats['inventory']:
            if item['type'] == 'equipment':
                sanitized.append(item)
                print('Added item to sanitized list') 
        embed, view = await build_page_embed(user_stats, 1, sanitized)
        await interaction.send(embed=embed, view=view)        
        
        
        ## Load all data, place into "subfolder" structure;
        ## Check user's proficiency level in the certain area if required\
        
                
        ## Display 
        

async def setup(bot):
    await bot.add_cog(Equip(bot))
