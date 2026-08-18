"""活世界子系统的数据类模型。

使用 stdlib dataclasses 定义，替代返回原始 dict 的做法。
渐进式引入：函数返回值可从 dict 逐步迁移到 dataclass，
用 dataclasses.asdict() 保持旧调用方兼容。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(frozen=True)
class WorldContext:
    """get_or_create_world_context 的返回值。

    Attributes:
        turn: 回合号
        seed: 种子哈希
        season: 季节（春/夏/秋/冬/四时）
        weather: 天气数据
        regional_conditions: 区域状态
        public_mood: 民情
        power_budgets: 势力预算映射
    """
    turn: int
    seed: str
    season: str
    weather: dict = field(default_factory=dict)
    regional_conditions: dict = field(default_factory=dict)
    public_mood: dict = field(default_factory=dict)
    power_budgets: dict = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """兼容 dict 访问方式。"""
        return asdict(self)


@dataclass(frozen=True)
class BattleEnvironment:
    """battle_environment 的返回值。

    Attributes:
        seed: 种子
        season: 季节
        weather: 天气数据
        terrain_condition: 地形条件
        probability_delta: 概率修正
        campaign_seed_ref: 种子引用
        regional_state_refs: 区域状态引用列表
        battlefield: 战场数据
    """
    seed: str
    season: str
    weather: dict = field(default_factory=dict)
    terrain_condition: dict = field(default_factory=dict)
    probability_delta: int = 0
    campaign_seed_ref: str = ""
    regional_state_refs: list = field(default_factory=list)
    battlefield: dict = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReactionCandidate:
    """draw_weighted 的候选项（地缘反应 / 内部动态）。

    Attributes:
        key: 候选标识
        weight: 权重
        target: 目标势力（可选）
        severity: 严重度（可选）
    """
    key: str
    weight: float
    target: str = ""
    severity: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
