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

# Default times - these will be overridden by server configuration
default_times = [
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
        self.last_sent_times = {}  # Track when pins were last sent for each guild
        
        # Load existing pin indices or create new state file
        if os.path.exists(self.state_file):
            with open(self.state_file, 'r') as f:
                state = yaml.safe_load(f) or {}
                self.guild_pin_indices = state.get('regular_pins', {})
                self.guild_seq_indices = state.get('sequential_pins', {})
                self.last_sent_times = state.get('last_sent_times', {})
        else:
            # Create data directory if it doesn't exist
            os.makedirs('data', exist_ok=True)
            with open(self.state_file, 'w') as f:
                yaml.dump({'regular_pins': {}, 'sequential_pins': {}, 'last_sent_times': {}}, f)
    
        # Start the task but don't use the decorator since we need dynamic times
        self.pinned_message_task.start()
    
    async def get_server_config(self):
        """Get the server configuration cog for accessing pin times."""
        return self.bot.get_cog('ServerConfig')
    
    def get_pin_times_for_guild(self, guild_id: int):
        """Get pin times for a specific guild, checking inter-bot communication first."""
        # Check if we have received config from Muninn via inter-bot communication
        ibc_cog = self.bot.get_cog('InterBotCommunication')
        if ibc_cog and hasattr(ibc_cog, 'received_configs'):
            guild_config = ibc_cog.received_configs.get(str(guild_id), {})
            if guild_config:
                # Extract devotion times if configured
                devotion_hour = guild_config.get('devotion_hour', {}).get('value')
                devotion_minute = guild_config.get('devotion_minute', {}).get('value')
                devotion_enabled = guild_config.get('devotion_enabled', {}).get('value', True)
                
                if devotion_enabled and devotion_hour is not None and devotion_minute is not None:
                    # Create custom pin time based on devotion schedule
                    import datetime
                    custom_time = datetime.time(devotion_hour, devotion_minute)
                    print(f"Using custom pin time for guild {guild_id}: {custom_time}")
                    return [custom_time] + default_times  # Add devotion time to defaults
        
        # Fallback to default times
        return default_times
    
    async def get_pin_times_for_all_guilds(self):
        """Get all unique pin times across all guilds."""
        server_config = await self.get_server_config()
        if not server_config:
            return default_times
        
        all_times = set()
        
        # Get times for each guild
        for guild in self.bot.guilds:
            try:
                guild_times = server_config.get_pin_times_for_guild(guild.id)
                all_times.update(guild_times)
            except Exception as e:
                print(f"Error getting pin times for guild {guild.id}: {e}")
                continue
        
        # If no times found, use defaults
        if not all_times:
            return default_times
        
        return list(all_times)
    
    async def should_send_pin_for_guild(self, guild_id: int) -> bool:
        """Check if it's time to send a pin for a specific guild."""
        # Check cooldown - don't send pins more than once every 30 minutes
        guild_id_str = str(guild_id)
        current_timestamp = datetime.datetime.now().timestamp()
        last_sent = self.last_sent_times.get(guild_id_str, 0)
        
        # Minimum 30 minutes (1800 seconds) between pins
        if current_timestamp - last_sent < 1800:
            return False
        
        server_config = await self.get_server_config()
        
        try:
            if server_config:
                guild_times = server_config.get_pin_times_for_guild(guild_id)
            else:
                # Use the new method that checks inter-bot communication
                guild_times = self.get_pin_times_for_guild(guild_id)
            
            current_time = datetime.datetime.now().time()
            
            # Check if current time matches any of the guild's configured times (within 30 seconds)
            for pin_time in guild_times:
                time_diff = abs(
                    (datetime.datetime.combine(datetime.date.today(), current_time) -
                     datetime.datetime.combine(datetime.date.today(), pin_time)).total_seconds()
                )
                
                # If within 30 seconds of a scheduled time, send the pin
                if time_diff <= 30:
                    return True
            
            return False
            
        except Exception as e:
            print(f"Error checking pin time for guild {guild_id}: {e}")
            # On error, use the new method as fallback
            current_time = datetime.datetime.now().time()
            guild_times = self.get_pin_times_for_guild(guild_id)
            for pin_time in guild_times:
                time_diff = abs(
                    (datetime.datetime.combine(datetime.date.today(), current_time) -
                     datetime.datetime.combine(datetime.date.today(), pin_time)).total_seconds()
                )
                if time_diff <= 30:
                    return True
            return False
    
    def save_state(self):
        """Save the current pin indices to the state file with thread safety."""
        import tempfile
        import shutil
        
        # Write to temporary file first, then atomically move it
        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as temp_file:
                yaml.dump({
                    'regular_pins': self.guild_pin_indices,
                    'sequential_pins': self.guild_seq_indices,
                    'last_sent_times': self.last_sent_times
                }, temp_file)
                temp_file_path = temp_file.name
            
            # Atomically replace the original file
            shutil.move(temp_file_path, self.state_file)
            
        except Exception as e:
            print(f"Error saving pin state: {e}")
            # Clean up temp file if it exists
            if temp_file and os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                except:
                    pass

    def cog_unload(self):
        """Ensure the loop is properly canceled when the cog is unloaded."""
        self.save_state()
        self.pinned_message_task.cancel()
        
    @tasks.loop(minutes=1)  # Check every minute instead of specific times
    async def pinned_message_task(self):
        """Check if it's time to send pins for any guild and send them."""
        try:
            current_time = datetime.datetime.now()
            pins_sent = 0
            
            # Check each guild to see if it's time to send a pin
            for guild in self.bot.guilds:
                try:
                    if await self.should_send_pin_for_guild(guild.id):
                        print(f"[{current_time.strftime('%H:%M:%S')}] Sending pin for guild {guild.name}")
                        await self.send_random_pinned_message_for_guild(guild.id)
                        pins_sent += 1
                except Exception as e:
                    print(f"Error processing guild {guild.name}: {e}")
                    import traceback
                    traceback.print_exc()
            
            if pins_sent > 0:
                print(f"Pin autosend task completed - sent {pins_sent} pins at {current_time.strftime('%H:%M:%S')}")
                
        except Exception as e:
            print(f"Error in pin autosend task: {e}")
            import traceback
            traceback.print_exc()
    
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
        try:
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
                    await ctx.send("No pins found in this server.", ephemeral=True)
                    return

                # Determine which type to show
                show_sequential = False
                if pin_type:
                    pin_type = pin_type.lower()
                    if pin_type in ['seq', 'sequential']:
                        if sequential_count == 0:
                            await ctx.send("No sequential pins found in this server.", ephemeral=True)
                            return
                        show_sequential = True
                    elif pin_type in ['regular', 'normal']:
                        if regular_count == 0:
                            await ctx.send("No regular pins found in this server.", ephemeral=True)
                            return
                        show_sequential = False
                    else:
                        await ctx.send("Invalid pin type. Use 'regular' or 'seq'.", ephemeral=True)
                        return
                else:
                    # Random choice if both types exist
                    if regular_count > 0 and sequential_count > 0:
                        show_sequential = random.random() < 0.5
                    else:
                        show_sequential = sequential_count > 0

                # Get the pins based on type
                if show_sequential:
                    try:
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
                                await ctx.send("Could not find the channel for this pin.", ephemeral=True)
                                return

                            await ctx.send(f"Displaying sequential pin (ID: {sequence_id})")
                            
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
                                except Exception as e:
                                    print(f"Error fetching message {msg_id} in sequential pin: {e}")
                                    continue

                            # Create one embed per author
                            embeds = []
                            for author_messages in messages_by_author.values():
                                if author_messages:  # Check if we have messages for this author
                                    try:
                                        embed = await self.create_message_embed(
                                            author_messages[0],  # Use first message for author info
                                            ctx.guild.id, 
                                            channel_id,
                                            sequence_id=sequence_id,
                                            messages=author_messages
                                        )
                                        embeds.append(embed)
                                    except Exception as e:
                                        print(f"Error creating embed for sequential pin: {e}")

                            if embeds:  # Only send if we have valid embeds
                                await ctx.channel.send(embeds=embeds)
                                await ctx.send("Sequential pin sent to channel.", ephemeral=True)
                            else:
                                await ctx.send("No valid messages found for this sequential pin.", ephemeral=True)
                        else:
                            await ctx.send("No sequential pin data found.", ephemeral=True)
                    except Exception as e:
                        print(f"Error in sequential pin test: {e}")
                        await ctx.send(f"Error displaying sequential pin: {e}", ephemeral=True)
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

    async def send_random_pinned_message_for_guild(self, guild_id: int):
        """Send a random pinned message for a specific guild."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
            
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            try:
                # Get counts of both pin types
                cursor.execute("SELECT COUNT(*) FROM pinned_messages WHERE guild_id = ?", (guild_id,))
                regular_count = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT COUNT(DISTINCT sp.sequence_id)
                    FROM sequential_pins sp
                    JOIN sequential_pin_messages spm ON sp.sequence_id = spm.sequence_id
                    WHERE sp.guild_id = ?
                """, (guild_id,))
                sequential_count = cursor.fetchone()[0]

                if regular_count == 0 and sequential_count == 0:
                    return

                # Find a suitable channel to send pins to
                target_channel = None
                # Try common channel names in order of preference
                for channel_name in ['general', 'chat', 'main', 'pins']:
                    target_channel = discord.utils.get(guild.text_channels, name=channel_name)
                    if target_channel and target_channel.permissions_for(guild.me).send_messages:
                        break
                
                # If no named channel found, use the first channel we can send to
                if not target_channel:
                    for channel in guild.text_channels:
                        if channel.permissions_for(guild.me).send_messages:
                            target_channel = channel
                            break
                
                if not target_channel:
                    print(f"No suitable channel found in guild {guild.name}")
                    return

                # Decide whether to show a sequential pin or regular pin
                if regular_count == 0:
                    show_sequential = True  # Only sequential pins exist
                    print(f"Guild {guild.name}: Only sequential pins exist ({sequential_count} sequential)")
                elif sequential_count == 0:
                    show_sequential = False  # Only regular pins exist
                    print(f"Guild {guild.name}: Only regular pins exist ({regular_count} regular)")
                else:
                    random_value = random.random()
                    show_sequential = random_value < 0.5  # 50/50 chance when both exist
                    print(f"Guild {guild.name}: Both types exist ({regular_count} regular, {sequential_count} sequential). Random value: {random_value:.3f}, Choosing: {'sequential' if show_sequential else 'regular'}")

                if show_sequential:
                    print(f"Guild {guild.name}: Sending sequential pin")
                    await self._send_sequential_pin(guild, target_channel, cursor)
                else:
                    print(f"Guild {guild.name}: Sending regular pin")
                    await self._send_regular_pin(guild, target_channel, cursor)
                
                # Record the timestamp when pin was sent
                self.last_sent_times[str(guild_id)] = datetime.datetime.now().timestamp()

            except Exception as e:
                print(f"Error processing guild {guild.name}: {e}")
                import traceback
                traceback.print_exc()

            # Save the updated indices after processing
            self.save_state()

    async def send_random_pinned_message(self):
        """Send a random pinned message from the database for all guilds."""
        # This method is kept for backward compatibility but now processes all guilds
        for guild in self.bot.guilds:
            await self.send_random_pinned_message_for_guild(guild.id)

    async def _send_sequential_pin(self, guild, target_channel, cursor):
        """Send a sequential pin to the target channel."""
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
            return
            
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
            return

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
            except Exception as e:
                print(f"Error fetching message {msg_id}: {e}")
                continue

        # Create one embed per author
        embeds = []
        for author_messages in messages_by_author.values():
            if author_messages:  # Check if we have messages for this author
                try:
                    embed = await self.create_message_embed(
                        author_messages[0],  # Use first message for author info
                        guild.id, 
                        channel_id,
                        sequence_id=sequence_id,
                        messages=author_messages
                    )
                    embeds.append(embed)
                except Exception as e:
                    print(f"Error creating embed: {e}")

        if embeds:  # Only send if we have valid embeds
            try:
                await target_channel.send(embeds=embeds)
            except Exception as e:
                print(f"Error sending sequential pin to {target_channel.name}: {e}")

        # Update sequence index for next time
        self.guild_seq_indices[guild_id_str] = (current_index + 1) % len(sequence_pins)

    async def _send_regular_pin(self, guild, target_channel, cursor):
        """Send a regular pin to the target channel."""
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
            return
            
        current_index = self.guild_pin_indices[guild_id_str] % len(regular_pins)
        message_id, channel_id = regular_pins[current_index]

        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        try:
            message = await channel.fetch_message(message_id)
            embed = await self.create_message_embed(message, guild.id, channel_id)
            await target_channel.send(embed=embed)
        except discord.NotFound:
            cursor.execute("DELETE FROM pinned_messages WHERE message_id = ?", (message_id,))
            # Don't commit here, let the parent function handle it
            return
        except Exception as e:
            print(f"Error sending regular pin: {e}")
            return

        # Update regular pin index for next time
        self.guild_pin_indices[guild_id_str] = (current_index + 1) % len(regular_pins)

async def setup(bot):
    await bot.add_cog(AutoPins(bot))