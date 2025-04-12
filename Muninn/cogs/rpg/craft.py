import sqlite3
import json
import math
import os

from icecream import ic

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button

class Tinker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.user_manager = self.bot.get_cog("StatsManager")
        self.data_manager = self.bot.get_cog("DataManager") 
        self.item_manager = self.bot.get_cog("ItemRandomizer") 

    @commands.hybrid_command(name="craft", description="Create a brand new thing from items you've gathered.")
    async def craft(self, interaction):
        
        async def craft_item(recipe, user_id):         
            ##Generate the item...
            generated_item = await self.item_manager.generate_item(recipe['type'], recipe['name'])
            
            ##First, remove the items to craft
            for item in recipe['recipe']:
                for _ in range(item['amount']):
                    item_data = await self.item_manager.generate_item("crafting", item['name'])
                    self.user_manager.remove_from_user_inventory(user_id, item_data)
                    
            ##Then add to inventory
            generated_item
            
            self.user_manager.add_to_user_inventory(user_id, generated_item)
            
            if generated_item.get('prefix'):
                prefix = f"*{generated_item.get('prefix')}* "
            else:
                prefix = ""
            
            embed = discord.Embed(title=f"Successfully crafted {recipe['name']}!",
                                  description=f"{prefix}{generated_item['name']}".strip(),
                                  color=0x7B12B4)
            
            return embed
            
        async def skill_unlocks(recipe, user_id):
            if not recipe.get('skill_level') or not recipe.get('required_skill'):
                return True
            
            skill = recipe['required_skill']
            user_proficiency = await self.user_manager.get_users_proficiency_by_id(user_id, skill)
            needed_proficiency = recipe['skill_level']
            
            if user_proficiency < needed_proficiency:
                return False
            else: return True
            
        async def build_recipe_embed(user_stats, recipe, recipes):     
            considered_items = []
            got_items_str = ""
            craftable = True

            for item in recipe['recipe']:
                item_data = await self.item_manager.generate_item("crafting", item['name'])
                inv_count = user_stats['inventory'].count(item_data)
                ic(item_data, user_stats['inventory'][0], inv_count)
                ic(item)
                got_items_str += f"**`{item['amount']}`** {item['name']} *(Have `{inv_count}`)*\n"
                if inv_count < item['amount']:
                    craftable = False
                    
            recipe_data = await self.data_manager.find_data(recipe['type'], recipe['name'])
                    
            recipe_embed = discord.Embed(title=f"Craft {recipe['name']}?", 
                                         description=recipe_data['description'],
                                         color=0x3617FE)
            recipe_embed.add_field(name="Required Items:", value=got_items_str)
            
            class CraftView(View):
                def __init__(self):
                    super().__init__()
                
                @discord.ui.button(label="Craft", style=discord.ButtonStyle.blurple)
                async def craft_button(self, interaction: discord.Interaction, button: Button):
                    embed = await craft_item(recipe, interaction.user.id)
                    await interaction.response.edit_message(embed=embed, view=None)
            
                @discord.ui.button(label=f"Cancel", style=discord.ButtonStyle.grey)
                async def cancel_button(self, interaction: discord.Interaction, button: Button):
                    embed, view = build_page_embed(user_stats, 1, recipes)
                    await interaction.response.edit_message(embed=embed, view=view)
            
            view = CraftView()
            
            if not craftable:
                view.craft_button.disabled = True
            
            return recipe_embed, view
            
        def build_page_embed(user_stats, page, recipes):
            page_beginning_index = (5 * (page-1))
            total_pages = math.ceil(len(recipes)/5)
            eval_item_index = page_beginning_index
            description = ""
            
            for i in range(5):
                if ((i+1)*page) > (len(recipes)):
                    continue
                
                recipe = recipes[eval_item_index]
                description += f"{eval_item_index}. {recipe['name']}\n"
                 
                eval_item_index += 1

            embed = discord.Embed(title=f"{user_stats['profile_name']}'s Tinker Book - Page {page}", description=description, color=0x1777FE)
            
            class MarketView(View):
                def __init__(self):
                    super().__init__()
                    self.page = page
                
                @discord.ui.button(label=f"{((page-1)*5)+1}", style=discord.ButtonStyle.grey)
                async def first_button(self, interaction: discord.Interaction, button: Button):
                    embed, view = await build_recipe_embed(user_stats, recipes[((self.page-1)*5)+0], recipes)
                    await interaction.response.edit_message(embed=embed, view=view)
            
                @discord.ui.button(label=f"{((page-1)*5)+2}", style=discord.ButtonStyle.grey)
                async def second_button(self, interaction: discord.Interaction, button: Button):
                    embed, view = await build_recipe_embed(user_stats, recipes[((self.page-1)*5)+1], recipes)
                    await interaction.response.edit_message(embed=embed, view=view)
            
                @discord.ui.button(label=f"{((page-1)*5)+3}", style=discord.ButtonStyle.grey)
                async def third_button(self, interaction: discord.Interaction, button: Button):
                    embed, view = await build_recipe_embed(user_stats, recipes[((self.page-1)*5)+2], recipes)
                    await interaction.response.edit_message(embed=embed, view=view)
            
                @discord.ui.button(label=f"{((page-1)*5)+4}", style=discord.ButtonStyle.grey)
                async def fourth_button(self, interaction: discord.Interaction, button: Button):
                    embed, view = await build_recipe_embed(user_stats, recipes[((self.page-1)*5)+3], recipes)
                    await interaction.response.edit_message(embed=embed, view=view)
            
                @discord.ui.button(label=f"{((page-1)*5)+5}", style=discord.ButtonStyle.grey)
                async def fifth_button(self, interaction: discord.Interaction, button: Button):
                    embed, view = await build_recipe_embed(user_stats, recipes[((self.page-1)*5)+4], recipes)
                    await interaction.response.edit_message(embed=embed, view=view)
            
                @discord.ui.button(label=f"Previous", style=discord.ButtonStyle.grey)
                async def prev_button(self, interaction: discord.Interaction, button: Button):
                    embed, view = self.build_page_embed(user_stats, page-1, recipes)
                    await interaction.response.edit_message(embed=embed, view=view)
            
                @discord.ui.button(label=f"Next", style=discord.ButtonStyle.grey)
                async def next_button(self, interaction: discord.Interaction, button: Button):
                    embed, view = self.build_page_embed(user_stats, page+1, recipes)
                    await interaction.response.edit_message(embed=embed, view=view)
            
            view = MarketView()
            
            if page == 1:
                view.prev_button.disabled = True
            if page == total_pages:
                view.next_button.disabled = True
        
            return embed, view
        
        datapath = './data/recipes'
        unifieddata = []
        
        for dirpath, _, filenames in os.walk(datapath):
            for file in filenames:
                if file.endswith(".json"):
                    file_path = os.path.join(dirpath, file)
                    with open(file_path, 'r') as f:
                        try:
                            data = json.load(f)
                            if await skill_unlocks(data, interaction.author.id):
                                unifieddata.append(data)
                                print("Added recipe!")
                            else:     
                                print("User has not unlocked recipe!")                                
                        except json.JSONDecodeError as e:
                            print(f"Skipping invalid JSON: {file_path}, {e}")
                            
        ic(unifieddata)
        user_stats = await self.user_manager.fetch_user_stats(interaction.author)
        embed, view = build_page_embed(user_stats, 1, unifieddata)
        await interaction.send(embed=embed, view=view)        
        
        
        ## Load all data, place into "subfolder" structure;
        ## Check user's proficiency level in the certain area if required\
        
                
        ## Display 
        

async def setup(bot):
    await bot.add_cog(Tinker(bot))
