# Server Configuration System

## Overview
Created an extensible server configuration system that allows different cogs to store and retrieve server-specific settings in a centralized way.

## Files Created/Modified

### New Files:
- `cogs/server_config.py` - Main configuration cog
- `CONFIGURATION_SYSTEM.md` - This documentation

### Modified Files:
- `cogs/devotion.py` - Updated to use configuration system
- `cogs/helpme.py` - Added configuration commands to help

## Features

### ServerConfig Cog (`cogs/server_config.py`)
- **Extensible design** - Any cog can store configuration values
- **Type-safe storage** - Supports string, boolean, integer, and channel types
- **Database-backed** - Uses SQLite with proper indexing
- **Admin-only commands** - Requires administrator permissions

### Supported Data Types
- `string` - Text values
- `boolean` - True/false values  
- `integer` - Numeric values
- `channel` - Discord channel IDs with validation

### Commands Available

#### Configuration Management
- `!config` - Show configuration help
- `!config list` - List all server settings
- `!config get <key>` - Get specific value
- `!config delete <key>` - Delete a setting
- `!config devotion_channel <#channel>` - Set devotion channel

#### Devotion-Specific
- `!devotion_setup` - View devotion configuration status
- `!devotion` - Send manual devotion check-in (uses configured channel)

## Usage Examples

### Setting Up Devotion Channel
```
!config devotion_channel #faith-accountability
```

### Viewing Configuration
```
!config list
!devotion_setup
```

### Manual Devotion Check-in
```
!devotion
```

## Technical Implementation

### Database Schema
```sql
CREATE TABLE server_config (
    guild_id INTEGER NOT NULL,
    config_key TEXT NOT NULL,
    config_value TEXT,
    config_type TEXT DEFAULT 'string',
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, config_key)
);
```

### API Methods
```python
# Set configuration
server_config_cog.set_config(guild_id, 'key', value, 'type', 'description')

# Get configuration  
value = server_config_cog.get_config(guild_id, 'key', default_value)

# Delete configuration
server_config_cog.delete_config(guild_id, 'key')

# Get all configurations
configs = server_config_cog.get_all_config(guild_id)
```

## Devotion System Updates

### Scheduling Changes
- **Before**: Hardcoded channel ID `1298762960184934432`
- **After**: Uses configured channel per server via `devotion_channel` setting

### Daily Messages
- Sent at **5:30 PM Pacific Time** daily
- Only sent to servers with configured devotion channels
- Automatically handles multiple servers

### Manual Commands
- `!devotion` now uses configured channel or current channel with setup tip
- `!devotion_setup` shows configuration status and guidance

## Extensibility

### Adding New Configuration Types
```python
# In your cog's __init__:
def __init__(self, bot):
    self.bot = bot
    self.server_config = None

async def setup_hook(self):
    self.server_config = self.bot.get_cog('ServerConfig')

# Setting a new config type:
self.server_config.set_config(
    guild_id, 
    'my_feature_setting', 
    value, 
    'custom_type',
    'Description of what this setting does'
)
```

### Configuration Best Practices
1. **Use descriptive keys** - `devotion_channel` not `dev_ch`
2. **Include descriptions** - Help admins understand settings
3. **Provide defaults** - Always specify fallback values
4. **Validate input** - Check channel existence, value ranges, etc.
5. **Handle missing ServerConfig** - Gracefully degrade if cog unavailable

## Next Steps
1. Test the configuration system with a live bot
2. Add more configuration options as needed
3. Consider adding configuration export/import
4. Add configuration change logging
5. Create configuration backup/restore functionality

## Benefits
- **Centralized** - All server settings in one place
- **Extensible** - Easy to add new configuration options
- **Type-safe** - Proper data type handling
- **Admin-controlled** - Secure permission system
- **Persistent** - Database-backed storage
- **Scalable** - Works across multiple servers
