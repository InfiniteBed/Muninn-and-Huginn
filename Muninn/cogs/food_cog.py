import discord
from discord.ext import commands, tasks
import random
from datetime import datetime, time
from .tz import TimezoneConverter  # Import the TimezoneConverter cog
import pytz  # Import pytz for timezone handling

class FoodCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.target_user_id = None  # Replace with the target user's Discord ID
        self.food_emojis = ["🍕", "🍔", "🍣", "🍎", "🍇", "🥗", "🍩", "🍪"]
        self.breakfast_time = time(8, 0)  # 8:00 AM
        self.lunch_time = time(12, 45)    # 12:30 PM
        self.dinner_time = time(18, 0)   # 6:00 PM
        self.food_scheduler.start()

    def cog_unload(self):
        self.food_scheduler.cancel()

    @tasks.loop(minutes=1)
    async def food_scheduler(self):
        now_utc = datetime.now(pytz.utc)  # Get the current UTC time
        california_tz = pytz.timezone('US/Pacific')  # Define California timezone
        now = now_utc.astimezone(california_tz).time()  # Convert to California time

        if now.hour == self.breakfast_time.hour and now.minute == self.breakfast_time.minute:
            await self.send_food_message("breakfast")
        elif now.hour == self.lunch_time.hour and now.minute == self.lunch_time.minute:
            await self.send_food_message("lunch")
        elif now.hour == self.dinner_time.hour and now.minute == self.dinner_time.minute:
            await self.send_food_message("dinner")

    async def send_food_message(self, meal):
        if self.target_user_id is None:
            return  # No target user set
        user = self.bot.get_user(self.target_user_id)
        if user is None:
            return  # User not found
        food_options = random.sample(self.food_emojis, 3)
        food_message = f"Time for {meal}! Choose your food: {' '.join(food_options)}"
        await user.send(food_message)

    @commands.command(name="setuser")
    async def set_user(self, ctx, user: discord.User):
        """Set the target user to receive food messages."""
        self.target_user_id = user.id
        await ctx.send(f"Target user set to {user.name}.")

    @commands.command(name="settimes")
    async def set_times(self, ctx, breakfast: str, lunch: str, dinner: str):
        """Set custom times for breakfast, lunch, and dinner (HH:MM format)."""
        try:
            self.breakfast_time = datetime.strptime(breakfast, "%H:%M").time()
            self.lunch_time = datetime.strptime(lunch, "%H:%M").time()
            self.dinner_time = datetime.strptime(dinner, "%H:%M").time()
            await ctx.send("Meal times updated successfully.")
        except ValueError:
            await ctx.send("Invalid time format. Use HH:MM.")

async def setup(bot):
    await bot.add_cog(FoodCog(bot))
