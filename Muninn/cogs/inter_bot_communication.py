import discord
from discord.ext import commands
import json
import asyncio
import datetime
from typing import Dict, Any, Optional
import yaml
import os

class InterBotCommunication(commands.Cog):
    """Handles communication between Muninn and Huginn bots via DMs."""
    
    def __init__(self, bot):
        self.bot = bot
        self.bot_name = "Muninn"  # This will be overridden in each bot
        self.other_bot_id = None  # Will be set based on which bot this is
        self.message_queue = []
        self.pending_responses = {}
        
        # Define bot IDs and owner ID
        self.MUNINN_BOT_ID = None  # Will be set when bot starts
        self.HUGINN_BOT_ID = None  # Will be set when bot starts  
        self.BOT_OWNER_ID = 867261583871836161
        
    async def cog_load(self):
        """Initialize bot-specific settings when cog loads."""
        await self.bot.wait_until_ready()
        
        # Determine which bot this is and set other bot ID
        app_info = await self.bot.application_info()
        current_bot_id = self.bot.user.id
        
        # You'll need to update these with actual bot IDs once both bots are running
        if "muninn" in self.bot.user.name.lower():
            self.bot_name = "Muninn"
            # Set Huginn's bot ID here when known
            self.other_bot_id = None  # Replace with Huginn's bot ID
        else:
            self.bot_name = "Huginn" 
            # Set Muninn's bot ID here when known
            self.other_bot_id = None  # Replace with Muninn's bot ID
            
        print(f"{self.bot_name} inter-bot communication system initialized")

    async def get_bot_owner(self):
        """Get the bot owner user object."""
        try:
            return await self.bot.fetch_user(self.BOT_OWNER_ID)
        except:
            return None

    async def send_to_other_bot(self, message_type: str, data: Dict[str, Any], 
                               guild_id: Optional[int] = None) -> bool:
        """Send a message to the other bot via DM."""
        if not self.other_bot_id:
            print(f"Other bot ID not set, cannot send message")
            return False
            
        try:
            other_bot = await self.bot.fetch_user(self.other_bot_id)
            if not other_bot:
                print(f"Could not find other bot with ID {self.other_bot_id}")
                return False
            
            # Create structured message
            message_data = {
                "type": message_type,
                "from": self.bot_name,
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "guild_id": guild_id,
                "data": data
            }
            
            # Send as JSON
            message_content = f"```json\n{json.dumps(message_data, indent=2)}\n```"
            await other_bot.send(message_content)
            
            # Also notify bot owner
            await self.notify_owner(f"📤 {self.bot_name} sent {message_type} to other bot", message_data)
            
            return True
            
        except Exception as e:
            print(f"Error sending message to other bot: {e}")
            return False

    async def notify_owner(self, title: str, data: Dict[str, Any]):
        """Send a notification to the bot owner."""
        try:
            owner = await self.get_bot_owner()
            if not owner:
                return
                
            embed = discord.Embed(
                title=title,
                description=f"```json\n{json.dumps(data, indent=2)}\n```",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.set_footer(text=f"From {self.bot_name}")
            
            await owner.send(embed=embed)
            
        except Exception as e:
            print(f"Error notifying owner: {e}")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for DMs from the other bot."""
        # Only process DMs to this bot
        if not isinstance(message.channel, discord.DMChannel):
            return
            
        # Ignore messages from self
        if message.author.id == self.bot.user.id:
            return
            
        # Check if message is from the other bot
        if self.other_bot_id and message.author.id == self.other_bot_id:
            await self.process_inter_bot_message(message)
            
    async def process_inter_bot_message(self, message):
        """Process a message received from the other bot."""
        try:
            # Extract JSON from code block
            content = message.content.strip()
            if content.startswith("```json") and content.endswith("```"):
                json_content = content[7:-3].strip()  # Remove ```json and ```
                message_data = json.loads(json_content)
                
                await self.handle_inter_bot_command(message_data)
                
                # Notify owner of received message
                await self.notify_owner(f"📥 {self.bot_name} received {message_data.get('type', 'unknown')} from other bot", message_data)
                
        except Exception as e:
            print(f"Error processing inter-bot message: {e}")

    async def handle_inter_bot_command(self, message_data: Dict[str, Any]):
        """Handle specific commands received from the other bot."""
        command_type = message_data.get("type")
        data = message_data.get("data", {})
        guild_id = message_data.get("guild_id")
        
        if command_type == "server_config_sync":
            await self.handle_server_config_sync(data, guild_id)
        elif command_type == "suggestion_approved":
            await self.handle_suggestion_approved(data, guild_id)
        elif command_type == "at_response_update":
            await self.handle_at_response_update(data, guild_id)
        elif command_type == "ping":
            await self.handle_ping(data)
        else:
            print(f"Unknown inter-bot command type: {command_type}")

    async def handle_server_config_sync(self, data: Dict[str, Any], guild_id: int):
        """Handle server configuration synchronization."""
        print(f"Received server config sync for guild {guild_id}: {data}")
        
        # If this is Huginn, update pin schedule based on config
        if self.bot_name == "Huginn":
            pin_cog = self.bot.get_cog('AutoPins')
            if pin_cog:
                # Force refresh of pin times
                print(f"Updating pin schedule for guild {guild_id} based on server config")

    async def handle_suggestion_approved(self, data: Dict[str, Any], guild_id: int):
        """Handle approved suggestions."""
        suggestion_type = data.get("suggestion_type")
        content = data.get("content")
        
        print(f"Processing approved suggestion: {suggestion_type}")
        
        if suggestion_type == "at_response":
            await self.add_at_response(content, guild_id)

    async def handle_at_response_update(self, data: Dict[str, Any], guild_id: int):
        """Handle @ response updates."""
        new_response = data.get("response")
        if new_response:
            await self.add_at_response(new_response, guild_id)

    async def add_at_response(self, response: str, guild_id: int):
        """Add a new @ response to the bot's response file."""
        try:
            # Determine the correct file path based on bot
            if self.bot_name == "Huginn":
                response_file = "/mnt/Lake/Starboard/Discord/Huginn/data/at_responses.yaml"
            else:
                response_file = "/mnt/Lake/Starboard/Discord/Muninn/data/at_responses.yaml"
            
            # Load current responses
            with open(response_file, 'r', encoding='utf-8') as f:
                responses_data = yaml.safe_load(f)
            
            # Add new response if it doesn't already exist
            if response not in responses_data["responses"]:
                responses_data["responses"].append(response)
                
                # Save updated responses
                with open(response_file, 'w', encoding='utf-8') as f:
                    yaml.dump(responses_data, f, default_flow_style=False, allow_unicode=True)
                
                print(f"Added new @ response: {response}")
                
                # Notify owner
                await self.notify_owner(
                    f"✅ New @ Response Added to {self.bot_name}",
                    {"response": response, "guild_id": guild_id}
                )
            else:
                print(f"@ response already exists: {response}")
                
        except Exception as e:
            print(f"Error adding @ response: {e}")

    async def handle_ping(self, data: Dict[str, Any]):
        """Handle ping messages."""
        await self.send_to_other_bot("pong", {"message": "Hello from " + self.bot_name})

    # Commands for testing and management
    @commands.command(name="ibc_ping")
    @commands.is_owner()
    async def ping_other_bot(self, ctx):
        """Ping the other bot (owner only)."""
        success = await self.send_to_other_bot("ping", {"message": "Ping from " + self.bot_name})
        if success:
            await ctx.send("✅ Ping sent to other bot")
        else:
            await ctx.send("❌ Failed to send ping")

    @commands.command(name="ibc_sync_config")
    @commands.is_owner()
    async def sync_config(self, ctx, guild_id: int = None):
        """Sync server configuration to other bot (owner only)."""
        if not guild_id:
            guild_id = ctx.guild.id if ctx.guild else None
            
        if not guild_id:
            await ctx.send("❌ Guild ID required")
            return
            
        # Only Muninn should send config
        if self.bot_name != "Muninn":
            await ctx.send("❌ Only Muninn can sync server configs")
            return
            
        # Get server config
        server_config = self.bot.get_cog('ServerConfig')
        if not server_config:
            await ctx.send("❌ ServerConfig cog not found")
            return
            
        configs = server_config.get_all_config(guild_id)
        
        success = await self.send_to_other_bot("server_config_sync", configs, guild_id)
        if success:
            await ctx.send(f"✅ Server config synced to other bot for guild {guild_id}")
        else:
            await ctx.send("❌ Failed to sync config")

    @commands.command(name="ibc_suggest_response")
    @commands.is_owner()
    async def suggest_at_response(self, ctx, *, response: str):
        """Suggest a new @ response to be added to both bots (owner only)."""
        suggestion_data = {
            "suggestion_type": "at_response",
            "content": response,
            "suggested_by": str(ctx.author),
            "suggestion_id": f"{ctx.message.id}"
        }
        
        success = await self.send_to_other_bot("suggestion_approved", suggestion_data, ctx.guild.id if ctx.guild else None)
        
        # Also add to this bot
        await self.add_at_response(response, ctx.guild.id if ctx.guild else None)
        
        if success:
            await ctx.send(f"✅ @ response suggestion sent to both bots: `{response}`")
        else:
            await ctx.send(f"⚠️ @ response added to {self.bot_name} but failed to send to other bot: `{response}`")

    @commands.command(name="ibc_status")
    @commands.is_owner()
    async def communication_status(self, ctx):
        """Show inter-bot communication status (owner only)."""
        embed = discord.Embed(
            title=f"{self.bot_name} Inter-Bot Communication Status",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="Bot Identity",
            value=f"**This Bot:** {self.bot_name}\n**Bot ID:** {self.bot.user.id}",
            inline=True
        )
        
        embed.add_field(
            name="Other Bot",
            value=f"**Target ID:** {self.other_bot_id or 'Not Set'}\n**Connected:** {'✅' if self.other_bot_id else '❌'}",
            inline=True
        )
        
        embed.add_field(
            name="Owner",
            value=f"**Owner ID:** {self.BOT_OWNER_ID}",
            inline=True
        )
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(InterBotCommunication(bot))
