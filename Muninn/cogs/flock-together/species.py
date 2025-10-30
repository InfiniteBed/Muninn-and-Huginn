import discord  # type:ignore
from discord import app_commands # type:ignore
import discord.ext.commands as commands  # type:ignore
import sqlite3

class Species(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.get_cog("Database")

    @commands.hybrid_command(name="get_all_species")  ## Retrieves all bird species from the database
    async def get_all_species(self, ctx):
        rows = await self.db.get("Species")
        await ctx.send(rows)

    @commands.hybrid_command(name="add_species")  ## Adds a new bird species to the database
    @app_commands.describe(name="The name of the species to add")
    async def add_species(self, ctx, name: str):
        species_data = {
            "Name": name.title(),
            "CreatedByUserId": ctx.author.id,
        }
        await self.db.post("Species", species_data)
        await ctx.send(f"Species '{name}' added successfully.")

async def setup(bot):
    species = Species(bot)
    await bot.add_cog(species)