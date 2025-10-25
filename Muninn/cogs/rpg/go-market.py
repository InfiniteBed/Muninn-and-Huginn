import ast
import asyncio
import datetime
import json
import math
import random
import sqlite3

import discord
from discord import SelectOption
from discord.ext import commands
from discord.ui import Button, Select, View, TextInput, Modal

from icecream import ic

class GoMarket(commands.Cog):    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "discord.db"
        self.item_generator = bot.get_cog('ItemFetch')
        self.user_manager = self.bot.get_cog("StatsManager")
        self.data_manager = self.bot.get_cog("DataManager")
    
        """Create the table in the SQLite database if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''CREATE TABLE IF NOT EXISTS vendors (
                            user NUMERIC PRIMARY KEY,
                            name TEXT,
                            description TEXT,
                            items TEXT
                            )'''        
                        )

        cursor.execute('''CREATE TABLE IF NOT EXISTS inventory (
                            user_id INTEGER PRIMARY KEY,
                            inventory TEXT)''')

        conn.commit()
        conn.close()
        
        
    def market_serialize(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT user, name, description, items FROM vendors")
        result = cursor.fetchall()
        
        if not result:
            return
        
        serialized = []
        
        for x in result:
            user = x[0]
            name = x[1]
            description = x[2]
            
            if not x[3]:
                items = None
            else:
                items = json.loads(x[3])
                
            block = user, name, description, items
            serialized.append(block)

                
        return serialized
    
    def market_analyze(self, market):
        user_id = market[0]
        name = market[1]
        description = market[2]
        items = market[3]
        username = self.bot.get_user(user_id).display_name
        
        return user_id, name, description, items, username
    
    def get_user_inventory(self, user_id):
        """Retrieve the user's inventory from the database."""
        conn = sqlite3.connect('discord.db')
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

    def update_user_inventory(self, user_id, new_inventory, shop_name):
        """Update the user's inventory in the database."""
        conn = sqlite3.connect('discord.db')
        cursor = conn.cursor()

        cursor.execute("INSERT OR REPLACE INTO inventory (user_id, inventory) VALUES (?, ?)", (user_id, json.dumps(new_inventory)))
        conn.commit()
        conn.close()

    def get_default_values(self, vendor_id):
        
        conn = sqlite3.connect('discord.db')
        cursor = conn.cursor()

        cursor.execute("SELECT user, name, description, items FROM vendors WHERE user = ?", (vendor_id, ))
        x = cursor.fetchone()
        
        if not x:
            return "", ""
        
        name = x[1]
        description = x[2]

        return name, description

    def add_item_to_vendor(self, vendor_id, item_data):
        conn = sqlite3.connect('discord.db')
        cursor = conn.cursor()
        cursor.execute("SELECT items FROM vendors WHERE user = ?", (vendor_id,))
        items = cursor.fetchone()
        
        if items is None or items[0] is None:
            new_items = []
        else:
            new_items = json.loads(items[0])

        new_items.append(item_data)
            
        name, description = self.get_default_values(vendor_id)
        
        cursor.execute("INSERT OR REPLACE INTO vendors (user, name, description, items) VALUES (?, ?, ?, ?)", (vendor_id, name, description, json.dumps(new_items)))
        conn.commit()
        conn.close()
        
    async def buy_item(self, ctx, item, items, vendor_id, vendor_name, vendor_description):
        """Handle the item purchase."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        price = item['base_price']

        # Get the user's stats and check if they have enough coins
        user_stats = await self.user_manager.fetch_user_stats(ctx.author)

        if user_stats['coins'] < price:
            await ctx.send("You don't have enough coins to purchase this item.")
            return

        # Deduct the price from the user's coins
        await self.user_manager.modify_user_stat(ctx.author, 'coins', (price * -1))
        
        # Add coins to vendor user
        await self.user_manager.modify_user_stat(vendor_id, 'coins', (price))

        # Add the item to the user's inventory
        user_inventory = self.get_user_inventory(ctx.author.id)
        user_inventory.append(item)
        self.update_user_inventory(ctx.author.id, user_inventory, vendor_name)

        # Remove the item from the shop's inventory
        new_shop_data = list(items)
        new_shop_data.remove(item)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("INSERT OR REPLACE INTO vendors (user, name, description, items) VALUES (?, ?, ?, ?)", (vendor_id, vendor_name, vendor_description, json.dumps(new_shop_data)))
        finally:
            conn.commit()
            conn.close()
            
        vendor_user = self.bot.get_user(vendor_id)
        
        embed = discord.Embed(
            title=f"{ctx.author.display_name} bought your {item['name']}!",
            description=f"{ctx.author.display_name} has purchased **{item['name']}** for **{price} coins**!\nI'm sure they'll put it to good use!",
            color=discord.Color.green()
        )
        
        await vendor_user.send(embed=embed)

        # Display the final page
        final_embed = discord.Embed(
            title="Purchase Successful!",
            description=f"You have successfully purchased **{item['name']}** for **{price} coins**!",
            color=discord.Color.green()
        )
        final_embed.set_footer(text="Thank you for your purchase!")
        final_view = View()
        
        return final_embed

    async def item_buy(self, ctx, item, market_cog, market, user_data, message):
        
        combined_name = f"*{item.get('prefix', '')}* {item['name']}".strip()
        embed = discord.Embed(title=combined_name, color=discord.Color.blue())
        if item.get('description'):
            embed.add_field(name="Description", value=item['description'], inline=False)
        embed.add_field(name="Price", value=f"{item['base_price']} coins", inline=False)
        embed.set_footer(text=f"{user_data['profile_name']} has {user_data['coins']} coins")
        
        if 'slot' in item:
            embed.add_field(name="Slot", value=item['slot'], inline=False)
        if 'actions' in item:
            actions = "\n".join([f"- {action['name']}: {action['description']}" for action in item['actions']])
            embed.add_field(name="Actions", value=actions, inline=False)
            
        class BuyView(View):
            def __init__(self, ctx, market_cog, item, market):
                super().__init__()
                self.market_cog = market_cog
                self.item = item
                self.ctx = ctx
            
            @discord.ui.button(label=f"Purchase", style=discord.ButtonStyle.green)
            async def buy_button(self, interaction: discord.Interaction, button: Button):
                embed = await market_cog.buy_item(ctx, item, market[3], market[0], market[1], market[2])
                await interaction.response.edit_message(embed=embed, view=None)
            
            @discord.ui.button(label=f"Back", style=discord.ButtonStyle.red)
            async def back_button(self, interaction: discord.Interaction, button: Button):
                embed, view = self.market_cog.market_comb(ctx, market, market_cog, 1, user_data, message)
                await interaction.response.edit_message(embed=embed, view=view)
                
        view = BuyView(ctx, market_cog, item, market)
        
        if user_data['coins'] < item['base_price']:
            view.buy_button.disabled = True
                    
        return embed, view

    def page_embed(self, page, items, name, user_data):
        total_pages = math.ceil(len(items)/10)
        
        # Calculate start index for current page
        start_index = (page - 1) * 10
        description = f"{user_data['profile_name']} has **{user_data['coins']} coins**.\n"
        
        for i in range(10):
            if ((i)*page) > (len(items)-1):
                break
            if start_index >= len(items):
                break
            
            ic(len(items), i, (i+1)*page)
            
            item = items[i]
            if item.get('prefix'):
                prefix = f"*{item['prefix']}* "
            else:
                prefix = ""
            description += f"{i}. {prefix}{item['name']} - `{item['base_price']}` coins\n" 

        embed = discord.Embed(title=f"*{name}* - Page {page}", description=description, color=0xFEBA17)
        embed.set_footer(text=f"Items {start_index+1}-{min(start_index+10, len(items))} of {len(items)}")
        
        return embed
    
    def market_comb(self, ctx, market, market_cog, page, user_data, message):
        user, name, description, items, username = self.market_analyze(market)
        start_index = (page - 1) * 10
        total_pages = math.ceil(len(items)/10)

        embed = self.page_embed(page, items, name, user_data)
        
        class MarketView(View):
            def __init__(self, ctx, market_cog, items, page):
                super().__init__()
                self.market_cog = market_cog
                self.items = items
                self.page = page
                self.ctx = ctx
            
            @discord.ui.button(label=f"{start_index+1}", style=discord.ButtonStyle.grey)
            async def first_button(self, interaction: discord.Interaction, button: Button):
                embed, view = await self.market_cog.item_buy(ctx, items[start_index], market_cog, market, user_data, message)
                await interaction.response.edit_message(embed=embed, view=view)
        
            @discord.ui.button(label=f"{start_index+2}", style=discord.ButtonStyle.grey)
            async def second_button(self, interaction: discord.Interaction, button: Button):
                embed, view = await self.market_cog.item_buy(ctx, items[start_index+1], market_cog, market, user_data, message)
                await interaction.response.edit_message(embed=embed, view=view)
        
            @discord.ui.button(label=f"{start_index+3}", style=discord.ButtonStyle.grey)
            async def third_button(self, interaction: discord.Interaction, button: Button):
                embed, view = await self.market_cog.item_buy(ctx, items[start_index+2], market_cog, market, user_data, message)
                await interaction.response.edit_message(embed=embed, view=view)
        
            @discord.ui.button(label=f"{start_index+4}", style=discord.ButtonStyle.grey)
            async def fourth_button(self, interaction: discord.Interaction, button: Button):
                embed, view = await self.market_cog.item_buy(ctx, items[start_index+3], market_cog, market, user_data, message)
                await interaction.response.edit_message(embed=embed, view=view)
        
            @discord.ui.button(label=f"{start_index+5}", style=discord.ButtonStyle.grey)
            async def fifth_button(self, interaction: discord.Interaction, button: Button):
                embed, view = await self.market_cog.item_buy(ctx, items[start_index+4], market_cog, market, user_data, message)
                await interaction.response.edit_message(embed=embed, view=view)
        
            @discord.ui.button(label=f"{start_index+6}", style=discord.ButtonStyle.grey)
            async def sixth_button(self, interaction: discord.Interaction, button: Button):
                embed, view = await self.market_cog.item_buy(ctx, items[start_index+5], market_cog, market, user_data, message)
                await interaction.response.edit_message(embed=embed, view=view)
        
            @discord.ui.button(label=f"{start_index+7}", style=discord.ButtonStyle.grey)
            async def seventh_button(self, interaction: discord.Interaction, button: Button):
                embed, view = await self.market_cog.item_buy(ctx, items[start_index+6], market_cog, market, user_data, message)
                await interaction.response.edit_message(embed=embed, view=view)
        
            @discord.ui.button(label=f"{start_index+8}", style=discord.ButtonStyle.grey)
            async def eighth_button(self, interaction: discord.Interaction, button: Button):
                embed, view = await self.market_cog.item_buy(ctx, items[start_index+7], market_cog, market, user_data, message)
                await interaction.response.edit_message(embed=embed, view=view)
        
            @discord.ui.button(label=f"{start_index+9}", style=discord.ButtonStyle.grey)
            async def ninth_button(self, interaction: discord.Interaction, button: Button):
                embed, view = await self.market_cog.item_buy(ctx, items[start_index+8], market_cog, market, user_data, message)
                await interaction.response.edit_message(embed=embed, view=view)
        
            @discord.ui.button(label=f"{start_index+10}", style=discord.ButtonStyle.grey)
            async def tenth_button(self, interaction: discord.Interaction, button: Button):
                embed, view = await self.market_cog.item_buy(ctx, items[start_index+9], market_cog, market, user_data, message)
                await interaction.response.edit_message(embed=embed, view=view)
        
            @discord.ui.button(label=f"Previous", style=discord.ButtonStyle.grey)
            async def prev_button(self, interaction: discord.Interaction, button: Button):
                embed, view = self.market_cog.market_comb(ctx, market, market_cog, page-1, user_data, message)
                await interaction.response.edit_message(embed=embed, view=view)
        
            @discord.ui.button(label=f"Next", style=discord.ButtonStyle.grey)
            async def next_button(self, interaction: discord.Interaction, button: Button):
                embed, view = self.market_cog.market_comb(ctx, market, market_cog, page+1, user_data, message)
                await interaction.response.edit_message(embed=embed, view=view)
        
            @discord.ui.button(label=f"Back", style=discord.ButtonStyle.red)
            async def back_button(self, interaction: discord.Interaction, button: Button):
                embed, view = await self.market_cog.market_overview_embed(ctx, market_cog, user_data, message)
                await interaction.response.edit_message(embed=embed, view=view)
        
        view = MarketView(ctx, market_cog, items, page)
        
        # Enable/disable buttons based on available items
        buttons = [
            view.first_button,
            view.second_button,
            view.third_button,
            view.fourth_button,
            view.fifth_button,
            view.sixth_button,
            view.seventh_button,
            view.eighth_button,
            view.ninth_button,
            view.tenth_button,
        ]
        
        for index, button in enumerate(buttons):
            item_index = start_index + index
            button.disabled = False if item_index < len(items) else True
            
        if page == 1:
            view.prev_button.disabled = True
        if page == total_pages:
            view.next_button.disabled = True
    
        return embed, view
    
    async def market_browse_embed_view(self, ctx, market_cog, user_data, message, interaction):
        market_data = self.market_serialize()

        embed = discord.Embed(
            title="Eustrox Market",
            description="Upon entering the market, it was immediately clear that it was bigger that perceived from the outside. Rows of stalls lined the worn cobbled streets, winding and twisting in all directions. The smell of freshly baked bread wafted through the air, sparking hunger in all passersby. A calm breeze ambled along the stalls, pushing hanging goods to dance and sing.\n\nThe vendors themselves were all as pleasant as the market's atmosphere. After some friendly small talk, the vendors mention that they set up their stalls every day for any traveler that may pass through, as the roads converge there before a mountain pass.\n\nEventually, a stop is made at one particular vendor...\n-# Written by Luci",
            color=0xFFCF50
        )
        
        options = []

        for index, market in enumerate(market_data[:25]):  # Max 25 options allowed
            user, name, description, items, username = market_cog.market_analyze(market)
            
            if not items:
                continue
            
            
            label = f"{username}'s Shop"
            option_description = name if len(name) < 100 else name[:97] + "..."
            options.append(SelectOption(label=label, description=option_description, value=str(index)))
    
        if len(options) is 0:
            embed = discord.Embed(title='The Market is completely empty!',
                                  description="Come back later, or sell some of your own items!",
                                  color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        class VendorDropdown(Select):
            def __init__(self, market_data, user_data):
                options = []
                for index, market in enumerate(market_data[:25]):  # Max 25 options allowed
                    user, name, description, items, username = market_cog.market_analyze(market)
                    
                    if not items:
                        continue
                    
                    label = f"{username}'s Shop"
                    option_description = name if len(name) < 100 else name[:97] + "..."
                    options.append(SelectOption(label=label, description=option_description, value=str(index)))


                super().__init__(placeholder="Select a vendor...", options=options, min_values=1, max_values=1)

                self.market_data = market_data

            async def callback(self, interaction: discord.Interaction):
                if interaction.user.id != ctx.author.id:
                    await interaction.response.send_message("Sorry, this menu isn't for you.", ephemeral=True)
                    return

                index = int(self.values[0])
                selected_market = self.market_data[index]
                embed, view = market_cog.market_comb(ctx, selected_market, market_cog, 1, user_data, message)
                await interaction.response.edit_message(embed=embed, view=view)

        class VendorDropdownView(View):
            def __init__(self, market_data):
                super().__init__(timeout=60)
                self.add_item(VendorDropdown(market_data, user_data))

        view = VendorDropdownView(market_data)

        return embed, view

    async def sell_item_view(self, ctx, market_cog, user_data):
        data_manager = self.bot.get_cog("DataManager")
        user_manager = self.bot.get_cog("StatsManager")

        embed = discord.Embed(
            title="Sell Item",
            description="The stall lay barren. The splintering wood creaked idly with the wind. Everything was mad for a purpose, and this stall was made to display wares for selling. Now, it seemed almost downcast without anything on it's worn shelves. It has been without fulfilling it's purpose for long enough... maybe it's time to restock?",
            color=0xFF8250
        )

        class SellValueModal(Modal):
            def __init__(self, ctx, item_index, user_data, market_cog):
                super().__init__(title="Sell Item")

                # Store the necessary data
                self.ctx = ctx
                self.item_index = item_index
                self.user_data = user_data
                self.market_cog = market_cog

                # Create input fields first
                self.sellvalue = SellValue("How many coins will you sell your item for?", ctx)

                # Then add them to the modal
                self.add_item(self.sellvalue)

            async def on_submit(self, interaction: discord.Interaction):
                sell_value_str = self.sellvalue.value
            
                ic('made it here!')
                
                # Try to convert the string to an integer
                try:
                    sell_value = int(sell_value_str)
                    # Optional: Check if the value is positive
                    if sell_value <= 0:
                        await interaction.response.send_message(embed=discord.Embed(
                            title="Invalid price!",
                            description="Please enter a positive number greater than 0.",
                            color=discord.Color.red()
                        ), view=None, ephemeral=True)
                        return
                except ValueError:
                    await interaction.response.send_message(embed=discord.Embed(
                            title="You did not enter a number!",
                            description="Please enter only a number next time. :(",
                            color=discord.Color.red()
                        ), view=None, ephemeral=True)
                    return
                
                # Process the item sale here
                item = self.user_data['inventory'][self.item_index]
                item['base_price'] = sell_value

                embed = discord.Embed(
                    title=f"{self.user_data['profile_name']} put the {item['name']} up for sale for {item['base_price']} coins! You've made the stall happy :)", 
                    color=0xFF8250, 
                    description=""
                )
                
                # Remove item from the user's inventory and add to vendor
                self.market_cog.add_item_to_vendor(interaction.user.id, item)
                user_manager.remove_from_user_inventory(interaction.user.id, item)
                
                await interaction.response.edit_message(embed=embed, view=None)
                
        class SellValue(TextInput):
            def __init__(self, label, ctx):
                super().__init__(label=label, placeholder="Type a number here...", default=None, required=True)
            
            async def callback(self, interaction: discord.Interaction):
                sellvalue = self.value

        class VendorDropdown(Select):
            def __init__(self, options):
                super().__init__(
                    placeholder="Select an item to put up for sale...",
                    options=options,
                    min_values=1,
                    max_values=1
                )

            @classmethod
            async def create(cls):
                options = []
                
                for index, item in enumerate(user_data['inventory'][:25]):
                    item_data = await data_manager.find_data(item['type'], item['name'])
                    description = item_data.get('description')[:100] if item_data.get('description') else None
                    prefix = item.get('prefix', '')  # Get the prefix if available
                    heal_info = f" (heals {item.get('base_heal')} HP)" if item.get('base_heal') else ""
                    label = f"{prefix} {item['name']} {heal_info}".strip()
                    options.append(SelectOption(label=label, description=description, value=str(index)))

                return cls(options)

            async def callback(self, interaction: discord.Interaction):
                if interaction.user.id != ctx.author.id:
                    await interaction.response.send_message("Sorry, this menu isn't for you.", ephemeral=True)
                    return
                
                index = int(self.values[0])
                modal = SellValueModal(ctx, index, user_data, market_cog)
                await interaction.response.send_modal(modal)

    
        class VendorDropdownView(View):
            def __init__(self, dropdown: VendorDropdown):
                super().__init__(timeout=60)
                self.add_item(dropdown)
                
        dropdown = await VendorDropdown.create()

        view = VendorDropdownView(dropdown)
        
        return embed, view
    
    def if_user_has_stall(self, ctx):
        conn = sqlite3.connect('discord.db')
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT user FROM vendors WHERE user = ?", (ctx.author.id,))
            row = cursor.fetchone()
            user = row[0] if row else None  # Preserve current items, or None if new
        except Exception as e:
            print (e)
        finally:
            conn.close()
            
        if user:
            return True
        else:
            return False

    async def market_overview_embed(self, ctx, market_cog, user_data, message):
        embed = discord.Embed(title="Market Overview", 
                              description="Coming up over the hill, a quaint market comes into view. The early morning sun reflected off the colorful glass trinkets and cups, giving the area pleasant, ethereal lighting. The morning dew cooled the air, making it a perfect day to browse the wares.\n\nApproaching closer to the market ,it becomes evident that the stalls are handmade by the vendors. The wooden beams are varied in size and distance, and the canopies - though beautifully differed in color - were also varied in quality and type of material. However, whether faded or new, it was clear each canopy was made with love.", 
                              color=0x9ACD32)
        embed.set_footer(text="written by Luci")
        
        class ShopOverView(View):
            def __init__(self):
                super().__init__()

            @discord.ui.button(label="Browse Market", style=discord.ButtonStyle.blurple)
            async def browse_button(self, interaction: discord.Interaction, button: Button):
                embed, view = await market_cog.market_browse_embed_view(ctx, market_cog, user_data, message, interaction)
                await interaction.response.edit_message(embed=embed, view=view)
                
            if not market_cog.if_user_has_stall(ctx):
                @discord.ui.button(label="Set Up Stall", style=discord.ButtonStyle.grey)
                async def setup_button(self, interaction: discord.Interaction, button: Button):
                    await market_cog.bot.get_cog("GoMarketSetup").setup_market(ctx, interaction)
                
            if market_cog.if_user_has_stall(ctx):
                @discord.ui.button(label="Manage Stall", style=discord.ButtonStyle.grey)
                async def setup_button(self, interaction: discord.Interaction, button: Button):
                    await market_cog.bot.get_cog("GoMarketSetup").setup_market(ctx, interaction)

            if market_cog.if_user_has_stall(ctx):
                @discord.ui.button(label="Add Items to Stall", style=discord.ButtonStyle.grey)
                async def manage_button(self, interaction: discord.Interaction, button: Button):
                    if user_data['inventory'] == 'empty':
                        await interaction.response.send_message(embed=discord.Embed(title=f"{user_data['profile_name']} has no items to put up for sale!", color=discord.Color.red()), ephemeral=True)
                    else:
                        embed, view = await market_cog.sell_item_view(ctx, market_cog, user_data)
                        await interaction.response.edit_message(embed=embed, view=view)

            @discord.ui.button(label=f"Back", style=discord.ButtonStyle.red)
            async def back_button(self, interaction: discord.Interaction, button: Button):
                await message.delete()
                await market_cog.bot.get_cog("Go").go(ctx)
        
        view = ShopOverView()

        return embed, view
    
    
async def setup(bot):
    await bot.add_cog(GoMarket(bot))