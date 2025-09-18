import asyncio
from services.db_service import open_pool, get_pool

async def main():
    await open_pool()
    pool = get_pool()
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute('ALTER TABLE users ADD COLUMN email TEXT;')
        await conn.commit()
    print('Migración: columna email agregada.')

if __name__ == "__main__":
    asyncio.run(main())
