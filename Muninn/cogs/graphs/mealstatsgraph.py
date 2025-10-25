import discord
from discord.ext import commands
import matplotlib.pyplot as plt
import sqlite3
import os
from pathlib import Path
from cogs.graphs.discord_theme import DiscordTheme
from cogs.graphs.discord_theme import font_manager as _fm  # type: ignore
from ..advanced_graphs import sanitize_text
import pytz
from datetime import datetime, timedelta
import numpy as np
from .emoji_renderer import TwemojiRenderer

class MealStatsGraph(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "discord.db"
        self.california_tz = pytz.timezone('US/Pacific')
        self.emoji_renderer = TwemojiRenderer(bot)
        # emoji_prop will be set when needed; fallback to regular prop if font missing
        self.emoji_prop = None
        
    def _get_emoji_name(self, emoji):
        """Extract readable name from emoji"""
        # Common food emoji mappings
        emoji_names = {
            '🍕': 'PIZZA',
            '🍔': 'HAMBURGER',
            '🌭': 'HOT DOG',
            '🥪': 'SANDWICH',
            '🌮': 'TACO',
            '🌯': 'BURRITO',
            '🥗': 'SALAD',
            '🥘': 'PAN OF FOOD',
            '🍝': 'SPAGHETTI',
            '🍜': 'RAMEN',
            '🍛': 'CURRY',
            '🍚': 'RICE',
            '🥩': 'STEAK',
            '🍗': 'CHICKEN',
            '🍖': 'MEAT ON BONE',
            '🌶️': 'CHILI',
            '🫕': 'FONDUE',
            '🥣': 'BOWL WITH SPOON',
            '🥡': 'TAKEOUT BOX',
            '🍱': 'BENTO BOX',
            '🍙': 'RICE BALL',
            '🍘': 'RICE CRACKER',
            '🍥': 'FISH CAKE',
            '🥠': 'FORTUNE COOKIE',
            '🥨': 'PRETZEL',
            '🥯': 'BAGEL',
            '🥖': 'BAGUETTE',
            '🥐': 'CROISSANT',
            '🌽': 'CORN',
            '🥕': 'CARROT',
            '🥬': 'LEAFY GREEN',
            '🥦': 'BROCCOLI',
            '🧄': 'GARLIC',
            '🧅': 'ONION',
            '🍄': 'MUSHROOM',
            '🥜': 'PEANUTS',
            '🌰': 'CHESTNUT',
            '🍞': 'BREAD',
            '🧀': 'CHEESE',
            '🥚': 'EGG',
            '🥓': 'BACON',
            '🥞': 'PANCAKES',
            '🧇': 'WAFFLE',
            '🥐': 'CROISSANT',
            '🍳': 'COOKING',
            '🥫': 'CANNED FOOD',
            '🍿': 'POPCORN',
            '🧂': 'SALT',
            '🥤': 'CUP WITH STRAW',
            '🧃': 'JUICE BOX',
            '☕': 'COFFEE',
            '🫖': 'TEAPOT',
            '🍵': 'TEA',
            '🥛': 'MILK',
            '🍺': 'BEER',
            '🍷': 'WINE',
            '🥂': 'CHAMPAGNE',
            '🍹': 'TROPICAL DRINK',
            '🧊': 'ICE CUBE',
            '🍨': 'ICE CREAM',
            '🍧': 'SHAVED ICE',
            '🍦': 'SOFT ICE CREAM',
            '🍰': 'SHORTCAKE',
            '🎂': 'BIRTHDAY CAKE',
            '🧁': 'CUPCAKE',
            '🥧': 'PIE',
            '🍫': 'CHOCOLATE BAR',
            '🍭': 'LOLLIPOP',
            '🍬': 'CANDY',
            '🍩': 'DOUGHNUT',
            '🍪': 'COOKIE',
        }
        
        # If it's a Discord custom emoji (format like <:name:id>)
        if emoji.startswith('<') and emoji.endswith('>'):
            parts = emoji[1:-1].split(':')
            if len(parts) >= 2:
                return parts[1].upper()  # Return the name part in uppercase
        
        # If it's a regular emoji, look up its name
        if emoji in emoji_names:
            return emoji_names[emoji]

        # If we don't recognize it, return a generic UNKNOWN label (do not return the raw glyph)
        return "UNKNOWN"

    @commands.command(name="top_emojis")
    async def show_top_emojis(self, ctx, user: discord.User = None, days: int = 30):
        """Show the top 10 most used emojis in meal responses."""
        prop = DiscordTheme.apply_discord_theme()
        conn = None
        cursor = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Calculate date range
            end_date = datetime.now(self.california_tz)
            start_date = end_date - timedelta(days=days)

            # Fetch emoji statistics
            if user:
                cursor.execute("""
                    SELECT emoji, COUNT(*) as count
                    FROM meals
                    WHERE user_id = ? AND timestamp >= ? 
                    AND emoji IS NOT NULL AND emoji != ''
                    GROUP BY emoji
                    ORDER BY count DESC
                    LIMIT 10
                """, (user.id, start_date.strftime("%Y-%m-%d")))
            else:
                cursor.execute("""
                    SELECT emoji, COUNT(*) as count
                    FROM meals
                    WHERE timestamp >= ?
                    AND emoji IS NOT NULL AND emoji != ''
                    GROUP BY emoji
                    ORDER BY count DESC
                    LIMIT 10
                """, (start_date.strftime("%Y-%m-%d"),))
            
            stats = cursor.fetchall()

            if not stats:
                await ctx.send(f"No emoji data available for the last {days} days.")
                return

            # Create figure with dark theme
            plt.figure(figsize=(12, 8))
            
            # Extract data
            emojis = [stat[0] for stat in stats]
            counts = [stat[1] for stat in stats]
            
            # Create position array for bars
            y_pos = np.arange(len(emojis))
            
            # Plot horizontal bars
            bars = plt.barh(y_pos, counts, color='#5865F2')  # Discord blurple color
            
            # Customize the plot
            plt.title(f"Top 10 Meal Reactions {'for ' + user.name if user else '(All Users)'}\n{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}", 
                     fontproperties=prop, pad=20)
            plt.xlabel("Times Used", fontproperties=prop)
            
            # Set y-axis labels
            ax = plt.gca()
            ax.set_yticks(y_pos)
            
            # Create labels by using only the readable name (no emoji glyphs)
            labels_text = [sanitize_text(self._get_emoji_name(e)) for e in emojis]

            ax.set_yticks(y_pos)
            ax.set_yticklabels(labels_text, fontproperties=prop)
            
            # Add count labels on the bars
            for i, v in enumerate(counts):
                plt.text(v + 0.1, i, f' {v}', va='center', fontproperties=prop)

            # Adjust layout
            plt.subplots_adjust(left=0.3)  # More room for labels
            plt.margins(x=0.2)  # Add padding on the right
            
            # Set background color
            ax.set_facecolor("#2C2F33")
            plt.gcf().patch.set_facecolor("#2C2F33")
            
            # Save with proper theme and high DPI
            file_path = "cogs/graphs/emoji_stats.png"
            if os.path.exists(file_path):
                os.remove(file_path)
            plt.savefig(file_path, bbox_inches="tight", dpi=300, facecolor="#2C2F33", edgecolor="none", pad_inches=0.3)
            plt.close()

            await ctx.send(file=discord.File(file_path))
            os.remove(file_path)

        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")
            print(f"Error details: {str(e)}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def _set_emoji_font(self, ax):
        """Apply emoji font to an axis's labels"""
        labels = [label.get_text() for label in ax.get_yticklabels()]
        ax.set_yticklabels(labels, fontproperties=self.emoji_prop, fontsize=20)  # Increased font size for emojis

    @commands.command(name="meal_graph")
    async def generate_meal_graph(self, ctx, user: discord.User = None, days: int = 30):
        """Generate meal statistics visualizations.
        
        Args:
            user (discord.User, optional): User to filter stats for
            days (int, optional): Number of days to analyze (default: 30)
        """
        prop = DiscordTheme.apply_discord_theme()
        conn = None
        cursor = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Calculate date range
            end_date = datetime.now(self.california_tz)
            start_date = end_date - timedelta(days=days)

            # Fetch meal statistics with time data
            if user:
                cursor.execute("""
                    SELECT meal, status, emoji, timestamp, COUNT(*) as count
                    FROM meals
                    WHERE user_id = ? AND timestamp >= ?
                    GROUP BY meal, status, emoji, DATE(timestamp)
                    ORDER BY timestamp
                """, (user.id, start_date.strftime("%Y-%m-%d")))
            else:
                cursor.execute("""
                    SELECT meal, status, emoji, timestamp, COUNT(*) as count
                    FROM meals
                    WHERE timestamp >= ?
                    GROUP BY meal, status, emoji, DATE(timestamp)
                    ORDER BY timestamp
                """, (start_date.strftime("%Y-%m-%d"),))
            
            stats = cursor.fetchall()

            if not stats:
                await ctx.send(f"No meal data available for the last {days} days.")
                return

            # Create a figure with multiple subplots
            fig = plt.figure(figsize=(15, 10))
            fig.suptitle(f"Meal Statistics {'for ' + user.name if user else '(All Users)'}\n{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}", 
                        fontproperties=prop, y=0.95)

            # 1. Bar chart of meal choices (top left)
            ax1 = plt.subplot(221)
            self._plot_meal_distribution(stats, ax1, prop)

            # 2. Pie chart of meal percentages (top right)
            ax2 = plt.subplot(222)
            self._plot_meal_percentages(stats, ax2, prop)

            # 3. Time series of meal choices (bottom)
            ax3 = plt.subplot(212)
            self._plot_time_series(stats, ax3, prop)

            plt.tight_layout()
            
            # Save and send the graph
            file_path = "cogs/graphs/meal_stats.png"
            if os.path.exists(file_path):
                os.remove(file_path)
            plt.savefig(file_path, bbox_inches="tight", dpi=300)
            plt.close()

            await ctx.send(file=discord.File(file_path))
            os.remove(file_path)

        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def _plot_meal_distribution(self, stats, ax, prop):
        """Plot bar chart of meal choices."""
        meal_counts = {}
        for meal, _, emoji, _, count in stats:
            if meal not in meal_counts:
                meal_counts[meal] = 0
            meal_counts[meal] += count

        meals = list(meal_counts.keys())
        counts = list(meal_counts.values())
        
        bars = ax.bar(meals, counts)
        ax.set_title("Meal Distribution", fontproperties=prop)
        ax.set_xlabel("Meals", fontproperties=prop)
        ax.set_ylabel("Count", fontproperties=prop)
        plt.setp(ax.get_xticklabels(), rotation=45, ha='right')

        # Add value labels on top of bars
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{int(height)}', ha='center', va='bottom')

        # Set emoji font for labels that contain emojis
        self._set_emoji_font(ax)

    def _plot_meal_percentages(self, stats, ax, prop):
        """Plot pie chart of meal percentages."""
        meal_counts = {}
        for meal, _, emoji, _, count in stats:
            if meal not in meal_counts:
                meal_counts[meal] = 0
            meal_counts[meal] += count

        meals = list(meal_counts.keys())
        counts = list(meal_counts.values())
        total = sum(counts)
        percentages = [count/total * 100 for count in counts]

        ax.pie(percentages, labels=[f"{meal}\n({percent:.1f}%)" for meal, percent in zip(meals, percentages)],
               autopct='', startangle=90)
        ax.set_title("Meal Distribution (%)", fontproperties=prop)

    def _plot_time_series(self, stats, ax, prop):
        """Plot time series of meal choices."""
        meal_time_series = {}
        dates = sorted(set(datetime.strptime(stat[3].split()[0], "%Y-%m-%d").date() 
                         for stat in stats))

        for meal, _, _, timestamp, count in stats:
            date = datetime.strptime(timestamp.split()[0], "%Y-%m-%d").date()
            if meal not in meal_time_series:
                meal_time_series[meal] = {date: 0 for date in dates}
            meal_time_series[meal][date] += count

        for meal, data in meal_time_series.items():
            dates_list = list(data.keys())
            counts_list = list(data.values())
            ax.plot(dates_list, counts_list, marker='o', label=meal, linewidth=2, markersize=4)

        ax.set_title("Meal Choices Over Time", fontproperties=prop)
        ax.set_xlabel("Date", fontproperties=prop)
        ax.set_ylabel("Count", fontproperties=prop)
        ax.legend(prop=prop)
        plt.setp(ax.get_xticklabels(), rotation=45, ha='right')

async def setup(bot):
    await bot.add_cog(MealStatsGraph(bot))
