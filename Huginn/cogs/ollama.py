import discord
from discord.ext import commands
import aiohttp
from collections import defaultdict
from typing import List

class OllamaResponder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ollama_url = "http://100.84.237.81:11434/api/generate"  # Change to your Ollama server URL
        self.monitored_guild_id = 1298762959614640148  # Replace with your server ID
        self.monitored_channel_id = 1298762960184934432  # Replace with the channel ID
        self.message_history = defaultdict(list)  # Stores history per user
        self.history_limit = 5  # Adjust the number of messages to remember

    async def fetch_ollama_response(self, history: List[str]):
        """Sends a conversation history to the Ollama server and fetches a response."""
        prompt = "\n".join(history)  # Join message history into one prompt
        payload = {"model": "mistral", "prompt": prompt, "stream": False}

        async with aiohttp.ClientSession() as session:
            async with session.post(self.ollama_url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("response", "No response received.")
                else:
                    return f"Error: {response.status}"

    @commands.Cog.listener()
    async def on_message(self, message):
        """Listens for messages in the specified channel and suggests a response to the bot owner."""
        if message.author.bot:
            return  # Ignore bot messages
        if message.guild and message.guild.id == self.monitored_guild_id and message.channel.id == self.monitored_channel_id:
            # Maintain a rolling history for each user
            self.message_history[message.author.id].append(message.content)
            if len(self.message_history[message.author.id]) > self.history_limit:
                self.message_history[message.author.id].pop(0)  # Remove oldest message if over limit

            # Get a response based on history
            suggested_response = await self.fetch_ollama_response(self.message_history[message.author.id])

            # Send the response to the bot owner
            owner = await self.bot.application_info()
            if owner and owner.owner:
                try:
                    await owner.owner.send(f"Suggested response for {message.author}:\n{suggested_response}")
                except discord.Forbidden:
                    print("Could not DM the bot owner.")
            else:
                print("Bot owner not found.")

async def setup(bot):
    await bot.add_cog(OllamaResponder(bot))