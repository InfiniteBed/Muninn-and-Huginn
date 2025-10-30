import discord  # type:ignore
from discord import app_commands # type:ignore
import discord.ext.commands as commands  # type:ignore
import sqlite3

class Personality(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.get_cog("Database")
        self.input = bot.get_cog("UserInput")
        self.user = bot.get_cog("User")

    @commands.hybrid_command(name="create_personality", aliases=["add_personality", "ap"])
    @app_commands.describe(name="The name of the personality")
    async def create_personality(self, ctx: commands.Context, name: str = None, description: str = None):
        if await self.user.deny_unregistered_user(ctx): return
        
        if name is None:
            name = await self.input.prompt(ctx, "What is the name of the personality you want to create?")
            if not name:
                await ctx.send("Personality creation cancelled.")
                return

        # return only alphanumeric and space characters
        name = ''.join(c for c in name if c.isalnum() or c.isspace()).strip()

        embed = discord.Embed(
            title=f"Personality *{name}* was successfully created!",
            color=discord.Color.green()
        )
        
        await self.db.post("PersonalityType", {"Name": name.title(), "Description": description})
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="list_personalities", aliases=["lp"])
    async def list_personalities(self, ctx: commands.Context): 
        personalities = await self.db.get("PersonalityType")
        if not personalities:
            await ctx.send("No personalities found.")
            return

        description = "\n".join([f"{p['Id']}. **{p['Name']}**{f': {p['Description']}' if p['Description'] else ''}" for p in personalities])
        embed = discord.Embed(title="Available Personalities", description=description, color=discord.Color.blue())
        await ctx.send(embed=embed)

async def setup(bot):
    personality = Personality(bot)
    await bot.add_cog(personality)