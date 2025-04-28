import discord
from discord.ext import commands
import json
import yaml
from icecream import ic
import os
import time

class Verify(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_manager = self.bot.get_cog("DataManager")  

    async def type_test(self, ctx, file, data, key_name, type, required_field: bool = False):
        object = data.get(key_name)
        
        if required_field and object is None:
            await ctx.send(F"`{file}`: Required key `{key_name}` does not exist!")
            return
        if not isinstance(object, type) and object is not None:
            await ctx.send(F"`{file}`: Key `{key_name}` is not type `{str(type)}`!")
                        
    async def value_test(self, ctx, file, data, key_name, values: list, required_field: bool = False):
        object = data.get(key_name)
        
        if required_field and object is None:
            await ctx.send(F"`{file}`: Required key `{key_name}` does not exist!")
            return
        if object not in values and object is not None:
            await ctx.send(F"`{file}`: Key `{key_name}` is not a valid value: `{object}`!")
            
    async def item_test(self, ctx, file, item_name, type):
        if not await self.data_manager.find_data(type, item_name):
            await ctx.send(F"`{file}`: `{type}` item `{item_name}` is not a valid item!")
        
    @commands.command()
    @commands.is_owner()
    async def verify(self, ctx):    
        unifieddata = {}

        for dirpath, _, filenames in os.walk("./data"):
            folder_key = os.path.relpath(dirpath, "./data")
            folder_data = []
            
            for file in filenames:
                if file.endswith(".json") or file.endswith(".yaml"):
                    file_path = os.path.join(dirpath, file)
                    with open(file_path, 'r') as f:
                        try:
                            data = yaml.safe_load(f)
                            data['file_name'] = file_path
                            folder_data.append(data)
                        except json.JSONDecodeError:
                            await ctx.send(f"Skipping invalid JSON: {file_path}")
            if folder_data:
                unifieddata[folder_key] = folder_data

        ## Verify Recipes
        for recipe in unifieddata['recipes']:
            file_name = recipe.get('file_name')
            
            await self.item_test(ctx, file_name, item_name=recipe['name'], type=recipe['type'])
            
            await self.type_test(ctx, file_name, data=recipe, key_name='name', type=str, required_field=True)
            await self.type_test(ctx, file_name, data=recipe, key_name='type', type=str, required_field=True)
            
            if await self.type_test(ctx, file_name, data=recipe, key_name='required_skill', type=str, required_field=False):
                await self.type_test(ctx, file_name, data=recipe, key_name='skill_level', type=str, required_field=True)
                
            for component in recipe['recipe']:
                await self.item_test(ctx, file_name, item_name=component['name'], type='crafting')
                
                await self.type_test(ctx, file_name, data=component, key_name='name', type=str, required_field=True)
                await self.type_test(ctx, file_name, data=component, key_name='amount', type=int, required_field=True)

        ## Verify Crafting Items
        for crafting_item in unifieddata['items/crafting']:
            file_name = crafting_item.get('file_name')
            
            await self.type_test(ctx, file_name, data=crafting_item, key_name='name', type=str, required_field=True)
            await self.type_test(ctx, file_name, data=crafting_item, key_name='base_price', type=int, required_field=True)
        
        ## Verify Equipment Items
        for equipment_item in unifieddata['items/equipment']:
            file_name = equipment_item.get('file_name')
            
            await self.type_test(ctx, file_name, data=equipment_item, key_name='name', type=str, required_field=True)
            await self.type_test(ctx, file_name, data=equipment_item, key_name='description', type=str, required_field=True)
            await self.type_test(ctx, file_name, data=equipment_item, key_name='type', type=str, required_field=True)
            await self.type_test(ctx, file_name, data=equipment_item, key_name='slot', type=str, required_field=True)
            await self.value_test(ctx, file_name, data=equipment_item, key_name='slot', values=['hand', 'feet', 'lower', 'upper', 'head'], required_field=True)
            await self.type_test(ctx, file_name, data=equipment_item, key_name='base_price', type=int, required_field=True)
            await self.type_test(ctx, file_name, data=equipment_item, key_name='base_defense', type=int, required_field=False)
            if await self.type_test(ctx, file_name, data=equipment_item, key_name='actions', type=list, required_field=False):
                for action in equipment_item['actions']:
                    await self.type_test(ctx, file_name, data=action, key_name='name', type=str, required_field=True)
                    await self.type_test(ctx, file_name, data=action, key_name='description', type=str, required_field=True)
                    await self.type_test(ctx, file_name, data=action, key_name='damage', type=int, required_field=True)
                    await self.type_test(ctx, file_name, data=action, key_name='defense', type=int, required_field=True)
            
        ## Verify Single Use Items
        for single_use_item in unifieddata['items/single_use']:
            file_name = single_use_item.get('file_name')
            
            await self.type_test(ctx, file_name, data=single_use_item, key_name='name', type=str, required_field=True)
            await self.type_test(ctx, file_name, data=single_use_item, key_name='description', type=str, required_field=True)
            await self.type_test(ctx, file_name, data=single_use_item, key_name='type', type=str, required_field=True)
            await self.value_test(ctx, file_name, data=single_use_item, key_name='type', values=['consumable'], required_field=True)
            await self.type_test(ctx, file_name, data=single_use_item, key_name='base_heal', type=int, required_field=True)
            await self.type_test(ctx, file_name, data=single_use_item, key_name='base_price', type=int, required_field=True)
            
        
        ## Verify Item Gathering Locations
        for gathering_location in unifieddata['locations/item_gathering']:
            file_name = gathering_location.get('file_name')
            
            await self.type_test(ctx, file_name, data=gathering_location, key_name='name', type=str, required_field=True)
            await self.type_test(ctx, file_name, data=gathering_location, key_name='type', type=str, required_field=True)
            await self.value_test(ctx, file_name, data=gathering_location, key_name='type', values=['gathering'], required_field=True)
            await self.type_test(ctx, file_name, data=gathering_location, key_name='description', type=str, required_field=True)
            await self.type_test(ctx, file_name, data=gathering_location, key_name='base_hrs', type=float, required_field=True)
            await self.type_test(ctx, file_name, data=gathering_location, key_name='visit_cost', type=int, required_field=False)
            await self.type_test(ctx, file_name, data=gathering_location, key_name='skill_test', type=int, required_field=True)
            await self.type_test(ctx, file_name, data=gathering_location, key_name='item_pool', type=list, required_field=True)
            
            for item in gathering_location['item_pool']:
                await self.type_test(ctx, file_name, data=item, key_name='name', type=str, required_field=True)
                await self.type_test(ctx, file_name, data=item, key_name='type', type=str, required_field=True)
                await self.type_test(ctx, file_name, data=item, key_name='chance_to_appear', type=float, required_field=True)
                await self.type_test(ctx, file_name, data=item, key_name='std_amount', type=int, required_field=True)
                await self.type_test(ctx, file_name, data=item, key_name='std_deviation', type=int, required_field=True)
                
            if len(gathering_location['item_pool']) == 0:
                await ctx.send(F"`{file_name}`: This gathering location has no result items!")
        
        ## Verify Jobs
        for job in unifieddata['locations/jobs']:
            file_name = job.get('file_name')
            
            await self.type_test(ctx, file_name, data=job, key_name='name', type=str, required_field=True)
            await self.type_test(ctx, file_name, data=job, key_name='introduction', type=str, required_field=True)
            await self.type_test(ctx, file_name, data=job, key_name='proficiency', type=str, required_field=True)
            await self.type_test(ctx, file_name, data=job, key_name='results', type=list, required_field=True)
            
            for result in job['results']:
                await self.type_test(ctx, file_name, data=result, key_name='text', type=str, required_field=True)
                await self.type_test(ctx, file_name, data=result, key_name='coins_change', type=int, required_field=True)
                await self.type_test(ctx, file_name, data=result, key_name='xp_change', type=int, required_field=True)
                await self.type_test(ctx, file_name, data=result, key_name='hours', type=int, required_field=True)
            
            if len(job['results']) == 0:
                await ctx.send(F"`{file_name}`: This work location has no work results!")
        
        await ctx.send("Verification Complete!")

async def setup(bot):
    await bot.add_cog(Verify(bot))

if __name__ == "__main__":
    import asyncio

    class DummyCtx:
        async def send(self, msg):
            print(msg)

    class DummyBot:
        pass

    dummy_ctx = DummyCtx()
    dummy_bot = DummyBot()
    cog = Verify(dummy_bot)
    asyncio.run(cog.verify(dummy_ctx))