"""Pipeline 步骤执行器

将各服务模块（LLM、图像生成、FramePack、TTS、FFmpeg）串联到 Pipeline 引擎。
每个执行器是一个独立的 async 函数，接收 project_id 参数，
从数据库读取项目数据，调用对应服务，并将结果保存回数据库。

Requirements: 全部（集成所有服务模块）
"""

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.database import get_connection, get_db_path
from app.models.character import Character
from app.models.scene import StoryboardScene
from app.services.template_service import TemplateService, ContentTemplate, BUILTIN_TEMPLATES

logger = logging.getLogger(__name__)

# Shared template service instance
_template_service = TemplateService()


def _get_projects_root() -> Path:
    """获取项目文件存储根目录"""
    return get_db_path().parent / "projects"


def _load_config() -> dict:
    """加载应用配置"""
    from app.api.config import _load_config as load_app_config
    config = load_app_config()
    return config.model_dump()


async def _get_project(project_id: str) -> dict:
    """从数据库读取项目基本信息"""
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise ValueError(f"项目不存在: {project_id}")
        return dict(row)
    finally:
        await conn.close()


async def _get_characters(project_id: str) -> list[Character]:
    """从数据库读取项目的角色列表"""
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            "SELECT * FROM characters WHERE project_id = ?", (project_id,)
        )
        rows = await cursor.fetchall()
        return [
            Character(
                id=row["id"],
                name=row["name"],
                appearance=row["appearance"] or "",
                personality=row["personality"] or "",
                background=row["background"] or "",
                image_prompt=row["image_prompt"] or "",
            )
            for row in rows
        ]
    finally:
        await conn.close()


async def _get_scenes(project_id: str) -> list[dict]:
    """从数据库读取项目的分镜列表（按顺序）"""
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            "SELECT * FROM scenes WHERE project_id = ? ORDER BY scene_order",
            (project_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await conn.close()


def _get_template(template_id: str) -> ContentTemplate:
    """获取模板，找不到则返回默认动漫模板"""
    tpl = _template_service.get_template(template_id)
    if tpl is None:
        # Fallback to anime template
        tpl = _template_service.get_template("builtin-anime")
    if tpl is None:
        # Last resort: use the constant directly
        from app.services.template_service import ANIME_TEMPLATE
        tpl = ANIME_TEMPLATE
    return tpl


# ============================================================
# Step 1: 角色提取
# ============================================================

async def execute_character_extraction(project_id: str) -> None:
    """调用 LLMService 提取角色，保存到数据库。"""
    from app.services.llm_service import LLMService

    project = await _get_project(project_id)
    source_text = project.get("source_text", "")
    if not source_text:
        raise ValueError("项目没有源文本，无法提取角色")

    template = _get_template(project.get("template_id", "builtin-anime"))
    config = _load_config()

    llm = LLMService(
        api_url=config.get("llm_api_url") or "https://api.openai.com/v1",
        api_key=config.get("llm_api_key", ""),
    )

    try:
        characters = await llm.extract_characters(source_text, template)
    except Exception as e:
        logger.error("角色提取失败: %s", e)
        raise
    finally:
        await llm.close()

    if not characters:
        logger.warning("角色提取结果为空: project=%s，文本可能不包含明确的角色", project_id)

    # Save characters to DB
    conn = await get_connection()
    try:
        # Clear existing characters for this project
        await conn.execute(
            "DELETE FROM characters WHERE project_id = ?", (project_id,)
        )
        for char in characters:
            await conn.execute(
                "INSERT INTO characters (id, project_id, name, appearance, personality, background, image_prompt, confirmed) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (char.id, project_id, char.name, char.appearance,
                 char.personality, char.background, char.image_prompt, False),
            )
        await conn.commit()
    finally:
        await conn.close()

    logger.info("角色提取完成: project=%s, count=%d", project_id, len(characters))


# ============================================================
# Step 2: 分镜脚本生成
# ============================================================

async def execute_storyboard_generation(project_id: str) -> None:
    """调用 LLMService 生成分镜脚本，保存到数据库。"""
    from app.services.llm_service import LLMService

    project = await _get_project(project_id)
    source_text = project.get("source_text", "")
    if not source_text:
        raise ValueError("项目没有源文本，无法生成分镜")

    template = _get_template(project.get("template_id", "builtin-anime"))
    characters = await _get_characters(project_id)
    config = _load_config()

    llm = LLMService(
        api_url=config.get("llm_api_url") or "https://api.openai.com/v1",
        api_key=config.get("llm_api_key", ""),
    )

    try:
        scenes = await llm.generate_storyboard(source_text, characters, template)
    except Exception as e:
        logger.error("分镜生成失败: %s", e)
        raise
    finally:
        await llm.close()

    # Save scenes to DB
    conn = await get_connection()
    try:
        # Clear existing scenes for this project
        await conn.execute(
            "DELETE FROM scenes WHERE project_id = ?", (project_id,)
        )
        for scene in scenes:
            await conn.execute(
                "INSERT INTO scenes (id, project_id, scene_order, scene_description, dialogue, "
                "camera_direction, image_prompt, motion_prompt, confirmed) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (scene.id, project_id, scene.order, scene.scene_description,
                 scene.dialogue, scene.camera_direction, scene.image_prompt,
                 scene.motion_prompt, False),
            )
        await conn.commit()
    finally:
        await conn.close()

    logger.info("分镜生成完成: project=%s, count=%d", project_id, len(scenes))


# ============================================================
# Step 3: 关键帧图片生成
# ============================================================

async def execute_keyframe_generation(project_id: str) -> None:
    """调用图像生成服务为每个分镜生成关键帧。

    根据配置 image_gen_mode 选择本地 SDXL 或远程 API。
    本地模式下，生成完所有关键帧后自动卸载模型释放显存，
    为后续视频生成腾出 GPU 空间。
    """
    from app.services.image_service import ImageGeneratorService
    from app.services.local_image_service import LocalImageGeneratorService

    project = await _get_project(project_id)
    template = _get_template(project.get("template_id", "builtin-anime"))
    characters = await _get_characters(project_id)
    scenes = await _get_scenes(project_id)

    if not scenes:
        raise ValueError("项目没有分镜，无法生成关键帧")

    config = _load_config()
    projects_root = _get_projects_root()
    image_gen_mode = config.get("image_gen_mode", "local")

    # 根据模式选择服务
    use_local = image_gen_mode == "local"
    if use_local:
        image_service = LocalImageGeneratorService(
            gpu_device=config.get("gpu_device", 0),
            projects_dir=projects_root,
        )
    else:
        image_service = ImageGeneratorService(
            api_url=config.get("image_gen_api_url") or "https://api.openai.com/v1",
            api_key=config.get("image_gen_api_key", ""),
            projects_dir=projects_root,
        )

    try:
        # 本地模式需要先加载模型
        if use_local:
            await image_service.load_model()

        conn = await get_connection()
        try:
            for scene_row in scenes:
                scene = StoryboardScene(
                    id=scene_row["id"],
                    order=scene_row["scene_order"],
                    scene_description=scene_row["scene_description"] or "",
                    dialogue=scene_row["dialogue"] or "",
                    camera_direction=scene_row["camera_direction"] or "",
                    image_prompt=scene_row["image_prompt"] or "",
                    motion_prompt=scene_row["motion_prompt"] or "",
                )

                keyframe_path = await image_service.generate_keyframe(
                    scene=scene,
                    characters=characters,
                    style_config=template.image_style,
                    project_id=project_id,
                )

                await conn.execute(
                    "UPDATE scenes SET keyframe_path = ? WHERE id = ?",
                    (keyframe_path, scene_row["id"]),
                )
                await conn.commit()

                logger.info("关键帧生成: scene=%s, path=%s", scene_row["id"], keyframe_path)
        finally:
            await conn.close()
    except Exception as e:
        logger.error("关键帧生成失败: %s", e)
        raise
    finally:
        await image_service.close()

    logger.info("关键帧生成完成: project=%s", project_id)


# ============================================================
# Step 4: 视频片段生成
# ============================================================

async def execute_video_generation(project_id: str) -> None:
    """调用 FramePackService 为每个分镜生成视频片段。"""
    from app.services.framepack_service import FramePackService

    project = await _get_project(project_id)
    template = _get_template(project.get("template_id", "builtin-anime"))
    scenes = await _get_scenes(project_id)

    if not scenes:
        raise ValueError("项目没有分镜，无法生成视频")

    config = _load_config()
    projects_root = _get_projects_root()

    framepack = FramePackService(
        gpu_device=config.get("gpu_device", 0),
        projects_dir=projects_root,
    )

    try:
        await framepack.load_model()

        motion_style = template.motion_style
        duration = motion_style.get("duration", 5.0)
        fps = motion_style.get("fps", 30)

        conn = await get_connection()
        try:
            for scene_row in scenes:
                keyframe_path = scene_row.get("keyframe_path")
                if not keyframe_path:
                    logger.warning("分镜 %s 没有关键帧，跳过视频生成", scene_row["id"])
                    continue

                motion_prompt = scene_row.get("motion_prompt", "") or ""

                video_path = await framepack.generate_video(
                    image_path=keyframe_path,
                    prompt=motion_prompt,
                    duration=duration,
                    fps=fps,
                )

                await conn.execute(
                    "UPDATE scenes SET video_path = ?, duration = ? WHERE id = ?",
                    (video_path, duration, scene_row["id"]),
                )
                await conn.commit()

                logger.info("视频生成: scene=%s, path=%s", scene_row["id"], video_path)
        finally:
            await conn.close()
    except Exception as e:
        logger.error("视频生成失败: %s", e)
        raise
    finally:
        await framepack.unload_model()

    logger.info("视频生成完成: project=%s", project_id)


# ============================================================
# Step 5: TTS 语音生成
# ============================================================

async def execute_tts_generation(project_id: str) -> None:
    """调用 TTSService 为每个分镜的台词生成语音。"""
    from app.services.tts_service import TTSService

    project = await _get_project(project_id)
    characters = await _get_characters(project_id)
    scenes = await _get_scenes(project_id)

    if not scenes:
        raise ValueError("项目没有分镜，无法生成语音")

    config = _load_config()
    projects_root = _get_projects_root()
    tts_engine = config.get("tts_engine", "edge-tts")

    tts = TTSService(projects_dir=projects_root, config=config)

    # Assign voices to characters
    char_names = [c.name for c in characters]
    voice_map: dict[str, str] = {}
    if char_names:
        try:
            voice_map = await tts.assign_voices(char_names, engine=tts_engine)
        except Exception as e:
            logger.warning("语音分配失败，使用默认语音: %s", e)

    # Get default voice from template
    template = _get_template(project.get("template_id", "builtin-anime"))
    default_voice = template.voice_config.get("default_voice", "zh-CN-XiaoxiaoNeural")

    conn = await get_connection()
    try:
        for scene_row in scenes:
            dialogue = scene_row.get("dialogue", "") or ""
            if not dialogue.strip():
                logger.info("分镜 %s 没有台词，跳过语音生成", scene_row["id"])
                continue

            # Determine voice_id: try to match character, fallback to default
            voice_id = default_voice
            for char_name, vid in voice_map.items():
                if char_name in dialogue:
                    voice_id = vid
                    break

            try:
                audio_path = await tts.generate_speech(
                    text=dialogue,
                    voice_id=voice_id,
                    engine=tts_engine,
                    project_id=project_id,
                    scene_id=scene_row["id"],
                )

                await conn.execute(
                    "UPDATE scenes SET audio_path = ? WHERE id = ?",
                    (audio_path, scene_row["id"]),
                )
                await conn.commit()

                logger.info("语音生成: scene=%s, path=%s", scene_row["id"], audio_path)
            except Exception as e:
                logger.error("分镜 %s 语音生成失败: %s", scene_row["id"], e)
                # Continue with other scenes rather than failing entirely
                continue
    finally:
        await conn.close()

    logger.info("语音生成完成: project=%s", project_id)


# ============================================================
# Step 6: 视频合成
# ============================================================

async def execute_composition(project_id: str) -> None:
    """调用 FFmpegCompositor 合成最终视频。"""
    from app.services.ffmpeg_service import (
        CompositionScene,
        FFmpegCompositor,
        OutputConfig,
    )

    scenes = await _get_scenes(project_id)
    if not scenes:
        raise ValueError("项目没有分镜，无法合成视频")

    scenes_with_video = [s for s in scenes if s.get("video_path")]
    if not scenes_with_video:
        raise ValueError("没有已生成的视频片段，无法合成")

    projects_root = _get_projects_root()
    compositor = FFmpegCompositor(projects_dir=projects_root)

    # Build composition scenes
    composition_scenes: list[CompositionScene] = []
    cumulative_time = 0.0
    for scene_row in scenes_with_video:
        duration = scene_row.get("duration") or 5.0
        cs = CompositionScene(
            video_path=scene_row["video_path"],
            audio_path=scene_row.get("audio_path"),
            subtitle_text=scene_row.get("dialogue"),
            start_time=cumulative_time,
            duration=duration,
        )
        composition_scenes.append(cs)
        cumulative_time += duration

    output_config = OutputConfig()

    video_path = await compositor.compose_final_video(
        project_id=project_id,
        scenes=composition_scenes,
        output_config=output_config,
    )

    # Update project status
    conn = await get_connection()
    try:
        now = datetime.now(timezone.utc).isoformat()
        await conn.execute(
            "UPDATE projects SET status = 'completed', updated_at = ? WHERE id = ?",
            (now, project_id),
        )
        await conn.commit()
    finally:
        await conn.close()

    logger.info("视频合成完成: project=%s, path=%s", project_id, video_path)
