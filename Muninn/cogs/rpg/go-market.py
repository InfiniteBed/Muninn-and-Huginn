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
    
    async def item_buy(self, ctx, item, market_cog, market, user_data):
        
        combined_name = f"*{item.get('prefix', '')}* {item['name']}".strip()
        embed = discord.Embed(title=combined_name, color=discord.Color.blue())
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
                market_cog.buy_item()
                
            @discord.ui.button(label=f"Back", style=discord.ButtonStyle.red)
            async def back_button(self, interaction: discord.Interaction, button: Button):
                embed, view = self.market_cog.market_comb(ctx, market, market_cog, 1, user_data)
                await interaction.response.edit_message(embed=embed, view=view)
                
        view = BuyView(ctx, market_cog, item, market)
        
        if user_data['coins'] < item['base_price']:
            view.buy_button.disabled = True
                    
        return embed, view

    def page_embed(self, page, items, name, user_data):
        page_beginning_index = 5 * ( page - 1 )
        eval_item_index = page_beginning_index
        description = ""
        
        for i in range(5):
            item = items[eval_item_index]
            if item.get('prefix'):
                prefix = f"*{item['prefix']}* "
            else:
                prefix = ""
            description += f"{eval_item_index}. {prefix}{item['name']} - `{item['base_price']}` coins\n" 
            eval_item_index += 1

        embed = discord.Embed(title=f"*{name}*: Page {page}", description=description, color=0xFEBA17)
        embed.set_footer(text=f"{user_data['profile_name']} has {user_data['coins']} coins")
        
        return embed
    
    def market_comb(self, ctx, market, market_cog, page, user_data):
        user, name, description, items, username = self.market_analyze(market)
        total_pages = math.ceil(len(items)/5)

        embed = self.page_embed(page, items, name, user_data)
        
        class MarketView(View):
            def __init__(self, ctx, market_cog, items, page):
                super().__init__()
                self.market_cog = market_cog
                self.items = items
                self.page = page
                self.ctx = ctx
            
            @discord.ui.button(label=f"1", style=discord.ButtonStyle.grey)
            async def first_button(self, interaction: discord.Interaction, button: Button):
                embed, view = await self.market_cog.item_buy(ctx, items[(self.page*1)-1], market_cog, market, user_data)
                await interaction.response.edit_message(embed=embed, view=view)
        
            @discord.ui.button(label=f"2", style=discord.ButtonStyle.grey)
            async def second_button(self, interaction: discord.Interaction, button: Button):
                embed, view = await self.market_cog.item_buy(ctx, items[(self.page*2)-1], market_cog, market, user_data)
                await interaction.response.edit_message(embed=embed, view=view)
        
            @discord.ui.button(label=f"3", style=discord.ButtonStyle.grey)
            async def third_button(self, interaction: discord.Interaction, button: Button):
                embed, view = await self.market_cog.item_buy(ctx, items[(self.page*3)-1], market_cog, market, user_data)
                await interaction.response.edit_message(embed=embed, view=view)
        
            @discord.ui.button(label=f"4", style=discord.ButtonStyle.grey)
            async def fourth_button(self, interaction: discord.Interaction, button: Button):
                embed, view = await self.market_cog.item_buy(ctx, items[(self.page*4)-1], market_cog, market, user_data)
                await interaction.response.edit_message(embed=embed, view=view)
        
            @discord.ui.button(label=f"5", style=discord.ButtonStyle.grey)
            async def fifth_button(self, interaction: discord.Interaction, button: Button):
                embed, view = await self.market_cog.item_buy(ctx, items[(self.page*5)-1], market_cog, market, user_data)
                await interaction.response.edit_message(embed=embed, view=view)
        
            @discord.ui.button(label=f"Previous", style=discord.ButtonStyle.grey)
            async def prev_button(self, interaction: discord.Interaction, button: Button):
                embed, view = self.market_cog.market_comb(ctx, market, market_cog, page-1, user_data)
                await interaction.response.edit_message(embed=embed, view=view)
        
            @discord.ui.button(label=f"Next", style=discord.ButtonStyle.grey)
            async def next_button(self, interaction: discord.Interaction, button: Button):
                embed, view = self.market_cog.market_comb(ctx, market, market_cog, page+1, user_data)
                await interaction.response.edit_message(embed=embed, view=view)
        
            @discord.ui.button(label=f"Back", style=discord.ButtonStyle.red)
            async def back_button(self, interaction: discord.Interaction, button: Button):
                embed, view = self.market_cog.market_browse_embed_view(ctx, market_cog)
                await interaction.response.edit_message(embed=embed, view=view)
        
        view = MarketView(ctx, market_cog, items, page)
        
        if page == 1:
            view.prev_button.disabled = True
        if page == total_pages:
            view.next_button.disabled = True
    
        return embed, view
    
    async def market_browse_embed_view(self, ctx, market_cog, user_data):
        market_data = self.market_serialize()

        embed = discord.Embed(
            title="Eustrox Market",
            description="Select a shop from the dropdown menu below.",
            color=0xFFCF50
        )

        class VendorDropdown(Select):
            def __init__(self, market_data, user_data):
                options = []
                for index, market in enumerate(market_data[:25]):  # Max 25 options allowed
                    user, name, description, items, username = market_cog.market_analyze(market)
                    label = f"{username}'s Shop"
                    option_description = name if len(name) < 100 else name[:97] + "..."
                    options.append(SelectOption(label=label, description=option_description, value=str(index)))

                super().__init__(placeholder="Select a vendor...", options=options, min_values=1, max_values=1)

                self.market_data = market_data

            async def callback(self, interaction: discord.Interaction):
                index = int(self.values[0])
                selected_market = self.market_data[index]
                embed, view = market_cog.market_comb(ctx, selected_market, market_cog, 1, user_data)
                await interaction.response.edit_message(embed=embed, view=view)

        class VendorDropdownView(View):
            def __init__(self, market_data):
                super().__init__(timeout=60)
                self.add_item(VendorDropdown(market_data, user_data))

        view = VendorDropdownView(market_data)

        return embed, view

    async def market_overview_embed(self, ctx):
        embed = discord.Embed(title="Market Overview", description="shush", color=0x9ACD32)
        
        return embed
    
    class ShopOverView(View):
        def __init__(self, ctx, market_cog, user_data):
            super().__init__()
            self.market_cog = market_cog
            self.user_data = user_data
            self.ctx = ctx

        @discord.ui.button(label="Browse Market", style=discord.ButtonStyle.blurple)
        async def browse_button(self, interaction: discord.Interaction, button: Button):
            embed, view = await self.market_cog.market_browse_embed_view(self.ctx, self.user_data, self.user_data)
            await interaction.response.edit_message(embed=embed, view=view)
            
        ### CONDITIONAL, BASED ON USER ID NOT BEING IN VENDORS
        @discord.ui.button(label="Set Up Stall", style=discord.ButtonStyle.grey)
        async def setup_button(self, interaction: discord.Interaction, button: Button):
            embed, view = self.market_cog.name_question(self.ctx, self.user_data)
            await interaction.response.edit_message(embed=embed, view=view)
        
        ### CONDITIONAL, BASED ON USER ID ALREADY HAVING A VENDOR
        @discord.ui.button(label="Manage Stall", style=discord.ButtonStyle.grey)
        async def manage_button(self, interaction: discord.Interaction, button: Button):
            pass

async def setup(bot):
    await bot.add_cog(GoMarket(bot))