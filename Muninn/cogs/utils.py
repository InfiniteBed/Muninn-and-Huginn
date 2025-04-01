import discord # type: ignore
from discord.ext import commands # type: ignore
import os
import requests
from PIL import Image
from io import BytesIO
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Utils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_avatar_color_and_image(self, user):
        """Fetch the user's avatar and calculate the average color."""
        try:
            # Check if custom profile image exists on the server
            if os.path.exists(f"/usr/src/bot/profile_images/{user.id}.png"):
                # Read the custom avatar image from the server
                with open(f"/usr/src/bot/profile_images/{user.id}.png", "rb") as image_file:
                    response = image_file.read()

                avatar_image = Image.open(BytesIO(response)).convert("RGB")
                has_custom_image = True
            else:
                # Fetch avatar from Discord if custom profile doesn't exist
                avatar_url = user.avatar.url
                response = requests.get(avatar_url)
                avatar_image = Image.open(BytesIO(response.content)).convert("RGB")
                has_custom_image = False

            # Calculate the average color of the avatar image
            pixels = list(avatar_image.getdata())
            avg_color = tuple(sum(c) // len(c) for c in zip(*pixels))
            embed_color = discord.Color.from_rgb(*avg_color)
            logger.info(f"Calculated average avatar color: {avg_color}")

            # Return the calculated color and the image
            return embed_color, avatar_image, has_custom_image

        except Exception as e:
            logger.error(f"Error fetching or processing avatar image: {e}")
            return discord.Color.blue(), None  # Fallback to blue if there's an error

async def setup(bot):
    await bot.add_cog(Utils(bot))
