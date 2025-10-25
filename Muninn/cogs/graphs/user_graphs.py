import discord
from discord.ext import commands


class UserGraphs(commands.Cog):
	"""Placeholder user graphs cog to satisfy loader expectations."""
	def __init__(self, bot):
		self.bot = bot

	@commands.command(name='user_graphs')
	async def user_graphs_cmd(self, ctx, user: discord.Member = None):
		"""Simple placeholder command that lists available user graphs."""
		target = user or ctx.author
		await ctx.send(f"User graphs are available for {target.display_name}. Use the graphs menu to explore.")


async def setup(bot):
	await bot.add_cog(UserGraphs(bot))
