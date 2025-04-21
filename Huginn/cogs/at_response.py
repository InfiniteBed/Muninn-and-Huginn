import random
import asyncio
import time
import json
import os
from discord.ext import commands

class AtResponse(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        with open(os.path.join(os.path.dirname(__file__), '../data/at_responses.json'), 'r', encoding='utf-8') as f:
            responses = json.load(f)["responses"]
        
        print(message.content)
        
        if message.author.bot:
            return

        if self.bot.user.mentioned_in(message):
            await message.channel.send(str.format(random.choice(responses), user=message.author.display_name))

async def setup(bot):
    await bot.add_cog(AtResponse(bot))
