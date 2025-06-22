import datetime
import yaml
import random
import sqlite3
import time
import os

import pytz # type:ignore

import discord  # type: ignore
from discord.ext import commands, tasks  # type: ignore

conn = sqlite3.connect("huginn.db")
c = conn.cursor()

GUILD_BLACKLIST = [1198144553383895150]

# Define Los Angeles timezone
la_timezone = pytz.timezone("America/Los_Angeles")

# Get current date to handle daylight saving time properly
def get_time(hour, minute=0):
    now = datetime.datetime.now(la_timezone)
    return la_timezone.localize(datetime.datetime(now.year, now.month, now.day, hour, minute))

# Times set in Los Angeles timezone, adjusted for DST
times = [
    get_time(17).timetz(),
]

class PromptDownvoteView(discord.ui.View):
    def __init__(self, prompt_data, prompt_index):
        super().__init__(timeout=3600)  # 1 hour timeout
        self.prompt_data = prompt_data
        self.prompt_index = prompt_index

    @discord.ui.button(label="👎 Downvote This Prompt", style=discord.ButtonStyle.red)
    async def downvote_prompt(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        
        # Load current responses data
        try:
            with open("responses.yaml", "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            await interaction.response.send_message("Error accessing prompt data.", ephemeral=True)
            return
        
        if "prompts" not in data or self.prompt_index >= len(data["prompts"]):
            await interaction.response.send_message("Prompt no longer exists.", ephemeral=True)
            return
        
        prompt = data["prompts"][self.prompt_index]
        
        # Check if user already downvoted
        if "downvoted_by" not in prompt:
            prompt["downvoted_by"] = []
        
        if user_id in prompt["downvoted_by"]:
            await interaction.response.send_message("You have already downvoted this prompt.", ephemeral=True)
            return
        
        # Add downvote
        prompt["downvoted_by"].append(user_id)
        if "downvotes" not in prompt:
            prompt["downvotes"] = 0
        prompt["downvotes"] += 1
        
        # Check if prompt should be removed (3+ downvotes)
        if prompt["downvotes"] >= 3:
            removed_prompt = data["prompts"].pop(self.prompt_index)
            await interaction.response.send_message(
                f"Prompt removed due to excessive downvotes:\n*\"{removed_prompt['text']}\"*", 
                ephemeral=True
            )
            print(f"Removed prompt due to downvotes: {removed_prompt['text']}")
        else:
            await interaction.response.send_message(
                f"Downvote recorded. ({prompt['downvotes']}/3 downvotes)", 
                ephemeral=True
            )
        
        # Save updated data
        with open("responses.yaml", "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, indent=2)

class random_prompt(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.my_task.start()
        self.check_new_prompts.start()  # Start the new prompt checking task

    def cog_unload(self):
        self.my_task.cancel()
        self.check_new_prompts.cancel()

    @tasks.loop(time=times)
    async def my_task(self):
        current_time = time.time()  # Get the current timestamp
        print(f"Current time: {current_time}")

        for guild in self.bot.guilds:
            try:
                print(f"Checking guild: {guild.name} (ID: {guild.id})")
                if guild.id in GUILD_BLACKLIST:
                    print(f"Guild {guild.name} is blacklisted, skipping.")
                    continue

                # Check if the last message was sent more than 30 minutes ago
                c.execute("SELECT last_message_time FROM guild_last_messages WHERE guild_id = ?", (guild.id,))
                last_message_time = c.fetchone()
                if last_message_time:
                    last_message = float(last_message_time[0])  # Ensure it's a float
                    time_diff = current_time - last_message
                    print(f"Time since last message in {guild.name}: {time_diff} seconds")
                    if time_diff < 600:  # 600 seconds = 10 minutes
                        print(f"Last message in {guild.name} was less than 10 minutes ago, skipping.")
                        continue

                # Pick a random prompt
                prompt_data = random.choice(self.bot.data.get("prompts", []))
                if not prompt_data:
                    print("No prompts available in responses.json")
                    continue

                prompt_text = prompt_data.get("text", "No prompt available")
                contributor = prompt_data.get("contributor", "Anonymous")
                
                # Find the index of this prompt for downvoting
                prompt_index = -1
                try:
                    for i, p in enumerate(self.bot.data.get("prompts", [])):
                        if p.get("text") == prompt_text and p.get("contributor") == contributor:
                            prompt_index = i
                            break
                except:
                    prompt_index = -1

                print(f"Selected prompt for {guild.name}: {prompt_text}")

                # Send the prompt as an embed with downvote button
                embed = discord.Embed(title=prompt_text, color=discord.Color.blue())
                embed.set_footer(text=f"Random Prompt | Suggested by: {contributor}")
                
                # Create view with downvote button
                view = PromptDownvoteView(prompt_data, prompt_index) if prompt_index >= 0 else None
                
                general_channel = discord.utils.get(guild.text_channels, name='general')
                if general_channel:
                    print(f"Sending prompt to {guild.name} in #general")
                    await general_channel.send(embed=embed, view=view)
                else:
                    print(f"No #general channel found in {guild.name}")

                # Update the last message time
                c.execute("REPLACE INTO guild_last_messages (guild_id, last_message_time) VALUES (?, ?)",
                          (guild.id, current_time))
                conn.commit()
                print(f"Updated last message time for {guild.name}")

            except sqlite3.DatabaseError as db_err:
                print(f"Database error for guild {guild.name}: {db_err}")
            except discord.DiscordException as discord_err:
                print(f"Discord API error for guild {guild.name}: {discord_err}")
            except Exception as e:
                print(f"Unexpected error for guild {guild.name}: {e}")

    @tasks.loop(minutes=5)  # Check every 5 minutes for new prompts
    async def check_new_prompts(self):
        """Check shared communication file for new prompts from Muninn"""
        try:
            shared_comm_path = "/mnt/Lake/Starboard/Discord/shared_communication.yaml"
            
            if not os.path.exists(shared_comm_path):
                return
            
            # Load shared communication data
            with open(shared_comm_path, 'r', encoding='utf-8') as f:
                comm_data = yaml.safe_load(f) or {}
            
            if "communication" not in comm_data or "pending_prompts" not in comm_data["communication"]:
                return
            
            pending_prompts = comm_data["communication"]["pending_prompts"]
            
            if not pending_prompts:
                return
            
            # Load current responses
            with open("responses.yaml", "r", encoding="utf-8") as f:
                responses_data = yaml.safe_load(f)
            
            if "prompts" not in responses_data:
                responses_data["prompts"] = []
            
            # Add all pending prompts
            added_count = 0
            for prompt in pending_prompts:
                if prompt.get("status") == "pending_addition":
                    # Create clean prompt object for responses.yaml
                    clean_prompt = {
                        "text": prompt.get("text", ""),
                        "contributor": prompt.get("contributor", "Anonymous"),
                        "downvotes": 0,
                        "downvoted_by": []
                    }
                    
                    # Check for duplicates
                    duplicate = False
                    for existing_prompt in responses_data["prompts"]:
                        if existing_prompt.get("text", "").strip().lower() == clean_prompt["text"].strip().lower():
                            duplicate = True
                            break
                    
                    if not duplicate:
                        responses_data["prompts"].append(clean_prompt)
                        added_count += 1
                        print(f"Added new prompt from Muninn: {clean_prompt['text'][:50]}...")
            
            if added_count > 0:
                # Save updated responses
                with open("responses.yaml", "w", encoding="utf-8") as f:
                    yaml.dump(responses_data, f, default_flow_style=False, allow_unicode=True, indent=2)
                
                # Clear the pending prompts from shared communication
                comm_data["communication"]["pending_prompts"] = []
                comm_data["communication"]["last_processed"] = datetime.datetime.utcnow().isoformat()
                
                with open(shared_comm_path, 'w', encoding='utf-8') as f:
                    yaml.dump(comm_data, f, default_flow_style=False, allow_unicode=True, indent=2)
                
                print(f"Successfully added {added_count} new prompts from Muninn")
                
                # Reload bot data if available
                if hasattr(self.bot, 'data'):
                    self.bot.data = responses_data
                
        except Exception as e:
            print(f"Error checking for new prompts: {e}")

    @check_new_prompts.before_loop
    async def before_check_new_prompts(self):
        await self.bot.wait_until_ready()

    @commands.command()
    async def prompt_stats(self, ctx):
        """View statistics about current prompts"""
        try:
            with open("responses.yaml", "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            await ctx.send("Error accessing prompt data.")
            return
        
        if "prompts" not in data:
            await ctx.send("No prompts found.")
            return
        
        prompts = data["prompts"]
        total_prompts = len(prompts)
        
        # Count prompts by downvotes
        no_downvotes = len([p for p in prompts if p.get("downvotes", 0) == 0])
        one_downvote = len([p for p in prompts if p.get("downvotes", 0) == 1])
        two_downvotes = len([p for p in prompts if p.get("downvotes", 0) == 2])
        
        # Most downvoted prompts (but not removed)
        most_downvoted = sorted([p for p in prompts if p.get("downvotes", 0) > 0], 
                               key=lambda x: x.get("downvotes", 0), reverse=True)[:5]
        
        # Count contributors
        contributors = {}
        for prompt in prompts:
            contributor = prompt.get("contributor", "Anonymous")
            contributors[contributor] = contributors.get(contributor, 0) + 1
        
        top_contributors = sorted(contributors.items(), key=lambda x: x[1], reverse=True)[:5]
        
        embed = discord.Embed(title="Random Prompt Statistics", color=discord.Color.blue())
        embed.add_field(name="Total Prompts", value=total_prompts, inline=True)
        embed.add_field(name="No Downvotes", value=no_downvotes, inline=True)
        embed.add_field(name="1 Downvote", value=one_downvote, inline=True)
        embed.add_field(name="2 Downvotes", value=two_downvotes, inline=True)
        
        if top_contributors:
            contributor_text = "\n".join([f"{name}: {count}" for name, count in top_contributors])
            embed.add_field(name="Top Contributors", value=contributor_text, inline=False)
        
        if most_downvoted:
            downvoted_text = "\n".join([f"({p.get('downvotes', 0)}) {p.get('text', '')[:50]}..." 
                                       for p in most_downvoted])
            embed.add_field(name="Most Downvoted Prompts", value=downvoted_text, inline=False)
        
        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def remove_prompt(self, ctx, *, prompt_text: str):
        """Manually remove a prompt by text (bot owner only)"""
        try:
            with open("responses.yaml", "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            await ctx.send("Error accessing prompt data.")
            return
        
        if "prompts" not in data:
            await ctx.send("No prompts found.")
            return
        
        # Find and remove the prompt
        original_count = len(data["prompts"])
        data["prompts"] = [p for p in data["prompts"] if prompt_text.lower() not in p.get("text", "").lower()]
        new_count = len(data["prompts"])
        
        if original_count == new_count:
            await ctx.send("No prompts found matching that text.")
            return
        
        # Save updated data
        with open("responses.yaml", "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, indent=2)
        
        removed_count = original_count - new_count
        await ctx.send(f"Removed {removed_count} prompt(s) containing '{prompt_text}'.")

    @commands.command()
    async def list_prompts(self, ctx, page: int = 1):
        """List all current prompts with pagination"""
        try:
            with open("responses.yaml", "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            await ctx.send("Error accessing prompt data.")
            return
        
        if "prompts" not in data:
            await ctx.send("No prompts found.")
            return
        
        prompts = data["prompts"]
        per_page = 10
        total_pages = (len(prompts) + per_page - 1) // per_page
        
        if page < 1 or page > total_pages:
            await ctx.send(f"Invalid page number. Please use a page between 1 and {total_pages}.")
            return
        
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_prompts = prompts[start_idx:end_idx]
        
        embed = discord.Embed(
            title=f"Random Prompts (Page {page}/{total_pages})", 
            color=discord.Color.blue()
        )
        
        for i, prompt in enumerate(page_prompts, start_idx + 1):
            text = prompt.get("text", "No text")[:100]
            if len(prompt.get("text", "")) > 100:
                text += "..."
            
            contributor = prompt.get("contributor", "Anonymous")
            downvotes = prompt.get("downvotes", 0)
            
            embed.add_field(
                name=f"{i}. {text}",
                value=f"By: {contributor} | Downvotes: {downvotes}",
                inline=False
            )
        
        embed.set_footer(text=f"Use !list_prompts <page> to see other pages")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(random_prompt(bot))
