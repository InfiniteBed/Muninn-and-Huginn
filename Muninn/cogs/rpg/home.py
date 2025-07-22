import sqlite3
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
import json
from icecream import ic
import os
import math
import yaml


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

        async def craft_item(recipe, user_id, ctx):         
            ##Generate the item...
            generated_item = await self.item_manager.generate_item(recipe['type'], recipe['name'])
            
            ## First, remove the items to craft
            for item in recipe['recipe']:
                amount_to_remove = item['amount']
                item_name = item['name']
                removed = 0

                for index in range(len(user_stats['inventory'])):
                    inv_item = user_stats['inventory'][index]
                    if inv_item['name'] == item_name:
                        item_data = self.user_manager.get_item_in_inventory(interaction.author.id, index)
                        ic(item_data)
                        self.user_manager.remove_from_user_inventory(user_id, item_data)
                        removed += 1
                        if removed >= amount_to_remove:
                            break

            ##Then add to inventory
            generated_item
            
            self.user_manager.add_to_user_inventory(user_id, generated_item)
            
            ##Give Experience if Applicable
            proficiency = recipe.get('skill')
            if proficiency:
                await self.user_manager.proficency_increase(interaction.author, proficiency, 1, ctx)
            
            if generated_item.get('prefix'):
                prefix = f"*{generated_item.get('prefix')}* "
            else:
                prefix = ""
            
            embed = discord.Embed(title=f"Successfully crafted {recipe['name']}!",
                                  description=f"{prefix}{generated_item['name']} crafted.".strip(),
                                  color=0x7B12B4)
            if proficiency:
                embed.description += f"\n\nIncreased `{proficiency}` proficiency by `1`!"
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
            
        async def build_recipe_embed(user_stats, recipe, recipes, ctx):
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
                    embed = await craft_item(recipe, interaction.user.id, ctx)
                    await interaction.response.edit_message(embed=embed, view=None)
            
                @discord.ui.button(label=f"Cancel", style=discord.ButtonStyle.grey)
                async def cancel_button(self, interaction: discord.Interaction, button: Button):
                    embed, view = build_page_embed(user_stats, 1, recipes, ctx)
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
            
        def build_page_embed(user_stats, page, recipes, ctx):
            if not recipes:  # Handle empty recipe list
                embed = discord.Embed(
                    title=f"{user_stats['profile_name']}'s Tinker Book",
                    description="No recipes available.",
                    color=0x1777FE
                )
                view = ChestView()  # Use the basic view with just return button
                return embed, view

            total_pages = math.ceil(len(recipes)/10)
            page = max(1, min(page, total_pages))  # Ensure page is within bounds
            
            # Calculate start index for current page
            start_index = (page - 1) * 10
            description = ""
            
            # Display recipes for current page
            for i in range(10):
                recipe_index = start_index + i
                if recipe_index >= len(recipes):
                    break
                    
                recipe = recipes[recipe_index]
                locked = recipe.get('locked')
                
                                
                if locked:
                    description += f"~~{recipe_index+1}. {recipe['name']}:~~ `Requires {recipe['required_skill'].title()} {recipe['skill_level']}`\n"
                elif not locked:
                    description += f"{recipe_index+1}. {recipe['name']}\n"

            embed = discord.Embed(title=f"{user_stats['profile_name']}'s Tinker Book - Page {page}/{total_pages}", description=description, color=0x1777FE)
            embed.set_footer(text=f"Items {start_index+1}-{min(len(recipes), start_index+10)} of {len(recipes)}")
            
            class CraftView(View):
                def __init__(self):
                    super().__init__()
                    self.page = page
                
                @discord.ui.button(label=f"{start_index+1}", style=discord.ButtonStyle.grey)
                async def first_button(self, interaction: discord.Interaction, button: Button):
                    if start_index < len(recipes):
                        embed, view = await build_recipe_embed(user_stats, recipes[start_index], recipes, ctx)
                        await interaction.response.edit_message(embed=embed, view=view)
            
                @discord.ui.button(label=f"{start_index+2}", style=discord.ButtonStyle.grey)
                async def second_button(self, interaction: discord.Interaction, button: Button):
                    if start_index + 1 < len(recipes):
                        embed, view = await build_recipe_embed(user_stats, recipes[start_index+1], recipes, ctx)
                        await interaction.response.edit_message(embed=embed, view=view)
            
                @discord.ui.button(label=f"{start_index+3}", style=discord.ButtonStyle.grey)
                async def third_button(self, interaction: discord.Interaction, button: Button):
                    if start_index + 2 < len(recipes):
                        embed, view = await build_recipe_embed(user_stats, recipes[start_index+2], recipes, ctx)
                        await interaction.response.edit_message(embed=embed, view=view)
            
                @discord.ui.button(label=f"{start_index+4}", style=discord.ButtonStyle.grey)
                async def fourth_button(self, interaction: discord.Interaction, button: Button):
                    if start_index + 3 < len(recipes):
                        embed, view = await build_recipe_embed(user_stats, recipes[start_index+3], recipes, ctx)
                        await interaction.response.edit_message(embed=embed, view=view)
            
                @discord.ui.button(label=f"{start_index+5}", style=discord.ButtonStyle.grey)
                async def fifth_button(self, interaction: discord.Interaction, button: Button):
                    if start_index + 4 < len(recipes):
                        embed, view = await build_recipe_embed(user_stats, recipes[start_index+4], recipes, ctx)
                        await interaction.response.edit_message(embed=embed, view=view)
            
                @discord.ui.button(label=f"{start_index+6}", style=discord.ButtonStyle.grey)
                async def sixth_button(self, interaction: discord.Interaction, button: Button):
                    if start_index + 4 < len(recipes):
                        embed, view = await build_recipe_embed(user_stats, recipes[start_index+4], recipes, ctx)
                        await interaction.response.edit_message(embed=embed, view=view)
            
                @discord.ui.button(label=f"{start_index+7}", style=discord.ButtonStyle.grey)
                async def seventh_button(self, interaction: discord.Interaction, button: Button):
                    if start_index + 4 < len(recipes):
                        embed, view = await build_recipe_embed(user_stats, recipes[start_index+4], recipes, ctx)
                        await interaction.response.edit_message(embed=embed, view=view)
            
                @discord.ui.button(label=f"{start_index+8}", style=discord.ButtonStyle.grey)
                async def eighth_button(self, interaction: discord.Interaction, button: Button):
                    if start_index + 4 < len(recipes):
                        embed, view = await build_recipe_embed(user_stats, recipes[start_index+4], recipes, ctx)
                        await interaction.response.edit_message(embed=embed, view=view)
            
                @discord.ui.button(label=f"{start_index+9}", style=discord.ButtonStyle.grey)
                async def ninth_button(self, interaction: discord.Interaction, button: Button):
                    if start_index + 4 < len(recipes):
                        embed, view = await build_recipe_embed(user_stats, recipes[start_index+4], recipes, ctx)
                        await interaction.response.edit_message(embed=embed, view=view)
            
                @discord.ui.button(label=f"{start_index+10}", style=discord.ButtonStyle.grey)
                async def tenth_button(self, interaction: discord.Interaction, button: Button):
                    if start_index + 4 < len(recipes):
                        embed, view = await build_recipe_embed(user_stats, recipes[start_index+4], recipes, ctx)
                        await interaction.response.edit_message(embed=embed, view=view)
            
                @discord.ui.button(label=f"Previous", style=discord.ButtonStyle.grey)
                async def prev_button(self, interaction: discord.Interaction, button: Button):
                    embed, view = build_page_embed(user_stats, page-1, recipes, ctx)
                    await interaction.response.edit_message(embed=embed, view=view)
            
                @discord.ui.button(label=f"Next", style=discord.ButtonStyle.grey)
                async def next_button(self, interaction: discord.Interaction, button: Button):
                    embed, view = build_page_embed(user_stats, page+1, recipes, ctx)
                    await interaction.response.edit_message(embed=embed, view=view)
            
                @discord.ui.button(label=f"Return", style=discord.ButtonStyle.red)
                async def return_button(self, interaction: discord.Interaction, button: Button):
                    await interaction.response.edit_message(embed=home_embed, view=home_view)
            
            view = CraftView()
            
            # Enable/disable buttons based on available recipes
            buttons = [
                view.first_button,
                view.second_button,
                view.third_button,
                view.fourth_button,
                view.fifth_button,
                view.sixth_button,
                view.seventh_button,
                view.eighth_button,
                view.ninth_button,
                view.tenth_button,
            ]

            for i, button in enumerate(buttons):
                recipe_index = start_index + i
                if recipe_index < len(recipes):
                    button.disabled = recipes[recipe_index].get('locked', False)
                else:
                    button.disabled = True
            
            if page <= 1:
                view.prev_button.disabled = True
            if page >= total_pages:
                view.next_button.disabled = True
        
            return embed, view
        
        datapath = './data/recipes'
        unifieddata = []
        
        for dirpath, _, filenames in os.walk(datapath):
            for file in filenames:
                if file.endswith(".json") or file.endswith(".yaml"):
                    file_path = os.path.join(dirpath, file)
                    with open(file_path, 'r') as f:
                        try:
                            data = yaml.safe_load(f)
                            if await skill_unlocks(data, interaction.author.id):
                                unifieddata.append(data)
                                print("Added recipe!")
                            else:     
                                data['locked'] = True
                                unifieddata.append(data)   
                                print("Added locked recipe!")                          
                        except json.JSONDecodeError as e:
                            print(f"Skipping invalid JSON: {file_path}, {e}")
                         
        user_stats = await self.user_manager.fetch_user_stats(interaction.author)
        embed, crafting_view = build_page_embed(user_stats, 1, unifieddata, interaction)
        craft_embed = discord.Embed(title=embed.title,
                              color=embed.color,
                              description=("-# *The leather-bound book contained well-worn pages, so used that tearing was threatened with every sheet of paper that was turned. The recipes carefully etched into the sheet were faded with time and use, but still as understandable.*\n\n-# **To use the tinker book, simply select the number of the item desired. If the required materials are in the chest (which can found in !home), then the item will be crafted.**\n\n-# Items, such at armor and weapons,  can be used in battles to increase the chance of winning by adding to the base defense and attacks scores. Armor, weapons, as well as miscellaneous items can also be sold in the market.\n\n"+embed.description))
        craft_embed.set_footer(text=embed.footer.text)
        
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
