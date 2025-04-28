import json
import random
import discord
from discord.ext import commands

class ItemFetch(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.load_data()

    def load_data(self):
        """Load item and rarity data from JSON files."""
        
    async def random_item_or_equip(self, category: str = 'any', from_shop: bool = False):
        """Return a random item or equip with a weighted chance based on price and a random rarity."""
        
        combined_list = self.data  # Assuming this contains all items

        items_with_weights = []
        weights = []

        for item in combined_list:
            price = item['base_price']
            weight = 1 / (price ** 0.5)
            items_with_weights.append(item)
            weights.append(weight)

        # Random Item
        random_item = random.choices(items_with_weights, weights=weights, k=1)[0]

        # Random rarity selection
        rarity = random.choices(self.rarities, weights=[r['chance'] for r in self.rarities], k=1)[0]
        rarity_quality = rarity['quality']
        rarity_prefix = random.choice(rarity['rarities'])  # One rarity prefix

        # Add rarity information to the item
        random_item['prefix'] = rarity_prefix  # Prefix assigned directly to 'prefix'
        random_item['quality'] = rarity_quality  # Quality assigned directly
        random_item['base_price'] = max(1, int(random_item['base_price'] * (1 + rarity['price_mod'] / 100)))

        # Modify stats based on rarity modifier (healing, defense, attack)
        if 'base_heal' in random_item:
            random_item['base_heal'] = max(1, int(random_item['base_heal'] * (1 + rarity['modifier'] / 100)))
        elif 'base_defense' in random_item:
            random_item['base_defense'] = max(1, int(random_item['base_defense'] * (1 + rarity['modifier'] / 100)))
        elif 'attack' in random_item:
            random_item['attack'] = max(1, int(random_item['attack'] * (1 + rarity['modifier'] / 100)))

        # Modify the name with the rarity prefix, but avoid duplicating
        random_item['name'] = random_item['name']

        return random_item

    @commands.command()
    @commands.is_owner()
    async def dev_random_item_test(self, ctx):
        await ctx.send(await self.random_item_or_equip())

async def setup(bot):
    await bot.add_cog(ItemFetch(bot))
