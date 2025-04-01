import discord
from discord.ext import commands
import time  # Used for tracking timestamps

class GifDetector(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.user_gif_data = {}  # {user_id: [(timestamp1, count), (timestamp2, count)]}
        self.TIME_LIMIT = 3 * 60 * 60  # 3 hours in seconds

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return  # Ignore bot messages

        user_id = message.author.id
        current_time = time.time()
        gif_found = False

        # Check for GIF in attachments
        for attachment in message.attachments:
            if attachment.filename.endswith(".gif"):
                gif_found = True
                break

        # Check for GIF in embeds (like Tenor or Giphy)
        for embed in message.embeds:
            if embed.type == "gifv" or (embed.url and embed.url.endswith(".gif")):
                gif_found = True
                break

        if gif_found:
            # Remove old GIFs from count (outside 3-hour window)
            if user_id in self.user_gif_data:
                self.user_gif_data[user_id] = [
                    (timestamp, count) for timestamp, count in self.user_gif_data[user_id]
                    if current_time - timestamp <= self.TIME_LIMIT
                ]

            # Add the new GIF entry
            if user_id not in self.user_gif_data:
                self.user_gif_data[user_id] = []

            self.user_gif_data[user_id].append((current_time, 1))

            # Calculate total GIFs in the last 3 hours
            total_gifs = sum(count for _, count in self.user_gif_data[user_id])

            if total_gifs > 2:
                try:
                    await message.delete()
                    await message.channel.send(f"{message.author.mention}, STOP SPAMMING GIFS! 😡")
                except discord.Forbidden:
                    await message.channel.send(f"{message.author.mention}, I can’t delete messages here, but seriously, chill with the GIFs! 😤")

    @commands.command()
    async def reset_gif_count(self, ctx, member: discord.Member = None):
        """Manually resets the GIF count for a user."""
        if member:
            self.user_gif_data.pop(member.id, None)
            await ctx.send(f"Reset GIF count for {member.mention}. They have another chance to spam... for now. 😈")
        else:
            self.user_gif_data.clear()
            await ctx.send("All GIF counts have been reset. Let the GIF flood begin! 🎉")

async def setup(bot):
    await bot.add_cog(GifDetector(bot))