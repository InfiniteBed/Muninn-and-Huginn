from discord.ext import commands # type:ignore
import os

class Reload(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def reload(self, ctx):
        await ctx.send("Reloading!")
        
        # Track currently loaded cogs
        loaded_cogs = set(self.bot.extensions.keys())
        found_cogs = set()

        for foldername, subfolders, files in os.walk("./cogs"):
            for filename in files:
                if filename.endswith(".py"):
                    relative_path = os.path.relpath(foldername, "./cogs")
                    if relative_path == ".":
                        cog_path = f"cogs.{filename[:-3]}"
                    else:
                        cog_path = f"cogs.{relative_path.replace(os.sep, '.')}" + f".{filename[:-3]}"

                    found_cogs.add(cog_path)

                    try:
                        if cog_path in self.bot.extensions:
                            await self.bot.reload_extension(cog_path)
                            print(f"Reloaded {filename}")
                        else:
                            await self.bot.load_extension(cog_path)
                            print(f"Loaded {filename}")
                    except Exception as e:
                        await ctx.send(f"Failed to reload/load {filename}: {e}")
                        print(f"Failed to reload/load {filename}: {e}")

        # Unload missing cogs
        missing_cogs = loaded_cogs - found_cogs
        for cog in missing_cogs:
            try:
                await self.bot.unload_extension(cog)
                print(f"Unloaded missing cog: {cog}")
            except Exception as e:
                await ctx.send(f"Failed to unload missing cog {cog}: {e}")
                print(f"Failed to unload missing cog {cog}: {e}")

async def setup(bot):
    await bot.add_cog(Reload(bot))
