from discord.ext import commands # type:ignore

class Multifile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def multifile(self, ctx):
        await ctx.send("This tests a multi-file configuration for Huginn!")

async def setup(bot):
    await bot.add_cog(Multifile(bot))