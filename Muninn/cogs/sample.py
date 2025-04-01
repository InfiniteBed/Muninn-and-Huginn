from discord.ext import commands

class Multifile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.search = bot.get_cog('Search') # For User Find
        self.utils = bot.get_cog('Utils') # For Player's Icon
        self.stats_manager = self.bot.get_cog("StatsManager") # For Player Info
            # fetch_user_stats(user)
        self.list_manager = self.bot.get_cog("ListManager") # For Item and Expedition Info
            # get_expedition(expedition: str)
            # get_item(item: str)

    @commands.command()
    async def multifile(self, ctx):
        await ctx.send("This tests a multi-file configuration for Muninn!")

async def setup(bot):
    await bot.add_cog(Multifile(bot))