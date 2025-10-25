#!/bin/bash

# Advanced Graph System - Installation & Test Script
# Run this to set up and verify the new graph system

echo "🚀 Advanced Graph System - Setup Script"
echo "========================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Step 1: Check if we're in the right directory
echo "📁 Checking directory..."
if [ ! -f "requirements.txt" ]; then
    echo -e "${RED}❌ Error: requirements.txt not found${NC}"
    echo "Please run this script from the Muninn directory"
    exit 1
fi
echo -e "${GREEN}✅ In correct directory${NC}"
echo ""

# Step 2: Install dependencies
echo "📦 Installing dependencies..."
echo "This may take a minute..."

if pip install -r requirements.txt > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Dependencies installed successfully${NC}"
else
    echo -e "${RED}❌ Error installing dependencies${NC}"
    echo "Try manually: pip install -r requirements.txt"
    exit 1
fi
echo ""

# Step 3: Verify seaborn installation
echo "🔍 Verifying seaborn installation..."
if python3 -c "import seaborn" 2>/dev/null; then
    echo -e "${GREEN}✅ Seaborn installed and importable${NC}"
else
    echo -e "${YELLOW}⚠️  Seaborn not found, attempting install...${NC}"
    pip install seaborn
fi
echo ""

# Step 4: Verify matplotlib
echo "🔍 Verifying matplotlib installation..."
if python3 -c "import matplotlib.pyplot" 2>/dev/null; then
    echo -e "${GREEN}✅ Matplotlib installed and importable${NC}"
else
    echo -e "${RED}❌ Matplotlib not found${NC}"
    exit 1
fi
echo ""

# Step 5: Check file structure
echo "📂 Checking file structure..."
files_to_check=(
    "cogs/advanced_graphs.py"
    "cogs/statistics_tracker.py"
    "cogs/graphs/discord_theme.py"
    "GRAPH_SYSTEM.md"
    "QUICKSTART_GRAPHS.md"
    "GRAPH_OVERHAUL_SUMMARY.md"
)

all_files_exist=true
for file in "${files_to_check[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✅ $file${NC}"
    else
        echo -e "${RED}❌ $file not found${NC}"
        all_files_exist=false
    fi
done
echo ""

if [ "$all_files_exist" = false ]; then
    echo -e "${RED}❌ Some files are missing${NC}"
    exit 1
fi

# Step 6: Check fonts directory
echo "🔤 Checking fonts..."
if [ -d "fonts" ]; then
    echo -e "${GREEN}✅ Fonts directory exists${NC}"
    if [ -f "fonts/Uni Sans Heavy.otf" ]; then
        echo -e "${GREEN}✅ Uni Sans Heavy font found${NC}"
    else
        echo -e "${YELLOW}⚠️  Uni Sans Heavy font not found (graphs will use fallback)${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Fonts directory not found (graphs will use fallback fonts)${NC}"
fi
echo ""

# Step 7: Verify Python syntax
echo "🐍 Checking Python syntax..."
if python3 -m py_compile cogs/advanced_graphs.py 2>/dev/null; then
    echo -e "${GREEN}✅ Python syntax valid${NC}"
else
    echo -e "${RED}❌ Syntax errors in advanced_graphs.py${NC}"
    exit 1
fi
echo ""

# Step 8: Check database
echo "💾 Checking database..."
if [ -f "discord.db" ]; then
    echo -e "${GREEN}✅ Database file exists${NC}"
    
    # Check if user_activity table exists
    if sqlite3 discord.db "SELECT name FROM sqlite_master WHERE type='table' AND name='user_activity';" | grep -q "user_activity"; then
        echo -e "${GREEN}✅ user_activity table exists${NC}"
        
        # Count records
        record_count=$(sqlite3 discord.db "SELECT COUNT(*) FROM user_activity;")
        echo -e "${GREEN}✅ Database has $record_count message records${NC}"
        
        if [ "$record_count" -eq 0 ]; then
            echo -e "${YELLOW}⚠️  No messages in database - run !import_data in Discord${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️  user_activity table doesn't exist yet${NC}"
        echo -e "${YELLOW}   Run the bot to create tables automatically${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Database not found - will be created on first run${NC}"
fi
echo ""

# Step 9: Summary
echo "================================"
echo "🎉 Setup Complete!"
echo "================================"
echo ""
echo "Next steps:"
echo "1. Start your bot"
echo "2. In Discord, run: !graphs"
echo "3. Click buttons to test different graph types"
echo ""
echo "📚 Documentation:"
echo "   - Quick start: QUICKSTART_GRAPHS.md"
echo "   - Full docs:   GRAPH_SYSTEM.md"
echo "   - Changes:     GRAPH_OVERHAUL_SUMMARY.md"
echo ""
echo "💡 Tips:"
echo "   - If no data: Run !import_data first"
echo "   - Test with:  !graphs @username"
echo "   - Compare:    !graphs → Click 'Compare Users'"
echo ""
echo -e "${GREEN}✨ Ready to visualize! ✨${NC}"
