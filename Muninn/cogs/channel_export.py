import discord
from discord.ext import commands
from datetime import datetime, timedelta
import os

class ChannelExport(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    @commands.command(name='export_channel')
    @commands.has_permissions(manage_messages=True)
    async def export_channel(self, ctx, channel: discord.TextChannel = None):
        """
        Export the last 24 hours of messages from a channel to a text file.
        If no channel is specified, uses the current channel.
        """
        # Use current channel if none specified
        channel = channel or ctx.channel
        
        # Get the cutoff time (24 hours ago)
        cutoff_time = datetime.utcnow() - timedelta(days=1)
        
        async with ctx.typing():
            # Inform the user we're working on it
            status_msg = await ctx.send(f"📥 Collecting messages from {channel.mention}...")
            
            messages = []
            try:
                # Fetch messages after the cutoff time
                async for message in channel.history(after=cutoff_time, oldest_first=True):
                    timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                    attachments = " ".join([f"[{a.filename}]({a.url})" for a in message.attachments])
                    
                    # Format the message content
                    content = f"[{timestamp}] {message.author.name}#{message.author.discriminator}: {message.content}"
                    if attachments:
                        content += f"\nAttachments: {attachments}"
                    if message.embeds:
                        content += f"\nEmbeds: {len(message.embeds)} embed(s)"
                    if message.reactions:
                        reactions = [f"{reaction.emoji}:{reaction.count}" for reaction in message.reactions]
                        content += f"\nReactions: {' '.join(reactions)}"
                    
                    messages.append(content)
            
                # Create the exports directory if it doesn't exist
                os.makedirs("exports", exist_ok=True)
                
                # Generate filename with channel name and timestamp
                filename = f"exports/channel_export_{channel.name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
                
                # Write messages to file
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(f"Channel Export: #{channel.name}\n")
                    f.write(f"Export Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
                    f.write(f"Messages from: {cutoff_time.strftime('%Y-%m-%d %H:%M:%S UTC')} to {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
                    f.write("=" * 80 + "\n\n")
                    f.write("\n\n".join(messages))
                
                # Send the file back to Discord
                await status_msg.edit(content=f"✅ Export complete! Uploading file...")
                await ctx.send(file=discord.File(filename))
                
            except Exception as e:
                await status_msg.edit(content=f"❌ Error during export: {str(e)}")
                return

async def setup(bot):
    await bot.add_cog(ChannelExport(bot))
