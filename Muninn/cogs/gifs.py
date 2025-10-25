import discord
from discord.ext import commands
import time  # Used for tracking timestamps
import asyncio


class GifDetector(commands.Cog):
    """Detect GIF usage and enforce GIF-ban rules.

    Behavior implemented:
    - A single automatic ban slot: the first user to exceed the limit will be auto-banned (3 hours by default).
    - One hardcoded allowed user (set ALLOWED_USER_ID) may send up to 3 GIFs per 6 hours.
    - Manual command `!gifban` to ban a user for a specified number of hours (default 3).
    """

    # --- CONFIGURE THESE ---
    ALLOWED_USER_ID = 123456789012345678  # <-- Replace with the user ID you want to allow (hardcoded)
    ALLOWED_USER_LIMIT = 3
    ALLOWED_USER_WINDOW = 6 * 60 * 60  # 6 hours

    DEFAULT_WINDOW = 3 * 60 * 60  # 3 hours window for counting GIFs for everyone else
    DEFAULT_THRESHOLD = 3  # number of GIFs that triggers enforcement (>= this)
    AUTO_BAN_DURATION = 3 * 60 * 60  # 3 hours auto-ban duration

    def __init__(self, bot):
        self.bot = bot
        # user_id -> list of timestamps (seconds since epoch) when GIFs were sent
        self.user_gif_data = {}  # {user_id: [ts1, ts2, ...]}

        # currently auto-banned user id (only one at a time) and its unban time
        self.auto_banned_user = None  # user_id
        self.auto_ban_expires = 0

        # track manual bans to allow scheduled unban bookkeeping
        # maps user_id -> unban_timestamp
        self.manual_bans = {}

    def _is_gif_in_message(self, message: discord.Message) -> bool:
        # Check attachments
        for attachment in message.attachments:
            if attachment.filename.lower().endswith('.gif'):
                return True

        # Check embeds (Tenor/Giphy and others)
        for embed in message.embeds:
            try:
                if embed.type in ('gifv', 'gif'):
                    return True
                if embed.url and (embed.url.lower().endswith('.gif') or 'gif' in embed.url.lower()):
                    return True
            except Exception:
                continue

        # Optionally, check for direct urls in content
        if 'tenor.com' in message.content.lower() or 'giphy.com' in message.content.lower():
            return True

        return False

    def _cleanup_old_entries(self, user_id: int, now: float, window: int):
        if user_id in self.user_gif_data:
            self.user_gif_data[user_id] = [ts for ts in self.user_gif_data[user_id] if now - ts <= window]

    async def _apply_ban(self, guild: discord.Guild, user: discord.User, duration_seconds: int, reason: str = "GIF ban"):
        # NOTE: per user's request, do NOT actually ban users. We keep the "ban" nomenclature
        # but instead record the ban in-memory and send a randomized approved response.
        # Return True to indicate enforcement applied.
        unban_ts = time.time() + duration_seconds
        # record in manual_bans for bookkeeping
        self.manual_bans[user.id] = unban_ts
        # Schedule removal
        asyncio.create_task(self._clear_manual_ban_after(user.id, duration_seconds))
        return True

    async def _schedule_unban(self, guild: discord.Guild, user_id: int, duration_seconds: int):
        # Legacy unban scheduler kept for compatibility (no-op since we don't actually ban)
        await asyncio.sleep(duration_seconds)
        self.manual_bans.pop(user_id, None)

    async def _clear_manual_ban_after(self, user_id: int, duration_seconds: int):
        await asyncio.sleep(duration_seconds)
        self.manual_bans.pop(user_id, None)

    async def _get_random_gifban_response(self, guild: discord.Guild):
        """Fetch a random approved 'GIF Ban Response' from the contributions DB for this guild.

        Falls back to a default message if none are available.
        """
        import sqlite3
        try:
            conn = sqlite3.connect('discord.db')
            cursor = conn.cursor()
            cursor.execute('''SELECT content FROM contributions WHERE contribution_type = ? AND approved = 1 AND guild_id = ?''',
                           ("GIF Ban Response", guild.id))
            rows = cursor.fetchall()
            conn.close()
            if rows:
                import random as _random
                return _random.choice([r[0] for r in rows])
        except Exception:
            pass

        # default fallback responses
        fallbacks = [
            "Please don't post GIFs here.",
            "GIFs are restricted right now — please use images instead.",
            "Heads up: GIF posting is temporarily limited."
        ]
        import random as _random
        return _random.choice(fallbacks)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return  # Ignore bot messages

        if not self._is_gif_in_message(message):
            return

        user_id = message.author.id
        now = time.time()

        # If user is currently the auto-banned user and ban hasn't expired, ensure they remain banned
        if self.auto_banned_user and user_id == self.auto_banned_user and now < self.auto_ban_expires:
            # Try to delete message and remind
            try:
                await message.delete()
            except Exception:
                pass
            return

        # If user is currently manually banned (we store manual bans for bookkeeping), ignore (they should be banned at guild level)
        if user_id in self.manual_bans and now < self.manual_bans[user_id]:
            try:
                await message.delete()
            except Exception:
                pass
            return

        # Determine window/threshold depending on whether this is the allowed user
        if user_id == self.ALLOWED_USER_ID:
            window = self.ALLOWED_USER_WINDOW
            threshold = self.ALLOWED_USER_LIMIT
        else:
            window = self.DEFAULT_WINDOW
            threshold = self.DEFAULT_THRESHOLD

        # Cleanup old timestamps and add this one
        self._cleanup_old_entries(user_id, now, window)
        self.user_gif_data.setdefault(user_id, []).append(now)

        count = len(self.user_gif_data[user_id])

        # If within allowed threshold, do nothing
        if count <= threshold:
            return

        # Count exceeded
        # If this is the allowed user, enforce by deleting and warning (but do not ban)
        if user_id == self.ALLOWED_USER_ID:
            try:
                await message.delete()
                resp = await self._get_random_gifban_response(message.guild)
                await message.channel.send(f"{message.author.mention}, {resp}")
            except discord.Forbidden:
                await message.channel.send(f"{message.author.mention}, you exceeded your GIF allowance.")
            return

        # For other users: if there's currently no auto-banned user, auto-ban this one (single slot)
        if self.auto_banned_user is None or time.time() >= self.auto_ban_expires:
            # Attempt to ban
            try:
                    guild = message.guild
                    user = message.author
                    # Apply "ban" (now just bookkeeping + response)
                    applied = await self._apply_ban(guild, user, self.AUTO_BAN_DURATION, reason="Auto GIF ban")
                    if applied:
                        self.auto_banned_user = user_id
                        self.auto_ban_expires = now + self.AUTO_BAN_DURATION
                        resp = await self._get_random_gifban_response(guild)
                        await message.channel.send(f"{user.mention}, {resp} (enforced for {int(self.AUTO_BAN_DURATION/3600)} hours)")
                    else:
                        # Fallback to deletion + warning
                        try:
                            await message.delete()
                            resp = await self._get_random_gifban_response(guild)
                            await message.channel.send(f"{user.mention}, {resp}")
                        except Exception:
                            pass
            except Exception:
                pass
            return

        # If an auto-banned user already exists and is active, just delete the message and warn
        try:
            await message.delete()
            resp = await self._get_random_gifban_response(message.guild)
            await message.channel.send(f"{message.author.mention}, {resp}")
        except Exception:
            pass

    @commands.command(name='gifban')
    @commands.has_permissions(ban_members=True)
    async def gifban(self, ctx, member: discord.Member, hours: int = 3):
        """Manually GIF-ban a member for a number of hours (default 3).

        This will ban the user from the guild and schedule an unban after the duration.
        """
        duration = max(1, hours) * 60 * 60
        try:
            success = await self._apply_ban(ctx.guild, member, duration, reason=f"Manual GIF ban by {ctx.author}")
            if success:
                self.manual_bans[member.id] = time.time() + duration
                await ctx.send(f"{member.mention} has been GIF-banned for {hours} hour(s).")
            else:
                await ctx.send(f"Could not ban {member.mention}. I may lack permissions.")
        except Exception as e:
            await ctx.send(f"Error attempting to ban: {e}")

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def ungifban(self, ctx, member: discord.User):
        """Remove a GIF-ban (manual) before it expires."""
        try:
            await ctx.guild.unban(member)
            self.manual_bans.pop(member.id, None)
            # If this was the auto-banned user, clear that state
            if self.auto_banned_user == member.id:
                self.auto_banned_user = None
                self.auto_ban_expires = 0
            await ctx.send(f"Removed GIF-ban for {member.mention}.")
        except Exception as e:
            await ctx.send(f"Could not unban: {e}")

    @commands.command()
    async def reset_gif_count(self, ctx, member: discord.Member = None):
        """Manually resets the GIF count for a user or all users."""
        if member:
            self.user_gif_data.pop(member.id, None)
            await ctx.send(f"Reset GIF count for {member.mention}.")
        else:
            self.user_gif_data.clear()
            await ctx.send("All GIF counts have been reset.")

    @commands.command(name='gifbans')
    @commands.has_permissions(ban_members=True)
    async def gifbans(self, ctx):
        """Show current GIF-ban state: auto-ban slot and manual bans."""
        now = time.time()
        lines = []

        # Auto-ban
        if self.auto_banned_user and now < self.auto_ban_expires:
            remaining = int(self.auto_ban_expires - now)
            hrs = remaining // 3600
            mins = (remaining % 3600) // 60
            try:
                user = await self.bot.fetch_user(self.auto_banned_user)
                lines.append(f"Auto-banned user: {user} (ID: {self.auto_banned_user}) — expires in {hrs}h {mins}m")
            except Exception:
                lines.append(f"Auto-banned user ID: {self.auto_banned_user} — expires in {hrs}h {mins}m")
        else:
            lines.append("Auto-banned user: None")

        # Manual bans
        if self.manual_bans:
            lines.append("Manual bans:")
            for uid, expire_ts in list(self.manual_bans.items()):
                if now >= expire_ts:
                    # expired, remove bookkeeping
                    self.manual_bans.pop(uid, None)
                    continue
                remaining = int(expire_ts - now)
                hrs = remaining // 3600
                mins = (remaining % 3600) // 60
                try:
                    user = await self.bot.fetch_user(uid)
                    lines.append(f"  - {user} (ID: {uid}) — expires in {hrs}h {mins}m")
                except Exception:
                    lines.append(f"  - ID: {uid} — expires in {hrs}h {mins}m")
        else:
            lines.append("Manual bans: None")

        await ctx.send("\n".join(lines))


async def setup(bot):
    await bot.add_cog(GifDetector(bot))