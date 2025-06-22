import discord
from discord.ext import commands
import sqlite3
import logging
import matplotlib.pyplot as plt
import io
from collections import Counter
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

c = sqlite3.connect("discord.db")
cursor = c.cursor()

class DebugProfile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    def create_bar_chart(self, data, title, xlabel, ylabel):
        # Set style for consistent look
        plt.style.use('bmh')  # Using 'bmh' style which is clean and modern
        
        # Create figure with smaller standard size
        plt.figure(figsize=(8, 4))
        
        # Create bar plot with consistent color
        bars = plt.bar(range(len(data)), sorted(data, reverse=True), color='#2C82D1')
        
        # Customize the plot
        plt.title(title, pad=15)
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.grid(True, axis='y', alpha=0.3)
        
        # Add some padding to prevent label cutoff
        plt.margins(x=0.01)
        plt.tight_layout()
        
        # Save plot to bytes buffer with higher DPI for better quality
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100)
        buf.seek(0)
        plt.close()
        return buf

    def create_comparative_chart(self, data_dict, title, xlabel, ylabel):
        # Set style for consistent look
        plt.style.use('bmh')
        
        # Create figure with smaller standard size
        plt.figure(figsize=(10, 5))
        
        # Calculate positions for bars
        users = list(data_dict.keys())
        values = [data_dict[user] for user in users]
        pos = range(len(users))
        
        # Create bar plot
        bars = plt.bar(pos, values, color='#2C82D1', width=0.6)
        
        # Customize the plot
        plt.title(title, pad=15)
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.grid(True, axis='y', alpha=0.3)
        
        # Set user names as x-tick labels, rotated for better readability
        plt.xticks(pos, users, rotation=45, ha='right')
        
        # Add value labels on top of bars
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.1f}',
                    ha='center', va='bottom')
        
        # Adjust layout to prevent label cutoff
        plt.tight_layout()
        
        # Save plot to bytes buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100)
        buf.seek(0)
        plt.close()
        return buf

    async def get_user_data(self, guild_id, user_id, limit=100):
        cursor.execute('SELECT * FROM user_activity WHERE guild_id = ? AND user_id = ? ORDER BY timestamp DESC LIMIT ?', 
                      (guild_id, user_id, limit))
        return cursor.fetchall()

    @commands.command(name='statistics')
    async def statistics(self, ctx, user: str = None):
        if user is None:
            user = ctx.author
        else:
            user = await self.bot.get_cog('Search').find_user(user, ctx.guild)
            if not user:
                await ctx.send("No profile found.")
                return

        guild_id = ctx.guild.id

        try:
            cursor.execute(f'SELECT * FROM user_activity WHERE guild_id = ? AND user_id = ? ORDER BY timestamp DESC LIMIT 100', (guild_id, user.id))
            user_data = cursor.fetchall()

            message_count = len(user_data)
            if not message_count:
                await ctx.send(f"No stats found for user with ID {user.id}.")
                return

            # Extract data for graphs
            word_counts = [row[7] for row in user_data]
            msg_lengths = [row[5] for row in user_data]
            # Safely convert timestamps - skip any invalid ones
            timestamps = []
            for row in user_data:
                try:
                    if isinstance(row[3], str):
                        timestamps.append(datetime.fromisoformat(row[3]))
                    else:
                        timestamps.append(row[3])
                except (ValueError, TypeError):
                    logger.warning(f"Could not parse timestamp: {row[3]}")
                    continue

            user_id, friendly_name = user_data[0][1], user_data[0][2]

            # Create graphs
            word_count_graph = self.create_bar_chart(word_counts, f"Word Count Distribution - {friendly_name}", "Messages", "Word Count")
            length_graph = self.create_bar_chart(msg_lengths, f"Message Length Distribution - {friendly_name}", "Messages", "Character Count")

            # Create embed with stats
            embed = discord.Embed(title=f"Stats for {friendly_name}", color=discord.Color.green())
            embed.add_field(name="User ID", value=user.id, inline=False)
            embed.add_field(name="Friendly Name", value=friendly_name, inline=False)
            embed.add_field(name="Message Count", value=message_count, inline=False)
            embed.add_field(name="Avg. Message Length", value=round(sum(msg_lengths) / message_count, 1), inline=False)
            embed.add_field(name="Avg. Words per Message", value=round(sum(word_counts) / message_count, 1), inline=False)
            embed.add_field(name="Avg. Letters per Word", value=round(sum(msg_lengths) / sum(word_counts), 1) if sum(word_counts) else 0, inline=False)
            embed.set_thumbnail(url=user.avatar.url)

            # Send embed and graphs
            await ctx.send(embed=embed)
            await ctx.send(file=discord.File(word_count_graph, 'word_counts.png'))
            await ctx.send(file=discord.File(length_graph, 'message_lengths.png'))

        except Exception as e:
            logger.error(f"Error fetching user stats: {e}")
            await ctx.send(f"Error fetching user stats: {e}")

    @commands.command(name='compare_words')
    async def compare_words(self, ctx, *users: str):
        """Compare average words per message between users"""
        if len(users) < 2:
            await ctx.send("Please mention at least 2 users to compare!")
            return

        data = {}
        guild_id = ctx.guild.id

        for user_mention in users:
            user = await self.bot.get_cog('Search').find_user(user_mention, ctx.guild)
            if not user:
                await ctx.send(f"Could not find user: {user_mention}")
                continue

            user_data = await self.get_user_data(guild_id, user.id)
            if not user_data:
                await ctx.send(f"No data found for user: {user.name}")
                continue

            word_counts = [row[7] for row in user_data]
            avg_words = sum(word_counts) / len(word_counts)
            data[user.name] = avg_words

        if len(data) < 2:
            await ctx.send("Not enough valid users to compare!")
            return

        graph = self.create_comparative_chart(data, 
                                           "Average Words per Message Comparison",
                                           "Users", 
                                           "Average Words")
        await ctx.send(file=discord.File(graph, 'word_comparison.png'))

    @commands.command(name='compare_length')
    async def compare_length(self, ctx, *users: str):
        """Compare average message length between users"""
        if len(users) < 2:
            await ctx.send("Please mention at least 2 users to compare!")
            return

        data = {}
        guild_id = ctx.guild.id

        for user_mention in users:
            user = await self.bot.get_cog('Search').find_user(user_mention, ctx.guild)
            if not user:
                await ctx.send(f"Could not find user: {user_mention}")
                continue

            user_data = await self.get_user_data(guild_id, user.id)
            if not user_data:
                await ctx.send(f"No data found for user: {user.name}")
                continue

            msg_lengths = [row[5] for row in user_data]
            avg_length = sum(msg_lengths) / len(msg_lengths)
            data[user.name] = avg_length

        if len(data) < 2:
            await ctx.send("Not enough valid users to compare!")
            return

        graph = self.create_comparative_chart(data, 
                                           "Average Message Length Comparison",
                                           "Users", 
                                           "Average Characters")
        await ctx.send(file=discord.File(graph, 'length_comparison.png'))

    @commands.command(name='compare_activity')
    async def compare_activity(self, ctx, *users: str):
        """Compare message count between users"""
        if len(users) < 2:
            await ctx.send("Please mention at least 2 users to compare!")
            return

        data = {}
        guild_id = ctx.guild.id

        for user_mention in users:
            user = await self.bot.get_cog('Search').find_user(user_mention, ctx.guild)
            if not user:
                await ctx.send(f"Could not find user: {user_mention}")
                continue

            user_data = await self.get_user_data(guild_id, user.id)
            if not user_data:
                await ctx.send(f"No data found for user: {user.name}")
                continue

            data[user.name] = len(user_data)

        if len(data) < 2:
            await ctx.send("Not enough valid users to compare!")
            return

        graph = self.create_comparative_chart(data, 
                                           "Message Count Comparison",
                                           "Users", 
                                           "Number of Messages")
        await ctx.send(file=discord.File(graph, 'activity_comparison.png'))

async def setup(bot):
    await bot.add_cog(DebugProfile(bot))
