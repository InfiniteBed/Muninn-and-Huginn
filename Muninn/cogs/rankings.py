import discord
from discord.ext import commands
import sqlite3

class Rankings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.con = sqlite3.connect("/usr/src/bot/discord.db")
        self.cur = self.con.cursor()

    @commands.command(name='rankings')
    async def rankings(self, ctx):
        guild_id = ctx.guild.id
        table_name = f"discord_{guild_id}"
        try:
            self.cur.execute(f'SELECT id, friendly_name, message_count FROM {table_name} ORDER BY message_count DESC')
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