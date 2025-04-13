import discord
from discord.ext import commands
import matplotlib.pyplot as plt
import sqlite3
import os
from pathlib import Path
from cogs.graphs.discord_theme import DiscordTheme  # Import the Discord theme cog
import pytz
from datetime import datetime
import matplotlib.font_manager  # Import font manager for adding custom fonts

class MealStatsGraph(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "discord.db"
        self.california_tz = pytz.timezone('US/Pacific')  # Add California timezone

        # Add NotoColorEmoji font for emoji rendering
        matplotlib.font_manager.fontManager.addfont("/usr/src/bot/fonts/NotoColorEmoji-Regular.ttf")

    @commands.command(name="meal_graph")
    async def generate_meal_graph(self, ctx, user: discord.User = None):
        """Generate a bar chart for meal statistics, optionally filtered by a specific user."""
        prop = DiscordTheme.apply_discord_theme()  # Apply global Discord theme and capture prop
        conn = None
        cursor = None
        try:
            # Connect to the database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Fetch meal statistics, optionally filtered by user
            if user:
                cursor.execute("""
                    SELECT meal, status, emoji, COUNT(*) as count
                    FROM meals
                    WHERE user_id = ?
                    GROUP BY meal, status, emoji
                """, (user.id,))
            else:
                cursor.execute("""
                    SELECT meal, status, emoji, COUNT(*) as count
                    FROM meals
                    GROUP BY meal, status, emoji
                """)
            stats = cursor.fetchall()

            if not stats:
                await ctx.send("No meal data available to generate a graph.")
                return

            # Process data for the graph
            meal_status = {}
            for meal, status, emoji, count in stats:
                key = f"{status} ({emoji})" if emoji else status
                if meal not in meal_status:
                    meal_status[meal] = {}
                meal_status[meal][key] = count

            # Prepare data for plotting
            meals = list(meal_status.keys())
            statuses = sorted({key for meal in meal_status.values() for key in meal.keys()})
            data = {status: [meal_status.get(meal, {}).get(status, 0) for meal in meals] for status in statuses}

            # Include emojis in meal labels
            meal_labels = [
                f"{meal} ({', '.join(set(key.split(' ')[-1] for key in meal_status[meal].keys() if '(' in key))})"
                for meal in meals
            ]

            # Generate the bar chart
            x = range(len(meals))
            plt.figure(figsize=(12, 8))
            for i, status in enumerate(statuses):
                plt.bar([p + i * 0.25 for p in x], data[status], width=0.25, label=status)

            plt.xticks([p + 0.25 for p in x], meal_labels, fontproperties=prop, rotation=45, ha="right")
            plt.xlabel("Meals", fontproperties=prop)
            plt.ylabel("Count", fontproperties=prop)
            title = f"Meal Statistics for {user.name}" if user else "Meal Statistics (All Users)"
            plt.title(title, fontproperties=prop)
            plt.legend()  # Use default font for the legend

            # Add California time to the graph title
            california_time = datetime.now(self.california_tz).strftime("%Y-%m-%d %I:%M %p %Z")
            plt.suptitle(f"Generated on {california_time}", fontproperties=prop)

            # Save the graph to a file
            file_path = "cogs/graphs/meal_stats.png"
            if os.path.exists(file_path):
                os.remove(file_path)
            plt.savefig(file_path, bbox_inches="tight")
            plt.close()

            # Send the graph to the Discord channel
            await ctx.send(file=discord.File(file_path))

            # Remove the file after sending
            os.remove(file_path)

        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

# Setup function to add the cog to the bot
async def setup(bot):
    await bot.add_cog(MealStatsGraph(bot))
