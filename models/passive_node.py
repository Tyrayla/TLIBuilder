from dataclasses import dataclass, field
from enum import Enum


class NodeType(str, Enum):
    MICRO            = "Micro Talent"
    MEDIUM           = "Medium Talent"
    LEGENDARY_MEDIUM = "Legendary Medium Talent"


@dataclass
class NodeStat:
    label: str       # e.g. "% Spell Damage" or " Energy Shield"
    per_point: float # value added per allocated point
    prefix: str = "+"

    def display(self, points: int) -> str:
        value = self.per_point * points
        formatted = int(value) if value == int(value) else f"{value:.1f}"
        return f"{self.prefix}{formatted}{self.label}"


@dataclass
class PassiveNode:
    id: str
    node_type: NodeType
    column: int       # 0-based index; display label = column * 3
    row: int          # vertical position 0-4 within the column
    max_points: int   # varies per node
    current_points: int = field(default=0, init=True)
    stats: list[NodeStat] = field(default_factory=list)

    @property
    def column_label(self) -> int:
        return self.column * 3

    @property
    def is_full(self) -> bool:
        return self.current_points >= self.max_points

    @property
    def is_empty(self) -> bool:
        return self.current_points == 0
