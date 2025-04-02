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

        try:
            print(f"Rankusers command triggered for guild {ctx.guild.id}")  # Debugging line to check guild ID

            # Fetch rankings data from the Rankings cog
            rankings_cog = self.bot.get_cog("Rankings")
            if not rankings_cog:
                await ctx.send("Rankings cog is not loaded.")
                return

            guild_id = ctx.guild.id
            rankings_cog.cur.execute(f'''
                SELECT friendly_name, message_count 
                FROM discord_{guild_id} 
                ORDER BY message_count DESC
            ''')
            rankings = rankings_cog.cur.fetchall()

            if not rankings:
                await ctx.send("No ranking data found.")
                return

            # Extract user names and message counts
            user_names = [row[0] for row in rankings]
            message_counts = [row[1] for row in rankings]

            # Generate the ranking graph
            plt.figure(figsize=(10, 6))
            plt.barh(user_names, message_counts, color='skyblue')
            plt.xlabel("Messages Sent")
            plt.ylabel("User")
            plt.title("User Ranking Based on Messages Sent (All Time)")

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
            pass  # No database connection to close here

# Setup function to add the cog to the bot
async def setup(bot):
    await bot.add_cog(GraphMessageRankingsTotal(bot))