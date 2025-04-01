import discord
from discord.ext import commands
import sqlite3

class PinManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "huginn.db"
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pinned_messages (
                    guild_id INTEGER,
                    message_id INTEGER PRIMARY KEY,
                    channel_id INTEGER
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ignored_messages (
                    guild_id INTEGER,
                    message_id INTEGER PRIMARY KEY
                )
            """)
            conn.commit()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Check if the message is a system pin message
        if message.type == discord.MessageType.pins_add:
            try:
                # Optionally delete the pin notification message
                await message.delete()
                print(f"Deleted a pin notification in {message.channel.name}")
                
                # Get the most recent pinned message in the same channel
                pinned_messages = await message.channel.pins()
                if pinned_messages:
                    recent_pin = pinned_messages[0]  # Most recent pinned message

                    # Check if the message is already in the pinned_messages table
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT message_id FROM pinned_messages WHERE message_id = ? AND guild_id = ?", 
                                       (recent_pin.id, message.guild.id))
                        if cursor.fetchone():
                            # If the message is already in the pinned_messages table, move it to ignored_messages
                            cursor.execute("INSERT OR REPLACE INTO ignored_messages (guild_id, message_id) VALUES (?, ?)",
                                           (message.guild.id, recent_pin.id))
                            cursor.execute("DELETE FROM pinned_messages WHERE message_id = ? AND guild_id = ?", 
                                           (recent_pin.id, message.guild.id))
                            conn.commit()
                            print(f"Message {recent_pin.id} moved to ignored_messages table.")
                            await message.channel.send(f"Removed pin from random pins: {message.recent_pin.content}")
                            # React to the message with a pin emoji when removed from the database
                            await recent_pin.add_reaction("📌")
                            await recent_pin.remove_reaction("📌", self.bot.user)
                        else:
                            # Otherwise, add it to the pinned_messages table
                            cursor.execute("INSERT INTO pinned_messages (guild_id, message_id, channel_id) VALUES (?, ?, ?)",
                                           (message.guild.id, recent_pin.id, message.channel.id))
                            conn.commit()
                            print(f"Added message {recent_pin.id} to pinned_messages table.")
                            # React to the message with a pin emoji when added to the database
                            await recent_pin.add_reaction("📌")

                        # Now unpin the message to keep the database clean
                        try:
                            await recent_pin.unpin()
                            print(f"Unpinned message {recent_pin.id} in {message.channel.name}")
                        except discord.Forbidden:
                            print(f"Failed to unpin message {recent_pin.id} due to missing permissions.")
                        except discord.HTTPException as e:
                            print(f"Failed to unpin message {recent_pin.id}: {e}")

            except discord.Forbidden:
                print("Bot lacks permissions to delete messages.")
            except discord.HTTPException as e:
                print(f"Failed to delete pin notification: {e}")

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def migrate_pins(self, ctx, channel: discord.TextChannel = None):
        """Migrate existing pinned messages in a channel or all channels in the guild to the new system without unpinning them."""
        channels = [channel] if channel else ctx.guild.text_channels
        total_migrated = 0

        print("Attempting migration process...")
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for ch in channels:
                pinned_messages = await ch.pins()
                for message in pinned_messages:
                    cursor.execute("INSERT OR IGNORE INTO pinned_messages (guild_id, message_id, channel_id) VALUES (?, ?, ?)",
                                   (ctx.guild.id, message.id, message.channel.id))
                total_migrated += len(pinned_messages)
            conn.commit()
        
        await ctx.send(f"Migrated {total_migrated} pinned messages {'from ' + channel.mention if channel else 'from all channels'} to the database.")


    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def pin_count(self, ctx):
        """Shows the number of pinned messages in each channel of the guild."""
        pin_counts = {}
        
        # Fetch the count of pinned messages per channel from the database
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT channel_id, COUNT(*) FROM pinned_messages WHERE guild_id = ? GROUP BY channel_id", 
                           (ctx.guild.id,))
            rows = cursor.fetchall()
            for row in rows:
                channel_id, count = row
                channel = ctx.guild.get_channel(channel_id)
                if channel:
                    pin_counts[channel.name] = count
        
        # Prepare the embed to show pin counts
        embed = discord.Embed(
            title=f"Pinned Messages Count for {ctx.guild.name}",
            description="This is the number of pinned messages in each channel:",
            color=discord.Color.blue()
        )
        
        # Add fields for each channel's pin count
        if pin_counts:
            for channel_name, count in pin_counts.items():
                embed.add_field(name=channel_name, value=f"{count} pinned messages", inline=False)
        else:
            embed.add_field(name="No pinned messages", value="There are no pinned messages in this guild.", inline=False)
        
        # Send the embed as a response
        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def pin_refresh(self, ctx):
        """Refresh pin reactions for all messages in the pinned_messages table."""
        refreshed_count = 0

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT channel_id, message_id FROM pinned_messages WHERE guild_id = ?", (ctx.guild.id,))
            rows = cursor.fetchall()

        for channel_id, message_id in rows:
            channel = ctx.guild.get_channel(channel_id)
            if not channel:
                continue

            try:
                message = await channel.fetch_message(message_id)
                # Check if the bot has already reacted with the pin emoji
                if not any(reaction.emoji == "📌" and reaction.me for reaction in message.reactions):
                    await message.add_reaction("📌")
                    refreshed_count += 1
            except discord.NotFound:
                print(f"Message {message_id} not found in channel {channel_id}.")
            except discord.Forbidden:
                print(f"Missing permissions to fetch or react to message {message_id} in channel {channel_id}.")
            except discord.HTTPException as e:
                print(f"Failed to refresh pin reaction for message {message_id}: {e}")

        await ctx.send(f"Refreshed pin reactions for {refreshed_count} messages.")

async def setup(bot):
    await bot.add_cog(PinManagement(bot))
