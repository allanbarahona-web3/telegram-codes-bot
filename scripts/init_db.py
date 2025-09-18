import asyncio
from services.db_service import open_pool, init_db

async def main():
    await open_pool()
    await init_db()
    print("DB INIT OK")

if __name__ == "__main__":
    asyncio.run(main())
