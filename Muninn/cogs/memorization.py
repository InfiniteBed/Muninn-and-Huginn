import discord
from discord.ext import commands
from discord.ui import View, Button
import json
import random
import os
import asyncio  # Add this import for the delay functionality
import string  # Add this import for handling punctuation

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
    async def create_set(self, ctx, group: str, set_name: str, skip_non_essential: bool, *memorization_types):
        """Create a new memorization set with multiple types and a toggle for skipping non-essential words."""
        if group not in self.data:
            self.data[group] = {}
        if set_name in self.data[group]:
            await ctx.send(f"A set with the name '{set_name}' already exists in group '{group}'.")
            return
        self.data[group][set_name] = {
            "author": ctx.author.id,
            "types": list(memorization_types),
            "skip_non_essential": skip_non_essential,
            "items": []
        }
        self.save_data()
        await ctx.send(f"Set '{set_name}' created in group '{group}' with types: {', '.join(memorization_types)} and skip_non_essential set to {skip_non_essential}.")

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

            # Allow user to select memorization type if multiple are available
            if len(set_data["types"]) > 1:
                embed.title = f"Select a Memorization Type for '{set_name}'"
                embed.description = "Choose a memorization type to practice."
                view.clear_items()

                for mem_type in set_data["types"]:
                    button = Button(label=mem_type, style=discord.ButtonStyle.primary)
                    button.callback = self.create_type_callback(ctx, group, set_name, mem_type, embed, view)
                    view.add_item(button)

                await interaction.response.edit_message(embed=embed, view=view)
            else:
                await self.start_practice(ctx, set_data, set_data["types"][0])
        return callback

    def create_type_callback(self, ctx, group, set_name, mem_type, embed, view):
        async def callback(interaction):
            if interaction.user != ctx.author:
                await interaction.response.send_message("This button is not for you!", ephemeral=True)
                return

            set_data = self.data[group][set_name]
            embed.title = f"Practicing Set: {set_name} ({mem_type})"
            embed.description = f"Memorization Type: {mem_type}\n\nStarting practice..."
            view.clear_items()

            await interaction.response.edit_message(embed=embed, view=view)
            await self.start_practice(ctx, set_data, mem_type)
        return callback

    async def start_practice(self, ctx, set_data, memorization_type):
        """Start the practice session."""
        # Delete the embed in the root channel
        root_message = None
        async for message in ctx.channel.history(limit=1):
            if message.author == self.bot.user:
                root_message = message
                break
        if root_message:
            await root_message.delete()

        # Create a thread for the study session
        thread = await ctx.channel.create_thread(
            name=f"Study Session: {memorization_type}",
            type=discord.ChannelType.public_thread
        )

        await thread.send("How many questions would you like to practice? (Enter a number or type `!stop` to cancel.)")

        def check(m):
            return m.author == ctx.author and m.channel == thread

        try:
            while True:
                response = await self.bot.wait_for("message", check=check, timeout=600)  # 10-minute timeout
                if response.content.strip().lower() == "!stop":
                    await thread.send("Practice session stopped.")
                    await asyncio.sleep(5)  # Pause before deleting the thread
                    await thread.delete()
                    return
                elif response.content.isdigit():
                    num_questions = int(response.content)
                    break
                else:
                    await thread.send("Please enter a valid number or type `!stop` to cancel.")
        except asyncio.TimeoutError:
            await thread.send("No response received. Ending practice session.")
            await asyncio.sleep(5)  # Pause before deleting the thread
            await thread.delete()
            return

        correct_answers = 0
        total_questions = 0
        message = None  # Track the message to edit

        skip_non_essential = set_data.get("skip_non_essential", False)
        non_essential_words = {"a", "an", "the", "and", "or", "but", "of", "in", "on", "at", "to", "by", "for", "with"}

        for question_number in range(1, num_questions + 1):
            item = random.choice(set_data["items"])

            # Filter out non-essential words if the toggle is enabled
            if skip_non_essential:
                words = [word for word in item["body"].split() if word.lower() not in non_essential_words]
            else:
                words = item["body"].split()

            # Add "Question X of Y" to the title
            question_title = f"Question {question_number} of {num_questions}: {item['title']}"

            if memorization_type == "Multiple Choice (All Words)":
                is_correct, message = await self.multiple_choice_all(ctx, item, message, thread, question_title, words)
            elif memorization_type == "Multiple Choice (Single Word)":
                is_correct, message = await self.multiple_choice_one(ctx, item, message, thread, question_title)
            elif memorization_type == "Fill in the Blank (All Words)":
                is_correct, message = await self.fill_in_blank_all(ctx, item, message, thread, question_title, words)
            elif memorization_type == "Fill in the Blank (Single Word)":
                is_correct, message = await self.fill_in_blank_one(ctx, item, message, thread, question_title)
            elif memorization_type == "Sequential Practice (All Words)":
                is_correct, message = await self.sequential_practice(ctx, item, message, thread, question_title)
            else:
                await thread.send(f"Unknown memorization type: {memorization_type}")
                return

            total_questions += 1
            if is_correct:
                correct_answers += 1

            # Add a delay before proceeding to the next question
            await asyncio.sleep(2)

        # Show results
        await self.show_results(ctx, correct_answers, total_questions, message, thread)

        # Pause before deleting the thread
        await asyncio.sleep(10)
        await thread.delete()

    async def show_results(self, ctx, correct_answers, total_questions, message, thread):
        """Display the test results."""
        embed = discord.Embed(
            title="Practice Results",
            description=f"You answered {correct_answers} out of {total_questions} questions correctly!",
            color=discord.Color.green() if correct_answers == total_questions else discord.Color.orange()
        )
        if message:
            await message.edit(embed=embed, view=None)
        else:
            await thread.send(embed=embed)

    async def multiple_choice_all(self, ctx, item, message, thread, question_title, words):
        """Handle Multiple Choice (all words)."""
        blank_word = random.choice(words)
        options = random.sample(words, min(4, len(words)))
        if blank_word not in options:
            options.append(blank_word)
        random.shuffle(options)

        embed = discord.Embed(title=question_title, description=item["body"].replace(blank_word, "???"))
        view = View()
        result = {"is_correct": False}

        for option in options:
            button = Button(label=option, style=discord.ButtonStyle.primary)

            async def callback(interaction, option=option):
                if interaction.user != ctx.author:
                    await interaction.response.send_message("This button is not for you!", ephemeral=True)
                    return
                result["is_correct"] = (option == blank_word)
                embed.description += f"\n\n{'Correct!' if result['is_correct'] else 'Incorrect.'}"
                await interaction.response.edit_message(embed=embed, view=None)
                view.stop()

            button.callback = callback
            view.add_item(button)

        if message:
            await message.edit(embed=embed, view=view)
        else:
            message = await thread.send(embed=embed, view=view)

        await view.wait()
        return result["is_correct"], message

    async def multiple_choice_one(self, ctx, item, message, thread, question_title):
        """Handle Multiple Choice (one word)."""
        correct_word = item["solutions"][0]
        options = random.sample(item["body"].split(), min(4, len(item["body"].split())))
        if correct_word not in options:
            options.append(correct_word)
        random.shuffle(options)

        embed = discord.Embed(title=question_title, description=item["body"].replace(correct_word, "_____"))
        view = View()
        result = {"is_correct": False}

        for option in options:
            button = Button(label=option, style=discord.ButtonStyle.primary)

            async def callback(interaction, option=option):
                if interaction.user != ctx.author:
                    await interaction.response.send_message("This button is not for you!", ephemeral=True)
                    return
                result["is_correct"] = (option == correct_word)
                embed.description += f"\n\n{'Correct!' if result['is_correct'] else 'Incorrect.'}"
                await interaction.response.edit_message(embed=embed, view=None)
                view.stop()

            button.callback = callback
            view.add_item(button)

        if message:
            await message.edit(embed=embed, view=view)
        else:
            message = await thread.send(embed=embed, view=view)

        await view.wait()
        return result["is_correct"], message

    async def fill_in_blank_all(self, ctx, item, message, thread, question_title, words):
        """Handle Fill in the Blank (all words) with dashes."""
        blank_word = random.choice(words)

        # Replace only the first occurrence of the blank word
        blanked_body = item["body"].replace(f" {blank_word} ", " ----- ", 1)

        embed = discord.Embed(title=question_title, description=blanked_body)
        if message:
            await message.edit(embed=embed, view=None)
        else:
            message = await thread.send(embed=embed)

        def check(m):
            return m.author == ctx.author and m.channel == thread

        try:
            response = await self.bot.wait_for("message", check=check, timeout=60)  # 1-minute timeout
            # Strip punctuation from both the user's response and the blank word
            user_answer = response.content.strip().translate(str.maketrans('', '', string.punctuation))
            correct_answer = blank_word.translate(str.maketrans('', '', string.punctuation))

            if user_answer.lower() == correct_answer.lower():
                embed.description += "\n\nCorrect!"
                await message.edit(embed=embed)
                await response.delete()  # Delete the user's answer
                return True, message
            else:
                embed.description += f"\n\nIncorrect. The correct word was '{blank_word}'."
                await message.edit(embed=embed)
                await response.delete()  # Delete the user's answer
                return False, message
        except asyncio.TimeoutError:
            embed.description += f"\n\nTime's up! The correct word was '{blank_word}'."
            await message.edit(embed=embed)
            return False, message

    async def fill_in_blank_one(self, ctx, item, message, thread, question_title):
        """Handle Fill in the Blank (one word) with dashes."""
        correct_word = item["solutions"][0]

        embed = discord.Embed(title=question_title, description=item["body"].replace(correct_word, "-----"))
        if message:
            await message.edit(embed=embed, view=None)
        else:
            message = await thread.send(embed=embed)

        def check(m):
            return m.author == ctx.author and m.channel == thread

        try:
            response = await self.bot.wait_for("message", check=check, timeout=30)
            # Strip punctuation from both the user's response and the correct word
            user_answer = response.content.strip().translate(str.maketrans('', '', string.punctuation))
            correct_answer = correct_word.translate(str.maketrans('', '', string.punctuation))

            if user_answer.lower() == correct_answer.lower():
                embed.description += "\n\nCorrect!"
                await message.edit(embed=embed)
                await response.delete()  # Delete the user's answer
                return True, message
            else:
                embed.description += f"\n\nIncorrect. The correct word was '{correct_word}'."
                await message.edit(embed=embed)
                await response.delete()  # Delete the user's answer
                return False, message
        except asyncio.TimeoutError:
            embed.description += f"\n\nTime's up! The correct word was '{correct_word}'."
            await message.edit(embed=embed)
            return False, message

    async def sequential_practice(self, ctx, item, message, thread, question_title):
        """Handle Sequential Practice (All Words)."""
        words = item["body"].split()
        correct_answers = 0

        for blank_word in words:
            # Replace only the first occurrence of the blank word
            blanked_body = item["body"].replace(f" {blank_word} ", " ----- ", 1)

            embed = discord.Embed(title=question_title, description=blanked_body)
            if message:
                await message.edit(embed=embed, view=None)
            else:
                message = await thread.send(embed=embed)

            def check(m):
                return m.author == ctx.author and m.channel == thread

            try:
                response = await self.bot.wait_for("message", check=check, timeout=60)  # 1-minute timeout
                if response.content.strip() == blank_word:
                    embed.description += "\n\nCorrect!"
                    correct_answers += 1
                else:
                    embed.description += f"\n\nIncorrect. The correct word was '{blank_word}'."
                await message.edit(embed=embed)
                await response.delete()  # Delete the user's answer
            except asyncio.TimeoutError:
                embed.description += f"\n\nTime's up! The correct word was '{blank_word}'."
                await message.edit(embed=embed)

            # Add a delay before proceeding to the next word
            await asyncio.sleep(2)

        return correct_answers == len(words), message

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
