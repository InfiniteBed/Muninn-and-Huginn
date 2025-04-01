import discord
from discord.ext import commands
import sqlite3
import logging

logger = logging.getLogger(__name__)

c = sqlite3.connect("discord.db")
cursor = c.cursor()

class DebugProfile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='statistics')
    async def statistics(self, ctx, user: str = None):
        if user is None:
            user = ctx.author
        else:
            user = await self.bot.get_cog('Search').find_user(user, ctx.guild)
            if not user:
                await ctx.send("No profile found.")
                return

        guild_id = ctx.guild.id

        try:
            cursor.execute(f'SELECT * FROM user_activity WHERE guild_id = ? AND user_id = ?', (guild_id, user.id))
            user_data = cursor.fetchall()

            message_count = len(user_data)
            avg_word_count = round(sum([row[7] for row in user_data]) / message_count, 1) if message_count else 0
            avg_message_length = round(sum([row[5] for row in user_data]) / message_count, 1) if message_count else 0

            if user_data:
                user_id, friendly_name = user_data[0][1], user_data[0][2]  # Assuming user_id and friendly_name are at these indices

                embed = discord.Embed(title=f"Stats for {friendly_name}", color=discord.Color.green())
                embed.add_field(name="User ID", value=user.id, inline=False)
                embed.add_field(name="Friendly Name", value=friendly_name, inline=False)
                embed.add_field(name="Message Count", value=message_count, inline=False)
                embed.add_field(name="Avg. Message Length", value=avg_message_length, inline=False)
                embed.add_field(name="Avg. Words per Message", value=avg_word_count, inline=False)
                embed.add_field(name="Avg. Letters per Word", value=round(avg_message_length/avg_word_count, 1) if avg_word_count else 0, inline=False)
                embed.set_thumbnail(url=user.avatar.url)

                await ctx.send(embed=embed)
            else:
                await ctx.send(f"No stats found for user with ID {user.id}.")
        except Exception as e:
            logger.error(f"Error fetching user stats: {e}")
            await ctx.send(f"Error fetching user stats: {e}")

async def setup(bot):
    await bot.add_cog(DebugProfile(bot))
