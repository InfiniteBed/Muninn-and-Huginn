import os
import requests
from PIL import Image
from io import BytesIO
import numpy as np
from discord.ext import commands

class TwemojiRenderer(commands.Cog):
    TWEMOJI_CDN = "https://cdn.jsdelivr.net/gh/twitter/twemoji@latest/assets/72x72/"
    CACHE_DIR = "cogs/graphs/emoji_cache"

    def __init__(self, bot):
        self.bot = bot
        # Create cache directory if it doesn't exist
        os.makedirs(self.CACHE_DIR, exist_ok=True)

    def _get_twemoji_code(self, emoji):
        """Convert emoji to its hex code for Twemoji URL"""
        if len(emoji) == 0:
            return None
        
        # Handle combined emojis (like flags)
        codes = []
        for char in emoji:
            codes.extend([f"{ord(c):x}" for c in char])
        return "-".join(codes)

    def get_emoji_image(self, emoji):
        """Get Twemoji image for an emoji, using cache if available"""
        code = self._get_twemoji_code(emoji)
        if not code:
            return None

        cache_path = os.path.join(self.CACHE_DIR, f"{code}.png")
        
        # Use cached image if available
        if os.path.exists(cache_path):
            return Image.open(cache_path)

        # Download from Twemoji CDN
        url = f"{self.TWEMOJI_CDN}/{code}.png"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                img = Image.open(BytesIO(response.content))
                img.save(cache_path)  # Cache for future use
                return img
        except Exception:
            pass
        return None

    def create_emoji_label(self, emoji, text, size=(100, 24)):
        """Create a label with Twemoji and text"""
        try:
            # Create a fully transparent background
            label = Image.new('RGBA', size, (0, 0, 0, 0))
            
            # Get the emoji image
            emoji_img = self.get_emoji_image(emoji)
            if emoji_img:
                # Convert to RGBA and ensure proper alpha channel
                emoji_img = emoji_img.convert('RGBA')
                
                # Calculate emoji size while maintaining aspect ratio
                emoji_height = size[1] - 4  # Leave some padding
                aspect = emoji_img.width / emoji_img.height
                emoji_width = int(emoji_height * aspect)
                emoji_img = emoji_img.resize((emoji_width, emoji_height), Image.Resampling.LANCZOS)
                
                # Center emoji vertically
                y_offset = (size[1] - emoji_height) // 2
                # Paste emoji at the start of the label
                label.paste(emoji_img, (2, y_offset), emoji_img)  # Add 2px padding from left

            # Convert to numpy array with proper alpha handling
            return np.array(label)
        except Exception as e:
            print(f"Error creating emoji label: {e}")
            return None


async def setup(bot):
    await bot.add_cog(TwemojiRenderer(bot))
