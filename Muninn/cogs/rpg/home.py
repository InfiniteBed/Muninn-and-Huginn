import sqlite3
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
import json
from icecream import ic
import os
import math


class Home(commands.Cog):
    def __init__(self, bot):
        self.user_manager = bot.get_cog("StatsManager")
        self.data_manager = bot.get_cog("DataManager")
        self.item_manager = bot.get_cog("ItemRandomizer")
        self.bot = bot

    @commands.hybrid_command(name="home", description="Rest and relax, or make some new items")
    async def home(self, interaction):
         
        user_stats = await self.user_manager.fetch_user_stats(interaction.author)
        
        """View your home and interact with it."""
        user = interaction.author
        
        user_stats = await self.user_manager.fetch_user_stats(user)

        home_embed = discord.Embed(
            title=f"{user.display_name}'s Home",
            description="Welcome to your home! Here you can check your crafting items and tinker to create new ones!",
            color=discord.Color.blue()
        )
        home_embed.set_thumbnail(url=user.avatar.url if user.avatar else None)
        
        # Inventory page embed
        user_inventory = user_stats['inventory']
        if not user_inventory:  # Handle empty or None inventory
            user_inventory = []
        elif isinstance(user_inventory, str):
            try:
                user_inventory = json.loads(user_inventory)  # Deserialize if it's a JSON string
            except json.JSONDecodeError:
                user_inventory = []  # Default to an empty list if JSON parsing fails
        elif not isinstance(user_inventory, list):
            user_inventory = []  # Default to an empty list if it's neither a string nor a list

        # Increment item counters for every item that is found
        parsed_inventory = {}
        for item in user_inventory:
            item_name = item['name']
            item_in_inventory = parsed_inventory.get(item_name)
            
            if not item_in_inventory:
                parsed_inventory[item_name] = 1
            else:
                parsed_inventory[item_name] += 1
                
        ic(parsed_inventory)
                
        async def get_crafting_items(user_stats,):
            # Inventory page embed
            user_inventory = user_stats['inventory']
            if not user_inventory:  # Handle empty or None inventory
                user_inventory = []
            elif isinstance(user_inventory, str):
                try:
                    user_inventory = json.loads(user_inventory)  # Deserialize if it's a JSON string
                except json.JSONDecodeError:
                    user_inventory = []  # Default to an empty list if JSON parsing fails
            elif not isinstance(user_inventory, list):
                user_inventory = []  # Default to an empty list if it's neither a string nor a list

            # Increment item counters for every item that is found
            parsed_inventory = {}
            for item in user_inventory:
                item_name = item['name']
                item_in_inventory = parsed_inventory.get(item_name)
                
                if not item_in_inventory:
                    parsed_inventory[item_name] = 1
                else:
                    parsed_inventory[item_name] += 1
            
            inventory_embed = discord.Embed(title=f"Crafting Item Chest", color=discord.Color.yellow(), description="")
            
            ic(parsed_inventory)
            
            if parsed_inventory != {}:
                for key, value in parsed_inventory.items():
                    inventory_embed.description += f"**`{value}`** {key}\n"
            else:
                inventory_embed.description = "Your crafting item chest is empty."
            return inventory_embed

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
            got_items_str = ""
            craftable = True

            for item in recipe['recipe']:
                item_data = await self.item_manager.generate_item("crafting", item['name'])
                inv_count = 0
                
                if len(user_stats['inventory']) > 0:
                    for inv_item in user_stats['inventory']:
                        if inv_item['name'] == item['name']:
                            inv_count += 1
                else:
                    inv_count = 0
               
                got_items_str += f"**`{item['amount']}`** {item['name']} *(Have `{inv_count}`)*\n"
                if inv_count < item['amount']:
                    craftable = False
                    
            recipe_data = await self.data_manager.find_data(recipe['type'], recipe['name'])
                    
            recipe_embed = discord.Embed(title=f"Craft {recipe['name']}?", 
                                         description=recipe_data.get('description'),
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
        
        class ChestView(View):
            def __init__(self):
                super().__init__()
            
            @discord.ui.button(label=f"Return", style=discord.ButtonStyle.grey)
            async def return_button(self, interaction: discord.Interaction, button: Button):
                await interaction.response.edit_message(embed=home_embed, view=home_view)
            
        chest_view = ChestView()
            
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
            
            class CraftView(View):
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
            
                @discord.ui.button(label=f"Return", style=discord.ButtonStyle.red)
                async def return_button(self, interaction: discord.Interaction, button: Button):
                    await interaction.response.edit_message(embed=home_embed, view=home_view)
            
            view = CraftView()
            
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
        embed, crafting_view = build_page_embed(user_stats, 1, unifieddata)
        craft_embed = discord.Embed(title=embed.title,
                              color=embed.color,
                              description=("The leather-bound book contained well-worn pages, so used that tearing was threatened with every sheet of paper that was turned. The recipes carefully etched into the sheet were faded with time and use, but still as understandable.\n\n**To use the tinker book, simply select the number of the item desired. If the required materials are in the chest (which can found in !home), then the item will be crafted.**\n\nItems, such at armor and weapons,  can be used in battles to increase the chance of winning by adding to the base defense and attacks scores. Armor, weapons, as well as miscellaneous items can also be sold in the market.\n\n"+embed.description))
        
        
        class HomeView(View):
            def __init__(self, interaction, user_id, user_stats):
                super().__init__()
                self.user_id = user_id
                self.user_stats = user_stats
                self.interaction = interaction

            # @discord.ui.button(label="Rest", style=discord.ButtonStyle.green)
            # async def rest_button(self, interaction: discord.Interaction, button: Button):
            #     conn = sqlite3.connect('discord.db')
            #     c = conn.cursor()

            #     # Check if the user has any ongoing activity
            #     c.execute('SELECT activity FROM stats WHERE user_id = ?', (self.user_id,))
            #     activity = c.fetchone()

            #     if activity and activity[0]:
            #         await interaction.response.send_message("You cannot rest while engaged in another activity.", ephemeral=True)
            #     else:
            #         # Update the activity to "long rest"
            #         c.execute('UPDATE stats SET activity = ? WHERE user_id = ?', ("long rest", self.user_id))
            #         conn.commit()
            #         await interaction.response.send_message("You are now taking a long rest.", ephemeral=True)

            #     conn.close()
            
            @discord.ui.button(label="Crafting Items", style=discord.ButtonStyle.secondary, row=0)
            async def inventory_button(self, interaction: discord.Interaction, button: Button):
                self.current_menu = "Crafting Items"
                inventory_view = await get_crafting_items(user_stats)
                await interaction.response.edit_message(embed=inventory_view, view=chest_view)
                
            @discord.ui.button(label="Tinker Book", style=discord.ButtonStyle.secondary, row=0)
            async def crafting_book(self, interaction: discord.Interaction, button: Button):
                self.current_menu = "Crafting Items"
                await interaction.response.edit_message(embed=craft_embed, view=crafting_view)

        home_view = HomeView(interaction, user.id, user_stats)

        await interaction.send(embed=home_embed, view=home_view)
        
async def setup(bot):
    await bot.add_cog(Home(bot))
