import random
import asyncio
import time
import json
import os
import yaml
from discord.ext import commands

class AtResponse(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        with open(os.path.join(os.path.dirname(__file__), '../data/at_responses.yaml'), 'r', encoding='utf-8') as f:
            responses = yaml.safe_load(f)["responses"]
        
        print(message.content)

        if self.bot.user.mentioned_in(message):
            await message.channel.send(str.format(random.choice(responses), user=message.author.display_name))

async def setup(bot):
    await bot.add_cog(AtResponse(bot))
