import sqlite3
import discord
from discord.ext import commands
import json
import os

class ListManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_expedition(self, expedition: str):
        expeditions_dir = '/usr/src/bot/expeditions/'
        if not os.path.exists(expeditions_dir):
            os.makedirs(expeditions_dir)  # Create the directory if it doesn't exist

        # Do not replace underscores; assume the expedition name is stored with underscores
        expedition_path = os.path.join(expeditions_dir, f'{expedition}.json')
        print(f"Attempting to load expedition file: {expedition_path}")  # Debugging log
        if not os.path.exists(expedition_path):
            return {"error": "Expedition not found"}

        with open(expedition_path, 'r') as file:
            expedition_data = json.load(file)

        # Ensure compatibility with the updated format
        expedition_data["description"] = expedition_data.get("description", {}).get("male", "No description available.")
        expedition_data["id"] = expedition  # Add the trimmed file name as the expedition ID
        return expedition_data
    
    async def get_item_data(self, item: str):
        with open('items.json', 'r') as file:
            item_data = json.load(file)

        for got_item in item_data:
            if got_item["name"] == item:
                return {
                    "name": got_item["name"],
                    "description": got_item["description"],
                    "type": got_item.get("type"),  # Add type (e.g., consumable, equippable)
                    "slot": got_item.get("slot"),  # Add slot for equippable items
                    "base_heal": got_item.get("base_heal", 0),  # Add healing value for consumables
                    "base_defense": got_item.get("base_defense", 0),  # Add defense value for equippable items
                    "actions": got_item.get("actions", [])  # Add actions for equippable items
                }
        return {"error": "Item not found"}

# Setup the cog
async def setup(bot):
    await bot.add_cog(ListManager(bot))