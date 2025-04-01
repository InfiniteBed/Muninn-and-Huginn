import discord # type: ignore
from discord.ext import commands # type: ignore
import json

class DataLoader(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data = self.load_data()
        self.bot.data = self.data  # Store data in bot for other cogs to access

    def load_data(self):
        """Loads the JSON data from a file."""
        try:
            with open("responses.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}  # Return an empty dictionary if file is missing

    @commands.command(name="reload_data")
    async def reload_data(self, ctx):
        """Reloads the JSON data and updates the bot's shared data reference."""
        self.data = self.load_data()
        self.bot.data = self.data
        await ctx.send("Data reloaded successfully.")

async def setup(bot):
    await bot.add_cog(DataLoader(bot))
