import random
import asyncio
import time
from discord.ext import commands
INSULT_FEATURE_ENABLED = False

class InsultCog(commands.Cog):
    def __init__(self, bot, db_cursor):
        self.bot = bot
        self.c = db_cursor
        self.c.execute("SELECT user_id FROM opt_in_users")
        self.opted_in_users = {row[0] for row in self.c.fetchall()}

    @commands.Cog.listener()
    async def on_message(self, message):
        if not INSULT_FEATURE_ENABLED:
            return
        chance_to_respond = .01
        
        print(random.random(), message.author.id, self.opted_in_users)
        
        if message.author.id in self.opted_in_users and random.random() < chance_to_respond:
            print('yes')
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
            
            async with message.channel.typing():
                for _ in range(10):  # Simulate 10 seconds of typing
                    await asyncio.sleep(1)
                    async for interrupt_message in message.channel.history(limit=5):  # Check recent messages
                        if interrupt_message.content.lower() in ["shut", "quiet"]:
                            await interrupt_message.add_reaction("😢")  # React with a sad face
                            return

            await message.channel.send(response)

async def setup(bot):
    from sqlite3 import connect
    conn = connect("huginn.db")
    c = conn.cursor()
    await bot.add_cog(InsultCog(bot, c))
