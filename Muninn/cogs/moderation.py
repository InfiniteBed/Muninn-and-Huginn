import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from typing import Optional

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="purge", description="Delete messages from the channel")
    @app_commands.describe(
        amount="Number of messages to delete (1-100)",
        up_to_id="Delete all messages up to this message ID (most recent first)"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge_messages(
        self, 
        interaction: discord.Interaction, 
        amount: Optional[int] = None, 
        up_to_id: Optional[str] = None
    ):
        """Delete messages from the channel either by amount or up to a specific message ID"""
        
        # Validate input
        if amount is None and up_to_id is None:
            await interaction.response.send_message(
                "❌ You must specify either `amount` or `up_to_id`.", 
                ephemeral=True
            )
            return
        
        if amount is not None and up_to_id is not None:
            await interaction.response.send_message(
                "❌ You can only specify either `amount` OR `up_to_id`, not both.", 
                ephemeral=True
            )
            return
        
        if amount is not None and (amount < 1 or amount > 100):
            await interaction.response.send_message(
                "❌ Amount must be between 1 and 100.", 
                ephemeral=True
            )
            return

        # Defer the response since deletion might take a while
        await interaction.response.defer(ephemeral=True)
        
        try:
            channel = interaction.channel
            deleted_count = 0
            
            if amount is not None:
                # Delete X most recent messages
                deleted_messages = await channel.purge(limit=amount)
                deleted_count = len(deleted_messages)
                
            elif up_to_id is not None:
                # Validate message ID format
                try:
                    target_message_id = int(up_to_id)
                except ValueError:
                    await interaction.followup.send(
                        "❌ Invalid message ID format. Please provide a valid message ID.", 
                        ephemeral=True
                    )
                    return
                
                # Check if the target message exists
                try:
                    target_message = await channel.fetch_message(target_message_id)
                except discord.NotFound:
                    await interaction.followup.send(
                        "❌ Message with that ID not found in this channel.", 
                        ephemeral=True
                    )
                    return
                except discord.HTTPException as e:
                    await interaction.followup.send(
                        f"❌ Error fetching message: {e}", 
                        ephemeral=True
                    )
                    return
                
                # Delete messages from most recent up to the target message
                messages_to_delete = []
                async for message in channel.history(limit=None):
                    if message.id == target_message_id:
                        break
                    messages_to_delete.append(message)
                
                if not messages_to_delete:
                    await interaction.followup.send(
                        "❌ No messages found newer than the specified message ID.", 
                        ephemeral=True
                    )
                    return
                
                # Discord bulk delete has limitations, so we need to handle this carefully
                if len(messages_to_delete) <= 100:
                    # Use bulk delete for efficiency (works for messages < 14 days old)
                    try:
                        await channel.delete_messages(messages_to_delete)
                        deleted_count = len(messages_to_delete)
                    except discord.HTTPException:
                        # Fall back to individual deletion if bulk delete fails
                        for message in messages_to_delete:
                            try:
                                await message.delete()
                                deleted_count += 1
                                await asyncio.sleep(0.5)  # Rate limit protection
                            except discord.HTTPException:
                                continue
                else:
                    # For large amounts, delete in chunks
                    for i in range(0, len(messages_to_delete), 100):
                        chunk = messages_to_delete[i:i+100]
                        try:
                            await channel.delete_messages(chunk)
                            deleted_count += len(chunk)
                        except discord.HTTPException:
                            # Fall back to individual deletion for this chunk
                            for message in chunk:
                                try:
                                    await message.delete()
                                    deleted_count += 1
                                    await asyncio.sleep(0.5)
                                except discord.HTTPException:
                                    continue
                        await asyncio.sleep(1)  # Pause between chunks
            
            # Send confirmation
            embed = discord.Embed(
                title="✅ Messages Deleted",
                description=f"Successfully deleted **{deleted_count}** message(s).",
                color=discord.Color.green()
            )
            embed.set_footer(text=f"Requested by {interaction.user.display_name}")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Log the action
            print(f"[MODERATION] {interaction.user} deleted {deleted_count} messages in #{channel.name}")
            
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to delete messages in this channel.", 
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ An error occurred while deleting messages: {str(e)}", 
                ephemeral=True
            )
            print(f"[MODERATION ERROR] {e}")

    @app_commands.command(name="purgemessages", description="Delete a specific number of recent messages")
    @app_commands.describe(
        count="Number of messages to delete (1-100)"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge_messages_count(self, interaction: discord.Interaction, count: int):
        """Delete a specific number of recent messages"""
        
        if count < 1 or count > 100:
            await interaction.response.send_message(
                "❌ Count must be between 1 and 100.", 
                ephemeral=True
            )
            return
        
        # Use the purge command internally
        await self.purge_messages(interaction, amount=count)

    @purge_messages.error
    @purge_messages_count.error
    async def moderation_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Error handler for moderation commands"""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ You need the 'Manage Messages' permission to use this command.", 
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ An unexpected error occurred.", 
                ephemeral=True
            )
            print(f"[MODERATION ERROR] {error}")

    # Traditional command aliases for purge functionality
    @commands.command(name='purge')
    @commands.has_permissions(manage_messages=True)
    async def purge_traditional(self, ctx, amount: int = None, *, up_to_id: str = None):
        """Traditional command version of purge
        
        Usage:
        !purge 10 - Delete 10 messages
        !purge up_to_id:1234567890 - Delete messages up to that ID
        """
        
        # Parse up_to_id from message if provided in format "up_to_id:123456"
        if up_to_id and up_to_id.startswith('up_to_id:'):
            up_to_id = up_to_id.split(':', 1)[1]
            amount = None
        elif up_to_id:
            # If there's extra text, treat it as invalid
            await ctx.send("❌ Invalid format. Use `!purge 10` or `!purge up_to_id:123456789`")
            return
        
        # Validate input
        if amount is None and up_to_id is None:
            await ctx.send("❌ You must specify either an amount or use `up_to_id:message_id`.\n"
                          "Examples: `!purge 10` or `!purge up_to_id:1234567890123456789`")
            return
        
        if amount is not None and (amount < 1 or amount > 100):
            await ctx.send("❌ Amount must be between 1 and 100.")
            return

        try:
            channel = ctx.channel
            deleted_count = 0
            
            if amount is not None:
                # Delete X most recent messages (including the command message)
                deleted_messages = await channel.purge(limit=amount + 1)  # +1 for command message
                deleted_count = len(deleted_messages) - 1  # Don't count the command message
                
            elif up_to_id is not None:
                # Validate message ID format
                try:
                    target_message_id = int(up_to_id)
                except ValueError:
                    await ctx.send("❌ Invalid message ID format. Please provide a valid message ID.")
                    return
                
                # Check if the target message exists
                try:
                    target_message = await channel.fetch_message(target_message_id)
                except discord.NotFound:
                    await ctx.send("❌ Message with that ID not found in this channel.")
                    return
                except discord.HTTPException as e:
                    await ctx.send(f"❌ Error fetching message: {e}")
                    return
                
                # Delete messages from most recent up to the target message (including command)
                messages_to_delete = []
                async for message in channel.history(limit=None):
                    if message.id == target_message_id:
                        break
                    messages_to_delete.append(message)
                
                if not messages_to_delete:
                    await ctx.send("❌ No messages found newer than the specified message ID.")
                    return
                
                # Handle bulk deletion with proper error handling
                if len(messages_to_delete) <= 100:
                    try:
                        await channel.delete_messages(messages_to_delete)
                        deleted_count = len(messages_to_delete)
                    except discord.HTTPException:
                        # Fall back to individual deletion
                        for message in messages_to_delete:
                            try:
                                await message.delete()
                                deleted_count += 1
                                await asyncio.sleep(0.5)
                            except discord.HTTPException:
                                continue
                else:
                    # Handle large amounts in chunks
                    for i in range(0, len(messages_to_delete), 100):
                        chunk = messages_to_delete[i:i+100]
                        try:
                            await channel.delete_messages(chunk)
                            deleted_count += len(chunk)
                        except discord.HTTPException:
                            for message in chunk:
                                try:
                                    await message.delete()
                                    deleted_count += 1
                                    await asyncio.sleep(0.5)
                                except discord.HTTPException:
                                    continue
                        await asyncio.sleep(1)
            
            # Send confirmation message
            embed = discord.Embed(
                title="✅ Messages Deleted",
                description=f"Successfully deleted **{deleted_count}** message(s).",
                color=discord.Color.green()
            )
            embed.set_footer(text=f"Requested by {ctx.author.display_name}")
            
            confirmation_msg = await ctx.send(embed=embed)
            
            # Auto-delete confirmation after 5 seconds
            await asyncio.sleep(5)
            try:
                await confirmation_msg.delete()
            except discord.HTTPException:
                pass
            
            # Log the action
            print(f"[MODERATION] {ctx.author} deleted {deleted_count} messages in #{channel.name} using traditional command")
            
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to delete messages in this channel.")
        except Exception as e:
            await ctx.send(f"❌ An error occurred while deleting messages: {str(e)}")
            print(f"[MODERATION ERROR] {e}")

    @purge_traditional.error
    async def purge_traditional_error(self, ctx, error):
        """Error handler for traditional purge command"""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You need the 'Manage Messages' permission to use this command.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("❌ Invalid argument. Please provide a valid number.\n"
                          "Examples: `!purge 10` or `!purge up_to_id:1234567890123456789`")
        else:
            await ctx.send("❌ An unexpected error occurred.")
            print(f"[MODERATION ERROR] {error}")

async def setup(bot):
    await bot.add_cog(Moderation(bot))
