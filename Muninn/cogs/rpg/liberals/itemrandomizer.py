import discord
from discord.ext import commands
import json
import os
import random
from icecream import ic

class ItemRandomizer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_manager = self.bot.get_cog("DataManager") # For Item and Expedition Info

    ## Modifies Item's Values by Rarity if Needed
    async def generate_item(self, type: str, item_name: str):
        item = await self.data_manager.find_data(type, item_name)

        if item is None:
            print('Could not find item to generate!')
            return None
        
        if type == 'single_use' or type == 'equipment':
            with open("rarities.json", "r") as f:
                self.rarities = json.load(f)

            rarity = random.choices(self.rarities, weights=[r['chance'] for r in self.rarities], k=1)[0]
            rarity_quality = rarity['quality']
            rarity_prefix = random.choice(rarity['rarities'])  # One rarity prefix

            item['prefix'] = rarity_prefix  # Prefix assigned directly to 'prefix'
            item['quality'] = rarity_quality  # Quality assigned directly
            item['base_price'] = max(1, int(item['base_price'] * (1 + rarity['price_mod'] / 100)))
            item['type'] = type

            ic(item)
            
            if type == 'equipment' or type == 'single_use':
                if 'base_heal' in item:
                    item['base_heal'] = max(1, int(item['base_heal'] * (1 + rarity['modifier'] / 100)))
                elif 'base_defense' in item:
                    item['base_defense'] = max(1, int(item['base_defense'] * (1 + rarity['modifier'] / 100)))
                elif 'attack' in item:
                    item['attack'] = max(1, int(item['attack'] * (1 + rarity['modifier'] / 100)))

            return item
        
        item['type'] = type
        return item
    
    async def weighted_random_items(self, ctx, type: str, pool: list, item_count: int = 1):
        ic("Started randomized item generation")
        items_result = []
        weights = []
        
        for item in pool:
            print (item) 

            if await self.data_manager.find_data(ctx, type, item['name']) == None:
                print(f"Item '{item['name']}' in selected pool not found")
                return
            
            weights.append(item['weight'])

        if item_count == 1:
            random_item = random.choices(pool, weights=weights)
            item_name = random_item[0]['name']
            ic(item_name)
            generated_item = await self.generate_item(ctx, type, item_name)
            return generated_item
        
        for i in range(item_count):
            random_item = random.choices(pool, weights=weights)['name']
            generated_item = await self.generate_item(ctx, type, random_item['name'])
            items_result.append(generated_item)
            return items_result

async def setup(bot):
    await bot.add_cog(ItemRandomizer(bot))
