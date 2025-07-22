import discord
from discord.ext import commands
import matplotlib.pyplot as plt
import sqlite3
import os
from datetime import datetime, timedelta
import seaborn as sns
import pytz
from cogs.graphs.discord_theme import DiscordTheme  # Import the new Discord theme cog

# Function to convert timestamp to California time
def convert_to_california_time(timestamp: datetime) -> datetime:
    if timestamp is None:
        raise ValueError("Timestamp cannot be None.")
    if timestamp.tzinfo is None:
        timestamp = pytz.utc.localize(timestamp)
    california_zone = pytz.timezone('America/Los_Angeles')
    california_time = timestamp.astimezone(california_zone)
    return california_time

class GraphUserActivityMonth(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.search = bot.get_cog('Search')

    @commands.command(name="g_user_activity_month")
    async def generate_graph(self, ctx, user: str = None):
        prop = DiscordTheme.apply_discord_theme()  # Apply global Discord theme and capture prop
        """Generate a bar chart of user activity over the past week."""
        
        if user is None:
            user = ctx.author
        else:
            user = await self.search.find_user(user, ctx.guild)
            if not user:
                await ctx.send("No profile found.")
                return

        # Open database connection here
        conn = sqlite3.connect("discord.db")
        cursor = conn.cursor()

        try:
            # Get user activity for the past 7 days, including today
            start_date = datetime.utcnow() - timedelta(days=30)  # Starting from 30 days ago
            california_start_date = convert_to_california_time(start_date)

            # Ensure the start date is the beginning of the day
            california_start_date = california_start_date.replace(hour=0, minute=0, second=0, microsecond=0)

            # Get today's date for comparison (California time)
            today = datetime.utcnow()
            california_today = convert_to_california_time(today).replace(hour=0, minute=0, second=0, microsecond=0)

            cursor.execute("""
                SELECT DATE(timestamp), COUNT(*)
                FROM user_activity
                WHERE user_id = ? AND timestamp >= ?
                GROUP BY DATE(timestamp)
            """, (user.id, california_start_date.strftime('%Y-%m-%d')))

            data = cursor.fetchall()
            
            # Extract data
            dates = [row[0] for row in data]  # This is the list of dates fetched from the database
            message_counts = [row[1] for row in data]  # Message counts for each date

            # Ensure all days are present, including today
            all_dates = [(california_start_date + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(31)]  # 7 days + today
            message_counts_dict = dict(zip(dates, message_counts))
            message_counts = [message_counts_dict.get(date, 0) for date in all_dates]

            # Convert string dates to datetime objects for proper plotting
            all_dates_datetime = [datetime.strptime(date, '%Y-%m-%d') for date in all_dates]

            # Generate the graph
            plt.figure(figsize=(8, 5))
            plt.bar(all_dates_datetime, message_counts)  # Use datetime objects here
            plt.xlabel("Date", fontproperties=prop)
            plt.ylabel("Messages Sent", fontproperties=prop)
            plt.title(f"Message Activity for {user.display_name}", fontproperties=prop)
            plt.xticks(rotation=45, fontproperties=prop)
            plt.grid(axis="y")

            # Check if the graph file exists, and remove it if it does
            file_path = f"cogs/graphs/user_activity_{user.id}.png"

            # Save the graph to file
            plt.savefig(file_path, bbox_inches="tight")
            plt.close()

            # Send the graph to the Discord channel
            await ctx.send(file=discord.File(file_path))

            # Delete the file after sending
            os.remove(file_path)
        
        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")
        
        finally:
            # Ensure the connection is closed after processing
            cursor.close()
            conn.close()

# Setup function to add the cog to the bot
async def setup(bot):
    await bot.add_cog(GraphUserActivityMonth(bot))