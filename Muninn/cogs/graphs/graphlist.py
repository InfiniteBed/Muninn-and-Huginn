import discord
from discord.ext import commands

class GraphListCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='graphs')
    async def graphlist(self, ctx):
        # Create the embed
        embed = discord.Embed(
            title="Available Graphs",
            description="Here is a list of all available graphs you can view:",
            color=discord.Color.gold()
        )

        # Define a hardcoded list of graphs and descriptions
        graphs = {
            "User Activity `!g_user_activity_week (Optional: User)`": "Show a user's activity over the past 7 days.",
            "User Activity `!g_user_activity_month (Optional: User)`": "Show a user's activity over the past 30 days.",
            "User Rankings `!g_user_rankings`": "Show a guild's rankings by messages sent.",
            "User Rankings `!g_emoji_rankings`": "Show a guild's rankings by emojis used.",
            "Meal Statistics `!meal_graph`": "Show statistics of meals sent, chosen, and skipped.",
        }

        # Add each graph to the embed
        for graph, description in graphs.items():
            embed.add_field(name=graph, value=description, inline=False)

        # Send the embed
        await ctx.send(embed=embed)

# Set up the bot and load the cog
async def setup(bot):
    await bot.add_cog(GraphListCog(bot))