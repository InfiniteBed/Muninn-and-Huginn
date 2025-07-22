import discord
from discord.ext import commands
import sqlite3
import asyncio
from typing import Optional, Dict, Any

class ServerConfig(commands.Cog):
    """Handles server-wide configuration settings in an extensible way."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "discord.db"
        self._initialize_database()
        
    def _initialize_database(self):
        """Initialize the server configuration database table."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS server_config (
                    guild_id INTEGER NOT NULL,
                    config_key TEXT NOT NULL,
                    config_value TEXT,
                    config_type TEXT DEFAULT 'string',
                    description TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, config_key)
                )
            """)
            
            # Create index for faster lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_server_config_guild 
                ON server_config(guild_id)
            """)
            conn.commit()
    
    def set_config(self, guild_id: int, key: str, value: Any, 
                   config_type: str = 'string', description: str = None) -> bool:
        """Set a configuration value for a server."""
        try:
            # Convert value to string for storage
            if config_type == 'channel':
                # Store channel ID as string
                str_value = str(value) if value else None
            elif config_type == 'boolean':
                str_value = 'true' if value else 'false'
            elif config_type == 'integer':
                str_value = str(int(value)) if value is not None else None
            else:
                str_value = str(value) if value is not None else None
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO server_config 
                    (guild_id, config_key, config_value, config_type, description, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (guild_id, key, str_value, config_type, description))
                conn.commit()
                
                # Sync to Huginn if this is a relevant config
                asyncio.create_task(self._sync_config_to_huginn(guild_id, key, value, config_type))
                
                return True
        except Exception as e:
            print(f"Error setting config {key} for guild {guild_id}: {e}")
            return False

    async def _sync_config_to_huginn(self, guild_id: int, key: str, value: Any, config_type: str):
        """Sync configuration changes to Huginn bot."""
        try:
            # Only sync relevant configs (devotion settings that affect pin timing)
            relevant_keys = ['devotion_hour', 'devotion_minute', 'devotion_enabled', 'devotion_channel']
            
            if key in relevant_keys:
                ibc_cog = self.bot.get_cog('InterBotCommunication')
                if ibc_cog:
                    # Get all current configs for this guild
                    all_configs = self.get_all_config(guild_id)
                    
                    await ibc_cog.send_to_other_bot(
                        "server_config_sync",
                        all_configs,
                        guild_id
                    )
                    print(f"Synced config '{key}' to Huginn for guild {guild_id}")
        except Exception as e:
            print(f"Error syncing config to Huginn: {e}")
    
    def get_config(self, guild_id: int, key: str, default: Any = None) -> Any:
        """Get a configuration value for a server."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT config_value, config_type FROM server_config 
                    WHERE guild_id = ? AND config_key = ?
                """, (guild_id, key))
                
                result = cursor.fetchone()
                if not result or result[0] is None:
                    return default
                
                value, config_type = result
                
                # Convert back to appropriate type
                if config_type == 'channel':
                    try:
                        return int(value) if value else default
                    except ValueError:
                        return default
                elif config_type == 'boolean':
                    return value.lower() == 'true'
                elif config_type == 'integer':
                    try:
                        return int(value)
                    except ValueError:
                        return default
                else:
                    return value
                    
        except Exception as e:
            print(f"Error getting config {key} for guild {guild_id}: {e}")
            return default
    
    def delete_config(self, guild_id: int, key: str) -> bool:
        """Delete a configuration value for a server."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM server_config 
                    WHERE guild_id = ? AND config_key = ?
                """, (guild_id, key))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Error deleting config {key} for guild {guild_id}: {e}")
            return False
    
    def get_all_config(self, guild_id: int) -> Dict[str, Any]:
        """Get all configuration values for a server."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT config_key, config_value, config_type, description 
                    FROM server_config WHERE guild_id = ?
                    ORDER BY config_key
                """, (guild_id,))
                
                configs = {}
                for key, value, config_type, description in cursor.fetchall():
                    if value is None:
                        configs[key] = {'value': None, 'type': config_type, 'description': description}
                        continue
                        
                    # Convert to appropriate type
                    if config_type == 'channel':
                        try:
                            configs[key] = {
                                'value': int(value), 
                                'type': config_type, 
                                'description': description
                            }
                        except ValueError:
                            configs[key] = {'value': None, 'type': config_type, 'description': description}
                    elif config_type == 'boolean':
                        configs[key] = {
                            'value': value.lower() == 'true', 
                            'type': config_type, 
                            'description': description
                        }
                    elif config_type == 'integer':
                        try:
                            configs[key] = {
                                'value': int(value), 
                                'type': config_type, 
                                'description': description
                            }
                        except ValueError:
                            configs[key] = {'value': None, 'type': config_type, 'description': description}
                    else:
                        configs[key] = {'value': value, 'type': config_type, 'description': description}
                
                return configs
        except Exception as e:
            print(f"Error getting all configs for guild {guild_id}: {e}")
            return {}

    @commands.group(name="config", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def config_group(self, ctx):
        """Server configuration commands. Requires administrator permissions."""
        if ctx.invoked_subcommand is None:
            # Show the main server settings interface
            await self.show_main_settings_interface(ctx)
    
    async def show_main_settings_interface(self, ctx):
        """Show the main server settings interface with emojis and navigation."""
        embed = discord.Embed(
            title="🔧 Server Configuration Panel",
            description="Welcome to the comprehensive server settings panel! Navigate through different categories to configure your server.",
            color=discord.Color.blue()
        )
        
        # Get current configurations to show status
        configs = self.get_all_config(ctx.guild.id)
        
        # Devotion Settings Section
        devotion_channel = configs.get('devotion_channel', {}).get('value')
        devotion_hour = configs.get('devotion_hour', {}).get('value', 17)  # Default 5 PM
        devotion_minute = configs.get('devotion_minute', {}).get('value', 30)  # Default :30
        
        if devotion_channel:
            channel = self.bot.get_channel(devotion_channel)
            channel_status = f"✅ {channel.mention}" if channel else "❌ Channel not found"
        else:
            channel_status = "❌ Not configured"
        
        embed.add_field(
            name="🙏 **Devotion & Faith Settings**",
            value=(
                f"**Channel:** {channel_status}\n"
                f"**Daily Time:** {devotion_hour:02d}:{devotion_minute:02d} Pacific Time\n"
                f"📝 `!config devotion` - Configure devotion settings"
            ),
            inline=False
        )
        
        # Music Settings Section  
        embed.add_field(
            name="🎵 **Music System Settings**",
            value=(
                "**Stream Mode:** Configure continuous playback\n"
                "**Cache Settings:** Audio caching preferences\n"
                "📝 `!config music` - Configure music settings"
            ),
            inline=False
        )
        
        # General Server Settings
        embed.add_field(
            name="⚙️ **General Server Settings**",
            value=(
                "**Server Name:** Display preferences\n"
                "**Notifications:** Global notification settings\n"
                "📝 `!config general` - Configure general settings"
            ),
            inline=False
        )
        
        # Quick Actions
        embed.add_field(
            name="🚀 **Quick Actions**",
            value=(
                "`!config list` - View all current settings\n"
                "`!config backup` - Export server configuration\n"
                "`!config reset` - Reset all settings (dangerous!)"
            ),
            inline=False
        )
        
        embed.set_footer(text="💡 Use the specific category commands above or use !config list to see all settings")
        await ctx.send(embed=embed)

    @config_group.command(name="list")
    @commands.has_permissions(administrator=True)
    async def list_config(self, ctx):
        """List all server configuration settings."""
        configs = self.get_all_config(ctx.guild.id)
        
        if not configs:
            embed = discord.Embed(
                title="Server Configuration",
                description="No configuration settings found for this server.",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(
            title=f"Server Configuration for {ctx.guild.name}",
            color=discord.Color.green()
        )
        
        for key, config_data in configs.items():
            value = config_data['value']
            config_type = config_data['type']
            description = config_data['description'] or 'No description'
            
            # Format value based on type
            if config_type == 'channel' and value:
                channel = self.bot.get_channel(value)
                display_value = f"<#{value}>" if channel else f"Channel ID: {value} (not found)"
            elif config_type == 'boolean':
                display_value = "✅ Enabled" if value else "❌ Disabled"
            else:
                display_value = str(value) if value is not None else "Not set"
            
            embed.add_field(
                name=f"`{key}` ({config_type})",
                value=f"**Value:** {display_value}\n**Description:** {description}",
                inline=False
            )
        
        await ctx.send(embed=embed)

    @config_group.command(name="get")
    @commands.has_permissions(administrator=True)
    async def get_config_cmd(self, ctx, key: str):
        """Get a specific configuration value."""
        value = self.get_config(ctx.guild.id, key)
        
        embed = discord.Embed(
            title=f"Configuration: {key}",
            color=discord.Color.blue()
        )
        
        if value is None:
            embed.description = "This configuration key is not set."
            embed.color = discord.Color.orange()
        else:
            embed.add_field(name="Value", value=str(value), inline=False)
        
        await ctx.send(embed=embed)

    @config_group.command(name="delete")
    @commands.has_permissions(administrator=True)
    async def delete_config_cmd(self, ctx, key: str):
        """Delete a configuration value."""
        success = self.delete_config(ctx.guild.id, key)
        
        if success:
            embed = discord.Embed(
                title="Configuration Deleted ✅",
                description=f"Successfully deleted configuration key: `{key}`",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="Configuration Not Found ❌",
                description=f"Configuration key `{key}` was not found or could not be deleted.",
                color=discord.Color.red()
            )
        
        await ctx.send(embed=embed)

    @config_group.command(name="devotion")
    @commands.has_permissions(administrator=True)
    async def configure_devotion(self, ctx):
        """Configure devotion system settings with interactive interface."""
        configs = self.get_all_config(ctx.guild.id)
        
        # Get current settings
        devotion_channel = configs.get('devotion_channel', {}).get('value')
        devotion_hour = configs.get('devotion_hour', {}).get('value', 17)
        devotion_minute = configs.get('devotion_minute', {}).get('value', 30)
        devotion_enabled = configs.get('devotion_enabled', {}).get('value', True)
        
        embed = discord.Embed(
            title="🙏 Devotion System Configuration",
            description="Configure your server's daily devotion accountability system",
            color=discord.Color.green()
        )
        
        # Current Channel Status
        if devotion_channel:
            channel = self.bot.get_channel(devotion_channel)
            channel_status = f"✅ {channel.mention}" if channel else "❌ Channel not found"
        else:
            channel_status = "❌ Not configured"
        
        embed.add_field(
            name="📺 Current Channel",
            value=channel_status,
            inline=True
        )
        
        # Current Schedule
        embed.add_field(
            name="🕐 Daily Schedule",
            value=f"{'✅' if devotion_enabled else '❌'} {devotion_hour:02d}:{devotion_minute:02d} Pacific Time",
            inline=True
        )
        
        # Status
        status_emoji = "🟢" if devotion_enabled and devotion_channel else "🔴"
        status_text = "Active" if devotion_enabled and devotion_channel else "Inactive"
        embed.add_field(
            name="📊 System Status",
            value=f"{status_emoji} {status_text}",
            inline=True
        )
        
        # Configuration Commands
        embed.add_field(
            name="⚙️ Configuration Commands",
            value=(
                f"**Set Channel:** `!config devotion_channel #channel`\n"
                f"**Set Time:** `!config devotion_time <hour> <minute>`\n"
                f"**Toggle:** `!config devotion_toggle`\n"
                f"**Test:** `!devotion` (manual trigger)"
            ),
            inline=False
        )
        
        # Quick Setup Examples
        embed.add_field(
            name="💡 Quick Setup Examples",
            value=(
                "`!config devotion_channel #faith` - Set to #faith channel\n"
                "`!config devotion_time 18 0` - Set to 6:00 PM\n"
                "`!config devotion_time 19 30` - Set to 7:30 PM"
            ),
            inline=False
        )
        
        embed.set_footer(text="💡 All times are in Pacific Time Zone • Changes take effect immediately")
        await ctx.send(embed=embed)

    @config_group.command(name="devotion_time")
    @commands.has_permissions(administrator=True)
    async def set_devotion_time(self, ctx, hour: int, minute: int = 0):
        """Set the daily devotion message time (Pacific Time)."""
        # Validate time
        if not (0 <= hour <= 23):
            await ctx.send("❌ Hour must be between 0 and 23 (24-hour format)")
            return
        if not (0 <= minute <= 59):
            await ctx.send("❌ Minute must be between 0 and 59")
            return
        
        # Set the configuration
        hour_success = self.set_config(
            ctx.guild.id, 
            'devotion_hour', 
            hour, 
            'integer',
            'Hour for daily devotion messages (Pacific Time, 24-hour format)'
        )
        
        minute_success = self.set_config(
            ctx.guild.id, 
            'devotion_minute', 
            minute, 
            'integer',
            'Minute for daily devotion messages'
        )
        
        if hour_success and minute_success:
            # Convert to 12-hour format for display
            display_hour = hour
            am_pm = "AM"
            if hour == 0:
                display_hour = 12
            elif hour > 12:
                display_hour = hour - 12
                am_pm = "PM"
            elif hour == 12:
                am_pm = "PM"
            
            embed = discord.Embed(
                title="🕐 Devotion Time Updated",
                description=f"Daily devotion messages will now be sent at **{display_hour}:{minute:02d} {am_pm} Pacific Time**",
                color=discord.Color.green()
            )
            embed.add_field(
                name="24-Hour Format",
                value=f"{hour:02d}:{minute:02d}",
                inline=True
            )
            embed.add_field(
                name="Next Message",
                value="Tomorrow at the configured time",
                inline=True
            )
            embed.set_footer(text="💡 Use `!devotion` to test the message immediately")
        else:
            embed = discord.Embed(
                title="❌ Error Setting Time",
                description="Failed to update devotion time. Please try again.",
                color=discord.Color.red()
            )
        
        await ctx.send(embed=embed)

    @config_group.command(name="devotion_toggle")
    @commands.has_permissions(administrator=True)
    async def toggle_devotion(self, ctx):
        """Toggle devotion system on/off."""
        current_enabled = self.get_config(ctx.guild.id, 'devotion_enabled', True)
        new_enabled = not current_enabled
        
        success = self.set_config(
            ctx.guild.id,
            'devotion_enabled',
            new_enabled,
            'boolean',
            'Whether daily devotion messages are enabled'
        )
        
        if success:
            status = "enabled" if new_enabled else "disabled"
            emoji = "✅" if new_enabled else "❌"
            color = discord.Color.green() if new_enabled else discord.Color.red()
            
            embed = discord.Embed(
                title=f"{emoji} Devotion System {status.title()}",
                description=f"Daily devotion messages are now **{status}**",
                color=color
            )
            
            if new_enabled:
                # Show current configuration
                devotion_channel = self.get_config(ctx.guild.id, 'devotion_channel')
                if devotion_channel:
                    channel = self.bot.get_channel(devotion_channel)
                    if channel:
                        embed.add_field(
                            name="Channel",
                            value=channel.mention,
                            inline=True
                        )
                
                devotion_hour = self.get_config(ctx.guild.id, 'devotion_hour', 17)
                devotion_minute = self.get_config(ctx.guild.id, 'devotion_minute', 30)
                embed.add_field(
                    name="Time",
                    value=f"{devotion_hour:02d}:{devotion_minute:02d} PT",
                    inline=True
                )
            else:
                embed.add_field(
                    name="To Re-enable",
                    value="Use `!config devotion_toggle` again",
                    inline=False
                )
        else:
            embed = discord.Embed(
                title="❌ Error",
                description="Failed to toggle devotion system",
                color=discord.Color.red()
            )
        
        await ctx.send(embed=embed)

    @config_group.command(name="devotion_channel")
    @commands.has_permissions(administrator=True)
    async def set_devotion_channel(self, ctx, channel: discord.TextChannel):
        """Set the channel for daily devotion check-ins."""
        success = self.set_config(
            ctx.guild.id, 
            'devotion_channel', 
            channel.id, 
            'channel',
            'Channel where daily devotion accountability messages are sent'
        )
        
        if success:
            embed = discord.Embed(
                title="✅ Devotion Channel Set",
                description=f"Daily devotion check-ins will now be sent to {channel.mention}",
                color=discord.Color.green()
            )
            
            # Show current configuration summary
            devotion_hour = self.get_config(ctx.guild.id, 'devotion_hour', 17)
            devotion_minute = self.get_config(ctx.guild.id, 'devotion_minute', 30)
            devotion_enabled = self.get_config(ctx.guild.id, 'devotion_enabled', True)
            
            embed.add_field(
                name="📅 Schedule",
                value=f"{'✅' if devotion_enabled else '❌'} Daily at {devotion_hour:02d}:{devotion_minute:02d} PT",
                inline=True
            )
            embed.add_field(
                name="🔧 Next Steps",
                value="Use `!devotion` to test or `!config devotion` to adjust settings",
                inline=True
            )
        else:
            embed = discord.Embed(
                title="❌ Error Setting Channel",
                description="Failed to set the devotion channel. Please try again.",
                color=discord.Color.red()
            )
        
        await ctx.send(embed=embed)

    @config_group.command(name="music")
    @commands.has_permissions(administrator=True)
    async def configure_music(self, ctx):
        """Configure music system settings."""
        configs = self.get_all_config(ctx.guild.id)
        
        # Get current music settings
        default_volume = configs.get('music_default_volume', {}).get('value', 50)
        auto_queue = configs.get('music_auto_queue', {}).get('value', False)
        stream_mode = configs.get('music_stream_mode', {}).get('value', False)
        cache_limit = configs.get('music_cache_limit', {}).get('value', 100)
        
        embed = discord.Embed(
            title="🎵 Music System Configuration",
            description="Configure your server's music playback settings",
            color=discord.Color.purple()
        )
        
        embed.add_field(
            name="🔊 Playback Settings",
            value=(
                f"**Default Volume:** {default_volume}%\n"
                f"**Auto Queue:** {'✅ Enabled' if auto_queue else '❌ Disabled'}\n"
                f"**Stream Mode:** {'✅ Enabled' if stream_mode else '❌ Disabled'}"
            ),
            inline=True
        )
        
        embed.add_field(
            name="💾 Cache Settings",
            value=(
                f"**Cache Limit:** {cache_limit} songs\n"
                f"**Cache Status:** Active\n"
                f"**Auto-cleanup:** Enabled"
            ),
            inline=True
        )
        
        embed.add_field(
            name="⚙️ Configuration Commands",
            value=(
                "`!config music_volume <1-100>` - Set default volume\n"
                "`!config music_auto_queue <true/false>` - Toggle auto-queue\n"
                "`!config music_stream_mode <true/false>` - Toggle stream mode\n"
                "`!config music_cache_limit <number>` - Set cache limit"
            ),
            inline=False
        )
        
        embed.set_footer(text="💡 Music settings affect all future playback sessions")
        await ctx.send(embed=embed)

    @config_group.command(name="general")
    @commands.has_permissions(administrator=True)
    async def configure_general(self, ctx):
        """Configure general server settings."""
        configs = self.get_all_config(ctx.guild.id)
        
        # Get current general settings
        server_prefix = configs.get('command_prefix', {}).get('value', '!')
        auto_responses = configs.get('auto_responses', {}).get('value', True)
        logging_enabled = configs.get('logging_enabled', {}).get('value', True)
        
        embed = discord.Embed(
            title="⚙️ General Server Configuration",
            description="Configure general bot behavior for your server",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🤖 Bot Behavior",
            value=(
                f"**Command Prefix:** `{server_prefix}`\n"
                f"**Auto Responses:** {'✅ Enabled' if auto_responses else '❌ Disabled'}\n"
                f"**Activity Logging:** {'✅ Enabled' if logging_enabled else '❌ Disabled'}"
            ),
            inline=True
        )
        
        embed.add_field(
            name="📊 Server Info",
            value=(
                f"**Server ID:** {ctx.guild.id}\n"
                f"**Member Count:** {ctx.guild.member_count}\n"
                f"**Created:** {ctx.guild.created_at.strftime('%Y-%m-%d')}"
            ),
            inline=True
        )
        
        embed.add_field(
            name="⚙️ Configuration Commands",
            value=(
                "`!config prefix <character>` - Set command prefix\n"
                "`!config auto_responses <true/false>` - Toggle responses\n"
                "`!config logging <true/false>` - Toggle activity logging\n"
                "`!config backup` - Export all settings"
            ),
            inline=False
        )
        
        embed.set_footer(text="💡 General settings affect overall bot behavior")
        await ctx.send(embed=embed)

    @config_group.command(name="backup")
    @commands.has_permissions(administrator=True)
    async def backup_config(self, ctx):
        """Export server configuration as a backup."""
        configs = self.get_all_config(ctx.guild.id)
        
        if not configs:
            embed = discord.Embed(
                title="📦 No Configuration Found",
                description="No configuration settings to backup for this server.",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
            return
        
        # Create backup string
        backup_lines = [f"# Server Configuration Backup for {ctx.guild.name}"]
        backup_lines.append(f"# Generated on {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        backup_lines.append("")
        
        for key, config_data in configs.items():
            value = config_data['value']
            config_type = config_data['type']
            description = config_data['description'] or 'No description'
            
            backup_lines.append(f"# {description}")
            backup_lines.append(f"{key}={value}  # Type: {config_type}")
            backup_lines.append("")
        
        backup_content = '\n'.join(backup_lines)
        
        # Create file and send
        import io
        backup_file = io.StringIO(backup_content)
        file = discord.File(backup_file, filename=f"{ctx.guild.name}_config_backup.txt")
        
        embed = discord.Embed(
            title="📦 Configuration Backup Created",
            description=f"Backup contains {len(configs)} configuration settings",
            color=discord.Color.green()
        )
        embed.add_field(
            name="Backup Info",
            value=(
                f"**Settings Count:** {len(configs)}\n"
                f"**Generated:** {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
                f"**Server:** {ctx.guild.name}"
            ),
            inline=False
        )
        embed.set_footer(text="💡 Keep this backup safe! You can use it to restore settings later.")
        
        await ctx.send(embed=embed, file=file)

    @commands.command(name="test_config")
    @commands.has_permissions(administrator=True)
    async def test_config(self, ctx):
        """Test the server configuration system."""
        # Test setting and getting various config types
        test_configs = [
            ('test_string', 'Hello World', 'string', 'A test string value'),
            ('test_boolean', True, 'boolean', 'A test boolean value'),
            ('test_integer', 42, 'integer', 'A test integer value'),
        ]
        
        embed = discord.Embed(
            title="Configuration System Test 🧪",
            color=discord.Color.blue()
        )
        
        results = []
        for key, value, config_type, description in test_configs:
            # Set the config
            set_success = self.set_config(ctx.guild.id, key, value, config_type, description)
            
            # Get the config back
            retrieved_value = self.get_config(ctx.guild.id, key)
            
            # Check if it matches
            matches = retrieved_value == value
            
            status = "✅" if set_success and matches else "❌"
            results.append(f"{status} {key}: {value} → {retrieved_value}")
            
            # Clean up test config
            self.delete_config(ctx.guild.id, key)
        
        embed.add_field(
            name="Test Results",
            value="\n".join(results),
            inline=False
        )
        
        embed.set_footer(text="Test configurations have been cleaned up")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ServerConfig(bot))
