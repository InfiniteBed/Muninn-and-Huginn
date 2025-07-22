import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
import sqlite3
import datetime
import random

class EmojiApprovalView(View):
    def __init__(self, submission_id, bot_owner_id):
        super().__init__(timeout=None)
        self.submission_id = submission_id
        self.bot_owner_id = bot_owner_id

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green, custom_id="approve_emoji")
    async def approve(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.bot_owner_id:
            await interaction.response.send_message("Only the bot owner can approve.", ephemeral=True)
            return

        with sqlite3.connect("discord.db") as conn:
            c = conn.cursor()
            # Move from pending to approved emojis table
            c.execute("SELECT url, uploader_id FROM emoji_submissions WHERE id = ?", (self.submission_id,))
            submission = c.fetchone()
            
            if submission:
                url, uploader_id = submission
                c.execute("INSERT INTO emojis (url, uploader_id) VALUES (?, ?)", (url, uploader_id))
                c.execute("UPDATE emoji_submissions SET approved = 1, approved_at = ? WHERE id = ?", 
                         (datetime.datetime.utcnow().isoformat(), self.submission_id))
                
                # Award star to submitter
                c.execute('SELECT stars FROM stars WHERE guild_id = ? AND user_id = ?', (0, uploader_id))
                result = c.fetchone()
                if result:
                    c.execute('UPDATE stars SET stars = stars + 1 WHERE guild_id = ? AND user_id = ?', 
                             (0, uploader_id))
                else:
                    c.execute('INSERT INTO stars (guild_id, user_id, stars) VALUES (?, ?, ?)', 
                             (0, uploader_id, 1))
                
                conn.commit()

        await interaction.response.send_message("Emoji submission approved! Submitter awarded a star.", ephemeral=True)
        await interaction.message.edit(view=None)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.red, custom_id="reject_emoji")
    async def reject(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.bot_owner_id:
            await interaction.response.send_message("Only the bot owner can reject.", ephemeral=True)
            return

        with sqlite3.connect("discord.db") as conn:
            c = conn.cursor()
            c.execute("UPDATE emoji_submissions SET approved = -1, approved_at = ? WHERE id = ?", 
                     (datetime.datetime.utcnow().isoformat(), self.submission_id))
            conn.commit()

        await interaction.response.send_message("Emoji submission rejected.", ephemeral=True)
        await interaction.message.edit(view=None)

class EmojiContest(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.conn = sqlite3.connect("discord.db")
        self.cursor = self.conn.cursor()
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS emojis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            uploader_id INTEGER NOT NULL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS emoji_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            uploader_id INTEGER NOT NULL,
            guild_id INTEGER,
            approved INTEGER DEFAULT 0,
            submitted_at TEXT,
            approved_at TEXT
        )
        """)
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            user_id INTEGER PRIMARY KEY,
            choice INTEGER NOT NULL,
            voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        # Create stars table if it doesn't exist
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS stars (
            guild_id INTEGER,
            user_id INTEGER,
            stars INTEGER,
            PRIMARY KEY (guild_id, user_id)
        )''')
        self.conn.commit()
        self.emoji_vote_task.start()

    def cog_unload(self):
        self.emoji_vote_task.cancel()
        self.conn.close()

    @commands.command()
    async def upload(self, ctx):
        if not ctx.message.attachments:
            await ctx.send("Please attach an image.")
            return
        
        for attachment in ctx.message.attachments:
            # Validate that it's an image
            if not any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                await ctx.send(f"File {attachment.filename} is not a valid image format.")
                continue
                
            url = attachment.url
            now = datetime.datetime.utcnow().isoformat()
            
            # Store submission in pending state
            self.cursor.execute(
                "INSERT INTO emoji_submissions (url, uploader_id, guild_id, submitted_at) VALUES (?, ?, ?, ?)",
                (url, ctx.author.id, ctx.guild.id if ctx.guild else None, now)
            )
            submission_id = self.cursor.lastrowid
            self.conn.commit()
            
            # Send approval request to bot owner
            bot_owner = self.bot.get_user(self.bot.owner_id)
            if bot_owner:
                embed_to_owner = discord.Embed(
                    title="New Emoji Submission Awaiting Approval",
                    color=discord.Color.orange(),
                    description=(
                        f"**Filename:** {attachment.filename}\n"
                        f"**Submitted by:** {ctx.author.mention} ({ctx.author.display_name})\n"
                        f"**Guild:** {ctx.guild.name if ctx.guild else 'DM'}"
                    )
                )
                embed_to_owner.set_image(url=url)
                embed_to_owner.set_author(
                    name=ctx.author.display_name, 
                    icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                )
                embed_to_owner.set_footer(text=f"Submission ID: {submission_id}")
                
                view = EmojiApprovalView(submission_id, self.bot.owner_id)
                await bot_owner.send(embed=embed_to_owner, view=view)
        
        await ctx.send("✅ Your emoji submission(s) have been sent to the bot owner for approval! You'll receive a star if approved.")

    @commands.command()
    async def vote(self, ctx, choice: int):
        if choice not in [1, 2]:
            await ctx.send("Invalid choice! Use `!vote 1` or `!vote 2`.")
            return
        
        self.cursor.execute("REPLACE INTO votes (user_id, choice) VALUES (?, ?)", (ctx.author.id, choice))
        self.conn.commit()
        await ctx.send(f"Vote registered for option {choice}!")

    @commands.command()
    @commands.is_owner()
    async def start_vote(self, ctx):
        """Manually starts an emoji vote."""
        channel = ctx.channel  # Use the current channel for voting
        self.cursor.execute("SELECT id, url FROM emojis ORDER BY RANDOM() LIMIT 2")
        images = self.cursor.fetchall()
        
        if len(images) < 2:
            return
        
        embed = discord.Embed(title="Emoji Vote!", description="Vote using `!vote 1` or `!vote 2`.", color=discord.Color.blue())
        embed.add_field(name="Option 1", value="React with 1️⃣", inline=True)
        embed.add_field(name="Option 2", value="React with 2️⃣", inline=True)
        embed.set_image(url=images[0][1])
        embed.set_footer(text="Voting lasts 24 hours!")
        await channel.send(embed=embed)
        
        # Store current vote session
        self.current_vote = images
        self.conn.execute("DELETE FROM votes")  # Clear old votes
        self.conn.commit()
        
        # Wait 24 hours, then announce the result
        await discord.utils.sleep_until(datetime.datetime.utcnow() + datetime.timedelta(days=1))
        self.announce_winner(channel)

    @tasks.loop(hours=168)  # Runs every week
    async def emoji_vote_task(self):
        now = datetime.datetime.utcnow()
        if now.weekday() != 0:  # Only run on Monday
            return
        
        channel = self.bot.get_channel(1298762960184934432)  # Replace with your channel ID
        self.cursor.execute("SELECT id, url FROM emojis ORDER BY RANDOM() LIMIT 2")
        images = self.cursor.fetchall()
        
        if len(images) < 2:
            return
        
        embed = discord.Embed(title="Emoji Vote!", description="Vote using `!vote 1` or `!vote 2`.", color=discord.Color.blue())
        embed.add_field(name="Option 1", value="React with 1️⃣", inline=True)
        embed.add_field(name="Option 2", value="React with 2️⃣", inline=True)
        embed.set_image(url=images[0][1])
        embed.set_footer(text="Voting lasts 24 hours!")
        await channel.send(embed=embed)
        
        # Store current vote session
        self.current_vote = images
        self.conn.execute("DELETE FROM votes")  # Clear old votes
        self.conn.commit()
        
        # Wait 24 hours, then announce the result
        await discord.utils.sleep_until(now + datetime.timedelta(days=1))
        self.announce_winner(channel)

    def announce_winner(self, channel):
        self.cursor.execute("SELECT choice, COUNT(*) FROM votes GROUP BY choice")
        results = self.cursor.fetchall()
        
        if not results:
            channel.send("No votes were cast!")
            return
        
        winner = max(results, key=lambda x: x[1])[0]
        winning_image = self.current_vote[winner - 1][1]
        
        embed = discord.Embed(title="Voting Results", description=f"Option {winner} wins!", color=discord.Color.green())
        embed.set_image(url=winning_image)
        channel.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def pending_emojis(self, ctx):
        """View all pending emoji submissions (bot owner only)"""
        self.cursor.execute('''SELECT id, uploader_id, guild_id, url, submitted_at 
                             FROM emoji_submissions WHERE approved = 0 ORDER BY submitted_at DESC''')
        pending = self.cursor.fetchall()
        
        if not pending:
            await ctx.send("No pending emoji submissions.")
            return
        
        for submission_id, uploader_id, guild_id, url, submitted_at in pending:
            guild = self.bot.get_guild(guild_id) if guild_id else None
            uploader = self.bot.get_user(uploader_id)
            
            embed = discord.Embed(
                title=f"Pending Emoji Submission #{submission_id}",
                color=discord.Color.orange()
            )
            embed.add_field(name="Submitter", value=f"{uploader.mention if uploader else 'Unknown'} ({uploader.display_name if uploader else 'Unknown'})", inline=True)
            embed.add_field(name="Guild", value=guild.name if guild else "Unknown", inline=True)
            embed.add_field(name="Submitted", value=submitted_at, inline=True)
            embed.set_image(url=url)
            
            await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def emoji_stats(self, ctx):
        """View emoji submission statistics"""
        # Get statistics
        self.cursor.execute("SELECT COUNT(*) FROM emoji_submissions")
        total = self.cursor.fetchone()[0]
        
        self.cursor.execute("SELECT COUNT(*) FROM emoji_submissions WHERE approved = 1")
        approved = self.cursor.fetchone()[0]
        
        self.cursor.execute("SELECT COUNT(*) FROM emoji_submissions WHERE approved = -1")
        rejected = self.cursor.fetchone()[0]
        
        self.cursor.execute("SELECT COUNT(*) FROM emoji_submissions WHERE approved = 0")
        pending = self.cursor.fetchone()[0]
        
        # Most active submitter
        self.cursor.execute('''SELECT uploader_id, COUNT(*) FROM emoji_submissions 
                             GROUP BY uploader_id ORDER BY COUNT(*) DESC LIMIT 1''')
        most_active = self.cursor.fetchone()
        
        approval_rate = round((approved / total * 100), 1) if total > 0 else 0
        
        embed = discord.Embed(title="Emoji Submission Statistics", color=discord.Color.blue())
        embed.add_field(name="Total Submissions", value=total, inline=True)
        embed.add_field(name="Approved", value=f"{approved} ({approval_rate}%)", inline=True)
        embed.add_field(name="Rejected", value=rejected, inline=True)
        embed.add_field(name="Pending", value=pending, inline=True)
        
        if most_active:
            user = self.bot.get_user(most_active[0])
            embed.add_field(name="Most Active Submitter", 
                           value=f"{user.mention if user else 'Unknown'} ({most_active[1]} submissions)", 
                           inline=False)
        
        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def approve_emoji(self, ctx, submission_id: int):
        """Manually approve an emoji submission by ID (bot owner only)"""
        self.cursor.execute("SELECT url, uploader_id, guild_id FROM emoji_submissions WHERE id = ? AND approved = 0", 
                          (submission_id,))
        submission = self.cursor.fetchone()
        
        if not submission:
            await ctx.send(f"No pending emoji submission found with ID {submission_id}.")
            return
        
        url, uploader_id, guild_id = submission
        
        # Move to approved emojis and award star
        self.cursor.execute("INSERT INTO emojis (url, uploader_id) VALUES (?, ?)", (url, uploader_id))
        self.cursor.execute("UPDATE emoji_submissions SET approved = 1, approved_at = ? WHERE id = ?", 
                          (datetime.datetime.utcnow().isoformat(), submission_id))
        
        # Award star
        self.cursor.execute('SELECT stars FROM stars WHERE guild_id = ? AND user_id = ?', (0, uploader_id))
        result = self.cursor.fetchone()
        if result:
            self.cursor.execute('UPDATE stars SET stars = stars + 1 WHERE guild_id = ? AND user_id = ?', 
                              (0, uploader_id))
        else:
            self.cursor.execute('INSERT INTO stars (guild_id, user_id, stars) VALUES (?, ?, ?)', 
                              (0, uploader_id, 1))
        
        self.conn.commit()
        
        uploader = self.bot.get_user(uploader_id)
        embed = discord.Embed(
            title="Emoji Submission Approved",
            color=discord.Color.green(),
            description=f"**ID:** {submission_id}\n**Submitter:** {uploader.mention if uploader else 'Unknown'}"
        )
        embed.set_image(url=url)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def reject_emoji(self, ctx, submission_id: int):
        """Manually reject an emoji submission by ID (bot owner only)"""
        self.cursor.execute("SELECT url, uploader_id FROM emoji_submissions WHERE id = ? AND approved = 0", 
                          (submission_id,))
        submission = self.cursor.fetchone()
        
        if not submission:
            await ctx.send(f"No pending emoji submission found with ID {submission_id}.")
            return
        
        url, uploader_id = submission
        
        # Reject the submission
        self.cursor.execute("UPDATE emoji_submissions SET approved = -1, approved_at = ? WHERE id = ?", 
                          (datetime.datetime.utcnow().isoformat(), submission_id))
        
        self.conn.commit()
        
        uploader = self.bot.get_user(uploader_id)
        embed = discord.Embed(
            title="Emoji Submission Rejected",
            color=discord.Color.red(),
            description=f"**ID:** {submission_id}\n**Submitter:** {uploader.mention if uploader else 'Unknown'}"
        )
        embed.set_image(url=url)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(EmojiContest(bot))
