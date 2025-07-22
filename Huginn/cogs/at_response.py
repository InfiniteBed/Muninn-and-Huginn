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
        
        # Check if bot is mentioned but ignore @everyone mentions
        is_mentioned = (self.bot.user.mentioned_in(message) and not message.mention_everyone) or "<@&1301425229213470762>" in message.content
        if is_mentioned:
            await message.channel.send(str.format(random.choice(responses), user=message.author.display_name))

async def setup(bot):
    await bot.add_cog(AtResponse(bot))
