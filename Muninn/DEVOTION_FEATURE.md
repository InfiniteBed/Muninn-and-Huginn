# Bible/Devotion Accountability Feature

## Overview
This new cog implements Screamer's requested Bible and devotion accountability feature for the Muninn Discord bot. It provides daily check-ins to encourage community members to read their Bible and talk to God, fostering accountability and spiritual growth.

## Features

### 🕕 Daily Scheduled Check-ins
- Automatically sends a daily message at **5:30 PM Pacific Time**
- Asks: "Did you read your Bible and/or talk to God today?"
- Sends to the specified channel (currently set to the same channel as meals)

### 📝 Response Options
Users can respond with interactive buttons:
- **"Yes! 🙌"** - Opens a modal for sharing details
- **"Not yet! ⏰"** - Encouraging response with motivation to continue
- **"No ❌"** - Supportive response for tomorrow's opportunity

### 💬 Public Sharing (Privacy-Conscious)
When users select "Yes!":
- Modal popup asks for "When" (required) and "What God was leading them to" (optional)
- Responses are shared publicly as embeds to encourage others
- Clear disclaimer that responses will be public
- Users can be as vague or detailed as they're comfortable with

### 📊 Statistics & Tracking
- **`!devotion_stats [days]`** - Server-wide statistics showing participation rates
- **`!my_devotions [days]`** - Personal devotion history for users
- All responses logged to database with timestamps
- Prevents duplicate responses per day

### 🎯 Manual Commands
- **`!devotion`** - Manually trigger the daily check-in message
- **`!test_devotion`** - Test command to verify the system is working

## Database Schema
Creates a new table `devotion_responses`:
```sql
CREATE TABLE IF NOT EXISTS devotion_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    response_type TEXT NOT NULL,    -- 'yes', 'no', 'not_yet'
    when_text TEXT,                 -- When they had devotion time
    what_text TEXT,                 -- What God was leading them to
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_responded DATE NOT NULL    -- For preventing duplicate daily responses
)
```

## Technical Implementation

### Key Components
1. **DevotionAccountability** - Main cog class with scheduling and database management
2. **DevotionView** - Discord UI View with interactive buttons
3. **DevotionModal** - Modal for collecting "when" and "what" responses
4. **Database logging** - Tracks all responses for statistics and personal history

### Scheduling
- Uses `@tasks.loop` with Pacific timezone scheduling
- Matches the existing pattern used by the meals cog
- Runs daily at 5:30 PM PT (late afternoon/early evening as requested)

### Privacy & Community Balance
- Clear disclaimer about public sharing
- Optional "what" field for spiritual reflections
- Encouraging responses for all answer types
- Prevents spam with once-per-day response tracking

## Installation & Setup

1. The cog file is located at `/mnt/Lake/Starboard/Discord/Muninn/cogs/devotion.py`
2. Update the `target_channel_id` in the cog to match your desired channel
3. The bot will automatically load the cog and start the daily schedule
4. Help documentation has been added to `helpme.py` under "Faith & Devotion"

## Example Usage

Daily automated message:
```
📝 Daily Faith Check-In 🙏

Hey everyone! Time for our daily accountability check-in!

Did you read your Bible and/or talk to God today?

Note: If you select 'Yes!', you'll be asked to share when and optionally what 
the Holy Spirit was leading you to. Your response will be shared publicly to 
encourage others, but feel free to be as vague or detailed as you're comfortable with!

[Yes! 🙌] [Not yet! ⏰] [No ❌]
```

When someone clicks "Yes!", they get a modal:
```
When did you have your devotion time?
> "This morning during coffee"

What was the Holy Spirit leading you to? (Optional)
> "Patience and trusting in God's timing"
```

This creates a public embed:
```
🙏 Screamer's Bible Reading/Prayer Time Sharing

When: This morning during coffee
What God was leading me to: Patience and trusting in God's timing

🙏 Keep growing in faith together!
```

## Community Impact
This feature addresses Screamer's desire for:
- ✅ Accountability for Bible reading and prayer
- ✅ Community encouragement and sharing
- ✅ Growing in faith together
- ✅ Flexible sharing (vague or detailed)
- ✅ Daily reminders for those who "forgot"
- ✅ Late afternoon/evening timing
