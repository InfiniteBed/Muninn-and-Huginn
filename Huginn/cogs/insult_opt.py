import sqlite3
from discord.ext import commands

# Database setup
conn = sqlite3.connect('huginn.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS opt_in_users (user_id INTEGER PRIMARY KEY)''')
conn.commit()

class InsultOpt(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='insultopt')
    async def insultopt(self, ctx):
        user_id = ctx.author.id
        c.execute("SELECT user_id FROM opt_in_users WHERE user_id = ?", (user_id,))
        result = c.fetchone()

        if result:
            c.execute("DELETE FROM opt_in_users WHERE user_id = ?", (user_id,))
            conn.commit()
            await ctx.send(f"{ctx.author.mention}, you have **opted out** of insults.")
        else:
            c.execute("INSERT INTO opt_in_users (user_id) VALUES (?)", (user_id,))
            conn.commit()
            await ctx.send(f"{ctx.author.mention}, you have **opted in** to insults.")

async def setup(bot):
    await bot.add_cog(InsultOpt(bot))