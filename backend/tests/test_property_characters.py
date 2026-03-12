"""Property 5: 角色数据持久化往返一致性

Feature: ai-video-generator, Property 5: 角色数据持久化往返一致性
For any 角色数据和任意字段更新，更新角色信息后再读取应当得到包含更新内容的角色数据，
且未修改的字段保持不变。

Validates: Requirements 2.3, 2.4
"""

import pytest
from hypothesis import given, settings, HealthCheck, strategies as st

# 非空文本策略：至少 1 个字符的中英文混合文本
non_empty_text = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=100,
).filter(lambda s: s.strip())

# 可选文本策略
optional_text = st.one_of(st.none(), non_empty_text)


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    name=non_empty_text,
    appearance=non_empty_text,
    personality=non_empty_text,
    background=non_empty_text,
    image_prompt=non_empty_text,
)
@pytest.mark.asyncio
async def test_character_create_roundtrip(client, name, appearance, personality, background, image_prompt):
    """创建角色后读取，所有字段应与输入一致"""
    # 创建项目
    res = await client.post("/api/projects", json={"name": "prop-test", "template_id": "anime"})
    pid = res.json()["id"]

    # 创建角色
    res = await client.post(f"/api/projects/{pid}/characters", json={
        "name": name,
        "appearance": appearance,
        "personality": personality,
        "background": background,
        "image_prompt": image_prompt,
    })
    assert res.status_code == 201
    char = res.json()

    assert char["name"] == name
    assert char["appearance"] == appearance
    assert char["personality"] == personality
    assert char["background"] == background
    assert char["image_prompt"] == image_prompt

    # 再次读取验证
    res = await client.get(f"/api/projects/{pid}/characters")
    chars = res.json()
    found = [c for c in chars if c["id"] == char["id"]]
    assert len(found) == 1
    assert found[0]["name"] == name
    assert found[0]["appearance"] == appearance


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    update_name=optional_text,
    update_appearance=optional_text,
    update_personality=optional_text,
)
@pytest.mark.asyncio
async def test_character_partial_update_preserves_unmodified(
    client, update_name, update_appearance, update_personality
):
    """部分更新角色后，未修改字段保持不变"""
    # 创建项目和角色
    res = await client.post("/api/projects", json={"name": "prop-test", "template_id": "anime"})
    pid = res.json()["id"]

    original = {
        "name": "原始名称",
        "appearance": "原始外貌",
        "personality": "原始性格",
        "background": "原始背景",
        "image_prompt": "original prompt",
    }
    res = await client.post(f"/api/projects/{pid}/characters", json=original)
    cid = res.json()["id"]

    # 构建更新请求（只包含非 None 的字段）
    update = {}
    if update_name is not None:
        update["name"] = update_name
    if update_appearance is not None:
        update["appearance"] = update_appearance
    if update_personality is not None:
        update["personality"] = update_personality

    if not update:
        return  # 没有更新字段，跳过

    res = await client.put(f"/api/projects/{pid}/characters/{cid}", json=update)
    assert res.status_code == 200
    updated = res.json()

    # 验证更新的字段
    if update_name is not None:
        assert updated["name"] == update_name
    else:
        assert updated["name"] == original["name"]

    if update_appearance is not None:
        assert updated["appearance"] == update_appearance
    else:
        assert updated["appearance"] == original["appearance"]

    if update_personality is not None:
        assert updated["personality"] == update_personality
    else:
        assert updated["personality"] == original["personality"]

    # 未更新的字段保持不变
    assert updated["background"] == original["background"]
    assert updated["image_prompt"] == original["image_prompt"]
