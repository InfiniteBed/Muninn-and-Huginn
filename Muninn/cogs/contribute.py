import discord
from discord.ext import commands
import json

class Contribution(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.file_path = "contributions.json"
        self.load_data()

    def load_data(self):
        try:
            with open(self.file_path, "r") as f:
                self.data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.data = {}

    def save_data(self):
        with open(self.file_path, "w") as f:
            json.dump(self.data, f, indent=4)

    @commands.command()
    async def contribute(self, ctx, *, content: str = None):
        if not content:
            embed = discord.Embed(
                title="Contribute Data",
                description=(
                    "Contributions will earn you ⭐️ stars! Here’s what you can help with:\n"
                    "- Randomized Insults\n"
                    "- Prompts, theological discussions, or brain teasers\n"
                    "- Message rewards for every 100, 200 messages sent\n"
                    "- Custom graphs for `!graphs`\n"
                    "- Items, weapons, and armor\n"
                    "- Expeditions\n"
                    "- Suggest improvements or new commands\n\n"
                    "Simply type your contribution after the command!\n"
						"`!contribute Is time relative?`"
                ),
                color=discord.Color.purple()
            )
            await ctx.send(embed=embed)
            return
        
        self.data.setdefault("submissions", []).append({
            "user": ctx.author.name,
            "guild": ctx.guild.name if ctx.guild else "DMs",
            "channel": ctx.channel.name if ctx.guild else "Private Message",
            "content": content
        })
        self.save_data()
        
        embed = discord.Embed(
            title=content, 
            color=discord.Color.green(),
            description="Thank you for your response! It's been sent straight to the bot owner!"
        )
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)

        await ctx.author.send(embed=embed)

        # Send the embed to the bot owner
        bot_owner = self.bot.get_user(self.bot.owner_id)
        embed_to_author = discord.Embed(
            title=content, 
            color=discord.Color.green(),
            description=ctx.channel.mention if ctx.guild else "Private Message"
        )
        embed_to_author.set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
        await bot_owner.send(embed=embed_to_author)

        await ctx.send("Contribution recorded and sent to the bot owner's DMs!")

async def setup(bot):
    await bot.add_cog(Contribution(bot))