import sqlite3
import json
import datetime
import discord
from discord.ext import commands
import asyncio
import math
import ast
from discord.ui import View, Button

class Shop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "discord.db"
        self.item_generator = bot.get_cog('ItemFetch')
        self.stats_manager = self.bot.get_cog("StatsManager")

        """Create the table in the SQLite database if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''CREATE TABLE IF NOT EXISTS vendors (
                            vendor TEXT PRIMARY KEY,
                            items TEXT,
                            time_loaded TEXT)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS inventory (
                            user_id INTEGER PRIMARY KEY,
                            inventory TEXT)''')

        conn.commit()
        conn.close()

    def get_last_timestamp(self):
        """Get the timestamp of the last shop contents entry."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT time_loaded FROM vendors WHERE vendor = ?", ("Shop",))
        timestamp = cursor.fetchone()
        conn.close()

        return timestamp[0] if timestamp else None

    def is_shop_empty(self):
        """Check if the shop is empty."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT items FROM vendors WHERE vendor = ?", ("Shop",))
        result = cursor.fetchone()
        conn.close()

        return not result or not json.loads(result[0])

    async def regenerate_shop(self, ctx):
        """Regenerate the shop's content and store it in the database."""
        last_timestamp = self.get_last_timestamp()
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")

        if last_timestamp and last_timestamp.split('T')[0] == current_date:
            await ctx.send("The shop has already been regenerated today.")
            return

        stock = 10
        shop_data = []

        for _ in range(stock):
            item = await self.item_generator.random_item_or_equip("equip", True)
            shop_data.append(item)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("INSERT OR REPLACE INTO vendors (vendor, items, time_loaded) VALUES (?, ?, ?)", 
                       ("Shop", json.dumps(shop_data), datetime.datetime.now().isoformat()))
        conn.commit()
        conn.close()

        await ctx.send("The shop has been restocked with new items!")

    async def check_and_regenerate(self, ctx):
        """Check if the shop needs to be regenerated, or force regeneration if empty."""
        if self.is_shop_empty():
            await self.regenerate_shop(ctx)
        else:
            last_timestamp = self.get_last_timestamp()
            current_date = datetime.datetime.now().strftime("%Y-%m-%d")

            if not last_timestamp or last_timestamp.split('T')[0] != current_date:
                await self.regenerate_shop(ctx)

    def get_user_inventory(self, user_id):
        """Retrieve the user's inventory from the database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        #Check if inventotry is empty, then skip if empty. theres definitely a waaaaay better way to do this
        cursor.execute("SELECT user_id FROM inventory WHERE inventory IS NULL")
        data = cursor.fetchall()
        print (data)
        for id in data:
            print (id)   
            if id[0] == user_id:
                return []

        cursor.execute("SELECT inventory FROM inventory WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()

        return json.loads(result[0]) if result is not 'None' else []

    def update_user_inventory(self, user_id, new_inventory):
        """Update the user's inventory in the database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("INSERT OR REPLACE INTO inventory (user_id, inventory) VALUES (?, ?)", (user_id, json.dumps(new_inventory)))
        conn.commit()
        conn.close()

    async def buy_item(self, ctx, item_index):
        """Handle the item purchase."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT items FROM vendors WHERE vendor = ?", ("Shop",))
        shop_data = json.loads(cursor.fetchone()[0])
        conn.close()

        # Validate the item index
        if item_index < 1 or item_index > len(shop_data):
            await ctx.send("Invalid item index.")
            return

        item = shop_data[item_index - 1]
        price = item['base_price']

        # Get the user's stats and check if they have enough coins
        user_stats = await self.stats_manager.fetch_user_stats(ctx.author)

        if user_stats['coins'] < price:
            await ctx.send("You don't have enough coins to purchase this item.")
            return

        # Deduct the price from the user's coins
        await self.stats_manager.modify_user_stat(ctx.author, 'coins', (price * -1))

        # Add the item to the user's inventory
        user_inventory = self.get_user_inventory(ctx.author.id)
        user_inventory.append(item)
        self.update_user_inventory(ctx.author.id, user_inventory)

        # Remove the item from the shop's inventory
        shop_data.pop(item_index - 1)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("INSERT OR REPLACE INTO vendors (vendor, items, time_loaded) VALUES (?, ?, ?)", ("Shop", json.dumps(shop_data), datetime.datetime.now().isoformat(),))
        conn.commit()
        conn.close()

        # Display the final page
        final_embed = discord.Embed(
            title="Purchase Successful!",
            description=f"You have successfully purchased **{item['name']}** for **{price} coins**!",
            color=discord.Color.green()
        )
        final_embed.set_footer(text="Thank you for your purchase!")
        final_view = View()
        await ctx.send(embed=final_embed, view=final_view)

    @commands.command()
    async def shop(self, ctx):
        await self.check_and_regenerate(ctx)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT items FROM vendors WHERE vendor = ?", ("Shop", ))
        result = cursor.fetchone()

        if not result:
            await ctx.send("The shop has no available items right now.")
            return

        data = json.loads(result[0])
        conn.close()
        user_stats = await self.stats_manager.fetch_user_stats(ctx.author)

        items_per_page = 5
        total_pages = math.ceil(len(data) / items_per_page)
        page = 1

        def generate_main_embed(page):
            start_index = (page - 1) * items_per_page
            end_index = start_index + items_per_page
            embed = discord.Embed(title=f"Shop - Page {page}/{total_pages}", color=discord.Color.orange())

            description = ""
            for index, item_data in enumerate(data[start_index:end_index], start=start_index + 1):
                combined_name = f"{item_data.get('prefix', '')} {item_data['name']}".strip()
                price = item_data['base_price']
                description += f"**{index}.** {combined_name} - **{price} coins**\n"

            embed.description = description
            embed.set_footer(text=f"{user_stats['coins']} Coins in {user_stats['profile_name']}'s Coin Purse")
            return embed

        async def generate_item_embed(item_index):
            item = data[item_index]
            combined_name = f"*{item.get('prefix', '')}* {item['name']}".strip()
            embed = discord.Embed(title=combined_name, color=discord.Color.blue())
            embed.add_field(name="Description", value=item['description'], inline=False)
            embed.add_field(name="Price", value=f"{item['base_price']} coins", inline=False)
            if 'slot' in item:
                embed.add_field(name="Slot", value=item['slot'], inline=False)
            if 'actions' in item:
                actions = "\n".join([f"- {action['name']}: {action['description']}" for action in item['actions']])
                embed.add_field(name="Actions", value=actions, inline=False)
            embed.set_footer(text=f"{user_stats['coins']} Coins in {user_stats['profile_name']}'s Coin Purse")
            return embed

        async def update_main_embed(interaction, message, page):
            await interaction.response.defer()
            await message.edit(embed=generate_main_embed(page), view=create_main_view(page))

        async def update_item_embed(interaction, message, item_index):
            await interaction.response.defer()
            await message.edit(embed=await generate_item_embed(item_index), view=create_item_view(item_index))

        def create_main_view(page):
            view = View()
            start_index = (page - 1) * items_per_page
            end_index = start_index + items_per_page

            for index in range(start_index, min(end_index, len(data))):
                item_button = Button(label=f"{index + 1}", style=discord.ButtonStyle.primary)

                async def item_button_callback(interaction, idx=index):
                    await update_item_embed(interaction, interaction.message, idx)

                item_button.callback = item_button_callback
                view.add_item(item_button)

            if page > 1:
                prev_button = Button(label="Previous", style=discord.ButtonStyle.secondary)

                async def prev_button_callback(interaction):
                    await update_main_embed(interaction, interaction.message, page - 1)

                prev_button.callback = prev_button_callback
                view.add_item(prev_button)

            if page < total_pages:
                next_button = Button(label="Next", style=discord.ButtonStyle.secondary)

                async def next_button_callback(interaction):
                    await update_main_embed(interaction, interaction.message, page + 1)

                next_button.callback = next_button_callback
                view.add_item(next_button)

            return view

        def create_item_view(item_index):
            view = View()

            buy_button = Button(label="Buy", style=discord.ButtonStyle.success)

            async def buy_button_callback(interaction):
                await interaction.response.defer()
                await self.buy_item(ctx, item_index + 1)

            buy_button.callback = buy_button_callback
            view.add_item(buy_button)

            back_button = Button(label="Back to Shop", style=discord.ButtonStyle.secondary)

            async def back_button_callback(interaction):
                await update_main_embed(interaction, interaction.message, page)

            back_button.callback = back_button_callback
            view.add_item(back_button)

            return view

        message = await ctx.send(embed=generate_main_embed(page), view=create_main_view(page))

    @commands.command()
    async def buy(self, ctx, item_index: int):
        """Buy an item from the shop."""
        await self.buy_item(ctx, item_index)

# Setup the cog
async def setup(bot):
    await bot.add_cog(Shop(bot))  # Ensure this function is correctly defined
