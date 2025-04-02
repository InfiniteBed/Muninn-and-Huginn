import discord
from discord.ext import commands
import sqlite3
from .utils import Utils  # Import Utils for avatar processing

class Rankings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.con = sqlite3.connect("/usr/src/bot/discord.db")
        self.cur = self.con.cursor()
        self.search = bot.get_cog('Search')

    @commands.command(name='rankings')
    async def rankings(self, ctx, user: str = None):
        if user is not None:
            user = await self.search.find_user(user, ctx.guild)
            if not user:
                await ctx.send("No user found.")
                return
            
        guild_id = ctx.guild.id
        table_name = f"discord_{guild_id}"
        try:
            if user:
                # Fetch specific user's ranking
                self.cur.execute(f'''
                    SELECT id, friendly_name, message_count 
                    FROM {table_name} 
                    WHERE id = ? 
                    ORDER BY message_count DESC
                ''', (user.id,))
                user_data = self.cur.fetchone()

                if not user_data:
                    await ctx.send(f"{user.display_name} has no ranking data.")
                    return

                friendly_name, message_count = user_data[1], user_data[2]
                utils_cog = self.bot.get_cog("Utils")
                embed_color, avatar_image, _ = await utils_cog.get_avatar_color_and_image(user)

                embed = discord.Embed(
                    title=f"{friendly_name}'s Ranking",
                    description=f"{friendly_name} has sent {message_count} messages!",
                    color=embed_color
                )
                embed.set_thumbnail(url=user.avatar.url)
                await ctx.send(embed=embed)
            else:
                # Fetch all rankings
                self.cur.execute(f'''
                    SELECT id, friendly_name, message_count 
                    FROM {table_name} 
                    ORDER BY message_count DESC
                ''')
                rankings = self.cur.fetchall()

                embed = discord.Embed(title=f"{ctx.guild.name} Rankings", color=discord.Color.blue())
                ranking_message = ""
                for rank, (user_id, friendly_name, message_count) in enumerate(rankings, start=1):
                    if rank == 1:
                        ranking_message += f"🥇 {friendly_name} - {message_count} messages\n"
                    elif rank == 2:
                        ranking_message += f"🥈 {friendly_name} - {message_count} messages\n"
                    elif rank == 3:
                        ranking_message += f"🥉 {friendly_name} - {message_count} messages\n"
                    else:
                        ranking_message += f"{rank}. {friendly_name} - {message_count} messages\n"

                embed.description = ranking_message
                await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"Error fetching rankings: {e}")

async def setup(bot):
    await bot.add_cog(Rankings(bot))