import discord
from discord.ext import commands
import asyncio
import threading
import json
import random
import time
from icecream import ic
import math

class Battle(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.search = bot.get_cog('Search')  # For User Find
        self.utils = bot.get_cog('Utils')  # For Player's Icon
        self.stats_manager = self.bot.get_cog("StatsManager") 
        self.data_manager = self.bot.get_cog("DataManager")  
        self.active_battles = set()

    @commands.command()
    async def battle(self, ctx, user: str = None):
        print("Battle command invoked")
        if user is None:
            await ctx.send("I don't know who you want to battle!")
            return
        else:
            user = await self.search.find_user(user, ctx.guild)
            print(f"Challenging user: {user}")
            if not user:
                await ctx.send("No person found.")
                return
            
        if user == ctx.author:
            await ctx.send("You can't fight yourself!")
            return

        # Check if either user has 0 health
        author_stats = await self.stats_manager.fetch_user_stats(ctx.author)
        user_stats = await self.stats_manager.fetch_user_stats(user)
        if author_stats['health'] <= 0:
            await ctx.send(f"{ctx.author.mention}, you cannot battle with 0 health!")
            return
        if user_stats['health'] <= 0:
            await ctx.send(f"{user.mention} cannot battle with 0 health!")
            return
        
        embed = discord.Embed(title="Battle Challenge!", description=f"{user.mention}, you've been challenged by {ctx.author.mention}!", color=discord.Color.red())
        embed.add_field(name="Instructions", value="Respond with `!accept` to begin or `!cancel` to deny the challenge.")
        await ctx.send(embed=embed)
        
        def check(confirm_message):
            return confirm_message.author == user and confirm_message.channel == ctx.channel

        try:
            while True:
                confirm_message = await self.bot.wait_for("message", check=check, timeout=600)  # Waits for 10 minutes
                if confirm_message.content.startswith("!cancel"):
                    await ctx.send(f"Battle cancelled by {user.display_name}.")
                    return
                elif confirm_message.content.startswith("!accept"):
                    # Re-check health before starting the battle
                    user_stats = await self.stats_manager.fetch_user_stats(user)
                    if user_stats['health'] <= 0:
                        await ctx.send(f"{user.mention} cannot battle with 0 health!")
                        return
                    break
        except asyncio.TimeoutError:
            await ctx.send(f"No response received in time from {user.display_name}!")
            return

        print("User accepted the battle")
        thread = await ctx.channel.create_thread(
            name=f"Battle: {ctx.author.display_name} vs {user.display_name}",
            type=discord.ChannelType.public_thread,
            auto_archive_duration=60  # Set to 1 minute
        )
        await thread.send("Battle starting!")
        await self.start_battle(thread, ctx.author, user)

    async def start_battle(self, thread, player1, player2):
        print("Starting battle thread")
        self.active_battles.add((player1, player2))
        player1_stats = await self.stats_manager.fetch_user_stats(player1)
        player2_stats = await self.stats_manager.fetch_user_stats(player2)
        async def battle_loop():
            while player1_stats['health'] > 0 and player2_stats['health'] > 0:
                await self.prompt_actions(thread, player1, player2, player1_stats, player2_stats)
            print("Exiting battle loop!")

        # Start the battle loop asynchronously
        await battle_loop()
        self.active_battles.discard((player1, player2))

    async def prompt_actions(self, thread, player1, player2, player1_stats, player2_stats):
        print("Prompting actions")
        async def get_player_info(player, player_stats):
            print(f"Fetching inventory for {player.display_name}")

            embed_color, avatar_image, has_custom_image = await self.utils.get_avatar_color_and_image(player)
            pfp = discord.File(f"/usr/src/bot/profile_images/{player.id}.png", filename="image.png") if has_custom_image else None
            
            action_embed = discord.Embed(title=f"{player_stats['profile_name']}'s Actions", color=discord.Color.blue())
            action_embed.set_thumbnail(url="attachment://image.png" if has_custom_image else player.avatar.url)

            item_slots = [
                'head',
                'upper',
                'lower',
                'feet',
                'hand_left',
                'hand_right'
            ]

            # Loop through each item in equipped items, finding actions
            actions = []
            armor = ""
            items = ""

            for slot in item_slots:
                if not player_stats[slot]:
                    continue
                
                if slot == 'hand_left' and not player_stats[slot]:
                    item_data = await self.data_manager.find_data('equipment', 'Right Fist')
                elif slot == 'hand_right' and player_stats[slot] is None:
                    item_data = await self.data_manager.find_data('equipment', 'Left Fist')
                else:
                    item = json.loads(player_stats[slot])
                    item_data = await self.data_manager.find_data(item['type'], item['name'])

                if 'actions' in item_data and isinstance(item_data['actions'], list):
                    actions.extend(item_data['actions'])  # Ensure actions are appended correctly
                if 'base_defense' in item_data:
                    armor += f"**{item_data['name']}**: +{item_data['base_defense']} Defense\n"
                if 'base_heal' in item_data:
                    items += f"**{item_data['name']}**: Heals {item_data['base_heal']} HP\n"
                    
            ic(actions)
        

            action_embed.add_field(name="Actions", 
                                   value="\n".join(
                                       [f"**{action['name']}** – *{action['type']}*\n{action['description']}\n" for action in actions]
                                       ) or "No actions available", 
                                   inline=False)
            action_embed.add_field(name="Armor", value=armor or "No armor equipped", inline=False)
            action_embed.add_field(name="Items", value=items or "No items available", inline=False)

            return actions, action_embed, pfp

        async def selected_action_embed(player, player_name):
            embed_color, avatar_image, has_custom_image = await self.utils.get_avatar_color_and_image(player)
            embed = discord.Embed(title=f"{player_name} made a decision!")
            embed.set_thumbnail(url="attachment://image.png" if has_custom_image else player.avatar.url)
            return embed

        class ActionSelection(discord.ui.View):
            def __init__(self, actions, player, player_stats):
                super().__init__(timeout=600)  # Set a timeout for the view
                self.actions = actions
                self.player = player
                self.selected_action = None

                for action in actions:
                    button = discord.ui.Button(label=action['name'], style=discord.ButtonStyle.blurple)
                    
                    async def callback(interaction: discord.Interaction, action=action):
                        if interaction.user != self.player:
                            await interaction.response.send_message("It's not your turn!", ephemeral=True)
                            return
                        self.selected_action = action
                        embed = await selected_action_embed(player, player_stats['profile_name'])
                        await interaction.response.edit_message(embed=embed, view=None)
                        self.stop()

                    button.callback = callback
                    self.add_item(button)

        # Player 1 action
        actions, player1_embed, pfp = await get_player_info(player1, player1_stats)
        view1 = ActionSelection(actions, player1, player1_stats)
        player1_message = await thread.send(embed=player1_embed, view=view1, file=pfp)
        await view1.wait()  # Wait for user interaction
        if not view1.selected_action:
            await thread.send(f"{player1.mention}, please make an action!")
            return
        player1_action = view1.selected_action  # Retrieve selected action

        # Player 2 action
        actions, player2_embed, pfp = await get_player_info(player2, player2_stats)
        view2 = ActionSelection(actions, player2, player2_stats)
        player2_message = await thread.send(embed=player2_embed, view=view2, file=pfp)
        await view2.wait()  # Wait for user interaction
        if not view2.selected_action:
            await thread.send(f"{player2.mention}, please make an action!")
            return
        player2_action = view2.selected_action  # Retrieve selected action
        
        text = ""
        
        # Calculate Values
        action1_strength = player1_action['strength']
        action2_strength = player2_action['strength']
        
        action1_type = player1_action['type']
        action2_type = player2_action['type']
        
        damage_to_player1 = 0
        damage_to_player2 = 0
        
        # Both Players Attack...
        if action1_type in ['Physical Offense', 'Magic Offense'] and action2_type in ['Physical Offense', 'Magic Offense']:
            p1_strength_advantage = max((action2_strength - action1_strength) - (player2_stats['defense'] + player2_stats['defense_boost']), 0)
            p2_strength_advantage = max((action1_strength - action2_strength) - (player1_stats['defense'] + player1_stats['defense_boost']), 0)

            damage_to_player1 = math.ceil(p1_strength_advantage)
            damage_to_player2 = math.ceil(p2_strength_advantage)
            if damage_to_player1 == damage_to_player2:
                text = "Both combatants' weapons clashed together, but neither came out on top! Both left unscathed."
            elif damage_to_player1 > 0: 
                text = f"Both combatants' weapons clashed together!\n{player1.display_name} took **{damage_to_player1} damage!**"
            elif damage_to_player2 > 0: 
                text = f"Both combatants' weapons clashed together!\n{player2.display_name} took **{damage_to_player2} damage!**"
        
        # Both Players Defend...
        elif action1_type in ['Physical Defense', 'Magic Defense'] and action2_type in ['Physical Defense', 'Magic Defense']:
            text = "Both combatants went on the defensive!\nUnsurprisingly, **nothing happened.**"
            return
        
        def defense_win(attacker_stats, defender_stats, attack_strength, defense_strength, defense_is_magical):
            damage_to_defender = max((attack_strength - (2 * defense_strength)) - (defender_stats['defense'] + defender_stats['defense_boost']), 1)
            if defense_is_magical:
                text = f"{defender_stats['profile_name']}'s magical defence dulled {attacker_stats['profile_name']}'s attack!\n{attacker_stats['profile_name']} dealt **{damage_to_defender} damage**!"
            else:
                text = f"{defender_stats['profile_name']}'s defence dulled {attacker_stats['profile_name']}'s attack!\n{attacker_stats['profile_name']} dealt **{damage_to_defender} damage**!" 
            return damage_to_defender, text
        
        def attack_win(attacker_stats, defender_stats, attack_strength, defense_strength, attack_is_magical):
            damage_to_defender = max(((2 * attack_strength) - defense_strength) - (defender_stats['defense'] + defender_stats['defense_boost']), 1)
            if attack_is_magical:
                text = f"{attacker_stats['profile_name']}'s magical offensive won out against {defender_stats['profile_name']}'s defenses!\n{attacker_stats['profile_name']} dealt **{damage_to_defender} damage**!"
            else:
                text = f"{attacker_stats['profile_name']}'s brute force won out against {defender_stats['profile_name']}'s magical shielding!\n{attacker_stats['profile_name']} dealt **{damage_to_defender} damage**!" 
            return damage_to_defender, text
        
        # Defense Wins...
            ## magic defense beats magic attack
        if action1_type == 'Magic Defense' and action2_type == 'Magic Offense':
            damage_to_player1, text = defense_win(player2_stats, player1_stats, action2_strength, action1_strength, True)
            
        elif action2_type == 'Magic Defense' and action1_type == 'Magic Offense':
            damage_to_player2, text = defense_win(player1_stats, player2_stats, action1_strength, action2_strength, True)
            
            ## phys defense beats phys attack
        elif action1_type == 'Physical Defense' and action2_type == 'Physical Offense':
            damage_to_player1, text = defense_win(player2_stats, player1_stats, action2_strength, action1_strength, False)
            
        elif action2_type == 'Physical Defense' and action1_type == 'Physical Offense':
            damage_to_player2, text = defense_win(player1_stats, player2_stats, action1_strength, action2_strength, False)
            
        # Attack Wins...
            ## magic attack beats phys defense
        elif action1_type == 'Magic Offense' and action2_type == 'Physical Defense':
            damage_to_player2, text = attack_win(player1_stats, player2_stats, action1_strength, action2_strength, True)
            
        elif action2_type == 'Magic Offense' and action1_type == 'Physical Defense':
            damage_to_player1, text = attack_win(player2_stats, player1_stats, action2_strength, action1_strength, True)
            
            ## phys attack beats magic defense
        elif action1_type == 'Physical Offense' and action2_type == 'Magic Defense':
            damage_to_player2, text = attack_win(player1_stats, player2_stats, action1_strength, action2_strength, False)
            
        elif action2_type == 'Physical Offense' and action1_type == 'Magic Defense':
            damage_to_player1, text = attack_win(player2_stats, player1_stats, action2_strength, action1_strength, False)
            
        
        # Modify stats
        await self.stats_manager.modify_user_stat(player1, 'health', -damage_to_player1) # Update Database
        await self.stats_manager.modify_user_stat(player2, 'health', -damage_to_player2) # Update Database
        player1_stats['health'] = player1_stats['health'] - damage_to_player1 # Update Local
        player2_stats['health'] = player2_stats['health'] - damage_to_player2 # Update Local

        # Send battle update
        battle_embed = discord.Embed(title="Battle Update", 
                                     color=discord.Color.red(), 
                                     description=f"{player1_stats['profile_name']} used **{player1_action['name']}**! *(strength {action1_strength})*\n"
                                                 f"***\"{random.choice(player1_action['lines'])}\"***\n\n"
                                                 f"{player2_stats['profile_name']} used **{player2_action['name']}**! *(strength {action2_strength})*\n"
                                                 f"***\"{random.choice(player2_action['lines'])}\"***\n\n\n"
                                                 f"{text}",
                                     )
        battle_embed.add_field(name=f"{player1_stats['profile_name']}'s Health", value=f"{player1_stats['health']} HP", inline=True)
        battle_embed.add_field(name=f"{player2_stats['profile_name']}'s Health", value=f"{player2_stats['health']} HP", inline=True)
        await thread.send(embed=battle_embed)

        time.sleep(5)

        # Check if anyone has won
        if player1_stats['health'] <= 0:
            # Steal 20% of player1's coins
            player1_coins = player1_stats.get('coins', 0)
            stolen_coins = int(player1_coins * 0.2)
            await self.stats_manager.modify_user_stat(player1, 'coins', -stolen_coins)
            await self.stats_manager.modify_user_stat(player2, 'coins', stolen_coins)

            victory_embed = discord.Embed(
                title="Battle Over!",
                description=f"{player2.mention} wins!\n{player2.mention} stole {stolen_coins} coins from {player1.mention}!",
                color=discord.Color.green()
            )
            victory_embed.add_field(name=f"{player1_stats['profile_name']}'s Final Health", value=f"{max(0, player1_stats['health'])} HP", inline=True)
            victory_embed.add_field(name=f"{player2_stats['profile_name']}'s Final Health", value=f"{max(0, player2_stats['health'])} HP", inline=True)
            await thread.send(embed=victory_embed)

        elif player2_stats['health'] <= 0:
            # Steal 20% of player2's coins
            player2_coins = player2_stats.get('coins', 0)
            stolen_coins = int(player2_coins * 0.2)
            await self.stats_manager.modify_user_stat(player2, 'coins', -stolen_coins)
            await self.stats_manager.modify_user_stat(player1, 'coins', stolen_coins)

            victory_embed = discord.Embed(
                title="Battle Over!",
                description=f"{player1.mention} wins!\n{player1.mention} stole {stolen_coins} coins from {player2.mention}!",
                color=discord.Color.green()
            )
            victory_embed.add_field(name=f"{player1_stats['profile_name']}'s Final Health", value=f"{max(0, player1_stats['health'])} HP", inline=True)
            victory_embed.add_field(name=f"{player2_stats['profile_name']}'s Final Health", value=f"{max(0, player2_stats['health'])} HP", inline=True)
            await thread.send(embed=victory_embed)

    async def cog_unload(self):
        for player1, player2 in list(self.active_battles):
            self.active_battles.discard((player1, player2))
            channel = self.bot.get_channel(1300535207371472998)  # Replace with the appropriate channel reference
            if channel:
                await channel.send(f"Battle between {player1.mention} and {player2.mention} has been forcibly stopped due to a reload.")

async def setup(bot):
    await bot.add_cog(Battle(bot))