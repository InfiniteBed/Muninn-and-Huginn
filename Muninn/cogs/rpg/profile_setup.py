import discord
from discord.ext import commands
from discord.ui import Button, View
import sqlite3
import random
import os
import requests
from PIL import Image
from io import BytesIO
import time
import asyncio

# List of available options for profile setup
classes = ["Barbarian", "Bard", "Cleric", "Druid", "Fighter", "Monk", "Paladin", "Ranger", "Rogue", "Sorcerer", "Warlock", "Wizard", "Artificer"]
races = ["Dragonborn", "Dwarf", "Elf", "Gnome", "Half-Elf", "Half-Orc", "Halfling", "Human", "Tiefling", "Aarakocra", "Genasi", "Goliath", "Tabaxi", "Triton", "Firbolg", "Kenku", "Lizardfolk", "Orc", "Yuan-Ti Pureblood", "Goblin", "Hobgoblin", "Kobold", "Tortle", "Changeling", "Shifter", "Warforged", "Kalashtar", "Gith", "Loxodon", "Minotaur", "Simic Hybrid", "Vedalken", "Centaur", "Satyr", "Leonin", "Owlin", "Fairy", "Harengon", "Autognome", "Plasmoid", "Thri-Kreen"]
alignments = ["Lawful Good", "Neutral Good", "Chaotic Good", "Lawful Neutral", "True Neutral", "Chaotic Neutral", "Lawful Evil", "Neutral Evil", "Chaotic Evil"]

class Setup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.image_dir = "profile_images"  # Directory to store profile images
        
        # Make sure the directory exists
        if not os.path.exists(self.image_dir):
            os.makedirs(self.image_dir)

    async def ask_question(self, thread, ctx, question, expected_responses=[]):
        await thread.send(question)

        def check(message):
            return message.author == ctx.author and message.channel == thread

        while True:
            response = await self.bot.wait_for('message', check=check)
            if response.content.lower() == 'exit':
                await thread.delete()
                await ctx.send("Setup was cancelled, and the thread has been deleted.")
                return None

            response_content = response.content.title()
            if expected_responses and response_content not in expected_responses:
                await thread.send(f"'{response_content}' is not a recognized response. Are you sure? (yes/no)")
                confirmation = await self.bot.wait_for('message', check=check)
                if confirmation.content.lower() != 'yes':
                    await thread.send("Please send the desired response.")
                    continue

            return response_content

    async def check_and_create_profile(self, ctx):
        conn = sqlite3.connect('discord.db')
        try:
            c = conn.cursor()

            # Create tables if they do not exist
            c.execute('''
                CREATE TABLE IF NOT EXISTS profiles (
                    user_id INTEGER PRIMARY KEY,
                    class TEXT,
                    alignment TEXT,
                    gender TEXT,
                    race TEXT,
                    name TEXT,
                    ability_scores TEXT,
                    bio TEXT
                )
            ''')

            c.execute('''
                CREATE TABLE IF NOT EXISTS stats (
                    user_id INTEGER PRIMARY KEY, 
                    health INTEGER,
                    health_max INTEGER,
                    health_boost INTEGER,
                    defense INTEGER,
                    defense_boost INTEGER,
                    attack INTEGER,
                    attack_boost INTEGER,
                    activity TEXT,
                    level INTEGER,
                    coins INTEGER
                )
            ''')

            c.execute('''
                CREATE TABLE IF NOT EXISTS proficiencies (
                    user_id INTEGER PRIMARY KEY,
                    author NUMERIC,
                    baking NUMERIC,
                    brewer NUMERIC,
                    carpentry NUMERIC,
                    cleaning NUMERIC,
                    coachman NUMERIC,
                    cooking NUMERIC,
                    cupbearing NUMERIC,
                    farming NUMERIC,
                    fishing NUMERIC,
                    floristry NUMERIC,
                    gardening NUMERIC,
                    guarding NUMERIC,
                    glassblowing NUMERIC,
                    healing NUMERIC,
                    husbandry NUMERIC,
                    innkeeping NUMERIC,
                    knighthood NUMERIC,
                    leadership NUMERIC,
                    masonry NUMERIC,
                    metalworking NUMERIC,
                    painting NUMERIC,
                    pottery NUMERIC,
                    royalty NUMERIC,
                    sculpting NUMERIC,
                    smithing NUMERIC,
                    spinning NUMERIC,
                    stablekeeping NUMERIC,
                    tailoring NUMERIC,
                    teaching NUMERIC,
                    vigilance NUMERIC
                )
            ''')
            
            c.execute('''
                INSERT OR REPLACE INTO proficiencies (
                    user_id, author, baking, brewer, carpentry, cleaning, coachman, cooking, cupbearing, farming, fishing, floristry, gardening, guarding, glassblowing, healing, husbandry, innkeeping, knighthood, leadership, masonry, metalworking, painting, pottery, royalty, sculpting, smithing, spinning, stablekeeping, tailoring, teaching, vigilance
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (ctx.author.id, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))
            conn.commit()

            c.execute('''
                CREATE TABLE IF NOT EXISTS equipped_items (
                    user_id INTEGER PRIMARY KEY,
                    head TEXT,
                    upper TEXT,
                    lower TEXT,
                    feet TEXT,
                    hand_left TEXT,
                    hand_right TEXT
                )
            ''')

            c.execute('SELECT * FROM profiles WHERE user_id = ?', (ctx.author.id,))
            profile = c.fetchone()

            return profile
        except sqlite3.Error as e:
            await ctx.send(f"An error occurred while accessing the database: {e}")
            return None
        finally:
            conn.close()

    async def ask_with_buttons(self, ctx, thread, question, options):
        """Ask a question using buttons and return the selected option."""
        await thread.send(question)

        class ButtonView(View):
            def __init__(self, options):
                super().__init__()
                self.value = None

                for option in options:
                    self.add_item(Button(label=option, style=discord.ButtonStyle.primary, custom_id=option))

            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                return interaction.user == ctx.author

            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
            async def cancel(self, button: Button, interaction: discord.Interaction):
                self.value = "exit"
                self.stop()

        view = ButtonView(options)
        message = await thread.send(view=view)

        try:
            await asyncio.wait_for(view.wait(), timeout=900)  # Wait for 15 minutes (maximum allowed by Discord)
        except asyncio.TimeoutError:
            await message.delete()
            await thread.send("No response received. Resending the buttons...")
            return await self.ask_with_buttons(ctx, thread, question, options)

        await message.delete()

        if view.value == "exit":
            await thread.delete()
            await ctx.send("Setup was cancelled, and the thread has been deleted.")
            return None

        return view.value

    async def ask_with_buttons_or_other(self, ctx, thread, question, options, custom_prompt):
        """Ask a question using buttons with an 'Other' option for custom input."""
        await thread.send(question)

        class ButtonView(View):
            def __init__(self, options):
                super().__init__()
                self.value = None

                for option in options:
                    self.add_item(Button(label=option, style=discord.ButtonStyle.primary, custom_id=option))

                self.add_item(Button(label="Other", style=discord.ButtonStyle.secondary, custom_id="other"))

            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                return interaction.user == ctx.author

            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
            async def cancel(self, button: Button, interaction: discord.Interaction):
                self.value = "exit"
                self.stop()

        view = ButtonView(options)
        message = await thread.send(view=view)

        try:
            await asyncio.wait_for(view.wait(), timeout=900)  # Wait for 15 minutes (maximum allowed by Discord)
        except asyncio.TimeoutError:
            await message.delete()
            await thread.send("No response received. Resending the buttons...")
            return await self.ask_with_buttons_or_other(ctx, thread, question, options, custom_prompt)

        await message.delete()

        if view.value == "exit":
            await thread.delete()
            await ctx.send("Setup was cancelled, and the thread has been deleted.")
            return None

        if view.value == "other":
            await thread.send(custom_prompt)

            def check(message):
                return message.author == ctx.author and message.channel == thread

            while True:
                try:
                    response = await self.bot.wait_for('message', check=check, timeout=900)  # Wait for 15 minutes
                except asyncio.TimeoutError:
                    await thread.send("No response received. Please provide your input or type 'exit' to cancel.")
                    continue

                if response.content.lower() == 'exit':
                    await thread.delete()
                    await ctx.send("Setup was cancelled, and the thread has been deleted.")
                    return None

                response_content = response.content.title()
                if response_content not in options:
                    await thread.send(f"'{response_content}' is not a recognized option. Are you sure? (yes/no)")
                    try:
                        confirmation = await self.bot.wait_for('message', check=check, timeout=900)  # Wait for 15 minutes
                    except asyncio.TimeoutError:
                        await thread.send("No response received. Please confirm or type 'exit' to cancel.")
                        continue

                    if confirmation.content.lower() != 'yes':
                        await thread.send("Please send the desired response.")
                        continue

                return response_content

        return view.value

    async def ask_with_paginated_buttons(self, ctx, thread, question, options):
        """Ask a question using paginated buttons and return the selected option."""
        await thread.send(question)

        class PaginatedButtonView(View):
            def __init__(self, options, page_size=23):  # Limit to 23 to account for navigation buttons
                super().__init__(timeout=900)  # Set timeout to 15 minutes
                self.options = options
                self.page_size = page_size
                self.current_page = 0
                self.value = None
                self.update_buttons()

            def update_buttons(self):
                self.clear_items()
                start = self.current_page * self.page_size
                end = start + self.page_size
                for option in self.options[start:end]:
                    self.add_item(Button(label=option, style=discord.ButtonStyle.primary, custom_id=option))

                # Add navigation buttons if necessary
                if self.current_page > 0:
                    self.add_item(Button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="previous"))
                if end < len(self.options):
                    self.add_item(Button(label="Next", style=discord.ButtonStyle.secondary, custom_id="next"))

                self.add_item(Button(label="Cancel", style=discord.ButtonStyle.danger, custom_id="cancel"))

            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                # Ensure the interaction is from the correct user
                if interaction.user != ctx.author:
                    await interaction.response.send_message("You are not allowed to interact with these buttons.", ephemeral=True)
                    return False
                return True

            async def on_timeout(self):
                self.value = "timeout"
                self.stop()

            async def interaction_handler(self, interaction: discord.Interaction):
                """Handle button interactions."""
                if interaction.data["custom_id"] == "previous":
                    self.current_page -= 1
                    self.update_buttons()
                    await interaction.response.edit_message(view=self)
                elif interaction.data["custom_id"] == "next":
                    self.current_page += 1
                    self.update_buttons()
                    await interaction.response.edit_message(view=self)
                elif interaction.data["custom_id"] == "cancel":
                    self.value = "exit"
                    self.stop()
                else:
                    self.value = interaction.data["custom_id"]
                    self.stop()

        view = PaginatedButtonView(options)
        message = await thread.send(view=view)

        # Explicitly handle interactions
        while not view.is_finished():
            try:
                interaction = await self.bot.wait_for("interaction", timeout=900)  # Wait for 15 minutes
                if interaction.message.id == message.id:
                    await view.interaction_handler(interaction)
            except asyncio.TimeoutError:
                break

        await message.delete()

        if view.value == "exit":
            await thread.delete()
            await ctx.send("Setup was cancelled, and the thread has been deleted.")
            return None

        if view.value == "timeout":
            await thread.send("No response received. Setup timed out.")
            return None

        return view.value

    async def profile_setup_step(self, ctx, step, question, choices=None, field_name=None):
        profile = await self.check_and_create_profile(ctx)
        if not profile:
            await ctx.send("Your profile is incomplete. Please start the full setup using `!profile_setup`.")
            return

        thread = await ctx.channel.create_thread(name=f"{step} Setup")
        await thread.add_user(ctx.author)

        if choices:
            response = await self.ask_with_paginated_buttons(
                ctx,
                thread,
                question,
                choices
            )
        else:
            response = await self.ask_question(thread, ctx, question)

        if not response:
            return

        conn = sqlite3.connect('discord.db')
        try:
            c = conn.cursor()
            c.execute(f'UPDATE profiles SET {field_name} = ? WHERE user_id = ?', (response, ctx.author.id))
            conn.commit()
        except sqlite3.Error as e:
            await thread.send(f"An error occurred while updating the database: {e}")
        finally:
            conn.close()

        await thread.send(f"Your {step} has been set to {response}. You can proceed with the next step.")
        await asyncio.sleep(5)
        await thread.delete()

    @commands.command()
    async def profile_setup(self, ctx):
        profile = await self.check_and_create_profile(ctx)
        if profile:
            await ctx.send("Your profile already exists. Would you like to completely restart your profile? Type `yes` to confirm or `no` to cancel.\n**This will delete your current profile and all associated data!**")

            def check(message):
                return message.author == ctx.author and message.channel == ctx.channel

            try:
                confirmation = await self.bot.wait_for('message', check=check, timeout=30)
                if confirmation.content.lower() == 'yes':
                    conn = sqlite3.connect('discord.db')
                    try:
                        c = conn.cursor()
                        c.execute('DELETE FROM profiles WHERE user_id = ?', (ctx.author.id,))
                        c.execute('DELETE FROM stats WHERE user_id = ?', (ctx.author.id,))
                        c.execute('DELETE FROM equipped_items WHERE user_id = ?', (ctx.author.id,))
                        c.execute('DELETE FROM inventory WHERE user_id = ?', (ctx.author.id,))
                        conn.commit()
                        await ctx.send("Your profile has been reset. Starting the setup process...")
                    except sqlite3.Error as e:
                        await ctx.send(f"An error occurred while resetting your profile: {e}")
                        return
                    finally:
                        conn.close()
                else:
                    await ctx.send("Profile setup cancelled.")
                    return
            except asyncio.TimeoutError:
                await ctx.send("No response received. Profile setup cancelled.")
                return

        conn = sqlite3.connect('discord.db')
        try:
            c = conn.cursor()

            # Create a new profile entry
            c.execute('''
                INSERT INTO profiles (user_id, class, alignment, race, name, ability_scores)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (ctx.author.id, "", "", "", "", ""))

            # Initialize stats for the user
            c.execute('''
                INSERT INTO stats (user_id, health, health_max, health_boost, defense, defense_boost, attack, attack_boost, level, coins)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (ctx.author.id, 10, 10, 0, 2, 0, 2, 0, 1, 20))

            c.execute('''
                INSERT INTO equipped_items (user_id)
                VALUES (?)
            ''', (ctx.author.id,))

            c.execute('''
                INSERT INTO inventory (user_id)
                VALUES (?)
            ''', (ctx.author.id,))

            conn.commit()
        except sqlite3.Error as e:
            await ctx.send(f"An error occurred while initializing your profile: {e}")
        finally:
            conn.close()

        await ctx.send("Your profile has been initialized. Let's start the setup process. Please follow the instructions for each step.")

        # Automatically go through each setup step using buttons
        await self.profile_setup_step(
            ctx,
            "Class",
            "**Question 1:**\n*Classes* represent your character's role and abilities in the game. Each class has unique features, strengths, and weaknesses.\n\nHere are the available classes:\n- **Barbarian**: A fierce warrior of primal instincts.\n- **Bard**: A master of song, speech, and magic.\n- **Cleric**: A divine spellcaster who serves a deity.\n- **Druid**: A nature-based spellcaster with shapeshifting abilities.\n- **Fighter**: A versatile combat expert.\n- **Monk**: A martial artist who channels inner energy.\n- **Paladin**: A holy warrior bound by an oath.\n- **Ranger**: A skilled hunter and tracker.\n- **Rogue**: A stealthy and cunning adventurer.\n- **Sorcerer**: A spellcaster with innate magical power.\n- **Warlock**: A spellcaster who gains power through a pact.\n- **Wizard**: A scholarly spellcaster who studies magic.\n- **Artificer**: A magical inventor and craftsman.\n\nFor more details, visit: https://www.dndbeyond.com/classes",
            classes,
            'class'
        )
        await self.profile_setup_step(
            ctx,
            "Race",
            "**Question 2:**\n*Races* define your character's physical traits, culture, and abilities. Each race has unique characteristics and bonuses.\n\nHere are some examples:\n- **Dragonborn**: Proud dragon-like humanoids.\n- **Dwarf**: Hardy and resilient mountain dwellers.\n- **Elf**: Graceful and magical beings.\n- **Human**: Versatile and adaptable.\n- **Tiefling**: Descendants of fiendish heritage.\n- **Halfling**: Small and nimble adventurers.\n\nFor a full list of races and their descriptions, visit: https://www.dndbeyond.com/species",
            races,
            'race'
        )
        await self.profile_setup_step(
            ctx,
            "Name",
            "**Question 3:**\nWhat is your character's *name*? This is how your character will be identified in the game.",
            None,
            'name'
        )
        await self.profile_setup_step(
            ctx,
            "Gender",
            "**Question 4:**\nWhat is your character's *gender*? (M for Male, F for Female)",
            ["M", "F"],
            'gender'
        )
        await self.profile_setup_step(
            ctx,
            "Alignment",
            "**Question 5:**\n*Alignment* represents your character's moral and ethical perspective. It helps define how your character interacts with the world.\n\nHere are the alignments:\n- **Lawful Good**: Acts with compassion and follows the law.\n- **Neutral Good**: Does the best they can to help others.\n- **Chaotic Good**: Follows their heart but strives to do good.\n- **Lawful Neutral**: Follows the law above all else.\n- **True Neutral**: Maintains balance between good and evil, law and chaos.\n- **Chaotic Neutral**: Follows their own whims without regard for rules.\n- **Lawful Evil**: Uses the law to achieve selfish or malevolent goals.\n- **Neutral Evil**: Does whatever they can get away with.\n- **Chaotic Evil**: Acts with selfishness and destruction in mind.\n\nFor more details, visit: https://en.wikipedia.org/wiki/Alignment_(Dungeons_%26_Dragons)#Alignments",
            alignments,
            'alignment'
        )
        await self.profile_setup_ability_scores(ctx)
        await self.profile_setup_image(ctx)

        await ctx.send("Profile setup complete!")

    @commands.command()
    async def profile_setup_ability_scores(self, ctx):
        profile = await self.check_and_create_profile(ctx)
        if not profile:
            await ctx.send("Your profile is incomplete. Please start the full setup using `!profile_setup`.")
            return

        thread = await ctx.channel.create_thread(
            name="Ability Scores Setup",
            
        )
        await thread.add_user(ctx.author)
        await thread.send("**Question 6:**\nWould you like to roll for your ability scores or use the point buy system?\nType `roll` to roll 4d6 (dropping the lowest die) for each score, or type `point buy` to distribute 27 points among your six ability scores.")

        def check(message):
            return message.author == ctx.author and message.channel == thread

        response_method = await self.bot.wait_for('message', check=check)
        if response_method.content.lower() == 'exit':
            await thread.delete()
            await ctx.send("Setup was cancelled, and the thread has been deleted.")
            return

        ability_scores = {}

        if response_method.content.lower() == 'roll':
            def roll_ability_score():
                rolls = [random.randint(1, 6) for _ in range(4)]
                return sum(sorted(rolls)[1:])

            ability_scores = {
                "Strength": roll_ability_score(),
                "Dexterity": roll_ability_score(),
                "Constitution": roll_ability_score(),
                "Intelligence": roll_ability_score(),
                "Wisdom": roll_ability_score(),
                "Charisma": roll_ability_score()
            }

            scores_message = "\n".join(f"{stat}: {score}" for stat, score in ability_scores.items())
            await thread.send(f"Here are your ability scores:\n{scores_message}")

        elif response_method.content.lower() == 'point buy':
            await thread.send("You have 27 points to spend on your ability scores.\nEach score starts at 8...\n\nSubmit scores in the format: `Strength,Dexterity,Constitution,Intelligence,Wisdom,Charisma`. Total must add up to 27 points.")

            response = await self.bot.wait_for('message', check=check)
            if response.content.lower() == 'exit':
                await thread.delete()
                await ctx.send("Setup was cancelled, and the thread has been deleted.")
                return

            try:
                scores = list(map(int, response.content.split(',')))
                if len(scores) != 6 or sum(scores) - 48 != 27:
                    await thread.send("Invalid scores or total points not equal to 27. Please try again.")
                    return

                ability_scores = dict(zip(["Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Charisma"], scores))
            except ValueError:
                await thread.send("Invalid format. Please enter six numbers separated by commas.")
                return

        conn = sqlite3.connect('discord.db')
        try:
            c = conn.cursor()
            c.execute('UPDATE profiles SET ability_scores = ? WHERE user_id = ?', (str(ability_scores), ctx.author.id))
            conn.commit()
        except sqlite3.Error as e:
            await thread.send(f"An error occurred while updating the database: {e}")
        finally:
            conn.close()

        await thread.send(f"Your ability scores have been set. You can proceed to the next step.")
        await asyncio.sleep(10)  # Wait for 5 seconds before deleting the thread
        await thread.delete()

    @commands.command()
    async def profile_setup_image(self, ctx):
        profile = await self.check_and_create_profile(ctx)
        if not profile:
            await ctx.send("Your profile is incomplete. Please start the full setup using `!profile_setup`.")
            return

        thread = await ctx.channel.create_thread(
            name="Image Setup",
            
        )
        await thread.add_user(ctx.author)

        await thread.send("**Question 7:**\nPlease upload a profile image (this will be saved as your character's image).\nIf you'd like to skip, type `skip`.")
        
        def check_image(message):
            return message.author == ctx.author and message.channel == thread

        image_message = await self.bot.wait_for('message', check=check_image)
        if image_message.content.lower() == 'exit':
            await thread.delete()
            await ctx.send("Setup was cancelled, and the thread has been deleted.")
            return

        if image_message.content.lower() == 'skip':
            image_path = None  # No image selected, set to None
            await thread.send("You chose to skip the image upload.")
        else:
            # Save the image
            image_url = image_message.attachments[0].url
            image_response = requests.get(image_url)
            avatar_image = Image.open(BytesIO(image_response.content)).convert("RGB")
            
            # Scale the image to 512x512
            avatar_image = avatar_image.resize((512, 512), Image.Resampling.LANCZOS)

            image_path = os.path.join(self.image_dir, f"{ctx.author.id}.png")
            avatar_image.save(image_path)
            
        await thread.send("Your profile image has been uploaded. Setup is complete!")
        await asyncio.sleep(5)  # Wait for 5 seconds before deleting the thread
        await thread.delete()

    @commands.command()
    async def profile_setup_class(self, ctx):
        """Command to set up the class directly."""
        await self.profile_setup_step(ctx, "Class", "**Question 1:**\n*Classes* are typical with most roleplaying games, and especially D&D.\nMore information: https://www.dndbeyond.com/classes", classes, 'class')

    @commands.command()
    async def profile_setup_race(self, ctx):
        """Command to set up the race directly."""
        await self.profile_setup_step(ctx, "Race", "**Question 2:**\nYour character's *race* defines their physical appearance.\nReference: https://www.dndbeyond.com/species", races, 'race')

    @commands.command()
    async def profile_setup_name(self, ctx):
        """Command to set up the name directly."""
        await self.profile_setup_step(ctx, "Name", "**Question 3:**\nWhat is your character's *name?*", None, 'name')

    @commands.command()
    async def profile_setup_gender(self, ctx):
        """Command to set up the gender directly."""
        await self.profile_setup_step(ctx, "Gender", "**Question 4:**\nWhat is your character's *gender*? (M for Male, F for Female)", ["M", "F"], 'gender')

    @commands.command()
    async def profile_setup_alignment(self, ctx):
        """Command to set up the alignment directly."""
        await self.profile_setup_step(ctx, "Alignment", "**Question 5:**\nYour *alignment* is your character's moral calling.\nReference: https://en.wikipedia.org/wiki/Alignment_(Dungeons_%26_Dragons)#Alignments", alignments, 'alignment')

    @commands.command()
    async def profile_setup_ability_scores(self, ctx):
        """Command to set up ability scores directly."""
        profile = await self.check_and_create_profile(ctx)
        if not profile:
            await ctx.send("Your profile is incomplete. Please start the full setup using `!profile_setup`.")
            return

        thread = await ctx.channel.create_thread(
            name="Ability Scores Setup",
            
        )
        await thread.add_user(ctx.author)
        await thread.send("**Question 6:**\nWould you like to roll for your ability scores or use the point buy system?\nType `roll` to roll 4d6 (dropping the lowest die) for each score, or type `point buy` to distribute 27 points among your six ability scores.")

        def check(message):
            return message.author == ctx.author and message.channel == thread

        response_method = await self.bot.wait_for('message', check=check)
        if response_method.content.lower() == 'exit':
            await thread.delete()
            await ctx.send("Setup was cancelled, and the thread has been deleted.")
            return

        ability_scores = {}

        if response_method.content.lower() == 'roll':
            def roll_ability_score():
                rolls = [random.randint(1, 6) for _ in range(4)]
                return sum(sorted(rolls)[1:])

            ability_scores = {
                "Strength": roll_ability_score(),
                "Dexterity": roll_ability_score(),
                "Constitution": roll_ability_score(),
                "Intelligence": roll_ability_score(),
                "Wisdom": roll_ability_score(),
                "Charisma": roll_ability_score()
            }

            scores_message = "\n".join(f"{stat}: {score}" for stat, score in ability_scores.items())
            await thread.send(f"Here are your ability scores:\n{scores_message}")

        elif response_method.content.lower() == 'point buy':
            await thread.send("You have 27 points to spend on your ability scores.\nEach score starts at 8...\n\nSubmit scores in the format: `Strength,Dexterity,Constitution,Intelligence,Wisdom,Charisma`. Total must add up to 27 points.")

            response = await self.bot.wait_for('message', check=check)
            if response.content.lower() == 'exit':
                await thread.delete()
                await ctx.send("Setup was cancelled, and the thread has been deleted.")
                return

            try:
                scores = list(map(int, response.content.split(',')))
                if len(scores) != 6 or sum(scores) - 48 != 27:
                    await thread.send("Invalid scores or total points not equal to 27. Please try again.")
                    return

                ability_scores = dict(zip(["Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Charisma"], scores))
            except ValueError:
                await thread.send("Invalid format. Please enter six numbers separated by commas.")
                return

        conn = sqlite3.connect('discord.db')
        try:
            c = conn.cursor()
            c.execute('UPDATE profiles SET ability_scores = ? WHERE user_id = ?', (str(ability_scores), ctx.author.id))
            conn.commit()
        except sqlite3.Error as e:
            await thread.send(f"An error occurred while updating the database: {e}")
        finally:
            conn.close()

        await thread.send(f"Your ability scores have been set. You can proceed with the next steps using `!profile_setup_image`.")
        await asyncio.sleep(10)  # Wait for 5 seconds before deleting the thread
        await thread.delete()

    @commands.command()
    async def profile_setup_image(self, ctx):
        profile = await self.check_and_create_profile(ctx)
        if not profile:
            await ctx.send("Your profile is incomplete. Please start the full setup using `!profile_setup`.")
            return

        thread = await ctx.channel.create_thread(
            name="Image Setup",
            
        )
        await thread.add_user(ctx.author)

        await thread.send("**Question 7:**\nPlease upload a profile image (this will be saved as your character's image). If you'd like to skip, type 'skip'.")
        
        def check_image(message):
            return message.author == ctx.author and message.channel == thread

        image_message = await self.bot.wait_for('message', check=check_image)
        if image_message.content.lower() == 'exit':
            await thread.delete()
            await ctx.send("Setup was cancelled, and the thread has been deleted.")
            return

        if image_message.content.lower() == 'skip':
            image_path = None  # No image selected, set to None
            await thread.send("You chose to skip the image upload.")
        else:
            # Save the image
            image_url = image_message.attachments[0].url
            image_response = requests.get(image_url)
            avatar_image = Image.open(BytesIO(image_response.content)).convert("RGB")
            
            # Scale the image to 512x512
            avatar_image = avatar_image.resize((512, 512), Image.Resampling.LANCZOS)

            image_path = os.path.join(self.image_dir, f"{ctx.author.id}.png")
            avatar_image.save(image_path)
            
        await thread.send("Your profile image has been uploaded. Setup is complete!")
        await asyncio.sleep(5)  # Wait for 5 seconds before deleting the thread
        await thread.delete()

async def setup(bot):
    await bot.add_cog(Setup(bot))
