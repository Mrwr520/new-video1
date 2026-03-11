"""健康检查端点测试"""

import pytest


@pytest.mark.asyncio
async def test_health_check(client):
    """测试健康检查端点返回正确状态"""
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
