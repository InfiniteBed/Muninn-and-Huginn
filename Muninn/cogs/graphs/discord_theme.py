import matplotlib.pyplot as plt
from matplotlib import font_manager
from discord.ext import commands

class DiscordTheme(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def apply_discord_theme():
        """Apply a unified Discord-like theme to all graphs."""
        plt.style.use("dark_background")
        
        # Load the custom font
        prop = font_manager.FontProperties(fname="/usr/src/bot/fonts/Uni Sans Heavy.otf")

        font_path = '/usr/src/bot/fonts/Uni Sans Heavy.otf'
        font_name = font_manager.FontProperties(fname=font_path).get_name()
        plt.rcParams['font.family'] = [font_name]

        # Apply font properties to specific plot elements
        plt.rcParams["text.color"] = "#DCDDDE"  # Light gray text
        plt.rcParams["axes.facecolor"] = "#2C2F33"  # Dark mode background
        plt.rcParams["axes.edgecolor"] = "#99AAB5"  # Subtle borders
        plt.rcParams["axes.labelcolor"] = "#DCDDDE"
        plt.rcParams["xtick.color"] = "#DCDDDE"
        plt.rcParams["ytick.color"] = "#DCDDDE"
        plt.rcParams["grid.color"] = "#555555"  # Subtle grid lines
        plt.rcParams["figure.facecolor"] = "#5762E3"
        plt.rcParams["savefig.facecolor"] = "#2C2F33"

        # Ensure font is applied to axes and titles directly
        plt.rcParams["axes.titleweight"] = "bold"
        plt.rcParams["axes.titlesize"] = 14
        plt.rcParams["axes.labelsize"] = 12
        plt.rcParams["xtick.labelsize"] = 10
        plt.rcParams["ytick.labelsize"] = 10

        return prop  # Return the font property to be used later

# Setup function to add the cog to the bot
async def setup(bot):
    await bot.add_cog(DiscordTheme(bot))