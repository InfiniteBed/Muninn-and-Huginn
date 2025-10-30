import asyncio
import discord  # type:ignore
from discord import app_commands # type:ignore
import discord.ext.commands as commands  # type:ignore

class UserInput(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._prompt_tasks: set[asyncio.Task] = set()

    def cog_unload(self):
        # Cancel any active prompts when the cog is unloaded (e.g., on reload)
        for t in list(self._prompt_tasks):
            t.cancel()

    async def confirmation_check(self, ctx, submission_content):
        embed = discord.Embed(title="Please confirm your input", description=f"You entered: {submission_content}\nReact with ✅ to confirm or ❌ to cancel.", color=discord.Color.blue())
        embed_timeout = discord.Embed(title="Confirmation timed out", description="You did not respond in time.", color=discord.Color.red())
        message = await ctx.send(embed=embed)

        await message.add_reaction("✅")
        await message.add_reaction("❌")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.channel == ctx.channel

        try:
            reaction, user = await self.bot.wait_for("reaction_add", check=check)
        except asyncio.TimeoutError:
            await ctx.send(embed=embed_timeout)
            return False

        if str(reaction.emoji) == "✅":
            return True
        else:
            return False

    async def prompt(
        self, 
        ctx, 
        question: str = "", 
        body: str = "",
        type: type = str, 
        acceptable_values: list = [], 
        embed_color: discord.Color = discord.Color.blue(),
        require_confirmation: bool = False
    ):
        # Register this coroutine so it gets cancelled on reload
        current_task = asyncio.current_task()
        if current_task:
            self._prompt_tasks.add(current_task)

        try:
            embed = discord.Embed(title=question, color=embed_color, description=body if body else None)
            await ctx.send(embed=embed)

            while True:
                try:
                    message = await self.bot.wait_for(
                        "message",
                        check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
                    )
                except asyncio.CancelledError:
                    # Bot/cog is being reloaded; stop waiting
                    return None

                if acceptable_values and message.content.lower() not in [str(v).lower() for v in acceptable_values]:
                    await ctx.send(f"Please enter a valid {type.__name__}.")
                    continue

                if type == str:
                    if require_confirmation:
                        confirmed = await self.confirmation_check(ctx, message.content)
                        if not confirmed:
                            self.prompt(ctx, question, body, type, acceptable_values, embed_color, require_confirmation)
                            continue
                    
                    return message.content

                if type == int:
                    try:
                        if require_confirmation:
                            confirmed = await self.confirmation_check(ctx, message.content)
                            if not confirmed:
                                self.prompt(ctx, question, body, type, acceptable_values, embed_color, require_confirmation)
                                continue
                        return int(message.content)
                    except ValueError:
                        await ctx.send(f"Please enter a valid {type.__name__}.")
                        continue

                if type == float:
                    try:
                        if require_confirmation:
                            confirmed = await self.confirmation_check(ctx, message.content)
                            if not confirmed:
                                self.prompt(ctx, question, body, type, acceptable_values, embed_color, require_confirmation)
                                continue
                        return float(message.content)
                    except ValueError:
                        await ctx.send(f"Please enter a valid {type.__name__}.")
                        continue

        finally:
            if current_task:
                self._prompt_tasks.discard(current_task)
    
async def setup(bot):
    user_input = UserInput(bot)
    await bot.add_cog(user_input)