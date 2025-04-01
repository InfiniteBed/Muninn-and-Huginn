import discord # type: ignore
from discord.ext import commands # type: ignore
import sqlite3

class PenaltyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='penalize')
    @commands.is_owner()
    async def penalize(self, ctx, user: discord.User, amount: int):
        guild_id = ctx.guild.id
        table_name = f"discord_{guild_id}"

        try:
            # Connect to the database
            conn = sqlite3.connect('discord.db')
            cur = conn.cursor()

            # Ensure table exists
            cur.execute(f'''CREATE TABLE IF NOT EXISTS {table_name} (
                            id INTEGER PRIMARY KEY,
                            friendly_name TEXT,
                            message_count INTEGER
                        )''')

            # Check if user exists
            cur.execute(f"SELECT message_count FROM {table_name} WHERE id = ?", (user.id,))
            result = cur.fetchone()

            print (result)

            if result:
                new_count = max(0, result[0] - amount)  # Deduct custom amount, no negative numbers
                cur.execute(f"UPDATE {table_name} SET message_count = ? WHERE id = ?", (new_count, user.id))
                await ctx.send(f"{user.display_name} has been penalized by {amount} points. New message count: {new_count}")
            else:
                await ctx.send(f"{user.display_name} is not in the database.")

            conn.commit()
        except sqlite3.Error as e:
            await ctx.send(f"Database error: {e}")
        except Exception as e:
            await ctx.send(f"An unexpected error occurred: {e}")
        finally:
            conn.close()

async def setup(bot):
    await bot.add_cog(PenaltyCog(bot))
