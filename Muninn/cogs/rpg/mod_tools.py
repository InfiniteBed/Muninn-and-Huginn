import sqlite3
import discord
from discord.ext import commands
from discord.ui import View, Button
import re

from icecream import ic

class ModTools(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.search = bot.get_cog('Search')
        self.data_manager = self.bot.get_cog("DataManager") # For Item and Expedition Info
        self.item_randomizer = self.bot.get_cog("ItemRandomizer") # For Item and Expedition Info
        self.user_manager = self.bot.get_cog("StatsManager") # For Item and Expedition Info

    @commands.command()
    async def give_item(self, ctx, type: str, item: str, user: str = None):
        if user is None:
            user = ctx.author
        else:
            user = await self.search.find_user(user, ctx.guild)
            if not user:
                await ctx.send("No profile found.")
                return
            
        item = await self.item_randomizer.generate_item(type, item)

        self.user_manager.add_to_user_inventory(user.id, item)

        await ctx.send(f"Added {item['name']} to inventory.")

    @commands.command()
    async def remove_item_index(self, ctx, index: int, user: str = None):
        if user is None:
            user = ctx.author
        else:
            user = await self.search.find_user(user, ctx.guild)
            if not user:
                await ctx.send("No profile found.")
                return
            
        item = self.user_manager.get_item_in_inventory(user.id, index)

        self.user_manager.remove_from_user_inventory(user.id, item)

        await ctx.send(f"Removed {item[0]['name']} from inventory.")
    
    @commands.command()
    async def find_data(self, ctx, type: str, item: str):
        item = await self.data_manager.find_data(type, item)
        await ctx.send(item)
    
    @commands.command()
    async def gen_item(self, ctx, type: str, item: str):
        item = await self.item_randomizer.generate_item(type, item)
        await ctx.send(item)

    @commands.command()
    async def job_prog(self, ctx, job_name: str):
        job_data = await self.data_manager.find_data('jobs', job_name)
        progress = await self.user_manager.get_job_progress(ctx.author.id, job_data)
        await ctx.send(progress)

    @commands.command()
    async def prog_inc(self, ctx, job_name: str):
        job_data = await self.data_manager.find_data('jobs', job_name)
        progress = await self.user_manager.job_progress_increase(ctx.author.id, job_data)
        await ctx.send(progress)
        
    @commands.command()
    async def for_job(self, ctx, job_name: str, progress: int = None):
        user_stats = await self.user_manager.fetch_user_stats(ctx.author)
        job_data = await self.data_manager.find_data('jobs', job_name)
        
        username = user_stats['profile_name']
        pclass = user_stats['class']
        
        def format_gendered(text, gender):
            pattern = re.compile(r'\[([^\[\]]+?)\]')
            gender_index = 0 if gender.lower() == 'm' else 1

            def replace(match):
                options = match.group(1).split('|')
                return options[gender_index]

            return pattern.sub(replace, text)
        
        ic(job_data['results'])
        
        if progress is None:
            for result in job_data['results']:
                result = str.format(result['text'], name=username, pclass=pclass)
                result = self.format_gendered(result, user_stats['gender_letter'])
                await ctx.send(result)
            return
                
        result = job_data['results'][progress]
        result = str.format(result['text'], name=username, pclass=pclass)
        result = format_gendered(result, user_stats['gender_letter'])
        
        if len(result) <= 2000:
            await ctx.send(result)
            return

        lines = result.split('\n')
        chunk = ""
        for line in lines:
            if len(chunk) + len(line) + 1 > 2000:
                await ctx.send(chunk)
                chunk = line + "\n"
            else:
                chunk += line + "\n"

        if chunk:
            await ctx.send(chunk)

    @commands.command()
    async def gen_items_HC(self, ctx):
        hardcoded_list = [
            {
                "name": "katana",
                "weight": 10
            },
            {
                "name": "steel boots",
                "weight": 1
            },
            {
                "name": "steel sword",
                "weight": 1
            },
        ]

        item = await self.item_randomizer.weighted_random_items(ctx, 'equipment', hardcoded_list)
        await ctx.send(item)

    @commands.command()
    async def remove_activity(self, ctx, user: str = None):
        if user is None:
            user = ctx.author
        else:
            user = await self.search.find_user(user, ctx.guild)
            if not user:
                await ctx.send("No profile found.")
                return
            
        conn = sqlite3.connect('discord.db')
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE stats SET activity = NULL WHERE user_id = ?", (user.id,))
            conn.commit()
            print(f"[DEBUG] Deleted expedition for user {user.id}")
        except sqlite3.Error as e:
            print(f"[ERROR] Failed to delete expedition from database: {e}")
        finally:
            conn.close()


async def setup(bot):
    await bot.add_cog(ModTools(bot))
