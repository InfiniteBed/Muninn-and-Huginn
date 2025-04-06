import discord  # type: ignore
from discord.ext import commands  # type: ignore
from discord.ui import View, Button
import sqlite3
from datetime import datetime, timedelta
import json
import random
from dateutil import parser  # Add this import
from icecream import ic

class Status(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.search = bot.get_cog('Search')
        self.utils = bot.get_cog('Utils')
        self.timezone_converter = bot.get_cog('TimezoneConverter')
        self.stats_manager = bot.get_cog("StatsManager")
        self.data_manager = self.bot.get_cog("DataManager") # For Item and Expedition Info

    @commands.command(name="status", aliases=["me"])
    async def status(self, ctx, user: str = None):
        if user is None:
            user = ctx.author
        else:
            user = await self.search.find_user(user, ctx.guild)
            if not user:
                await ctx.send("No profile found.")
                return

        user_stats = await self.stats_manager.fetch_user_stats(user)
        
        if not user_stats:
            error_embed = discord.Embed(
                title="Error",
                description="The specified user does not exist or has no profile. Please create a profile with !profile_setup.",
                color=discord.Color.red()
            )
            await ctx.send(embed=error_embed)
            return

        embed_color, avatar_image, has_custom_image = await self.utils.get_avatar_color_and_image(user)
        file = discord.File(f"/usr/src/bot/profile_images/{user.id}.png", filename="image.png") if has_custom_image else None

        # Main page embed
        main_embed = discord.Embed(title=f"{user_stats['profile_name']} - Level {user_stats['level']}", color=embed_color)
        main_embed.set_thumbnail(url="attachment://image.png" if has_custom_image else user.avatar.url)
        main_embed.add_field(name="Health", value=user_stats['health_display'], inline=True)
        main_embed.add_field(name="Coins", value=f"{user_stats['coins']} coins", inline=True)  # Added coins field
        main_embed.add_field(name="Expedition", value="Active" if user_stats['activity'] else "Idle", inline=True)

        # Expedition page embed
        expedition_embed = discord.Embed(title="Expedition Details", color=embed_color)
        expedition_completed = False
        expedition_name = None
        if user_stats['activity'] and user_stats['activity'] != "{}":
            activity_data = eval(user_stats['activity'])
            expedition_name = activity_data.get('expedition_name')
            start_time_str = activity_data.get('start_time')
            expedition_details = activity_data.get('expedition_details', {})
            start_time = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
            current_time = datetime.now()
            california_time = await self.timezone_converter.convert_time(start_time_str)
            # Adjust parsing to handle timezone abbreviations
            california_time = parser.parse(california_time)  # Use dateutil.parser to parse the time
            formatted_start_time = california_time.strftime("%b. %d at %I:%M %p")
            time_remaining = start_time - current_time
            rounded_time_remaining = timedelta(seconds=round(time_remaining.total_seconds()))
            formatted_time_remaining = str(rounded_time_remaining).split(".")[0]

            expedition_embed.add_field(name="Expedition Name", value=expedition_name, inline=True)
            expedition_embed.add_field(name="End Time", value=formatted_start_time, inline=False)
            expedition_embed.add_field(name="Time Remaining", value=formatted_time_remaining if start_time > current_time else "Complete!", inline=True)
            expedition_embed.set_thumbnail(url="attachment://image.png" if has_custom_image else user.avatar.url)

            if start_time <= current_time:
                expedition_completed = True
        else:
            expedition_embed.add_field(name="Expedition", value="No active expedition.", inline=False)
            expedition_embed.set_thumbnail(url="attachment://image.png" if has_custom_image else user.avatar.url)

        # Info page embed
        info_embed = discord.Embed(title="Character Info", color=embed_color)
        info_embed.set_thumbnail(url="attachment://image.png" if has_custom_image else user.avatar.url)
        info_embed.add_field(name="Class", value=user_stats['class'], inline=True)
        info_embed.add_field(name="Race", value=user_stats['race'], inline=True)
        info_embed.add_field(name="Alignment", value=user_stats['alignment'], inline=True)
        info_embed.add_field(name="Ability Scores", value=user_stats['scores_display'], inline=True)
        info_embed.add_field(name="Bio", value=user_stats['bio'], inline=True)

        # Helper function to format equipped items
        def format_item(item):
            """Format an item with its prefix, name, and actions."""
            if not item or item == "None":
                return "None"
            item_data = json.loads(item) if isinstance(item, str) else item
            prefix = item_data.get("prefix", "")
            name = item_data.get("name", "Unknown Item")
            actions = item_data.get("actions", [])

            formatted_item = f"{prefix} {name}".strip()
            if actions:
                formatted_actions = "\n".join(
                    f"- *{action['name']}*: {action['description']} (Damage: {action.get('damage', 0)}, Defense: {action.get('defense', 0)})"
                    for action in actions
                )
                formatted_item += f"\n{formatted_actions}"
            return formatted_item

        # Equipped Items page embed
        equipped_embed = discord.Embed(title="Equipped Items", color=embed_color)
        equipped_embed.set_thumbnail(url="attachment://image.png" if has_custom_image else user.avatar.url)
        equipped_embed.add_field(name="Head", value=format_item(user_stats['head']), inline=True)
        equipped_embed.add_field(name="Upper Body", value=format_item(user_stats['upper']), inline=True)
        equipped_embed.add_field(name="Lower Body", value=format_item(user_stats['lower']), inline=True)
        equipped_embed.add_field(name="Feet", value=format_item(user_stats['feet']), inline=True)
        equipped_embed.add_field(name="Left Hand", value=format_item(user_stats['hand_left']), inline=True)
        equipped_embed.add_field(name="Right Hand", value=format_item(user_stats['hand_right']), inline=True)

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

        async def get_inventory_page(page):
            start_index = (page - 1) * items_per_page
            end_index = start_index + items_per_page
            page_items = parsed_inventory[start_index:end_index]

            inventory_embed = discord.Embed(title=f"Inventory (Page {page}/{total_pages})", color=embed_color)
            inventory_embed.set_thumbnail(url="attachment://image.png" if has_custom_image else user.avatar.url)
            if page_items:
                inventory_list = []
                for index, item in enumerate(page_items, start=1):
                    item_data = await self.data_manager.find_data(ctx, item['type'], item['name'])
                    ic(item_data)
                    description = item_data['description']
                    prefix = item.get('prefix', '')  # Get the prefix if available
                    heal_info = f" (Heals: {item.get('base_heal')} HP)" if item.get('base_heal') else ""
                    inventory_list.append(f"**{index + start_index}. *{prefix}* {item['name']}** - {description}{heal_info}".strip())
                inventory_embed.description = "\n".join(inventory_list)
            else:
                inventory_embed.description = "Your inventory is empty."
            return inventory_embed, page_items

        # Button view for inventory and page navigation
        from discord.ui import Button as CustomButton  # Rename Button to avoid conflicts with discord.ui.Button decorator

        class InventoryView(View):
            def __init__(self, profile_user, navigation_view):
                super().__init__(timeout=180)
                self.profile_user = profile_user
                self.navigation_view = navigation_view  # Reference to the top-level navigation view
                self.current_page = 1
                self.current_embed = None
                self.current_items = None

                # Define navigation buttons
                self.previous_page_button = CustomButton(label="Previous", style=discord.ButtonStyle.secondary, row=4)
                self.previous_page_button.callback = self.previous_page
                self.add_item(self.previous_page_button)

                self.next_page_button = CustomButton(label="Next", style=discord.ButtonStyle.secondary, row=4)
                self.next_page_button.callback = self.next_page
                self.add_item(self.next_page_button)

            async def previous_page(self, interaction: discord.Interaction):
                """Navigate to the previous inventory page."""
                if not await self.ensure_correct_user(interaction):
                    return
                if self.current_page > 1:
                    self.current_page -= 1
                    self.current_embed, self.current_items = await get_inventory_page(self.current_page)
                    self.refresh_inventory_buttons()
                    await interaction.message.edit(embed=self.current_embed, view=self)

            async def next_page(self, interaction: discord.Interaction):
                """Navigate to the next inventory page."""
                if not await self.ensure_correct_user(interaction):
                    return
                if self.current_page < total_pages:
                    self.current_page += 1
                    self.current_embed, self.current_items = await get_inventory_page(self.current_page)
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
                self.current_embed, self.current_items = await get_inventory_page(self.current_page)
                print(f"[DEBUG] Current page: {self.current_page}, Items on page: {len(self.current_items)}")
                self.refresh_inventory_buttons()

                # Add "Back to Main" button dynamically
                back_to_main_button = CustomButton(label="Return", style=discord.ButtonStyle.secondary, row=4)
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

                for index, item in enumerate(self.current_items):
                    row = index // 5
                    if row >= 4:
                        break
                    custom_id = f"use_item_{index}"
                    button = CustomButton(label=f"Use {item['name']}", style=discord.ButtonStyle.success, row=row, custom_id=custom_id)
                    button.callback = self.create_button_callback(index)
                    self.add_item(button)

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

                # Acknowledge the interaction to prevent "This interaction failed" errors
                await interaction.response.defer()

                if item.get("slot") == "consumable":
                    # Fetch the user's current stats
                    user_stats = await self.navigation_view.parent_cog.stats_manager.fetch_user_stats(self.profile_user)
                    current_health = user_stats['health']
                    max_health = user_stats['health_max']

                    # Check if the user's health is already at maximum
                    if current_health >= max_health:
                        # Send a red embed indicating the user cannot heal
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

                # Redirect to the main page after using the item
                await interaction.message.edit(embed=self.navigation_view.main_embed, view=self.navigation_view)

        # Button view for top-level navigation
        class NavigationView(View):
            def __init__(self, profile_user, expedition_completed, expedition_name=None, parent_cog=None, main_embed=None):
                super().__init__(timeout=180)
                self.profile_user = profile_user
                self.expedition_completed = expedition_completed
                self.expedition_name = expedition_name
                self.parent_cog = parent_cog  # Reference to the parent cog
                self.main_embed = main_embed  # Store the main embed
                self.current_menu = "Main"  # Track the current menu

            def update_button_styles(self):
                """Update button styles based on the current menu."""
                for child in self.children:
                    if isinstance(child, Button):
                        if child.label == self.current_menu:
                            child.style = discord.ButtonStyle.blurple  # Highlight the current menu
                        else:
                            child.style = discord.ButtonStyle.secondary  # Reset other buttons

            @discord.ui.button(label="Main", style=discord.ButtonStyle.primary)
            async def main_button(self, interaction: discord.Interaction, button: Button):
                self.current_menu = "Main"
                self.update_button_styles()
                await interaction.response.edit_message(embed=self.main_embed, view=self)

            @discord.ui.button(label="Expedition", style=discord.ButtonStyle.secondary)
            async def expedition_button(self, interaction: discord.Interaction, button: Button):
                self.current_menu = "Expedition"
                self.update_button_styles()
                await interaction.response.edit_message(embed=expedition_embed, view=self)

            @discord.ui.button(label="Info", style=discord.ButtonStyle.secondary)
            async def info_button(self, interaction: discord.Interaction, button: Button):
                self.current_menu = "Info"
                self.update_button_styles()
                await interaction.response.edit_message(embed=info_embed, view=self)

            @discord.ui.button(label="Equipped Items", style=discord.ButtonStyle.secondary)
            async def equipped_button(self, interaction: discord.Interaction, button: Button):
                self.current_menu = "Equipped Items"
                self.update_button_styles()
                await interaction.response.edit_message(embed=equipped_embed, view=self)

            @discord.ui.button(label="Inventory", style=discord.ButtonStyle.secondary)
            async def inventory_button(self, interaction: discord.Interaction, button: Button):
                self.current_menu = "Inventory"
                self.update_button_styles()
                inventory_view = InventoryView(self.profile_user, self)
                await inventory_view.initialize_inventory()
                await interaction.response.edit_message(embed=inventory_view.current_embed, view=inventory_view)

            # Add a button for expedition results if the expedition is completed
            if expedition_completed:
                @discord.ui.button(label="Expedition Results", style=discord.ButtonStyle.success)
                async def expedition_results_button(self, interaction: discord.Interaction, button: Button):
                    if not self.parent_cog:
                        return

                    # Calculate expedition results
                    result, roll_for_result, name, pronoun, pronoun_possessive, formatted_text = await self.parent_cog.calculate_expedition_results(
                        self.profile_user, self.expedition_name
                    )

                    # Determine embed color based on result type
                    color_map = {
                        "major success": discord.Color.green(),
                        "success": discord.Color.dark_green(),
                        "fail": discord.Color.dark_red(),
                        "major fail": discord.Color.red()
                    }
                    embed_color = color_map.get(roll_for_result, discord.Color.blue())

                    # Prepare the results embeds
                    embeds = []
                    current_description = ""
                    for paragraph in formatted_text:
                        if len(current_description) + len(paragraph) + 2 > 4096:  # Split if adding the paragraph exceeds 4096 characters
                            embed = discord.Embed(
                                title="Expedition Results",
                                description=current_description,
                                color=embed_color
                            )
                            embed.set_thumbnail(url="attachment://image.png" if self.profile_user.avatar else self.profile_user.avatar.url)
                            embeds.append(embed)
                            current_description = paragraph
                        else:
                            current_description += f"\n\n{paragraph}"

                    # Add the last embed if there's remaining content
                    if current_description:
                        embed = discord.Embed(
                            title="Expedition Results",
                            description=current_description,
                            color=embed_color
                        )
                        embed.set_thumbnail(url="attachment://image.png" if self.profile_user.avatar else self.profile_user.avatar.url)
                        embeds.append(embed)

                    # Add outcome, coins, and damage to the first embed
                    if embeds:
                        embeds[0].add_field(name="Outcome", value=roll_for_result.replace("_", " ").title(), inline=False)
                        embeds[0].add_field(name="Coins Earned", value=f"{result.get('coins', 0)} coins", inline=True)
                        embeds[0].add_field(name="Damage Taken", value=f"{result.get('health', 0)} health", inline=True)

                    # Remove all buttons after showing results
                    self.clear_items()

                    # Send the embeds sequentially
                    try:
                        for embed in embeds:
                            if interaction.response.is_done():
                                await interaction.followup.send(embed=embed)
                            else:
                                await interaction.response.send_message(embed=embed)
                    except discord.errors.NotFound:
                        print("[ERROR] Interaction webhook expired or invalid. Unable to send expedition results.")

                    # Delete the expedition from the database
                    await self.parent_cog.delete_expedition_from_database(self.profile_user.id)

            async def interaction_check(self, interaction: discord.Interaction):
                """Ensure only the requested user can interact with the buttons."""
                if interaction.user.id != self.profile_user.id:
                    await interaction.response.send_message("You cannot interact with this profile!", ephemeral=True)
                    return False
                return True

        navigation_view = NavigationView(user, expedition_completed, expedition_name=expedition_name, parent_cog=self, main_embed=main_embed)
        await ctx.send(file=file, embed=main_embed, view=navigation_view)

    async def calculate_expedition_results(self, user, expedition_name):
        expedition = await self.list_manager.get_expedition(expedition_name)
        print (expedition_name)
        print (expedition)
        if "error" in expedition:
            print(f"[ERROR] Expedition not found: {expedition_name}")
            return {"error": "Expedition not found"}

        user_stats = await self.stats_manager.fetch_user_stats(user)
        name = user_stats['profile_name']
        pronoun = user_stats['pronoun']
        pronoun_possessive = user_stats['pronoun_possessive']
        gender = "male" if pronoun.lower() in ["he", "him"] else "female"

        ability_test = expedition['ability_test']
        ability_scores = user_stats['ability_scores']

        roll_for_result = self.simulate_ability_check(ability_test, ability_scores)

        results = expedition.get('results', {})
        result = results.get(roll_for_result, {
            'text': {'male': ['No result text available.'], 'female': ['No result text available.']},
            'coins': 0,
            'health': 0
        })

        # Apply stat changes
        await self.stats_manager.modify_user_stat(user, 'coins', result.get('coins', 0))
        await self.stats_manager.modify_user_stat(user, 'health', -result.get('health', 0))

        # Format the result text based on gender
        formatted_text = [
            paragraph.format(name=name, pronoun=pronoun, pronoun_possessive=pronoun_possessive)
            for paragraph in result['text'].get(gender, ['No result text available.'])
        ]

        return result, roll_for_result, name, pronoun, pronoun_possessive, formatted_text

    def simulate_ability_check(self, ability, user_ability_scores):
        if ability in user_ability_scores:
            score = user_ability_scores[ability]
            roll = random.randint(1, 20)
            total = roll + score
            if total >= 25:
                return 'major success'
            elif total >= 18:
                return 'success'
            elif total >= 12:
                return 'fail'
            else:
                return 'major fail'
        return 'fail'

    async def update_inventory_in_database(self, user_id, updated_inventory):
        """Update the user's inventory in the inventory table."""
        conn = sqlite3.connect('discord.db')
        cursor = conn.cursor()
        try:
            # Update the inventory in the inventory table
            cursor.execute("UPDATE inventory SET inventory = ? WHERE user_id = ?", (updated_inventory, user_id))
            conn.commit()
            print(f"[DEBUG] Updated inventory for user {user_id}: {updated_inventory}")
        except sqlite3.Error as e:
            print(f"[ERROR] Failed to update inventory in database: {e}")
        finally:
            conn.close()

    async def delete_expedition_from_database(self, user_id):
        """Delete the user's expedition from the database."""
        conn = sqlite3.connect('discord.db')
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE stats SET activity = NULL WHERE user_id = ?", (user_id,))
            conn.commit()
            print(f"[DEBUG] Deleted expedition for user {user_id}")
        except sqlite3.Error as e:
            print(f"[ERROR] Failed to delete expedition from database: {e}")
        finally:
            conn.close()

async def setup(bot):
    await bot.add_cog(Status(bot))
