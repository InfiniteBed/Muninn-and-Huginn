import datetime
import json
import random
import sqlite3
import time

import pytz # type:ignore

import discord  # type: ignore
from discord.ext import commands, tasks  # type: ignore

conn = sqlite3.connect("huginn.db")
c = conn.cursor()

GUILD_BLACKLIST = [1198144553383895150]

# Define Los Angeles timezone
la_timezone = pytz.timezone("America/Los_Angeles")

# Get current date to handle daylight saving time properly
def get_time(hour, minute=0):
    now = datetime.datetime.now(la_timezone)
    return la_timezone.localize(datetime.datetime(now.year, now.month, now.day, hour, minute))

# Times set in Los Angeles timezone, adjusted for DST
times = [
    get_time(9, 30).timetz(),
    get_time(13).timetz(),
    get_time(16).timetz(),
]

class random_prompt(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.my_task.start()

    def cog_unload(self):
        self.my_task.cancel()

    @tasks.loop(time=times)
    async def my_task(self):
        current_time = time.time()  # Get the current timestamp
        print(f"Current time: {current_time}")

        for guild in self.bot.guilds:
            try:
                print(f"Checking guild: {guild.name} (ID: {guild.id})")
                if guild.id in GUILD_BLACKLIST:
                    print(f"Guild {guild.name} is blacklisted, skipping.")
                    continue

                # Check if the last message was sent more than 30 minutes ago
                c.execute("SELECT last_message_time FROM guild_last_messages WHERE guild_id = ?", (guild.id,))
                last_message_time = c.fetchone()
                if last_message_time:
                    last_message = float(last_message_time[0])  # Ensure it's a float
                    time_diff = current_time - last_message
                    print(f"Time since last message in {guild.name}: {time_diff} seconds")
                    if time_diff < 600:  # 600 seconds = 10 minutes
                        print(f"Last message in {guild.name} was less than 10 minutes ago, skipping.")
                        continue

                # Pick a random prompt
                prompt_data = random.choice(self.bot.data.get("prompts", []))
                if not prompt_data:
                    print("No prompts available in responses.json")
                    continue

                prompt_text = prompt_data.get("text", "No prompt available")
                contributor = prompt_data.get("contributor", "Anonymous")

                print(f"Selected prompt for {guild.name}: {prompt_text}")

                # Send the prompt as an embed
                embed = discord.Embed(title=prompt_text, color=discord.Color.blue())
                embed.set_footer(text=f"Random Prompt | Suggested by: {contributor}")
                general_channel = discord.utils.get(guild.text_channels, name='general')
                if general_channel:
                    print(f"Sending prompt to {guild.name} in #general")
                    await general_channel.send(embed=embed)
                else:
                    print(f"No #general channel found in {guild.name}")

                # Update the last message time
                c.execute("REPLACE INTO guild_last_messages (guild_id, last_message_time) VALUES (?, ?)",
                          (guild.id, current_time))
                conn.commit()
                print(f"Updated last message time for {guild.name}")

            except sqlite3.DatabaseError as db_err:
                print(f"Database error for guild {guild.name}: {db_err}")
            except discord.DiscordException as discord_err:
                print(f"Discord API error for guild {guild.name}: {discord_err}")
            except Exception as e:
                print(f"Unexpected error for guild {guild.name}: {e}")

async def setup(bot):
    await bot.add_cog(random_prompt(bot))
