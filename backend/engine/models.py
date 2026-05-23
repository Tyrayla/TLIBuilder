from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class SourceEntry:
    """A single stat contribution with its origin metadata."""
    stat:         str
    amount:       float
    source_type:  str   # "talent" | "slate" — extendable to "gear", "hero_memory", etc.
    label:        str   # human-readable origin: "Goddess of Knowledge Micro", "Ranger Slate Medium"
    text:         str   # original game text: "+15% Critical Strike Rating"
    points:       int = 1  # points allocated (>1 for multi-rank talent nodes)


@dataclass
class SkillConfig:
    name:           str
    skill_type:     str              # "attack" | "spell"
    tags:           list[str]        # ["attack", "melee", "area", ...] — mechanics tags
    damage_types:   list[str]        # ["fire", "physical", ...] — what damage the skill deals
    base_level:     int
    extra_levels:   int   = 0        # bonus levels from gear/talents ON TOP of base_level
    base_dmg_min:   float = 0.0
    base_dmg_max:   float = 0.0
    base_csr:       float = 0.0      # base critical strike rating (from weapon/spell)


@dataclass
class EnemyConfig:
    fire_resistance:       float = 0.0
    cold_resistance:       float = 0.0
    lightning_resistance:  float = 0.0
    erosion_resistance:    float = 0.0
    armor:                 float = 0.0


@dataclass
class BuildSource:
    """Flat list of (stat_value_string, numeric_amount) from all build sources."""
    _entries: list[tuple[str, float]] = field(default_factory=list)
    source_log: list[SourceEntry] = field(default_factory=list)

    def add(self, stat: str, amount: float) -> None:
        self._entries.append((stat, amount))

    def add_with_source(self, stat: str, amount: float, entry: SourceEntry) -> None:
        self._entries.append((stat, amount))
        self.source_log.append(entry)

    def total(self, stat: str) -> float:
        return sum(v for s, v in self._entries if s == stat)

    def all_stats(self) -> set[str]:
        return {s for s, _ in self._entries}


@dataclass
class ComputedResult:
    avg_hit:           float = 0.0
    min_hit:           float = 0.0
    max_hit:           float = 0.0
    crit_chance:       float = 0.0
    crit_multiplier:   float = 1.5
    effective_dps:     float = 0.0   # avg_hit × attacks_per_second (placeholder)
    breakdown:         dict  = field(default_factory=dict)


@dataclass
class BuildInput:
    """Everything the engine needs to run a calculation."""
    slots:      list[dict | None]       # TreeSlot dicts: {treeName, nodeStates}
    slates:     list[dict]              # SavedSlate dicts from the build
    season:     str                     # active season name for data lookups
    skill:      SkillConfig | None = None
    enemy:      EnemyConfig | None = None
    conditions: list[str] = field(default_factory=list)  # active condition keys
    gear:            list[dict] = field(default_factory=list)  # GearEngineItem dicts
    character:       list[dict] = field(default_factory=list)  # CharacterStatContribution dicts
    memory_effects:  list[str]  = field(default_factory=list)  # resolved hero memory modifier strings
    spirit_effects:  list[str]  = field(default_factory=list)  # pact spirit slot + rank modifier strings
