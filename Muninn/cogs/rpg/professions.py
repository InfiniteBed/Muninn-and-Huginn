import sqlite3
PROFESSIONS = [
    "baking", "brewing", "carting", "carpentry", "cleaning", "coachman", "cooking", "cupbearing",
    "farming", "fishing", "floristry", "gardening", "guarding", "glassblowing", "healing",
    "husbandry", "innkeeping", "knighthood", "leadership", "masonry", "metalworking",
    "painting", "pottery", "royalty", "sculpting", "smithing", "spinning", "stablekeeping",
    "tailoring", "teaching", "vigilance", "woodworking"
]
from discord.ext import commands

class ProfessionsLoader(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.item_randomizer = self.bot.get_cog("ItemRandomizer") # For Item and Expedition Info
        
    @commands.command()
    async def proff(self, ctx):
        conn = sqlite3.connect('discord.db')
        c = conn.cursor()

        print(PROFESSIONS)

        # Get existing columns
        c.execute("PRAGMA table_info(proficiencies)")
        existing_columns = {row[1] for row in c.fetchall()}
        
        # Add missing columns
        for profession in PROFESSIONS:
            if profession not in existing_columns:
                print(f"Adding missing column: {profession}")
                c.execute(f"ALTER TABLE proficiencies ADD COLUMN {profession} INTEGER DEFAULT 0")

        conn.commit()
        conn.close()

async def setup(bot):
    await bot.add_cog(ProfessionsLoader(bot))

