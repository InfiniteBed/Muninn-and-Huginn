import discord
from discord.ext import commands
import matplotlib.pyplot as plt
import sqlite3
import os
from pathlib import Path
from cogs.graphs.discord_theme import DiscordTheme  # Import the new Discord theme cog

class GraphWordCountPerMessage(commands.Cog):
    requires_user = True

    def __init__(self, bot):
        self.bot = bot
        self.utils = bot.get_cog('Utils')  # Reference the Utils cog


    @commands.command(name='g_word_count')
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
            
            user_ids = []
            word_counts = []

            for user in ctx.guild.members:
                cursor.execute(f'SELECT * FROM user_activity WHERE guild_id = ? AND user_id = ?', (ctx.guild.id, user.id))
                user_data = cursor.fetchall()

                message_count = len(user_data)
                if message_count == 0:
                    continue
                word_counts.append(round(sum([row[7] for row in user_data]) / message_count, 1) if message_count else 0)
                user_ids.append(user.id)
                
            # Get user names for display
            user_names = []
            for user_id in user_ids:
                user = await self.bot.fetch_user(user_id)
                user_names.append(user.display_name if user else str(user_id))
                
            # Zip together and sort by word count
            combined = list(zip(user_names, word_counts))
            combined.sort(key=lambda x: x[1], reverse=False)  # Sort descending by word count

            # Unzip sorted data
            sorted_user_names, sorted_word_counts = zip(*combined)

            # Generate the ranking graph
            plt.figure(figsize=(6, 3))
            plt.barh(sorted_user_names, sorted_word_counts, color="orange")
            plt.xlabel("Average Word Count per Message", fontproperties=prop)  # Use prop for font styling
            plt.title("\"How much does this person send in a single message?\"", fontproperties=prop)
            plt.yticks(fontproperties=prop)

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
    await bot.add_cog(GraphWordCountPerMessage(bot))