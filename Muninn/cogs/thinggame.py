import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import asyncio
import json
from discord.ui import View, Button

DB_PATH = "discord.db"

class ThingApprovalView(View):
    def __init__(self, thing_id, bot_owner_id):
        super().__init__(timeout=None)
        self.thing_id = thing_id
        self.bot_owner_id = bot_owner_id

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green, custom_id="approve_thing")
    async def approve(self, interaction: discord.Interaction, button: Button):
        import datetime
        if interaction.user.id != self.bot_owner_id:
            await interaction.response.send_message("Only the bot owner can approve.", ephemeral=True)
            return
        submitter_id = None
        guild_id = None
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("UPDATE things SET approved = 1, approved_at = ? WHERE id = ?", (datetime.datetime.utcnow().isoformat(), self.thing_id))
            c.execute("SELECT submitter_id, guild_id FROM things WHERE id = ?", (self.thing_id,))
            row = c.fetchone()
            if row:
                submitter_id, guild_id = row
            conn.commit()
        # Award a star to the submitter in the stars table
        if submitter_id and guild_id:
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                c.execute('''SELECT stars FROM stars WHERE guild_id = ? AND user_id = ?''', (guild_id, submitter_id))
                result = c.fetchone()
                if result:
                    new_stars = result[0] + 1
                    c.execute('''UPDATE stars SET stars = ? WHERE guild_id = ? AND user_id = ?''', (new_stars, guild_id, submitter_id))
                else:
                    c.execute('''INSERT INTO stars (guild_id, user_id, stars) VALUES (?, ?, ?)''', (guild_id, submitter_id, 1))
                conn.commit()
        await interaction.response.send_message("Thing approved! Submitter awarded a star.", ephemeral=True)
        await interaction.message.edit(view=None)

class ThingGame(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self._init_db())

    async def _init_db(self):
        await asyncio.sleep(1)  # Wait for bot to be ready
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS things (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    submitter_id INTEGER,
                    thing TEXT,
                    approved INTEGER DEFAULT 0,
                    score INTEGER DEFAULT 0,
                    guild_id INTEGER,
                    submitted_at TEXT,
                    approved_at TEXT
                )
            """)
            # Add columns if missing (for upgrades)
            try:
                c.execute("ALTER TABLE things ADD COLUMN submitted_at TEXT;")
            except sqlite3.OperationalError:
                pass
            try:
                c.execute("ALTER TABLE things ADD COLUMN approved_at TEXT;")
            except sqlite3.OperationalError:
                pass
            conn.commit()

    @commands.hybrid_command(name="submit_thing", description="Submit a thing to be rated.")
    async def submit_thing(self, ctx, *, thing: str):
        import datetime
        now = datetime.datetime.utcnow().isoformat()
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO things (submitter_id, thing, guild_id, submitted_at) VALUES (?, ?, ?, ?)", (ctx.author.id, thing, ctx.guild.id if ctx.guild else None, now))
            thing_id = c.lastrowid
            conn.commit()
        owner = self.bot.get_user(self.bot.owner_id)
        if owner:
            embed = discord.Embed(title="Thing Approval Needed", description=f"Submitted by: {ctx.author.mention}\nThing: {thing}")
            view = ThingApprovalView(thing_id, self.bot.owner_id)
            await owner.send(embed=embed, view=view)
        await ctx.reply("Your thing has been submitted for approval.")

    @commands.hybrid_command(name="thing_battle", description="Pick the better thing!")
    async def thing_battle(self, ctx):
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT id, thing FROM things WHERE approved = 1 ORDER BY RANDOM() LIMIT 2")
            things = c.fetchall()
        if len(things) < 2:
            await ctx.reply("Not enough approved things to battle.")
            return
        thing1_id, thing1 = things[0]
        thing2_id, thing2 = things[1]
        class BattleView(View):
            def __init__(self, thing1_id, thing2_id):
                super().__init__(timeout=30)
                self.thing1_id = thing1_id
                self.thing2_id = thing2_id
                self.voted = False
            def disable_all_buttons(self):
                for child in self.children:
                    if isinstance(child, Button):
                        child.disabled = True
            @discord.ui.button(label="Option 1", style=discord.ButtonStyle.primary)
            async def vote1(self, interaction: discord.Interaction, button: Button):
                if self.voted:
                    await interaction.response.send_message("You already voted!", ephemeral=True)
                    return
                self.voted = True
                self.disable_all_buttons()
                with sqlite3.connect(DB_PATH) as conn:
                    c = conn.cursor()
                    c.execute("UPDATE things SET score = score + 1 WHERE id = ?", (self.thing1_id,))
                    c.execute("UPDATE things SET score = score - 1 WHERE id = ?", (self.thing2_id,))
                    conn.commit()
                # Fetch the thing name for display
                with sqlite3.connect(DB_PATH) as conn:
                    c = conn.cursor()
                    c.execute("SELECT thing FROM things WHERE id = ?", (self.thing1_id,))
                    row = c.fetchone()
                    thing_name = row[0].title() if row else "Option 1"
                await interaction.response.edit_message(content=f"Thanks for voting, {ctx.author.display_name}! **{thing_name}** gets a point.", embed=None, view=None)
            @discord.ui.button(label="Option 2", style=discord.ButtonStyle.secondary)
            async def vote2(self, interaction: discord.Interaction, button: Button):
                if self.voted:
                    await interaction.response.send_message("You already voted!", ephemeral=True)
                    return
                self.voted = True
                self.disable_all_buttons()
                with sqlite3.connect(DB_PATH) as conn:
                    c = conn.cursor()
                    c.execute("UPDATE things SET score = score + 1 WHERE id = ?", (self.thing2_id,))
                    c.execute("UPDATE things SET score = score - 1 WHERE id = ?", (self.thing1_id,))
                    conn.commit()
                # Fetch the thing name for display
                with sqlite3.connect(DB_PATH) as conn:
                    c = conn.cursor()
                    c.execute("SELECT thing FROM things WHERE id = ?", (self.thing2_id,))
                    row = c.fetchone()
                    thing_name = row[0].title() if row else "Option 2"
                await interaction.response.edit_message(content=f"Thanks for voting! **{thing_name}** gets a point.", embed=None, view=None)
        embed = discord.Embed(title="Thing Battle!", description=f"**Option 1:** {thing1}\n**Option 2:** {thing2}")
        await ctx.send(embed=embed, view=BattleView(thing1_id, thing2_id))

    @commands.hybrid_command(name="thing_leaderboard", description="Show the top 10 things.")
    async def thing_leaderboard(self, ctx):
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT thing, score FROM things WHERE approved = 1 ORDER BY score DESC LIMIT 10")
            top = c.fetchall()
        if not top:
            await ctx.reply("No things have been rated yet.")
            return
        desc = "\n".join([f"**{i+1}.** {thing} — {score} pts" for i, (thing, score) in enumerate(top)])
        embed = discord.Embed(title="Top 10 Things", description=desc)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="thinggame_tutorial", description="Show a tutorial for the Thing Game.")
    async def thinggame_tutorial(self, ctx):
        embed = discord.Embed(
            title="Thing Game Tutorial",
            description=(
                "Welcome to the Thing Game!\n\n"
                "1. Use `/submit_thing <thing>` to submit something to be rated.\n"
                "2. Your submission must be approved by the bot owner. If approved, you earn a star!\n"
                "3. Use `/thing_battle` to vote between two approved things. The winner gains a point, the loser loses a point.\n"
                "4. Use `/thing_leaderboard` to see the top 10 things.\n\n"
                "Earn stars by getting your things approved! See `/stars` for the star leaderboard."
            ),
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="thinggame_stats", description="Show statistics for the Thing Game.")
    async def thinggame_stats(self, ctx):
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            # Most submitted user
            c.execute("SELECT submitter_id, COUNT(*) FROM things GROUP BY submitter_id ORDER BY COUNT(*) DESC LIMIT 1")
            row = c.fetchone()
            most_submitted = f"<@{row[0]}> ({row[1]} submissions)" if row else "N/A"
            # Most approved user
            c.execute("SELECT submitter_id, COUNT(*) FROM things WHERE approved = 1 GROUP BY submitter_id ORDER BY COUNT(*) DESC LIMIT 1")
            row = c.fetchone()
            most_approved = f"<@{row[0]}> ({row[1]} approved)" if row else "N/A"
            # Approval rate
            c.execute("SELECT COUNT(*) FROM things")
            total = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM things WHERE approved = 1")
            approved = c.fetchone()[0]
            approval_rate = f"{(approved/total*100):.1f}%" if total else "N/A"
            # Most popular thing
            c.execute("SELECT thing, score FROM things WHERE approved = 1 ORDER BY score DESC LIMIT 1")
            row = c.fetchone()
            most_popular = f"{row[0]} ({row[1]} pts)" if row else "N/A"
            # Most controversial thing
            c.execute("SELECT thing, score FROM things WHERE approved = 1 ORDER BY score ASC LIMIT 1")
            row = c.fetchone()
            most_controversial = f"{row[0]} ({row[1]} pts)" if row else "N/A"
            # Total votes (battles)
            c.execute("SELECT SUM(score) FROM things WHERE approved = 1")
            total_votes = c.fetchone()[0] or 0
        embed = discord.Embed(title="Thing Game Statistics", color=discord.Color.purple())
        embed.add_field(name="Most Submissions", value=most_submitted, inline=False)
        embed.add_field(name="Most Approved", value=most_approved, inline=False)
        embed.add_field(name="Approval Rate", value=approval_rate, inline=False)
        embed.add_field(name="Most Popular Thing", value=most_popular, inline=False)
        embed.add_field(name="Most Controversial Thing", value=most_controversial, inline=False)
        embed.add_field(name="Total Votes (Net)", value=total_votes, inline=False)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ThingGame(bot))
