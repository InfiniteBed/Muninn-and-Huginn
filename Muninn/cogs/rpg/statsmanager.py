import sqlite3
import discord
from discord.ext import commands
import json

class StatsManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def fetch_user_stats(self, user):
        conn = sqlite3.connect('discord.db')
        c = conn.cursor()

        c.execute('SELECT health, health_max, defense, attack, level, activity, coins FROM stats WHERE user_id = ?', (user.id,))
        stats_data = c.fetchone()

        c.execute('SELECT class, gender, alignment, race, name, bio, ability_scores FROM profiles WHERE user_id = ?', (user.id,))
        profile_data = c.fetchone()

        c.execute('SELECT user_id, head, upper, lower, feet, hand_left, hand_right FROM equipped_items WHERE user_id = ?', (user.id,))
        equipped_armor = c.fetchone()

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
        health, health_max, defense, attack, level, activity, coins = stats_data
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
            hand_left = "{\"name\": \"Left Fist\"}"
        if not hand_left:
            hand_left = "{\"name\": \"Right Fist\"}"

        return {
            'profile_name': profile_name,
            'class': profile_class,
            'alignment': profile_alignment,
            'race': profile_race,
            'bio': profile_bio,
            'pronoun': pronoun,
            'pronoun_possessive': pronoun_possessive,
            'ability_scores': ability_scores,
            'scores_display': scores_display,
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
    
    async def equip(self, ctx, slot: str, item: dict):
        user = ctx.author
        user_data = await self.fetch_user_stats(user)
        inventory = user_data['inventory']

        if user_data is None:
            await ctx.send("User data not found.")
            return

        if item not in inventory:
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
        inventory.remove(item)

        # Equip new item
        c.execute(f'UPDATE equipped_items SET {slot} = ? WHERE user_id = ?', (json.dumps(item), user.id))

        # Return old item to inventory if applicable
        if current_equipped:
            inventory.append(json.loads(current_equipped))

        c.execute("UPDATE inventory SET inventory = ? WHERE user_id = ?", (json.dumps(inventory), user.id))

        conn.commit()
        conn.close()

        await ctx.send(f"Equipped {item['name']} in {slot}.")

    @commands.command()
    async def unequip(self, ctx, slot: str):
        user = ctx.author
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

        await ctx.send(f"Unequipped {equipped_item} from {slot.title()}.")


async def setup(bot):
    await bot.add_cog(StatsManager(bot))
