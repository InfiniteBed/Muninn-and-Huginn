import discord # type: ignore
import sqlite3
import time
from collections import defaultdict
from discord.ext import commands # type: ignore
import os
import subprocess
import yaml
import random
import re
import asyncio
from discord.utils import get # type: ignore
import configparser  # Add this import for reading the token from a config file

# Load message rewards from YAML file
def load_yaml():
    try:
        with open("responses.yaml", "r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
    except FileNotFoundError:
        # Fallback to JSON if YAML doesn't exist
        import json
        with open("responses.json", "r") as file:
            data = json.load(file)
    return data["message_rewards"], data["thank_you_responses"]

message_rewards, thank_you_data = load_yaml()
normal_thank_you_responses = thank_you_data["normal"]
excessive_thank_you_responses = thank_you_data["excessive"]

# Connect to SQLite database
con = sqlite3.connect("/usr/src/bot/discord.db")
cur = con.cursor()

# Spam protection settings
MESSAGE_COOLDOWN = 5  # seconds
SPAM_PENALTY = 10      # message count penalty for spamming
MAX_MESSAGES_WITHIN_COOLDOWN = 4
# GIF spam protection settings
GIF_COOLDOWN = 86400  # 24 hours in seconds
MAX_GIFS_IN_PERIOD = 3  # Max GIFs per user in 24 hours

recent_messages = defaultdict(list)
user_gif_timestamps = defaultdict(list)
thank_timestamps = defaultdict(list)

intents = discord.Intents.all()

bot = commands.Bot(command_prefix='!', intents=intents)
bot.owner_id = 867261583871836161

# Load bot token from config file
config = configparser.ConfigParser()
config.read("config.ini")
BOT_TOKEN = config["Muninn"]["BotToken"]

async def load_cogs():
    for foldername, subfolders, files in os.walk("./cogs"):
        for filename in files:
            if filename.endswith(".py"):
                if filename == "profile_setup.py" and relative_path == ".":
                    # Skip legacy duplicate; RPG version provides the cog
                    continue
                relative_path = os.path.relpath(foldername, "./cogs")
                if relative_path == ".":
                    cog_path = f"cogs.{filename[:-3]}"
                else:
                    cog_path = f"cogs.{relative_path.replace(os.sep, '.')}" + f".{filename[:-3]}"

                try:
                    await bot.load_extension(cog_path)
                    print(f"Loaded {filename}")
                except Exception as e:
                    print(f"Failed to load {filename}: {e}")
@bot.event
async def on_ready():
    print(f'Logged on as {bot.user}!')

async def main():
    await load_cogs()
    await asyncio.gather(bot.start(BOT_TOKEN))  # Use the loaded token here

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    user_id = message.author.id
    guild_id = message.guild.id
    nick = message.author.nick if message.author.nick else message.author.name

    current_time = time.time()
    recent_messages[user_id].append(current_time)

    # Create unique table for each guild if not exists
    table_name = f"discord_{guild_id}"
    cur.execute(f'''CREATE TABLE IF NOT EXISTS {table_name} (
                    id INTEGER PRIMARY KEY,
                    friendly_name TEXT,
                    message_count INTEGER
                )''')

    # Remove messages older than the cooldown window
    recent_messages[user_id] = [t for t in recent_messages[user_id] if current_time - t < MESSAGE_COOLDOWN]

    if len(recent_messages[user_id]) > MAX_MESSAGES_WITHIN_COOLDOWN:
        try:
            cur.execute(f'SELECT message_count FROM {table_name} WHERE id = ?', (user_id,))
            result = cur.fetchone()
            if result:
                message_count = max(0, result[0] - SPAM_PENALTY)
                cur.execute(f'UPDATE {table_name} SET message_count = ? WHERE id = ?', (message_count, user_id))
                con.commit()
                await message.channel.send(f"{nick}, please stop spamming! Penalty applied.")
        except Exception as e:
            print(f"Spam Detection Error: {e}")
        return

    # Message Counter
    if not message.content.startswith("!"):
        try:
            member = message.guild.get_member(user_id) or next((m for m in message.guild.members if m.id == user_id), None)
            current_nick = member.nick if member and member.nick else message.author.name

            # Store message length, excluding emojis and punctuation
            message_length = len(re.sub(r"[^\w\s]", "", message.content))  # Remove punctuation
            message_length = len(re.sub(r"[^\x00-\x7F]+", "", message.content))  # Remove emojis

            cur.execute(f'SELECT friendly_name, message_count FROM {table_name} WHERE id = ?', (user_id,))
            result = cur.fetchone()

            if result is None:
                cur.execute(f'INSERT INTO {table_name} (id, friendly_name, message_count) VALUES (?, ?, ?)', (user_id, current_nick, 1))
            else:
                stored_nick, message_count = result
                if current_nick != stored_nick:
                    cur.execute(f'UPDATE {table_name} SET friendly_name = ? WHERE id = ?', (current_nick, user_id))
                message_count += 1
                cur.execute(f'UPDATE {table_name} SET message_count = ? WHERE id = ?', (message_count, user_id))

                if str(message_count) in message_rewards:
                    reward = message_rewards[str(message_count)].format(nick=nick, message=message.content)
                    time.sleep(2)
                    await message.channel.send(reward)

            con.commit()
        except Exception as e:
            print(f"Message Counter Error: {e}")

    # Handle other events like thank you messages, GIFs, etc.
    for attachment in message.attachments:
        if 'tenor' in attachment.url.lower():
            await message.channel.send("That's a gif!")

            user_gif_timestamps[user_id].append(current_time)
            user_gif_timestamps[user_id] = [t for t in user_gif_timestamps[user_id] if current_time - t < GIF_COOLDOWN]

            if len(user_gif_timestamps[user_id]) > MAX_GIFS_IN_PERIOD:
                try:
                    nick = message.author.display_name
                    await message.channel.send(f"{nick}, you've sent too many GIFs in the last 24 hours. Please slow down!")
                except Exception as e:
                    print(f"Error sending warning: {e}")

    # Track thank you messages
    if "thank" in message.content.lower() and bot.user in message.mentions:
        thank_timestamps[user_id].append(current_time)
        thank_timestamps[user_id] = [t for t in thank_timestamps[user_id] if current_time - t < GIF_COOLDOWN]

        if len(thank_timestamps[user_id]) == 3:
            response = random.choice(excessive_thank_you_responses)
        elif len(thank_timestamps[user_id]) > 3:
            response = random.choice(excessive_thank_you_responses)
        else:
            response = random.choice(normal_thank_you_responses)

        await message.channel.send(response.format(user=message.author.mention))

    await bot.process_commands(message)
    if message.content.startswith(bot.command_prefix):
        print(f"Command executed: {message.content} by {message.author} in {message.guild.name if message.guild else 'DM'}")

asyncio.run(main())
