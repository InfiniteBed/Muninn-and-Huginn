from collections import defaultdict
import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from typing import Union, Optional, List, Dict

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

        # Fetch messages and group by author
        messages_by_author = {}
        first_author = None
        for msg_id in message_id_list:
            message = await self._fetch_message_safe(ctx.channel, msg_id)
            if message is None:
                await ctx.send(f"Could not find message with ID {msg_id}. Operation cancelled.")
                return
                
            # Store first author to validate all messages are from same author
            if first_author is None:
                first_author = message.author.id
            elif message.author.id != first_author:
                await ctx.send("All messages in a sequence must be from the same author.")
                return
                
            if message.author.id not in messages_by_author:
                messages_by_author[message.author.id] = []
            messages_by_author[message.author.id].append(message)

        # Store the sequential pin in the database
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO sequential_pins (guild_id, channel_id) VALUES (?, ?)",
                (ctx.guild.id, ctx.channel.id)
            )
            sequence_id = cursor.lastrowid

            # Store each message in order
            for position, message in enumerate(messages_by_author[first_author]):
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
        messages = messages_by_author[first_author]
        embed = discord.Embed(
            description="\n\n".join(msg.content for msg in messages),
            color=discord.Color.blue()
        )
        embed.set_author(
            name=messages[0].author.display_name,
            icon_url=str(messages[0].author.display_avatar.url)
        )
        
        # Add the first attachment found, if any
        for msg in messages:
            if msg.attachments:
                embed.set_image(url=msg.attachments[0].url)
                break
                
        embed.set_footer(text=f"Sequential Pin Created | Sequence ID: {sequence_id}")
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
        messages_by_author = {}
        
        for msg_id in message_ids:
            message = await self._fetch_message_safe(ctx.channel, msg_id)
            if message:
                if message.author.id not in messages_by_author:
                    messages_by_author[message.author.id] = []
                messages_by_author[message.author.id].append(message)

        if not messages_by_author:
            await ctx.send("Could not find any messages for this sequential pin.")
            return

        # Create embeds for each author's messages
        embeds = []
        for author_messages in messages_by_author.values():
            if author_messages:
                embed = discord.Embed(
                    description="\n\n".join(msg.content for msg in author_messages),
                    color=discord.Color.blue(),
                    timestamp=author_messages[0].created_at
                )
                embed.set_author(
                    name=author_messages[0].author.display_name,
                    icon_url=str(author_messages[0].author.display_avatar.url)
                )
                embed.set_footer(text=f"Sequence ID: {sequence_id}")
                
                # Add the first attachment found, if any
                for msg in author_messages:
                    if msg.attachments:
                        embed.set_image(url=msg.attachments[0].url)
                        break
                
                embeds.append(embed)

        # Send all embeds
        await ctx.send(embeds=embeds)

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

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def cleanseq(self, ctx):
        """Clean up sequential pins by removing any that have messages from multiple authors."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get all sequence IDs
            cursor.execute("""
                SELECT DISTINCT sp.sequence_id, sp.channel_id
                FROM sequential_pins sp
                JOIN sequential_pin_messages spm ON sp.sequence_id = spm.sequence_id
                WHERE sp.guild_id = ?
            """, (ctx.guild.id,))
            sequences = cursor.fetchall()
            
            deleted_count = 0
            for sequence_id, channel_id in sequences:
                # Get all messages in this sequence
                cursor.execute("""
                    SELECT message_id
                    FROM sequential_pin_messages
                    WHERE sequence_id = ?
                    ORDER BY position
                """, (sequence_id,))
                message_ids = cursor.fetchall()
                
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    continue
                
                # Check messages for multiple authors
                authors = set()
                for (msg_id,) in message_ids:
                    try:
                        message = await channel.fetch_message(msg_id)
                        authors.add(message.author.id)
                        if len(authors) > 1:  # Multiple authors found
                            # Remove pin reactions
                            for (msg_id_to_unpin,) in message_ids:
                                try:
                                    msg_to_unpin = await channel.fetch_message(msg_id_to_unpin)
                                    await msg_to_unpin.remove_reaction("📌", self.bot.user)
                                except (discord.NotFound, discord.Forbidden):
                                    pass
                            
                            # Delete from database
                            cursor.execute("DELETE FROM sequential_pin_messages WHERE sequence_id = ?", (sequence_id,))
                            cursor.execute("DELETE FROM sequential_pins WHERE sequence_id = ?", (sequence_id,))
                            
                            # Remove from cache
                            if sequence_id in self.seq_pin_cache:
                                del self.seq_pin_cache[sequence_id]
                                
                            deleted_count += 1
                            break
                            
                    except discord.NotFound:
                        continue
            
            conn.commit()
            
        await ctx.send(f"Cleanup complete. Removed {deleted_count} sequential pins with multiple authors.")

    async def _create_pin_embed(self, message: discord.Message, sequence_id: Optional[int] = None, total_pages: Optional[int] = None, current_page: Optional[int] = None) -> discord.Embed:
        """Create an embed for a pinned message."""
        avatar_url = str(message.author.display_avatar.url)
        embed_color = discord.Color.blue()

        # Create base embed
        embed = discord.Embed(
            description=message.content or "No content",
            color=embed_color,
            timestamp=message.created_at
        )

        # Set author
        embed.set_author(
            name=message.author.display_name,
            icon_url=avatar_url
        )

        # Add jump link
        embed.add_field(
            name="Source",
            value=f"{message.jump_url}",
            inline=False
        )

        # Add sequence info if applicable
        if sequence_id:
            embed.add_field(
                name="Sequential Pin",
                value=f"ID: {sequence_id}",
                inline=True
            )

        # Add pagination info if applicable
        if total_pages is not None and current_page is not None:
            embed.set_footer(text=f"Page {current_page + 1}/{total_pages}")

        # Add first attachment if any
        if message.attachments:
            embed.set_image(url=message.attachments[0].url)

        return embed

    async def _get_pin_messages(self, guild_id: int, channel_id: Optional[int] = None) -> List[Dict]:
        """Get all pinned messages for a guild, optionally filtered by channel."""
        all_pins = []
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get regular pins
            query = """
                SELECT pm.message_id, pm.channel_id, NULL as sequence_id
                FROM pinned_messages pm
                WHERE pm.guild_id = ?
            """
            params = [guild_id]
            
            if channel_id:
                query += " AND pm.channel_id = ?"
                params.append(channel_id)
                
            cursor.execute(query, params)
            regular_pins = cursor.fetchall()
            all_pins.extend([{"message_id": mid, "channel_id": cid, "sequence_id": sid} 
                           for mid, cid, sid in regular_pins])
            
            # Get sequential pins
            query = """
                SELECT spm.message_id, sp.channel_id, sp.sequence_id
                FROM sequential_pins sp
                JOIN sequential_pin_messages spm ON sp.sequence_id = spm.sequence_id
                WHERE sp.guild_id = ?
            """
            params = [guild_id]
            
            if channel_id:
                query += " AND sp.channel_id = ?"
                params.append(channel_id)
                
            query += " ORDER BY sp.sequence_id, spm.position"
            cursor.execute(query, params)
            sequential_pins = cursor.fetchall()
            all_pins.extend([{"message_id": mid, "channel_id": cid, "sequence_id": sid} 
                           for mid, cid, sid in sequential_pins])
            
        return all_pins

    async def _handle_pin_pagination(self, ctx: commands.Context, pins_data: List[Dict], per_page: int = 5, message: Optional[discord.Message] = None):
        """Handle pagination for pins display."""
        if not pins_data:
            if message:
                await message.edit(content="No pins found!", embed=None)
            else:
                await ctx.send("No pins found!")
            return

        pages = [pins_data[i:i + per_page] for i in range(0, len(pins_data), per_page)]
        total_pages = len(pages)
        current_page = 0

        # Create single embed for current page
        embed = discord.Embed(
            title="Pinned Messages",
            color=discord.Color.blue(),
            description=""
        )
        embed.set_footer(text=f"Page {current_page + 1}/{total_pages}")

        for pin in pages[current_page]:
            channel = ctx.guild.get_channel(pin["channel_id"])
            if not channel:
                continue
                
            pin_msg = await self._fetch_message_safe(channel, pin["message_id"])
            if not pin_msg:
                continue

            # Add pin content to description
            pin_content = f"**{pin_msg.author.display_name}** {pin_msg.jump_url}\n"
            pin_content += pin_msg.content if pin_msg.content else "No content"
            if pin_msg.attachments:
                pin_content += f"\n[View Attachment]({pin_msg.attachments[0].url})"
            if pin["sequence_id"]:
                pin_content += f"\n*Part of sequence #{pin["sequence_id"]}*"
            pin_content += "\n\n"  # Add spacing between pins
            
            # Add to embed description
            embed.description += pin_content

        # Update existing message or send a new one
        display_msg = message
        if display_msg:
            await display_msg.edit(embed=embed)
        else:
            display_msg = await ctx.send(embed=embed)
        
        # Add navigation reactions
        if total_pages > 1:
            await display_msg.add_reaction("⬅️")
            await display_msg.add_reaction("➡️")

            def check(reaction, user):
                return (
                    user == ctx.author
                    and str(reaction.emoji) in ["⬅️", "➡️"]
                    and reaction.message.id == display_msg.id
                )

            while True:
                try:
                    reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)
                except TimeoutError:
                    await message.clear_reactions()
                    break

                try:
                    await message.remove_reaction(reaction, user)
                except (discord.Forbidden, discord.HTTPException):
                    pass

                if str(reaction.emoji) == "➡️":
                    current_page = (current_page + 1) % total_pages
                elif str(reaction.emoji) == "⬅️":
                    current_page = (current_page - 1) % total_pages

                # Create new embed for current page
                embed = discord.Embed(
                    title="Pinned Messages",
                    color=discord.Color.blue(),
                    description=""
                )
                embed.set_footer(text=f"Page {current_page + 1}/{total_pages}")

                for pin in pages[current_page]:
                    channel = ctx.guild.get_channel(pin["channel_id"])
                    if not channel:
                        continue
                        
                    pin_msg = await self._fetch_message_safe(channel, pin["message_id"])
                    if not pin_msg:
                        continue

                    # Add pin content to description
                    pin_content = f"**{pin_msg.author.display_name}** {pin_msg.jump_url}\n"
                    pin_content += pin_msg.content if pin_msg.content else "No content"
                    if pin_msg.attachments:
                        pin_content += f"\n[View Attachment]({pin_msg.attachments[0].url})"
                    if pin["sequence_id"]:
                        pin_content += f"\n*Part of sequence #{pin["sequence_id"]}*"
                    pin_content += "\n\n"  # Add spacing between pins
                    
                    # Add to embed description
                    embed.description += pin_content

                # Update message with new embed
                await display_msg.edit(embed=embed)
                
    @commands.hybrid_command(
        name="pins",
        description="Display all pins with pagination. Shows both regular and sequential pins."
    )
    @app_commands.describe(
        channel="Optional: Show pins from a specific channel only"
    )
    async def pins(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Display all pins with pagination. Shows both regular and sequential pins.
        
        Parameters
        -----------
        channel: Optional[discord.TextChannel]
            If specified, only show pins from this channel
        """
        # Send a temporary loading message
        loading_embed = discord.Embed(
            title="📍 Fetching Pins...",
            description="Please wait while I gather all the pins" + 
                      (f" from {channel.mention}" if channel else "") + "...",
            color=discord.Color.blue()
        )
        loading_msg = await ctx.send(embed=loading_embed)
        
        # Get the pins data
        pins_data = await self._get_pin_messages(
            ctx.guild.id,
            channel.id if channel else None
        )
        
        # Instead of deleting the loading message, we'll pass it to the pagination handler
        await self._handle_pin_pagination(ctx, pins_data, message=loading_msg)

async def setup(bot):
    await bot.add_cog(PinManagement(bot))
