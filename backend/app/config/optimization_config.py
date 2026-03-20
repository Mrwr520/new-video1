"""剧本迭代优化系统配置

定义 IterationConfig 配置类，支持目标分数、最大迭代次数、
搜索开关和维度权重等参数配置。
"""

from pydantic import BaseModel, Field, field_validator

from app.schemas.script_optimization import DimensionWeights


class IterationConfig(BaseModel):
    """迭代优化配置"""
    target_score: float = Field(
        default=8.0, description="目标分数 (0-10)"
    )
    max_iterations: int = Field(
        default=20, description="最大迭代次数"
    )
    enable_hotspot_search: bool = Field(
        default=True, description="启用热点搜索"
    )
    enable_technique_search: bool = Field(
        default=True, description="启用技巧搜索"
    )
    parallel_search: bool = Field(
        default=True, description="并行搜索"
    )
    dimension_weights: DimensionWeights = Field(
        default_factory=DimensionWeights, description="评审维度权重"
    )

    @field_validator("target_score")
    @classmethod
    def validate_target_score(cls, v: float) -> float:
        if v < 0:
            raise ValueError("目标分数不能为负数")
        if v > 10:
            raise ValueError("目标分数不能超过 10")
        return v

    @field_validator("max_iterations")
    @classmethod
    def validate_max_iterations(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("最大迭代次数必须为正整数")
        return v
