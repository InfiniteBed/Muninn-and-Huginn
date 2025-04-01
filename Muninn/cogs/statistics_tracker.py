import discord
from discord.ext import commands
import sqlite3
import time
from datetime import datetime, timedelta
import random
import matplotlib.pyplot as plt
import pytz
import emoji
import numpy as np
import regex as re

# Define an emoji regex pattern to match both traditional emojis and custom Discord emojis
EMOJI_PATTERN = re.compile(
    r'<a?:\w+:\d{18}>|\p{Extended_Pictographic}',
    re.UNICODE
)

def convert_to_california_time(timestamp: datetime) -> datetime:
    if timestamp is None:
        raise ValueError("Timestamp cannot be None.")
    if timestamp.tzinfo is None:
        timestamp = pytz.utc.localize(timestamp)
    california_zone = pytz.timezone('America/Los_Angeles')
    california_time = timestamp.astimezone(california_zone)
    return california_time

def parse_timestamp(timestamp_str) -> datetime:
    """Convert timestamp string or int to a datetime object."""
    if not timestamp_str:
        return None

    if isinstance(timestamp_str, int):
        return datetime.fromtimestamp(timestamp_str)

    formats = [
        '%Y-%m-%d %H:%M:%S.%f+00:00',
        '%Y-%m-%d %H:%M:%S+00:00',
    ]

    for fmt in formats:
        try:
            return datetime.strptime(timestamp_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Time data '{timestamp_str}' does not match any of the expected formats.")

class StatsTracker(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.conn = sqlite3.connect("discord.db")
        self.cursor = self.conn.cursor()
    
        """Create necessary tables if they do not exist."""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_activity (
                guild_id INTEGER,
                user_id INTEGER,
                message_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                timestamp TIMESTAMP,
                message_length INTEGER,
                emoji_count INTEGER,
                word_count INTEGER,
                has_media BOOLEAN,
                attachment_count INTEGER,
                mentioned_users TEXT,
                mentioned_roles TEXT
            )
        """)

    def close(self):
        """Close the database connection."""
        self.conn.close()

    async def cog_unload(self):
        self.close()

    async def send_status_report(self, ctx, channel_name, total_messages, missing_data_messages):
        """Send a status update to the channel."""
        percentage_missing = (missing_data_messages / total_messages) * 100 if total_messages else 0
        color = self.calculate_progress_color(percentage_missing)
        
        embed = discord.Embed(
            title=f"Status for {channel_name}",
            description=(
                f"Total messages processed: {total_messages}\n"
                f"Messages with missing data: {missing_data_messages}\n"
                f"Percentage of missing data: {percentage_missing:.2f}%"
            ),
            color=color
        )
        await ctx.send(embed=embed)

    async def import_messages(self, ctx):
        """Import messages from all channels and fill missing data."""
        start_time = time.time()
        channels = ctx.guild.text_channels
        total_messages = 0
        channel_progress = {}

        for channel in channels:
            total_messages_in_channel = 0
            missing_data_messages = 0
            processed_messages = 0

            async for message in channel.history(limit=None):
                if message.author.bot:  # Skip bot messages during import
                    continue
                if message.content.startswith("!"):
                    continue

                print(f"Processing message {message.id} from {message.author}: {message.content}")
                total_messages_in_channel += 1
                processed_messages += 1

                if processed_messages % 2500 == 0:
                    await self.send_status_report(ctx, channel.name, total_messages_in_channel, missing_data_messages)

                self.cursor.execute("SELECT COUNT(*) FROM user_activity WHERE message_id = ?", (message.id,))
                if self.cursor.fetchone()[0] > 0:
                    continue

                timestamp = message.created_at
                # Convert to California time
                timestamp = convert_to_california_time(timestamp)

                message_length = len(message.content) if message.content else 0

                # Updated emoji count using regex
                unicode_emoji_pattern = re.compile(r"[\U0001F300-\U0001F6FF\U0001F900-\U0001F9FF\U0001F1E0-\U0001F1FF]+", flags=re.UNICODE)
                custom_emoji_pattern = re.compile(r"<a?:\w+:\d+>")
                
                unicode_emojis = unicode_emoji_pattern.findall(message.content)
                custom_emojis = custom_emoji_pattern.findall(message.content)
                
                emoji_count = len(unicode_emojis) + len(custom_emojis)

                word_count = len(message.content.split()) if message.content else 0
                has_media = bool(message.attachments)
                attachment_count = len(message.attachments)
                mentioned_users = ', '.join(str(user.id) for user in message.mentions) if message.mentions else ''
                mentioned_roles = ', '.join(str(role.id) for role in message.role_mentions) if message.role_mentions else ''

                if timestamp and (message_length > 0 or has_media):
                    missing_data_messages += 1
                    self.cursor.execute("""
                        INSERT INTO user_activity (guild_id, user_id, message_id, channel_id, timestamp, message_length, emoji_count,
                        word_count, has_media, attachment_count, mentioned_users, mentioned_roles)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        message.guild.id, message.author.id, message.id, message.channel.id, timestamp, message_length, emoji_count,
                        word_count, has_media, attachment_count, mentioned_users, mentioned_roles
                    ))
                self.conn.commit()

            await self.send_status_report(ctx, channel.name, total_messages_in_channel, missing_data_messages)

            channel_progress[channel.name] = {
                "total": total_messages_in_channel,
                "missing": missing_data_messages,
                "percentage": (missing_data_messages / total_messages_in_channel) * 100 if total_messages_in_channel else 0
            }

        elapsed_time = time.time() - start_time
        await self.report_progress(ctx, channel_progress, elapsed_time)

    async def report_progress(self, ctx, channel_progress, elapsed_time):
        """Send progress reports for each channel, including time elapsed."""
        elapsed_minutes, elapsed_seconds = divmod(elapsed_time, 60)
        elapsed_time_message = f"Total time elapsed: {int(elapsed_minutes)}m {int(elapsed_seconds)}s\n"

        for channel_name, progress in channel_progress.items():
            color = self.calculate_progress_color(progress['percentage'])
            embed = discord.Embed(
                title=f"Progress for {channel_name}",
                description=(
                    f"Total messages: {progress['total']}\n"
                    f"Messages with missing data: {progress['missing']}\n"
                    f"Percentage of missing data: {progress['percentage']:.2f}%"
                ),
                color=color
            )
            await ctx.send(embed=embed)

        # Send the elapsed time message in an embed
        embed = discord.Embed(
            title="Progress Report Completed",
            description=elapsed_time_message,
            color=0x00FF00  # Bright green
        )
        await ctx.send(embed=embed)

    def calculate_progress_color(self, percentage):
        """Calculate the embed color based on the progress percentage."""
        if percentage <= 100:
            red = 49 + int((0 - 49) * (percentage / 100))  # Starts from Discord background color
            green = 51 + int((255 - 51) * (percentage / 100))  # Ends at bright green
            blue = 56 + int((0 - 56) * (percentage / 100))  # Ends at bright green
            return (red << 16) + (green << 8) + blue
        return 0x00FF00  # If somehow percentage goes over 100, return bright green directly

    @commands.command()
    async def import_data(self, ctx):
        """Command to start the import process."""
        await self.import_messages(ctx)

    @commands.Cog.listener()
    async def on_message(self, message):
        """Track messages sent by users."""
        conn = sqlite3.connect("discord.db")
        cursor = conn.cursor()

        if message.author.bot:
            return

        user_id = message.author.id
        message_id = message.id
        channel_id = message.channel.id
        timestamp = message.created_at

        # Convert timestamp to UTC and then to California time
        timestamp = convert_to_california_time(timestamp)

        message_length = len(message.content) if message.content else 0

        # Updated emoji count using regex
        unicode_emoji_pattern = re.compile(r"[\U0001F300-\U0001F6FF\U0001F900-\U0001F9FF\U0001F1E0-\U0001F1FF]+", flags=re.UNICODE)
        custom_emoji_pattern = re.compile(r"<a?:\w+:\d+>")
        
        unicode_emojis = unicode_emoji_pattern.findall(message.content)
        custom_emojis = custom_emoji_pattern.findall(message.content)
        
        emoji_count = len(unicode_emojis) + len(custom_emojis)
        
        word_count = len(message.content.split()) if message.content else 0
        has_media = bool(message.attachments)
        attachment_count = len(message.attachments)
        mentioned_users = ', '.join(str(user.id) for user in message.mentions) if message.mentions else ''
        mentioned_roles = ', '.join(str(role.id) for role in message.role_mentions) if message.role_mentions else ''

        cursor.execute("""
            INSERT INTO user_activity (guild_id, user_id, message_id, channel_id, timestamp, message_length, emoji_count, 
            word_count, has_media, attachment_count, mentioned_users, mentioned_roles)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (message.guild.id, user_id, message_id, channel_id, timestamp, message_length, emoji_count, word_count, 
              has_media, attachment_count, mentioned_users, mentioned_roles))

        conn.commit()
        conn.close()

async def setup(bot):
    await bot.add_cog(StatsTracker(bot))
