
import pytest
import pytest_asyncio
import asyncio
from services.db_service import open_pool, get_pool


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_pool(event_loop):
    await open_pool()
    pool = get_pool()
    assert pool is not None, "Pool was not initialized after open_pool()!"
    yield
    await pool.close()
