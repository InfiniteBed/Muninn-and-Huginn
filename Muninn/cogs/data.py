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

    async def get_all_data_type(self, data_type: str = None):
        if data_type is None:
            return None

        unifieddata = []

        if data_type == 'items':
            datapath = f'./data/{data_type}'
        if data_type == 'shops' or data_type == 'item_gathering':
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
    

    @commands.command()
    @commands.is_owner()
    async def debug_data(self, ctx, data_type):
        data = await self.get_data(ctx, data_type)
        print(data)
    
    

async def setup(bot):
    await bot.add_cog(DataManager(bot))
