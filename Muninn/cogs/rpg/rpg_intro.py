import discord
from discord.ext import commands
from discord import app_commands

class RPGIntro(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="rpg_intro", description="Learn about the RPG system and how to get started!")
    async def rpg_intro(self, ctx):
        """
        Introduces new players to the RPG system with a comprehensive overview.
        """
        
        # Create a beautiful intro embed
        embed = discord.Embed(
            title="🎲 Welcome to the RPG Adventure! 🏰",
            description="Ready to embark on an epic journey? This RPG system lets you create a character, explore, battle, craft, and so much more!",
            color=0x7B12B4  # Purple color to match the RPG theme
        )
        
        # Add a thumbnail - using a more accessible RPG dice image
        # embed.set_thumbnail(url="https://i.imgur.com/FDcI6JZ.png")  # Generic RPG dice image
        
        # What is the RPG section
        embed.add_field(
            name="🎭 What is this RPG?",
            value=(
                "This is a comprehensive text-based RPG system inspired by Dungeons & Dragons! "
                "Create your own unique character with a class, race, abilities, and backstory. "
                "Then explore the world, complete jobs, craft items, battle other players, "
                "and build your character's legend one adventure at a time!"
            ),
            inline=False
        )
        
        # Getting Started section
        embed.add_field(
            name="🚀 Getting Started",
            value=(
                "**Step 1:** Use `!profile_setup` to create your character\n"
                "**Step 2:** Choose your class, race, name, and more!\n"
                "**Step 3:** Set your ability scores and upload a character image\n"
                "**Step 4:** Use `!me` to view your character sheet\n"
                "**Step 5:** Start your adventure with `!go` or `!home`!"
            ),
            inline=False
        )
        
        # Core Features section
        embed.add_field(
            name="⚔️ Core Features",
            value=(
                "🏠 **Home** - Rest, craft items, and manage your inventory\n"
                "🌍 **Go** - Explore, work jobs, shop, and gather resources\n"
                "⚔️ **Battle** - Challenge other players to combat\n"
                "🛡️ **Equipment** - Equip weapons and armor to boost your stats\n"
                "📈 **Professions** - Level up skills like blacksmithing and alchemy\n"
                "💰 **Economy** - Earn coins and trade with others"
            ),
            inline=False
        )
        
        # Tips for Fun section
        embed.add_field(
            name="🎉 Tips for Maximum Fun",
            value=(
                "• **Create a backstory** - Use `!setbio` to give your character personality!\n"
                "• **Interact with others** - The RPG is more fun with friends\n"
                "• **Experiment with crafting** - Create powerful custom equipment\n"
                "• **Join expeditions** - Group up for challenging adventures\n"
                "• **Set goals** - Work towards specific levels or rare items"
            ),
            inline=False
        )
        
        # Contributing to the Project section
        embed.add_field(
            name="🌟 Help Shape the RPG!",
            value=(
                "**Contribute to the bot's development!** Your ideas help make the RPG better for everyone!\n\n"
                "• **`!contribute <your idea>`** - Suggest new items, weapons, armor, jobs, or commands\n"
                "• **`!submit <emoji>`** - Submit emojis for the server emoji contest\n"
                "• **Share feedback** - Tell us what you love and what could be improved\n"
                "• **Get rewarded** - Approved contributions earn you ⭐ stars!\n\n"
                "*You can contribute: RPG items, weapons, armor, jobs, @ responses, random prompts, and more!*"
            ),
            inline=False
        )
        
        # Quick Commands section
        embed.add_field(
            name="📋 Essential Commands",
            value=(
                "`!profile_setup` - Create your character\n"
                "`!me` - View your character sheet\n"
                "`!go` - Start exploring and working\n"
                "`!home` - Rest and craft items\n"
                "`!helpme rpg` - See all RPG commands\n"
                "`!battle @user` - Challenge someone to combat\n"
                "`!contribute <idea>` - Suggest improvements to the RPG"
            ),
            inline=False
        )
        
        # Footer with encouragement
        embed.set_footer(
            text="🌟 Your adventure awaits! Start with !profile_setup, and help us improve with !contribute! 🌟",
            icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
        )
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(RPGIntro(bot))
