import discord  # type:ignore
from discord import app_commands  # type:ignore
import discord.ext.commands as commands  # type:ignore

class Shinies(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.get_cog("Database")
        self.user = bot.get_cog("User")
        
    async def add_shinies(self, user_id: int, amount: int):
        user = await self.db.get_one("User", f"Id = {user_id}")
        new_shinies = (user['Shinies'] or 0) + amount
        await self.db.patch("User", {"Shinies": new_shinies}, user['Id'])
        print(f'Added {amount} shinies to user {user_id}. New total: {new_shinies}')
        return True

    @commands.hybrid_command(name="shinies", aliases=['sl', 'shinies_leaderboard']) ## Lists user's birds
    async def shinies(self, ctx: commands.Context):
        if await self.user.deny_unregistered_user(ctx): return

        server = await self.db.get_one("Server", f"DiscordServerId = {ctx.guild.id}")
        users = await self.db.get('User')
        server_shinies = sum(
            u['Shinies'] or 0 for u in users
            if u['ServerId'] == server['Id']
        ) if server else 0  
        
        description = ''
        for user in users:
            shinies = user['Shinies'] or 0
            description += f"**{user['Name']}**: `{shinies}` Shinies\n"
            
        embed = discord.Embed(
            title=f"{ctx.author.display_name}'s Birds",
            description=description,
            color=discord.Color.gold()
        )

        await ctx.send(embed=embed)    
    
async def setup(bot):
    shinies = Shinies(bot)
    await bot.add_cog(shinies)