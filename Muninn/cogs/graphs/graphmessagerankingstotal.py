import discord
from discord.ext import commands
import matplotlib.pyplot as plt
import sqlite3
import os

class GraphMessageRankingsTotal(commands.Cog):
    # Set global Discord-style theme
    def apply_discord_theme(self):
        """Apply a unified Discord-like theme to all graphs."""
        plt.style.use("dark_background")

        plt.rcParams["font.family"] = "Montserrat"  # Close to Discord's "gg sans"
        plt.rcParams["text.color"] = "#DCDDDE"  # Light gray text
        plt.rcParams["axes.facecolor"] = "#2C2F33"  # Dark mode background
        plt.rcParams["axes.edgecolor"] = "#99AAB5"  # Subtle borders
        plt.rcParams["axes.labelcolor"] = "#DCDDDE"
        plt.rcParams["xtick.color"] = "#DCDDDE"
        plt.rcParams["ytick.color"] = "#DCDDDE"
        plt.rcParams["grid.color"] = "#555555"  # Subtle grid lines
        plt.rcParams["figure.facecolor"] = "#5762E3"
        plt.rcParams["savefig.facecolor"] = "#2C2F33"
    
    requires_user = True

    def __init__(self, bot):
        self.bot = bot
        self.utils = bot.get_cog('Utils')  # Reference the Utils cog

    @commands.command(name='g_user_rankings')
    async def generate_graph(self, ctx):
        self.apply_discord_theme()  # Apply global styling
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
                SELECT user_id, guild_id, COUNT(*)
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

            # Extract user_ids and message counts
            user_ids = [row[0] for row in filtered_data]
            message_counts = [row[2] for row in filtered_data]

            # Get user names for display
            user_names = []
            for user_id in user_ids:
                user = await self.bot.fetch_user(user_id)
                user_names.append(user.display_name if user else str(user_id))

            # Generate the ranking graph
            plt.figure(figsize=(10, 6))
            plt.barh(user_names, message_counts, color='skyblue')
            plt.xlabel("Messages Sent", fontproperties=prop)
            plt.ylabel("User", fontproperties=prop)
            plt.title("User Ranking Based on Messages Sent (All Time)", fontproperties=prop)

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
    await bot.add_cog(GraphMessageRankingsTotal(bot))