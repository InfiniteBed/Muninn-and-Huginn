import discord
from discord.ext import commands
import sqlite3
import asyncio
from typing import Optional, Dict, Any, List
def _import_load_global_config():
    try:
        from Muninn.configuration import load_global_config
        return load_global_config
    except Exception:
        pass
    try:
        from configuration import load_global_config
        return load_global_config
    except Exception:
        pass
    try:
        from ..configuration import load_global_config
        return load_global_config
    except Exception:
        pass

    import importlib.util, os
    config_path = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'configuration.py'))
    if os.path.exists(config_path):
        spec = importlib.util.spec_from_file_location('muninn_configuration', config_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore
        return getattr(module, 'load_global_config')

    raise ImportError('Could not import load_global_config from Muninn.configuration or configuration.py')


load_global_config = _import_load_global_config()

class ServerConfig(commands.Cog):
    """Handles server-wide configuration settings in an extensible way."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "discord.db"
        self._initialize_database()
        self.global_config = load_global_config()
        
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

    def refresh_global_config(self) -> None:
        self.global_config = load_global_config(refresh=True)

    def get_default_music_provider(self) -> str:
        return self.global_config.get('music', {}).get('default_provider', 'youtube')

    def is_plex_ready(self) -> bool:
        plex_cfg = self.global_config.get('plex', {})
        token = plex_cfg.get('token', '')
        return (
            plex_cfg.get('enabled', False)
            and bool(plex_cfg.get('base_url'))
            and bool(token)
            and token != "YOUR_PLEX_TOKEN"
        )
    
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
            await self.start_interactive_session(ctx)
    
    def _build_overview_embed(self, guild: discord.Guild, configs: Optional[Dict[str, Any]] = None) -> discord.Embed:
        if configs is None:
            configs = self.get_all_config(guild.id)
        self.refresh_global_config()

        embed = discord.Embed(
            title="🔧 Server Configuration Panel",
            description="Use the interactive controls below to configure your server.",
            color=discord.Color.blue()
        )

        devotion_channel = configs.get('devotion_channel', {}).get('value')
        devotion_hour = configs.get('devotion_hour', {}).get('value', 17)
        devotion_minute = configs.get('devotion_minute', {}).get('value', 30)

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
                "Select the 📿 option below to adjust"
            ),
            inline=False
        )

        default_volume = configs.get('music_default_volume', {}).get('value', 50)
        auto_queue = configs.get('music_auto_queue', {}).get('value', False)
        stream_mode = configs.get('music_stream_mode', {}).get('value', False)
        provider_value = configs.get('music_provider', {}).get('value', self.get_default_music_provider())
        provider_value = (provider_value or 'youtube').lower()
        plex_library = configs.get('plex_library', {}).get('value')
        plex_library = plex_library or self.global_config.get('plex', {}).get('music_library', 'Music')
        provider_label = "Plex" if provider_value == 'plex' else "YouTube"
        plex_status = "—"
        if provider_value == 'plex':
            provider_label = f"Plex ({plex_library})"
            plex_status = "✅ Ready" if self.is_plex_ready() else "⚠️ Configure global Plex settings"

        embed.add_field(
            name="🎵 **Music System Settings**",
            value=(
                f"**Provider:** {provider_label}\n"
                f"**Default Volume:** {default_volume}%\n"
                f"**Auto Queue:** {'✅ Enabled' if auto_queue else '❌ Disabled'}\n"
                f"**Stream Mode:** {'✅ Enabled' if stream_mode else '❌ Disabled'}\n"
                f"**Plex Status:** {plex_status}\n"
                "Select the 🎶 option below to adjust"
            ),
            inline=False
        )

        server_prefix = configs.get('command_prefix', {}).get('value', '!')
        auto_responses = configs.get('auto_responses', {}).get('value', True)
        logging_enabled = configs.get('logging_enabled', {}).get('value', True)

        embed.add_field(
            name="⚙️ **General Server Settings**",
            value=(
                f"**Command Prefix:** `{server_prefix}`\n"
                f"**Auto Responses:** {'✅ Enabled' if auto_responses else '❌ Disabled'}\n"
                f"**Activity Logging:** {'✅ Enabled' if logging_enabled else '❌ Disabled'}\n"
                "Select the ⚙️ option below to adjust"
            ),
            inline=False
        )

        embed.set_footer(text="Changes made through the panel apply immediately.")
        return embed

    async def show_main_settings_interface(self, ctx):
        """Show the main server settings interface."""
        embed = self._build_overview_embed(ctx.guild)
        await ctx.send(embed=embed)

    async def start_interactive_session(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            await ctx.send("This command must be used within a server context.")
            return

        session = ConfigSession(self, ctx)
        await session.start()

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

    def _build_devotion_embed(self, guild: discord.Guild, configs: Optional[Dict[str, Any]] = None) -> discord.Embed:
        if configs is None:
            configs = self.get_all_config(guild.id)

        devotion_channel = configs.get('devotion_channel', {}).get('value')
        devotion_hour = configs.get('devotion_hour', {}).get('value', 17)
        devotion_minute = configs.get('devotion_minute', {}).get('value', 30)
        devotion_enabled = configs.get('devotion_enabled', {}).get('value', True)

        embed = discord.Embed(
            title="🙏 Devotion System Configuration",
            description="Configure your server's daily devotion accountability system",
            color=discord.Color.green()
        )

        if devotion_channel:
            channel = self.bot.get_channel(devotion_channel)
            channel_status = f"✅ {channel.mention}" if channel else "❌ Channel not found"
        else:
            channel_status = "❌ Not configured"

        embed.add_field(name="📺 Current Channel", value=channel_status, inline=True)
        embed.add_field(
            name="🕐 Daily Schedule",
            value=f"{'✅' if devotion_enabled else '❌'} {devotion_hour:02d}:{devotion_minute:02d} Pacific Time",
            inline=True
        )

        status_emoji = "🟢" if devotion_enabled and devotion_channel else "🔴"
        status_text = "Active" if devotion_enabled and devotion_channel else "Inactive"
        embed.add_field(name="📊 System Status", value=f"{status_emoji} {status_text}", inline=True)

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
        return embed

    @config_group.command(name="devotion")
    @commands.has_permissions(administrator=True)
    async def configure_devotion(self, ctx):
        """Configure devotion system settings with interactive interface."""
        embed = self._build_devotion_embed(ctx.guild)
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

    def _build_music_embed(self, guild: discord.Guild, configs: Optional[Dict[str, Any]] = None) -> discord.Embed:
        if configs is None:
            configs = self.get_all_config(guild.id)
        self.refresh_global_config()

        default_volume = configs.get('music_default_volume', {}).get('value', 50)
        auto_queue = configs.get('music_auto_queue', {}).get('value', False)
        stream_mode = configs.get('music_stream_mode', {}).get('value', False)
        cache_limit = configs.get('music_cache_limit', {}).get('value', 100)
        provider_value = configs.get('music_provider', {}).get('value', self.get_default_music_provider())
        provider_value = (provider_value or 'youtube').lower()
        plex_library = configs.get('plex_library', {}).get('value')
        plex_library = plex_library or self.global_config.get('plex', {}).get('music_library', 'Music')
        provider_label = "Plex" if provider_value == 'plex' else "YouTube"
        plex_status = "✅ Ready" if self.is_plex_ready() else "⚠️ Configure global Plex settings"
        if provider_value == 'plex':
            provider_detail = f"Plex ({plex_library})"
        else:
            provider_detail = "YouTube"
            plex_status = "—"

        embed = discord.Embed(
            title="🎵 Music System Configuration",
            description="Configure your server's music playback settings",
            color=discord.Color.purple()
        )

        embed.add_field(
            name="🔊 Playback Settings",
            value=(
                f"**Provider:** {provider_detail}\n"
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

        if provider_value == 'plex':
            embed.add_field(
                name="🎼 Plex Integration",
                value=(
                    f"**Status:** {plex_status}\n"
                    f"**Library:** {plex_library}\n"
                    "Configure Plex credentials via `global_config.yaml`."
                ),
                inline=False
            )

        embed.set_footer(text="💡 Music settings affect all future playback sessions")
        return embed

    @config_group.command(name="music")
    @commands.has_permissions(administrator=True)
    async def configure_music(self, ctx):
        """Configure music system settings."""
        embed = self._build_music_embed(ctx.guild)
        await ctx.send(embed=embed)

    def _build_general_embed(self, guild: discord.Guild, configs: Optional[Dict[str, Any]] = None) -> discord.Embed:
        if configs is None:
            configs = self.get_all_config(guild.id)

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
                f"**Server ID:** {guild.id}\n"
                f"**Member Count:** {guild.member_count}\n"
                f"**Created:** {guild.created_at.strftime('%Y-%m-%d')}"
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
        return embed

    def _toggle_boolean_config(
        self,
        guild_id: int,
        key: str,
        description: str,
        default: bool = False
    ) -> Optional[bool]:
        current = self.get_config(guild_id, key, default)
        new_value = not current
        if self.set_config(guild_id, key, new_value, 'boolean', description):
            return new_value
        return None

    def _set_devotion_time_values(self, guild_id: int, hour: int, minute: int) -> bool:
        if not (0 <= hour <= 23) or not (0 <= minute <= 59):
            return False

        hour_success = self.set_config(
            guild_id,
            'devotion_hour',
            hour,
            'integer',
            'Hour for daily devotion messages (Pacific Time, 24-hour format)'
        )

        minute_success = self.set_config(
            guild_id,
            'devotion_minute',
            minute,
            'integer',
            'Minute for daily devotion messages'
        )

        return hour_success and minute_success

    @config_group.command(name="general")
    @commands.has_permissions(administrator=True)
    async def configure_general(self, ctx):
        """Configure general server settings."""
        embed = self._build_general_embed(ctx.guild)
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


class ConfigSession:
    def __init__(self, cog: "ServerConfig", ctx: commands.Context):
        self.cog = cog
        self.ctx = ctx
        self.guild = ctx.guild
        self.message: Optional[discord.Message] = None
        self.closed = False

    def is_authorized(self, user: discord.abc.User) -> bool:
        if not isinstance(user, discord.Member):
            return False
        if user.guild != self.guild:
            return False
        return user == self.ctx.author or user.guild_permissions.administrator

    async def start(self) -> None:
        embed = self.cog._build_overview_embed(self.guild)
        view = ConfigOverviewView(self)
        self.message = await self.ctx.send(embed=embed, view=view)

    async def show_overview(self, interaction: Optional[discord.Interaction] = None) -> None:
        if self.closed:
            return
        embed = self.cog._build_overview_embed(self.guild)
        view = ConfigOverviewView(self)
        await self._update_main_message(embed, view, interaction)

    async def show_category(self, category: str, interaction: discord.Interaction) -> None:
        if self.closed:
            return

        configs = self.cog.get_all_config(self.guild.id)
        if category == "devotion":
            embed = self.cog._build_devotion_embed(self.guild, configs)
            view = DevotionConfigView(self, configs)
        elif category == "music":
            embed = self.cog._build_music_embed(self.guild, configs)
            view = MusicConfigView(self, configs)
        elif category == "general":
            embed = self.cog._build_general_embed(self.guild, configs)
            view = GeneralConfigView(self, configs)
        else:
            await interaction.response.send_message("Unknown configuration category.", ephemeral=True)
            return

        await self._update_main_message(embed, view, interaction)

    async def refresh_category(self, category: str) -> None:
        if not self.message or self.closed:
            return
        configs = self.cog.get_all_config(self.guild.id)
        if category == "devotion":
            embed = self.cog._build_devotion_embed(self.guild, configs)
            view = DevotionConfigView(self, configs)
        elif category == "music":
            embed = self.cog._build_music_embed(self.guild, configs)
            view = MusicConfigView(self, configs)
        elif category == "general":
            embed = self.cog._build_general_embed(self.guild, configs)
            view = GeneralConfigView(self, configs)
        else:
            embed = self.cog._build_overview_embed(self.guild, configs)
            view = ConfigOverviewView(self)

        await self._edit_message(embed, view)

    async def close(self, interaction: Optional[discord.Interaction] = None) -> None:
        if self.closed:
            return
        self.closed = True
        if self.message:
            if interaction and not interaction.response.is_done():
                await interaction.response.edit_message(view=None)
            else:
                await self.message.edit(view=None)

    async def _update_main_message(
        self,
        embed: discord.Embed,
        view: discord.ui.View,
        interaction: Optional[discord.Interaction] = None
    ) -> None:
        if interaction and not interaction.response.is_done():
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await self._edit_message(embed, view)

    async def _edit_message(self, embed: discord.Embed, view: discord.ui.View) -> None:
        if self.message:
            await self.message.edit(embed=embed, view=view)


class ConfigOverviewView(discord.ui.View):
    def __init__(self, session: ConfigSession):
        super().__init__(timeout=300)
        self.session = session

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.session.is_authorized(interaction.user):
            return True
        await interaction.response.send_message(
            "You need administrator permissions to use this panel.",
            ephemeral=True
        )
        return False

    async def on_timeout(self) -> None:
        await self.session.close()

    @discord.ui.button(emoji="📿", label="Devotion", style=discord.ButtonStyle.primary)
    async def devotion_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.session.show_category("devotion", interaction)

    @discord.ui.button(emoji="🎶", label="Music", style=discord.ButtonStyle.primary)
    async def music_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.session.show_category("music", interaction)

    @discord.ui.button(emoji="⚙️", label="General", style=discord.ButtonStyle.primary)
    async def general_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.session.show_category("general", interaction)

    @discord.ui.button(emoji="🔄", label="Refresh", style=discord.ButtonStyle.secondary)
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.session.show_overview(interaction)

    @discord.ui.button(emoji="🛑", label="Close", style=discord.ButtonStyle.danger)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.session.close(interaction)


class ConfigCategoryView(discord.ui.View):
    def __init__(self, session: ConfigSession, category: str, configs: Dict[str, Any]):
        super().__init__(timeout=300)
        self.session = session
        self.category = category
        self.configs = configs

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.session.is_authorized(interaction.user):
            return True
        await interaction.response.send_message(
            "You need administrator permissions to modify these settings.",
            ephemeral=True
        )
        return False

    async def on_timeout(self) -> None:
        await self.session.close()

    @discord.ui.button(emoji="⬅️", label="Back", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.session.show_overview(interaction)

    @discord.ui.button(emoji="🛑", label="Close", style=discord.ButtonStyle.danger)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.session.close(interaction)


class DevotionConfigView(ConfigCategoryView):
    def __init__(self, session: ConfigSession, configs: Dict[str, Any]):
        super().__init__(session, "devotion", configs)

    @discord.ui.button(emoji="#️⃣", label="Set Channel", style=discord.ButtonStyle.secondary)
    async def set_channel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        view = DevotionChannelSelectView(self.session)
        await interaction.response.send_message(
            "Select a channel to use for devotion reminders:",
            view=view,
            ephemeral=True
        )

    @discord.ui.button(emoji="🕰️", label="Set Time", style=discord.ButtonStyle.secondary)
    async def set_time(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        modal = DevotionTimeModal(self.session)
        await interaction.response.send_modal(modal)

    @discord.ui.button(emoji="🔀", label="Toggle", style=discord.ButtonStyle.primary)
    async def toggle_devotion(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        result = self.session.cog._toggle_boolean_config(
            interaction.guild.id,
            'devotion_enabled',
            'Whether daily devotion messages are enabled',
            default=True
        )

        if result is None:
            await interaction.response.send_message("Failed to toggle devotion system.", ephemeral=True)
            return

        status = "enabled" if result else "disabled"
        await interaction.response.send_message(
            f"Devotion system is now **{status}**.",
            ephemeral=True
        )
        await self.session.refresh_category("devotion")


class DevotionChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, session: ConfigSession):
        super().__init__(channel_types=[discord.ChannelType.text, discord.ChannelType.news], min_values=1, max_values=1)
        self.session = session

    async def callback(self, interaction: discord.Interaction) -> None:
        channel_id = int(interaction.data["values"][0])
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            await interaction.response.send_message("Could not resolve the selected channel.", ephemeral=True)
            return

        success = self.session.cog.set_config(
            interaction.guild.id,
            'devotion_channel',
            channel.id,
            'channel',
            'Channel where daily devotion accountability messages are sent'
        )

        if success:
            await interaction.response.send_message(
                f"Devotion channel updated to {channel.mention}.",
                ephemeral=True
            )
            await self.session.refresh_category("devotion")
        else:
            await interaction.response.send_message("Failed to update devotion channel.", ephemeral=True)


class DevotionChannelSelectView(discord.ui.View):
    def __init__(self, session: ConfigSession):
        super().__init__(timeout=60)
        self.add_item(DevotionChannelSelect(session))


class DevotionTimeModal(discord.ui.Modal, title="Set Devotion Time"):
    hour: discord.ui.TextInput
    minute: discord.ui.TextInput

    def __init__(self, session: ConfigSession):
        super().__init__(timeout=None)
        self.session = session
        self.hour = discord.ui.TextInput(label="Hour (0-23)", min_length=1, max_length=2, default="17")
        self.minute = discord.ui.TextInput(label="Minute (0-59)", min_length=1, max_length=2, default="30")
        self.add_item(self.hour)
        self.add_item(self.minute)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            hour = int(self.hour.value)
            minute = int(self.minute.value)
        except ValueError:
            await interaction.response.send_message("Please enter valid numbers for hour and minute.", ephemeral=True)
            return

        if not self.session.cog._set_devotion_time_values(interaction.guild.id, hour, minute):
            await interaction.response.send_message(
                "Hour must be 0-23 and minute must be 0-59.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"Devotion time updated to {hour:02d}:{minute:02d} PT.",
            ephemeral=True
        )
        await self.session.refresh_category("devotion")


class MusicProviderSelect(discord.ui.Select):
    def __init__(self, session: ConfigSession, current_value: Optional[str]):
        self.session = session
        current_value = (current_value or session.cog.get_default_music_provider()).lower()
        plex_ready = session.cog.is_plex_ready()

        options = [
            discord.SelectOption(
                label="YouTube",
                value="youtube",
                description="Use YouTube via yt-dlp",
                default=current_value == 'youtube',
                emoji="📺"
            ),
            discord.SelectOption(
                label="Plex",
                value="plex",
                description="Stream from your Plex music library",
                default=current_value == 'plex',
                emoji="🎼",
                disabled=not plex_ready
            ),
        ]

        placeholder = "Select music provider"
        if not plex_ready:
            placeholder += " (configure Plex globally to enable)"

        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not self.session.is_authorized(interaction.user):
            await interaction.response.send_message(
                "You need administrator permissions to modify these settings.",
                ephemeral=True
            )
            return

        new_value = self.values[0]
        if new_value == 'plex' and not self.session.cog.is_plex_ready():
            await interaction.response.send_message(
                "Plex integration isn't ready yet. Update `global_config.yaml` with your Plex details first.",
                ephemeral=True
            )
            return

        success = self.session.cog.set_config(
            interaction.guild.id,
            'music_provider',
            new_value,
            'string',
            'Preferred music provider (youtube or plex)'
        )

        if success:
            provider_name = 'Plex' if new_value == 'plex' else 'YouTube'
            await interaction.response.send_message(
                f"Music provider updated to **{provider_name}**.",
                ephemeral=True
            )
            await self.session.refresh_category("music")
        else:
            await interaction.response.send_message(
                "Failed to update music provider.",
                ephemeral=True
            )


class PlexLibraryButton(discord.ui.Button):
    def __init__(self, session: ConfigSession, current_library: Optional[str]):
        disabled = not session.cog.is_plex_ready()
        label = "Plex Library"
        super().__init__(
            label=label,
            emoji="🎼",
            style=discord.ButtonStyle.secondary,
            disabled=disabled
        )
        self.session = session
        self.current_library = current_library

    async def callback(self, interaction: discord.Interaction) -> None:
        if not self.session.is_authorized(interaction.user):
            await interaction.response.send_message(
                "You need administrator permissions to modify these settings.",
                ephemeral=True
            )
            return

        if not self.session.cog.is_plex_ready():
            await interaction.response.send_message(
                "Plex integration isn't configured yet. Update `global_config.yaml` with your Plex server details first.",
                ephemeral=True
            )
            return

        modal = PlexLibraryModal(self.session, self.current_library)
        await interaction.response.send_modal(modal)


class MusicConfigView(ConfigCategoryView):
    def __init__(self, session: ConfigSession, configs: Dict[str, Any]):
        super().__init__(session, "music", configs)
        current_provider = configs.get('music_provider', {}).get('value')
        self.add_item(MusicProviderSelect(session, current_provider))
        current_library = configs.get('plex_library', {}).get('value')
        self.add_item(PlexLibraryButton(session, current_library))

    @discord.ui.button(emoji="🎚️", label="Volume", style=discord.ButtonStyle.secondary)
    async def set_volume(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        modal = MusicVolumeModal(self.session)
        await interaction.response.send_modal(modal)

    @discord.ui.button(emoji="🔁", label="Auto Queue", style=discord.ButtonStyle.primary)
    async def toggle_auto_queue(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        result = self.session.cog._toggle_boolean_config(
            interaction.guild.id,
            'music_auto_queue',
            'Automatically queue related tracks after the current playlist',
            default=False
        )

        if result is None:
            await interaction.response.send_message("Failed to toggle auto queue.", ephemeral=True)
            return

        status = "enabled" if result else "disabled"
        await interaction.response.send_message(
            f"Auto queue is now **{status}**.",
            ephemeral=True
        )
        await self.session.refresh_category("music")

    @discord.ui.button(emoji="📡", label="Stream Mode", style=discord.ButtonStyle.primary)
    async def toggle_stream_mode(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        result = self.session.cog._toggle_boolean_config(
            interaction.guild.id,
            'music_stream_mode',
            'Enable low-latency stream mode for music playback',
            default=False
        )

        if result is None:
            await interaction.response.send_message("Failed to toggle stream mode.", ephemeral=True)
            return

        status = "enabled" if result else "disabled"
        await interaction.response.send_message(
            f"Stream mode is now **{status}**.",
            ephemeral=True
        )
        await self.session.refresh_category("music")

    @discord.ui.button(emoji="📦", label="Cache Limit", style=discord.ButtonStyle.secondary)
    async def set_cache_limit(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        modal = MusicCacheModal(self.session)
        await interaction.response.send_modal(modal)


class MusicVolumeModal(discord.ui.Modal, title="Set Music Volume"):
    volume: discord.ui.TextInput

    def __init__(self, session: ConfigSession):
        super().__init__(timeout=None)
        self.session = session
        self.volume = discord.ui.TextInput(label="Default Volume (1-100)", min_length=1, max_length=3, default="50")
        self.add_item(self.volume)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            volume = int(self.volume.value)
        except ValueError:
            await interaction.response.send_message("Please enter a whole number between 1 and 100.", ephemeral=True)
            return

        if not (1 <= volume <= 100):
            await interaction.response.send_message("Volume must be between 1 and 100.", ephemeral=True)
            return

        success = self.session.cog.set_config(
            interaction.guild.id,
            'music_default_volume',
            volume,
            'integer',
            'Default playback volume percentage for the music system'
        )

        if success:
            await interaction.response.send_message(
                f"Default music volume set to {volume}%.",
                ephemeral=True
            )
            await self.session.refresh_category("music")
        else:
            await interaction.response.send_message("Failed to update music volume.", ephemeral=True)


class MusicCacheModal(discord.ui.Modal, title="Set Music Cache Limit"):
    limit: discord.ui.TextInput

    def __init__(self, session: ConfigSession):
        super().__init__(timeout=None)
        self.session = session
        self.limit = discord.ui.TextInput(label="Cache Limit (songs)", min_length=1, max_length=4, default="100")
        self.add_item(self.limit)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            limit = int(self.limit.value)
        except ValueError:
            await interaction.response.send_message("Please enter a valid number of songs.", ephemeral=True)
            return

        if limit < 0:
            await interaction.response.send_message("Cache limit must be positive.", ephemeral=True)
            return

        success = self.session.cog.set_config(
            interaction.guild.id,
            'music_cache_limit',
            limit,
            'integer',
            'Maximum number of songs to retain in the music cache'
        )

        if success:
            await interaction.response.send_message(
                f"Music cache limit set to {limit} song(s).",
                ephemeral=True
            )
            await self.session.refresh_category("music")
        else:
            await interaction.response.send_message("Failed to update cache limit.", ephemeral=True)


class PlexLibraryModal(discord.ui.Modal, title="Set Plex Library"):
    library: discord.ui.TextInput

    def __init__(self, session: ConfigSession, current_library: Optional[str]):
        super().__init__(timeout=None)
        self.session = session
        default_library = current_library or session.cog.global_config.get('plex', {}).get('music_library', 'Music')
        self.library = discord.ui.TextInput(
            label="Library Section Name",
            default=default_library,
            placeholder="Leave empty to use global default",
            required=False,
            max_length=100
        )
        self.add_item(self.library)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not self.session.is_authorized(interaction.user):
            await interaction.response.send_message(
                "You need administrator permissions to modify these settings.",
                ephemeral=True
            )
            return

        if not self.session.cog.is_plex_ready():
            await interaction.response.send_message(
                "Plex integration isn't configured yet. Update `global_config.yaml` first.",
                ephemeral=True
            )
            return

        value = self.library.value.strip()
        if not value:
            removed = self.session.cog.delete_config(interaction.guild.id, 'plex_library')
            if removed:
                await interaction.response.send_message(
                    "Cleared Plex library override. Using global default.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "There was no Plex library override to clear.",
                    ephemeral=True
                )
        else:
            success = self.session.cog.set_config(
                interaction.guild.id,
                'plex_library',
                value,
                'string',
                'Preferred Plex library section for music playback'
            )

            if success:
                await interaction.response.send_message(
                    f"Plex library set to **{value}**.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "Failed to update Plex library.",
                    ephemeral=True
                )

        await self.session.refresh_category("music")


class GeneralConfigView(ConfigCategoryView):
    def __init__(self, session: ConfigSession, configs: Dict[str, Any]):
        super().__init__(session, "general", configs)

    @discord.ui.button(emoji="🔤", label="Prefix", style=discord.ButtonStyle.secondary)
    async def set_prefix(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        modal = PrefixModal(self.session)
        await interaction.response.send_modal(modal)

    @discord.ui.button(emoji="💬", label="Auto Responses", style=discord.ButtonStyle.primary)
    async def toggle_auto_responses(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        result = self.session.cog._toggle_boolean_config(
            interaction.guild.id,
            'auto_responses',
            'Enable automatic conversational responses from the bot',
            default=True
        )

        if result is None:
            await interaction.response.send_message("Failed to toggle auto responses.", ephemeral=True)
            return

        status = "enabled" if result else "disabled"
        await interaction.response.send_message(
            f"Auto responses are now **{status}**.",
            ephemeral=True
        )
        await self.session.refresh_category("general")

    @discord.ui.button(emoji="📜", label="Logging", style=discord.ButtonStyle.primary)
    async def toggle_logging(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        result = self.session.cog._toggle_boolean_config(
            interaction.guild.id,
            'logging_enabled',
            'Enable activity logging features for the bot',
            default=True
        )

        if result is None:
            await interaction.response.send_message("Failed to toggle logging setting.", ephemeral=True)
            return

        status = "enabled" if result else "disabled"
        await interaction.response.send_message(
            f"Activity logging is now **{status}**.",
            ephemeral=True
        )
        await self.session.refresh_category("general")


class PrefixModal(discord.ui.Modal, title="Set Command Prefix"):
    prefix: discord.ui.TextInput

    def __init__(self, session: ConfigSession):
        super().__init__(timeout=None)
        self.session = session
        self.prefix = discord.ui.TextInput(label="Prefix", min_length=1, max_length=5, default="!")
        self.add_item(self.prefix)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        value = self.prefix.value.strip()
        if not value:
            await interaction.response.send_message("Prefix cannot be empty.", ephemeral=True)
            return

        success = self.session.cog.set_config(
            interaction.guild.id,
            'command_prefix',
            value,
            'string',
            'Primary command prefix for the bot in this server'
        )

        if success:
            await interaction.response.send_message(
                f"Command prefix updated to `{value}`.",
                ephemeral=True
            )
            await self.session.refresh_category("general")
        else:
            await interaction.response.send_message("Failed to update prefix.", ephemeral=True)
