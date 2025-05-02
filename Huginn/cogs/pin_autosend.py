import discord # type: ignore
import random
import sqlite3
from discord.ext import commands, tasks # type: ignore
from discord.utils import get # type: ignore
from PIL import Image # type: ignore
import requests # type: ignore
from io import BytesIO
import pytz
import datetime

la_timezone = pytz.timezone("America/Los_Angeles")

def get_time(hour, minute=0):
    now = datetime.datetime.now(la_timezone)
    return la_timezone.localize(datetime.datetime(now.year, now.month, now.day, hour, minute))

times = [
    get_time(6).timetz(),
    get_time(9).timetz(),
    get_time(12).timetz(),
    get_time(15).timetz(),
    get_time(18).timetz(),
    get_time(21).timetz(),
    get_time(0).timetz(),
]

class AutoPins(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "huginn.db"
        self.first_run = True
    
        # Stop the loop if it is already running to prevent multiple instances
        if self.pinned_message_task.is_running():
            self.pinned_message_task.cancel()

        self.pinned_message_task.change_interval(hours=3)
        self.pinned_message_task.start()
    
    def cog_unload(self):
        """Ensure the loop is properly canceled when the cog is unloaded."""
        self.pinned_message_task.cancel()
        
    @tasks.loop(time=times)
    async def pinned_message_task(self):
        if self.first_run:
            self.first_run = False
            return
        await self.send_random_pinned_message()
    
    @commands.command()
    async def test_pin(self, ctx):
        """Manually trigger the pinned message function."""
        await self.send_random_pinned_message()
        await ctx.send("Test pin message sent.")
        
    async def send_random_pinned_message(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for guild in self.bot.guilds:
                if guild.id == 1298762959614640148:
                    continue
                
                cursor.execute("SELECT message_id, channel_id FROM pinned_messages WHERE guild_id = ?", (guild.id,))
                pinned_entries = cursor.fetchall()
                if not pinned_entries:
                    continue

                message_id, channel_id = random.choice(pinned_entries)
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    continue

                try:
                    message = await channel.fetch_message(message_id)
                except discord.NotFound:
                    cursor.execute("DELETE FROM pinned_messages WHERE message_id = ?", (message_id,))
                    conn.commit()
                    continue

                avatar_url = str(message.author.display_avatar.url)

                try:
                    response = requests.get(avatar_url)
                    avatar_image = Image.open(BytesIO(response.content)).convert("RGB")
                    pixels = list(avatar_image.getdata())
                    avg_color = tuple(sum(c) // len(c) for c in zip(*pixels))
                    embed_color = discord.Color.from_rgb(*avg_color)
                except Exception:
                    embed_color = discord.Color.blue()

                message_url = f"https://discord.com/channels/{guild.id}/{channel.id}/{message_id}"
                embed = discord.Embed(title=message.content, color=embed_color, description=f"Random Pin | {message_url}")
                embed.set_thumbnail(url=avatar_url)
                embed.set_author(name=message.author.display_name)

                # Add the pin location (channel) to the footer with a link to jump to the pinned message

                # Check if there are any attachments
                if message.attachments:
                    # Add the first attachment (image, video, etc.) to the embed
                    attachment = message.attachments[0]
                    embed.set_image(url=attachment.url)

                general_channel = discord.utils.get(guild.text_channels, name='general')
                if general_channel:
                    await general_channel.send(embed=embed)



async def setup(bot):
    await bot.add_cog(AutoPins(bot))