"""配置 API 测试"""

import json

import pytest


@pytest.mark.asyncio
async def test_get_config_returns_defaults(client):
    """GET /api/config 在无配置文件时返回默认值"""
    response = await client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert data["python_path"] == "python"
    assert data["gpu_device"] == 0
    assert data["backend_port"] == 8000
    assert data["llm_api_key"] == ""
    assert data["llm_api_url"] == ""
    assert data["image_gen_api_key"] == ""
    assert data["image_gen_api_url"] == ""
    assert data["tts_engine"] == "edge-tts"


@pytest.mark.asyncio
async def test_put_config_full_update(client):
    """PUT /api/config 完整更新所有字段"""
    payload = {
        "python_path": "/usr/bin/python3",
        "gpu_device": 1,
        "backend_port": 9000,
        "llm_api_key": "sk-test-key",
        "llm_api_url": "https://api.example.com/v1",
        "image_gen_api_key": "img-key-123",
        "image_gen_api_url": "https://img.example.com",
        "tts_engine": "chattts",
    }
    response = await client.put("/api/config", json=payload)
    assert response.status_code == 200
    data = response.json()
    for key, value in payload.items():
        assert data[key] == value

    # 验证持久化：再次 GET 应返回更新后的值
    response = await client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    for key, value in payload.items():
        assert data[key] == value


@pytest.mark.asyncio
async def test_put_config_partial_update(client):
    """PUT /api/config 部分更新只修改指定字段"""
    # 先设置一些初始值
    await client.put("/api/config", json={
        "python_path": "/usr/bin/python3",
        "gpu_device": 2,
    })

    # 只更新 gpu_device
    response = await client.put("/api/config", json={"gpu_device": 3})
    assert response.status_code == 200
    data = response.json()
    assert data["gpu_device"] == 3
    assert data["python_path"] == "/usr/bin/python3"  # 未修改的字段保持不变


@pytest.mark.asyncio
async def test_put_config_invalid_tts_engine(client):
    """PUT /api/config 使用无效的 tts_engine 应返回 422"""
    response = await client.put("/api/config", json={"tts_engine": "invalid"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_config_persistence_across_requests(client, tmp_db):
    """配置在多次请求间持久化"""
    await client.put("/api/config", json={"llm_api_key": "key-abc"})
    await client.put("/api/config", json={"image_gen_api_url": "https://img.test"})

    response = await client.get("/api/config")
    data = response.json()
    assert data["llm_api_key"] == "key-abc"
    assert data["image_gen_api_url"] == "https://img.test"


@pytest.mark.asyncio
async def test_config_json_file_created(client, tmp_db):
    """PUT 后应在数据目录创建 config.json 文件"""
    await client.put("/api/config", json={"gpu_device": 5})

    config_path = tmp_db.parent / "config.json"
    assert config_path.exists()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["gpu_device"] == 5
