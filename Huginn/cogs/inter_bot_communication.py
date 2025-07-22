import discord # type: ignore
from discord.ext import commands # type: ignore
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
        self.bot_name = "Huginn"  # This bot is Huginn
        self.other_bot_id = None  # Will be set to Muninn's bot ID
        self.message_queue = []
        self.pending_responses = {}
        self.received_configs = {}  # Store configs received from Muninn
        
        # Define bot IDs and owner ID
        self.MUNINN_BOT_ID = None  # Will be set when discovered
        self.HUGINN_BOT_ID = None  # Will be set when bot starts  
        self.BOT_OWNER_ID = 867261583871836161
        
    async def cog_load(self):
        """Initialize bot-specific settings when cog loads."""
        await self.bot.wait_until_ready()
        
        # This is Huginn, so we need to find Muninn's ID
        # For now, we'll set it manually - you can update this later
        self.other_bot_id = None  # Replace with Muninn's bot ID when known
            
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
                color=discord.Color.purple(),  # Purple for Huginn
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
        elif command_type == "pong":
            await self.handle_pong(data)
        else:
            print(f"Unknown inter-bot command type: {command_type}")

    async def handle_server_config_sync(self, data: Dict[str, Any], guild_id: int):
        """Handle server configuration synchronization."""
        print(f"Received server config sync for guild {guild_id}: {data}")
        
        # Store the received config
        self.received_configs[str(guild_id)] = data
        
        # Huginn should update its pin schedule based on the config
        pin_cog = self.bot.get_cog('AutoPins')
        if pin_cog and data:
            print(f"Updating pin schedule for guild {guild_id} based on server config")
            
            # Check for devotion settings that affect pin timing
            devotion_hour = data.get('devotion_hour', {}).get('value')
            devotion_minute = data.get('devotion_minute', {}).get('value')
            devotion_enabled = data.get('devotion_enabled', {}).get('value')
            
            if devotion_hour is not None and devotion_minute is not None:
                print(f"Guild {guild_id} devotion time: {devotion_hour:02d}:{devotion_minute:02d}, enabled: {devotion_enabled}")
                
                # Notify owner of the sync
                await self.notify_owner(
                    f"🔄 Pin Schedule Updated for Guild {guild_id}",
                    {
                        "guild_id": guild_id,
                        "devotion_time": f"{devotion_hour:02d}:{devotion_minute:02d}",
                        "enabled": devotion_enabled
                    }
                )

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
        """Add a new @ response to Huginn's response file."""
        try:
            response_file = "data/at_responses.yaml"
            
            # Load current responses
            with open(response_file, 'r', encoding='utf-8') as f:
                responses_data = yaml.safe_load(f)
            
            # Add new response if it doesn't already exist
            if response not in responses_data["responses"]:
                responses_data["responses"].append(response)
                
                # Save updated responses
                with open(response_file, 'w', encoding='utf-8') as f:
                    yaml.dump(responses_data, f, default_flow_style=False, allow_unicode=True)
                
                print(f"Added new @ response to Huginn: {response}")
                
                # Notify owner
                await self.notify_owner(
                    f"✅ New @ Response Added to {self.bot_name}",
                    {"response": response, "guild_id": guild_id}
                )
            else:
                print(f"@ response already exists in Huginn: {response}")
                
        except Exception as e:
            print(f"Error adding @ response to Huginn: {e}")

    async def handle_ping(self, data: Dict[str, Any]):
        """Handle ping messages."""
        await self.send_to_other_bot("pong", {"message": "Hello from " + self.bot_name})

    async def handle_pong(self, data: Dict[str, Any]):
        """Handle pong messages."""
        print(f"Received pong from other bot: {data}")

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
        
        # Also add to this bot (Huginn)
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
            color=discord.Color.purple()
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
