import sqlite3
import json
import datetime
import discord
from discord import app_commands, SelectOption
from discord.ext import commands
import asyncio
import math
import ast
from icecream import ic
from discord.ui import View, Button, Select
import random

class Go(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "discord.db"
        self.item_generator = bot.get_cog('ItemFetch')
        self.stats_manager = self.bot.get_cog("StatsManager")
        self.data_manager = self.bot.get_cog("DataManager")
        self.go_market = self.bot.get_cog("GoMarket")
    
    @commands.hybrid_command(name="go", description="Go work, find a job, shop around, or gather items.")
    async def go(self, ctx):
        user_stats = await self.stats_manager.fetch_user_stats(ctx.author)
        all_jobs = await self.data_manager.get_data_of_type('jobs')
        user_jobs = await self.stats_manager.get_available_jobs(ctx.author)
        stats_manager = self.stats_manager
        random_job = []
        
        ic(all_jobs, random_job, user_jobs)
        
        ## Construct Job Embeds
        ### Get random job, return none if all jobs have been gotten
        if len(all_jobs) == len(user_jobs):
            random_job = None
        else:
            available_jobs = [job for job in all_jobs if job['name'] not in user_jobs]
            random_job = random.choice(available_jobs)
                
        available_jobs_data = []
        available_jobs_str = ""
        
        if user_stats['available_jobs']:
            for job in json.loads(user_stats['available_jobs']):
                job = await self.data_manager.find_data("jobs", job)
                available_jobs_data.append(job)
                
            for job_data in available_jobs_data:
                available_jobs_str += (f"{job_data['name']}: *{job_data['introduction']}*")
        
        job_overview_embed = discord.Embed(title='Job Menu',
                                           color=0x00D9FF)
        job_overview_embed.add_field(name="Search for Jobs", value=f"**{user_stats['profile_name']}** can search for a job.", inline=False)
        
        if user_stats['available_jobs']:
            job_overview_embed.add_field(name="Apply", value=f"**{user_stats['profile_name']}** can apply to work for up to three jobs.", inline=False)
                       
        if user_stats.get('job1') or user_stats.get('job2') or user_stats.get('job3') :
            job_overview_embed.add_field(name="Work", value=f"Allows **{user_stats['profile_name']}** to earn cash.", inline=False)

        def job_search_embed(time_gathering = 1):
            embed = discord.Embed(title=f"It's time for **{user_stats['profile_name']}** to find a job!", color=0x89CFF0, description=f"Select how long **{user_stats['profile_name']}** will search for a job.")

            item_bonus = time_gathering/2

            if time_gathering == 1:
                time_gathering_str = f"{time_gathering} hour"
            else:
                time_gathering_str = f"{time_gathering} hours"

            embed.add_field(name="Time Searching:", value=time_gathering_str)
            embed.add_field(name="Time Bonus:", value=f"x{item_bonus}")

            return embed
        def job_apply_embed():                
            embed = discord.Embed(title="Apply to up to 3 jobs at once.", description=available_jobs_str)
            return embed
        def job_apply_slot_embed():
            apply_slot_embed = discord.Embed(title="What slot will the job be applied to?")
            return apply_slot_embed
        def job_applied_embed(slot, job):
            job_applied_embed = discord.Embed(title=f"You applied {job['name']} to Job Slot `{slot}`!", 
                                              color=discord.Color.green(),
                                              description=f"**{user_stats['profile_name']}** can now start working in the `!go` menu!")
            return job_applied_embed
        def job_slot_embed():
            embed = discord.Embed(title="Which job will you be working?", 
                                  color=0x002FFF,
                                  description=f"**Slot 1: {user_stats['job1']}**\n**Slot 2: {user_stats['job2']}**\n**Slot 3: {user_stats['job3']}**")
            return embed
        
        def apply_job(slot, job):
            self.stats_manager.apply_job(slot, ctx.author, job)

        ## Construct Item Gathering Embed
        gather_embed = discord.Embed(title="Explore", color=0x00DD77, description=f"Where will **{user_stats['profile_name']}** explore?")

        gather_locations = await self.data_manager.get_data_of_type("item_gathering")
        
        for location in gather_locations:
            gather_embed.add_field(name=location['name'], value=location['description'])
            
        ## Construct Main Menu Embed
        main_embed = discord.Embed(title=f"**{user_stats['profile_name']}** stands just outside {user_stats['pronoun_possessive']} home.", 
                                   color=0x00DD77, 
                                   description=f"{user_stats['pronoun'].title()} could go to work or find a job, explore for items or shop at the user-led market.")

        def location_details_embed(location, time_gathering = 1):
            item_bonus = time_gathering/2
            
            cost = location.get('visit_cost')

            if location['base_hrs'] == 1:
                base_hrs_str = f"{location['base_hrs']} hour"
            else:
                base_hrs_str = f"{location['base_hrs']} hours"

            if time_gathering == 1:
                time_gathering_str = f"{time_gathering} hour"
            else:
                time_gathering_str = f"{time_gathering} hours"

            description = f"{location['description']}\n\nSelect how long **{user_stats['profile_name']}** will explore for."
            description += f"\n*It will cost **`{cost}` Coins** to explore this area.*" if cost else ""

            embed = discord.Embed(title=f"{location['name']}", 
                                  color=0x89CFF0, 
                                  description=description)

            embed.add_field(name="Time to Arrive:", value=base_hrs_str)
            embed.add_field(name="Time Gathering:", value=time_gathering_str)
            embed.add_field(name="Time to Return:", value=base_hrs_str)
            embed.add_field(name="Total Time:", value=f"*{time_gathering + (location['base_hrs'] * 2)} hours*")
            embed.add_field(name="Time Bonus:", value=f"x{item_bonus}")
            
            return embed
        
        def job_already_applied_embed():
            return discord.Embed(description="This job has already been applied to a slot!",
                                  color=discord.Color.red())

        class TimeSelectionView(View):
            def __init__(self, ctx, location, hours, parent_cog, job):
                self.main_embed = main_embed
                self.location = location
                self.hours = hours
                self.job = job
                self.parent_cog = parent_cog
                super().__init__(timeout=None)
                self.disable_buttons(hours)
                
            async def build_result_embed(self, interaction, hours) -> discord.Embed:
                raise NotImplementedError("Subclasses must implement build_result_embed()")

            async def build_details_embed(self, location, hours) -> discord.Embed:
                raise NotImplementedError("Subclasses must implement build_details_embed()")
                
            @discord.ui.button(label="Take", style=discord.ButtonStyle.blurple)
            async def accept_button(self, interaction: discord.Interaction, button: Button):
                result_embed = await self.build_result_embed(interaction, self.hours)
                await interaction.response.edit_message(embed=result_embed, view=None)

            @discord.ui.button(label="1/2 hrs", style=discord.ButtonStyle.grey)
            async def decrease_button(self, interaction: discord.Interaction, button: Button):
                self.hours = self.hours/2
                embed = await self.build_details_embed(location, self.hours)
                self.disable_buttons(self.hours)
                await interaction.response.edit_message(embed=embed, view=self)

            @discord.ui.button(label="x2 hrs", style=discord.ButtonStyle.grey)
            async def increase_button(self, interaction: discord.Interaction, button: Button):
                self.hours = self.hours*2
                embed = await self.build_details_embed(location, self.hours)
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

        class JobSearchView(TimeSelectionView):
            async def build_result_embed(self, interaction, hours) -> discord.Embed:
                hours = self.hours
                user_stats = await self.parent_cog.stats_manager.fetch_user_stats(interaction.user)

                random_job['type'] = 'job_search'
                random_job['chance'] = (15 * hours)
                random_job['job_name'] = random_job['name']
                random_job['name'] = 'Searching for a Job'

                eta = await self.parent_cog.stats_manager.update_activity(interaction, random_job, hours, cost=0)

                embed = discord.Embed(
                    title=f"{user_stats['profile_name']} went to search for a job!",
                    description=f"{user_stats['profile_name']} is traveling around the city to look for a job.",
                    color=discord.Color.gold()
                )
                embed.add_field(name="ETA", value=eta)
                embed.add_field(name="Time Bonus", value=f"x{hours / 2}")
                return embed
            
            async def build_details_embed(self, location, hours) -> discord.Embed:
                return job_search_embed(hours)
        
        async def working_job(interaction, job_data) -> discord.Embed:
            user_stats = await stats_manager.fetch_user_stats(interaction.user)
            
            ic(job_data)
            
            eta = await stats_manager.update_activity(interaction, job_data, job_data['hours'], cost=0)

            embed = discord.Embed(
                title=f"{user_stats['profile_name']} went to work at {job_data['name']}!",
                description=f"Rest assured, **{user_stats['profile_name']}** is hard at work.",
                color=discord.Color.gold()
            )
            
            embed.add_field(name="ETA", value=eta)
            embed.add_field(name="Time Working:", value=f"{job_data['hours']} hours")
            embed.add_field(name="Wage:", value=f"**{job_data['coins_change']}** coins")
            
            return embed
        
        async def work_confirmation(self, job):
            job_data = await self.parent_cog.data_manager.find_data('jobs', job)
            proficiency = await self.parent_cog.stats_manager.get_proficiency(ctx.author, job_data['proficiency'])
            story_progress_int = await self.parent_cog.stats_manager.get_job_progress(ctx.author.id, job_data)
            
            if story_progress_int+1 > len(job_data['results']):
                embed = discord.Embed(title = f"There's nothing for you here!",
                                      description = f"{job_data['name']} doesn't need you to work yet!\n\nCome back later...") 
                return embed
            
            result_data = job_data['results'][story_progress_int]
            
            result_text = result_data['text']
            hours = result_data['hours']
            coins_change = result_data['coins_change']
            xp_change = result_data['xp_change']
            is_promotion = result_data.get('is_promotion')
            promotion_title = result_data.get('promotion_title')
            
            job_data['type'] = 'job'
            
            job_data['result'] = result_text
            job_data['coins_change'] = coins_change
            job_data['xp_change'] = xp_change
            job_data['hours'] = hours
            job_data['is_promotion'] = is_promotion
            job_data['promotion_title'] = promotion_title
            
            if hours == 1:
                time_working_str = f"{hours} hour"
            else:
                time_working_str = f"{hours} hours"

            embed = discord.Embed(title=f"Go work at {job}!",
                                  color=0x3c00FF)
            embed.add_field(name="Time Working:", value=time_working_str)
            embed.add_field(name="Wage:", value=f"**{coins_change}** coins")
            
            class WorkConfirmation(View):
                def __init__(self):
                    self.main_embed = main_embed
                    self.nav_buttons = nav_buttons
                    super().__init__(timeout=None)
                    
                @discord.ui.button(label="Work", style=discord.ButtonStyle.green)
                async def work_button(self, interaction: discord.Interaction, button: Button):
                    embed = await working_job(interaction, job_data)
                    await interaction.response.edit_message(embed=embed, view=None)
    
                @discord.ui.button(label="Back", style=discord.ButtonStyle.red)
                async def back_button(self, interaction: discord.Interaction, button: Button):
                    await interaction.response.edit_message(embed=self.main_embed, view=nav_buttons)
              
            view = WorkConfirmation()
                
            return embed, view

        class JobWorkSlotView(View):
            def __init__(self, ctx, parent_cog):
                self.main_embed = main_embed
                self.nav_buttons = nav_buttons
                self.parent_cog = parent_cog
                super().__init__(timeout=None)
 
            if user_stats['job1']:
                @discord.ui.button(label=user_stats['job1'], style=discord.ButtonStyle.grey)
                async def slot1_button(self, interaction: discord.Interaction, button: Button):
                    embed, view = await work_confirmation(self, job=user_stats['job1'])
                    await interaction.response.edit_message(embed=embed, view=view)
                    
            if user_stats['job2']:
                @discord.ui.button(label=user_stats['job2'], style=discord.ButtonStyle.grey)
                async def slot2_button(self, interaction: discord.Interaction, button: Button):
                    embed, view = await work_confirmation(self, job=user_stats['job2'])
                    await interaction.response.edit_message(embed=embed, view=view)
                    
            if user_stats['job3']:
                @discord.ui.button(label=user_stats['job3'], style=discord.ButtonStyle.grey)
                async def slot3_button(self, interaction: discord.Interaction, button: Button): 
                    embed, view = await work_confirmation(self, job=user_stats['job3'])
                    await interaction.response.edit_message(embed=embed, view=view)
                
            @discord.ui.button(label="Back", style=discord.ButtonStyle.red)
            async def home_button(self, interaction: discord.Interaction, button: Button):
                await interaction.response.edit_message(embed=self.main_embed, view=nav_buttons)
 
        class JobApplySlotView(View):
            def __init__(self, ctx, parent_cog, job_data):
                self.main_embed = main_embed
                self.nav_buttons = nav_buttons
                self.job_data = job_data
                self.parent_cog = parent_cog
                super().__init__(timeout=None)
                self.job1 = user_stats.get('job1')
                self.job2 = user_stats.get('job2')
                self.job3 = user_stats.get('job3')
 
            @discord.ui.button(label="Slot 1", style=discord.ButtonStyle.grey)
            async def slot1_button(self, interaction: discord.Interaction, button: Button):
                if self.job1 == self.job_data['name'] or self.job2 == self.job_data['name'] or self.job3 == self.job_data['name']:
                    embed = job_already_applied_embed()
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                applied_embed = job_applied_embed(slot=1, job=self.job_data)
                apply_job(slot=1, job=self.job_data['name'])
                await interaction.response.edit_message(embed=applied_embed, view=None)
                
            @discord.ui.button(label="Slot 2", style=discord.ButtonStyle.grey)
            async def slot2_button(self, interaction: discord.Interaction, button: Button):
                if self.job1 == self.job_data['name'] or self.job2 == self.job_data['name'] or self.job3 == self.job_data['name']:
                    embed = job_already_applied_embed()
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                applied_embed = job_applied_embed(slot=2, job=self.job_data)
                apply_job(slot=2, job=self.job_data['name'])
                await interaction.response.edit_message(embed=applied_embed, view=None)
                
            @discord.ui.button(label="Slot 3", style=discord.ButtonStyle.grey)
            async def slot3_button(self, interaction: discord.Interaction, button: Button): 
                if self.job1 == self.job_data['name'] or self.job2 == self.job_data['name'] or self.job3 == self.job_data['name']:
                    embed = job_already_applied_embed()
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                applied_embed = job_applied_embed(slot=3, job=self.job_data)
                apply_job(slot=3, job=self.job_data['name'])
                await interaction.response.edit_message(embed=applied_embed, view=None)
                
            @discord.ui.button(label="Back", style=discord.ButtonStyle.red)
            async def home_button(self, interaction: discord.Interaction, button: Button):
                await interaction.response.edit_message(embed=self.main_embed, view=nav_buttons)
 
        class JobApplyView(View):
            def __init__(self, ctx, parent_cog):
                self.main_embed = main_embed
                self.nav_buttons = nav_buttons
                self.parent_cog = parent_cog
                super().__init__(timeout=None)

            for job in available_jobs_data:
                @discord.ui.button(label=job['name'], style=discord.ButtonStyle.grey)
                async def search_button(self, interaction: discord.Interaction, button: Button):
                    job_search_view = JobApplySlotView(ctx, parent_cog=self.parent_cog, job_data=job)
                    apply_slot_embed = job_apply_slot_embed()
                    await interaction.response.edit_message(embed=apply_slot_embed, view=job_search_view)
                    
            @discord.ui.button(label="Back", style=discord.ButtonStyle.red)
            async def home_button(self, interaction: discord.Interaction, button: Button):
                await interaction.response.edit_message(embed=self.main_embed, view=nav_buttons)
                
        class JobView(View):
            def __init__(self, ctx, nav_buttons, parent_cog):
                self.main_embed = main_embed
                self.nav_buttons = nav_buttons
                self.parent_cog = parent_cog
                super().__init__(timeout=None)

            if user_stats.get('job1') or user_stats.get('job2') or user_stats.get('job3') :
                @discord.ui.button(label="Work", style=discord.ButtonStyle.blurple)
                async def work_button(self, interaction: discord.Interaction, button: Button):
                    work_slot_view = JobWorkSlotView(ctx, self.parent_cog)
                    slot_embed = job_slot_embed()
                    await interaction.response.edit_message(embed=slot_embed, view=work_slot_view)
                
            if user_stats['available_jobs']:
                @discord.ui.button(label="Apply", style=discord.ButtonStyle.grey)
                async def apply_button(self, interaction: discord.Interaction, button: Button):
                    job_apply_view = JobApplyView(ctx, self.parent_cog)
                    apply_embed = job_apply_embed()
                    await interaction.response.edit_message(embed=apply_embed, view=job_apply_view)

            @discord.ui.button(label="Search", style=discord.ButtonStyle.grey)
            async def search_button(self, interaction: discord.Interaction, button: Button):
                if random_job is None:
                    embed = discord.Embed(title="You've found all the jobs!",
                                          description="Check back later when new job openings appear!",
                                          color=discord.Color.orange())
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                job_search_view = JobSearchView(ctx, location="Job Search", hours=1, parent_cog=self.parent_cog, job=None)
                search_embed = job_search_embed(1)
                await interaction.response.edit_message(embed=search_embed, view=job_search_view)
            
            @discord.ui.button(label="Back", style=discord.ButtonStyle.red)
            async def home_button(self, interaction: discord.Interaction, button: Button):
                await interaction.response.edit_message(embed=self.main_embed, view=nav_buttons)
                ## Navigate to the Main Menu

        class ExploreDetailView(TimeSelectionView):
            async def build_result_embed(self, interaction, hours) -> discord.Embed:
                location = self.location
                user_stats = await self.parent_cog.stats_manager.fetch_user_stats(interaction.user)
                
                cost = location.get('visit_cost')
                
                if user_stats['coins'] < cost:
                    embed = discord.Embed(
                        title=f"You don's have enough coins to go on this expedition!",
                        color=discord.Color.red()
                    )
                    interaction.response.send_message(embed=embed, ephemeral=True)

                if cost:
                    await self.parent_cog.stats_manager.modify_user_stat(ctx.author, 'coins', (cost * -1))
                
                eta = await self.parent_cog.stats_manager.update_activity(
                    interaction,
                    location,
                    (hours + (location['base_hrs'] * 2)),
                    0
                )

                embed = discord.Embed(
                    title=f"{user_stats['profile_name']} went to gather items!",
                    description=f"{user_stats['profile_name']} is traveling to **{location['name']}** to explore.",
                    color=discord.Color.gold()
                )
                embed.add_field(name="ETA", value=eta)
                embed.add_field(name="Time Bonus", value=f"x{hours / 2}")
                return embed

            async def build_details_embed(self, location, time_gathering = 1):
                return location_details_embed(location, time_gathering)
            
        class ExploreDropdown(Select):
            def __init__(self, parent_cog):
                self.parent_cog = parent_cog
                options = []
                for index, location in enumerate(gather_locations):
                    options.append(SelectOption(label=location['name'], description=location['description'][:100], value=str(index)))

                super().__init__(placeholder="Select a location to explore...", options=options, min_values=1, max_values=1)

            async def callback(self, interaction: discord.Interaction):
                if interaction.user.id != ctx.author.id:
                    await interaction.response.send_message("Sorry, this menu isn't for you.", ephemeral=True)
                    return
                
                index = int(self.values[0])

                embed = location_details_embed(gather_locations[index])

                detail_view = ExploreDetailView(ctx, location, 1, self.parent_cog, job=None)
                await interaction.response.edit_message(embed=embed, view=detail_view)

        class VendorDropdownView(View):
            def __init__(self, parent_cog):
                super().__init__(timeout=60)
                self.add_item(ExploreDropdown(parent_cog))

        class NavigationButtons(View):
            def __init__(self, ctx, gather_embed, parent_cog):
                self.gather_embed = gather_embed
                self.parent_cog = parent_cog
                super().__init__(timeout=None)

            @discord.ui.button(label="Explore", style=discord.ButtonStyle.grey, emoji="🌲")
            async def explore_button(self, interaction: discord.Interaction, button: Button):
                explore_view = VendorDropdownView(self.parent_cog)
                await interaction.response.edit_message(embed=self.gather_embed, view=explore_view)

            @discord.ui.button(label="Market", style=discord.ButtonStyle.grey, emoji="🛍️")
            async def expedition_button(self, interaction: discord.Interaction, button: Button):
                market_overview_embed, view = await self.parent_cog.go_market.market_overview_embed(ctx, self.parent_cog.bot.get_cog("GoMarket"), user_stats, message)
                await interaction.response.edit_message(embed=market_overview_embed, view=view)

            @discord.ui.button(label="Jobs", style=discord.ButtonStyle.grey, emoji="🛠️")
            async def job_button(self, interaction: discord.Interaction, button: Button):
                job_view = JobView(ctx, nav_buttons, self.parent_cog)
                await interaction.response.edit_message(embed=job_overview_embed, view=job_view)

        nav_buttons = NavigationButtons(ctx, gather_embed, self)
        message = await ctx.send(embed=main_embed, view=nav_buttons)
async def setup(bot):
    await bot.add_cog(Go(bot))