import discord  # type:ignore
from discord import app_commands # type:ignore
import discord.ext.commands as commands  # type:ignore
import sqlite3

class User(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.get_cog("Database")
        
    async def deny_unregistered_user(self, ctx):
        user_id = ctx.author.id if hasattr(ctx, 'author') else ctx.user.id
        user = await self.db.get_one("User", f"DiscordUserId = {user_id}")
        if not user:
            if hasattr(ctx, 'send'):
                await ctx.send("You are not registered, please register with the `!create_bird` command first.")
            else:
                await ctx.response.send_message("You are not registered, please register with the `!create_bird` command first.", ephemeral=True)
            return True
        return False
        
    async def get_user_by_discord_id(self, discord_user_id: int):
        return await self.db.get_one("User", f"DiscordUserId = {discord_user_id}")

    @commands.hybrid_command(name="register") ## Registers self within Flock Together
    async def register(self, ctx: commands.Context):
        if await self.db.get("User", f"DiscordUserId = {ctx.author.id}"):
            await ctx.send("You are already registered in Flock Together!")
            return

        server = await self.db.get("Server", f"DiscordServerId = {ctx.guild.id}")
        
        user_data = {
            "DiscordUserId": ctx.author.id,
            "Name": ctx.author.nick or ctx.author.name,
            "ServerId": server['Id'] if server else None
        }
        
        await self.db.post("User", user_data)
        
        await ctx.send("You have been registered in Flock Together!")

async def setup(bot):
    user = User(bot)
    await bot.add_cog(user)