import os
import shutil
from glob import glob
from matplotlib import matplotlib_fname
from matplotlib import get_cachedir
from discord.ext import commands

class FontManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="transfer_fonts")
    async def transfer_fonts(self, ctx):
        """Transfers .ttf and .otf font files to the appropriate directory."""
        dir_source = '<your-font-directory-here>'
        dir_data = os.path.dirname(matplotlib_fname())
        dir_dest = os.path.join(dir_data, 'fonts', 'ttf')

        await ctx.send(f'Transferring .ttf and .otf files from {dir_source} to {dir_dest}.')

        for file in glob(os.path.join(dir_source, '*.[ot]tf')):
            dest_file = os.path.join(dir_dest, os.path.basename(file))
            if not os.path.exists(dest_file):
                shutil.copy(file, dir_dest)
                await ctx.send(f'Adding font "{os.path.basename(file)}".')

        await ctx.send('Font transfer complete.')

    @commands.command(name="clear_cache")
    async def clear_cache(self, ctx):
        """Deletes font cache files."""
        dir_cache = get_cachedir()

        deleted_files = []
        for file in glob(os.path.join(dir_cache, '*.cache')) + glob(os.path.join(dir_cache, 'font*')):
            if not os.path.isdir(file):  # don't dump the tex.cache folder
                os.remove(file)
                deleted_files.append(file)

        if deleted_files:
            await ctx.send(f'Deleted font cache files: {", ".join(deleted_files)}.')
        else:
            await ctx.send('No font cache files were deleted.')

    @commands.command(name="list_fonts")
    async def list_fonts(self, ctx):
        """Lists all the fonts in the font directory."""
        dir_data = os.path.dirname(matplotlib_fname())
        dir_dest = os.path.join(dir_data, 'fonts', 'ttf')

        # Get a list of .ttf and .otf font files in the directory
        font_files = glob(os.path.join(dir_dest, '*.[ot]tf'))
        
        if font_files:
            font_names = [os.path.basename(file) for file in font_files]
            font_list = "\n".join(font_names)
            await ctx.send(f"Fonts found in the directory:\n{font_list}")
        else:
            await ctx.send("No fonts found in the directory.")

# Setup function to add this cog to the bot
async def setup(bot):
    await bot.add_cog(FontManager(bot))