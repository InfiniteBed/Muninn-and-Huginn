import discord
from discord.ext import commands, tasks
import sqlite3
import datetime
import random

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
        CREATE TABLE IF NOT EXISTS votes (
            user_id INTEGER PRIMARY KEY,
            choice INTEGER NOT NULL,
            voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
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
            url = attachment.url
            self.cursor.execute("INSERT INTO emojis (url, uploader_id) VALUES (?, ?)", (url, ctx.author.id))
        self.conn.commit()
        await ctx.send("Image uploaded successfully!")

    @commands.command()
    async def vote(self, ctx, choice: int):
        if choice not in [1, 2]:
            await ctx.send("Invalid choice! Use `!vote 1` or `!vote 2`.")
            return
        
        self.ursor.execute("REPLACE INTO votes (user_id, choice) VALUES (?, ?)", (ctx.author.id, choice))
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

async def setup(bot):
    await bot.add_cog(EmojiContest(bot))
