import discord
from discord.ext import commands, tasks
import random
from datetime import datetime, time
from .tz import TimezoneConverter  # Import the TimezoneConverter cog
import pytz  # Import pytz for timezone handling
import asyncio  # Import asyncio for async tasks
import sqlite3  # Import sqlite3 for database handling
import matplotlib.pyplot as plt  # Import matplotlib for graph generation
import os  # Import os for file handling

class FoodCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.target_user_id = 738065718909862049  # Replace with the target user's Discord ID
        self.target_channel_id = 1337136026895782049  # Replace with the target channel's ID
        self.food_emojis = [
                "🍏", "🍎", "🍐", "🍊", "🍋", "🍌", "🍉", "🍇", "🍓", "🫐", "🍈", "🍒", "🍑", "🥭",
                "🥩", "🥓", "🍔", "🍟", "🍕", "🌭", "🥪", "🌮", "🌯", "🫔", "🥙", "🧆", "🥚", "🍳",
                "🥘", "🍲", "🫕", "🥣", "🥗", "🍿", "🧈", "🫘", "🍚", "🍘", "🍙", "🍛", "🍜", "🍝",
                "🍠", "🥠", "🍢", "🍡", "🥮", "🍧", "🍨", "🍦", "🥧", "🍰", "🎂", "🧁", "🍮", "🍭",
                "🍬", "🍫", "🍩", "🍪", "🍼", "🥛", "☕", "🫖", "🍵", "🍶", "🍾", "🍷", "🍸", "🍹",
                "🍺", "🍻", "🥂", "🥃"
            ]

        self.scheduled_times = [
            time(8, 0),  # 8:00 AM
            time(12, 45),  # 12:45 PM
            time(18, 0),  # 6:00 PM
        ]
        self.food_scheduler = tasks.loop(time=self.scheduled_times)(self.food_scheduler_task)
        self.food_scheduler.start()
        self.db_path = "discord.db"
        self._initialize_database()
        self.reaction_timeout = 300  # Timeout for reactions in seconds
        print("FoodCog initialized with scheduled meal times and reaction detection.")

    def cog_unload(self):
        self.food_scheduler.cancel()
        print("FoodCog unloaded and scheduler stopped.")

    def _initialize_database(self):
        """Initialize the SQLite database and create the meals table if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS meals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    meal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    emoji TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
        print("Database initialized and meals table ensured.")

    async def food_scheduler_task(self):
        """Task to send food messages at scheduled times."""
        now = datetime.now(pytz.utc)
        print(f"Scheduler triggered at {now}.")
        for meal, scheduled_time in zip(["breakfast", "lunch", "dinner"], self.scheduled_times):
            if now.time() >= scheduled_time:
                await self.send_food_message(meal)
                print(f"Sent {meal} message.")

    async def send_food_message(self, meal):
        if self.target_channel_id is None:
            return  # No target channel set
        channel = self.bot.get_channel(self.target_channel_id)
        if channel is None:
            return  # Channel not found
        food_options = random.sample(self.food_emojis, 3)
        food_message = f"Time for {meal}! React with your choice: {' '.join(food_options)}"
        message = await channel.send(food_message)
        print(f"Sending {meal} message to channel {self.target_channel_id}.")
        self._log_meal_status(meal, "sent")

        # Add reactions to the message
        for emoji in food_options:
            await message.add_reaction(emoji)

        # Wait for a reaction
        try:
            while True:
                reaction, user = await self.bot.wait_for(
                    "reaction_add",
                    timeout=self.reaction_timeout,
                    check=lambda r, u: r.message.id == message.id and str(r.emoji) in food_options
                )
                if user.bot:
                    continue  # Ignore bot reactions
                if user.id != self.target_user_id:
                    await message.remove_reaction(reaction.emoji, user)
                    await channel.send(f"Hey {user.mention}, this isn't your meal! Let the right person choose.")
                    print(f"Removed reaction from {user} for {meal}.")
                else:
                    chosen_food = str(reaction.emoji)
                    self._log_meal_status(meal, f"chosen", chosen_food)  # Log the chosen emoji
                    print(f"User {user} chose {chosen_food} for {meal}.")
                    break

        except asyncio.TimeoutError:
            self._log_meal_status(meal, "skipped")
            funny_responses = [
                f"No response for {meal}? The guards took your tray away.",
                f"{meal.capitalize()} skipped! Hope you enjoy the stale bread and water instead. 🥖💧",
                f"Looks like you missed {meal}.",
                f"Skipping {meal}? The warden won't be happy about this.",
            ]
            await channel.send(random.choice(funny_responses))
            print(f"No reaction received for {meal} within the timeout period.")

    def _log_meal_status(self, meal, status, emoji=None):
        """Log the meal status (e.g., 'sent', 'chosen: 🍕', 'skipped') in the database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO meals (meal, status, emoji) VALUES (?, ?, ?)", 
                (meal, status, emoji)
            )
            conn.commit()
        print(f"Logged meal: {meal}, status: {status}, emoji: {emoji}.")

    @commands.command(name="setuser")
    async def set_user(self, ctx, user: discord.User):
        """Set the target user to receive food messages."""
        self.target_user_id = user.id
        await ctx.send(f"Target user set to {user.name}.")
        print(f"Target user set to {user.id} ({user.name}).")

    @commands.command(name="setchannel")
    async def set_channel(self, ctx, channel: discord.TextChannel):
        """Set the target channel to receive food messages."""
        self.target_channel_id = channel.id
        await ctx.send(f"Target channel set to {channel.name}.")
        print(f"Target channel set to {channel.id} ({channel.name}).")

    @commands.command(name="settimes")
    async def set_times(self, ctx, breakfast: str, lunch: str, dinner: str):
        """Set custom times for breakfast, lunch, and dinner (HH:MM format)."""
        try:
            self.scheduled_times = [
                datetime.strptime(breakfast, "%H:%M").time(),
                datetime.strptime(lunch, "%H:%M").time(),
                datetime.strptime(dinner, "%H:%M").time(),
            ]
            self.food_scheduler.cancel()  # Stop the current loop
            self.food_scheduler = tasks.loop(time=self.scheduled_times)(self.food_scheduler_task)
            self.food_scheduler.start()  # Restart the loop with updated times
            await ctx.send("Meal times updated successfully.")
            print(f"Meal times updated: Breakfast at {breakfast}, Lunch at {lunch}, Dinner at {dinner}.")
        except ValueError:
            await ctx.send("Invalid time format. Use HH:MM.")

    @commands.command(name="sendfood")
    async def send_food(self, ctx, meal: str):
        """Manually send a food message for a specific meal."""
        if meal.lower() not in ["breakfast", "lunch", "dinner"]:
            await ctx.send("Invalid meal. Choose from 'breakfast', 'lunch', or 'dinner'.")
            print(f"Invalid meal input: {meal}")
            return
        await self.send_food_message(meal.lower())
        await ctx.send(f"Food message for {meal} sent to channel.")
        self._log_meal_status(meal.lower(), "manual")
        print(f"Manual food message for {meal} logged as 'manual'.")

    @commands.command(name="mealstats")
    async def meal_stats(self, ctx):
        """Retrieve and display meal statistics."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT meal, status, COUNT(*) as count
                FROM meals
                GROUP BY meal, status
            """)
            stats = cursor.fetchall()

        if not stats:
            await ctx.send("No meal data available.")
            print("No meal data to display.")
            return

        stats_message = "Meal Statistics:\n"
        for meal, status, count in stats:
            stats_message += f"{meal.capitalize()} ({status}): {count}\n"

        await ctx.send(stats_message)
        print("Displayed meal statistics.")

async def setup(bot):
    await bot.add_cog(FoodCog(bot))
