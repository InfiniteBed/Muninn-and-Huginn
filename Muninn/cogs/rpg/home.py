import sqlite3
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
import json


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

        # Ensure each item in the inventory is a dictionary
        parsed_inventory = []
        for item in user_inventory:
            if item['type'] == 'crafting':
                continue
            if isinstance(item, str):
                try:
                    parsed_inventory.append(json.loads(item))  # Parse string items as JSON
                except json.JSONDecodeError:
                    continue  # Skip invalid items
            elif isinstance(item, dict):
                parsed_inventory.append(item)

        # Pagination setup
        items_per_page = 5
        total_pages = max(1, (len(parsed_inventory) + items_per_page - 1) // items_per_page)

        async def get_inventory_page(user_stats, page):
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

            # Ensure each item in the inventory is a dictionary
            parsed_inventory = []
            for item in user_inventory:
                if item['type'] != 'crafting':
                    continue
                if isinstance(item, str):
                    try:
                        parsed_inventory.append(json.loads(item))  # Parse string items as JSON
                    except json.JSONDecodeError:
                        continue  # Skip invalid items
                elif isinstance(item, dict):
                    parsed_inventory.append(item)

            # Pagination setup
            items_per_page = 5
            total_pages = max(1, (len(parsed_inventory) + items_per_page - 1) // items_per_page)

            
            start_index = (page - 1) * items_per_page
            end_index = start_index + items_per_page
            page_items = parsed_inventory[start_index:end_index]

            inventory_embed = discord.Embed(title=f"Crafting Item Chest (Page {page}/{total_pages})", color=discord.Color.yellow())
            
            if page_items:
                inventory_list = []
                for index, item in enumerate(page_items, start=1):
                    item_data = await self.data_manager.find_data(item['type'], item['name'])
                    inventory_list.append(f"**{index + start_index}.** {item['name']}".strip())
                inventory_embed.description = "\n".join(inventory_list)
            else:
                inventory_embed.description = "Your crafting item chest is empty."
            return inventory_embed, page_items

        class InventoryView(View):
            def __init__(self, profile_user, user_stats, top_view):
                super().__init__(timeout=180)
                self.profile_user = profile_user
                self.navigation_view = top_view  # Reference to the top-level navigation view
                self.user_stats = user_stats
                self.current_page = 1
                self.current_embed = None
                self.current_items = None

                # Define navigation buttons
                self.previous_page_button = Button(label="Previous", style=discord.ButtonStyle.secondary, row=4)
                self.previous_page_button.callback = self.previous_page
                self.add_item(self.previous_page_button)

                self.next_page_button = Button(label="Next", style=discord.ButtonStyle.secondary, row=4)
                self.next_page_button.callback = self.next_page
                self.add_item(self.next_page_button)

            async def previous_page(self, interaction: discord.Interaction):
                """Navigate to the previous inventory page."""
                if not await self.ensure_correct_user(interaction):
                    return
                if self.current_page > 1:
                    self.current_page -= 1
                    self.current_embed, self.current_items = await get_inventory_page(self.user_stats, self.current_page)
                    self.refresh_inventory_buttons()
                    await interaction.message.edit(embed=self.current_embed, view=self)

            async def next_page(interaction: discord.Interaction):
                """Navigate to the next inventory page."""
                if not await self.ensure_correct_user(interaction):
                    return
                if self.current_page < total_pages:
                    self.current_page += 1
                    self.current_embed, self.current_items = await get_inventory_page(self.user_stats, self.current_page)
                    self.refresh_inventory_buttons()
                    await interaction.message.edit(embed=self.current_embed, view=self)

            async def back_to_main(self, interaction: discord.Interaction):
                """Return to the main embed."""
                print(f"[DEBUG] Back to Main button clicked by user: {interaction.user.id}")
                if not await self.ensure_correct_user(interaction):
                    print("[DEBUG] User verification failed.")
                    return
                await interaction.message.edit(embed=self.navigation_view.main_embed, view=self.navigation_view)
                print("[DEBUG] Successfully returned to main view.")

            async def initialize_inventory(self):
                """Initialize the inventory page and add the 'Return' button."""
                print(f"[DEBUG] Initializing inventory for user: {self.profile_user.id}")
                self.current_embed, self.current_items = await get_inventory_page(self.user_stats, self.current_page)
                print(f"[DEBUG] Current page: {self.current_page}, Items on page: {len(self.current_items)}")
                self.refresh_inventory_buttons()

                # Add "Back to Main" button dynamically
                back_to_main_button = Button(label="Return", style=discord.ButtonStyle.secondary, row=4)
                back_to_main_button.callback = self.back_to_main
                self.add_item(back_to_main_button)

            async def ensure_correct_user(self, interaction: discord.Interaction):
                print(f"[DEBUG] Interaction by user: {interaction.user.id}, Expected user: {self.profile_user.id}")
                if interaction.user.id != self.profile_user.id:
                    print("[DEBUG] User mismatch. Interaction denied.")
                    await interaction.response.send_message("You cannot interact with this profile!", ephemeral=True)
                    return False
                print("[DEBUG] User verified.")
                return True

            def refresh_inventory_buttons(self):
                """Refresh buttons for the current inventory page."""
                for child in self.children[:]:
                    if hasattr(child, "custom_id") and child.custom_id.startswith("use_item_"):
                        self.remove_item(child)

                self.previous_page_button.disabled = self.current_page == 1
                self.next_page_button.disabled = self.current_page == total_pages

            def create_button_callback(self, index):
                async def button_callback(interaction: discord.Interaction):
                    if not await self.ensure_correct_user(interaction):
                        return
                    if index < len(self.current_items):
                        item = self.current_items[index]
                        await self.use_item(interaction, item)
                    else:
                        await interaction.response.send_message("Invalid item selection.", ephemeral=True)
                return button_callback

            async def use_item(self, interaction: discord.Interaction, item):
                """Handle item usage."""
                if not await self.ensure_correct_user(interaction):
                    return

                if item.get("type") == "consumable":
                    # Fetch the user's current stats
                    user_stats = await self.navigation_view.parent_cog.stats_manager.fetch_user_stats(self.profile_user)
                    current_health = user_stats['health']
                    max_health = user_stats['health_max']

                    # Check if the user's health is already at maximum
                    if current_health >= max_health:
                        max_health_embed = discord.Embed(
                            title="Cannot Use Item",
                            description=f"Your health is already at maximum (**{current_health}/{max_health}**).",
                            color=discord.Color.red()
                        )
                        await interaction.followup.send(embed=max_health_embed, ephemeral=True)
                        return

                    # Apply the healing effect
                    heal_amount = item.get("base_heal", 0)
                    await self.navigation_view.parent_cog.stats_manager.modify_user_stat(self.profile_user, "health", heal_amount)

                    # Reload the user's stats to get the updated health
                    updated_stats = await self.navigation_view.parent_cog.stats_manager.fetch_user_stats(self.profile_user)
                    updated_health = updated_stats['health_display']

                    # Send a green embed with healing information
                    heal_embed = discord.Embed(
                        title="Item Used",
                        description=f"You used **{item['name']}** and healed for **{heal_amount} HP**.\nYour current health is now **{updated_health}**.",
                        color=discord.Color.green()
                    )
                    await interaction.followup.send(embed=heal_embed, ephemeral=True)

                    # Remove the used item from the inventory
                    self.current_items.remove(item)
                    updated_inventory = json.dumps(self.current_items)  # Serialize the updated inventory

                    # Update the inventory in the database
                    await self.navigation_view.parent_cog.update_inventory_in_database(self.profile_user.id, updated_inventory)

                    # Reload the inventory data
                    user_inventory = updated_stats['inventory']
                    if isinstance(user_inventory, str):
                        try:
                            self.current_items = json.loads(user_inventory)  # Deserialize if it's a JSON string
                        except json.JSONDecodeError:
                            self.current_items = []  # Default to an empty list if JSON parsing fails
                    elif isinstance(user_inventory, list):
                        self.current_items = user_inventory
                    else:
                        self.current_items = []

                if item.get("type") == "equipment":
                    if item.get("slot") == "hand":
                        return

                    await self.navigation_view.parent_cog.stats_manager.equip_from_inventory(ctx, ctx.author, item['slot'], item)

                # Redirect to the main page after using the item
                await interaction.message.edit(embed=self.navigation_view.main_embed, view=self.navigation_view)
                
        class HomeView(View):
            def __init__(self, ctx, user_id, user_stats):
                super().__init__()
                self.user_id = user_id
                self.user_stats = user_stats
                self.ctx = ctx

            @discord.ui.button(label="Rest", style=discord.ButtonStyle.green)
            async def rest_button(self, interaction: discord.Interaction, button: Button):
                conn = sqlite3.connect('discord.db')
                c = conn.cursor()

                # Check if the user has any ongoing activity
                c.execute('SELECT activity FROM stats WHERE user_id = ?', (self.user_id,))
                activity = c.fetchone()

                if activity and activity[0]:
                    await interaction.response.send_message("You cannot rest while engaged in another activity.", ephemeral=True)
                else:
                    # Update the activity to "long rest"
                    c.execute('UPDATE stats SET activity = ? WHERE user_id = ?', ("long rest", self.user_id))
                    conn.commit()
                    await interaction.response.send_message("You are now taking a long rest.", ephemeral=True)

                conn.close()
            
            @discord.ui.button(label="Pack", style=discord.ButtonStyle.secondary, row=0)
            async def inventory_button(self, interaction: discord.Interaction, button: Button):
                self.current_menu = "Pack"
                inventory_view = InventoryView(self.ctx.author, self.user_stats, Home)
                await inventory_view.initialize_inventory()
                await interaction.response.edit_message(embed=inventory_view.current_embed, view=inventory_view)

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
