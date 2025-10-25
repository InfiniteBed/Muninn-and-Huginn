from collections import defaultdict
from dataclasses import dataclass
import asyncio
import datetime
import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from typing import Union, Optional, List, Dict, Set, Tuple
from zoneinfo import ZoneInfo


@dataclass
class PinRecord:
    message_id: int
    channel_id: int
    created_at: datetime.datetime


EVALUATION_DURATION_SECONDS = 3600  # 1 hour voting window
DOWNVOTE_THRESHOLD = 3  # Minimum number of 👎 reactions required to remove a pin
MERCY_THRESHOLD = 3  # Number of votes (👍/👎) to trigger the mercy rule
MAX_SIMULTANEOUS_PROMPTS = 5
CALIFORNIA_TZ = ZoneInfo("America/Los_Angeles")
DAYLIGHT_START = datetime.time(hour=8)  # 8 AM PT assumed daylight start
DAYLIGHT_END = datetime.time(hour=20)   # 8 PM PT assumed daylight end


class PinAuthorSelect(discord.ui.Select):
    def __init__(self, parent_view: "PinAuthorSelectView") -> None:
        self.parent_view = parent_view
        super().__init__(placeholder="Select a user to evaluate", min_values=1, max_values=1, options=[])

    async def callback(self, interaction: discord.Interaction) -> None:
        if not self.values:
            await interaction.response.defer()
            return
        author_id = int(self.values[0])
        await self.parent_view.handle_selection(interaction, author_id)


class PinAuthorSelectView(discord.ui.View):
    def __init__(
        self,
    cog: "PinManagement",
    guild: discord.Guild,
    pins_by_author: Dict[int, List[PinRecord]],
    channel: Union[discord.TextChannel, discord.Thread]
    ) -> None:
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.pins_by_author = pins_by_author
        self.channel = channel
        self.author_ids = sorted(pins_by_author.keys())
        self.per_page = 25
        self.page = 0
        self.message: Optional[discord.Message] = None

        self.select = PinAuthorSelect(self)
        self.add_item(self.select)
        self._refresh_options()

    def _refresh_options(self) -> None:
        start = self.page * self.per_page
        end = start + self.per_page
        subset = self.author_ids[start:end]

        options: List[discord.SelectOption] = []
        for author_id in subset:
            display_name = self.cog._resolve_author_name(self.guild, author_id)
            label = display_name[:100] if display_name else str(author_id)
            options.append(
                discord.SelectOption(
                    label=label,
                    value=str(author_id),
                    description=f"{len(self.pins_by_author[author_id])} message(s)"
                )
            )

        self.select.options = options or [discord.SelectOption(label="No authors available", value="0", default=True)]
        self.select.disabled = not bool(options)

        # Update button state if buttons exist
        if hasattr(self, "previous_page_button"):
            self.previous_page_button.disabled = self.page == 0
        if hasattr(self, "next_page_button"):
            max_index = len(self.author_ids) - 1
            self.next_page_button.disabled = (self.page + 1) * self.per_page > max_index

    async def handle_selection(self, interaction: discord.Interaction, author_id: int) -> None:
        if author_id not in self.pins_by_author:
            await interaction.response.send_message("Couldn't find any pins for that user.", ephemeral=True)
            return

        success = await self.cog.begin_pin_evaluation(
            interaction,
            author_id,
            self.pins_by_author[author_id],
            self.channel
        )

        if success:
            self.stop()

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_page_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.page == 0:
            await interaction.response.defer()
            return

        self.page -= 1
        self._refresh_options()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_page_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        max_page = (len(self.author_ids) - 1) // self.per_page
        if self.page >= max_page:
            await interaction.response.defer()
            return

        self.page += 1
        self._refresh_options()
        await interaction.response.edit_message(view=self)

    async def on_timeout(self) -> None:
        if self.message:
            for item in self.children:
                item.disabled = True
            try:
                await self.message.edit(view=self)
            except (discord.NotFound, discord.HTTPException):
                pass

class PinManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "huginn.db"
        # Add cache structures
        self.pin_cache = defaultdict(lambda: defaultdict(list))  # {guild_id: {channel_id: [message_ids]}}
        self.active_evaluations = {}  # {(guild_id, author_id): asyncio.Task}
        self._init_db()
        self._load_cache()

    def _current_pacific_time(self) -> datetime.datetime:
        return datetime.datetime.now(tz=CALIFORNIA_TZ)

    def _is_within_daylight_hours(self) -> bool:
        now = self._current_pacific_time().time()
        return DAYLIGHT_START <= now < DAYLIGHT_END

    async def _wait_for_daylight_window(self, channel: Union[discord.TextChannel, discord.Thread]) -> None:
        notification_sent = False

        while not self._is_within_daylight_hours():
            now = self._current_pacific_time()
            next_start = datetime.datetime.combine(now.date(), DAYLIGHT_START, tzinfo=CALIFORNIA_TZ)
            if now.time() >= DAYLIGHT_END:
                next_start += datetime.timedelta(days=1)

            if not notification_sent:
                start_str = DAYLIGHT_START.strftime("%I:%M %p").lstrip("0")
                end_str = DAYLIGHT_END.strftime("%I:%M %p").lstrip("0")
                resume_str = next_start.strftime("%I:%M %p %Z").lstrip("0")
                window_text = (
                    f"🌙 Pin evaluations run during daylight hours "
                    f"({start_str}–{end_str} PT). "
                    f"Resuming around {resume_str}."
                )
                try:
                    await channel.send(window_text)
                except (discord.Forbidden, discord.HTTPException):
                    pass
                notification_sent = True

            delay = max((next_start - now).total_seconds(), 60)
            await asyncio.sleep(min(delay, 900))

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pinned_messages (
                    guild_id INTEGER,
                    message_id INTEGER PRIMARY KEY,
                    channel_id INTEGER,
                    user_id INTEGER
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ignored_messages (
                    guild_id INTEGER,
                    message_id INTEGER PRIMARY KEY
                )
            """)
            # Ensure older databases get the new user_id column if it's missing
            cursor.execute("PRAGMA table_info(pinned_messages)")
            cols = [r[1] for r in cursor.fetchall()]
            if 'user_id' not in cols:
                try:
                    cursor.execute("ALTER TABLE pinned_messages ADD COLUMN user_id INTEGER")
                except sqlite3.OperationalError:
                    # If alter fails for any reason, ignore; table may be locked or altered elsewhere
                    pass
            conn.commit()

    def _load_cache(self):
        """Load existing pinned messages into cache from database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Load regular pins
            cursor.execute("SELECT guild_id, channel_id, message_id FROM pinned_messages")
            for guild_id, channel_id, message_id in cursor.fetchall():
                self.pin_cache[guild_id][channel_id].append(message_id)

    def _add_to_cache(self, guild_id: int, channel_id: int, message_id: int):
        """Add a message to the cache"""
        self.pin_cache[guild_id][channel_id].append(message_id)

    def _remove_from_cache(self, guild_id: int, channel_id: int, message_id: int):
        """Remove a message from the cache"""
        if message_id in self.pin_cache[guild_id][channel_id]:
            self.pin_cache[guild_id][channel_id].remove(message_id)

    def _remove_pin_entry(self, guild_id: int, channel_id: int, message_id: int) -> None:
        """Remove a pin from the cache and the persistent store."""
        self._remove_from_cache(guild_id, channel_id, message_id)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM pinned_messages WHERE message_id = ? AND guild_id = ?",
                (message_id, guild_id)
            )
            conn.commit()

    def _resolve_author_name(self, guild: discord.Guild, author_id: int) -> str:
        member = guild.get_member(author_id)
        if member:
            return member.display_name
        return f"Former member ({author_id})"

    async def _collect_pins_by_author(self, guild: discord.Guild) -> Dict[int, List[PinRecord]]:
        pins_by_author: Dict[int, List[PinRecord]] = defaultdict(list)
        stale_entries: List[tuple[int, int]] = []

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT message_id, channel_id FROM pinned_messages WHERE guild_id = ?",
                (guild.id,)
            )
            pinned_rows = cursor.fetchall()

        for message_id, channel_id in pinned_rows:
            channel = guild.get_channel(channel_id)
            if not channel:
                stale_entries.append((message_id, channel_id))
                continue

            message = await self._fetch_message_safe(channel, message_id)
            if not message:
                stale_entries.append((message_id, channel_id))
                continue

            pins_by_author[message.author.id].append(
                PinRecord(
                    message_id=message.id,
                    channel_id=channel_id,
                    created_at=message.created_at
                )
            )

        if stale_entries:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                for message_id, _ in stale_entries:
                    cursor.execute(
                        "DELETE FROM pinned_messages WHERE message_id = ? AND guild_id = ?",
                        (message_id, guild.id)
                    )
                conn.commit()

            for message_id, channel_id in stale_entries:
                self._remove_from_cache(guild.id, channel_id, message_id)

        for records in pins_by_author.values():
            records.sort(key=lambda record: record.created_at)

        return pins_by_author

    def _count_votes(self, message: discord.Message, emoji: str) -> int:
        for reaction in message.reactions:
            if str(reaction.emoji) == emoji:
                count = reaction.count
                if reaction.me:
                    count -= 1
                return max(count, 0)
        return 0

    async def begin_pin_evaluation(
        self,
        interaction: discord.Interaction,
        author_id: int,
        records: List[PinRecord],
        target_channel: Union[discord.TextChannel, discord.Thread]
    ) -> bool:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("This action must be used inside a server.", ephemeral=True)
            return False

        key = (guild.id, author_id)
        if key in self.active_evaluations:
            await interaction.response.send_message("An evaluation for that user is already in progress.", ephemeral=True)
            return False

        author_name = self._resolve_author_name(guild, author_id)

        announcement = (
            f"🔍 Beginning pin evaluation for **{author_name}**. "
            "We'll review up to five pinned messages at once. React with 👍 to keep or 👎 to remove."
        )

        evaluation_channel: Union[discord.TextChannel, discord.Thread] = target_channel
        thread_created = False

        if isinstance(target_channel, discord.TextChannel):
            try:
                announcement_message = await target_channel.send(announcement)
            except (discord.Forbidden, discord.HTTPException):
                await interaction.response.send_message(
                    "I don't have permission to post in that channel, so I can't start the evaluation.",
                    ephemeral=True
                )
                return False

            thread_name = f"Pin review: {author_name}"
            try:
                evaluation_channel = await announcement_message.create_thread(
                    name=thread_name[:100],
                    auto_archive_duration=1440
                )
                thread_created = True
            except (discord.Forbidden, discord.HTTPException):
                evaluation_channel = target_channel
        else:
            try:
                await target_channel.send(announcement)
            except (discord.Forbidden, discord.HTTPException):
                await interaction.response.send_message(
                    "I wasn't able to post in that thread, so I can't start the evaluation.",
                    ephemeral=True
                )
                return False

        if thread_created:
            try:
                await evaluation_channel.send(
                    (
                        f"This thread will host the evaluation. {len(records)} pinned message(s) are queued. "
                        "We'll keep five messages active at a time."
                    )
                )
            except (discord.Forbidden, discord.HTTPException):
                pass

        try:
            await interaction.response.edit_message(
                content=(
                    f"Started evaluation for **{author_name}**. "
                    f"Voting prompts will appear in {evaluation_channel.mention}."
                ),
                view=None
            )
        except discord.HTTPException:
            # If we can't edit the message, fall back to acknowledging via ephemeral response
            try:
                await interaction.followup.send(
                    f"Started evaluation for **{author_name}** in {evaluation_channel.mention}.",
                    ephemeral=True
                )
            except discord.HTTPException:
                pass

        async def _runner() -> None:
            try:
                await self._run_pin_evaluation(guild, author_id, records, evaluation_channel)
            except Exception as exc:
                print(f"Error during pin evaluation for guild {guild.id}, author {author_id}: {exc}")

        task = asyncio.create_task(_runner())
        self.active_evaluations[key] = task

        def _cleanup(finished_task: asyncio.Task) -> None:
            self.active_evaluations.pop(key, None)
            if finished_task.cancelled():
                return
            try:
                finished_task.result()
            except Exception as exc:
                print(f"Pin evaluation task error for guild {guild.id}, author {author_id}: {exc}")

        task.add_done_callback(_cleanup)
        return True

    async def _run_pin_evaluation(
        self,
        guild: discord.Guild,
        author_id: int,
        records: List[PinRecord],
        target_channel: Union[discord.TextChannel, discord.Thread]
    ) -> None:
        author_name = self._resolve_author_name(guild, author_id)
        total_records = len(records)
        if total_records == 0:
            try:
                await target_channel.send("No pinned messages were found for evaluation.")
            except (discord.Forbidden, discord.HTTPException):
                pass
            return

        active_tasks: Set[asyncio.Task] = set()
        index = 0

        while index < total_records or active_tasks:
            while len(active_tasks) < MAX_SIMULTANEOUS_PROMPTS and index < total_records:
                await self._wait_for_daylight_window(target_channel)
                record = records[index]
                index += 1
                task = asyncio.create_task(
                    self._evaluate_single_pin(guild, author_id, record, target_channel)
                )
                active_tasks.add(task)
                await asyncio.sleep(1)

            if not active_tasks:
                break

            done, pending = await asyncio.wait(active_tasks, return_when=asyncio.FIRST_COMPLETED)
            for finished in done:
                try:
                    finished.result()
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    print(f"Pin evaluation task error for guild {guild.id}, author {author_id}: {exc}")
            active_tasks = pending

        try:
            await target_channel.send(f"✅ Finished evaluation for **{author_name}**.")
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def _evaluate_single_pin(
        self,
        guild: discord.Guild,
        author_id: int,
        record: PinRecord,
        target_channel: Union[discord.TextChannel, discord.Thread]
    ) -> None:
        channel = guild.get_channel(record.channel_id)
        if not channel:
            self._remove_pin_entry(guild.id, record.channel_id, record.message_id)
            try:
                await target_channel.send(
                    f"⚠️ Skipping a message (ID {record.message_id}) because the channel no longer exists."
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
            return

        message = await self._fetch_message_safe(channel, record.message_id)
        if not message:
            self._remove_pin_entry(guild.id, record.channel_id, record.message_id)
            try:
                await target_channel.send(
                    f"⚠️ Skipping a message (ID {record.message_id}) because it could not be fetched."
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
            return

        header = (
            f"Evaluating a pinned message from **{message.author.display_name}** in {channel.mention}.\n"
            f"React with 👍 to keep or 👎 to remove. Voting ends in {EVALUATION_DURATION_SECONDS // 60} minute(s)"
            f" or earlier if the mercy threshold of {MERCY_THRESHOLD} votes is reached."
        )
        embed = await self._create_pin_embed(message)

        try:
            prompt = await target_channel.send(header, embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            return

        for emoji in ("👍", "👎"):
            try:
                await prompt.add_reaction(emoji)
            except (discord.Forbidden, discord.HTTPException):
                pass

        prompt, keep_votes, remove_votes, mercy_result = await self._await_votes_with_mercy(prompt)

        removed = False
        removal_notes = ""

        if mercy_result == "remove" or (
            remove_votes >= DOWNVOTE_THRESHOLD and remove_votes > keep_votes
        ):
            self._remove_pin_entry(guild.id, record.channel_id, record.message_id)
            removed = True
            try:
                await message.delete()
                removal_notes = "Original message deleted."
            except (discord.Forbidden, discord.HTTPException):
                removal_notes = "Original message could not be deleted, but it was removed from rotation."
        else:
            removal_notes = "Message retained in pin rotation."

        if mercy_result == "keep":
            removal_notes += " Mercy rule triggered with community support."
        elif mercy_result == "remove":
            removal_notes += " Mercy rule triggered with removal votes."

        summary = (
            f"Result for **{self._resolve_author_name(guild, author_id)}**'s message ({message.jump_url}): "
            f"{'Removed' if removed else 'Kept'} — 👍 {keep_votes} / 👎 {remove_votes}. {removal_notes}"
        )

        try:
            await prompt.edit(content=summary, embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            try:
                await target_channel.send(summary, embed=embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

        try:
            await prompt.clear_reactions()
        except (discord.Forbidden, discord.HTTPException):
            pass

        await asyncio.sleep(2)

    async def _await_votes_with_mercy(
        self,
        prompt: discord.Message
    ) -> Tuple[discord.Message, int, int, Optional[str]]:
        mercy_result: Optional[str] = None
        loop = asyncio.get_running_loop()
        end_time = loop.time() + EVALUATION_DURATION_SECONDS

        current_prompt = prompt
        last_keep = self._count_votes(current_prompt, "👍")
        last_remove = self._count_votes(current_prompt, "👎")

        def _should_track(reaction: discord.Reaction, user: Union[discord.Member, discord.User]) -> bool:
            if reaction.message.id != prompt.id:
                return False
            if user.bot:
                return False
            guild = reaction.message.guild
            if guild and guild.me and user.id == guild.me.id:
                return False
            return True

        while True:
            last_keep = self._count_votes(current_prompt, "👍")
            last_remove = self._count_votes(current_prompt, "👎")

            if last_keep >= MERCY_THRESHOLD:
                mercy_result = "keep"
                break

            if last_remove >= MERCY_THRESHOLD:
                mercy_result = "remove"
                break

            remaining = end_time - loop.time()
            if remaining <= 0:
                break

            try:
                await self.bot.wait_for(
                    "reaction_add",
                    timeout=min(remaining, 30),
                    check=_should_track
                )
            except asyncio.TimeoutError:
                pass

            try:
                current_prompt = await current_prompt.channel.fetch_message(current_prompt.id)
            except discord.NotFound:
                break

        try:
            current_prompt = await current_prompt.channel.fetch_message(current_prompt.id)
            last_keep = self._count_votes(current_prompt, "👍")
            last_remove = self._count_votes(current_prompt, "👎")
        except discord.NotFound:
            pass

        return current_prompt, last_keep, last_remove, mercy_result

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
                                # Add to cache and database (user_id unknown at pin time)
                                self._add_to_cache(message.guild.id, message.channel.id, recent_pin.id)
                                cursor.execute(
                                    "INSERT INTO pinned_messages (guild_id, message_id, channel_id, user_id) VALUES (?, ?, ?, ?)",
                                    (message.guild.id, recent_pin.id, message.channel.id, None)
                                )
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
                    cursor.execute(
                        "INSERT OR IGNORE INTO pinned_messages (guild_id, message_id, channel_id, user_id) VALUES (?, ?, ?, ?)",
                        (ctx.guild.id, message.id, message.channel.id, None)
                    )
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

    @commands.command(name="pin_delete_by_user")
    @commands.has_permissions(manage_messages=True)
    async def pin_delete_by_user(self, ctx: commands.Context, user: discord.User):
        """Permanently remove all stored pins created by the specified user."""
        if not ctx.guild:
            await ctx.send("This command can only be used inside a server.")
            return

        target_id = user.id
        member = ctx.guild.get_member(target_id)
        display_name = member.display_name if member else getattr(user, "name", str(target_id))

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT message_id, channel_id FROM pinned_messages WHERE guild_id = ?",
                (ctx.guild.id,)
            )
            stored_pins = cursor.fetchall()

        if not stored_pins:
            await ctx.send("No stored pins were found for this server.")
            return

        total = len(stored_pins)
        processed = 0
        deleted = 0
        stale = 0

        progress_message = await ctx.send(
            f"Scanning {total} stored pin(s) for content by {display_name}..."
        )

        update_interval = max(1, total // 20)

        def build_progress_bar(done: int, max_value: int, width: int = 20) -> str:
            if max_value == 0:
                return "[--------------------]"
            filled = int(width * done / max_value)
            filled = min(width, filled)
            empty = width - filled
            return "[" + "#" * filled + "-" * empty + "]"

        for message_id, channel_id in stored_pins:
            processed += 1
            channel = ctx.guild.get_channel(channel_id)

            if not channel:
                self._remove_pin_entry(ctx.guild.id, channel_id, message_id)
                stale += 1
                if processed % update_interval == 0 or processed == total:
                    bar = build_progress_bar(processed, total)
                    await progress_message.edit(
                        content=(
                            f"Scanning pins for {display_name}\n"
                            f"{bar} {processed}/{total} processed\n"
                            f"Removed {deleted} matching pin(s)\n"
                            f"Cleared {stale} stale record(s)"
                        )
                    )
                continue

            message = await self._fetch_message_safe(channel, message_id)

            if message is None:
                self._remove_pin_entry(ctx.guild.id, channel_id, message_id)
                stale += 1
            elif message.author.id == target_id:
                await self._remove_pin_entry(ctx.guild.id, channel_id, message_id)
                deleted += 1
                try:
                    if any(reaction.emoji == "📌" and reaction.me for reaction in message.reactions):
                        await message.remove_reaction("📌", self.bot.user)  # type: ignore[arg-type]
                except (discord.Forbidden, discord.HTTPException):
                    pass

            if processed % update_interval == 0 or processed == total:
                bar = build_progress_bar(processed, total)
                await progress_message.edit(
                    content=(
                        f"Scanning pins for {display_name}\n"
                        f"{bar} {processed}/{total} processed\n"
                        f"Removed {deleted} matching pin(s)\n"
                        f"Cleared {stale} stale record(s)"
                    )
                )

        summary = (
            f"Finished deleting pins for {display_name}. "
            f"Removed {deleted} pin(s) and cleared {stale} stale record(s)."
        )

        await progress_message.edit(content=summary)
        await ctx.send(summary)

    @commands.command(name="pin_assign_user")
    @commands.has_permissions(manage_messages=True)
    async def pin_assign_user(self, ctx: commands.Context, user: Optional[discord.User] = None):
        """Populate the `user_id` column for stored pins.

        If a user is provided, the command will set that user's ID on all stored pins (legacy behavior).
        If no user is provided, the command will fetch each stored message from Discord and set the
        `user_id` to the actual message author's ID. Progress updates occur after each Discord fetch
        because those API calls are the slow part of the operation.
        """
        if not ctx.guild:
            await ctx.send("This command can only be used inside a server.")
            return

        # Load stored pins first
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT message_id, channel_id, user_id FROM pinned_messages WHERE guild_id = ?",
                (ctx.guild.id,)
            )
            stored_pins = cursor.fetchall()

        if not stored_pins:
            await ctx.send("No stored pins were found for this server.")
            return

        total = len(stored_pins)
        processed = 0
        updated = 0
        skipped = 0
        stale = 0

        if user:
            # Legacy mode: set provided user ID on every stored pin
            target_id = user.id
            member = ctx.guild.get_member(target_id)
            display_name = member.display_name if member else getattr(user, "name", str(target_id))
            progress_message = await ctx.send(f"Assigning {display_name} to {total} stored pin(s)...")
            update_interval = max(1, total // 20)

            def build_progress_bar(done: int, max_value: int, width: int = 20) -> str:
                if max_value == 0:
                    return "[--------------------]"
                filled = int(width * done / max_value)
                filled = min(width, filled)
                empty = width - filled
                return "[" + "#" * filled + "-" * empty + "]"

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                for message_id, channel_id, current_user in stored_pins:
                    processed += 1
                    if current_user == target_id:
                        skipped += 1
                    else:
                        try:
                            cursor.execute(
                                "UPDATE pinned_messages SET user_id = ? WHERE message_id = ? AND guild_id = ?",
                                (target_id, message_id, ctx.guild.id)
                            )
                            conn.commit()
                            updated += 1
                        except Exception:
                            pass

                    if processed % update_interval == 0 or processed == total:
                        bar = build_progress_bar(processed, total)
                        await progress_message.edit(
                            content=(
                                f"Assigning {display_name} to pins\n"
                                f"{bar} {processed}/{total} processed\n"
                                f"Updated {updated} pin(s)\n"
                                f"Skipped {skipped} already-assigned pin(s)\n"
                                f"Cleared {stale} stale record(s)"
                            )
                        )

            summary = (
                f"Finished assigning {display_name}. Updated {updated} pin(s), skipped {skipped} already-assigned pin(s)."
            )
            await progress_message.edit(content=summary)
            await ctx.send(summary)
            return

        # Default mode: inspect each message via Discord to determine the author
        progress_message = await ctx.send(f"Searching Discord for authors on {total} stored pin(s)...")
        update_interval = max(1, total // 20)

        def build_progress_bar(done: int, max_value: int, width: int = 20) -> str:
            if max_value == 0:
                return "[--------------------]"
            filled = int(width * done / max_value)
            filled = min(width, filled)
            empty = width - filled
            return "[" + "#" * filled + "-" * empty + "]"

        # Iterate and fetch message objects (the slow part). Update progress after each fetch.
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for message_id, channel_id, current_user in stored_pins:
                processed += 1

                channel = ctx.guild.get_channel(channel_id)
                message_obj = None
                if channel:
                    # This is the Discord API call that takes the longest
                    message_obj = await self._fetch_message_safe(channel, message_id)

                if message_obj is None:
                    # Could not fetch message; mark as stale (do not delete by default)
                    try:
                        cursor.execute(
                            "UPDATE pinned_messages SET user_id = ? WHERE message_id = ? AND guild_id = ?",
                            (None, message_id, ctx.guild.id)
                        )
                        conn.commit()
                        stale += 1
                    except Exception:
                        pass
                else:
                    author_id = message_obj.author.id
                    if current_user == author_id:
                        skipped += 1
                    else:
                        try:
                            cursor.execute(
                                "UPDATE pinned_messages SET user_id = ? WHERE message_id = ? AND guild_id = ?",
                                (author_id, message_id, ctx.guild.id)
                            )
                            conn.commit()
                            updated += 1
                        except Exception:
                            pass

                if processed % update_interval == 0 or processed == total:
                    bar = build_progress_bar(processed, total)
                    await progress_message.edit(
                        content=(
                            f"Searching Discord for authors\n"
                            f"{bar} {processed}/{total} fetched\n"
                            f"Updated {updated} pin(s)\n"
                            f"Skipped {skipped} already-correct pin(s)\n"
                            f"Cleared {stale} stale record(s)"
                        )
                    )

        summary = (
            f"Finished populating authors. Updated {updated} pin(s), skipped {skipped} already-correct pin(s), "
            f"and noted {stale} stale record(s)."
        )

        await progress_message.edit(content=summary)
        await ctx.send(summary)

    @commands.hybrid_command(
        name="evaluatepins",
        description="Launch the pinned message evaluation workflow"
    )
    @commands.has_permissions(manage_messages=True)
    async def evaluate_pins(self, ctx: commands.Context):
        if not ctx.guild:
            await ctx.send("This command can only be used inside a server.")
            return

        if ctx.interaction:
            await ctx.defer()
            send_message = ctx.followup.send
        else:
            send_message = ctx.send

        status_message: Optional[discord.Message] = None
        try:
            status_message = await send_message(
                "📝 Gathering pinned messages for evaluation…",
                suppress_embeds=True
            )
        except discord.HTTPException:
            status_message = None

        pins_by_author = await self._collect_pins_by_author(ctx.guild)

        total_pins = sum(len(records) for records in pins_by_author.values())
        author_count = len(pins_by_author)

        progress_text = (
            "✅ Finished gathering pinned messages.\n"
            if total_pins
            else "⚠️ No pinned messages found during the scan."
        )
        if total_pins:
            progress_text += (
                f"Discovered {total_pins} message(s) from {author_count} author(s)."
                if author_count
                else "Discovered stored pins, but no associated authors could be resolved."
            )
        else:
            progress_text += ""

        if status_message:
            try:
                await status_message.edit(content=progress_text)
            except discord.HTTPException:
                status_message = None
        elif total_pins:
            try:
                status_message = await send_message(progress_text, suppress_embeds=True)
            except discord.HTTPException:
                status_message = None

        if not pins_by_author:
            if status_message:
                try:
                    await status_message.edit(content="⚠️ No stored pinned messages are available for evaluation.")
                except discord.HTTPException:
                    pass
            else:
                if ctx.interaction:
                    await ctx.followup.send("No stored pinned messages are available for evaluation.", ephemeral=True)
                else:
                    await ctx.send("No stored pinned messages are available for evaluation.")
            return

        channel = ctx.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            fallback = ctx.guild.system_channel
            if fallback is None:
                if status_message:
                    try:
                        await status_message.edit(content="Unable to determine a text channel for evaluation prompts.")
                    except discord.HTTPException:
                        pass
                else:
                    await send_message("Unable to determine a text channel for evaluation prompts.")
                return
            channel = fallback

        view = PinAuthorSelectView(self, ctx.guild, pins_by_author, channel)  # type: ignore[arg-type]
        final_prompt = (
            "Select a user whose pinned messages you would like to evaluate:"
            f"\nCurrently tracking {total_pins} message(s) across {author_count} author(s)."
        )

        if status_message:
            try:
                message = await status_message.edit(content=final_prompt, view=view)
            except discord.HTTPException:
                message = await send_message(final_prompt, view=view)
        else:
            message = await send_message(final_prompt, view=view)

        if isinstance(message, discord.Message):
            view.message = message

    async def _create_pin_embed(self, message: discord.Message) -> discord.Embed:
        """Create an embed for a pinned message."""
        avatar_url = str(message.author.display_avatar.url)
        embed = discord.Embed(
            description=message.content or "No content",
            color=discord.Color.blue(),
            timestamp=message.created_at
        )

        embed.set_author(
            name=message.author.display_name,
            icon_url=avatar_url
        )

        embed.add_field(
            name="Source",
            value=message.jump_url,
            inline=False
        )

        if message.attachments:
            embed.set_image(url=message.attachments[0].url)

        return embed

    async def _get_pin_messages(self, guild_id: int, channel_id: Optional[int] = None) -> List[Dict]:
        """Get all pinned messages for a guild, optionally filtered by channel."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            query = """
                SELECT pm.message_id, pm.channel_id
                FROM pinned_messages pm
                WHERE pm.guild_id = ?
            """
            params = [guild_id]

            if channel_id:
                query += " AND pm.channel_id = ?"
                params.append(channel_id)

            cursor.execute(query, params)
            return [{"message_id": mid, "channel_id": cid} for mid, cid in cursor.fetchall()]

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

        async def build_embed(page_index: int) -> discord.Embed:
            embed = discord.Embed(
                title="Pinned Messages",
                color=discord.Color.blue(),
                description=""
            )
            embed.set_footer(text=f"Page {page_index + 1}/{total_pages}")

            for pin in pages[page_index]:
                channel = ctx.guild.get_channel(pin["channel_id"])
                if not channel:
                    continue

                pin_msg = await self._fetch_message_safe(channel, pin["message_id"])
                if not pin_msg:
                    continue

                pin_content = f"**{pin_msg.author.display_name}** {pin_msg.jump_url}\n"
                pin_content += pin_msg.content if pin_msg.content else "No content"
                if pin_msg.attachments:
                    pin_content += f"\n[View Attachment]({pin_msg.attachments[0].url})"
                pin_content += "\n\n"

                embed.description += pin_content

            return embed

        display_msg = message
        first_embed = await build_embed(current_page)
        if display_msg:
            await display_msg.edit(embed=first_embed, content=None)
        else:
            display_msg = await ctx.send(embed=first_embed)

        if total_pages <= 1:
            return

        for emoji in ("⬅️", "➡️"):
            try:
                await display_msg.add_reaction(emoji)
            except (discord.Forbidden, discord.HTTPException):
                return

        def check(reaction: discord.Reaction, user: Union[discord.Member, discord.User]):
            return (
                user == ctx.author
                and str(reaction.emoji) in {"⬅️", "➡️"}
                and reaction.message.id == display_msg.id
            )

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)
            except asyncio.TimeoutError:
                try:
                    await display_msg.clear_reactions()
                except (discord.Forbidden, discord.HTTPException):
                    pass
                break

            try:
                await display_msg.remove_reaction(reaction.emoji, user)
            except (discord.Forbidden, discord.HTTPException):
                pass

            if str(reaction.emoji) == "➡️":
                current_page = (current_page + 1) % total_pages
            else:
                current_page = (current_page - 1) % total_pages

            updated_embed = await build_embed(current_page)
            await display_msg.edit(embed=updated_embed)

    @commands.hybrid_command(
        name="pins",
        description="Display stored pinned messages with pagination"
    )
    @app_commands.describe(
        channel="Optional: Show pins from a specific channel only"
    )
    async def pins(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Display stored pinned messages with pagination.
        
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
