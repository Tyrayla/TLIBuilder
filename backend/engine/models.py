from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class SourceEntry:
    """A single stat contribution with its origin metadata."""
    stat:         str
    amount:       float
    source_type:  str   # "talent" | "slate" | "gear" | "custom" | "support" | "condition" | "core_talent"
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
    # Consumption tracing (drives the "inert modifier" badges). When _recording is on, every stat
    # key read via total() is recorded in consumed_stats. compute.py turns it on only around the
    # consumption passes (derive_stats / offense / defense) so condition-system reads don't count.
    consumed_stats: set[str] = field(default_factory=set)
    _recording: bool = False

    def add(self, stat: str, amount: float) -> None:
        self._entries.append((stat, amount))

    def add_with_source(self, stat: str, amount: float, entry: SourceEntry) -> None:
        self._entries.append((stat, amount))
        self.source_log.append(entry)

    def total(self, stat: str) -> float:
        if self._recording:
            self.consumed_stats.add(stat)
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
class SkillRef:
    """Minimal skill reference passed from the frontend to the engine."""
    skill_id: str
    level:    int = 1


@dataclass
class BuildInput:
    """Everything the engine needs to run a calculation."""
    slots:      list[dict | None]       # TreeSlot dicts: {treeName, nodeStates}
    slates:     list[dict]              # SavedSlate dicts from the build
    season:     str                     # active season name for data lookups
    skill:      SkillConfig | None = None
    enemy:      EnemyConfig | None = None
    # Unified condition state: boolean conditions store True/False, numeric store float.
    condition_state: dict[str, float | bool] = field(default_factory=dict)
    gear:            list[dict] = field(default_factory=list)  # GearEngineItem dicts
    character:       list[dict] = field(default_factory=list)  # CharacterStatContribution dicts
    memory_effects:  list[str]  = field(default_factory=list)  # resolved hero memory modifier strings
    spirit_effects:  list[str]  = field(default_factory=list)  # pact spirit slot + rank modifier strings
    main_skill:      SkillRef | None = None  # main skill for offense calculation
    custom_contributions: list[dict] = field(default_factory=list)  # pre-resolved custom mod entries {stat_key, amount, text}
    # Pre-resolved support-skill contributions (same shape as custom_contributions), from the main
    # skill's attached supports. See engine/support_resolver.py.
    attached_support_contributions: list[dict] = field(default_factory=list)
    # Behavioral support effects (shotgun falloff, chains-per-jump, …) consumed by calculate_offense.
    support_behavior: dict = field(default_factory=dict)
    # Raw attached support refs ({item_id, skill_type, level, …}) for the standard support_skill /
    # activation_medium path, resolved IN the fixed-point loop (conditional lines + auto-derive) by
    # engine.support_resolver.resolve_standard_supports. Noble/Magnificent stay pre-resolved above.
    attached_supports: list[dict] = field(default_factory=list)
    # Pre-resolved + deduped core-talent contributions (roadmap #4), from server.resolve_core_talents.
    # Same shape as custom_contributions plus an optional `condition_expr` gate. Override flags
    # (core_sacrifice / divine_grace / core_conductive) ride in condition_state, not here.
    core_talent_contributions: list[dict] = field(default_factory=list)


@dataclass
class StatResult:
    """Output of engine.compute()."""
    stat_map:            dict                    # {stat_key: {display_name, total, sources, ...}}
    condition_maximums:  dict[str, float]        # {condition_key: derived_max}
    clamp_report:        dict[str, dict]         # {key: {"requested": v, "applied": v}}
    offense:             dict | None = None      # OffenseResult as dict, or None if no skill
    defense:             dict | None = None      # DefenseResult as dict
    skill_slots:         list[dict] | None = None  # per-slot summary: slot, skill_id, skill_name, level, effective_level, supported
    consumed_stats:      list[str] = field(default_factory=list)  # stat keys the offense/defense/derive passes actually read for this build
