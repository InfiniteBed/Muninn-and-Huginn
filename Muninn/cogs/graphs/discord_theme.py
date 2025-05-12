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
        
        # Load the fonts
        uni_sans_path = '/usr/src/bot/fonts/Uni Sans Heavy.otf'
        emoji_font_path = '/usr/src/bot/fonts/NotoColorEmoji-Regular.ttf'
        
        # Register the fonts with matplotlib
        font_manager.fontManager.addfont(uni_sans_path)
        font_manager.fontManager.addfont(emoji_font_path)
        
        # Create font properties
        prop = font_manager.FontProperties(fname=uni_sans_path)
        
        # Set up font families with fallback
        plt.rcParams['font.family'] = ['Uni Sans Heavy', 'Noto Color Emoji']
        
        # Theme colors and styles
        plt.rcParams["text.color"] = "#DCDDDE"  # Light gray text
        plt.rcParams["axes.facecolor"] = "#2C2F33"  # Dark mode background
        plt.rcParams["axes.edgecolor"] = "#99AAB5"  # Subtle borders
        plt.rcParams["axes.labelcolor"] = "#DCDDDE"
        plt.rcParams["xtick.color"] = "#DCDDDE"
        plt.rcParams["ytick.color"] = "#DCDDDE"
        plt.rcParams["grid.color"] = "#555555"  # Subtle grid lines
        plt.rcParams["figure.facecolor"] = "#2C2F33"
        plt.rcParams["savefig.facecolor"] = "#2C2F33"

        # Font sizes
        plt.rcParams["axes.titlesize"] = 14
        plt.rcParams["axes.labelsize"] = 12
        plt.rcParams["xtick.labelsize"] = 10
        plt.rcParams["ytick.labelsize"] = 10

        return prop  # Return the font property to be used later

# Setup function to add the cog to the bot
async def setup(bot):
    await bot.add_cog(DiscordTheme(bot))