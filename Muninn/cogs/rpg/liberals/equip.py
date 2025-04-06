from discord.ext import commands
import discord

class Equip(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.search = bot.get_cog('Search') # For User Find
        self.utils = bot.get_cog('Utils') # For Player's Icon
        self.stats_manager = self.bot.get_cog("StatsManager") # For Player Info
            # fetch_user_stats(user)
        self.list_manager = self.bot.get_cog("ListManager") # For Item and Expedition Info
            # get_expedition(expedition: str)
            # get_item(item: str)

    async def ask_slot(self, ctx, item):
        ### Establish which slots are available to equip based on the item's slot value
        ### If hands, ask which hand to equip it to.
        ### Then, Swap item slot and inventory locations
        user_stats = await self.stats_manager.fetch_user_stats(ctx.author)
        
        
    @commands.command()
    async def equip(self, ctx, item_index: int):
        user_stats = await self.stats_manager.fetch_user_stats(ctx.author)
        item_index = item_index-1
        item = user_stats['inventory'][item_index]

        # Search the player’s inventory for the requested item
        # If the item is not found, send an error message and return
        if not item or not user_stats['inventory'][item_index]:
            await ctx.send("Item not found!")
            return

        # Verify the item is equippable (like a weapon, armor, etc.)
        # If it’s not, send an error message and return
        if item['slot'] == 'consumable':
            await ctx.send("Item is not equippable!")

        # Ask the player which slot they want to equip the item in (if there are multiple valid slots)
        # This could be weapon, armor, accessory, etc.
        item_slot = item['slot']
        wanted_slot = [item_slot]

        if item_slot == 'hand':
            await ctx.send('What hand will you equip the item to?')

            def check(message):
                return message.author == ctx.author and message.channel == ctx.channel
            
            while True:
                response = await self.bot.wait_for('message', check=check)
                if 'left' in response.content.lower():
                    print('Left')
                    wanted_slot = 'hand_left'
                    break
                elif 'right' in response.content.lower():
                    print('Right')
                    wanted_slot = 'hand_right'
                    break
                else:
                    await ctx.send("Please specify 'left' or 'right'.")

        # Move the new item from inventory to the equipped slot
        await self.stats_manager.equip(ctx, wanted_slot, item)

        # Apply the item’s bonuses or effects to the player’s stats

        # Send a confirmation message that the item was successfully equipped

async def setup(bot):
    await bot.add_cog(Equip(bot))
