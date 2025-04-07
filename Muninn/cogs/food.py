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

def get_time(hour, minute=0):
    """Helper function to generate localized time."""
    now = datetime.now(pytz.timezone("US/Pacific"))
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0).timetz()

class FoodCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.target_channel_id = 1298762960184934432  # Replace with the target channel's ID
        self.food_emojis = [
            "🍓", "🍈", "🍉", "🍊", "🍋", "🍌", "🍍", "🥭", "🍎", "🍏", "🍐", "🍑", "🍒", "🍓", "🥝", 
            "🥥", "🥑", "🍆", "🥔", "🥕", "🌽", "🌶️", "🥒", "🥬", "🥦", "🧄", "🧅", "🍄", "🥜", "🌰",  
            "🍞", "🥐", "🥖", "🥨", "🥯", "🥞", "🧇", "🧀", "🍖", "🍗", "🥩", "🥓", "🍔", "🍟", "🍕",  
            "🌭", "🥪", "🌮", "🌯", "🥙", "🧆", "🥚", "🍳", "🥘", "🍲", "🥣", "🥗", "🍿", "🧈", "🧂",  
            "🥫", "🍱", "🍘", "🍙", "🍚", "🍛", "🍜", "🍝", "🍠", "🍢", "🍣", "🍤", "🍥", "🥮", "🍡",  
            "🥟", "🥠", "🥡", "🦪", "🍦", "🍧", "🍨", "🍩", "🍪", "🎂", "🍰", "🧁", "🥧", "🍫", "🍬",  
            "🍭", "🍮", "🍯", "🍼", "🥛", "☕", "🍵", "🍶", "🍾", "🍷", "🍸", "🍹", "🍺", "🍻", "🥂",  
            "🥃", "🥤", "🧃", "🧉", "🧊", "🍅"
        ]


        # Define scheduled times using the helper function
        self.scheduled_times = [
            get_time(8),  # 8:00 AM
            get_time(12),  # 12:00 PM
            get_time(19),  # 7:00 PM
        ]
        self.food_scheduler = tasks.loop(time=self.scheduled_times)(self.food_scheduler_task)
        self.food_scheduler.start()
        self.db_path = "discord.db"
        self.california_tz = pytz.timezone('US/Pacific')  # Add California timezone
        self._initialize_database()
        self.reaction_timeout = 1800  # Timeout for reactions in seconds

    def cog_unload(self):   
        self.food_scheduler.cancel()

    def _initialize_database(self):
        """Initialize the SQLite database and create the meals table if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS meals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    meal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    emoji TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    async def food_scheduler_task(self):
        """Task to send food messages at scheduled times."""
        now = datetime.now(self.california_tz)  # Use California timezone
        for meal, scheduled_time in zip(["breakfast", "lunch", "dinner"], self.scheduled_times):
            # Check if the current time matches the scheduled time (ignoring seconds and microseconds)
            if now.time().hour == scheduled_time.hour and now.time().minute == scheduled_time.minute:
                await self.send_food_message(meal)
                print(f"Sent {meal} message at {scheduled_time}.")
            else:
                print(f"Skipping {meal}. Current time: {now.time()}, Scheduled time: {scheduled_time}")

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

        reacted_users = set()  # Track users who have already reacted
        try:
            while True:
                reaction, user = await self.bot.wait_for(
                    "reaction_add",
                    timeout=self.reaction_timeout,
                    check=lambda r, u: r.message.id == message.id and str(r.emoji) in food_options and u.id not in reacted_users
                )
                if user.bot:
                    continue  # Ignore bot reactions

                chosen_food = str(reaction.emoji)
                reacted_users.add(user.id)  # Add user to the set of reacted users
                self._log_meal_status(meal, f"chosen", chosen_food, user.id)  # Log with user ID
                await channel.send(f"{user.mention} chose {chosen_food} for {meal}.")
                print(f"User {user} chose {chosen_food} for {meal}.")
        except asyncio.TimeoutError:
            await channel.send(f"Time's up! Thanks for participating in {meal}.")
            print(f"Reaction timeout reached for {meal}.")

    def _log_meal_status(self, meal, status, emoji=None, user_id=None):
        """Log the meal status (e.g., 'sent', 'chosen: 🍕', 'skipped') in the database."""
        user_id = user_id or 0  # Default to 0 if user_id is None
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO meals (user_id, meal, status, emoji, timestamp) VALUES (?, ?, ?, ?, ?)", 
                (user_id, meal, status, emoji, datetime.now(self.california_tz).strftime("%Y-%m-%d %H:%M:%S"))
            )
            conn.commit()
        print(f"Logged meal: {meal}, status: {status}, emoji: {emoji}, user_id: {user_id}.")

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

async def setup(bot):
    await bot.add_cog(FoodCog(bot))
