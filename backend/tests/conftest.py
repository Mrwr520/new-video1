"""测试配置和共享 fixtures"""

import asyncio
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.database import init_db, set_db_path
from app.main import app


@pytest.fixture(scope="session")
def event_loop():
    """为整个测试会话创建事件循环"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def tmp_db(tmp_path):
    """为每个测试创建临时数据库"""
    db_path = tmp_path / "test.db"
    set_db_path(db_path)
    await init_db()
    yield db_path


@pytest_asyncio.fixture
async def client(tmp_db):
    """创建测试用 HTTP 客户端"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
