"""Shared damage-type constants. Previously these lists/sets were redefined in offense, aggregator, compute,
and pipeline — a drift hazard (some "elemental" sets included Erosion, some did not). Defined once here so the
distinction is explicit and consistent.

NOTE the two DISTINCT concepts kept separate on purpose:
  - ELEMENTAL = Fire/Cold/Lightning — the in-game "Elemental" (TLI Elemental does NOT include Erosion).
  - NON_PHYSICAL = Fire/Cold/Lightning/Erosion — every non-Physical type (used by armor/non-phys mitigation etc.).
Some engine sites historically named the NON_PHYSICAL set "_ELEMENTAL"; their values are preserved exactly here
(see the offense vs compute/aggregator/pipeline split). Whether those erosion-inclusive uses are correct is a
separate question flagged to the owner — this module does not change any behavior.
"""

# Ordered list of all damage types (engine order). Kept a list to match prior usage (list()/iteration/index).
DAMAGE_TYPES = ["physical", "fire", "cold", "lightning", "erosion"]

ELEMENTAL = frozenset({"fire", "cold", "lightning"})
NON_PHYSICAL = frozenset({"fire", "cold", "lightning", "erosion"})
