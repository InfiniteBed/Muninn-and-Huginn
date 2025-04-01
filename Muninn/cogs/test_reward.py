import discord
from discord.ext import commands
import json

class TestReward(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.message_rewards, self.thank_you_data = self.load_json()

    def load_json(self):
        with open("responses.json", "r") as file:
            data = json.load(file)
        return data["message_rewards"], data["thank_you_responses"]

    @commands.command()
    @commands.is_owner()
    async def test_reward(self, ctx, reward_count: int):
        try:
            if str(reward_count) in self.message_rewards:
                reward = self.message_rewards[str(reward_count)].format(nick=ctx.author.display_name, message="Test message")
                await ctx.send(reward)
            else:
                await ctx.send(f"No reward message found for {reward_count} messages.")
        except Exception as e:
            await ctx.send(f"Error testing reward: {e}")

async def setup(bot):
    await bot.add_cog(TestReward(bot))
