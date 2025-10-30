import discord  # type:ignore
from discord.ui import View, Button  # type:ignore
from discord.ext import commands  # type:ignore
class SelectListMenuEmbed(View):
    """
    A paginated embed menu that displays a list of items.
    Each item can be selected via a button to show a detail view.
    """
    def __init__(
        self,
        lines: list = None,
        data: list = None,
        title: str = "Items List",
        custom_body: str = None,
        footer: str = None,
        items_per_page: int = 10,
        max_item_buttons: int = 10,
        has_detail_buttons: bool = True,
        detailview_cls=None,
        detailview_init_kwargs: dict = None,
        db=None,
        **kwargs
    ):
        # Use a finite timeout so this is non-persistent (avoids custom_id/persistence quirks)
        super().__init__(timeout=300)

        # Core data and display properties
        self.lines = lines or []
        self.data = data or []
        self.title = title
        self.custom_body = custom_body
        self.footer = footer

        # Pagination settings
        self.items_per_page = max(1, items_per_page)
        self.max_item_buttons = max(1, max_item_buttons)
        self.current_page = 0
        self.total_pages = (len(self.lines) - 1) // self.items_per_page + 1 if self.lines else 1
        self.has_detail_buttons = has_detail_buttons

        # Detail view configuration
        self.detailview_cls = detailview_cls
        self.detailview_init_kwargs = detailview_init_kwargs or {}
        self.detailview_init_kwargs.update(kwargs)  # Store extra kwargs for the detail view

        # External dependencies and configuration
        self.db = db
        self.log_level = "VERBOSE"

        # Note: Item buttons are dynamically built when send_initial_message is called.

    def _current_page_items(self):
        start_index = self.current_page * self.items_per_page
        end_index = start_index + self.items_per_page
        # Only show as many item buttons as allowed (default 10)
        return self.lines[start_index:end_index][:self.max_item_buttons]

    def get_page_embed(self):
        page_items = self._current_page_items()
        embed = discord.Embed(title=self.title, description="\n".join(map(str, page_items)) or "No items.")
        if self.custom_body:
            embed.description = f"{self.custom_body}"
        embed.set_footer(text=f"Page {self.current_page + 1} of {self.total_pages}" + (f" | {self.footer}" if self.footer else ""))
        return embed

    async def send_initial_message(self, ctx_or_interaction, **kwargs):
        # The kwargs are for the detail view, not for send_message.
        # The __init__ of SelectListMenuEmbed already stored them.
        # We only need to extract ephemeral if it's present for the send call.
        send_kwargs = {}
        if 'ephemeral' in kwargs:
            send_kwargs['ephemeral'] = kwargs['ephemeral']

        await self._rebuild_item_buttons()
        
        # Check if we have an interaction or a context object
        interaction = None
        if isinstance(ctx_or_interaction, discord.Interaction):
            interaction = ctx_or_interaction
        elif hasattr(ctx_or_interaction, "interaction") and ctx_or_interaction.interaction:
            interaction = ctx_or_interaction.interaction

        if interaction and not interaction.response.is_done():
            await interaction.response.send_message(embed=self.get_page_embed(), view=self, **send_kwargs)
            self.message = await interaction.original_response()
        elif isinstance(ctx_or_interaction, commands.Context):
            self.message = await ctx_or_interaction.send(embed=self.get_page_embed(), view=self, **send_kwargs)
        else:
            # Fallback or error
            raise TypeError("send_initial_message requires a context or interaction object.")
            
        return self.message

    async def _rebuild_item_buttons(self):
        # Keep nav buttons, but don't add them to the view yet
        nav_buttons = [
            btn for btn in (getattr(self, "previous_page", None), getattr(self, "next_page", None), getattr(self, "cancel_button", None)) 
            if btn is not None
        ]
        self.clear_items()
            
        # Create and add item buttons first
        current_items = self._current_page_items()
        base_index = self.current_page * self.items_per_page
        
        def make_callback(item_data):
            async def detail_callback(interaction: discord.Interaction):
                if self.detailview_cls:
                    if self.log_level == "VERBOSE":
                        print(f"[ListMenu] Item selected: {item_data.__repr__()}")
                    
                    # The detail view can be a class or an instance
                    if isinstance(self.detailview_cls, type):
                        # Pass both the selected item data and any extra kwargs
                        init_kwargs = {"db": self.db, "past_interaction": interaction, **self.detailview_init_kwargs}
                        detail_view = self.detailview_cls(item_data, **init_kwargs)
                    else:
                        detail_view = self.detailview_cls

                    # Ensure we have an awaitable embed and view
                    embed = await detail_view.get_embed() if hasattr(detail_view, "get_embed") else None
                    view = await detail_view.get_view(past_interaction=interaction) if hasattr(detail_view, "get_view") else detail_view

                    await interaction.response.edit_message(embed=embed, view=view)
                else:
                    await interaction.response.defer()
            return detail_callback

        if self.has_detail_buttons:
            for idx, display_line in enumerate(current_items):
                button = Button(
                    label=f"{idx+1}.", 
                    style=discord.ButtonStyle.secondary,
                    row=idx // 5
                )
                
                global_index = base_index + idx
                item_data = self.data[global_index] if isinstance(self.data, (list, tuple)) and global_index < len(self.data) else None
                button.callback = make_callback(item_data)
                self.add_item(button)

        # Update nav button states before adding them
        if getattr(self, "previous_page", None) in nav_buttons:
            self.previous_page.disabled = self.current_page == 0
        if getattr(self, "next_page", None) in nav_buttons:
            self.next_page.disabled = self.current_page >= self.total_pages - 1
            
        # Add nav buttons on the bottom row last
        for btn in nav_buttons:
            if btn == self.cancel_button and not self.has_detail_buttons:
                continue
            btn.row = 2
            self.add_item(btn)

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.primary, row=2)
    async def previous_page(self, interaction: discord.Interaction, button: Button):
        if self.current_page > 0:
            self.current_page -= 1
            await self._rebuild_item_buttons()
            await interaction.response.edit_message(embed=self.get_page_embed(), view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.primary, row=2)
    async def next_page(self, interaction: discord.Interaction, button: Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            await self._rebuild_item_buttons()
            await interaction.response.edit_message(embed=self.get_page_embed(), view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, row=2)
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(title="Cancelled", description="List selection has been cancelled.", color=discord.Color.red())
        await interaction.response.edit_message(embed=embed, view=None)


class ListMenuCog(commands.Cog, name="ListMenu"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.get_cog("Database")

    # Optional factory other cogs can use via bot.get_cog("ListMenu")
    def make(
        self, 
        lines=None, 
        data=None, 
        title="Items List", 
        items_per_page=10, 
        detailview_cls=None, 
        detailview_init_kwargs=None,
        max_item_buttons=10, 
        custom_body=None,
        footer=None,
        has_detail_buttons=True
    ):
        return SelectListMenuEmbed(
            lines=lines, 
            data=data, 
            title=title, 
            footer=footer,
            items_per_page=items_per_page, 
            detailview_cls=detailview_cls, 
            detailview_init_kwargs=detailview_init_kwargs, 
            max_item_buttons=max_item_buttons, 
            custom_body=custom_body, 
            db=self.db,
            has_detail_buttons=has_detail_buttons
        )

async def setup(bot: commands.Bot):
    list_menu = ListMenuCog(bot)
    await bot.add_cog(list_menu)