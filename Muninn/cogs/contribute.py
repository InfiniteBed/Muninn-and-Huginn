import discord
from discord.ext import commands
import json
from discord.ui import View, Button
import asyncio

class Contribution(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.file_path = "contributions.json"
        self.load_data()

    def load_data(self):
        try:
            with open(self.file_path, "r") as f:
                self.data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.data = {}

    def save_data(self):
        with open(self.file_path, "w") as f:
            json.dump(self.data, f, indent=4)

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
        self.add_item(ContributionButton("Randomized Insults", "Randomized Insults", bot, author, initial_response))
        self.add_item(ContributionButton("Mention Response", "Mention Response", bot, author, initial_response))
        self.add_item(ContributionButton("Randomized Prompts", "Randomized Prompts", bot, author, initial_response))
        self.add_item(ContributionButton("Message Rewards", "Message Rewards", bot, author, initial_response))
        self.add_item(ContributionButton("Custom Graphs", "Custom Graphs", bot, author, initial_response))
        self.add_item(ContributionButton("Items/Weapons/Armor", "Items/Weapons/Armor", bot, author, initial_response))
        self.add_item(ContributionButton("Expeditions", "Expeditions", bot, author, initial_response))
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
        for item in self.view.children:
            if isinstance(item, Button):
                item.disabled = True
        await interaction.message.edit(view=self.view)

        await interaction.response.send_message(
            f"You selected **{self.contribution_type}**. Your contribution has been sent to the bot owner.",
            ephemeral=True
        )

        cog = self.bot.get_cog("Contribution")
        cog.data.setdefault("submissions", []).append({
            "user": self.author.name,
            "type": self.contribution_type,
            "initial_response": self.initial_response
        })
        cog.save_data()

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