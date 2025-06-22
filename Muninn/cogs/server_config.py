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
                return True
        except Exception as e:
            print(f"Error setting config {key} for guild {guild_id}: {e}")
            return False
    
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
            embed = discord.Embed(
                title="Server Configuration 🔧",
                description="Manage server-wide settings for various bot features.",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Commands",
                value=(
                    "`!config list` - Show all current settings\n"
                    "`!config set <key> <value>` - Set a configuration value\n"
                    "`!config get <key>` - Get a specific configuration value\n"
                    "`!config delete <key>` - Delete a configuration value\n"
                    "`!config devotion_channel <#channel>` - Set devotion channel"
                ),
                inline=False
            )
            embed.set_footer(text="Only administrators can modify server configuration")
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
                title="Devotion Channel Set ✅",
                description=f"Daily devotion check-ins will now be sent to {channel.mention}",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="Error Setting Channel ❌",
                description="Failed to set the devotion channel. Please try again.",
                color=discord.Color.red()
            )
        
        await ctx.send(embed=embed)

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
