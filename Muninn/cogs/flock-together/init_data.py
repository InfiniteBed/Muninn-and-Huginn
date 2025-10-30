import discord  # type:ignore
import discord.ext.commands as commands  # type:ignore
import sqlite3

class InitData(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.get_cog("Database")
        
    async def initialize_data(self):
        # Placeholder for data initialization logic
        print("Initializing Flock Together data...")

        self.conn = sqlite3.connect("data/flock-together.db")
        self.cursor = self.conn.cursor()

        # Create tables if they don't exist
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS User (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                DiscordUserId INTEGER NOT NULL,
                CreatedDateTime INTEGER,
                Name TEXT,
				Shinies INTEGER DEFAULT 0,
                PrimaryBirdId INTEGER,
                ServerId INTEGER,
                FOREIGN KEY (PrimaryBirdId) REFERENCES Bird (Id),
                FOREIGN KEY (ServerId) REFERENCES Server (Id)
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS Bird (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                UserId INTEGER,
                FirstName TEXT,
                LastName TEXT,
                SpeciesId INTEGER,
                Color TEXT, 
                Gender INTEGER,
                Size TEXT,
				IsDeceased INTEGER,
                CreatedByUserId INTEGER,
                CreatedDateTime TEXT,
				ServerId INTEGER,
                FOREIGN KEY (UserId) REFERENCES User (Id),
				FOREIGN KEY (ServerId) REFERENCES Server (Id)
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS Species (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                Name TEXT NOT NULL,
                CreatedByUserId INTEGER,
                CreatedDateTime TEXT NOT NULL
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS Relationship (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                FromBird INTEGER,
                ToBird INTEGER,
                StartDateTime TEXT,
                EndDateTime TEXT,
                RelationshipType TEXT NOT NULL,
                Note TEXT,
                FOREIGN KEY (FromBird) REFERENCES Bird (Id),
                FOREIGN KEY (ToBird) REFERENCES Bird (Id)
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS AttributeValue (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                BirdId INTEGER,
                AttributeTypeId INTEGER NOT NULL,
                Value TEXT,
                CreatedByUserId INTEGER,
                CreatedDateTime TEXT,
                FOREIGN KEY (BirdId) REFERENCES Bird (Id),
                FOREIGN KEY (AttributeTypeId) REFERENCES Attribute (Id)
                
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS Attribute (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                Name TEXT NOT NULL,
                Description TEXT,
                CreatedByUserId INTEGER,
                CreatedDateTime TEXT
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS Food (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                Name TEXT NOT NULL,
                Description TEXT,
                CreatedByUserId INTEGER,
                CreatedDateTime TEXT
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS FoodItem (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                UserId INTEGER NOT NULL,
                FoodId INTEGER NOT NULL,
                CreatedDateTime TEXT,
                FOREIGN KEY (FoodId) REFERENCES Food (Id)
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS PersonalityType (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                Name TEXT NOT NULL,
                Description TEXT,
                CreatedByUserId INTEGER,
                CreatedDateTime TEXT
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS PersonalityTag (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                TagTypeId INTEGER NOT NULL,
                BirdId INTEGER NOT NULL,
                CreatedDateTime TEXT,
                FOREIGN KEY (TagTypeId) REFERENCES PersonalityType (Id),
                FOREIGN KEY (BirdId) REFERENCES Bird (Id)
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS Response (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                Response TEXT NOT NULL,
                CreatedByUserId INTEGER,
                CreatedDateTime TEXT
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS ResponsePersonalityType (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                ResponseId INTEGER NOT NULL,
                PersonalityTypeId INTEGER NOT NULL,
                CreatedByUserId INTEGER,
                CreatedDateTime TEXT,
                FOREIGN KEY (ResponseId) REFERENCES Response (Id),
                FOREIGN KEY (PersonalityTypeId) REFERENCES PersonalityType (Id)
            )
        """)

        self.cursor.execute("""
			CREATE TABLE IF NOT EXISTS HousingComplex (
				Id INTEGER PRIMARY KEY AUTOINCREMENT,
				Name TEXT NOT NULL,
				OwnerBirdId INTEGER,
				ChargesRent INTEGER
				RentAmount INTEGER,
				RentPeriod INTEGER,
				RentPeriodOccurence INTEGER,
				ServerId INTEGER,
				CreatedByUserId INTEGER,
				CreatedDateTime TEXT,
				IsBirdCreationDefault INTEGER,
				FOREIGN KEY (OwnerBirdId) REFERENCES Bird (Id)
			)
		""")
			
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS HousingFloor (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                Name TEXT NOT NULL,
                HousingComplexId INTEGER NOT NULL,
                FloorNumberFriendly INTEGER NOT NULL,
                FloorNumber INTEGER NOT NULL,
                CreatedByUserId INTEGER,
                CreatedDateTime TEXT,
                FOREIGN KEY (HousingComplexId) REFERENCES HousingComplex (Id)
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS HousingUnit (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                Name TEXT NOT NULL,
                UnitNumber INTEGER NOT NULL,
                HousingComplexId INTEGER NOT NULL,
                HousingFloorId INTEGER NOT NULL,
                OccupantBirdId INTEGER,
                CreatedByUserId INTEGER,
                CreatedDateTime TEXT,
                FOREIGN KEY (OccupantBirdId) REFERENCES Bird (Id),
                FOREIGN KEY (HousingFloorId) REFERENCES HousingFloor (Id),
                FOREIGN KEY (HousingComplexId) REFERENCES HousingComplex (Id)
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS Server (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                Name TEXT NOT NULL,
                DiscordServerId INTEGER NOT NULL,
                CreatedDateTime TEXT
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS Location (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                Name TEXT NOT NULL,
                CreatedByUserId INTEGER,
                CreatedDateTime TEXT
            )
        """)
        
        self.conn.commit()
        
        for guild in self.bot.guilds:
            if guild.id in [row["DiscordServerId"] for row in await self.db.get("Server")]:
                continue
            await self.db.post("Server", {
                "Name": guild.name,
                "DiscordServerId": guild.id
            })

        print("Flock Together data initialized.")

    async def close_connection(self):
        self.cursor.close()
        self.conn.close()
        
async def setup(bot):
    init_data = InitData(bot)
    await init_data.initialize_data()
    await bot.add_cog(init_data)