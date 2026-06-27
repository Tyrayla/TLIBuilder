"""Shared damage-type constants. Previously redefined in offense/aggregator/compute/pipeline — a drift hazard
where several sites wrongly counted Erosion as "elemental". Defined once here.

ELEMENTAL = Fire/Cold/Lightning ONLY — the in-game "Elemental". Erosion is NOT elemental (owner-confirmed); it
is its own damage type, penetrated/resisted on its own (no elemental_pen / elemental damage bonuses apply to it).
"""

# Ordered list of all damage types (engine order). Kept a list to match prior usage (list()/iteration/index).
DAMAGE_TYPES = ["physical", "fire", "cold", "lightning", "erosion"]

ELEMENTAL = frozenset({"fire", "cold", "lightning"})
