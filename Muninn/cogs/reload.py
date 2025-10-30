from discord.ext import commands  # type: ignore
import math
from pathlib import Path
import discord
from asyncio.subprocess import Process
import asyncio

class Reload(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._child_processes: set[Process] = set()

    @commands.Cog.listener()
    async def on_register_process(self, proc: Process):
        # Cogs call: bot.dispatch('register_process', proc)
        if isinstance(proc, Process):
            self._child_processes.add(proc)

    @commands.Cog.listener()
    async def on_unregister_process(self, proc: Process):
        # Cogs call when a proc exits cleanly
        self._child_processes.discard(proc)

    async def _terminate_children(self, grace: float = 5.0):
        # SIGTERM, then SIGKILL after grace
        procs = list(self._child_processes)
        self._child_processes.clear()

        for p in procs:
            try:
                if p.returncode is not None:
                    continue
                try:
                    p.terminate()  # SIGTERM
                except ProcessLookupError:
                    continue

                try:
                    await asyncio.wait_for(p.wait(), timeout=grace)
                except asyncio.TimeoutError:
                    try:
                        p.kill()  # SIGKILL
                    except ProcessLookupError:
                        pass
                    try:
                        await asyncio.wait_for(p.wait(), timeout=2.0)
                    except asyncio.TimeoutError:
                        pass
            except Exception:
                # Swallow to avoid blocking reload on a bad proc
                pass

    @commands.hybrid_command(name="reload", with_app_command=True, description="Reload bot cogs")
    @commands.is_owner()
    async def reload(self, ctx: commands.Context):
        # Handle slash vs prefix
        if getattr(ctx, "interaction", None):
            await ctx.defer(ephemeral=True)
            send = ctx.followup.send
        else:
            send = ctx.send

        message = await send("Reloading... [----------] 0%")

        # Let cogs stop their own tasks early if they want
        self.bot.dispatch("pre_reload")
        await asyncio.sleep(0.1)  # tiny yield so listeners run

        # Terminate any registered child processes
        try:
            await self._terminate_children(grace=5.0)
        except Exception:
            pass

        # Discover cogs relative to this file (e.g., Muninn.cogs)
        module_prefix = self.__class__.__module__.rsplit(".", 1)[0]  # 'Muninn.cogs'
        cogs_dir = Path(__file__).resolve().parent

        loaded_cogs = set(self.bot.extensions.keys())
        found_cogs = set()
        all_cogs: list[str] = []

        for path in cogs_dir.rglob("*.py"):
            if path.name == "__init__.py":
                continue

            # Optional: allow files to opt out
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
                if "ignore_cog_setup = True" in text:
                    continue
            except Exception:
                pass

            rel = path.relative_to(cogs_dir).with_suffix("")
            cog_path = f"{module_prefix}." + ".".join(rel.parts)
            all_cogs.append(cog_path)

        total_cogs = len(all_cogs)
        processed_cogs = 0
        self_cog = f"{module_prefix}.reload"

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
                await send(f"Failed to reload/load {cog_path}: {e}")
                print(f"Failed to reload/load {cog_path}: {e}")

            processed_cogs += 1
            if total_cogs:
                progress = (processed_cogs * 100) // total_cogs
                if progress in (25, 50, 75, 100):
                    bar_len = 10
                    filled = (progress * bar_len) // 100
                    bar = "[" + "#" * filled + "-" * (bar_len - filled) + "]"
                    try:
                        await message.edit(content=f"Reloading... {bar} {progress}%")
                    except Exception:
                        pass

        # Unloa missing cogs (except this one)
        for cog in {c for c in (loaded_cogs - found_cogs) if c != self_cog}:
            try:
                await self.bot.unload_extension(cog)
                print(f"Unloaded missing cog: {cog}")
            except Exception as e:
                await send(f"Failed to unload missing cog {cog}: {e}")
                print(f"Failed to unload missing cog {cog}: {e}")

        # Sync app commands so /reload is available again
        try:
            # Target the current guild and any cached guilds
            target_ids: set[int] = set()
            if ctx.guild:
                target_ids.add(ctx.guild.id)
            for g in self.bot.guilds:
                target_ids.add(g.id)

            if not target_ids:
                print("No guilds in cache; syncing globals only.")
                await self.bot.tree.sync()  # global sync (may take up to an hour)
            else:
                for gid in target_ids:
                    gid_obj = discord.Object(id=gid)
                    # Clean slate -> copy globals -> fast per-guild sync
                    self.bot.tree.clear_commands(guild=gid_obj)
                    self.bot.tree.copy_global_to(guild=gid_obj)
                    synced = await self.bot.tree.sync(guild=gid_obj)
                    print(f"Synced {len(synced)} commands to guild {gid}")
        except Exception as e:
            print(f"Tree sync failed: {e}")

        await message.edit(content="Reload complete.")

async def setup(bot):
    await bot.add_cog(Reload(bot))
