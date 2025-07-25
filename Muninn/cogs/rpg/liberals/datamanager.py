import discord
from discord.ext import commands
import json
import yaml
from icecream import ic
import os

class DataManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    ## Returns all data of a certain type
    async def get_data_of_type(self, data_type: str = None):
        print('Getting data of type...')
        if data_type is None:
            return None

        unifieddata = []

        if data_type == 'items':
            datapath = f'./data/items'
        elif data_type in ('crafting', 'equipment', 'single_use'):
            datapath = f'./data/items/{data_type}'
        elif data_type in ('jobs', 'item_gathering'):
            datapath = f'./data/locations/{data_type}'
        elif data_type in ('recipes'):
            datapath = f'./data/{data_type}'
        else: 
            print(f"ERROR: Data type {data_type} not found")
            return

        for dirpath, _, filenames in os.walk(datapath):
            for file in filenames:
                if file.endswith(".json") or file.endswith(".yaml"):
                    file_path = os.path.join(dirpath, file)
                    with open(file_path, 'r') as f:
                        try:
                            data = yaml.safe_load(f)
                            unifieddata.append(data)
                        except json.JSONDecodeError as e:
                            print(f"Skipping invalid JSON: {file_path}, {e}")

        return unifieddata
    
    ## Finds One Item within One Dataset
    async def find_data(self, type: str, item: str):
        print('Finding item in data...')
        item_data = await self.get_data_of_type(type)
        try:
            for got_item in item_data:
                if got_item["name"].lower() == item.lower():
                    ic("find_data result", type, got_item['name'])
                    return got_item
                
            
        except Exception as e:
            print(f'ERROR - Could not find item in database: {e}')  
            return None
        
        print(f"Unable to find item {item}")

    @commands.command()
    @commands.is_owner()
    async def debug_data(self, data_type):
        data = await self.get_data(data_type)
        print(data)
    
    

async def setup(bot):
    await bot.add_cog(DataManager(bot))
