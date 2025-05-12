from collections import defaultdict
import discord
from discord.ext import commands
from discord import app_commands
import sqlite3

class PinManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "huginn.db"
        # Add cache structures
        self.pin_cache = defaultdict(lambda: defaultdict(list))  # {guild_id: {channel_id: [message_ids]}}
        self.seq_pin_cache = defaultdict(list)  # {sequence_id: [message_ids]}
        self._init_db()
        self._load_cache()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pinned_messages (
                    guild_id INTEGER,
                    message_id INTEGER PRIMARY KEY,
                    channel_id INTEGER
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ignored_messages (
                    guild_id INTEGER,
                    message_id INTEGER PRIMARY KEY
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sequential_pins (
                    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    channel_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sequential_pin_messages (
                    sequence_id INTEGER,
                    message_id INTEGER,
                    position INTEGER,
                    FOREIGN KEY(sequence_id) REFERENCES sequential_pins(sequence_id),
                    PRIMARY KEY(sequence_id, message_id)
                )
            """)
            conn.commit()

    def _load_cache(self):
        """Load existing pinned messages into cache from database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Load regular pins
            cursor.execute("SELECT guild_id, channel_id, message_id FROM pinned_messages")
            for guild_id, channel_id, message_id in cursor.fetchall():
                self.pin_cache[guild_id][channel_id].append(message_id)
            
            # Load sequential pins
            cursor.execute("SELECT sequence_id, message_id FROM sequential_pin_messages ORDER BY position")
            for sequence_id, message_id in cursor.fetchall():
                self.seq_pin_cache[sequence_id].append(message_id)

    def _add_to_cache(self, guild_id: int, channel_id: int, message_id: int):
        """Add a message to the cache"""
        self.pin_cache[guild_id][channel_id].append(message_id)

    def _remove_from_cache(self, guild_id: int, channel_id: int, message_id: int):
        """Remove a message from the cache"""
        if message_id in self.pin_cache[guild_id][channel_id]:
            self.pin_cache[guild_id][channel_id].remove(message_id)

    async def _fetch_message_safe(self, channel, message_id: int):
        """Safely fetch a message, returning None if not found."""
        try:
            return await channel.fetch_message(message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.type == discord.MessageType.pins_add:
            try:
                await message.delete()
                print(f"Deleted a pin notification in {message.channel.name}")
                
                if message.reference:
                    recent_pin = await message.channel.fetch_message(message.reference.message_id)
                    
                    if recent_pin:
                        with sqlite3.connect(self.db_path) as conn:
                            cursor = conn.cursor()
                            cursor.execute("SELECT message_id FROM pinned_messages WHERE message_id = ? AND guild_id = ?", 
                                         (recent_pin.id, message.guild.id))
                            
                            if cursor.fetchone():
                                # Remove from cache and move to ignored
                                self._remove_from_cache(message.guild.id, message.channel.id, recent_pin.id)
                                cursor.execute("INSERT OR REPLACE INTO ignored_messages (guild_id, message_id) VALUES (?, ?)",
                                             (message.guild.id, recent_pin.id))
                                cursor.execute("DELETE FROM pinned_messages WHERE message_id = ? AND guild_id = ?", 
                                             (recent_pin.id, message.guild.id))
                                conn.commit()
                                print(f"Message {recent_pin.id} moved to ignored_messages table.")
                                await recent_pin.add_reaction("📌")
                                await recent_pin.remove_reaction("📌", self.bot.user)
                            else:
                                # Add to cache and database
                                self._add_to_cache(message.guild.id, message.channel.id, recent_pin.id)
                                cursor.execute("INSERT INTO pinned_messages (guild_id, message_id, channel_id) VALUES (?, ?, ?)",
                                             (message.guild.id, recent_pin.id, message.channel.id))
                                conn.commit()
                                print(f"Added message {recent_pin.id} to pinned_messages table.")
                                await recent_pin.add_reaction("📌")

                            try:
                                await recent_pin.unpin()
                                print(f"Unpinned message {recent_pin.id} in {message.channel.name}")
                            except (discord.Forbidden, discord.HTTPException) as e:
                                print(f"Failed to unpin message {recent_pin.id}: {e}")

            except discord.Forbidden:
                print("Bot lacks permissions to delete messages.")
            except discord.HTTPException as e:
                print(f"Failed to delete pin notification: {e}")

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def migrate_pins(self, ctx, channel: discord.TextChannel = None):
        """Migrate existing pinned messages in a channel or all channels in the guild to the new system without unpinning them."""
        channels = [channel] if channel else ctx.guild.text_channels
        total_migrated = 0

        print("Attempting migration process...")
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for ch in channels:
                pinned_messages = await ch.pins()
                for message in pinned_messages:
                    cursor.execute("INSERT OR IGNORE INTO pinned_messages (guild_id, message_id, channel_id) VALUES (?, ?, ?)",
                                   (ctx.guild.id, message.id, message.channel.id))
                    self._add_to_cache(ctx.guild.id, message.channel.id, message.id)
                total_migrated += len(pinned_messages)
            conn.commit()
        
        await ctx.send(f"Migrated {total_migrated} pinned messages {'from ' + channel.mention if channel else 'from all channels'} to the database.")

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def pin_count(self, ctx):
        """Shows the number of pinned messages in each channel of the guild."""
        pin_counts = {}
        
        # Fetch the count of pinned messages per channel from the cache
        for channel_id, messages in self.pin_cache[ctx.guild.id].items():
            channel = ctx.guild.get_channel(channel_id)
            if channel:
                pin_counts[channel.name] = len(messages)
        
        # Prepare the embed to show pin counts
        embed = discord.Embed(
            title=f"Pinned Messages Count for {ctx.guild.name}",
            description="This is the number of pinned messages in each channel:",
            color=discord.Color.blue()
        )
        
        # Add fields for each channel's pin count
        if pin_counts:
            for channel_name, count in pin_counts.items():
                embed.add_field(name=channel_name, value=f"{count} pinned messages", inline=False)
        else:
            embed.add_field(name="No pinned messages", value="There are no pinned messages in this guild.", inline=False)
        
        # Send the embed as a response
        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def pin_refresh(self, ctx):
        """Refresh pin reactions for all messages in the pinned_messages table."""
        refreshed_count = 0

        for channel_id, message_ids in self.pin_cache[ctx.guild.id].items():
            channel = ctx.guild.get_channel(channel_id)
            if not channel:
                continue

            for message_id in message_ids:
                try:
                    message = await channel.fetch_message(message_id)
                    # Check if the bot has already reacted with the pin emoji
                    if not any(reaction.emoji == "📌" and reaction.me for reaction in message.reactions):
                        await message.add_reaction("📌")
                        refreshed_count += 1
                except discord.NotFound:
                    print(f"Message {message_id} not found in channel {channel_id}.")
                except discord.Forbidden:
                    print(f"Missing permissions to fetch or react to message {message_id} in channel {channel_id}.")
                except discord.HTTPException as e:
                    print(f"Failed to refresh pin reaction for message {message_id}: {e}")

        await ctx.send(f"Refreshed pin reactions for {refreshed_count} messages.")

    @commands.hybrid_command(
        name="pinseq",
        description="Create a sequential pin with multiple messages. Messages must be from current channel."
    )
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(
        message_ids="Space-separated list of message IDs to add to the sequence (e.g. 123456789 987654321)"
    )
    async def pinseq(self, ctx: commands.Context, *, message_ids: str):
        """Create a sequential pin with multiple messages. Messages must be from current channel.
        
        Parameters
        -----------
        message_ids: Space-separated list of message IDs to add to the sequence
        """
        # Convert space-separated string of IDs to list of ints
        try:
            message_id_list = [int(mid.strip()) for mid in message_ids.split()]
        except ValueError:
            await ctx.send("Invalid message IDs provided. Please provide space-separated numbers only.")
            return

        if len(message_id_list) < 2:
            await ctx.send("Please provide at least 2 message IDs to create a sequential pin.")
            return

        messages = []
        for msg_id in message_id_list:
            message = await self._fetch_message_safe(ctx.channel, msg_id)
            if message is None:
                await ctx.send(f"Could not find message with ID {msg_id}. Operation cancelled.")
                return
            messages.append(message)

        # Store the sequential pin in the database
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO sequential_pins (guild_id, channel_id) VALUES (?, ?)",
                (ctx.guild.id, ctx.channel.id)
            )
            sequence_id = cursor.lastrowid

            # Store each message in order
            for position, message in enumerate(messages):
                cursor.execute(
                    "INSERT INTO sequential_pin_messages (sequence_id, message_id, position) VALUES (?, ?, ?)",
                    (sequence_id, message.id, position)
                )
                # Add to cache
                self.seq_pin_cache[sequence_id].append(message.id)
                # Add pin reaction
                await message.add_reaction("📌")

            conn.commit()

        # Create a preview embed
        embed = discord.Embed(
            title="Sequential Pin Created",
            description=f"Created sequential pin with {len(messages)} messages",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="First Message",
            value=messages[0].content[:100] + "..." if len(messages[0].content) > 100 else messages[0].content,
            inline=False
        )
        embed.add_field(
            name="Last Message",
            value=messages[-1].content[:100] + "..." if len(messages[-1].content) > 100 else messages[-1].content,
            inline=False
        )
        embed.set_footer(text=f"Sequence ID: {sequence_id}")

        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="showseq",
        description="Display all messages in a sequential pin."
    )
    @app_commands.describe(
        sequence_id="The ID of the sequential pin to display"
    )
    async def showseq(self, ctx, sequence_id: int):
        """Display all messages in a sequential pin.
        
        Parameters
        -----------
        sequence_id: The ID of the sequential pin to display
        """
        if sequence_id not in self.seq_pin_cache:
            await ctx.send("Sequential pin not found.")
            return

        message_ids = self.seq_pin_cache[sequence_id]
        messages = []
        
        for msg_id in message_ids:
            message = await self._fetch_message_safe(ctx.channel, msg_id)
            if message:
                messages.append(message)

        if not messages:
            await ctx.send("Could not find any messages for this sequential pin.")
            return

        # Create embeds for each message
        embeds = []
        for i, message in enumerate(messages):
            embed = discord.Embed(
                description=message.content,
                color=discord.Color.blue(),
                timestamp=message.created_at
            )
            embed.set_author(
                name=message.author.display_name,
                icon_url=str(message.author.display_avatar.url)
            )
            embed.set_footer(text=f"Message {i + 1}/{len(messages)} | Sequence ID: {sequence_id}")
            
            if message.attachments:
                embed.set_image(url=message.attachments[0].url)
            
            embeds.append(embed)

        # Send all embeds
        for embed in embeds:
            await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="delseq",
        description="Delete a sequential pin and remove all pin reactions."
    )
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(
        sequence_id="The ID of the sequential pin to delete"
    )
    async def delseq(self, ctx, sequence_id: int):
        """Delete a sequential pin and remove all pin reactions.
        
        Parameters
        -----------
        sequence_id: The ID of the sequential pin to delete
        """
        if sequence_id not in self.seq_pin_cache:
            await ctx.send("Sequential pin not found.")
            return

        message_ids = self.seq_pin_cache[sequence_id]
        
        # Remove reactions and delete from database
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sequential_pin_messages WHERE sequence_id = ?", (sequence_id,))
            cursor.execute("DELETE FROM sequential_pins WHERE sequence_id = ?", (sequence_id,))
            conn.commit()

        # Remove reactions
        for msg_id in message_ids:
            message = await self._fetch_message_safe(ctx.channel, msg_id)
            if message:
                await message.remove_reaction("📌", self.bot.user)

        # Remove from cache
        del self.seq_pin_cache[sequence_id]
        
        await ctx.send(f"Sequential pin {sequence_id} has been deleted.")

async def setup(bot):
    await bot.add_cog(PinManagement(bot))
