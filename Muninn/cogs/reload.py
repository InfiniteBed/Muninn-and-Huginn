from discord.ext import commands # type:ignore
from discord import app_commands
import os
import math

class Reload(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def reload(self, ctx):
        message = await ctx.send("Reloading... [----------] 0%")
        
        # Track currently loaded cogs
        loaded_cogs = set(self.bot.extensions.keys())
        found_cogs = set()

        # Gather all cogs
        all_cogs = []
        for foldername, subfolders, files in os.walk("./cogs"):
            for filename in files:
                if filename.endswith(".py"):
                    relative_path = os.path.relpath(foldername, "./cogs")
                    if relative_path == ".":
                        cog_path = f"cogs.{filename[:-3]}"
                    else:
                        cog_path = f"cogs.{relative_path.replace(os.sep, '.')}" + f".{filename[:-3]}"
                    all_cogs.append(cog_path)

        total_cogs = len(all_cogs)
        processed_cogs = 0

        for cog_path in all_cogs:
            found_cogs.add(cog_path)
            try:
                if cog_path in self.bot.extensions:
                    await self.bot.reload_extension(cog_path)
                    print(f"Reloaded {cog_path}")
                else:
                    await self.bot.load_extension(cog_path)
                    print(f"Loaded {cog_path}")
            except Exception as e:
                await ctx.send(f"Failed to reload/load {cog_path}: {e}")
                print(f"Failed to reload/load {cog_path}: {e}")

            # Update progress
            processed_cogs += 1
            progress = math.floor((processed_cogs / total_cogs) * 100)
            if progress in [25, 50, 75, 100]:  # Update only at 25%, 50%, 75%, and 100%
                bar_length = 10  # Length of the progress bar
                filled_length = math.floor((progress / 100) * bar_length)
                bar = "[" + "#" * filled_length + "-" * (bar_length - filled_length) + "]"
                await message.edit(content=f"Reloading... {bar} {progress}%")

        # Unload missing cogs
        missing_cogs = loaded_cogs - found_cogs
        for cog in missing_cogs:
            try:
                await self.bot.unload_extension(cog)
                print(f"Unloaded missing cog: {cog}")
            except Exception as e:
                await ctx.send(f"Failed to unload missing cog {cog}: {e}")
                print(f"Failed to unload missing cog {cog}: {e}")

        try:
            synced = await self.bot.tree.sync()
            print(f"Synced {len(synced)} commands globally.")
        except Exception as e:
            await ctx.send(f"Failed to sync slash commands: {e}")
            print(f"Failed to sync slash commands: {e}")

        await message.edit(content="Reload complete! [##########] 100%")
        
async def setup(bot):
    await bot.add_cog(Reload(bot))
