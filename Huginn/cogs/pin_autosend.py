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
        
        # Load existing pin indices or create new state file
        if os.path.exists(self.state_file):
            with open(self.state_file, 'r') as f:
                state = yaml.safe_load(f) or {}
                self.guild_pin_indices = state.get('regular_pins', {})
        else:
            # Create data directory if it doesn't exist
            os.makedirs('data', exist_ok=True)
            with open(self.state_file, 'w') as f:
                yaml.dump({'regular_pins': {}}, f)
    
        # Stop the loop if it is already running to prevent multiple instances
        if self.pinned_message_task.is_running():
            self.pinned_message_task.cancel()

        # Start the task (it will use the time schedule defined in @tasks.loop)
        self.pinned_message_task.start()
    
    def save_state(self):
        """Save the current pin indices to the state file."""
        with open(self.state_file, 'w') as f:
            yaml.dump({
                'regular_pins': self.guild_pin_indices,
            }, f)

    async def _notify_owner(self, subject: str, details: str):
        """Attempt to DM the application owner with an error message.

        This caches application info where possible and quietly fails if owner cannot be notified.
        """
        try:
            app_info = await self.bot.application_info()
            owner = app_info.owner
            if owner:
                try:
                    await owner.send(f"[AutoPins] {subject}\n{details}")
                except Exception:
                    # Best-effort: ignore if we can't DM the owner
                    print(f"Failed to DM owner about: {subject}")
        except Exception:
            print("Failed to fetch application info to notify owner.")

    def cog_unload(self):
        """Ensure the loop is properly canceled when the cog is unloaded."""
        self.save_state()
        self.pinned_message_task.cancel()
        
    @tasks.loop(time=times)
    async def pinned_message_task(self):
        print(f"Pin autosend task running at {datetime.datetime.now(la_timezone)}")
        try:
            await self.send_random_pinned_message()
            print("Pin autosend task completed successfully")
        except Exception as e:
            print(f"Error in pin autosend task: {e}")
            import traceback
            traceback.print_exc()
    
    @commands.hybrid_command(
        name="testpin",
        description="Test pin display functionality"
    )
    async def test_pin(self, ctx):
        """Test the pin display functionality."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("SELECT COUNT(*) FROM pinned_messages WHERE guild_id = ?", (ctx.guild.id,))
                regular_count = cursor.fetchone()[0]

                if regular_count == 0:
                    await ctx.send("No pins found in this server.", ephemeral=True)
                    return

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
                        await ctx.send("Could not find the channel for this pin.", ephemeral=True)
                        return
                    try:
                        message = await channel.fetch_message(message_id)
                        embed = await self.create_message_embed(message, ctx.guild.id, channel_id)
                        await ctx.channel.send(embed=embed)
                        await ctx.send("Regular pin sent to channel.", ephemeral=True)
                    except discord.NotFound:
                        cursor.execute("DELETE FROM pinned_messages WHERE message_id = ?", (message_id,))
                        conn.commit()
                        await ctx.send("This pin no longer exists. It has been removed from the database.", ephemeral=True)
                    except Exception as e:
                        print(f"Error displaying regular pin: {e}")
                        await ctx.send(f"Error displaying regular pin: {e}", ephemeral=True)
                else:
                    await ctx.send("No regular pin data found.", ephemeral=True)
        except Exception as e:
            print(f"Error in test_pin: {e}")
            await ctx.send(f"Unexpected error: {e}", ephemeral=True)
    
    async def create_message_embed(self, message, guild_id, channel_id, sequence_id=None, messages=None, total=None):
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
        
        # Prepare description with pin info first
        if sequence_id is not None:
            description = f"Sequential pin {sequence_id}"
        else:
            description = "Random Pin"
        
        # Helper function to replace user mentions with usernames
        async def replace_mentions(content, guild_id):
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return content
            
            def replace_mention(match):
                user_id = int(match.group(1))
                member = guild.get_member(user_id)
                return f"@{member.display_name}" if member else f"<@{user_id}>"
            
            import re
            return re.sub(r"<@!?(\d+)>", replace_mention, content)

        # If this is a sequential pin with multiple messages
        if messages:
            # Combine messages into title with newlines, replacing mentions
            processed_messages = []
            for msg in messages:
                processed_content = await replace_mentions(msg.content, guild_id)
                processed_messages.append(processed_content)
            title = "\n".join(processed_messages)
            # Always check title length and move to description if too long
            if len(title) <= 256:
                embed = discord.Embed(
                    title=title,
                    description=f"Sequential pin {sequence_id} | {message_url}",
                    color=embed_color
                )
            else:
                # Truncate description if needed to fit Discord's 4096 char limit
                desc_content = title[:4000] + ("..." if len(title) > 4000 else "")
                embed = discord.Embed(
                    description=f"{desc_content}\n\nSequential pin {sequence_id} | {message_url}",
                    color=embed_color
                )
        else:
            # Single message, replace mentions
            content = await replace_mentions(message.content, guild_id)
            if len(content) <= 256:
                embed = discord.Embed(
                    title=content,
                    description=f"Random Pin | {message_url}",
                    color=embed_color
                )
            else:
                desc_content = content[:4000] + ("..." if len(content) > 4000 else "")
                embed = discord.Embed(
                    description=f"{desc_content}\n\nRandom Pin | {message_url}",
                    color=embed_color
                )
        
        # Set author with user's name and avatar
        embed.set_author(
            name=message.author.display_name,
            icon_url=avatar_url
        )

        # Add attachment if present (from the first message with an attachment)
        if messages:
            for msg in messages:
                if msg.attachments:
                    embed.set_image(url=msg.attachments[0].url)
                    break
        elif message.attachments:
            embed.set_image(url=message.attachments[0].url)
            
        return embed

    async def send_random_pinned_message(self):
        """Send a random pinned message from the database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Loop through each guild
            for guild in self.bot.guilds:
                # Get counts of both pin types
                cursor.execute("SELECT COUNT(*) FROM pinned_messages WHERE guild_id = ?", (guild.id,))
                regular_count = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT COUNT(DISTINCT sp.sequence_id)
                    FROM sequential_pins sp
                    JOIN sequential_pin_messages spm ON sp.sequence_id = spm.sequence_id
                    WHERE sp.guild_id = ?
                """, (guild.id,))
                sequential_count = cursor.fetchone()[0]

                if regular_count == 0 and sequential_count == 0:
                    continue

                # Decide whether to show a sequential pin or regular pin
                if regular_count == 0:
                    show_sequential = True  # Only sequential pins exist
                elif sequential_count == 0:
                    show_sequential = False  # Only regular pins exist
                else:
                    show_sequential = random.random() < 0.5  # 50/50 chance when both exist

                if show_sequential:
                    # Initialize sequence index for this guild if needed
                    guild_id_str = str(guild.id)
                    if guild_id_str not in self.guild_seq_indices:
                        self.guild_seq_indices[guild_id_str] = 0

                    # Get the next sequential pin
                    cursor.execute("""
                        SELECT sp.sequence_id, sp.channel_id, COUNT(spm.message_id) as msg_count
                        FROM sequential_pins sp
                        JOIN sequential_pin_messages spm ON sp.sequence_id = spm.sequence_id
                        WHERE sp.guild_id = ?
                        GROUP BY sp.sequence_id
                    """, (guild.id,))
                    sequence_pins = cursor.fetchall()
                    
                    if not sequence_pins:
                        continue
                    
                    current_index = self.guild_seq_indices[guild_id_str] % len(sequence_pins)
                    sequence_id, channel_id, msg_count = sequence_pins[current_index]

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

                    # Fetch all messages and group by author
                    messages_by_author = {}
                    for msg_id, _ in sequence_messages:
                        try:
                            message = await channel.fetch_message(msg_id)
                            if message.author.id not in messages_by_author:
                                messages_by_author[message.author.id] = []
                            messages_by_author[message.author.id].append(message)
                        except discord.NotFound:
                            continue

                    # Create one embed per author
                    embeds = []
                    for author_messages in messages_by_author.values():
                        if author_messages:  # Check if we have messages for this author
                            embed = await self.create_message_embed(
                                author_messages[0],  # Use first message for author info
                                guild.id, 
                                channel_id,
                                sequence_id=sequence_id,
                                messages=author_messages
                            )
                            embeds.append(embed)

                    if embeds:  # Only send if we have valid embeds
                        general_channel = discord.utils.get(guild.text_channels, name='general')
                        if general_channel:
                            try:
                                await general_channel.send(embeds=embeds)
                            except Exception as e:
                                print(f"Failed to send sequential pin to guild {guild.id}: {e}")
                                try:
                                    await self._notify_owner(
                                        "Failed to send sequential pinned message",
                                        f"Guild: {guild.name} ({guild.id})\nError: {e}"
                                    )
                                except Exception:
                                    pass

                    # Update sequence index for next time
                    self.guild_seq_indices[guild_id_str] = (current_index + 1) % len(sequence_pins)

                else:
                    # Handle regular pins
                    guild_id_str = str(guild.id)
                    if guild_id_str not in self.guild_pin_indices:
                        self.guild_pin_indices[guild_id_str] = 0

                    # Get all regular pins for this guild
                    cursor.execute("""
                        SELECT message_id, channel_id
                        FROM pinned_messages
                        WHERE guild_id = ?
                    """, (guild.id,))
                    regular_pins = cursor.fetchall()

                    if not regular_pins:
                        continue

                    current_index = self.guild_pin_indices[guild_id_str] % len(regular_pins)
                    message_id, channel_id = regular_pins[current_index]

                    channel = self.bot.get_channel(channel_id)
                    if not channel:
                        continue

                    try:
                        message = await channel.fetch_message(message_id)
                        embed = await self.create_message_embed(message, guild.id, channel_id)
                        general_channel = discord.utils.get(guild.text_channels, name='general')
                        if general_channel:
                            try:
                                await general_channel.send(embed=embed)
                            except Exception as e:
                                print(f"Failed to send regular pin to guild {guild.id}: {e}")
                                try:
                                    await self._notify_owner(
                                        "Failed to send regular pinned message",
                                        f"Guild: {guild.name} ({guild.id})\nError: {e}"
                                    )
                                except Exception:
                                    pass
                    except discord.NotFound:
                        cursor.execute("DELETE FROM pinned_messages WHERE message_id = ?", (message_id,))
                        conn.commit()
                        continue

                    # Update regular pin index for next time
                    self.guild_pin_indices[guild_id_str] = (current_index + 1) % len(regular_pins)

                # Save the updated indices
                self.save_state()

async def setup(bot):
    await bot.add_cog(AutoPins(bot))