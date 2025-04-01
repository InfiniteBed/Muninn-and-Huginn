import discord
from discord.ext import commands

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def helpme(self, ctx, command=None):
        if command:
            command_details = {
                "rankings": "`!rankings` - Show the rankings of users based on message count.",
                "statistics": "`!statistics` - Show a user's message statistics.",
                "graphs": "`!graphs` - Show statistics graphs that can be displayed.",
                "submit": "`!submit` - Submit emojis to be voted on.",
                "profile_setup": (
                    "`!profile_setup` - Start the full profile setup process.\n"
                    "`!profile_setup_class` - Choose your character's class.\n"
                    "`!profile_setup_race` - Choose your character's race.\n"
                    "`!profile_setup_name` - Choose your character's name.\n"
                    "`!profile_setup_alignment` - Choose your character's alignment.\n"
                    "`!profile_setup_abilities` - Choose whether to roll or use point-buy for ability scores.\n"
                    "`!profile_setup_image` - Upload your character's profile image.\n"
                    "`!profile_setup_gender` - Change your character's gender."
                ),
                "status": "`!status` - Show the status of your character.",
                "shop": "`!shop` - Visit the shop.",
                "board": "`!board` - Visit the expedition board, where you can take on expeditions for money.",
                "battle": "`!battle (Player)` - Battle another player for cash."
            }
            description = command_details.get(command.lower(), "Command not found.")
            embed = discord.Embed(
                title=f"Help for `{command}`",
                description=description,
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            return

        embed = discord.Embed(
            title="Help Command",
            description="Here are all the available commands.",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="General Commands",
            value=(
                "`!rankings` - Show the rankings of users based on message count.\n"
                "`!statistics` - Show a user's message statistics.\n"
                "`!graphs` - Show statistics graphs that can be displayed.\n"
                "`!contribute` - Contribute ideas for the bot owner to implement into Huginn and Muninn.\n"
                "`!submit` - Submit emojis to be voted on."
            ),
            inline=False
        )
        embed.add_field(
            name="RPG Commands",
            value=(
                "`!profile_setup` - Start the full profile setup process.\n"
                "`!me` - Show the status of your character.\n"
                "`!shop` - Visit the shop.\n"
                "`!board` - Visit the expedition board, where you can take on expeditions for money.\n"
                "`!battle (Player)` - Battle another player for cash.\n"
            ),
            inline=False
        )

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Help(bot))
