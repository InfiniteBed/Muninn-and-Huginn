import discord
from discord.ext import commands, tasks
from discord.ui import Modal, TextInput, View, Select
import sqlite3
from datetime import datetime, time
import pytz

def get_time(hour, minute=0):
    """Helper function to generate localized time."""
    now = datetime.now(pytz.timezone("US/Pacific"))
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0).timetz()

class DevotionModal(Modal):
    def __init__(self, user, devotion_type):
        super().__init__(title=f"Share Your {devotion_type}")
        self.user = user
        self.devotion_type = devotion_type
        
        # When input
        self.when_input = TextInput(
            label="When did you have your devotion?",
            placeholder="e.g., 'This morning', 'During lunch break', 'Before bed'...",
            required=True,
            max_length=200
        )
        self.add_item(self.when_input)
        
        # What input (optional)
        self.what_input = TextInput(
            label="What did God speak to you?",
            placeholder="Share what the Holy Spirit was leading you to today (be as vague or detailed as you want)",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=1000
        )
        self.add_item(self.what_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Create response embed
        embed = discord.Embed(
            title=f"{self.user.display_name}'s {self.devotion_type} Sharing",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=self.user.avatar.url if self.user.avatar else self.user.default_avatar.url)
        embed.add_field(name="When", value=self.when_input.value, inline=False)
        
        if self.what_input.value.strip():
            embed.add_field(name="What God was leading me to", value=self.what_input.value, inline=False)
        
        # Log to database and get streak info
        devotion_cog = interaction.client.get_cog('DevotionAccountability')
        if devotion_cog:
            # Get current streak before logging (to check for new record)
            old_current, old_longest, _, _ = devotion_cog._get_user_streak(self.user.id, interaction.guild.id)
            
            streak_info = devotion_cog._log_devotion_response(
                self.user.id, 
                interaction.guild.id,
                "yes", 
                self.when_input.value, 
                self.what_input.value
            )
            
            # Add streak information if we have it
            if streak_info:
                current_streak, longest_streak, is_updated = streak_info
                if is_updated and current_streak > 0:
                    is_new_record = longest_streak > old_longest
                    streak_message = devotion_cog._generate_streak_message(current_streak, longest_streak, is_new_record)
                    embed.add_field(name="🔥 Devotion Streak", value=f"{streak_message}\n**Current:** {current_streak} days | **Best:** {longest_streak} days", inline=False)
            else:
                # Get updated streak info if streak_info is None (same day submission)
                current_streak, longest_streak, _, _ = devotion_cog._get_user_streak(self.user.id, interaction.guild.id)
                if current_streak > 0:
                    embed.add_field(name="🔥 Devotion Streak", value=f"**Current:** {current_streak} days | **Best:** {longest_streak} days", inline=False)
        
        embed.set_footer(text="Keep growing in faith!")
        
        await interaction.response.send_message(embed=embed)

class DevotionSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Yes! I had my devotion time today 🙌",
                description="I read my Bible and/or prayed today",
                emoji="✅",
                value="yes"
            ),
            discord.SelectOption(
                label="Not yet, but I plan to",
                description="I haven't had my devotion time yet today",
                emoji="⏰",
                value="later"
            ),
            discord.SelectOption(
                label="No, I didn't have time today",
                description="I didn't have devotion time today",
                emoji="❌",
                value="no"
            )
        ]
        super().__init__(placeholder="Choose your devotion status for today...", options=options)

    async def callback(self, interaction: discord.Interaction):
        devotion_cog = interaction.client.get_cog('DevotionAccountability')
        if not devotion_cog:
            await interaction.response.send_message("❌ Devotion system not available.", ephemeral=True)
            return

        # Check if user has already submitted today
        if devotion_cog._has_responded_today(interaction.user.id, interaction.guild.id):
            embed = discord.Embed(
                title="Already Submitted Today! ✅",
                description=(
                    f"{interaction.user.mention}, you've already submitted your final devotion response for today! 😊\n\n"
                    "Check your progress with `!my_devotions` or view server stats with `!devotion_stats`"
                ),
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=False)
            return

        has_said_later = devotion_cog._has_said_later_today(interaction.user.id, interaction.guild.id)
        response = self.values[0]

        if response == 'yes':
            # Show modal for sharing details
            modal = DevotionModal(interaction.user, "Bible Reading/Prayer Time")
            await interaction.response.send_modal(modal)
        elif response == 'later':
            # Log response but don't block future submissions
            devotion_cog._log_devotion_response(interaction.user.id, interaction.guild.id, "not_yet")
            if has_said_later:
                description = f"{interaction.user.mention}, no worries! Still plenty of time left in the day. You can submit again when you're ready."
            else:
                description = f"{interaction.user.mention}, there's still time today to spend time with God! You can submit again later."
            embed = discord.Embed(
                title="That's okay! 💪",
                description=description,
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed, ephemeral=False)
        elif response == 'no':
            # Log response
            devotion_cog._log_devotion_response(interaction.user.id, interaction.guild.id, "no")
            if has_said_later:
                description = f"{interaction.user.mention}, thank you for being honest! Even though you didn't have time today, tomorrow is a fresh opportunity to spend time with God."
            else:
                description = f"{interaction.user.mention}, thank you for being honest! Tomorrow is a fresh opportunity to spend time with God."
            embed = discord.Embed(
                title="Tomorrow's a new day! 🌅",
                description=description,
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=False)

class DevotionSelectView(View):
    def __init__(self, timeout=3600):  # 1 hour timeout
        super().__init__(timeout=timeout)
        self.add_item(DevotionSelect())

class DevotionAccountability(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "discord.db"
        self.california_tz = pytz.timezone('US/Pacific')
        
        # Initialize with default times - actual times will be pulled from server config
        self.default_hour = 18  # 6:00 PM Pacific (default)
        self.default_minute = 0
        
        self._initialize_database()
        
        # Start a loop that checks every minute and determines if any server needs a devotion message
        self.devotion_scheduler = tasks.loop(minutes=1)(self.devotion_scheduler_task)
        self.devotion_scheduler.start()

    def cog_unload(self):
        self.devotion_scheduler.cancel()

    def _get_server_devotion_time(self, guild_id):
        """Get the configured devotion time for a specific server."""
        server_config_cog = self.bot.get_cog('ServerConfig')
        if not server_config_cog:
            return self.default_hour, self.default_minute
        
        hour = server_config_cog.get_config(guild_id, 'devotion_hour', self.default_hour)
        minute = server_config_cog.get_config(guild_id, 'devotion_minute', self.default_minute)
        return hour, minute

    def _should_send_devotion_now(self, guild_id):
        """Check if it's time to send devotion message for this guild."""
        server_config_cog = self.bot.get_cog('ServerConfig')
        if not server_config_cog:
            return False
        
        # Check if devotion is enabled for this guild
        enabled = server_config_cog.get_config(guild_id, 'devotion_enabled', True)
        if not enabled:
            return False
        
        # Check if there's a devotion channel configured
        channel_id = server_config_cog.get_config(guild_id, 'devotion_channel')
        if not channel_id:
            return False
        
        # Get configured time
        hour, minute = self._get_server_devotion_time(guild_id)
        
        # Get current Pacific time
        now = datetime.now(self.california_tz)
        
        # Check if current time matches configured time (within the current minute)
        return now.hour == hour and now.minute == minute

    def _initialize_database(self):
        """Initialize the database table for devotion tracking."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS devotion_responses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    response_type TEXT NOT NULL,
                    when_text TEXT,
                    what_text TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    date_responded DATE NOT NULL
                )
            """)
            
            # Add streaks table for tracking devotion streaks
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS devotion_streaks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    current_streak INTEGER DEFAULT 0,
                    longest_streak INTEGER DEFAULT 0,
                    last_devotion_date DATE,
                    streak_start_date DATE,
                    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, guild_id)
                )
            """)
            conn.commit()

    def _log_devotion_response(self, user_id, guild_id, response_type, when_text=None, what_text=None):
        """Log a user's devotion response to the database."""
        today = datetime.now(self.california_tz).date()
        timestamp = datetime.now(self.california_tz).strftime("%Y-%m-%d %H:%M:%S")
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO devotion_responses 
                (user_id, guild_id, response_type, when_text, what_text, timestamp, date_responded)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, guild_id, response_type, when_text, what_text, timestamp, today))
            
            # Update streak if response is 'yes'
            if response_type == 'yes':
                streak_info = self._update_streak(cursor, user_id, guild_id, today)
                # streak_info will be None if it's a same-day submission
            
            conn.commit()
            return streak_info  # Return streak info for use in responses

    def _update_streak(self, cursor, user_id, guild_id, today):
        """Update the user's devotion streak."""
        # Get current streak data
        cursor.execute("""
            SELECT current_streak, longest_streak, last_devotion_date, streak_start_date
            FROM devotion_streaks 
            WHERE user_id = ? AND guild_id = ?
        """, (user_id, guild_id))
        
        row = cursor.fetchone()
        
        if row:
            current_streak, longest_streak, last_devotion_date, streak_start_date = row
            last_date = datetime.strptime(last_devotion_date, '%Y-%m-%d').date() if last_devotion_date else None
            
            # Check if this continues the streak (consecutive days)
            if last_date and (today - last_date).days == 1:
                # Continue streak
                current_streak += 1
            elif last_date == today:
                # Same day, don't update streak (but return current info)
                return current_streak, longest_streak, False
            else:
                # Streak broken or first devotion, start new streak
                current_streak = 1
                streak_start_date = today.strftime('%Y-%m-%d')
            
            # Update longest streak if current is longer
            longest_streak = max(longest_streak, current_streak)
            
            cursor.execute("""
                UPDATE devotion_streaks 
                SET current_streak = ?, longest_streak = ?, last_devotion_date = ?, 
                    streak_start_date = ?, last_updated = ?
                WHERE user_id = ? AND guild_id = ?
            """, (current_streak, longest_streak, today.strftime('%Y-%m-%d'), 
                  streak_start_date, datetime.now(self.california_tz).strftime("%Y-%m-%d %H:%M:%S"),
                  user_id, guild_id))
        else:
            # First devotion for this user
            current_streak = 1
            longest_streak = 1
            cursor.execute("""
                INSERT INTO devotion_streaks 
                (user_id, guild_id, current_streak, longest_streak, last_devotion_date, 
                 streak_start_date, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, guild_id, current_streak, longest_streak, today.strftime('%Y-%m-%d'),
                  today.strftime('%Y-%m-%d'), datetime.now(self.california_tz).strftime("%Y-%m-%d %H:%M:%S")))
        
        return current_streak, longest_streak, True

    def _get_user_streak(self, user_id, guild_id):
        """Get the current streak information for a user."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT current_streak, longest_streak, last_devotion_date, streak_start_date
                FROM devotion_streaks 
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))
            
            row = cursor.fetchone()
            if row:
                current_streak, longest_streak, last_devotion_date, streak_start_date = row
                
                # Check if streak is still active (last devotion was yesterday or today)
                if last_devotion_date:
                    last_date = datetime.strptime(last_devotion_date, '%Y-%m-%d').date()
                    today = datetime.now(self.california_tz).date()
                    days_since = (today - last_date).days
                    
                    if days_since > 1:
                        # Streak is broken
                        current_streak = 0
                
                return current_streak, longest_streak, last_devotion_date, streak_start_date
            else:
                return 0, 0, None, None

    def _generate_streak_message(self, current_streak, longest_streak, is_new_record=False):
        """Generate a congratulatory message for streaks."""
        if is_new_record and current_streak > 1:
            return f"🎊 NEW PERSONAL RECORD! {current_streak} days! Previous best was {longest_streak - 1}!"
        
        if current_streak == 1:
            return "🎉 Great start! You've begun a new devotion streak!"
        elif current_streak <= 3:
            return f"🔥 {current_streak} days in a row! Keep it up!"
        elif current_streak <= 7:
            return f"💪 Amazing! {current_streak} day streak! You're building a strong habit!"
        elif current_streak <= 30:
            return f"🌟 Incredible! {current_streak} days strong! God is pleased with your faithfulness!"
        elif current_streak <= 100:
            return f"⭐ PHENOMENAL! {current_streak} days of devotion! You're an inspiration!"
        else:
            return f"🏆 LEGENDARY! {current_streak} days! Your dedication is absolutely incredible!"

    async def devotion_scheduler_task(self):
        """Check each guild and send devotion messages if it's time."""
        try:
            for guild in self.bot.guilds:
                if self._should_send_devotion_now(guild.id):
                    server_config_cog = self.bot.get_cog('ServerConfig')
                    if server_config_cog:
                        channel_id = server_config_cog.get_config(guild.id, 'devotion_channel')
                        if channel_id:
                            channel = self.bot.get_channel(channel_id)
                            if channel:
                                try:
                                    # Check if we already sent today to avoid duplicates
                                    if not self._has_sent_today(guild.id):
                                        await self.send_devotion_message(channel)
                                        self._mark_sent_today(guild.id)
                                        print(f"Sent devotion message to {guild.name} - #{channel.name}")
                                except Exception as e:
                                    print(f"Error sending devotion message to {guild.name}: {e}")
                            else:
                                print(f"Devotion channel {channel_id} not found in {guild.name}")
        except Exception as e:
            print(f"Error in devotion scheduler: {e}")

    def _has_sent_today(self, guild_id):
        """Check if we've already sent a devotion message today for this guild."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) FROM devotion_sent_log 
                    WHERE guild_id = ? AND date_sent = date('now')
                """, (guild_id,))
                count = cursor.fetchone()[0]
                return count > 0
        except sqlite3.Error:
            # Table doesn't exist yet, so we haven't sent today
            return False

    def _mark_sent_today(self, guild_id):
        """Mark that we've sent a devotion message today for this guild."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Create table if it doesn't exist
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS devotion_sent_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id INTEGER NOT NULL,
                        date_sent DATE NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(guild_id, date_sent)
                    )
                """)
                
                # Insert today's log entry
                cursor.execute("""
                    INSERT OR IGNORE INTO devotion_sent_log (guild_id, date_sent)
                    VALUES (?, date('now'))
                """, (guild_id,))
                
                conn.commit()
        except Exception as e:
            print(f"Error marking devotion sent for guild {guild_id}: {e}")

    def _get_devotion_channel(self, guild_id: int):
        """Get the configured devotion channel for a guild (legacy method for compatibility)."""
        server_config_cog = self.bot.get_cog('ServerConfig')
        if server_config_cog:
            return server_config_cog.get_config(guild_id, 'devotion_channel')
        return None

    async def send_devotion_message(self, channel):
        """Send the daily devotion accountability message."""
        embed = discord.Embed(
            title="Faith Check-In",
            description=(
                "Time for our daily accountability check-in!"
            ),
            color=discord.Color.blue()
        )
        view = DevotionSelectView()
        message = await channel.send(embed=embed, view=view)
        
        print(f"Sent daily devotion check-in message to {channel.name}")

    @commands.command(name="devotion")
    async def manual_devotion(self, ctx):
        """Manually send the devotion accountability message."""
        server_config_cog = self.bot.get_cog('ServerConfig')
        if not server_config_cog:
            await ctx.send("❌ Server configuration system not available.")
            return
        
        # Check if there's a configured devotion channel
        channel_id = server_config_cog.get_config(ctx.guild.id, 'devotion_channel')
        
        if channel_id:
            # Send to configured channel
            channel = self.bot.get_channel(channel_id)
            if channel:
                await self.send_devotion_message(channel)
                await ctx.send(f"✅ Devotion check-in message sent to {channel.mention}!")
            else:
                await ctx.send("❌ Configured devotion channel not found. Please update your server configuration.")
        else:
            # Send to current channel and inform about configuration
            await self.send_devotion_message(ctx.channel)
            embed = discord.Embed(
                title="Devotion Message Sent ✅",
                description=(
                    f"Devotion check-in message sent to {ctx.channel.mention}!\n\n"
                    "💡 **Tip:** Set a dedicated devotion channel for daily automated messages:\n"
                    "`!config devotion_channel #your-channel`"
                ),
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)

    @commands.command(name="devotion_stats")
    async def devotion_stats(self, ctx, days: int = 7):
        """Show devotion statistics for the server."""
        if days > 30:
            days = 30  # Limit to 30 days max
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get stats for the last X days
            cursor.execute("""
                SELECT response_type, COUNT(*) as count
                FROM devotion_responses 
                WHERE guild_id = ? AND date_responded >= date('now', '-{} days')
                GROUP BY response_type
                ORDER BY count DESC
            """.format(days), (ctx.guild.id,))
            
            stats = cursor.fetchall()
            
            if not stats:
                await ctx.send(f"No devotion responses recorded in the last {days} days.")
                return
            
            # Get total unique users who responded
            cursor.execute("""
                SELECT COUNT(DISTINCT user_id) as unique_users
                FROM devotion_responses 
                WHERE guild_id = ? AND date_responded >= date('now', '-{} days')
            """.format(days), (ctx.guild.id,))
            
            unique_users = cursor.fetchone()[0]
            
            embed = discord.Embed(
                title=f"Devotion Stats - Last {days} Days 📊",
                color=discord.Color.green()
            )
            
            total_responses = sum(count for _, count in stats)
            embed.add_field(name="Total Responses", value=str(total_responses), inline=True)
            embed.add_field(name="Unique Participants", value=str(unique_users), inline=True)
            
            # Add streak information
            cursor.execute("""
                SELECT COUNT(*) as active_streaks, MAX(current_streak) as longest_current
                FROM devotion_streaks 
                WHERE guild_id = ? AND current_streak > 0 
                AND date(last_devotion_date) >= date('now', '-1 day')
            """, (ctx.guild.id,))
            
            streak_info = cursor.fetchone()
            if streak_info:
                active_streaks, longest_current = streak_info
                embed.add_field(name="🔥 Active Streaks", value=str(active_streaks or 0), inline=True)
            
            embed.add_field(name="━━━━━━━━━━━━━━━", value="", inline=False)
            
            for response_type, count in stats:
                emoji = {"yes": "✅", "no": "❌", "not_yet": "⏰"}.get(response_type, "📝")
                percentage = (count / total_responses) * 100
                embed.add_field(
                    name=f"{emoji} {response_type.replace('_', ' ').title()}", 
                    value=f"{count} ({percentage:.1f}%)", 
                    inline=True
                )
            
            embed.set_footer(text="Keep encouraging each other in faith! 🙏 Use !streak_stats for detailed streak info")
            await ctx.send(embed=embed)

    @commands.command(name="my_devotions")
    async def my_devotions(self, ctx, days: int = 7):
        """Show your personal devotion history."""
        if days > 30:
            days = 30  # Limit to 30 days max
            
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT response_type, when_text, what_text, date_responded
                FROM devotion_responses 
                WHERE user_id = ? AND guild_id = ? AND date_responded >= date('now', '-{} days')
                ORDER BY date_responded DESC
            """.format(days), (ctx.author.id, ctx.guild.id))
            
            history = cursor.fetchall()
            
            if not history:
                await ctx.send(f"No devotion responses found for the last {days} days.")
                return
            
            embed = discord.Embed(
                title=f"Your Devotion Journey - Last {days} Days 📖",
                color=discord.Color.blue()
            )
            embed.set_thumbnail(url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
            
            # Add streak information at the top
            current_streak, longest_streak, _, _ = self._get_user_streak(ctx.author.id, ctx.guild.id)
            if current_streak > 0 or longest_streak > 0:
                streak_text = f"🔥 **Current Streak:** {current_streak} days"
                if longest_streak > 0:
                    streak_text += f" | 🏆 **Personal Best:** {longest_streak} days"
                embed.add_field(name="Streak Progress", value=streak_text, inline=False)
                embed.add_field(name="━━━━━━━━━━━━━━━", value="", inline=False)
            
            for response_type, when_text, what_text, date_responded in history[:10]:  # Limit to 10 most recent
                emoji = {"yes": "✅", "no": "❌", "not_yet": "⏰"}.get(response_type, "📝")
                
                field_value = f"{emoji} {response_type.replace('_', ' ').title()}"
                if when_text:
                    field_value += f"\n**When:** {when_text}"
                if what_text:
                    field_value += f"\n**Reflection:** {what_text[:100]}{'...' if len(what_text) > 100 else ''}"
                
                embed.add_field(
                    name=date_responded,
                    value=field_value,
                    inline=False
                )
            
            if len(history) > 10:
                embed.set_footer(text=f"Showing 10 most recent entries out of {len(history)} total")
            else:
                embed.set_footer(text="Keep growing in your faith! 🌱")
            
            await ctx.send(embed=embed)

    @commands.command(name="devotion_setup")
    @commands.has_permissions(administrator=True)
    async def devotion_setup(self, ctx):
        """Check and configure devotion settings for this server."""
        server_config_cog = self.bot.get_cog('ServerConfig')
        if not server_config_cog:
            await ctx.send("❌ Server configuration system not available.")
            return
        
        channel_id = server_config_cog.get_config(ctx.guild.id, 'devotion_channel')
        devotion_hour = server_config_cog.get_config(ctx.guild.id, 'devotion_hour', 18)
        devotion_minute = server_config_cog.get_config(ctx.guild.id, 'devotion_minute', 0)
        devotion_enabled = server_config_cog.get_config(ctx.guild.id, 'devotion_enabled', True)
        
        embed = discord.Embed(
            title="🙏 Devotion Setup & Configuration",
            color=discord.Color.blue()
        )
        
        if channel_id:
            channel = self.bot.get_channel(channel_id)
            if channel:
                embed.add_field(
                    name="✅ Devotion Channel Configured",
                    value=f"Daily messages will be sent to {channel.mention}",
                    inline=False
                )
                embed.color = discord.Color.green()
            else:
                embed.add_field(
                    name="⚠️ Channel Not Found",
                    value=f"Configured channel ID {channel_id} no longer exists",
                    inline=False
                )
                embed.color = discord.Color.orange()
        else:
            embed.add_field(
                name="❌ No Devotion Channel Set",
                value="Daily devotion messages are currently disabled",
                inline=False
            )
            embed.color = discord.Color.red()
        
        # Format time display
        display_hour = devotion_hour
        am_pm = "AM"
        if devotion_hour == 0:
            display_hour = 12
        elif devotion_hour > 12:
            display_hour = devotion_hour - 12
            am_pm = "PM"
        elif devotion_hour == 12:
            am_pm = "PM"
        
        embed.add_field(
            name="🕐 Schedule Information",
            value=(
                f"**Status:** {'✅ Enabled' if devotion_enabled else '❌ Disabled'}\n"
                f"**Time:** {display_hour}:{devotion_minute:02d} {am_pm} Pacific Time\n"
                f"**24h Format:** {devotion_hour:02d}:{devotion_minute:02d}"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⚙️ Configuration Commands",
            value=(
                "`!config devotion` - Full devotion configuration panel\n"
                "`!config devotion_channel #channel` - Set devotion channel\n"
                "`!config devotion_time <hour> <minute>` - Set daily time\n"
                "`!config devotion_toggle` - Enable/disable system\n"
                "`!devotion` - Send manual devotion check-in"
            ),
            inline=False
        )
        
        embed.set_footer(text="💡 Only administrators can modify devotion settings")
        await ctx.send(embed=embed)

    @commands.command(name="test_devotion")
    async def test_devotion(self, ctx):
        """Test command to verify the devotion accountability system is working."""
        embed = discord.Embed(
            title="Devotion System Test ✅",
            description=(
                "The devotion accountability system is loaded and ready!\n\n"
                "**Features:**\n"
                "• Daily check-ins at 6:00 PM Pacific\n"
                "• Public sharing with privacy control\n"
                "• Statistics tracking\n"
                "• Personal devotion history\n\n"
                "Use `!devotion` to manually trigger a check-in or `!helpme faith` for more commands!"
            ),
            color=discord.Color.green()
        )
        embed.set_footer(text="Ready to grow in faith together!")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="devo")
    async def submit_devotion_quick(self, ctx, response: str):
        """Submit your devotion response quickly.
        
        Args:
            response: 'yes', 'no', or 'later'
        """
        response = response.lower()
        if response not in ['yes', 'no', 'later']:
            await ctx.send("Please use 'yes', 'no', or 'later' as your response.")
            return
        
        # Check if user has already submitted today
        if self._has_responded_today(ctx.author.id, ctx.guild.id):
            embed = discord.Embed(
                title="Already Submitted Today! ✅",
                description=(
                    f"{ctx.author.mention}, you've already submitted your final devotion response for today! 😊\n\n"
                    "Check your progress with `!my_devotions` or view server stats with `!devotion_stats`"
                ),
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            return
        
        # Check if they said "later" before
        has_said_later = self._has_said_later_today(ctx.author.id, ctx.guild.id)
        
        if response == 'yes':
            # For slash commands, we have access to interaction
            if hasattr(ctx, 'interaction') and ctx.interaction:
                # Show modal for sharing details
                modal = DevotionModal(ctx.author, "Bible Reading/Prayer Time")
                await ctx.interaction.response.send_modal(modal)
            else:
                # For prefix commands, we can't show modals, so log basic response
                # Get current streak before logging
                old_current, old_longest, _, _ = self._get_user_streak(ctx.author.id, ctx.guild.id)
                
                streak_info = self._log_devotion_response(ctx.author.id, ctx.guild.id, "yes", "Via command", "")
                
                if has_said_later:
                    description = f"{ctx.author.mention}, awesome! Thank you for following up and spending time with God today! 🙌"
                else:
                    description = f"{ctx.author.mention}, thank you for spending time with God today!"
                
                # Add streak information if we have it
                if streak_info:
                    current_streak, longest_streak, is_updated = streak_info
                    if is_updated and current_streak > 0:
                        is_new_record = longest_streak > old_longest
                        streak_message = self._generate_streak_message(current_streak, longest_streak, is_new_record)
                        description += f"\n\n🔥 **{streak_message}**\n**Current Streak:** {current_streak} days | **Personal Best:** {longest_streak} days"
                else:
                    # Get current streak info if streak_info is None (same day submission)
                    current_streak, longest_streak, _, _ = self._get_user_streak(ctx.author.id, ctx.guild.id)
                    if current_streak > 0:
                        description += f"\n\n🔥 **Current Streak:** {current_streak} days | **Personal Best:** {longest_streak} days"
                
                embed = discord.Embed(
                    title="Devotion Submitted! 🙌",
                    description=description,
                    color=discord.Color.green()
                )
                await ctx.send(embed=embed)
        elif response == 'later':
            # Log response but don't block future submissions
            self._log_devotion_response(ctx.author.id, ctx.guild.id, "not_yet")
            if has_said_later:
                description = f"{ctx.author.mention}, no worries! Still plenty of time left in the day. You can submit `!devo yes` or `!devo no` when you're ready."
            else:
                description = f"{ctx.author.mention}, there's still time today to spend time with God! You can still submit `!devo yes` or `!devo no` later."
            embed = discord.Embed(
                title="That's okay! 💪",
                description=description,
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
        elif response == 'no':
            # Log response
            self._log_devotion_response(ctx.author.id, ctx.guild.id, "no")
            if has_said_later:
                description = f"{ctx.author.mention}, thank you for being honest! Even though you didn't have time today, tomorrow is a fresh opportunity to spend time with God."
            else:
                description = f"{ctx.author.mention}, thank you for being honest! Tomorrow is a fresh opportunity to spend time with God."
            embed = discord.Embed(
                title="Tomorrow's a new day! 🌅",
                description=description,
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @commands.command(name="submit_devotion")
    async def submit_devotion(self, ctx):
        """Submit your devotion for today with dropdown menu."""
        # Check if user has already submitted today
        if self._has_responded_today(ctx.author.id, ctx.guild.id):
            embed = discord.Embed(
                title="Already Submitted Today! ✅",
                description=(
                    f"{ctx.author.mention}, you've already submitted your final devotion response for today! 😊\n\n"
                    "Check your progress with `!my_devotions` or view server stats with `!devotion_stats`"
                ),
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            return
        
        # Show dropdown submission form
        embed = discord.Embed(
            title="Devotion Submission 🙏",
            description=(
                "Choose your devotion status from the dropdown below, or use these quick commands:\n\n"
                "📖 `!devo yes` - I read my Bible and/or prayed today\n"
                "⏰ `!devo later` - I haven't had my devotion time yet\n"
                "❌ `!devo no` - I didn't have devotion time today"
            ),
            color=discord.Color.blue()
        )
        
        view = DevotionSelectView()
        await ctx.send(embed=embed, view=view)

    def _has_responded_today(self, user_id, guild_id):
        """Check if user has already responded today with a final answer (yes/no)."""
        today = datetime.now(self.california_tz).date()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM devotion_responses 
                WHERE user_id = ? AND guild_id = ? AND date_responded = ? 
                AND response_type IN ('yes', 'no')
            """, (user_id, guild_id, today))
            count = cursor.fetchone()[0]
            return count > 0

    def _has_said_later_today(self, user_id, guild_id):
        """Check if user has already said 'later' today."""
        today = datetime.now(self.california_tz).date()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM devotion_responses 
                WHERE user_id = ? AND guild_id = ? AND date_responded = ? 
                AND response_type = 'not_yet'
            """, (user_id, guild_id, today))
            count = cursor.fetchone()[0]
            return count > 0

    @commands.command(name="devotion_help")
    async def devotion_help(self, ctx):
        """Show help information for the devotion accountability system."""
        embed = discord.Embed(
            title="Devotion Accountability System Help 📖",
            description="Stay accountable in your daily walk with God!",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="📝 Submit Your Devotion",
            value=(
                "`!devo yes/no/later` - Quick devotion submission\n"
                "`!submit_devotion` - Dropdown menu submission\n"
                "Record whether you read your Bible or prayed today"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📊 View Statistics",
            value=(
                "`!devotion_stats [days]` - Server devotion statistics\n"
                "`!my_devotions [days]` - Your personal devotion history\n"
                "`!my_streak` - Check your current devotion streak\n"
                "`!streak_leaderboard [current/longest]` - View streak rankings\n"
                "`!streak_stats` - Server-wide streak statistics"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⚙️ Admin Commands",
            value=(
                "`!devotion_setup` - Configure devotion settings (Admin only)\n"
                "`!devotion` - Send manual devotion check-in (Admin)\n"
                "`!config devotion_channel #channel` - Set devotion channel"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🕒 Daily Reminders",
            value=(
                "Automatic reminders are sent daily at the configured time "
                "(default 6:00 PM Pacific Time). Use `!config devotion` to adjust the schedule."
            ),
            inline=False
        )
        
        embed.add_field(
            name="🙏 Privacy & Sharing",
            value=(
                "When you submit 'Yes', you can optionally share:\n"
                "• **When** you had your devotion time\n"
                "• **What** God was leading you to\n\n"
                "Sharing is public to encourage others, but be as detailed or "
                "vague as you're comfortable with!"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🔥 Streak System",
            value=(
                "Build consecutive day streaks by submitting devotions!\n"
                "• Streaks continue when you submit 'Yes' on consecutive days\n"
                "• Missing a day breaks your current streak\n"
                "• Track your progress and compete with others!\n"
                "• Streaks are server-specific"
            ),
            inline=False
        )
        
        embed.set_footer(text="Let's grow in faith together! 🌱")
        await ctx.send(embed=embed)

    @commands.command(name="my_streak")
    async def my_streak(self, ctx):
        """Check your current devotion streak."""
        current_streak, longest_streak, last_devotion_date, streak_start_date = self._get_user_streak(ctx.author.id, ctx.guild.id)
        
        embed = discord.Embed(
            title=f"{ctx.author.display_name}'s Devotion Streak 🔥",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
        
        if current_streak > 0:
            embed.add_field(name="🔥 Current Streak", value=f"{current_streak} days", inline=True)
            embed.add_field(name="🏆 Personal Best", value=f"{longest_streak} days", inline=True)
            embed.add_field(name="━━━━━━━━━━━━━━━", value="", inline=False)
            
            if last_devotion_date:
                embed.add_field(name="📅 Last Devotion", value=last_devotion_date, inline=True)
            if streak_start_date and current_streak > 1:
                embed.add_field(name="🎯 Streak Started", value=streak_start_date, inline=True)
            
            # Add motivational message
            if current_streak >= longest_streak:
                embed.add_field(name="🎊 Achievement", value="You're at your personal best!", inline=False)
            elif current_streak == 1:
                embed.add_field(name="💪 Keep Going", value="Great start! Build that habit one day at a time!", inline=False)
            else:
                days_to_record = longest_streak - current_streak
                embed.add_field(name="🎯 Goal", value=f"Only {days_to_record} more days to beat your record!", inline=False)
        else:
            embed.add_field(name="🌱 Start Your Journey", value="No active streak yet. Submit your devotion today to begin!", inline=False)
            if longest_streak > 0:
                embed.add_field(name="🏆 Personal Best", value=f"{longest_streak} days", inline=True)
                embed.add_field(name="💡 Tip", value="You've done it before, you can do it again!", inline=False)
        
        embed.set_footer(text="Use !devo yes to add to your streak!")
        await ctx.send(embed=embed)

    @commands.command(name="streak_leaderboard")
    async def streak_leaderboard(self, ctx, period: str = "current"):
        """Show devotion streak leaderboard.
        
        Args:
            period: 'current' for current streaks or 'longest' for all-time best streaks
        """
        if period not in ['current', 'longest']:
            await ctx.send("Use 'current' for active streaks or 'longest' for all-time records.")
            return
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if period == 'current':
                # Only show streaks that are still active (devotion within last day)
                cursor.execute("""
                    SELECT user_id, current_streak, last_devotion_date, streak_start_date
                    FROM devotion_streaks 
                    WHERE guild_id = ? AND current_streak > 0 
                    AND date(last_devotion_date) >= date('now', '-1 day')
                    ORDER BY current_streak DESC, last_devotion_date ASC
                    LIMIT 10
                """, (ctx.guild.id,))
                title = "🔥 Current Streak Leaderboard"
                description = "Active devotion streaks (must have had devotion within last day)"
            else:
                cursor.execute("""
                    SELECT user_id, longest_streak, last_devotion_date, streak_start_date
                    FROM devotion_streaks 
                    WHERE guild_id = ? AND longest_streak > 0
                    ORDER BY longest_streak DESC, last_devotion_date ASC
                    LIMIT 10
                """, (ctx.guild.id,))
                title = "🏆 All-Time Streak Records"
                description = "Longest devotion streaks ever achieved"
            
            results = cursor.fetchall()
            
            if not results:
                await ctx.send("No streak data found for this server yet!")
                return
            
            embed = discord.Embed(
                title=title,
                description=description,
                color=discord.Color.gold()
            )
            
            medal_emojis = ["🥇", "🥈", "🥉"]
            
            for i, (user_id, streak_days, last_date, start_date) in enumerate(results):
                try:
                    user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                    username = user.display_name if hasattr(user, 'display_name') else user.name
                except:
                    username = f"User {user_id}"
                
                # Add medal for top 3
                if i < 3:
                    position = medal_emojis[i]
                else:
                    position = f"{i+1}."
                
                streak_info = f"**{streak_days}** days"
                if period == 'current' and start_date:
                    streak_info += f" (started {start_date})"
                
                embed.add_field(
                    name=f"{position} {username}",
                    value=streak_info,
                    inline=False
                )
            
            embed.set_footer(text=f"Showing top {len(results)} • Use !my_streak to check your progress")
            await ctx.send(embed=embed)

    @commands.command(name="streak_stats")
    async def streak_stats(self, ctx):
        """Show server-wide streak statistics."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get various streak statistics
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_users,
                    COUNT(CASE WHEN current_streak > 0 AND date(last_devotion_date) >= date('now', '-1 day') THEN 1 END) as active_streaks,
                    MAX(current_streak) as longest_current,
                    MAX(longest_streak) as longest_ever,
                    AVG(CASE WHEN current_streak > 0 AND date(last_devotion_date) >= date('now', '-1 day') THEN current_streak END) as avg_active,
                    COUNT(CASE WHEN current_streak >= 7 AND date(last_devotion_date) >= date('now', '-1 day') THEN 1 END) as week_plus,
                    COUNT(CASE WHEN current_streak >= 30 AND date(last_devotion_date) >= date('now', '-1 day') THEN 1 END) as month_plus
                FROM devotion_streaks 
                WHERE guild_id = ?
            """, (ctx.guild.id,))
            
            stats = cursor.fetchone()
            
            if not stats or stats[0] == 0:
                await ctx.send("No streak data available for this server yet!")
                return
            
            total_users, active_streaks, longest_current, longest_ever, avg_active, week_plus, month_plus = stats
            
            embed = discord.Embed(
                title="📊 Server Streak Statistics",
                color=discord.Color.purple()
            )
            
            embed.add_field(name="👥 Total Users with Streaks", value=str(total_users), inline=True)
            embed.add_field(name="🔥 Currently Active", value=str(active_streaks), inline=True)
            embed.add_field(name="━━━━━━━━━━━━━━━", value="", inline=False)
            
            embed.add_field(name="🏃 Longest Current Streak", value=f"{longest_current or 0} days", inline=True)
            embed.add_field(name="🏆 All-Time Record", value=f"{longest_ever or 0} days", inline=True)
            embed.add_field(name="━━━━━━━━━━━━━━━", value="", inline=False)
            
            if avg_active:
                embed.add_field(name="📈 Average Active Streak", value=f"{avg_active:.1f} days", inline=True)
            embed.add_field(name="📅 Week+ Streaks", value=str(week_plus), inline=True)
            embed.add_field(name="📆 Month+ Streaks", value=str(month_plus), inline=True)
            
            # Calculate participation rate
            guild_member_count = ctx.guild.member_count
            if guild_member_count:
                participation_rate = (total_users / guild_member_count) * 100
                embed.add_field(
                    name="📋 Participation Rate", 
                    value=f"{participation_rate:.1f}% ({total_users}/{guild_member_count})", 
                    inline=False
                )
            
            embed.set_footer(text="Keep encouraging each other to maintain those streaks! 🙏")
            await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(DevotionAccountability(bot))
