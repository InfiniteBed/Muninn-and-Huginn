import sqlite3
import discord
from discord.ext import commands
import json
from icecream import ic
from datetime import datetime, timedelta, timezone
import random
import math
import time
import asyncio

class StatsManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.item_randomizer = self.bot.get_cog("ItemRandomizer") # For Item and Expedition Info

    async def fetch_user_stats(self, user):
        conn = sqlite3.connect('discord.db')
        c = conn.cursor()

        c.execute('SELECT health, health_max, defense, attack, level, activity, coins, job1, job2, job3, found_jobs FROM stats WHERE user_id = ?', (user.id,))
        stats_data = c.fetchone()

        c.execute('SELECT class, gender, alignment, race, name, bio, ability_scores FROM profiles WHERE user_id = ?', (user.id,))
        profile_data = c.fetchone()

        c.execute('SELECT user_id, head, upper, lower, feet, hand_left, hand_right FROM equipped_items WHERE user_id = ?', (user.id,))
        equipped_armor = c.fetchone()

        c.execute("SELECT * FROM proficiencies WHERE user_id = ?", (user.id,))
        raw_inventory = (c.fetchone())[0]

        c.execute("SELECT author, baking, brewing, carpentry, cleaning, coachman, cooking, cupbearing, farming, fishing, floristry, gardening, guarding, glassblowing, healing, husbandry, innkeeping, knighthood, leadership, masonry, metalworking, painting, pottery, royalty, sculpting, smithing, spinning, stablekeeping, tailoring, teaching, vigilance FROM proficiencies WHERE user_id = ?", (user.id,))
        proficiencies = (c.fetchone())[0]

        c.execute("SELECT inventory FROM inventory WHERE user_id = ?", (user.id,))
        raw_inventory = (c.fetchone())[0]

        #Process Inventory Data
        if raw_inventory is None:
            inventory = 'empty'
        elif raw_inventory: 
            inventory = json.loads(raw_inventory)
        conn.close()

        if not profile_data and not stats_data:
            return
        
        #Retrieve Variables from Dictionaries
        profile_class, profile_gender, profile_alignment, profile_race, profile_name, profile_bio, ability_scores_str = profile_data
        health, health_max, defense, attack, level, activity, coins, job1, job2, job3, available_jobs = stats_data
        _, head, upper, lower, feet, hand_left, hand_right = equipped_armor

        #Process Bio
        if profile_bio is None:
            profile_bio = "*Set a bio with !setbio*"
        
        #Process Gender
        pronoun, pronoun_possessive = ("he", "his") if profile_gender == "M" else ("she", "her")

        #Convert Ability Scores
        ability_scores = eval(ability_scores_str)
        scores_display = "\n".join(f"{stat}: {score}" for stat, score in ability_scores.items())

        # Merge base values with boosts
        health_display = f"{health}/{health_max}"
        defense_display = f"{defense}"
        attack_display = f"{attack}"

        # Ensure users can Still fight without weapons
        if not hand_right:
            hand_right = "{\"name\": \"Right Fist\"}"
        if not hand_left:
            hand_left = "{\"name\": \"Left Fist\"}"

        return {
            'profile_name': profile_name,
            'class': profile_class,
            'alignment': profile_alignment,
            'race': profile_race,
            'bio': profile_bio,
            'gender_letter': profile_gender,
            'pronoun': pronoun,
            'pronoun_possessive': pronoun_possessive,
            'ability_scores': ability_scores,
            'scores_display': scores_display,
            "job1": job1,
            "job2": job2,
            "job3": job3,
            'available_jobs': available_jobs,
            'proficiencies': proficiencies,
            'health': health,
            'health_max': health_max,
            'health_display': health_display,
            'defense': defense,
            'defense_display': defense_display,
            'attack': attack,
            'attack_display': attack_display,
            'level': level,
            'activity': activity,
            'coins': coins,
            'inventory': inventory,
            'head': head,
            'upper': upper,
            'lower': lower,
            'feet': feet,
            'hand_left': hand_left,
            'hand_right': hand_right
        }

    async def modify_user_stat(self, user, stat, amount):
        conn = sqlite3.connect('discord.db')
        c = conn.cursor()

        c.execute(f'SELECT {stat}, health_max FROM stats WHERE user_id = ?', (user.id,))
        current_value, health_max = c.fetchone()

        if stat == 'health':
            # Ensure health cannot increase when deducting health
            if amount < 0:
                new_value = max(0, current_value + amount)
            else:
                new_value = min(current_value + amount, health_max)
        else:
            new_value = max(0, current_value + amount)

        c.execute(f'UPDATE stats SET {stat} = ? WHERE user_id = ?', (new_value, user.id))
        conn.commit()
        conn.close()
        
    async def modify_ability_score(self, user, stat, amount, action='modify'):
        """
        Modify a user's ability score by adding, subtracting, or retrieving the value.

        :param user: The user whose ability score is to be modified.
        :param stat: The name of the ability score to modify (e.g., 'Strength').
        :param amount: The amount to add or subtract (use positive values for addition, negative for subtraction).
        :param action: The action to perform ('modify' to modify or 'retrieve' to just fetch the value).
        """
        conn = sqlite3.connect('discord.db')
        c = conn.cursor()

        # Fetch current ability scores
        c.execute('SELECT ability_scores FROM profiles WHERE user_id = ?', (user.id,))
        profile_data = c.fetchone()
        
        if not profile_data:
            return None

        ability_scores_str = profile_data[0]
        ability_scores = eval(ability_scores_str)

        # Retrieve ability score if action is 'retrieve'
        if action == 'retrieve':
            return ability_scores.get(stat, None)

        # Modify the ability score if action is 'modify'
        if stat in ability_scores:
            ability_scores[stat] = max(0, ability_scores[stat] + amount)
        else:
            return None

        # Save the modified ability scores back to the database
        c.execute('UPDATE profiles SET ability_scores = ? WHERE user_id = ?', (str(ability_scores), user.id))
        conn.commit()
        conn.close()

    async def set_user_armor(self, user, slot, item):
        conn = sqlite3.connect('discord.db')
        c = conn.cursor()

        c.execute(f'UPDATE equipment SET {slot} = ? WHERE user_id = ?', (item, user.id))
        conn.commit()
        conn.close()
    
    async def equip_from_inventory(self, ctx, user_id, user_data, slot: str, item_data: dict):
        inventory = user_data['inventory']

        if user_data is None:
            await ctx.send("User data not found.")
            return

        if item_data not in inventory:
            await ctx.send("Item not in inventory.")
            return

        valid_slots = ["head", "upper", "lower", "feet", "hand_left", "hand_right"]
        if slot not in valid_slots:
            await ctx.send("Invalid equipment slot.")
            return

        current_equipped = user_data.get(slot)

        conn = sqlite3.connect('discord.db')
        c = conn.cursor()

        # Remove item from inventory
        inventory.remove(item_data)

        # Equip new item
        c.execute(f'UPDATE equipped_items SET {slot} = ? WHERE user_id = ?', (json.dumps(item_data), user_id))

        # Return old item to inventory if applicable
        if current_equipped and 'Fist' not in current_equipped:
            inventory.append(json.loads(current_equipped))

        c.execute("UPDATE inventory SET inventory = ? WHERE user_id = ?", (json.dumps(inventory), user_id))

        conn.commit()
        conn.close()

        print(f"Equipped {item_data['name']} in {slot}.")

    def remove_from_user_inventory(self, user_id, item_data):
        ic(item_data['name'], user_id)

        conn = sqlite3.connect('discord.db')
        cursor = conn.cursor()

        #Check if inventotry is empty, then skip if empty.
        cursor.execute("SELECT inventory FROM inventory WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()

        if len(result) < 1:
            print("Nothing to remove from user's inventory!")
            return
        
        user_inventory = json.loads(result[0])

        #Remove item from inventory
        user_inventory.remove(item_data)

        ic(user_inventory)

        #Plant back into database
        cursor.execute("INSERT OR REPLACE INTO inventory (user_id, inventory) VALUES (?, ?)", (user_id, json.dumps(user_inventory)))
        conn.commit()
        conn.close()

    async def unequip_from_inventory(self, ctx, user, slot: str):
        user_data = await self.fetch_user_stats(user)

        if user_data is None:
            await ctx.send("User data not found.")
            return

        slot_aliases = {
            "torso": "upper", "chest": "upper", "body": "upper",
            "legs": "lower", "pants": "lower", "trousers": "lower",
            "feet": "feet", "shoes": "feet", "boots": "feet",
            "left hand": "hand_left", "lh": "hand_left",
            "right hand": "hand_right", "rh": "hand_right",
            "helmet": "head", "hat": "head"
        }

        slot = slot_aliases.get(slot.lower(), slot)

        valid_slots = ["head", "upper", "lower", "feet", "hand_left", "hand_right"]
        if slot not in valid_slots:
            await ctx.send("Invalid equipment slot.")
            print(f"Invalid equipment slot.\nExpected {valid_slots}, got {slot}")
            return

        equipped_item = user_data.get(slot)

        if not equipped_item:
            await ctx.send(f"No item equipped in {slot}.")
            return

        # Ensure inventory is properly loaded from JSON
        raw_inventory = user_data['inventory']
        
        if isinstance(raw_inventory, str):  
            try:
                inventory = json.loads(raw_inventory)  # Convert string to list
            except json.JSONDecodeError:
                inventory = []  # If JSON is corrupted, reset to an empty list
        else:
            inventory = raw_inventory if isinstance(raw_inventory, list) else []

        # Add unequipped item back to inventory
        inventory.append(json.loads(equipped_item))

        conn = sqlite3.connect('discord.db')
        c = conn.cursor()

        # Unequip item
        c.execute(f'UPDATE equipped_items SET {slot} = NULL WHERE user_id = ?', (user.id,))

        # Update inventory (store it back as JSON string)
        await ctx.send(json.dumps(inventory))
        c.execute("UPDATE inventory SET inventory = ? WHERE user_id = ?", (json.dumps(inventory), user.id))

        conn.commit()
        conn.close()

        print(f"Unequipped {equipped_item} from {slot.title()}.")

    def add_to_user_inventory(self, user_id, item_data):
        ic(item_data['name'], user_id)

        conn = sqlite3.connect('discord.db')
        cursor = conn.cursor()

        #Check if inventotry is empty, then skip if empty. theres definitely a waaaaay better way to do this
        cursor.execute("SELECT user_id FROM inventory WHERE inventory IS NULL")
        data = cursor.fetchall()

        if len(data) < 1:
            cursor.execute("SELECT inventory FROM inventory WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            ic(result)
            user_inventory = json.loads(result[0])

        for id in data:
            if id[0] == user_id:
                user_inventory = []
                break
            else:
                cursor.execute("SELECT inventory FROM inventory WHERE user_id = ?", (user_id,))
                result = cursor.fetchone()
                ic(result)
                user_inventory = json.loads(result[0])

        user_inventory.append(item_data)

        cursor.execute("INSERT OR REPLACE INTO inventory (user_id, inventory) VALUES (?, ?)", (user_id, json.dumps(user_inventory)))
        conn.commit()
        conn.close()

    def get_item_in_inventory(self, user_id, index):
        conn = sqlite3.connect('discord.db')
        cursor = conn.cursor()

        #Check if inventotry is empty, then skip if empty.
        cursor.execute("SELECT inventory FROM inventory WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()

        return json.loads(result[index])
    
    async def calculate_activity_results(self, interaction, activity):
        item_bonus = activity.get('item_bonus', 1)
        item_results = []
        
        if activity.get('type') == 'job':
            return activity
        
        if activity.get('type') == 'job_search':
            if random.random() < activity['chance']:  
                activity['got_job'] = True
            else:          
                activity['got_job'] = False
                
            return activity

        if 'skill_test' not in activity:
            for item in activity['item_pool']:
                if random.random() < item['chance_to_appear']:
                    std_deviation = item['std_deviation']

                    item_data = await self.item_randomizer.generate_item(item['type'], item['name'])

                    deviation = random.randint(-std_deviation, std_deviation)
                    item_count = math.ceil(float(item['std_amount'] + deviation) * item_bonus)

                    for i in range(item_count):
                        item_results.append(item_data)
                    
                    print("Generated activity :)")
        else:
            pass
            ## IMPLEMENT OR DIE
            ## (based off job skills)

        activity['item_results'] = item_results
        return activity
    
    async def activity_dm(self, interaction, user_stats, hours):
        await asyncio.sleep(hours*60*60)
        
        embed = discord.Embed(title=f"{user_stats['profile_name']} has completed an activity!",
                              description=f"Go into {interaction.guild.name} to see your results!")
        
        await interaction.user.send(embed=embed)
        
        return
    
    async def update_activity(self, interaction, activity, duration_hours, cost: int = 0):
        # The reward pool will consist of high, medium, and low luck results. This  will predetermine the results, and then store them
        user_stats = await self.fetch_user_stats(interaction.user)

        # Check if the user already has an activity
        if user_stats['activity']:
            await interaction.response.send_message(f"{user_stats['profile_name']} is already busy doing something else!")
            return

        if user_stats['coins'] < cost:
            await interaction.response.send_message(f"You do not have enough coins to do this! You need {cost} coins.")
            return

        # Deduct the cost
        await self.modify_user_stat(interaction.user, 'coins', -cost)

        resulting_activity = await self.calculate_activity_results(interaction, activity)

        # Calculate the end time based on the expedition's duration
        end_time = datetime.now(timezone.utc)  # Use timezone-aware datetime
        end_time += timedelta(hours=duration_hours)
        end_time_str = end_time.strftime('%Y-%m-%d %H:%M:%S')
        activity['end_time'] = end_time_str

        conn = sqlite3.connect('discord.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE stats SET activity = ? WHERE user_id = ?', (json.dumps(resulting_activity), interaction.user.id))
        conn.commit()
        conn.close()       
        
        asyncio.create_task(self.activity_dm(interaction, user_stats, hours=duration_hours))
    
        # Save the updated activity to the user
        return end_time_str
    
    async def get_users_proficiency_by_id(self, user_id, proficiency):
        query = f"SELECT {proficiency} FROM proficiencies WHERE user_id = ?"
        conn = sqlite3.connect('discord.db')
        c = conn.cursor()
        result = c.execute(query, (user_id,)).fetchone()[0]
        conn.close()
        return result
    
    async def get_proficiency(self, user, proficiency):
        query = f"SELECT {proficiency} FROM proficiencies WHERE user_id = ?"
        conn = sqlite3.connect('discord.db')
        c = conn.cursor()
        result = c.execute(query, (user.id,)).fetchone()[0]
        conn.close()
        return result
    
    async def proficency_increase(self, user, proficiency, amount: int):
        query = f"SELECT {proficiency} FROM proficiencies WHERE user_id = ?"
        execute = f"UPDATE proficiencies SET {proficiency} = ? WHERE user_id = ?"
        conn = sqlite3.connect('discord.db')
        c = conn.cursor()
        c.execute(query, (user.id,))

        proficiency_value = float((c.fetchone())[0])
        proficiency_value = max(0, proficiency_value + float(amount))
        
        c.execute(execute, (proficiency_value, user.id,))
        conn.commit()
        conn.close()
        
    def init_users_job_progress(self, user_id, job_data):
        insertion = {job_data['name']: {"name": job_data['name'],"progress": 0}}
        
        conn = sqlite3.connect('discord.db')
        c = conn.cursor()
        c.execute('''
            REPLACE INTO job_progress (user_id, progress)
            VALUES (?, ?)
        ''', (user_id, json.dumps(insertion)))
        
        conn.commit()
        conn.close()
    
    def job_progress_add_job(self, user_id, job_data):
        conn = sqlite3.connect('discord.db')
        c = conn.cursor()
        c.execute("SELECT progress FROM job_progress WHERE user_id = ?", (user_id,))
        result = c.fetchone()
        
        if not result or result[0] == None:
            self.init_users_job_progress(user_id, job_data)
            return
        
        data = json.loads(result[0])
        
        data[job_data['name']] = {"name": job_data['name'], "progress": 0}
        
        c.execute('''
            REPLACE INTO job_progress (user_id, progress)
            VALUES (?, ?)
        ''', (user_id, json.dumps(data)))
        
        conn.commit()
        conn.close()
        
        return data
    
    async def job_progress_increase(self, user_id, job_data):
        progress_int = await self.get_job_progress(user_id, job_data)
        job_name = job_data['name']
        
        conn = sqlite3.connect('discord.db')
        c = conn.cursor()
        c.execute("SELECT progress FROM job_progress WHERE user_id = ?", (user_id,))
        data = json.loads(c.fetchone()[0])

        data[job_name] = {"name": job_name, "progress": progress_int+1}
        
        c.execute('''
            REPLACE INTO job_progress (user_id, progress)
            VALUES (?, ?)
        ''', (user_id, json.dumps(data)))

        conn.commit()
        conn.close()
        
        return data
        
    async def get_job_progress(self, user_id, job_data):
        job_name = job_data['name']
        
        conn = sqlite3.connect('discord.db')
        c = conn.cursor()
        c.execute("SELECT progress FROM job_progress WHERE user_id = ?", (user_id,))
        result = c.fetchone()
        
        if not result or result[0] == None:
            self.init_users_job_progress(user_id, job_data)
            return 0

        user_progress_data = json.loads(result[0])
        job_progress_data = user_progress_data.get(job_name)
        
        if not job_progress_data:
            self.job_progress_add_job(user_id, job_data)
            return 0
            
        progress = job_progress_data['progress']
    
        return progress

    async def get_available_jobs(self, user):
        conn = sqlite3.connect('discord.db')
        c = conn.cursor()
        c.execute("SELECT found_jobs FROM stats WHERE user_id = ?", (user.id,))
        result = c.fetchone()
        
        if not result or result[0] == None:
            found_jobs = []
        else:
           found_jobs = json.loads(result[0])  # c
            
        conn.commit()
        conn.close()
        
        return found_jobs
            
    async def add_available_job(self, ctx, user, activity_name):
        conn = sqlite3.connect('discord.db')
        c = conn.cursor()
        c.execute("SELECT found_jobs FROM stats WHERE user_id = ?", (user.id,))
        result = c.fetchone()
        
        if not result or result[0] == None:
            found_jobs = []
        else:
           found_jobs = json.loads(result[0])  # c
            
        found_jobs.append(activity_name)
            
        c.execute("UPDATE stats SET found_jobs = ? WHERE user_id = ?", (json.dumps(found_jobs), user.id,))
        conn.commit()
        conn.close()

    def apply_job(self, slot, user, job_name):
        query = f"SELECT job{slot} FROM stats WHERE user_id = ?"
        execute = f"UPDATE stats SET job{slot} = ? WHERE user_id = ?"
        
        conn = sqlite3.connect('discord.db')
        c = conn.cursor()
        c.execute(query, (user.id,))
            
        c.execute(execute, (job_name, user.id,))
        conn.commit()
        conn.close()        

    @commands.command()
    @commands.is_owner()
    async def prof_inc(self, ctx, proficiency, amount):
        await self.proficency_increase(ctx.author, proficiency, amount)
        
async def setup(bot):
    await bot.add_cog(StatsManager(bot))
