import discord
from discord.ext import commands
import yaml
from discord.ui import View, Button
import asyncio
import sqlite3
import datetime
import os

class ContributionApprovalView(View):
    def __init__(self, contribution_id, bot_owner_id):
        super().__init__(timeout=None)
        self.contribution_id = contribution_id
        self.bot_owner_id = bot_owner_id

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green, custom_id="approve_contribution")
    async def approve(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.bot_owner_id:
            await interaction.response.send_message("Only the bot owner can approve.", ephemeral=True)
            return
        
        submitter_id = None
        guild_id = None
        content = None
        contribution_type = None
        
        with sqlite3.connect("discord.db") as conn:
            c = conn.cursor()
            c.execute("UPDATE contributions SET approved = 1, approved_at = ? WHERE id = ?", 
                     (datetime.datetime.utcnow().isoformat(), self.contribution_id))
            c.execute("SELECT submitter_id, guild_id, content, contribution_type FROM contributions WHERE id = ?", (self.contribution_id,))
            row = c.fetchone()
            if row:
                submitter_id, guild_id, content, contribution_type = row
            conn.commit()
        
        # Special handling for Random Prompts - communicate with Huginn
        if contribution_type == "Random Prompts":
            await self.add_prompt_to_huginn(content, submitter_id, interaction.client)
        
        # Award a star to the submitter
        if submitter_id and guild_id:
            with sqlite3.connect("discord.db") as conn:
                c = conn.cursor()
                c.execute('SELECT stars FROM stars WHERE guild_id = ? AND user_id = ?', (guild_id, submitter_id))
                result = c.fetchone()
                if result:
                    new_stars = result[0] + 1
                    c.execute('UPDATE stars SET stars = ? WHERE guild_id = ? AND user_id = ?', 
                             (new_stars, guild_id, submitter_id))
                else:
                    c.execute('INSERT INTO stars (guild_id, user_id, stars) VALUES (?, ?, ?)', 
                             (guild_id, submitter_id, 1))
                conn.commit()
        
        await interaction.response.send_message("Contribution approved! Submitter awarded a star.", ephemeral=True)
        await interaction.message.edit(view=None)

    async def add_prompt_to_huginn(self, content, submitter_id, bot):
        """Add approved prompt to shared communication for Huginn to pick up"""
        try:
            # Get submitter name
            submitter_name = "Anonymous"
            try:
                user = await bot.fetch_user(submitter_id)
                submitter_name = user.display_name
            except:
                pass
            
            # Create new prompt object
            new_prompt = {
                "text": content,
                "contributor": submitter_name,
                "downvotes": 0,
                "downvoted_by": [],
                "added_at": datetime.datetime.utcnow().isoformat(),
                "status": "pending_addition"
            }
            
            # Add to shared communication file for Huginn to pick up
            shared_comm_path = "/mnt/Lake/Starboard/Discord/shared_communication.yaml"
            try:
                # Load existing communication data
                if os.path.exists(shared_comm_path):
                    with open(shared_comm_path, 'r', encoding='utf-8') as f:
                        comm_data = yaml.safe_load(f) or {}
                else:
                    comm_data = {}
                
                if "communication" not in comm_data:
                    comm_data["communication"] = {}
                if "pending_prompts" not in comm_data["communication"]:
                    comm_data["communication"]["pending_prompts"] = []
                
                # Add the new prompt to pending list
                comm_data["communication"]["pending_prompts"].append(new_prompt)
                
                # Update last check time to signal new data
                comm_data["communication"]["last_update"] = datetime.datetime.utcnow().isoformat()
                
                # Write back to shared file
                with open(shared_comm_path, 'w', encoding='utf-8') as f:
                    yaml.dump(comm_data, f, default_flow_style=False, allow_unicode=True, indent=2)
                
                print(f"Added prompt to shared communication for Huginn: {content}")
                
            except Exception as e:
                print(f"Error updating shared communication: {e}")
            
        except Exception as e:
            print(f"Error in add_prompt_to_huginn: {e}")

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.red, custom_id="reject_contribution")
    async def reject(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.bot_owner_id:
            await interaction.response.send_message("Only the bot owner can reject.", ephemeral=True)
            return
        
        with sqlite3.connect("discord.db") as conn:
            c = conn.cursor()
            c.execute("UPDATE contributions SET approved = -1, approved_at = ? WHERE id = ?", 
                     (datetime.datetime.utcnow().isoformat(), self.contribution_id))
            conn.commit()
        
        await interaction.response.send_message("Contribution rejected.", ephemeral=True)
        await interaction.message.edit(view=None)

class Contribution(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_file = "discord.db"
        self.create_tables()

    def create_tables(self):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Create stars table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS stars (
            guild_id INTEGER,
            user_id INTEGER,
            stars INTEGER,
            PRIMARY KEY (guild_id, user_id)
        )''')
        
        # Create contributions table for pending submissions
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS contributions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submitter_id INTEGER,
            guild_id INTEGER,
            content TEXT,
            contribution_type TEXT,
            approved INTEGER DEFAULT 0,
            submitted_at TEXT,
            approved_at TEXT
        )''')
        
        conn.commit()
        conn.close()

    @commands.command()
    async def contribute(self, ctx, *, initial_response: str = None):
        if not initial_response:
            await ctx.send("Please provide an initial response. Usage: `!contribute <your response>`")
            return

        embed = discord.Embed(
            title="Contribute Data",
            description=(
                f"Your initial response: **{initial_response}**\n"
                "Now, choose the type of contribution you'd like to make by clicking one of the buttons below!"
            ),
            color=discord.Color.purple()
        )
        view = ContributionTypeView(self.bot, ctx.author, initial_response)
        await ctx.send(embed=embed, view=view)

class ContributionTypeView(View):
    def __init__(self, bot, author, initial_response):
        super().__init__()
        self.bot = bot
        self.author = author
        self.initial_response = initial_response

        # Add buttons with unique callbacks
        self.add_item(ContributionButton("Muninn @ Response", "Muninn @ Response", bot, author, initial_response))
        self.add_item(ContributionButton("Huginn @ Response", "Huginn @ Response", bot, author, initial_response))
        self.add_item(ContributionButton("Random Insults", "Random Insults", bot, author, initial_response))
        self.add_item(ContributionButton("Random Prompts", "Random Prompts", bot, author, initial_response))
        self.add_item(ContributionButton("Message Rewards", "Message Rewards", bot, author, initial_response))
        self.add_item(ContributionButton("Items/Weapons/Armor", "Items/Weapons/Armor", bot, author, initial_response))
        self.add_item(ContributionButton("Jobs", "Jobs", bot, author, initial_response))
        self.add_item(ContributionButton("Commands", "Commands", bot, author, initial_response))

class ContributionButton(Button):
    def __init__(self, label, contribution_type, bot, author, initial_response):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.contribution_type = contribution_type
        self.bot = bot
        self.author = author
        self.initial_response = initial_response

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.author:
            await interaction.response.send_message("This button is not for you.", ephemeral=True)
            return

        # Disable all buttons immediately after a valid interaction
        embed = discord.Embed(title="Contribution Submitted!",
                              description=f"Your Contribution: **{self.initial_response}**\n\nContribution Type: **{self.contribution_type}**\n\n✅ Your contribution has been submitted for approval!")
        
        await interaction.message.edit(embed=embed, view=None)

        await interaction.response.send_message(
            f"You selected **{self.contribution_type}**. Your contribution has been sent to the bot owner for approval. You'll receive a star if it's approved!",
            ephemeral=True
        )

        # Store the contribution in pending state
        now = datetime.datetime.utcnow().isoformat()
        with sqlite3.connect('discord.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''INSERT INTO contributions 
                             (submitter_id, guild_id, content, contribution_type, submitted_at) 
                             VALUES (?, ?, ?, ?, ?)''', 
                          (self.author.id, interaction.guild.id, self.initial_response, 
                           self.contribution_type, now))
            contribution_id = cursor.lastrowid
            conn.commit()

        # Send approval request to bot owner
        bot_owner = self.bot.get_user(self.bot.owner_id)
        if bot_owner:
            embed_to_owner = discord.Embed(
                title="New Contribution Awaiting Approval",
                color=discord.Color.orange(),
                description=(
                    f"**Type:** {self.contribution_type}\n"
                    f"**Content:** {self.initial_response}\n"
                    f"**Submitted by:** {self.author.mention} ({self.author.display_name})\n"
                    f"**Guild:** {interaction.guild.name if interaction.guild else 'DM'}"
                )
            )
            embed_to_owner.set_author(
                name=self.author.display_name, 
                icon_url=self.author.avatar.url if self.author.avatar else self.author.default_avatar.url
            )
            embed_to_owner.set_footer(text=f"Contribution ID: {contribution_id}")
            
            view = ContributionApprovalView(contribution_id, self.bot.owner_id)
            await bot_owner.send(embed=embed_to_owner, view=view)

    @commands.command()
    async def pending_contributions(self, ctx):
        """View all pending contributions (bot owner only)"""
        if ctx.author.id != self.bot.owner_id:
            await ctx.send("This command is only available to the bot owner.")
            return
        
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''SELECT id, submitter_id, guild_id, content, contribution_type, submitted_at 
                         FROM contributions WHERE approved = 0 ORDER BY submitted_at DESC''')
        pending = cursor.fetchall()
        conn.close()
        
        if not pending:
            await ctx.send("No pending contributions.")
            return
        
        embeds = []
        for contribution_id, submitter_id, guild_id, content, contribution_type, submitted_at in pending:
            guild = self.bot.get_guild(guild_id) if guild_id else None
            submitter = self.bot.get_user(submitter_id)
            
            embed = discord.Embed(
                title=f"Pending Contribution #{contribution_id}",
                color=discord.Color.orange()
            )
            embed.add_field(name="Type", value=contribution_type, inline=True)
            embed.add_field(name="Content", value=content[:1000] + ("..." if len(content) > 1000 else ""), inline=False)
            embed.add_field(name="Submitter", value=f"{submitter.mention} ({submitter.display_name})" if submitter else "Unknown", inline=True)
            embed.add_field(name="Guild", value=guild.name if guild else "Unknown", inline=True)
            embed.add_field(name="Submitted", value=submitted_at, inline=True)
            embeds.append(embed)
        
        # Send embeds in batches to avoid hitting limits
        for i in range(0, len(embeds), 10):
            batch = embeds[i:i+10]
            for embed in batch:
                await ctx.send(embed=embed)

    @commands.command()
    async def contribution_stats(self, ctx):
        """View contribution statistics"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Get statistics
        cursor.execute("SELECT COUNT(*) FROM contributions")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM contributions WHERE approved = 1")
        approved = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM contributions WHERE approved = -1")
        rejected = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM contributions WHERE approved = 0")
        pending = cursor.fetchone()[0]
        
        # Most active contributor
        cursor.execute('''SELECT submitter_id, COUNT(*) FROM contributions 
                         GROUP BY submitter_id ORDER BY COUNT(*) DESC LIMIT 1''')
        most_active = cursor.fetchone()
        
        # Most successful contributor (highest approval rate with at least 3 submissions)
        cursor.execute('''SELECT submitter_id, 
                         COUNT(*) as total,
                         SUM(CASE WHEN approved = 1 THEN 1 ELSE 0 END) as approved_count,
                         ROUND(CAST(SUM(CASE WHEN approved = 1 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) * 100, 1) as approval_rate
                         FROM contributions 
                         WHERE approved != 0
                         GROUP BY submitter_id 
                         HAVING total >= 3
                         ORDER BY approval_rate DESC LIMIT 1''')
        most_successful = cursor.fetchone()
        
        conn.close()
        
        approval_rate = round((approved / total * 100), 1) if total > 0 else 0
        
        embed = discord.Embed(title="Contribution Statistics", color=discord.Color.blue())
        embed.add_field(name="Total Submissions", value=total, inline=True)
        embed.add_field(name="Approved", value=f"{approved} ({approval_rate}%)", inline=True)
        embed.add_field(name="Rejected", value=rejected, inline=True)
        embed.add_field(name="Pending", value=pending, inline=True)
        
        if most_active:
            user = self.bot.get_user(most_active[0])
            embed.add_field(name="Most Active Contributor", 
                           value=f"{user.mention if user else 'Unknown'} ({most_active[1]} submissions)", 
                           inline=False)
        
        if most_successful:
            user = self.bot.get_user(most_successful[0])
            embed.add_field(name="Most Successful Contributor", 
                           value=f"{user.mention if user else 'Unknown'} ({most_successful[3]}% approval rate, {most_successful[1]} submissions)", 
                           inline=False)
        
        await ctx.send(embed=embed)

    @commands.command()
    async def manual_approve(self, ctx, contribution_id: int):
        """Manually approve a contribution by ID (bot owner only)"""
        if ctx.author.id != self.bot.owner_id:
            await ctx.send("This command is only available to the bot owner.")
            return
        
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Get contribution details
        cursor.execute("SELECT submitter_id, guild_id, content, contribution_type FROM contributions WHERE id = ? AND approved = 0", 
                      (contribution_id,))
        contribution = cursor.fetchone()
        
        if not contribution:
            await ctx.send(f"No pending contribution found with ID {contribution_id}.")
            conn.close()
            return
        
        submitter_id, guild_id, content, contribution_type = contribution
        
        # Approve the contribution
        cursor.execute("UPDATE contributions SET approved = 1, approved_at = ? WHERE id = ?", 
                      (datetime.datetime.utcnow().isoformat(), contribution_id))
        
        # Special handling for Random Prompts
        if contribution_type == "Random Prompts":
            await self.add_prompt_to_huginn(content, submitter_id, self.bot)
        
        # Award star
        cursor.execute('SELECT stars FROM stars WHERE guild_id = ? AND user_id = ?', (guild_id, submitter_id))
        result = cursor.fetchone()
        if result:
            cursor.execute('UPDATE stars SET stars = stars + 1 WHERE guild_id = ? AND user_id = ?', 
                          (guild_id, submitter_id))
        else:
            cursor.execute('INSERT INTO stars (guild_id, user_id, stars) VALUES (?, ?, ?)', 
                          (guild_id, submitter_id, 1))
        
        conn.commit()
        conn.close()
        
        submitter = self.bot.get_user(submitter_id)
        embed = discord.Embed(
            title="Contribution Approved",
            color=discord.Color.green(),
            description=f"**ID:** {contribution_id}\n**Type:** {contribution_type}\n**Content:** {content[:500]}...\n**Submitter:** {submitter.mention if submitter else 'Unknown'}"
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def manual_reject(self, ctx, contribution_id: int):
        """Manually reject a contribution by ID (bot owner only)"""
        if ctx.author.id != self.bot.owner_id:
            await ctx.send("This command is only available to the bot owner.")
            return
        
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Get contribution details
        cursor.execute("SELECT submitter_id, guild_id, content, contribution_type FROM contributions WHERE id = ? AND approved = 0", 
                      (contribution_id,))
        contribution = cursor.fetchone()
        
        if not contribution:
            await ctx.send(f"No pending contribution found with ID {contribution_id}.")
            conn.close()
            return
        
        submitter_id, guild_id, content, contribution_type = contribution
        
        # Reject the contribution
        cursor.execute("UPDATE contributions SET approved = -1, approved_at = ? WHERE id = ?", 
                      (datetime.datetime.utcnow().isoformat(), contribution_id))
        
        conn.commit()
        conn.close()
        
        submitter = self.bot.get_user(submitter_id)
        embed = discord.Embed(
            title="Contribution Rejected",
            color=discord.Color.red(),
            description=f"**ID:** {contribution_id}\n**Type:** {contribution_type}\n**Content:** {content[:500]}...\n**Submitter:** {submitter.mention if submitter else 'Unknown'}"
        )
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Contribution(bot))