import discord
from discord.ext import commands
import sqlite3

class LeaderboardsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "discord.db"

    @commands.command(name="meals")
    async def meals(self, ctx, user: discord.User = None):
        """Display leaderboards for emoji usage statistics, optionally filtered by a specific user."""
        conn = None
        cursor = None
        try:
            # Connect to the database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Fetch leaderboard data
            if user:
                cursor.execute("""
                    SELECT emoji, meal, COUNT(*) as count
                    FROM meals
                    WHERE user_id = ? AND emoji IS NOT NULL AND emoji != ''
                    GROUP BY emoji, meal
                    ORDER BY meal, count DESC
                """, (user.id,))
                stats = cursor.fetchall()
                title = f"Emoji Leaderboard for {user.name}"
            else:
                cursor.execute("""
                    SELECT emoji, meal, COUNT(*) as count
                    FROM meals
                    WHERE emoji IS NOT NULL AND emoji != ''
                    GROUP BY emoji, meal
                    ORDER BY meal, count DESC
                """)
                stats = cursor.fetchall()
                title = "Server-wide Emoji Leaderboard"

            if not stats:
                await ctx.send("No leaderboard data available.")
                return

            # Create the embed
            embed = discord.Embed(
                title=title,
                description="Here are the top emojis grouped by meal:",
                color=discord.Color.green()
            )

            # Group data by meal
            grouped_stats = {}
            for emoji, meal, count in stats:
                if meal not in grouped_stats:
                    grouped_stats[meal] = []
                grouped_stats[meal].append((emoji, count))

            # Add grouped data to the embed
            for meal, emojis in grouped_stats.items():
                emoji_list = "\n".join([f"{emoji}: {count} times" for emoji, count in emojis])
                embed.add_field(name=f"Meal: {meal}", value=emoji_list, inline=False)

            # Send the embed
            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

# Setup function to add the cog to the bot
async def setup(bot):
    await bot.add_cog(LeaderboardsCog(bot))
