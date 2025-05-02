import discord
from discord.ext import commands
from discord.ext.commands import Context
import random

class RandomMessage(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command()
    async def random_message(self, ctx: Context):
        """Fetches a random message from the entire channel history."""
        await ctx.send("CAW! This'll take a bit, so come back when I have your message!")

        channel = ctx.channel
        messages = []

        async for message in channel.history(limit=None):
            # Ignore messages that are embeds
            if message.embeds:
                continue
            messages.append(message)

        if not messages:
            await ctx.channel.send("No messages found in the channel history.", ephemeral=True)
            return

        random_message = random.choice(messages)
        message_link = f"https://discord.com/channels/{ctx.guild.id}/{channel.id}/{random_message.id}"
        
        await ctx.channel.send(
            content=f"Random Message: {random_message.content}\n{message_link}",
        )

async def setup(bot):
    await bot.add_cog(RandomMessage(bot))