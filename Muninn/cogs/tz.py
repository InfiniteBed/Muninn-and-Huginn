import pytz
from datetime import datetime
import discord
from discord.ext import commands

class TimezoneConverter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def convert_time(self, time_str: str):
        """
        Converts a time string in UTC to California time (PST/PDT).
        The `time_str` should be in the format 'YYYY-MM-DD HH:MM:SS' (24-hour format).
        """
        try:
            # Parse the time string to a datetime object (assuming it's in UTC)
            utc_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            utc_time = pytz.utc.localize(utc_time)

            # Convert the time to California (PST/PDT)
            california_tz = pytz.timezone('US/Pacific')
            california_time = utc_time.astimezone(california_tz)

            # Format the time to display
            formatted_time = california_time.strftime("%A, %B %d, %Y at %I:%M %p")
            return formatted_time
        
        except ValueError:
            return None  # Return None if there's an error in the format

async def setup(bot):
    await bot.add_cog(TimezoneConverter(bot))
