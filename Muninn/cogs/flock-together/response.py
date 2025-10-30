import discord  # type:ignore
from discord import app_commands # type:ignore
import discord.ext.commands as commands  # type:ignore

class ConfirmAndAddAnother(discord.ui.View):
    def __init__(self, selected_item, past_interaction=None, db=None, response_text=None, root_cog=None, response_id=None, timeout=300):
        super().__init__(timeout=timeout)
        self.result = None  # Will hold True/False based on user choice
        self.selected_item = selected_item
        self.past_interaction = past_interaction
        self.db = db
        self.response_text = response_text
        self.root_cog = root_cog
        self.response_id = response_id
        
    async def get_embed(self):
        
        embed = discord.Embed(
            title=f"Thanks! This response has been tagged with '{self.selected_item['Name']}'. Add another tag?",
            description="You've also been awarded 3 Shinies!\n\nClick 'Add Another' to add more personality tags, or 'Done' if you are finished.\nKeep in mind, *the more tags you add to a response, the less likely it is to be used.*",
            color=discord.Color.green()
        )
        embed.set_footer(text=self.response_text)
        return embed
    
    async def get_view(self, past_interaction: discord.Interaction):
        return self

    @discord.ui.button(label="Add Another Personality", style=discord.ButtonStyle.grey)
    async def add_another(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Save the previous selection before showing the menu again
        await self.db.post("ResponsePersonalityType", {"ResponseId": self.response_id, "PersonalityTypeId": self.selected_item["Id"]})
        await self.root_cog.create_response(interaction, response=self.response_text, id=self.response_id)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Done", style=discord.ButtonStyle.blurple)
    async def done(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Save the final selection
        await self.db.post("ResponsePersonalityType", {"ResponseId": self.response_id, "PersonalityTypeId": self.selected_item["Id"]})
        self.result = False
        await interaction.response.edit_message(view=None)

class Response(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.input = bot.get_cog("UserInput")
        self.db = self.bot.get_cog("Database")
        self.lm = bot.get_cog("ListMenu")
        self.user = bot.get_cog("User")
        self.shinies = bot.get_cog("Shinies")
    
    @commands.hybrid_command(name="create_response", aliases=["add_response", "ar"]) 
    @app_commands.describe(
        response="The text of the response to be created",
        id="(optional) The ID of an existing response to tag with personality types"
    )
    async def create_response(self, ctx, *, response: str = None, id: int = None):
        if await self.user.deny_unregistered_user(ctx): return
        
        response_text = response
        response_id = id

        if isinstance(ctx, commands.Context):
            interaction = ctx.interaction
            if interaction is None:
                interaction = ctx
            user_id = ctx.author.id
        else:
            interaction = ctx
            user_id = ctx.user.id

        personality_types = await self.db.get("PersonalityType")
        
        if not response_text:
            response_text = await self.input.prompt(
                ctx, 
                question="Please input the response text. It will be stored as-is, with no additional formatting.", 
                type=str, 
                embed_color=discord.Color.orange()
            )

        if response_id is None:
            response_id = (await self.db.post("Response", {"Response": response_text}))['Id']

        for types in personality_types:
            print(f"{types['Id']}: {types['Name']}")

        menu = self.lm.make(
            title="Select a personality type for this response",
            lines=[f"{index}. {p_type['Name']}" for index, p_type in enumerate(personality_types, start=1)],
            data=personality_types,
            detailview_cls=ConfirmAndAddAnother,
            detailview_init_kwargs={'root_cog': self, 'db': self.db, 'past_interaction': interaction, 'response_text': response_text, 'response_id': response_id},
            footer=response_text
        )
        
        if isinstance(ctx, commands.Context):
            await menu.send_initial_message(ctx)
        else:
            await menu.send_initial_message(interaction)

        db_id = await self.user.get_user_by_discord_id(user_id)
        await self.shinies.add_shinies(db_id['Id'], 3)

    @commands.hybrid_command(name="response_statistics", aliases=["rs"])
    async def response_statistics(self, ctx: commands.Context):
        # Fetch and display response statistics
        statistics = []
        description = ""
        responses = await self.db.get("Response")
        personality_types = await self.db.get("PersonalityType")
        response_personality_types = await self.db.get("ResponsePersonalityType")

        # shows counts of responses tagged with each personality type
        embed = discord.Embed(title="Response Statistics", color=discord.Color.blue())
        for type in personality_types:
            #formalize in arrays first, then sort for display
            count = sum(1 for rpt in response_personality_types if rpt["PersonalityTypeId"] == type["Id"])
            statistics.append((type["Name"], count))

        statistics.sort(key=lambda x: x[1], reverse=True)
        for name, count in statistics:
            description += f"{name}: {count}\n"

        embed.description = description
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="list_responses", aliases=["lr"])
    @app_commands.describe(
        verbose="Whether to show detailed information for each response"
    )
    async def list_responses(self, ctx: commands.Context, verbose: bool = False):
        # List all responses with their personality types
        responses = await self.db.get("Response")
        personality_types = await self.db.get("PersonalityType")
        response_personality_types = await self.db.get("ResponsePersonalityType")
        
        lines = []
        
        if verbose:
            for response in responses:
                tagged_types = [f"*{pt['Name']} `{rpt['Id']}`*" for rpt in response_personality_types for pt in personality_types if rpt["ResponseId"] == response["Id"] and rpt["PersonalityTypeId"] == pt["Id"]]
                lines.append(
                    f"**`{response['Id']}` {response['Response']}**" + 
                    f"\n{'\n'.join(tagged_types)}" if tagged_types else f"`{response['Id']}` {response['Response']} " + "[Tags: *None*]")
        else:
            for response in responses:
                tagged_types = [pt["Name"] for rpt in response_personality_types for pt in personality_types if rpt["ResponseId"] == response["Id"] and rpt["PersonalityTypeId"] == pt["Id"]]
                lines.append(f"`{response['Id']}` {response['Response']} " + f"[Tags: *{', '.join(tagged_types)}*]" if tagged_types else f"`{response['Id']}` {response['Response']} " + "[Tags: *None*]")

        list = self.lm.make(
            title="List of Responses",
            lines=lines,
            data=responses,
            footer="Use /tag_response <response_id> <personality_type or name> to tag a response.",
            has_detail_buttons=False
        )

        await list.send_initial_message(ctx)

    @commands.hybrid_command(name="tag_response", aliases=["tr"])
    @app_commands.describe(
        response_id="The ID of the response to tag",
        personality_type="The personality type or name to tag the response with"
    )
    async def tag_response(self, ctx, response_id: int, personality_type: str):
        if await self.user.deny_unregistered_user(ctx): return
        
        if isinstance(ctx, commands.Context):
            interaction = ctx.interaction
            if interaction is None:
                interaction = ctx
        else:
            interaction = ctx

        responses = await self.db.get("Response", f"Id = {response_id}")
        if not responses:
            await interaction.response.send_message(f"No response found with ID {response_id}.", ephemeral=True)
            return
        response = responses[0]

        personality_types = await self.db.get("PersonalityType")
        matched_types = [pt for pt in personality_types if str(pt["Id"]) == personality_type or pt["Name"].lower() == personality_type.lower()]

        if not matched_types:
            await interaction.response.send_message(f"No personality type found matching '{personality_type}'.", ephemeral=True)
            return

        for p_type in matched_types:
            await self.db.post("ResponsePersonalityType", {"ResponseId": response_id, "PersonalityTypeId": p_type["Id"]})

        await interaction.response.send_message(f"Tagged response ID {response_id} with personality type(s): {', '.join(pt['Name'] for pt in matched_types)}.", ephemeral=True)

    @commands.hybrid_command(name="untag_response", aliases=["ur"])
    @app_commands.describe(
        response_personality_type_id="(Optional) The personality type or name to untag the response from"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def untag_response(self, ctx, response_personality_type_id: int):
        # Utility function to remove all tags from a response
        await self.db.delete("ResponsePersonalityType", response_personality_type_id)

        await ctx.send(f"Untagged personality type ID {response_personality_type_id}.")
        
    @commands.hybrid_command(name="delete_response", aliases=["dr"])
    @app_commands.describe(
        response_id="The ID of the response to delete"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def delete_response(self, ctx, response_id: int):
        # Also delete any associated personality type tags
        await self.db.delete_where("ResponsePersonalityType", f"ResponseId = {response_id}")
        # Delete the response from the database
        await self.db.delete("Response", response_id)

        await ctx.send(f"Deleted response ID {response_id} and its associated tags.")

async def setup(bot):
    response = Response(bot)
    await bot.add_cog(response)