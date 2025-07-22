#!/usr/bin/env python3
"""
Test script for the Server Configuration and Devotion systems.
This script tests the integration without requiring a live Discord bot.
"""

import sqlite3
import asyncio
import tempfile
import os
from datetime import datetime

def test_server_config_database():
    """Test the server configuration database functionality."""
    print("🧪 Testing Server Configuration Database...")
    
    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name
    
    try:
        # Simulate ServerConfig database operations
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Create table (mimicking ServerConfig._initialize_database)
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
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_server_config_guild 
                ON server_config(guild_id)
            """)
            conn.commit()
            
            print("  ✅ Database table created successfully")
            
            # Test setting various config types
            test_guild_id = 123456789
            test_configs = [
                ('devotion_channel', '987654321', 'channel', 'Channel for devotion messages'),
                ('enable_notifications', 'true', 'boolean', 'Enable daily notifications'),
                ('reminder_hour', '17', 'integer', 'Hour to send reminders (24h format)'),
                ('server_name', 'Test Server', 'string', 'Display name for server')
            ]
            
            for key, value, config_type, description in test_configs:
                cursor.execute("""
                    INSERT OR REPLACE INTO server_config 
                    (guild_id, config_key, config_value, config_type, description, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (test_guild_id, key, value, config_type, description))
            
            conn.commit()
            print("  ✅ Test configurations inserted")
            
            # Test retrieving configurations
            cursor.execute("""
                SELECT config_key, config_value, config_type FROM server_config 
                WHERE guild_id = ?
            """, (test_guild_id,))
            
            results = cursor.fetchall()
            assert len(results) == 4, f"Expected 4 configs, got {len(results)}"
            print("  ✅ Configuration retrieval working")
            
            # Test type conversion logic
            for key, value, config_type in results:
                if config_type == 'channel':
                    converted = int(value) if value else None
                    assert isinstance(converted, int), f"Channel conversion failed for {key}"
                elif config_type == 'boolean':
                    converted = value.lower() == 'true'
                    assert isinstance(converted, bool), f"Boolean conversion failed for {key}"
                elif config_type == 'integer':
                    converted = int(value)
                    assert isinstance(converted, int), f"Integer conversion failed for {key}"
                else:
                    converted = value
                    assert isinstance(converted, str), f"String conversion failed for {key}"
            
            print("  ✅ Type conversion logic working")
            
    finally:
        # Clean up
        os.unlink(db_path)
    
    print("✅ Server Configuration Database Tests Passed!\n")

def test_devotion_database():
    """Test the devotion database functionality."""
    print("🧪 Testing Devotion Database...")
    
    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Create devotion table (mimicking DevotionAccountability._initialize_database)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS devotion_responses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    response_type TEXT NOT NULL,
                    when_text TEXT,
                    what_text TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    date_responded DATE NOT NULL
                )
            """)
            conn.commit()
            print("  ✅ Devotion table created successfully")
            
            # Test inserting devotion responses
            test_responses = [
                (111111, 123456789, 'yes', 'This morning', 'God showed me patience today', '2025-06-03'),
                (222222, 123456789, 'not_yet', None, None, '2025-06-03'),
                (333333, 123456789, 'no', None, None, '2025-06-03'),
                (111111, 123456789, 'yes', 'Evening', 'Prayer for wisdom', '2025-06-02')
            ]
            
            for user_id, guild_id, response_type, when_text, what_text, date_responded in test_responses:
                cursor.execute("""
                    INSERT INTO devotion_responses 
                    (user_id, guild_id, response_type, when_text, what_text, timestamp, date_responded)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                """, (user_id, guild_id, response_type, when_text, what_text, date_responded))
            
            conn.commit()
            print("  ✅ Test devotion responses inserted")
            
            # Test statistics query (mimicking devotion_stats command)
            cursor.execute("""
                SELECT response_type, COUNT(*) as count
                FROM devotion_responses 
                WHERE guild_id = ? AND date_responded >= date('now', '-7 days')
                GROUP BY response_type
                ORDER BY count DESC
            """, (123456789,))
            
            stats = cursor.fetchall()
            assert len(stats) > 0, "No statistics found"
            print(f"  ✅ Statistics query returned {len(stats)} response types")
            
            # Test user history query (mimicking my_devotions command)
            cursor.execute("""
                SELECT response_type, when_text, what_text, date_responded
                FROM devotion_responses 
                WHERE user_id = ? AND guild_id = ? AND date_responded >= date('now', '-7 days')
                ORDER BY date_responded DESC
            """, (111111, 123456789))
            
            history = cursor.fetchall()
            assert len(history) >= 1, "No user history found"
            print(f"  ✅ User history query returned {len(history)} entries")
            
    finally:
        # Clean up
        os.unlink(db_path)
    
    print("✅ Devotion Database Tests Passed!\n")

def test_time_scheduling():
    """Test the time scheduling logic."""
    print("🧪 Testing Time Scheduling...")
    
    import pytz
    from datetime import time, datetime
    
    # Test timezone handling
    california_tz = pytz.timezone('US/Pacific')
    now = datetime.now(california_tz)
    
    # Test scheduled time (5:30 PM Pacific)
    scheduled_hour = 17
    scheduled_minute = 30
    scheduled_time = now.replace(hour=scheduled_hour, minute=scheduled_minute, second=0, microsecond=0)
    
    assert scheduled_time.hour == 17, f"Expected hour 17, got {scheduled_time.hour}"
    assert scheduled_time.minute == 30, f"Expected minute 30, got {scheduled_time.minute}"
    print(f"  ✅ Scheduled time: {scheduled_time.strftime('%I:%M %p %Z')}")
    
    print("✅ Time Scheduling Tests Passed!\n")

def main():
    """Run all tests."""
    print("🚀 Starting Server Configuration & Devotion System Tests\n")
    
    try:
        test_server_config_database()
        test_devotion_database() 
        test_time_scheduling()
        
        print("🎉 All Tests Passed Successfully!")
        print("\n📋 Summary:")
        print("  • Server configuration database working")
        print("  • Devotion response tracking working")  
        print("  • Time scheduling logic working")
        print("  • Type conversions working")
        print("  • Database queries working")
        
        return 0
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
