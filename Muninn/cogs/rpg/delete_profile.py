import discord
from discord.ext import commands
import sqlite3  # Assuming you are using SQLite for your database

# You may need to set up your database connection properly
DATABASE_PATH = "path_to_your_database.db"  # Replace this with the path to your SQLite database

class DeleteProfile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="delete_profile")
    async def delete_profile(self, ctx):
        """Deletes all user data from the database."""
        user_id = ctx.author.id

        try:
            # Connect to the database
            conn = sqlite3.connect('muninn.db')
            c = conn.cursor()

            # Delete the user's data from the relevant tables
            # Delete from equipped_items
            c.execute('DELETE FROM equipped_items WHERE user_id = ?', (user_id,))
            
            # Delete from any other relevant tables
            # For example:
            c.execute('DELETE FROM user_profiles WHERE user_id = ?', (user_id,))
            c.execute('DELETE FROM user_inventory WHERE user_id = ?', (user_id,))
            c.execute('DELETE FROM user_stats WHERE user_id = ?', (user_id,))

            # Commit the changes and close the connection
            conn.commit()
            conn.close()

            # Notify the user that their profile data was deleted
            await ctx.send(f"All profile data for {ctx.author.mention} has been deleted successfully.")

        except sqlite3.Error as e:
            await ctx.send(f"An error occurred while deleting the profile data: {e}")
            print(f"SQLite error: {e}")

# Setup function to add the cog to the bot
async def setup(bot):
    await bot.add_cog(DeleteProfile(bot))
