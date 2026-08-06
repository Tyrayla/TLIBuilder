from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class NodeType(str, Enum):
    MICRO            = "Micro Talent"
    MEDIUM           = "Medium Talent"
    LEGENDARY_MEDIUM = "Legendary Medium Talent"


@dataclass
class PassiveNode:
    id: str
    node_type: NodeType
    column: int       # 0-based index; display label = column * 3
    row: int          # vertical position 0-4 within the column
    max_points: int   # varies per node
    current_points: int = field(default=0, init=True)
    icon_url: str | None = None   # CDN url from the scrape; UI pairs on its basename to a bundled webp

    @property
    def column_label(self) -> int:
        return self.column * 3

    @property
    def is_empty(self) -> bool:
        return self.current_points == 0
