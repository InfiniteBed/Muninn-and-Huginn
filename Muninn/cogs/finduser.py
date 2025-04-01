import discord
from discord.ext import commands
from fuzzywuzzy import process

class Search(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def find_user(self, search: str, guild: discord.Guild):
        """
        Finds the user in the guild whose name or nickname is closest to the search string.
        """
        if not guild:
            return None

        members = guild.members
        names = {member: member.display_name for member in members}

        # Use fuzzy matching to find the closest match
        best_match = process.extractOne(search, names.values())

        if best_match:
            closest_name = best_match[0]
            user = next(user for user, name in names.items() if name == closest_name)
            return user
        return None

async def setup(bot):
    await bot.add_cog(Search(bot))
