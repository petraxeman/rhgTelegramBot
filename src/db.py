import aiosqlite as sql
import os, asyncio



class DB:
    def __init__(self):
        self.db_path = os.path.join(".", "conf", "db.db")
        asyncio.run(self._init())
    
    async def _init(self):
        await self.execute("CREATE TABLE IF NOT EXISTS users (userid TEXT, username TEXT, gemini_token TEXT);")
        await self.execute("CREATE TABLE IF NOT EXISTS groups (userid TEXT, groupid TEXT, weather_enabled BOOL DEFAULT false)")
        await self.execute("CREATE TABLE IF NOT EXISTS weather_wallpaper(groupid TEXT, temp INT, weather TEXT, degree INT, wpid TEXT, wpah TEXT)")
    
    async def execute(self, query: str):
        async with sql.connect(self.db_path) as db:
            await db.execute(query)
            await db.commit()
    
    async def fetchone(self, query: str):
        async with sql.connect(self.db_path) as db:
            cursor = await db.execute(query)
            return await cursor.fetchone()
    
    async def fetchall(self, query: str):
        async with sql.connect(self.db_path) as db:
            cursor = await db.execute(query)
            return await cursor.fetchall()
    
    
                