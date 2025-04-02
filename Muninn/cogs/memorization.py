import discord
from discord.ext import commands
from discord.ui import View, Button
import json
import random
import os

DATA_FILE = "memorization_data.json"

class Memorization(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data = {}

    def load_data(self):
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        return {}

    def save_data(self):
        with open(DATA_FILE, "w") as f:
            json.dump(self.data, f, indent=4)

    @commands.command(name="create_set")
    async def create_set(self, ctx, group: str, set_name: str, memorization_type: str):
        """Create a new memorization set."""
        if group not in self.data:
            self.data[group] = {}
        if set_name in self.data[group]:
            await ctx.send(f"A set with the name '{set_name}' already exists in group '{group}'.")
            return
        self.data[group][set_name] = {
            "author": ctx.author.id,
            "type": memorization_type,
            "items": []
        }
        self.save_data()
        await ctx.send(f"Set '{set_name}' created in group '{group}' with type '{memorization_type}'.")

    @commands.command(name="add_item")
    async def add_item(self, ctx, group: str, set_name: str, title: str, body: str, *solutions):
        """Add an item to a memorization set."""
        if group not in self.data or set_name not in self.data[group]:
            await ctx.send(f"Set '{set_name}' in group '{group}' does not exist.")
            return
        self.data[group][set_name]["items"].append({
            "title": title,
            "body": body,
            "solutions": list(solutions)
        })
        self.save_data()
        await ctx.send(f"Item '{title}' added to set '{set_name}' in group '{group}'.")

    @commands.command(name="practice")
    async def practice(self, ctx, group: str = None):
        """Start practicing a memorization set."""
        self.data = self.load_data()  # Load data when the command is invoked

        if not self.data:
            await ctx.send("No data available. Please create a set first.")
            return

        if group is None:
            # Present group options if no group is specified
            embed = discord.Embed(title="Select a Group", description="Choose a group to practice.")
            view = View()

            for group_name in self.data.keys():
                button = Button(label=group_name, style=discord.ButtonStyle.primary)
                button.callback = self.create_group_callback(ctx, group_name, embed, view)
                view.add_item(button)

            await ctx.send(embed=embed, view=view)
            return

        if group not in self.data:
            await ctx.send(f"Group '{group}' does not exist.")
            return

        # Present set options within the selected group
        embed = discord.Embed(title=f"Select a Set in '{group}'", description="Choose a set to practice.")
        view = View()

        for set_name in self.data[group].keys():
            button = Button(label=set_name, style=discord.ButtonStyle.primary)
            button.callback = self.create_set_callback(ctx, group, set_name, embed, view)
            view.add_item(button)

        await ctx.send(embed=embed, view=view)

    def create_group_callback(self, ctx, group_name, embed, view):
        async def callback(interaction):
            if interaction.user != ctx.author:
                await interaction.response.send_message("This button is not for you!", ephemeral=True)
                return

            # Update embed and view for set selection
            embed.title = f"Select a Set in '{group_name}'"
            embed.description = "Choose a set to practice."
            view.clear_items()

            for set_name in self.data[group_name].keys():
                button = Button(label=set_name, style=discord.ButtonStyle.primary)
                button.callback = self.create_set_callback(ctx, group_name, set_name, embed, view)
                view.add_item(button)

            await interaction.response.edit_message(embed=embed, view=view)
        return callback

    def create_set_callback(self, ctx, group, set_name, embed, view):
        async def callback(interaction):
            if interaction.user != ctx.author:
                await interaction.response.send_message("This button is not for you!", ephemeral=True)
                return

            set_data = self.data[group][set_name]
            if not set_data["items"]:
                await interaction.response.send_message(f"Set '{set_name}' in group '{group}' has no items.", ephemeral=True)
                return

            item = random.choice(set_data["items"])
            memorization_type = set_data["type"]

            if memorization_type == "Multiple Choice (all words)":
                await self.multiple_choice_all(ctx, item)
            elif memorization_type == "Multiple Choice (one word)":
                await self.multiple_choice_one(ctx, item)
            elif memorization_type == "Fill in the Blank (all words)":
                await self.fill_in_blank_all(ctx, item)
            elif memorization_type == "Fill in the Blank (one word)":
                await self.fill_in_blank_one(ctx, item)
            else:
                await ctx.send(f"Unknown memorization type: {memorization_type}")
        return callback

    async def multiple_choice_all(self, ctx, item):
        """Handle Multiple Choice (all words)."""
        words = item["body"].split()
        blank_word = random.choice(words)
        options = random.sample(words, min(4, len(words)))
        if blank_word not in options:
            options.append(blank_word)
        random.shuffle(options)

        embed = discord.Embed(title=item["title"], description=item["body"].replace(blank_word, "_____"))
        view = View()

        for option in options:
            button = Button(label=option, style=discord.ButtonStyle.primary)
            button.callback = self.create_callback(ctx, option == blank_word)
            view.add_item(button)

        await ctx.send(embed=embed, view=view)

    async def multiple_choice_one(self, ctx, item):
        """Handle Multiple Choice (one word)."""
        correct_word = item["solutions"][0]
        options = random.sample(item["body"].split(), min(4, len(item["body"].split())))
        if correct_word not in options:
            options.append(correct_word)
        random.shuffle(options)

        embed = discord.Embed(title=item["title"], description=item["body"].replace(correct_word, "_____"))
        view = View()

        for option in options:
            button = Button(label=option, style=discord.ButtonStyle.primary)
            button.callback = self.create_callback(ctx, option == correct_word)
            view.add_item(button)

        await ctx.send(embed=embed, view=view)

    async def fill_in_blank_all(self, ctx, item):
        """Handle Fill in the Blank (all words)."""
        words = item["body"].split()
        blank_word = random.choice(words)

        embed = discord.Embed(title=item["title"], description=item["body"].replace(blank_word, "_____"))
        await ctx.send(embed=embed)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            response = await self.bot.wait_for("message", check=check, timeout=30)
            if response.content.strip() == blank_word:
                await ctx.send("Correct!")
            else:
                await ctx.send(f"Incorrect. The correct word was '{blank_word}'.")
        except asyncio.TimeoutError:
            await ctx.send(f"Time's up! The correct word was '{blank_word}'.")

    async def fill_in_blank_one(self, ctx, item):
        """Handle Fill in the Blank (one word)."""
        correct_word = item["solutions"][0]

        embed = discord.Embed(title=item["title"], description=item["body"].replace(correct_word, "_____"))
        await ctx.send(embed=embed)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            response = await self.bot.wait_for("message", check=check, timeout=30)
            if response.content.strip() == correct_word:
                await ctx.send("Correct!")
            else:
                await ctx.send(f"Incorrect. The correct word was '{correct_word}'.")
        except asyncio.TimeoutError:
            await ctx.send(f"Time's up! The correct word was '{correct_word}'.")

    def create_callback(self, ctx, is_correct):
        async def callback(interaction):
            if interaction.user != ctx.author:
                await interaction.response.send_message("This button is not for you!", ephemeral=True)
                return
            if is_correct:
                await interaction.response.send_message("Correct!")
            else:
                await interaction.response.send_message("Incorrect.")
        return callback

async def setup(bot):
    await bot.add_cog(Memorization(bot))
