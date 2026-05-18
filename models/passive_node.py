from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from models.stat import Stat


class NodeType(str, Enum):
    MICRO            = "Micro Talent"
    MEDIUM           = "Medium Talent"
    LEGENDARY_MEDIUM = "Legendary Medium Talent"


@dataclass
class NodeStat:
    stat:   Stat
    values: list[float]   # values[i] = contribution at rank i+1

    def display(self, points: int) -> str:
        from models.stat_meta import STAT_META
        if points < 1 or points > len(self.values):
            return ""
        val  = self.values[points - 1]
        meta = STAT_META.get(self.stat)
        name = meta.display_name if meta else self.stat.value
        unit = meta.unit        if meta else ""
        if unit == "%":
            pct = val * 100
            fmt = f"{pct:.0f}" if pct == int(pct) else f"{pct:.1f}"
            return f"+{fmt}% {name}"
        fmt = f"{val:.0f}" if val == int(val) else f"{val:.1f}"
        return f"+{fmt} {name}"


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
