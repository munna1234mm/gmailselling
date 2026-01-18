import asyncio
import aiosqlite
import pandas as pd

DB_NAME = "bot_data.db"

async def inspect():
    async with aiosqlite.connect(DB_NAME) as db:
        print("--- Table Info: accounts ---")
        async with db.execute("PRAGMA table_info(accounts)") as cursor:
            cols = await cursor.fetchall()
            for col in cols:
                print(col)
                
        print("\n--- All Accounts ---")
        async with db.execute("SELECT * FROM accounts") as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                print(row)

if __name__ == "__main__":
    asyncio.run(inspect())
