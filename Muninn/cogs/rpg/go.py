import sqlite3
import json
import datetime
import discord
from discord.ext import commands
import asyncio
import math
import ast
from discord.ui import View, Button

class TestView(View):
    def __init__(self):
        super().__init__()

    @discord.ui.button(label="test", style=discord.ButtonStyle.green)
    async def rest_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("testing")
        
class Go(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "discord.db"
        self.item_generator = bot.get_cog('ItemFetch')
        self.stats_manager = self.bot.get_cog("StatsManager")
        self.data_manager = self.bot.get_cog("DataManager")
    
    @commands.command()
    async def go(self, ctx):
        user_stats = await self.stats_manager.fetch_user_stats(ctx.author)

        ## Construct Job Search Embed
        

        ## Construct Item Gathering Embed
        gather_embed = discord.Embed(title="Explore", color=0x00DD77, description=f"Where will **{user_stats['profile_name']}** explore?")

        gather_locations = await self.data_manager.get_data_of_type("item_gathering")
        for location in gather_locations:
            gather_embed.add_field(name=location['name'], value=location['description'])
            
        ## Construct Main Menu Embed
        main_embed = discord.Embed(title="Go", color=0x00DD77, description=f"**{user_stats['profile_name']}** stands just outside {user_stats['pronoun_possessive']} home.")

        def location_details_embed(location, time_gathering = 1):
            embed = discord.Embed(title=f"{location['name']}", color=0x89CFF0, description=f"Select how long **{user_stats['profile_name']}** will explore for.")

            item_bonus = time_gathering/2

            if location['base_hrs'] == 1:
                base_hrs_str = f"{location['base_hrs']} hour"
            else:
                base_hrs_str = f"{location['base_hrs']} hours"

            if time_gathering == 1:
                time_gathering_str = f"{time_gathering} hour"
            else:
                time_gathering_str = f"{time_gathering} hours"

            embed.add_field(name="Time to Arrive:", value=base_hrs_str)
            embed.add_field(name="Time Gathering:", value=time_gathering_str)
            embed.add_field(name="Time to Return:", value=base_hrs_str)
            embed.add_field(name="Total Time:", value=f"*{time_gathering + (location['base_hrs'] * 2)} hours*")
            embed.add_field(name="Time Bonus:", value=f"x{item_bonus}")

            return embed
        
        class JobView(View):
            def __init__(self, nav_buttons, parent_cog):
                super().__init__(timeout=None)

            
                

        class ExploreDetailView(View):
            def __init__(self, ctx, location, hours, parent_cog):
                self.main_embed = main_embed
                self.location = location
                self.hours = hours
                self.parent_cog = parent_cog
                super().__init__(timeout=None)
                self.disable_buttons(hours)

            @discord.ui.button(label="Take", style=discord.ButtonStyle.blurple)
            async def accept_button(self, interaction: discord.Interaction, button: Button):
                location['item_bonus'] = self.hours/2
                
                #### PLEASE EDITs THIS BEFORE PUBLISHING
                eta = await self.parent_cog.stats_manager.update_activity(interaction, location, (self.hours + (location['base_hrs'] * 2)) / 400, 0)

                embed = discord.Embed(title=f"{user_stats['profile_name']} went to go gather items!", color=discord.Color.gold(),
                                      description=f"{user_stats['profile_name']} is now travelling to the {location['name']} to search for items.")
                embed.add_field(name="Time to Finish:", value=f"{self.hours + (location['base_hrs'] * 2)} Hours")
                embed.add_field(name="ETA:", value=eta)
                embed.add_field(name="Time Bonus:", value=f"x{self.hours/2}")
                await interaction.response.edit_message(embed=embed, view=None)

            @discord.ui.button(label="1/2 hrs", style=discord.ButtonStyle.grey)
            async def decrease_button(self, interaction: discord.Interaction, button: Button):
                self.hours = self.hours/2
                embed = location_details_embed(location, self.hours)
                self.disable_buttons(self.hours)
                await interaction.response.edit_message(embed=embed, view=self)

            @discord.ui.button(label="x2 hrs", style=discord.ButtonStyle.grey)
            async def increase_button(self, interaction: discord.Interaction, button: Button):
                self.hours = self.hours*2
                embed = location_details_embed(location, self.hours)
                self.disable_buttons(self.hours)
                await interaction.response.edit_message(embed=embed, view=self)

            @discord.ui.button(label="Back", style=discord.ButtonStyle.red)
            async def home_button(self, interaction: discord.Interaction, button: Button):
                await interaction.response.edit_message(embed=self.main_embed, view=self)

            def disable_buttons(self, hours):
                if hours <= 1:
                    self.decrease_button.disabled = True
                else:
                    self.decrease_button.disabled = False

                if hours >= 8:
                    self.increase_button.disabled = True
                else:
                    self.increase_button.disabled = False

        class ExploreView(View):
            def __init__(self, ctx, nav_buttons, gather_locations, parent_cog):
                self.main_embed = main_embed
                self.nav_buttons = nav_buttons
                self.gather_locations = gather_locations
                self.parent_cog = parent_cog
                super().__init__(timeout=None)

            for location in gather_locations:
                @discord.ui.button(label=location["name"], style=discord.ButtonStyle.grey)
                async def gather_button(self, interaction: discord.Interaction, button: Button):
                    location_name = button.label

                    embed = location_details_embed(location)

                    detail_view = ExploreDetailView(ctx, location, 1, self.parent_cog)
                    await interaction.response.edit_message(embed=embed, view=detail_view)

            @discord.ui.button(label="Back", style=discord.ButtonStyle.red)
            async def home_button(self, interaction: discord.Interaction, button: Button):
                await interaction.response.edit_message(embed=self.main_embed, view=nav_buttons)
                ## Navigate to the Main Menu

        class NavigationButtons(View):
            def __init__(self, ctx, job_embed, gather_embed, parent_cog):
                self.job_embed = job_embed
                self.gather_embed = gather_embed
                self.parent_cog = parent_cog
                super().__init__(timeout=None)

            @discord.ui.button(label="Professions", style=discord.ButtonStyle.blurple)
            async def explore_button(self, interaction: discord.Interaction, button: Button):
                home_button = ExploreView(ctx, nav_buttons, gather_locations, self.parent_cog)
                await interaction.response.edit_message(embed=self.job_embed, view=home_button)

            @discord.ui.button(label="Explore", style=discord.ButtonStyle.blurple)
            async def explore_button(self, interaction: discord.Interaction, button: Button):
                home_button = ExploreView(ctx, nav_buttons, gather_locations, self.parent_cog)
                await interaction.response.edit_message(embed=self.gather_embed, view=home_button)


        nav_buttons = NavigationButtons(ctx, job_embed, gather_embed, self)
        await ctx.send(embed=main_embed, view=nav_buttons)

async def setup(bot):
    await bot.add_cog(Go(bot))