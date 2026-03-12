"""分镜相关属性测试

Feature: ai-video-generator

Property 6: 分镜结构完整性不变量
Property 7: 分镜更新正确性
Property 8: 分镜重排序数据保持不变量

Validates: Requirements 3.2, 3.4, 3.5
"""

import pytest
from hypothesis import given, settings, HealthCheck, strategies as st

non_empty_text = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "Z")),
    min_size=1, max_size=80,
).filter(lambda s: s.strip())

optional_text = st.one_of(st.none(), non_empty_text)


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(desc=non_empty_text, dialogue=non_empty_text, camera=non_empty_text)
@pytest.mark.asyncio
async def test_scene_structure_integrity(client, desc, dialogue, camera):
    """Property 6: 分镜结构完整性不变量
    scene_description、dialogue、camera_direction 三个必要字段均应存在且非空。
    Validates: Requirements 3.2
    """
    res = await client.post("/api/projects", json={"name": "p", "template_id": "anime"})
    pid = res.json()["id"]

    res = await client.post(f"/api/projects/{pid}/scenes", json={
        "scene_description": desc, "dialogue": dialogue, "camera_direction": camera,
    })
    assert res.status_code == 201
    scene = res.json()
    assert scene["scene_description"] == desc
    assert scene["dialogue"] == dialogue
    assert scene["camera_direction"] == camera
    # 所有必要字段非空
    assert len(scene["scene_description"]) > 0
    assert len(scene["dialogue"]) > 0
    assert len(scene["camera_direction"]) > 0


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(update_desc=optional_text, update_dialogue=optional_text, update_camera=optional_text)
@pytest.mark.asyncio
async def test_scene_partial_update_preserves_unmodified(client, update_desc, update_dialogue, update_camera):
    """Property 7: 分镜更新正确性
    更新后再读取应当得到包含更新内容的场景数据，且未修改的字段保持不变。
    Validates: Requirements 3.4
    """
    res = await client.post("/api/projects", json={"name": "p", "template_id": "anime"})
    pid = res.json()["id"]

    original = {"scene_description": "原始场景", "dialogue": "原始台词", "camera_direction": "原始镜头"}
    res = await client.post(f"/api/projects/{pid}/scenes", json=original)
    sid = res.json()["id"]

    update = {}
    if update_desc is not None:
        update["scene_description"] = update_desc
    if update_dialogue is not None:
        update["dialogue"] = update_dialogue
    if update_camera is not None:
        update["camera_direction"] = update_camera

    if not update:
        return

    res = await client.put(f"/api/projects/{pid}/scenes/{sid}", json=update)
    assert res.status_code == 200
    updated = res.json()

    if update_desc is not None:
        assert updated["scene_description"] == update_desc
    else:
        assert updated["scene_description"] == original["scene_description"]

    if update_dialogue is not None:
        assert updated["dialogue"] == update_dialogue
    else:
        assert updated["dialogue"] == original["dialogue"]

    if update_camera is not None:
        assert updated["camera_direction"] == update_camera
    else:
        assert updated["camera_direction"] == original["camera_direction"]


@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(num_scenes=st.integers(min_value=2, max_value=6), perm_seed=st.integers(min_value=0))
@pytest.mark.asyncio
async def test_scene_reorder_preserves_data(client, num_scenes, perm_seed):
    """Property 8: 分镜重排序数据保持不变量
    重排序后的分镜列表应当包含与原列表完全相同的场景集合，不丢失也不重复。
    Validates: Requirements 3.5
    """
    res = await client.post("/api/projects", json={"name": "p", "template_id": "anime"})
    pid = res.json()["id"]

    scene_ids = []
    scene_data = {}
    for i in range(num_scenes):
        res = await client.post(f"/api/projects/{pid}/scenes", json={
            "scene_description": f"场景{i}", "dialogue": f"台词{i}", "camera_direction": f"镜头{i}",
        })
        s = res.json()
        scene_ids.append(s["id"])
        scene_data[s["id"]] = s["scene_description"]

    # 生成一个排列
    import random
    rng = random.Random(perm_seed)
    shuffled = list(scene_ids)
    rng.shuffle(shuffled)

    res = await client.put(f"/api/projects/{pid}/scenes/reorder", json={"scene_ids": shuffled})
    assert res.status_code == 200
    result = res.json()

    # 验证：场景集合不变
    result_ids = {s["id"] for s in result}
    assert result_ids == set(scene_ids)

    # 验证：数据不变
    for s in result:
        assert s["scene_description"] == scene_data[s["id"]]

    # 验证：顺序与请求一致
    assert [s["id"] for s in result] == shuffled
