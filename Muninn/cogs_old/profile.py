import discord
from discord.ext import commands
import logging

logger = logging.getLogger(__name__)

class Profile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.search = bot.get_cog('Search')
        self.utils = bot.get_cog('Utils')  # Reference the Utils cog
        self.stats_manager = self.bot.get_cog("StatsManager")

    @commands.command(name='profile') 
    async def profile(self, ctx, user: str = None):
        if user is None:
            user = ctx.author
        else:
            user = await self.search.find_user(user, ctx.guild)
            if not user:
                await ctx.send("No profile found.")
                return

        user_stats = await self.stats_manager.fetch_user_stats(user)
        if not user_stats:
            error_embed = discord.Embed(
                title="Error",
                description="The specified user does not exist or has no profile. Please create a profile with !profile_setup.",
                color=discord.Color.red()
            )
            await ctx.send(embed=error_embed)
            return
        
        embed = discord.Embed()

        # Use the utility function to fetch the avatar color and image
        embed_color, avatar_image, has_custom_image = await self.utils.get_avatar_color_and_image(user)

        embed = discord.Embed(title=user_stats['profile_name'], color=embed_color)
        
        if has_custom_image:
            file = discord.File(f"/usr/src/bot/profile_images/{user.id}.png", filename="image.png")
            embed.set_thumbnail(url="attachment://image.png")
        else:
            file = None
            embed.set_thumbnail(url=user.avatar.url)

        # Create the embed with the correct color
        embed.set_author(name=user.display_name)
        embed.set_footer(text="Custom Profile")
        embed.add_field(name="Class", value=user_stats['class'], inline=True)
        embed.add_field(name="Race", value=user_stats['race'], inline=True)
        embed.add_field(name="Alignment", value=user_stats['alignment'], inline=True)
        embed.add_field(name="Ability Scores", value=user_stats['scores_display'], inline=True)
        embed.add_field(name="Bio", value=user_stats['bio'], inline=True)

        await ctx.send(file=file, embed=embed)

async def setup(bot):
    await bot.add_cog(Profile(bot))
