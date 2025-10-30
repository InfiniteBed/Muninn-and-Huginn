import discord  # type:ignore
from discord import app_commands # type:ignore
import discord.ext.commands as commands  # type:ignore
import sqlite3
import importlib
from . import list_menu as list_menu  # import the module, not the class

class AddPersonalitySuccessView(discord.ui.View):
    def __init__(self, personality_data, bird_data, db=None, past_interaction=None):
        super().__init__(timeout=300)
        self.personality_data = personality_data
        self.bird_data = bird_data
        self.db = db

    async def get_embed(self):
        embed = discord.Embed(
            title="Personality Assigned!",
            description=f"Successfully assigned personality to {self.bird_data['FirstName']} {self.bird_data['LastName']}.",
            color=discord.Color.green()
        )
        
        await self.db.post("PersonalityTag", {
            "BirdId": self.bird_data["Id"], 
            "TagTypeId": self.personality_data["Id"]
        })

        return embed

    async def get_view(self, past_interaction=None):
        return self

    @discord.ui.button(label="Add Another", style=discord.ButtonStyle.green)
    async def add_another(self, interaction: discord.Interaction, button: discord.ui.Button):
        lm = self.db.bot.get_cog("ListMenu")
        personality_types = await self.db.get("PersonalityType")
        list_menu = lm.make(
            lines=[f"{pt['Name']} (ID: {pt['Id']})" for pt in personality_types],
            data=personality_types,
            title="Add Personality",
            detailview_cls=AddPersonalitySuccessView,
            detailview_init_kwargs={'bird_data': self.bird_data},
            items_per_page=10,
            max_item_buttons=10,
        )
        
        # Rebuild buttons and get embed for the new menu
        await list_menu._rebuild_item_buttons()
        embed = list_menu.get_page_embed()

        # Edit the existing message with the new menu
        await interaction.response.edit_message(embed=embed, view=list_menu)
        

class Bird(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.get_cog("Database")
        self.input = bot.get_cog("UserInput")
        # Do not assume a callable from a cog; we’ll handle it in the command
        # self.selectlistview = bot.get_cog("SelectListMenuEmbed")
        
    class BirdDetailView(discord.ui.View):
        def __init__(self, bird_data, db=None, past_interaction=None):
            super().__init__(timeout=300)
            self.bird_data = bird_data
            self.db = db
            self.past_interaction = past_interaction
            
        async def get_personality_tags(self):
            tags = await self.db.get("PersonalityTag", f"BirdId = {self.bird_data['Id']}")
            tag_types = []
            for tag in tags:
                tag_type = await self.db.get_one("PersonalityType", f"Id = {tag['TagTypeId']}")
                if tag_type:
                    tag_types.append(tag_type['Name'])
            return tag_types if tag_types else ["None"]

        async def get_embed(self):
            personality_tags = await self.get_personality_tags()
            embed = discord.Embed(
                title=f"Manage {self.bird_data['FirstName']} {self.bird_data['LastName']}",
                description=f"Personality Tags: {', '.join(personality_tags)}"
            )
            return embed

        async def get_view(self, past_interaction=None):
            self.past_interaction = past_interaction
            return self

        @discord.ui.button(label="Add Personality", style=discord.ButtonStyle.grey)
        async def add_personality(self, interaction: discord.Interaction, button: discord.ui.Button):
            # Create list menu to select personality
            lm = self.db.bot.get_cog("ListMenu")
            personality_types = await self.db.get("PersonalityType")
            list_menu = lm.make(
                lines=[f"{pt['Name']} (ID: {pt['Id']})" for pt in personality_types],
                data=personality_types,
                title="Add Personality",
                detailview_cls=AddPersonalitySuccessView,
                detailview_init_kwargs={'bird_data': self.bird_data},
                items_per_page=10,
                max_item_buttons=10,
            )
            await list_menu.send_initial_message(interaction)
            
        @discord.ui.button(label="Back", style=discord.ButtonStyle.grey)
        async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
            lm = self.db.bot.get_cog("ListMenu")
            birds = await self.db.get("Bird", f"UserId = {self.bird_data['UserId']}")
            list_menu = lm.make(
                lines=[f"{index}. {b['FirstName']} {b['LastName']} (ID: {b['Id']})" for index, b in enumerate(birds, start=1)],
                data=birds,
                title=f"{interaction.user.nick}'s Birds – Manage",
                detailview_cls=Bird.BirdDetailView,
                items_per_page=10,
                max_item_buttons=10,
            )
            await interaction.message.delete()
            await list_menu.send_initial_message(interaction)

    async def get_species_choices(self):
        species = await self.db.get("Species")
        return [(row["Name"], row["Id"]) for row in species]

    @commands.hybrid_command(name="add_bird")  ## Adds a bird to the user's flock
    @app_commands.describe(
        first_name="The bird's first name",
        last_name="The bird's last name",
        gender="The bird's gender (male or female)",
        size="The bird's size",
        color="The bird's color",
        species="The bird's species"
    )
    async def add_bird(
        self, 
        ctx, 
        first_name: str = "", 
        last_name: str = "", 
        gender: str = "",
        size: str = "", 
        color: str = "", 
        species: str = ""
    ):
        # Ensure user is registered
        user = await self.db.get_one("User", f"DiscordUserId = {ctx.author.id}")
        if not user:
            user_data = {
                "DiscordUserId": ctx.author.id,
                "Name": ctx.author.nick or ctx.author.name
            }
            
            await self.db.post("User", user_data)       
            user = await self.db.get_one("User", f"DiscordUserId = {ctx.author.id}")     

        species_acceptable_values = [row["Name"] for row in await self.db.get("Species")]
        
        first_name = first_name or await self.input.prompt(ctx, 
            question="Please enter the bird's first name:", 
            type=str, 
            embed_color=discord.Color.green(),
            require_confirmation=False
        )
        if first_name.lower() == 'stop':
            await ctx.send("Bird creation cancelled.")
            return
        last_name = last_name or await self.input.prompt(ctx, 
            question="Now enter the bird's last name:", 
            type=str, 
            embed_color=discord.Color.green(),
            require_confirmation=False
        )
        if last_name.lower() == 'stop':
            await ctx.send("Bird creation cancelled.")
            return
        gender_string = await self.input.prompt(ctx, 
            question="Great! Please enter the bird's gender (male or female):", 
            type=str, 
            acceptable_values=["male", "female"], 
            embed_color=discord.Color.green(),
            require_confirmation=False
        )
        size = size or await self.input.prompt(ctx, 
            question="Next enter the bird's size:", 
            type=str, 
            acceptable_values=[], 
            embed_color=discord.Color.green(),
            require_confirmation=False
        )
        if size.lower() == 'stop':
            await ctx.send("Bird creation cancelled.")
            return
        color = color or await self.input.prompt(ctx, 
            question="Please enter the bird's color:", 
            type=str, 
            acceptable_values=[], 
            embed_color=discord.Color.green(),
            require_confirmation=False
        )
        if color.lower() == 'stop':
            await ctx.send("Bird creation cancelled.")
            return
        species = await self.input.prompt(ctx, 
            question="Almost done! enter the bird's species:", 
            body="Available species: " + ", ".join(species_acceptable_values),
            type=str, 
            acceptable_values=species_acceptable_values, 
            embed_color=discord.Color.green(),
            require_confirmation=False
        )
        
        if gender_string.lower() == "male":
            gender = 0
        else:
            gender = 1

        # Resolve species name to its ID
        species_id = None
        species_rows = await self.db.get("Species")
        if species:
            exact = [r for r in species_rows if r["Name"].lower() == species.lower()]
            if exact:
                species_id = exact[0]["Id"]
            else:
                partial = [r for r in species_rows if species.lower() in r["Name"].lower()]
                if len(partial) == 1:
                    species_id = partial[0]["Id"]
                elif len(partial) > 1:
                    await ctx.send(f"Multiple matches: {[r['Name'] for r in partial[:10]]}. Please be more specific.")
                    return
                elif species.isdigit():
                    species_id = int(species)

        bird_data = {
            "UserId": user["Id"],
            "FirstName": first_name,
            "LastName": last_name,
            "Gender": gender,
            "Size": size,
            "Color": color,
            "SpeciesId": species_id
        }
        await self.db.post("Bird", bird_data)

        # Set as primary if user has none
        user = await self.db.get_one("User", f"DiscordUserId = {ctx.author.id}")
        if user and user["PrimaryBirdId"] is None:
            bird = await self.db.get_one(
                "Bird",
                f"UserId = {user['Id']} AND FirstName = '{first_name}' AND LastName = '{last_name}' AND SpeciesId = {species_id} ORDER BY CreatedDateTime DESC LIMIT 1"
            )
            if bird:
                await self.db.patch("User", {"PrimaryBirdId": bird["Id"]}, user["Id"])
                await ctx.send(f"{first_name} {last_name} added and set as your primary bird.")
                return
        else:
            bird = await self.db.get_one(
                "Bird",
                f"UserId = {user['Id']} AND FirstName = '{first_name}' AND LastName = '{last_name}' AND SpeciesId = {species_id} ORDER BY CreatedDateTime DESC LIMIT 1"
            )

        ## get default housing for birds
        default_housing = await self.db.get_one("HousingComplex", "IsBirdCreationDefault = 1")
        # set bird's default housing randomly, checking for occupancy so we dont overlap
        rooms_count = await self.db.get("HousingUnit", f"HousingComplexId = {default_housing['Id']}")
        if rooms_count:
            import random
            # check if room is occupied
            occupied = True
            while occupied:
                room = random.choice(rooms_count)
                room_data = await self.db.get_one("HousingUnit", f"Id = {room['Id']}")
                occupied = room_data['OccupantBirdId'] is not None
            await self.db.patch("HousingUnit", {"OccupantBirdId": bird['Id']}, room['Id'])
        
        embed = discord.Embed(
            title=f"{first_name} {last_name} added successfully!", 
            description=f"{'She' if gender else 'He'} is now at the {default_housing['Name']} at Room {room['Name']}.\nUse `/housing` to view your bird's housing.",
            color=discord.Color.green())
        await ctx.send(embed=embed)
        
    @commands.hybrid_command(name="my_birds")  ## Lists all birds in the user's flock
    async def my_birds(self, ctx):
        user = await self.db.get_one("User", f"DiscordUserId = {ctx.author.id}")
        if not user:
            await ctx.send("You are not registered in Flock Together. Use `/register` to register.")
            return
        
        birds = await self.db.get("Bird", f"UserId = {user['Id']}")
        if not birds:
            await ctx.send("You have no birds in your flock. Use `/add_bird` to add one.")
            return
        
        lm = self.bot.get_cog("ListMenu")

        menu = lm.make(
            lines=[f"{index}. {b['FirstName']} {b['LastName']} (ID: {b['Id']})" for index, b in enumerate(birds, start=1)],
            data=birds,
            title=f"{ctx.author.nick}'s Birds – Manage",
            items_per_page=10,
            detailview_cls=self.BirdDetailView,
            max_item_buttons=10,
        )
        await menu.send_initial_message(ctx)
        
    
        
async def setup(bot):
    bird = Bird(bot)
    await bot.add_cog(bird)