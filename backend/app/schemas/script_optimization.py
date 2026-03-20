"""剧本迭代优化系统的 Pydantic 数据模式

定义 DimensionScores、DimensionWeights、EvaluationResult、ScriptVersion、
Hotspot、Technique、IterationProgress 等数据类。
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class DimensionScores(BaseModel):
    """五维度评审分数"""
    content_quality: float = Field(..., ge=0, le=10, description="内容质量 (0-10)")
    structure: float = Field(..., ge=0, le=10, description="结构完整性 (0-10)")
    creativity: float = Field(..., ge=0, le=10, description="创意性 (0-10)")
    hotspot_relevance: float = Field(..., ge=0, le=10, description="热点相关性 (0-10)")
    technique_application: float = Field(..., ge=0, le=10, description="技巧运用 (0-10)")


class DimensionWeights(BaseModel):
    """五维度评审权重"""
    content_quality: float = Field(default=0.3, ge=0, le=1, description="内容质量权重")
    structure: float = Field(default=0.2, ge=0, le=1, description="结构完整性权重")
    creativity: float = Field(default=0.2, ge=0, le=1, description="创意性权重")
    hotspot_relevance: float = Field(default=0.15, ge=0, le=1, description="热点相关性权重")
    technique_application: float = Field(default=0.15, ge=0, le=1, description="技巧运用权重")

    @model_validator(mode="after")
    def validate_weights_sum(self) -> "DimensionWeights":
        total = (
            self.content_quality
            + self.structure
            + self.creativity
            + self.hotspot_relevance
            + self.technique_application
        )
        if abs(total - 1.0) > 0.01:
            raise ValueError(
                f"权重之和必须为 1.0（容差 0.01），当前为 {total:.4f}"
            )
        return self

    def calculate_total_score(self, scores: DimensionScores) -> float:
        """根据权重计算加权平均总分"""
        return (
            scores.content_quality * self.content_quality
            + scores.structure * self.structure
            + scores.creativity * self.creativity
            + scores.hotspot_relevance * self.hotspot_relevance
            + scores.technique_application * self.technique_application
        )


class EvaluationResult(BaseModel):
    """评审结果"""
    total_score: float = Field(..., ge=0, le=10, description="总分")
    dimension_scores: DimensionScores
    suggestions: List[str] = Field(default_factory=list, description="改进建议")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Hotspot(BaseModel):
    """网络热点"""
    title: str
    description: str
    source: str
    relevance_score: float = Field(..., ge=0, le=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Technique(BaseModel):
    """剧本创作技巧"""
    name: str
    description: str
    example: str
    category: str
    source: str


class ScriptVersion(BaseModel):
    """剧本版本"""
    session_id: str
    iteration: int = Field(..., ge=0)
    script: str
    evaluation: EvaluationResult
    hotspots: List[Hotspot] = Field(default_factory=list)
    techniques: List[Technique] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_final: bool = False


class IterationProgress(BaseModel):
    """迭代进度"""
    session_id: str
    current_iteration: int
    total_iterations: int
    stage: str = Field(
        ..., description="当前阶段: generating, searching, evaluating, completed"
    )
    current_score: Optional[float] = None
    message: str
    data: Optional[Dict] = None


class OptimizationSessionResponse(BaseModel):
    """优化会话响应"""
    id: str
    initial_prompt: str
    target_score: float
    max_iterations: int
    created_at: str
    completed_at: Optional[str] = None
    status: str
