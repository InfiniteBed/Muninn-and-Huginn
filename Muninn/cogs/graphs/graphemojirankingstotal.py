import discord
from discord.ext import commands
import matplotlib.pyplot as plt
import sqlite3
import os
from pathlib import Path
from cogs.graphs.discord_theme import DiscordTheme  # Import the new Discord theme cog

class GraphEmojiRankingsTotal(commands.Cog):
    requires_user = True

    def __init__(self, bot):
        self.bot = bot
        self.utils = bot.get_cog('Utils')  # Reference the Utils cog


    @commands.command(name='g_emoji_rankings')
    async def generate_graph(self, ctx):
        prop = DiscordTheme.apply_discord_theme()  # Apply global Discord theme and capture prop
        """Generate a bar chart of user rankings based on all-time messages sent."""
        
        conn = None
        cursor = None
        try:
            print(f"Rankusers command triggered for guild {ctx.guild.id}")  # Debugging line to check guild ID

            # Connect to the database with WAL mode enabled
            conn = sqlite3.connect("discord.db")
            cursor = conn.cursor()

            # Debugging: Confirm the guild_id data type in the database (checking for proper formatting)
            cursor.execute("PRAGMA table_info(user_activity);")
            columns = cursor.fetchall()
            print(f"Table columns: {columns}")  # Check column names and types

            # Get all user activity data
            cursor.execute("""
                SELECT user_id, guild_id, 
                       SUM(emoji_count) AS total_emoji
                FROM user_activity
                GROUP BY user_id, guild_id
            """)
            all_data = cursor.fetchall()

            if not all_data:
                await ctx.send("No message data found.")
                return

            # Filter data for the specific guild
            filtered_data = [row for row in all_data if row[1] == ctx.guild.id]

            if not filtered_data:
                await ctx.send("No data found for this guild.")
                return

            # Extract user_ids and total activity scores
            user_ids = [row[0] for row in filtered_data]
            emoji_count = [(row[2] or 0) for row in filtered_data]  # Sum all counts

            # Get user names for display
            user_names = []
            for user_id in user_ids:
                user = await self.bot.fetch_user(user_id)
                user_names.append(user.display_name if user else str(user_id))

            # Generate the ranking graph
            plt.figure(figsize=(6, 6))
            plt.barh(user_names, emoji_count, color="deeppink")
            plt.xlabel("Emojis Sent", fontproperties=prop)  # Use prop for font styling
            plt.title("User Ranking Based on Total Emojis Sent (All Time)", fontproperties=prop)

            # Check if the graph file exists, and remove it if it does
            file_path = "cogs/graphs/user_ranking_all_time.png"
            if os.path.exists(file_path):
                os.remove(file_path)

            # Save the graph to file
            plt.savefig(file_path, bbox_inches="tight")
            plt.close()

            # Send the graph to the Discord channel
            await ctx.send(file=discord.File(file_path))

            os.remove(file_path)

        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")
        
        finally:
            # Ensure that resources are released, even if an error occurs
            if cursor:
                cursor.close()
            if conn:
                conn.close()

# Setup function to add the cog to the bot
async def setup(bot):
    await bot.add_cog(GraphEmojiRankingsTotal(bot))