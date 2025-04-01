import discord
from discord.ext import commands
import sqlite3
from discord.ext.commands import has_permissions

class StarLeaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_file = "discord.db"
        self.create_table()

    def create_table(self):
        # Create the table if it doesn't exist
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS stars (
            guild_id INTEGER,
            user_id INTEGER,
            stars INTEGER,
            PRIMARY KEY (guild_id, user_id)
        )''')
        conn.commit()
        conn.close()

    def get_leaderboard(self, guild_id):
        # Get the leaderboard of stars for the specified guild
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
        SELECT user_id, stars FROM stars
        WHERE guild_id = ?
        ORDER BY stars DESC
        LIMIT 10''', (guild_id,))
        leaderboard = cursor.fetchall()
        conn.close()
        return leaderboard

    @commands.command(name="stars")
    async def stars(self, ctx):
        """Shows the star leaderboard for the current guild."""
        leaderboard = self.get_leaderboard(ctx.guild.id)
        if not leaderboard:
            await ctx.send("No stars have been awarded yet.")
            return

        # Create the embed
        embed = discord.Embed(title="⭐️ Contribution Star Leaderboard", color=discord.Color.blue())
        
        # Build the leaderboard description with podium emojis
        leaderboard_text = ""
        for idx, (user_id, stars) in enumerate(leaderboard, 1):
            user = await self.bot.fetch_user(user_id)
            if idx == 1:
                leaderboard_text += f"🥇 {user.name} - **{stars}** stars\n"
            elif idx == 2:
                leaderboard_text += f"🥈 {user.name} - **{stars}** stars\n"
            elif idx == 3:
                leaderboard_text += f"🥉 {user.name} - **{stars}** stars\n"
            else:
                leaderboard_text += f"{idx}. {user.name} - **{stars}** stars\n"
        
        embed.description = leaderboard_text
        embed.set_footer(text='Want stars? Message !contribute to find out how! ')

        # Send the embed
        await ctx.send(embed=embed)

    @commands.command(name="star")
    @commands.is_owner()
    async def star(self, ctx, user: discord.User, stars: int):
        """Adds stars to a user. (Bot owner only)"""
        if stars < 1:
            await ctx.send("You must add at least 1 star.")
            return

        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Check if the user already has stars in the guild
        cursor.execute('''
        SELECT stars FROM stars
        WHERE guild_id = ? AND user_id = ?''', (ctx.guild.id, user.id))
        result = cursor.fetchone()

        if result:
            # Update the existing star count
            new_stars = result[0] + stars
            cursor.execute('''
            UPDATE stars
            SET stars = ?
            WHERE guild_id = ? AND user_id = ?''', (new_stars, ctx.guild.id, user.id))
        else:
            # Insert new user if they don't have any stars
            cursor.execute('''
            INSERT INTO stars (guild_id, user_id, stars)
            VALUES (?, ?, ?)''', (ctx.guild.id, user.id, stars))

        conn.commit()
        conn.close()
        await ctx.send(f"Added {stars} stars to {user.name}.")

async def setup(bot):
    await bot.add_cog(StarLeaderboard(bot))