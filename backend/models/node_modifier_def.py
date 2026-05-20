# ── NO MANUAL WORK REQUIRED ───────────────────────────────────────────────────
# Structural dataclass used by data/node_modifier_pool.py.
# Each NodeModifierDef carries a per-node-type increment used by the stat editor
# to auto-fill rank values:
#   micro_increment     → used for MICRO nodes (3 ranks: ×1, ×2, ×3)
#   medium_increment    → used for MEDIUM nodes (3 ranks: ×1, ×2, ×3)
#   legendary_increment → used for LEGENDARY_MEDIUM nodes (1 rank: ×1)
# unit: "" for flat numbers, "%" for percentage stats.
# ──────────────────────────────────────────────────────────────────────────────
from dataclasses import dataclass
from models.stat import Stat


@dataclass(frozen=True)
class NodeModifierDef:
    stat:                Stat
    micro_increment:     float
    medium_increment:    float
    legendary_increment: float
    unit:                str = ""
