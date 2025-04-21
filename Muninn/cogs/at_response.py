import random
import asyncio
import time
from discord.ext import commands

## Certified AI-free file

class AtResponse(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        responses = [
            "WHAT",
            "CAW",
            "Yummy yummy",
            "huh?",
            "¿qué?",
            "what do u want?",
            "no",
            "yes, darling?",
            "no, let me sleep",
            "I'm busy, shhhh",
            "I'm making my nest bro, leave me",
            "SHHH",
            "Yes, pookie?",
            "oi",
            "yes plEEEASE",
            "oo lala",
            "Hey, so, I didn't like that-",
            "No comment",
            "i like my milk warm",
            "That's...confident",
            "thats very nice, {user}",
            "Could you not?"
        ]
        
        print(message.content)
        
        if message.author.bot:
            return

        if self.bot.user.mentioned_in(message):
            await message.channel.send(str.format(random.choice(responses), user=message.author.display_name))

async def setup(bot):
    await bot.add_cog(AtResponse(bot))
