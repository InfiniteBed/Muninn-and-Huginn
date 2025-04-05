import discord
from discord.ext import commands
import json
import os

class DataManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.is_owner()
    async def validate(self, ctx):
        unifieddata = []

        for dirpath, _, filenames in os.walk("./data"):
            for file in filenames:
                if file.endswith(".json"):
                    file_path = os.path.join(dirpath, file)
                    with open(file_path, 'r') as f:
                        try:
                            data = json.load(f)
                            unifieddata.append(data)
                        except json.JSONDecodeError:
                            await ctx.send(f"Skipping invalid JSON: {file_path}")

        await ctx.send(f"Data validated..")

    ## Returns all data of a certain type
    async def get_data_of_type(self, data_type: str = None):
        if data_type is None:
            return None

        unifieddata = []

        if data_type == 'items':
            datapath = f'./data/items'
        if data_type in ('crafting', 'equipment', 'single_use'):
            datapath = f'./data/items/{data_type}'
        if data_type in ('shops', 'item_gathering'):
            datapath = f'./data/locations/{data_type}'

        for dirpath, _, filenames in os.walk(datapath):
            for file in filenames:
                if file.endswith(".json"):
                    file_path = os.path.join(dirpath, file)
                    with open(file_path, 'r') as f:
                        try:
                            data = json.load(f)
                            unifieddata.append(data)
                        except json.JSONDecodeError:
                            await print(f"Skipping invalid JSON: {file_path}")

        return unifieddata
    
    ## Finds One Item within One Dataset
    async def find_data(self, type: str, item: str):
        item_data = await self.get_data_of_type(type)
        try:
            for got_item in item_data:
                if got_item["name"].lower() == item:
                    return got_item
        except Exception as e:
            print(f'ERROR - Could not find item in database: {e}')  
            return None

    @commands.command()
    @commands.is_owner()
    async def debug_data(self, ctx, data_type):
        data = await self.get_data(ctx, data_type)
        print(data)
    
    

async def setup(bot):
    await bot.add_cog(DataManager(bot))
