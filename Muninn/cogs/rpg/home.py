import sqlite3
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
import json
from icecream import ic


class Home(commands.Cog):
    def __init__(self, bot):
        self.user_manager = bot.get_cog("StatsManager")
        self.data_manager = bot.get_cog("DataManager")
        self.bot = bot

    @commands.hybrid_command(name="home", description="Rest and relax, or make some new items")
    async def home(self, ctx):
        
        user_stats = await self.user_manager.fetch_user_stats(ctx.author)
        
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
                
        # Pagination setup
        items_per_page = 5
        total_pages = max(1, (len(parsed_inventory) + items_per_page - 1) // items_per_page)

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

        class HomeView(View):
            def __init__(self, ctx, user_id, user_stats):
                super().__init__()
                self.user_id = user_id
                self.user_stats = user_stats
                self.ctx = ctx

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
                await interaction.response.edit_message(embed=inventory_view, view=None)

        """View your home and interact with it."""
        user = ctx.author
        
        user_stats = await self.user_manager.fetch_user_stats(user)

        embed = discord.Embed(
            title=f"{user.display_name}'s Home",
            description="Welcome to your home! You can rest here to recover.",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=user.avatar.url if user.avatar else None)

        view = HomeView(ctx, user.id, user_stats)
        await ctx.send(embed=embed, view=view)
        
async def setup(bot):
    await bot.add_cog(Home(bot))
