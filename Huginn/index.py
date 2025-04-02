import discord # type: ignore
import json
import random
import sqlite3
import asyncio
from datetime import datetime
from discord.ext import commands, tasks # type: ignore
import os
from discord.utils import get # type: ignore
from PIL import Image # type: ignore
import requests # type: ignore
from io import BytesIO
import time
import pytz # type: ignore
import configparser  # Add this import for reading the token from a config file

# Define Los Angeles timezone
la_timezone = pytz.timezone("America/Los_Angeles")

# Load bot token from config file
config = configparser.ConfigParser()
config.read("config.ini")
TOKEN = config["Huginn"]["BotToken"]  # Updated to use the Huginn section

CHANCE_TO_RESPOND = 0.01  # 1% chance to respond
GUILD_BLACKLIST = [123456789012345678]  # Add blacklisted guild IDs here

# Database setup
conn = sqlite3.connect("huginn.db")
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS opt_in_users (
    user_id INTEGER PRIMARY KEY
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS guild_last_messages (
    guild_id INTEGER PRIMARY KEY,
    last_message_time INTEGER
)
""")
conn.commit()

# Create bot
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

async def main():
    await load_cogs()
    await bot.start(TOKEN)  # Use the loaded token here

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

async def load_cogs():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            try:
                await bot.load_extension(f"cogs.{filename[:-3]}")
                print(f"Loaded {filename}")
            except Exception as e:
                print(f"Failed to load {filename}: {e}")

@bot.event
async def on_message(message):
    current_time = time.time()
    c.execute("REPLACE INTO guild_last_messages (guild_id, last_message_time) VALUES (?, ?)",
              (message.guild.id, current_time))
    conn.commit()

    await bot.process_commands(message)
    if message.content.startswith(bot.command_prefix):
        print(f"Command executed: {message.content} by {message.author} in {message.guild.name if message.guild else 'DM'}")

asyncio.run(main())

@bot.event
async def on_disconnect():
    conn.close()
