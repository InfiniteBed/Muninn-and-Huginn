import random
import asyncio
import time
from discord.ext import commands

class InsultCog(commands.Cog):
    def __init__(self, bot, db_cursor, chance_to_respond):
        self.bot = bot
        self.c = db_cursor
        self.chance_to_respond = chance_to_respond

    @commands.Cog.listener()
    async def on_message(self, message):
        self.c.execute("SELECT user_id FROM opt_in_users WHERE user_id = ?", (message.author.id,))
        if self.c.fetchone() and random.random() < self.chance_to_respond:
            # Calculate the chance for a unique insult
            total_parts = len(self.bot.data["unique"]) + len(self.bot.data["intro"]) + len(self.bot.data["command"]) + len(self.bot.data["comparison"]) + len(self.bot.data["target"])
            unique_chance = len(self.bot.data["unique"]) / total_parts

            if random.random() < unique_chance:  # Generate a unique insult
                unique_part = random.choice(self.bot.data["unique"])
                response = f"{message.author.mention} {unique_part}"
            else:  # Generate a regular insult
                intro = random.choice(self.bot.data["intro"])
                command = random.choice(self.bot.data["command"])
                comparison = random.choice(self.bot.data["comparison"])
                target = random.choice(self.bot.data["target"])
                response = f"{message.author.mention} {intro} {command}, {comparison} {target}"
            
            typing_task = asyncio.create_task(message.channel.typing())
            try:
                for _ in range(10):  # Simulate 10 seconds of typing
                    await asyncio.sleep(1)
                    async for interrupt_message in message.channel.history(limit=5):  # Check recent messages
                        if interrupt_message.content.lower() in ["shut", "quiet"]:
                            await typing_task.cancel()
                            await interrupt_message.add_reaction("😢")  # React with a sad face
                            return
            except asyncio.CancelledError:
                return
            
            await typing_task
            await message.channel.send(response)

async def setup(bot):
    from sqlite3 import connect
    conn = connect("huginn.db")
    c = conn.cursor()
    bot.add_cog(InsultCog(bot, c, 0.01))  # Pass CHANCE_TO_RESPOND here
