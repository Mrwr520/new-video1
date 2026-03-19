"""测试完整的 Pipeline 流程

使用本地模型测试从文本到视频的完整流程。
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


async def test_full_pipeline():
    """测试完整流程"""
    from app.database import init_db, get_connection
    import uuid
    
    print("=" * 60)
    print("测试完整 Pipeline 流程")
    print("=" * 60)
    
    # 初始化数据库
    await init_db()
    
    # 创建测试项目
    project_id = f"test-{uuid.uuid4().hex[:8]}"
    project_name = "测试项目"
    
    conn = await get_connection()
    try:
        await conn.execute(
            "INSERT INTO projects (id, name, template_id, status) VALUES (?, ?, ?, ?)",
            (project_id, project_name, "builtin-anime", "created")
        )
        await conn.commit()
        print(f"\n✓ 创建测试项目: {project_id}")
    finally:
        await conn.close()
    
    # 提交测试文本
    test_text = """
    在一个阳光明媚的早晨，小明走在上学的路上。
    他看到路边有一只受伤的小猫，决定帮助它。
    小明小心翼翼地把小猫抱起来，带到了附近的宠物医院。
    """
    
    conn = await get_connection()
    try:
        await conn.execute(
            "UPDATE projects SET source_text = ?, status = ? WHERE id = ?",
            (test_text, "text_submitted", project_id)
        )
        await conn.commit()
        print(f"✓ 提交测试文本")
    finally:
        await conn.close()
    
    # 测试角色提取
    print("\n" + "=" * 60)
    print("步骤 1: 角色提取")
    print("=" * 60)
    
    from app.pipeline.executors import execute_character_extraction
    
    try:
        await execute_character_extraction(project_id)
        print("✓ 角色提取成功")
        
        # 查看提取的角色
        conn = await get_connection()
        try:
            cursor = await conn.execute(
                "SELECT name, appearance FROM characters WHERE project_id = ?",
                (project_id,)
            )
            characters = await cursor.fetchall()
            print(f"\n提取到 {len(characters)} 个角色:")
            for char in characters:
                print(f"  - {char['name']}: {char['appearance'][:50]}...")
        finally:
            await conn.close()
            
    except Exception as e:
        print(f"✗ 角色提取失败: {e}")
        return False
    
    # 确认角色
    conn = await get_connection()
    try:
        await conn.execute(
            "UPDATE characters SET confirmed = TRUE WHERE project_id = ?",
            (project_id,)
        )
        await conn.commit()
        print("✓ 角色已确认")
    finally:
        await conn.close()
    
    # 测试分镜生成
    print("\n" + "=" * 60)
    print("步骤 2: 分镜生成")
    print("=" * 60)
    
    from app.pipeline.executors import execute_storyboard_generation
    
    try:
        await execute_storyboard_generation(project_id)
        print("✓ 分镜生成成功")
        
        # 查看生成的分镜
        conn = await get_connection()
        try:
            cursor = await conn.execute(
                "SELECT scene_order, scene_description FROM scenes WHERE project_id = ? ORDER BY scene_order",
                (project_id,)
            )
            scenes = await cursor.fetchall()
            print(f"\n生成了 {len(scenes)} 个分镜:")
            for scene in scenes:
                print(f"  {scene['scene_order']}. {scene['scene_description'][:50]}...")
        finally:
            await conn.close()
            
    except Exception as e:
        print(f"✗ 分镜生成失败: {e}")
        return False
    
    # 确认分镜
    conn = await get_connection()
    try:
        await conn.execute(
            "UPDATE scenes SET confirmed = TRUE WHERE project_id = ?",
            (project_id,)
        )
        await conn.commit()
        print("✓ 分镜已确认")
    finally:
        await conn.close()
    
    # 测试关键帧生成（使用本地模型）
    print("\n" + "=" * 60)
    print("步骤 3: 关键帧生成（本地 SDXL 模型）")
    print("=" * 60)
    
    from app.pipeline.executors import execute_keyframe_generation
    
    try:
        await execute_keyframe_generation(project_id)
        print("✓ 关键帧生成成功")
        
        # 查看生成的关键帧
        conn = await get_connection()
        try:
            cursor = await conn.execute(
                "SELECT scene_order, keyframe_path FROM scenes WHERE project_id = ? ORDER BY scene_order",
                (project_id,)
            )
            scenes = await cursor.fetchall()
            print(f"\n生成的关键帧:")
            for scene in scenes:
                path = scene['keyframe_path']
                exists = Path(path).exists() if path else False
                status = "✓" if exists else "✗"
                print(f"  {status} 分镜 {scene['scene_order']}: {path}")
        finally:
            await conn.close()
            
    except Exception as e:
        print(f"✗ 关键帧生成失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "=" * 60)
    print("✓ 测试完成！前三个步骤都成功了。")
    print("=" * 60)
    print(f"\n测试项目 ID: {project_id}")
    print("你可以在前端查看这个项目的结果。")
    
    return True


if __name__ == "__main__":
    success = asyncio.run(test_full_pipeline())
    sys.exit(0 if success else 1)
