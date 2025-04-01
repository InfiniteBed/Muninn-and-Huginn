import sqlite3
import discord
from discord.ext import commands
from discord.ui import View, Button

class HomeView(View):
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id

    @discord.ui.button(label="Rest", style=discord.ButtonStyle.green)
    async def rest_button(self, interaction: discord.Interaction, button: Button):
        conn = sqlite3.connect('discord.db')
        c = conn.cursor()

        # Check if the user has any ongoing activity
        c.execute('SELECT activity FROM stats WHERE user_id = ?', (self.user_id,))
        activity = c.fetchone()

        if activity and activity[0]:
            await interaction.response.send_message("You cannot rest while engaged in another activity.", ephemeral=True)
        else:
            # Update the activity to "long rest"
            c.execute('UPDATE stats SET activity = ? WHERE user_id = ?', ("long rest", self.user_id))
            conn.commit()
            await interaction.response.send_message("You are now taking a long rest.", ephemeral=True)

        conn.close()

class Home(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def home(self, ctx):
        """View your home and interact with it."""
        user = ctx.author

        embed = discord.Embed(
            title=f"{user.display_name}'s Home",
            description="Welcome to your home! You can rest here to recover.",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=user.avatar.url if user.avatar else None)

        view = HomeView(user.id)
        await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(Home(bot))
