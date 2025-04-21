import discord
from discord.ext import commands
import json
from discord.ui import View, Button
import asyncio
import sqlite3

class Contribution(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_file = "discord.db"
        self.create_star_table()

    def create_star_table(self):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS stars (
            guild_id INTEGER,
            user_id INTEGER,
            stars INTEGER,
            PRIMARY KEY (guild_id, user_id)
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
        embed = discord.Embed(title="You made a contribution!",
                              description=f"Your Contribution: **{self.initial_response}**\n\nContribution Type: **{self.contribution_type}**")
        
        await interaction.message.edit(embed=embed, view=None)

        await interaction.response.send_message(
            f"You selected **{self.contribution_type}**. Your contribution has been sent to the bot owner.",
            ephemeral=True
        )

        conn = sqlite3.connect('discord.db')
        cursor = conn.cursor()

        cursor.execute('SELECT stars FROM stars WHERE guild_id = ? AND user_id = ?', (interaction.guild.id, self.author.id))
        result = cursor.fetchone()

        if result:
            cursor.execute('UPDATE stars SET stars = stars + 1 WHERE guild_id = ? AND user_id = ?', (interaction.guild.id, self.author.id))
        else:
            cursor.execute('INSERT INTO stars (guild_id, user_id, stars) VALUES (?, ?, ?)', (interaction.guild.id, self.author.id, 1))

        conn.commit()
        conn.close()

        bot_owner = self.bot.get_user(self.bot.owner_id)
        embed_to_author = discord.Embed(
            title="New Contribution Received",
            color=discord.Color.green(),
            description=(
                f"Type: {self.contribution_type}\n"
                f"Initial Response: {self.initial_response}"
            )
        )
        embed_to_author.set_author(name=self.author.name, icon_url=self.author.avatar.url if self.author.avatar else self.author.default_avatar.url)
        await bot_owner.send(embed=embed_to_author)

async def setup(bot):
    await bot.add_cog(Contribution(bot))