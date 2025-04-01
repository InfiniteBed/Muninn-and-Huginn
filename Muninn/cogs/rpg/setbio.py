import sqlite3
from discord.ext import commands

class BioManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def setbio(self, ctx, *, bio: str):
        """
        Command to set the user's bio.
        :param ctx: The context of the command.
        :param bio: The bio text to set for the user.
        """
        user = ctx.author

        # Limit bio length
        if len(bio) > 500:
            await ctx.send("Your bio is too long! Please limit it to 500 characters.")
            return

        # Update the database
        conn = sqlite3.connect('discord.db')
        c = conn.cursor()

        # Check if the user exists in the profiles table
        c.execute('SELECT user_id FROM profiles WHERE user_id = ?', (user.id,))
        if not c.fetchone():
            # If the user doesn't exist, create a new profile entry
            c.execute('INSERT INTO profiles (user_id, bio) VALUES (?, ?)', (user.id, bio))
        else:
            # Update the existing bio
            c.execute('UPDATE profiles SET bio = ? WHERE user_id = ?', (bio, user.id))

        conn.commit()
        conn.close()

        await ctx.send(f"Your bio has been updated to: {bio}")

async def setup(bot):
    await bot.add_cog(BioManager(bot))