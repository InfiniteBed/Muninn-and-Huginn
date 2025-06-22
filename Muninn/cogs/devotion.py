import discord
from discord.ext import commands, tasks
from discord.ui import View, Button, Modal, TextInput
import sqlite3
from datetime import datetime, time
import pytz
import asyncio

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
        
        embed.set_footer(text="Keep growing in faith!")
        
        # Log to database
        devotion_cog = interaction.client.get_cog('DevotionAccountability')
        if devotion_cog:
            devotion_cog._log_devotion_response(
                self.user.id, 
                interaction.guild.id,
                "yes", 
                self.when_input.value, 
                self.what_input.value
            )
        
        await interaction.response.send_message(embed=embed)

class DevotionView(View):
    def __init__(self, timeout=3600):  # 1 hour timeout
        super().__init__(timeout=timeout)

    @discord.ui.button(label="Submit My Devotion! 🙌", style=discord.ButtonStyle.success, emoji="✅")
    async def submit_button(self, interaction: discord.Interaction, button: Button):
        # Get the devotion cog to check database
        devotion_cog = interaction.client.get_cog('DevotionAccountability')
        if devotion_cog and devotion_cog._has_responded_today(interaction.user.id, interaction.guild.id):
            await interaction.response.send_message(
                "You've already submitted your devotion for today! 😊 Check your progress with `!my_devotions`", 
                ephemeral=True
            )
            return
        
        # Use the submission command
        await interaction.response.send_message(
            "Let's record your devotion! Use the command: `!submit_devotion`", 
            ephemeral=True
        )

    @discord.ui.button(label="Remind Me Later ⏰", style=discord.ButtonStyle.secondary, emoji="⏰")
    async def remind_later_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(
            "I'll remind you again tomorrow! 😊 Remember, you can submit anytime with `!submit_devotion`", 
            ephemeral=True
        )

class DevotionSubmissionView(View):
    def __init__(self, user, timeout=300):  # 5 minute timeout
        super().__init__(timeout=timeout)
        self.user = user

    @discord.ui.button(label="Yes! 🙌", style=discord.ButtonStyle.success, emoji="✅")
    async def yes_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            await interaction.response.send_message("This submission is not for you.", ephemeral=True)
            return
        
        # Show modal for sharing details
        modal = DevotionModal(interaction.user, "Bible Reading/Prayer Time")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Not yet!", style=discord.ButtonStyle.secondary, emoji="⏰")
    async def not_yet_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            await interaction.response.send_message("This submission is not for you.", ephemeral=True)
            return
        
        # Log response
        devotion_cog = interaction.client.get_cog('DevotionAccountability')
        if devotion_cog:
            devotion_cog._log_devotion_response(
                interaction.user.id, 
                interaction.guild.id,
                "not_yet"
            )
        
        embed = discord.Embed(
            title="That's okay! 💪",
            description=f"{interaction.user.mention}, there's still time today to spend time with God!",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
        await interaction.message.edit(view=None)  # Remove buttons

    @discord.ui.button(label="No", style=discord.ButtonStyle.danger, emoji="❌")
    async def no_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            await interaction.response.send_message("This submission is not for you.", ephemeral=True)
            return
        
        # Log response
        devotion_cog = interaction.client.get_cog('DevotionAccountability')
        if devotion_cog:
            devotion_cog._log_devotion_response(
                interaction.user.id, 
                interaction.guild.id,
                "no"
            )
        
        embed = discord.Embed(
            title="Tomorrow's a new day! 🌅",
            description=f"{interaction.user.mention}, thank you for being honest! Tomorrow is a fresh opportunity to spend time with God.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
        await interaction.message.edit(view=None)  # Remove buttons

class DevotionAccountability(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "discord.db"
        self.california_tz = pytz.timezone('US/Pacific')
        
        # Schedule for late afternoon/early evening (5:30 PM Pacific)
        self.scheduled_time = get_time(17, 30)  # 5:30 PM
        
        self._initialize_database()
        self.devotion_scheduler = tasks.loop(time=[self.scheduled_time])(self.devotion_scheduler_task)
        self.devotion_scheduler.start()

    def cog_unload(self):
        self.devotion_scheduler.cancel()

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
            conn.commit()

    async def devotion_scheduler_task(self):
        """Daily task to send the devotion accountability message to all configured servers."""
        server_config_cog = self.bot.get_cog('ServerConfig')
        if not server_config_cog:
            print("ServerConfig cog not found - cannot send scheduled devotions")
            return
        
        # Send to all guilds that have a devotion channel configured
        for guild in self.bot.guilds:
            channel_id = server_config_cog.get_config(guild.id, 'devotion_channel')
            if channel_id:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        await self.send_devotion_message(channel)
                        print(f"Sent devotion message to {guild.name} - #{channel.name}")
                    except Exception as e:
                        print(f"Error sending devotion message to {guild.name}: {e}")
                else:
                    print(f"Devotion channel {channel_id} not found in {guild.name}")

    def _get_devotion_channel(self, guild_id: int):
        """Get the configured devotion channel for a guild."""
        server_config_cog = self.bot.get_cog('ServerConfig')
        if not server_config_cog:
            return None
        return server_config_cog.get_config(guild_id, 'devotion_channel')

    async def send_devotion_message(self, channel):
        """Send the daily devotion accountability message."""
        embed = discord.Embed(
            title="Daily Faith Check-In 🙏",
            description=(
                "Hey everyone! Time for our daily accountability check-in!\n\n"
                "**Did you read your Bible and/or talk to God today?**\n\n"
                "📝 *Use the button below to be directed to submit your devotion, or use the command `!submit_devotion` directly.*\n\n"
                "💡 *If you select 'Yes!', you'll be asked to share when and optionally what "
                "the Holy Spirit was leading you to. Your response will be shared publicly to encourage "
                "others, but feel free to be as vague or detailed as you're comfortable with!*"
            ),
            color=discord.Color.blue()
        )
        embed.set_footer(text="Let's grow in our faith together!")
        
        view = DevotionView()
        message = await channel.send(embed=embed, view=view)
        
        print(f"Sent daily devotion check-in message to {channel.name}")

    @commands.command(name="devotion")
    async def manual_devotion(self, ctx):
        """Manually send the devotion accountability message."""
        # Check if there's a configured devotion channel
        channel_id = self._get_devotion_channel(ctx.guild.id)
        
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
            embed.add_field(name="━━━━━━━━━━━━━━━", value="", inline=False)
            
            for response_type, count in stats:
                emoji = {"yes": "✅", "no": "❌", "not_yet": "⏰"}.get(response_type, "📝")
                percentage = (count / total_responses) * 100
                embed.add_field(
                    name=f"{emoji} {response_type.replace('_', ' ').title()}", 
                    value=f"{count} ({percentage:.1f}%)", 
                    inline=True
                )
            
            embed.set_footer(text="Keep encouraging each other in faith! 🙏")
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
        channel_id = self._get_devotion_channel(ctx.guild.id)
        
        embed = discord.Embed(
            title="Devotion Setup & Configuration 🔧",
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
        
        embed.add_field(
            name="Schedule Information",
            value="Daily messages are sent at **5:30 PM Pacific Time**",
            inline=False
        )
        
        embed.add_field(
            name="Configuration Commands",
            value=(
                "`!config devotion_channel #channel` - Set devotion channel\n"
                "`!config list` - View all server settings\n"
                "`!devotion` - Send manual devotion check-in"
            ),
            inline=False
        )
        
        embed.set_footer(text="Only administrators can modify devotion settings")
        await ctx.send(embed=embed)

    @commands.command(name="test_devotion")
    async def test_devotion(self, ctx):
        """Test command to verify the devotion accountability system is working."""
        embed = discord.Embed(
            title="Devotion System Test ✅",
            description=(
                "The devotion accountability system is loaded and ready!\n\n"
                "**Features:**\n"
                "• Daily check-ins at 5:30 PM Pacific\n"
                "• Public sharing with privacy control\n"
                "• Statistics tracking\n"
                "• Personal devotion history\n\n"
                "Use `!devotion` to manually trigger a check-in or `!helpme faith` for more commands!"
            ),
            color=discord.Color.green()
        )
        embed.set_footer(text="Ready to grow in faith together!")
        await ctx.send(embed=embed)

    @commands.command(name="submit_devotion")
    async def submit_devotion(self, ctx):
        """Submit your devotion for today."""
        # Check if user has already submitted today
        if self._has_responded_today(ctx.author.id, ctx.guild.id):
            embed = discord.Embed(
                title="Already Submitted Today! ✅",
                description=(
                    f"{ctx.author.mention}, you've already submitted your devotion for today! 😊\n\n"
                    "Check your progress with `!my_devotions` or view server stats with `!devotion_stats`"
                ),
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            return
        
        # Show the submission modal
        embed = discord.Embed(
            title="Devotion Submission 🙏",
            description=(
                "Choose your submission type:\n\n"
                "📖 **Yes** - I read my Bible and/or prayed today\n"
                "⏰ **Not Yet** - I haven't had my devotion time yet\n"
                "❌ **No** - I didn't have devotion time today"
            ),
            color=discord.Color.blue()
        )
        
        view = DevotionSubmissionView(ctx.author)
        await ctx.send(embed=embed, view=view)

    def _has_responded_today(self, user_id, guild_id):
        """Check if user has already responded today by checking the database."""
        today = datetime.now(self.california_tz).date()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM devotion_responses 
                WHERE user_id = ? AND guild_id = ? AND date_responded = ?
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
                "`!submit_devotion` - Submit your daily devotion\n"
                "Use this command to record whether you read your Bible or prayed today"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📊 View Statistics",
            value=(
                "`!devotion_stats [days]` - Server devotion statistics\n"
                "`!my_devotions [days]` - Your personal devotion history"
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
                "Automatic reminders are sent daily at **5:30 PM Pacific Time** "
                "to the configured devotion channel."
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
        
        embed.set_footer(text="Let's grow in faith together! 🌱")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(DevotionAccountability(bot))
