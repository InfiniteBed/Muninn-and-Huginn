import discord # type: ignore
import random
import yaml
import json
import os
import sqlite3
from discord.ext import commands, tasks # type: ignore
from discord import app_commands # type: ignore
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
    get_time(9).timetz(),
    get_time(15).timetz(),
    get_time(21).timetz(),
    get_time(0).timetz(),
]

class AutoPins(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "huginn.db"
        self.state_file = "data/pin_state.yaml"
        self.first_run = True
        self.guild_pin_indices = {}
        self.guild_seq_indices = {}  # Track sequential pin indices
        
        # Load existing pin indices or create new state file
        if os.path.exists(self.state_file):
            with open(self.state_file, 'r') as f:
                state = yaml.safe_load(f) or {}
                self.guild_pin_indices = state.get('regular_pins', {})
                self.guild_seq_indices = state.get('sequential_pins', {})
        else:
            # Create data directory if it doesn't exist
            os.makedirs('data', exist_ok=True)
            with open(self.state_file, 'w') as f:
                yaml.dump({'regular_pins': {}, 'sequential_pins': {}}, f)
    
        # Stop the loop if it is already running to prevent multiple instances
        if self.pinned_message_task.is_running():
            self.pinned_message_task.cancel()

        self.pinned_message_task.change_interval(hours=3)
        self.pinned_message_task.start()
    
    def save_state(self):
        """Save the current pin indices to the state file."""
        with open(self.state_file, 'w') as f:
            yaml.dump({
                'regular_pins': self.guild_pin_indices,
                'sequential_pins': self.guild_seq_indices
            }, f)

    def cog_unload(self):
        """Ensure the loop is properly canceled when the cog is unloaded."""
        self.save_state()
        self.pinned_message_task.cancel()
        
    @tasks.loop(time=times)
    async def pinned_message_task(self):
        if self.first_run:
            self.first_run = False
            return
        await self.send_random_pinned_message()
    
    @commands.hybrid_command(
        name="testpin",
        description="Test pin display functionality"
    )
    @app_commands.describe(
        pin_type="The type of pin to test (regular or sequential). If not specified, chooses randomly."
    )
    async def test_pin(self, ctx, pin_type: str = None):
        """Test the pin display functionality.
        
        Parameters
        -----------
        pin_type: Optional type of pin to test ('regular' or 'seq'). If not specified, chooses randomly.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get counts of both pin types
            cursor.execute("SELECT COUNT(*) FROM pinned_messages WHERE guild_id = ?", (ctx.guild.id,))
            regular_count = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT COUNT(DISTINCT sp.sequence_id)
                FROM sequential_pins sp
                JOIN sequential_pin_messages spm ON sp.sequence_id = spm.sequence_id
                WHERE sp.guild_id = ?
            """, (ctx.guild.id,))
            sequential_count = cursor.fetchone()[0]

            if regular_count == 0 and sequential_count == 0:
                await ctx.send("No pins found in this server.")
                return

            # Determine which type to show
            show_sequential = False
            if pin_type:
                pin_type = pin_type.lower()
                if pin_type in ['seq', 'sequential']:
                    if sequential_count == 0:
                        await ctx.send("No sequential pins found in this server.")
                        return
                    show_sequential = True
                elif pin_type in ['regular', 'normal']:
                    if regular_count == 0:
                        await ctx.send("No regular pins found in this server.")
                        return
                    show_sequential = False
                else:
                    await ctx.send("Invalid pin type. Use 'regular' or 'seq'.")
                    return
            else:
                # Random choice if both types exist
                if regular_count > 0 and sequential_count > 0:
                    show_sequential = random.random() < 0.5
                else:
                    show_sequential = sequential_count > 0

            # Get the pins based on type
            if show_sequential:
                cursor.execute("""
                    SELECT sp.sequence_id, sp.channel_id, COUNT(spm.message_id) as msg_count
                    FROM sequential_pins sp
                    JOIN sequential_pin_messages spm ON sp.sequence_id = spm.sequence_id
                    WHERE sp.guild_id = ?
                    GROUP BY sp.sequence_id
                    ORDER BY RANDOM()
                    LIMIT 1
                """, (ctx.guild.id,))
                sequence_data = cursor.fetchone()
                
                if sequence_data:
                    sequence_id, channel_id, msg_count = sequence_data
                    
                    # Get all messages in this sequence
                    cursor.execute("""
                        SELECT message_id, position
                        FROM sequential_pin_messages
                        WHERE sequence_id = ?
                        ORDER BY position
                    """, (sequence_id,))
                    sequence_messages = cursor.fetchall()

                    channel = self.bot.get_channel(channel_id)
                    if not channel:
                        await ctx.send("Could not find the channel for this pin.")
                        return

                    await ctx.send(f"Displaying sequential pin (ID: {sequence_id})")
                    
                    # Create embeds for all messages in sequence
                    embeds = []
                    for msg_id, position in sequence_messages:
                        try:
                            message = await channel.fetch_message(msg_id)
                            embed = await self.create_message_embed(
                                message, 
                                ctx.guild.id, 
                                channel_id,
                                sequence_id=sequence_id,
                                position=position + 1,
                                total=msg_count
                            )
                            embeds.append(embed)
                        except discord.NotFound:
                            continue

                    if embeds:  # Only send if we have valid embeds
                        await ctx.send(embeds=embeds)
            else:
                cursor.execute("""
                    SELECT message_id, channel_id
                    FROM pinned_messages
                    WHERE guild_id = ?
                    ORDER BY RANDOM()
                    LIMIT 1
                """, (ctx.guild.id,))
                pin_data = cursor.fetchone()
                
                if pin_data:
                    message_id, channel_id = pin_data
                    channel = self.bot.get_channel(channel_id)
                    if not channel:
                        await ctx.send("Could not find the channel for this pin.")
                        return

                    try:
                        message = await channel.fetch_message(message_id)
                        embed = await self.create_message_embed(message, ctx.guild.id, channel_id)
                        await ctx.send("Displaying random regular pin")
                        await ctx.send(embed=embed)
                    except discord.NotFound:
                        cursor.execute("DELETE FROM pinned_messages WHERE message_id = ?", (message_id,))
                        conn.commit()
                        await ctx.send("This pin no longer exists. It has been removed from the database.")
        
    async def create_message_embed(self, message, guild_id, channel_id, sequence_id=None, position=None, total=None):
        """Create a standardized embed for a pinned message."""
        avatar_url = str(message.author.display_avatar.url)
        
        try:
            response = requests.get(avatar_url)
            avatar_image = Image.open(BytesIO(response.content)).convert("RGB")
            pixels = list(avatar_image.getdata())
            avg_color = tuple(sum(c) // len(c) for c in zip(*pixels))
            embed_color = discord.Color.from_rgb(*avg_color)
        except Exception:
            embed_color = discord.Color.blue()

        message_url = f"https://discord.com/channels/{guild_id}/{channel_id}/{message.id}"
        
        # Prepare description with pin info first, then link
        if sequence_id is not None:
            description = f"seq pin {sequence_id} | msg {position}/{total} | {message_url}"
        else:
            description = f"Random Pin | {message_url}"

        # Create embed with content as title and combined info in description
        embed = discord.Embed(
            title=message.content,
            description=description,
            color=embed_color
        )
        
        # Set author with user's name and avatar
        embed.set_author(
            name=message.author.display_name,
            icon_url=avatar_url
        )

        # Add attachment if present
        if message.attachments:
            embed.set_image(url=message.attachments[0].url)

        return embed

    async def send_random_pinned_message(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for guild in self.bot.guilds:
                guild_id = str(guild.id)  # Convert to string for JSON compatibility
                
                # Get all sequential pins for this guild
                cursor.execute("""
                    SELECT sp.sequence_id, sp.channel_id, COUNT(spm.message_id) as msg_count
                    FROM sequential_pins sp
                    JOIN sequential_pin_messages spm ON sp.sequence_id = spm.sequence_id
                    WHERE sp.guild_id = ?
                    GROUP BY sp.sequence_id
                """, (guild.id,))
                sequential_pins = cursor.fetchall()

                # Get regular pins
                cursor.execute("SELECT message_id, channel_id FROM pinned_messages WHERE guild_id = ?", (guild.id,))
                regular_pins = cursor.fetchall()

                if not sequential_pins and not regular_pins:
                    continue

                # Decide whether to show a sequential pin or regular pin (50/50 chance if both exist)
                show_sequential = bool(sequential_pins) and (not regular_pins or random.random() < 0.5)

                if show_sequential:
                    # Initialize sequence index for this guild if needed
                    if guild_id not in self.guild_seq_indices:
                        self.guild_seq_indices[guild_id] = 0

                    current_index = self.guild_seq_indices[guild_id] % len(sequential_pins)
                    sequence_id, channel_id, msg_count = sequential_pins[current_index]

                    # Get all messages in this sequence
                    cursor.execute("""
                        SELECT message_id, position
                        FROM sequential_pin_messages
                        WHERE sequence_id = ?
                        ORDER BY position
                    """, (sequence_id,))
                    sequence_messages = cursor.fetchall()

                    channel = self.bot.get_channel(channel_id)
                    if not channel:
                        continue

                    # Create embeds for all messages in sequence
                    embeds = []
                    for msg_id, position in sequence_messages:
                        try:
                            message = await channel.fetch_message(msg_id)
                            embed = await self.create_message_embed(
                                message, 
                                guild.id, 
                                channel_id,
                                sequence_id=sequence_id,
                                position=position + 1,
                                total=msg_count
                            )
                            embeds.append(embed)
                        except discord.NotFound:
                            continue

                    if embeds:  # Only send if we have valid embeds
                        general_channel = discord.utils.get(guild.text_channels, name='general')
                        if general_channel:
                            await general_channel.send(embeds=embeds)

                    # Update sequence index
                    self.guild_seq_indices[guild_id] = (current_index + 1) % len(sequential_pins)

                else:
                    # Handle regular pins (existing logic)
                    if guild_id not in self.guild_pin_indices:
                        self.guild_pin_indices[guild_id] = 0

                    current_index = self.guild_pin_indices[guild_id] % len(regular_pins)
                    message_id, channel_id = regular_pins[current_index]

                    channel = self.bot.get_channel(channel_id)
                    if not channel:
                        continue

                    try:
                        message = await channel.fetch_message(message_id)
                        embed = await self.create_message_embed(message, guild.id, channel_id)
                        general_channel = discord.utils.get(guild.text_channels, name='general')
                        if general_channel:
                            await general_channel.send(embed=embed)
                    except discord.NotFound:
                        cursor.execute("DELETE FROM pinned_messages WHERE message_id = ?", (message_id,))
                        conn.commit()
                        continue

                    # Update regular pin index
                    self.guild_pin_indices[guild_id] = (current_index + 1) % len(regular_pins)

                self.save_state()

async def setup(bot):
    await bot.add_cog(AutoPins(bot))