import discord
from discord.ext import commands
import asyncio
import threading
import json
from icecream import ic

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
            action_embed = discord.Embed(title=f"{player.display_name}'s Actions", color=discord.Color.blue())

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

                
            action_embed.add_field(name="Actions", value="\n".join([f"**{action['name']}**: {action['description']}" for action in actions]) or "No actions available", inline=False)
            action_embed.add_field(name="Armor", value=armor or "No armor equipped", inline=False)
            action_embed.add_field(name="Items", value=items or "No items available", inline=False)

            return actions, action_embed

        class ActionSelection(discord.ui.View):
            def __init__(self, actions, player):
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
                        await interaction.response.edit_message(content=f"You selected: {action['name']}", view=None)
                        self.stop()

                    button.callback = callback
                    self.add_item(button)

        # Player 1 action
        actions, player1_embed = await get_player_info(player1, player1_stats)
        view1 = ActionSelection(actions, player1)
        player1_message = await thread.send(embed=player1_embed, view=view1)
        await view1.wait()  # Wait for user interaction
        if not view1.selected_action:
            await thread.send(f"{player1.mention} did not select an action in time!")
            return
        player1_action = view1.selected_action  # Retrieve selected action

        # Player 2 action
        actions, player2_embed = await get_player_info(player2, player2_stats)
        view2 = ActionSelection(actions, player2)
        player2_message = await thread.send(embed=player2_embed, view=view2)
        await view2.wait()  # Wait for user interaction
        if not view2.selected_action:
            await thread.send(f"{player2.mention} did not select an action in time!")
            return
        player2_action = view2.selected_action  # Retrieve selected action

        # Calculate damage
        player1_attack = player1_action['damage']
        player2_attack = player2_action['damage']
        player1_defense = player1_stats['defense']  # Assuming player1_stats has a defense value
        player2_defense = player2_stats['defense']  # Assuming player2_stats has a defense value

        damage_to_player2 = max((player1_attack) - (player2_defense), 0)
        damage_to_player1 = max((player2_attack) - (player1_defense), 0)

        # Modify stats
        print(f"Damage Calculation - {player1.display_name} deals {damage_to_player2}, {player2.display_name} deals {damage_to_player1}")
        await self.stats_manager.modify_user_stat(player1, 'health', -damage_to_player1) # Update Database
        await self.stats_manager.modify_user_stat(player2, 'health', -damage_to_player2) # Update Database
        player1_stats['health'] = player1_stats['health'] - damage_to_player1 # Update Local
        player2_stats['health'] = player2_stats['health'] - damage_to_player2 # Update Local

        print(f"Updated Health - {player1.display_name}: {player1_stats['health']}, {player2.display_name}: {player2_stats['health']}")

        # Send battle update
        battle_embed = discord.Embed(title="Battle Update", color=discord.Color.blue())
        battle_embed.add_field(name="Attack Results", value=f"{player1.mention} dealt **{damage_to_player2}** damage to {player2.mention}!\n"
                                                            f"{player2.mention} dealt **{damage_to_player1}** damage to {player1.mention}!", inline=False)
        battle_embed.add_field(name=f"{player1.display_name}'s Health", value=f"{player1_stats['health']} HP", inline=True)
        battle_embed.add_field(name=f"{player2.display_name}'s Health", value=f"{player2_stats['health']} HP", inline=True)
        await thread.send(embed=battle_embed)

        # Check if anyone has won
        print("Checking for battle winner")
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
            victory_embed.add_field(name=f"{player1.display_name}'s Final Health", value=f"{player1_stats['health']} HP", inline=True)
            victory_embed.add_field(name=f"{player2.display_name}'s Final Health", value=f"{player2_stats['health']} HP", inline=True)
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
            victory_embed.add_field(name=f"{player1.display_name}'s Final Health", value=f"{player1_stats['health']} HP", inline=True)
            victory_embed.add_field(name=f"{player2.display_name}'s Final Health", value=f"{player2_stats['health']} HP", inline=True)
            await thread.send(embed=victory_embed)

    async def cog_unload(self):
        for player1, player2 in list(self.active_battles):
            self.active_battles.discard((player1, player2))
            channel = self.bot.get_channel(1300535207371472998)  # Replace with the appropriate channel reference
            if channel:
                await channel.send(f"Battle between {player1.mention} and {player2.mention} has been forcibly stopped due to a reload.")

async def setup(bot):
    await bot.add_cog(Battle(bot))