import discord  # type:ignore
from discord import app_commands # type:ignore
from discord.ui import View, Button  # type:ignore
import discord.ext.commands as commands  # type:ignore
import random

class Housing(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.input = bot.get_cog("UserInput")
        self.db = bot.get_cog("Database")
        self.list_menu = bot.get_cog("ListMenu")
        self.user = bot.get_cog("User")
    
    @commands.hybrid_command(name="create_housing")  ## Creates housing for the user
    @commands.is_owner()
    async def create_housing(self, ctx):
        name = await self.input.prompt(
            ctx,
            question="Enter the name of your housing:",
            type=str,
            embed_color=discord.Color.purple()
        )
        charges_rent = await self.input.prompt(
            ctx,
            question="Does this housing charge rent? (1 for Yes, 0 for No):",
            type=int,
            embed_color=discord.Color.purple(),
            acceptable_values=[0, 1]
        )
        
        complex = await self.db.post("HousingComplex", {
            "Name": name,
            "ChargesRent": charges_rent,
            "ServerId": (await self.db.get_one("Server", f"DiscordServerId = {ctx.guild.id}"))["Id"],
            "CreatedByUserId": ctx.author.id
        })
        
        floor_count = await self.input.prompt(
            ctx,
            question="How many floors does this housing have?",
            type=int,
            embed_color=discord.Color.pink()
        )
        starting_floor = await self.input.prompt(
            ctx,
            question="What is the starting floor number for this housing?\n(e.g., enter -1 for basement, 0 for ground floor, 1 for first floor, etc.)",
            type=int,
            embed_color=discord.Color.pink()
        )
        conventional_floor_naming = await self.input.prompt(
            ctx,
            question="Does this housing use conventional floor and unit naming? (1 for Yes, 0 for No)\nWarning: Choosing 'No' will require you to manually name each floor and unit. This will take a very long time for large buildings.",
            type=int,
            embed_color=discord.Color.pink(),
            acceptable_values=[0, 1]
        )        

        unit_number_machine = 0
        for floor_number in range(1, floor_count + 1): ## if floor count is 1
            if not conventional_floor_naming:
                floor_name = await self.input.prompt(
                    ctx,
                    question=f"What is the name of floor {starting_floor + floor_number - 1}?",
                    type=str,
                    embed_color=discord.Color.orange()
                )
            else:
                floor_name = f"Floor {starting_floor + floor_number - 1}"
            
            
            floor = await self.db.post("HousingFloor", {
                "HousingComplexId": complex["Id"],
                "FloorNumber": floor_number,
                "FloorNumberFriendly": starting_floor + floor_number - 1,
                "Name": floor_name,
                "CreatedByUserId": ctx.author.id
            })
            
            unit_count = await self.input.prompt(
                ctx,
                question=f"How many units are on floor {starting_floor + floor_number - 1}?",
                type=int,
                embed_color=discord.Color.orange()
            )
            for unit_number in range(1, unit_count + 1):
                if conventional_floor_naming:
                    unit_number = unit_number + ((floor_number) * 100)  ## e.g., 101, 102, 201, 202, etc.
                else:
                    unit_number = await self.input.prompt(
                        ctx,
                        question=f"What is the unit number for unit {unit_number} on floor {starting_floor + floor_number - 1}?",
                        type=int,
                        embed_color=discord.Color.orange()
                    )
                    
                await self.db.post("HousingUnit", {
                    "HousingComplexId": complex["Id"],
                    "HousingFloorId": floor["Id"],
                    "UnitNumber": unit_number_machine,
                    "Name": f"Unit {unit_number}",
                    "CreatedByUserId": ctx.author.id
                })
                
                unit_number_machine = unit_number_machine + 1
          
    @commands.hybrid_command(name="starter_housing")  ## Patches housing complex details
    @commands.has_permissions(administrator=True)
    async def starter_housing(self, ctx):
        if self.db.get("HousingComplex", f"ServerId = {(await self.db.get_one('Server', f'IsBirdCreationDefault = 1, DiscordServerId = {ctx.guild.id}'))['Id']}"):
            await ctx.send("Starter housing already exists in this server.")
            return
        
        complex = await self.db.post("HousingComplex", {
            "Name": "Brokie Apartments",
            "ChargesRent": 0,
            "ServerId": (await self.db.get_one("Server", f"DiscordServerId = {ctx.guild.id}"))["Id"],
            "CreatedByUserId": ctx.author.id
        })
        for floor_number in range(1, 5):  ## Creates 4 floors
            floor = await self.db.post("HousingFloor", {
                "HousingComplexId": complex["Id"],
                "FloorNumber": floor_number,
                "FloorNumberFriendly": floor_number,
                "Name": f"Floor {floor_number}",
                "CreatedByUserId": ctx.author.id
            })
        
            for unit_number in range(1, 6):  ## Creates 6 units per floor
                await self.db.post("HousingUnit", {
                    "HousingComplexId": complex["Id"],
                    "HousingFloorId": floor["Id"],
                    "UnitNumber": unit_number,
                    "Name": f"Unit {unit_number + ((floor_number) * 100)}",
                    "CreatedByUserId": ctx.author.id
                })   
                
    @commands.hybrid_command(name="destroy_housing")  ## Deletes housing complex and all associated floors and units
    @commands.is_owner()
    async def destroy_housing(self, ctx, housing_id: int):
        ## Dont destroy if housing is occupied
        for unit in await self.db.get("HousingUnit", f"HousingComplexId = {housing_id}"):
            if unit["OccupantBirdId"] is not None:
                await ctx.send("Cannot destroy housing complex because it has occupied units.")
                return
        ## Deletes housing complex and all associated floors and units
        await self.db.delete_where("HousingUnit", f"HousingComplexId = {housing_id}")
        await self.db.delete_where("HousingFloor", f"HousingComplexId = {housing_id}")
        await self.db.delete("HousingComplex", housing_id)
        
    @commands.hybrid_command(name="housing")  ## Lists all housing complexes in the server    
    async def housing(self, ctx):
        if await self.user.deny_unregistered_user(ctx): return
        server = await self.db.get_one("Server", f"DiscordServerId = {ctx.guild.id}")
        complexes = await self.db.get("HousingComplex", f"ServerId = {server['Id']}")
        if not complexes:
            embed = discord.Embed(
                title="No Housing Complexes Found", 
                description="No housing complexes have been found in this server. An administrator should create a starter apartment with `/starter_housing`.", 
                color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        class UnitDetailView():
            def __init__(self, unit_data, parent_view):
                self.unit_data = unit_data
                self.parent_view = parent_view
                self.db = parent_view.db
                
            async def generate_embeds(self, bird, unit_data, response = None):
                embed = discord.Embed(
                    title=f"{unit_data['Name']} – {bird['FirstName']} {bird['LastName']}",
                    description=f"Unit details will be displayed here.\nBut uhhhh {bird['FirstName']} lives here!\n" + (f"\"{response}\"" if response else ""),
                    color=discord.Color.blue()
                )
                return embed

            async def get_embed(self):
                bird = await self.db.get_one("Bird", f"Id = {self.unit_data['OccupantBirdId']}")
                # TODO: Implement unit detail embed
                embed = await self.generate_embeds(bird, self.unit_data)
                return embed
            
            async def get_view(self):
                class DetailView(View):
                    def __init__(self, parent):
                        super().__init__()
                        self.parent = parent
                        
                    @discord.ui.button(label="Talk", style=discord.ButtonStyle.blurple)
                    async def talk_button(self, interaction: discord.Interaction, button: Button):
                        bird = await self.parent.db.get_one("Bird", f"Id = {self.parent.unit_data['OccupantBirdId']}")
                        all_responses = await self.parent.db.get("Response")
                        bird_tags = await self.parent.db.get("PersonalityTag", f"BirdId = {bird['Id']}")
                        
                        ## filter responses based on personality tags; only show responses that match all tags within the bird.
                        ## a tag can have fewer tags than the bird, but not more.
                        valid_responses = []
                        for response in all_responses:
                            response_tags = await self.parent.db.get("ResponsePersonalityType", f"ResponseId = {response['Id']}")
                            response_tag_ids = [tag['PersonalityTypeId'] for tag in response_tags]
                            bird_tag_ids = [tag['TagTypeId'] for tag in bird_tags]
                            if all(tag_id in bird_tag_ids for tag_id in response_tag_ids):
                                valid_responses.append(response)

                        if not valid_responses:
                            response = "Nah."
                        else:
                            response = random.choice(valid_responses)['Response']
                            
                        print(response)

                        await interaction.response.edit_message(
                            embed=await self.parent.generate_embeds(bird, self.parent.unit_data, response),
                            view=self
                        )

                    @discord.ui.button(label="Back", style=discord.ButtonStyle.grey)
                    async def back_button(self, interaction: discord.Interaction, button: Button):
                        await interaction.response.edit_message(
                            embed=await self.parent.parent_view.get_embed(),
                            view=self.parent.parent_view
                        )

                return DetailView(self)
                
        class ComplexDetailView():
            def __init__(self, complex_data, root_cog=self, db=None, past_interaction=None):
                self.complex_data = complex_data
                self.db = root_cog.db
                self.root_cog = root_cog
            
            async def get_embed(self):
                # generate representative view with windows via iterating through floors and units
                # and creating a visual layout
                description = "```"
                floors = await self.db.get("HousingFloor", f"HousingComplexId = {self.complex_data['Id']} ORDER BY FloorNumberFriendly DESC")
                for floor in floors:
                    units = await self.db.get("HousingUnit", f"HousingFloorId = {floor['Id']} ORDER BY UnitNumber ASC")
                    floor_line = f"{floor['Name']}\n"
                    for unit in units:
                        if unit["OccupantBirdId"] is not None:
                            floor_line += "[#] "  # occupied
                        else:
                            floor_line += "[ ] "  # unoccupied
                    description += floor_line + "\n"
                description += "```"
                
                # Add additional info
                description += f"\n**ID:** {self.complex_data['Id']}\n"
                description += f"**Charges Rent:** {'Yes' if self.complex_data['ChargesRent'] else 'No'}"
                
                embed = discord.Embed(
                    title=f"{self.complex_data['Name']}",
                    description=description,
                    color=discord.Color.green()
                )
                return embed
            
            async def get_view(self, past_interaction=None):
                # Get all units for this complex
                units = await self.db.get("HousingUnit", f"HousingComplexId = {self.complex_data['Id']} ORDER BY UnitNumber ASC")
                
                class HousingComplexView(View):
                    def __init__(self, units_data, parent_detail_view, root_cog=self.root_cog):
                        super().__init__(timeout=300)
                        self.units_data = units_data
                        self.parent_detail_view = parent_detail_view
                        self.current_page = 0
                        self.items_per_page = 10
                        self.total_pages = max(1, (len(units_data) - 1) // self.items_per_page + 1) if units_data else 1
                        # Build initial buttons synchronously
                        self._build_buttons()
                        self.db = root_cog.db
                    
                    async def get_embed(self):
                        # Delegate to parent_detail_view
                        return await self.parent_detail_view.get_embed()
                    
                    def _current_page_units(self):
                        start_index = self.current_page * self.items_per_page
                        end_index = start_index + self.items_per_page
                        return self.units_data[start_index:end_index]
                    
                    def _build_buttons(self):
                        self.clear_items()
                        
                        # Get units for current page
                        current_units = self._current_page_units()
                        
                        # Create callback factory for unit buttons
                        def make_unit_callback(unit_data):
                            async def unit_callback(interaction: discord.Interaction):
                                detail_view = UnitDetailView(unit_data, self)
                                await interaction.response.edit_message(
                                    embed=await detail_view.get_embed(),
                                    view=await detail_view.get_view()
                                )
                            return unit_callback
                        
                        # Add unit buttons (up to 10 per page, 5 per row)
                        for idx, unit in enumerate(current_units):
                            button = Button(
                                label=f"{unit['Name']}",
                                style=discord.ButtonStyle.secondary,
                                row=idx // 5
                            )
                            button.callback = make_unit_callback(unit)
                            self.add_item(button)
                            # disable if not occupied
                            if unit["OccupantBirdId"] is None:
                                button.disabled = True
                        
                        # Add navigation buttons on bottom row
                        self.previous_page.disabled = self.current_page == 0
                        self.next_page.disabled = self.current_page >= self.total_pages - 1
                        
                        self.add_item(self.previous_page)
                        self.add_item(self.next_page)
                    
                    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.primary, row=2)
                    async def previous_page(self, interaction: discord.Interaction, button: Button):
                        if self.current_page > 0:
                            self.current_page -= 1
                            self._build_buttons()
                            await interaction.response.edit_message(
                                embed=await self.parent_detail_view.get_embed(),
                                view=self
                            )
                        else:
                            await interaction.response.defer()
                    
                    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.primary, row=2)
                    async def next_page(self, interaction: discord.Interaction, button: Button):
                        if self.current_page < self.total_pages - 1:
                            self.current_page += 1
                            self._build_buttons()
                            await interaction.response.edit_message(
                                embed=await self.parent_detail_view.get_embed(),
                                view=self
                            )
                        else:
                            await interaction.response.defer()
                
                return HousingComplexView(units, self)

        lines = [f"{c['Name']} (ID: {c['Id']})" for c in complexes]
    
        complex_menu = self.list_menu.make(
            lines=lines, 
            data=complexes,
            detailview_cls=ComplexDetailView,
            title="Housing Complexes",
            )

        await complex_menu.send_initial_message(ctx)

async def setup(bot):
    housing = Housing(bot)
    await bot.add_cog(housing)