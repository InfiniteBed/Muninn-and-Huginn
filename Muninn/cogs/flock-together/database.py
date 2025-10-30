import discord  # type:ignore
import discord.ext.commands as commands  # type:ignore
import sqlite3

class Database(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logginglevel = 'VERBOSE'
        
    async def connect_db(self):
        self.conn = sqlite3.connect("data/flock-together.db")
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
    
    async def close_db(self):
        self.conn.close()

    async def post(self, table: str, row: dict):
        await self.connect_db()

        # so long as a CreatedDateTime field exists in table schema, we auto-set it
        self.cursor.execute(f"PRAGMA table_info({table})")
        columns_info = self.cursor.fetchall()
        column_names = [col[1] for col in columns_info]
        if "CreatedDateTime" in column_names and "CreatedDateTime" not in row:
            import time
            row["CreatedDateTime"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        if "CreatedByUserId" in column_names and "CreatedByUserId" not in row:
            row["CreatedByUserId"] = self.bot.user.id
            
        columns = ", ".join(row.keys())
        placeholders = ", ".join("?" * len(row))
        self.cursor.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(row.values()))
        self.conn.commit()

        await self.close_db()
        
        ## return all data of newly created row
        return await self.get_one(table, f"id = {self.cursor.lastrowid}")

    async def get(self, table: str, where: str = None):
        await self.connect_db()

        if where:
            self.cursor.execute(f"SELECT * FROM {table} WHERE {where}")
        else:
            self.cursor.execute(f"SELECT * FROM {table}")

        rows = self.cursor.fetchall()
        
        if self.logginglevel == 'VERBOSE':
            print(f"Database GET from {table} with where='{where}':! {rows}")

        await self.close_db()

        return rows

    async def get_one(self, table: str, where: str = None):
        rows = await self.get(table, where)
        return rows[0] if rows else None

    async def delete(self, table: str, id: int):
        await self.connect_db()
        self.cursor.execute(f"DELETE FROM {table} WHERE id = ?", (id,))
        self.conn.commit()
        await self.close_db()
        
    async def delete_where(self, table: str, where: str):
        await self.connect_db()
        self.cursor.execute(f"DELETE FROM {table} WHERE {where}")
        self.conn.commit()
        await self.close_db()

    async def patch(self, table: str, object: dict, id: int):
        await self.connect_db()

        set_values = ", ".join([f"{key} = ?" for key in object.keys()])
        self.cursor.execute(f"UPDATE {table} SET {set_values} WHERE id = ?", (*object.values(), id))
        self.conn.commit()

        await self.close_db()
        
async def setup(bot):
    database = Database(bot)
    await bot.add_cog(database)