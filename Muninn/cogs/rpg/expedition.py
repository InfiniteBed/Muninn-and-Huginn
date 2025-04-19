import asyncio
import sqlite3
import json
import datetime
import discord
from discord.ext import commands
import math
import ast
import random
from discord.ui import View, Button
import os

class ExpeditionBoard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "discord.db"
        self.stats_manager = self.bot.get_cog("StatsManager")
        self.list_manager = self.bot.get_cog("ListManager")

        """Create the table in the SQLite database if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''CREATE TABLE IF NOT EXISTS vendors (
                            vendor TEXT PRIMARY KEY,
                            items TEXT,
                            time_loaded TEXT)''')

        conn.commit()
        conn.close()
        
    async def gather_expeditions(self, location: str = "all"):
        expeditions_data = []
        expeditions_folder = "/usr/src/bot/expeditions/"

        for filename in os.listdir(expeditions_folder):
            if filename.endswith(".json"):
                expedition_name = filename[:-5]  # File name without extension
                expedition = await self.list_manager.get_expedition(expedition_name)
                if location == "all" or location == expedition.get("location"):
                    expeditions_data.append(expedition_name)  # Add file name (not pretty name)
                    print("Expedition added:", expedition_name)

        return expeditions_data

    def is_board_empty(self):
        """Check if the board is empty."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM vendors")
        count = cursor.fetchone()[0]

        conn.close()
        return count == 0
    
    async def regenerate_board(self, ctx):
        """Regenerate the expedition board's content and store it in the database."""
        gathered_expeditions = await self.gather_expeditions()

        # Select 5 unique expeditions randomly without duplicates
        expeditions_board_items = random.sample(gathered_expeditions, min(len(gathered_expeditions), 5))

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Store expedition names with underscores in the database
        cursor.execute(
            "INSERT OR REPLACE INTO vendors (vendor, items, time_loaded) VALUES (?, ?, ?)",
            ("Item Board", json.dumps(expeditions_board_items), datetime.datetime.now().isoformat())
        )

        conn.commit()
        conn.close()

    @commands.command()
    async def board(self, ctx):
        await ctx.send("This command has been deprecated, in favor of the new job system!\nUse `!go` to search for, apply to, and work at a variety of jobs.")
        
        user_stats = await self.stats_manager.fetch_user_stats(ctx.author)

        if user_stats['activity']:
            activity_data = json.loads(user_stats['activity'])
            start_time = activity_data['start_time']

            if not start_time:
                await ctx.send("Error: Missing start time in activity data.")
                return

            try:
                expedition_end_time = datetime.datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
            except ValueError as e:
                await ctx.send(f"Error parsing start time: {e}")
                return

            if datetime.datetime.now() > expedition_end_time:
                embed = discord.Embed(
                    title="Expedition Completed",
                    description="Your expedition has been completed! View the results in your profile using `!me`.",
                    color=discord.Color.gold()
                )
                await ctx.send(embed=embed)
                return

        await self.display_mission_board(ctx)

    async def display_mission_board(self, ctx):
        user_stats = await self.stats_manager.fetch_user_stats(ctx.author)
        name = user_stats['profile_name']
        pronoun = user_stats['pronoun']
        pronoun_possessive = user_stats['pronoun_possessive']

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT items FROM vendors WHERE vendor = ?", ("Item Board", ))
        data = json.loads(cursor.fetchone()[0])
        conn.close()

        if not data:
            await self.regenerate_board(ctx)
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT items FROM vendors WHERE vendor = ?", ("Item Board", ))
            data = json.loads(cursor.fetchone()[0])
            conn.close()

        async def generate_primary_page():
            embed = discord.Embed(title="Expedition Board", color=discord.Color.green())
            description = ""
            for index, expedition_id in enumerate(data):
                expedition_details = await self.list_manager.get_expedition(expedition_id)
                pretty_name = expedition_details.get("name", expedition_id)  # Fallback to ID if name is missing
                description += f"{index + 1}. {pretty_name}\n"
            embed.description = description
            return embed

        async def generate_secondary_page(expedition_id):
            expedition_details = await self.list_manager.get_expedition(expedition_id)
            pretty_name = expedition_details.get("name", expedition_id)  # Fallback to ID if name is missing

            embed = discord.Embed(title=f"Details for {pretty_name}", color=discord.Color.blue())
            embed.add_field(name="Location", value=expedition_details.get("location"), inline=False)
            embed.add_field(name="Description", value=expedition_details.get("description"), inline=False)
            embed.add_field(name="Cost", value=f"{expedition_details.get('cost')} coins", inline=True)
            embed.add_field(name="Time", value=f"{expedition_details.get('hours')} hours", inline=True)
            embed.add_field(name="Ability Test", value=expedition_details.get("ability_test"), inline=True)
            contributor = expedition_details.get("results", {}).get("major success", {}).get("contributor", "Unknown")
            embed.set_footer(text=f"Written by {contributor}")
            return embed

        class NavigationButton(Button):
            def __init__(self, label, style, expedition_name=None, take_action=False, stats_manager=None, list_manager=None, db_path=None):
                if not label:  # Ensure label is not empty
                    label = "Unnamed Button"
                super().__init__(label=label, style=style)
                self.expedition_name = expedition_name  # Use trimmed file name (expedition ID)
                self.take_action = take_action
                self.stats_manager = stats_manager
                self.list_manager = list_manager
                self.db_path = db_path

            async def callback(self, interaction):
                try:
                    if self.take_action and self.expedition_name:
                        user_stats = await self.stats_manager.fetch_user_stats(interaction.user)

                        # Check if the user already has an activity
                        if user_stats['activity']:
                            await interaction.response.send_message("You already have an active expedition!")
                            return

                        expedition_id = self.expedition_name  # Use file name (not pretty name)
                        expedition_details = await self.list_manager.get_expedition(expedition_id)
                        cost = expedition_details.get('cost')

                        if user_stats['coins'] < cost:
                            await interaction.response.send_message(f"You do not have enough coins to take this expedition! You need {cost} coins.")
                            return

                        # Deduct the cost
                        await self.stats_manager.modify_user_stat(interaction.user, 'coins', -cost)

                        # Calculate the end time based on the expedition's duration
                        duration_hours = expedition_details.get('hours', 0)
                        end_time = datetime.datetime.now(datetime.timezone.utc)  # Use timezone-aware datetime
                        end_time += datetime.timedelta(hours=duration_hours)
                        end_time_str = end_time.strftime('%Y-%m-%d %H:%M:%S')

                        # Save the updated activity to the user
                        updated_activity = {
                            'expedition_name': expedition_id,  # Use file name (not pretty name)
                            'start_time': end_time_str,
                        }

                        conn = sqlite3.connect(self.db_path)
                        cursor = conn.cursor()
                        cursor.execute('UPDATE stats SET activity = ? WHERE user_id = ?', 
                                    (json.dumps(updated_activity), interaction.user.id))

                        # Remove the taken expedition from the board
                        cursor.execute("SELECT items FROM vendors WHERE vendor = ?", ("Item Board", ))
                        data = json.loads(cursor.fetchone()[0])
                        data.remove(expedition_id)
                        cursor.execute("UPDATE vendors SET items = ? WHERE vendor = ?", (json.dumps(data), 'Item Board'))
                        conn.commit()
                        conn.close()

                        # Send confirmation as an embed
                        embed = discord.Embed(
                            title="Expedition Started!",
                            description=f"You've successfully started the expedition: **{expedition_id}**",
                            color=discord.Color.gold()
                        )
                        embed.set_footer(text="Good luck on your journey!")
                        await interaction.response.edit_message(embed=embed, view=None)
                    elif self.expedition_name:
                        embed = await generate_secondary_page(self.expedition_name)
                        detail_view = View()
                        detail_view.add_item(NavigationButton(label="Back", style=discord.ButtonStyle.secondary, stats_manager=self.stats_manager, list_manager=self.list_manager, db_path=self.db_path))
                        detail_view.add_item(NavigationButton(label="Take", style=discord.ButtonStyle.success, expedition_name=self.expedition_name, take_action=True, stats_manager=self.stats_manager, list_manager=self.list_manager, db_path=self.db_path))
                        await interaction.response.edit_message(embed=embed, view=detail_view)
                except Exception as e:
                    error_embed = discord.Embed(
                        title="Error",
                        description=f"An error occurred: {str(e)}",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=error_embed)

        embed = await generate_primary_page()
        view = View()

        for expedition_id in data:
            expedition_details = await self.list_manager.get_expedition(expedition_id)
            pretty_name = expedition_details.get("name", expedition_id)  # Fallback to ID if name is missing
            view.add_item(NavigationButton(label=pretty_name, style=discord.ButtonStyle.secondary, expedition_name=expedition_id, stats_manager=self.stats_manager, list_manager=self.list_manager, db_path=self.db_path))

        await ctx.send(embed=embed, view=view)

    @commands.command()
    async def take(self, ctx, expedition_id: int):
        """Take an expedition from the board."""
        user_stats = await self.stats_manager.fetch_user_stats(ctx.author)

        # Check if the user already has an activity
        if user_stats['activity']:
            await ctx.send("You already have an active expedition!")
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT items FROM vendors WHERE vendor = ?", ("Item Board", ))
        data = ast.literal_eval(cursor.fetchone()[0])

        conn.close()

        if not data[expedition_id-1]:
            await ctx.send("Invalid expedition ID!")
            return
    
        expedition_id = data[expedition_id-1]  # Use file name (minus extension)
        expedition_details = await self.list_manager.get_expedition(expedition_id)
        cost = expedition_details.get('cost')

        if user_stats['coins'] < cost:
            await ctx.send(f"You do not have enough coins to take this expedition! You need {cost} coins.")
            return

        # Deduct the cost
        await self.stats_manager.modify_user_stat(ctx.author, 'coins', -cost)

        # Calculate the end time based on the expedition's duration
        duration_hours = expedition_details.get('hours', 0)  # Assuming duration is in hours
        end_time = datetime.datetime.now() + datetime.timedelta(hours=duration_hours or 1)
        end_time_str = end_time.strftime('%Y-%m-%d %H:%M:%S')

        # Save the updated activity to the user
        updated_activity = {
            'expedition_name': expedition_id,  # Use file name (not pretty name)
            'start_time': end_time_str,
        }

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('UPDATE stats SET activity = ? WHERE user_id = ?', 
                    (json.dumps(updated_activity), ctx.author.id))

        # Remove the taken expedition from the board
        data.remove(expedition_id)
        cursor.execute("UPDATE vendors SET items = ? WHERE vendor = ?", (json.dumps(data), 'Item Board'))
        conn.commit()
        conn.close()

        # Regenerate the board if it becomes empty
        if self.is_board_empty():
            await self.regenerate_board(ctx)

        # Send confirmation as an embed
        embed = discord.Embed(
            title="Expedition Started!",
            description=f"You've successfully started the expedition: **{expedition_id}**",
            color=discord.Color.gold()
        )
        embed.set_footer(text="Good luck on your journey!")
        await ctx.send(embed=embed)

    @commands.command()
    async def test_expedition(self, ctx, *, expedition_name: str):
        """Test all possible results of an expedition with your character's stats."""
        expedition = await self.list_manager.get_expedition(expedition_name)
        if not expedition:
            await ctx.send("Expedition not found.")
            return

        user_stats = await self.stats_manager.fetch_user_stats(ctx.author)
        name = user_stats['profile_name']
        pronoun = user_stats['pronoun']
        pronoun_possessive = user_stats['pronoun_possessive']
        
        results = expedition.get('results', {})

        for outcome in results:
            result_texts = [
                paragraph.format(name=name, pronoun=pronoun, pronoun_possessive=pronoun_possessive)
                for paragraph in results[outcome].get('text', ['No result text available.'])
            ]
            coins = results[outcome].get('coins', 0)
            health = results[outcome].get('health', 0)

            # Determine embed color based on result type
            color_map = {
                "major success": discord.Color.green(),
                "success": discord.Color.dark_green(),
                "fail": discord.Color.dark_red(),
                "major fail": discord.Color.red()
            }
            embed_color = color_map.get(outcome, discord.Color.purple())

            current_chunk = ""
            embed_index = 1

            for paragraph in result_texts:
                if len(current_chunk) + len(paragraph) + 2 > 1024:  # +2 accounts for paragraph spacing
                    embed = discord.Embed(
                        title=f"Testing {expedition['name']}: {outcome.title()} (Part {embed_index})",
                        color=embed_color,
                        description=current_chunk.strip()
                    )
                    await ctx.send(embed=embed)
                    current_chunk = ""
                    embed_index += 1

                current_chunk += f"{paragraph}\n\n"

            if current_chunk:  # Send the last embed with coins and health
                embed = discord.Embed(
                    title=f"Testing {expedition['name']}: {outcome.title()} (Part {embed_index})",
                    color=embed_color,
                    description=current_chunk.strip()
                )
                embed.add_field(name="Coins Earned", value=f"{coins} coins", inline=True)
                if health != 0:
                    embed.add_field(name="Health Change", value=f"{-health} health", inline=True)
                await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def force_regenerate_board(self, ctx):
        """Force regenerate the expedition board."""
        await self.regenerate_board(ctx)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT items FROM vendors WHERE vendor = ?", ("Item Board", ))
        data = json.loads(cursor.fetchone()[0])
        conn.close()

        if data:
            await ctx.send("The expedition board has been successfully regenerated with new expeditions!")
        else:
            await ctx.send("The expedition board is now empty. No expeditions were available to add.")

# Setup the cog
async def setup(bot):
    await bot.add_cog(ExpeditionBoard(bot))