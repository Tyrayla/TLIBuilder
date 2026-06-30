from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class SourceEntry:
    """A single stat contribution with its origin metadata."""
    stat:         str
    amount:       float
    source_type:  str   # "talent" | "slate" | "gear" | "custom" | "support" | "condition" | "core_talent"
    label:        str   # human-readable origin: "Goddess of Knowledge Micro", "Ranger Slate Medium"
    text:         str   # original game text: "+15% Critical Strike Rating" (KEEP scope words — see note)
    points:       int = 1  # points allocated (>1 for multi-rank talent nodes)
    # Skill-type tag this contribution is restricted to (e.g. "attack" for "…for Attack Skills"); None =
    # unscoped/applies always. Scoped entries never enter `_entries`/`source_log`; they fold into the
    # SAME base stat key per-skill via BuildSource.materialize_for_skill. CRITICAL: `text` must remain the
    # ORIGINAL full line incl. the scope words so the additional pool's affix-identity stays distinct
    # (scoped vs unscoped additionals must multiply, never additively merge).
    scope:        str | None = None
    # Skill SLOT this contribution is local to (a slot's own supports / skill self-buffs). None =
    # character-wide (the default for every existing emit). Slot entries never enter `_entries`/
    # `source_log`; they fold into the SAME base stat key for the matching slot via materialize_for_skill.
    # NOTE: `slot` is deliberately NOT read by compute.py's stat_map (it reads source_type/label/text/
    # amount/points only), so adding it leaves character-stat output byte-identical.
    slot:         int | None = None
    # Human display NAME of the originating thing (item name, pact-spirit name, hero-memory name, support
    # name). Distinct from `label` (the type+context, e.g. "Gear · Chest") and `text` (the affix-pooling
    # identity). Drives the stat-breakdown "Source Name" column + its hover tooltip. None for sources whose
    # name the UI derives itself (talent → tree name from the label) or that have none (custom/character).
    source_name:  str | None = None
    # Weapon slot this contribution came from ("weapon1" = main-hand, "weapon2" = off-hand), set by the aggregator
    # for gear contributions. Lets offense scope a main-hand-only modifier to the weapon1 base share (see
    # BuildSource.main_hand_flat). None for non-weapon sources. Not read by compute.py's stat_map → output-neutral.
    weapon_slot:  str | None = None


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
    # Skill-scoped contributions, held SEPARATELY so `total()` / the offense pools never see them by
    # default. Per skill, materialize_for_skill folds the ones whose scope matches that skill's tags into
    # an effective source. Empty for every build that has no "for/dealt by <X> Skills" mods → the offense
    # runs on the identical base source → output byte-identical (the no-change guarantee).
    scoped_entries: list[tuple[str, float, str]] = field(default_factory=list)  # (stat, amount, scope_tag)
    scoped_log: list[SourceEntry] = field(default_factory=list)
    # Slot-local contributions (a slot's supports / skill self-buffs), held SEPARATELY like scoped_entries.
    # Per slot, materialize_for_skill folds the ones whose slot matches (and whose scope, if any, matches
    # the skill tags). Empty for every single-slot build today → offense runs on the identical base source
    # → byte-identical output (the same dormancy guarantee scoped_entries gives).
    slot_entries: list[tuple[str, float, int, str | None]] = field(default_factory=list)  # (stat, amount, slot, scope)
    slot_log: list[SourceEntry] = field(default_factory=list)
    # Condition keys referenced by ANY contribution in this build (collected before the on/off gate, so a
    # condition counts even when currently toggled off). Drives the UI's "hide conditions with no source".
    referenced_conditions: set[str] = field(default_factory=set)
    # Editable calc-target stats (fractions) for offense mitigation; None → offense's Lv85 constants.
    target_config: dict | None = None

    def add(self, stat: str, amount: float) -> None:
        self._entries.append((stat, amount))

    def add_with_source(self, stat: str, amount: float, entry: SourceEntry) -> None:
        self._entries.append((stat, amount))
        self.source_log.append(entry)

    def add_scoped(self, stat: str, amount: float, scope: str, entry: SourceEntry) -> None:
        """A contribution restricted to skills tagged `scope`. Folds into the base `stat` key only for
        matching skills (via materialize_for_skill); never enters the base `_entries`/`source_log`."""
        self.scoped_entries.append((stat, amount, scope))
        self.scoped_log.append(entry)

    def add_slotted(self, stat: str, amount: float, slot: int, scope: str | None, entry: SourceEntry) -> None:
        """A contribution local to skill `slot` (and optionally also tag-scoped). Folds into the base `stat`
        key only for that slot's offense pass (via materialize_for_skill); never enters the base
        `_entries`/`source_log`, so it cannot leak into other slots or the global character stats."""
        entry.slot = slot
        entry.scope = scope
        self.slot_entries.append((stat, amount, slot, scope))
        self.slot_log.append(entry)

    def materialize_for_skill(self, mod_tags: set[str], slot: int | None = None) -> "BuildSource":
        """Return a source whose `_entries`/`source_log` are the base PLUS the scoped contributions whose
        scope is in `mod_tags` AND the slot-local contributions for `slot` (whose scope, if any, also
        matches). Identity fast-path (returns self) when there are no scoped/slot entries or none match →
        the offense runs on the same object → identical output. `consumed_stats` is SHARED so badge
        recording sees the folded base keys; offense only READS the effective source, never mutates it."""
        if not self.scoped_entries and not self.slot_entries:
            return self
        matched = [(s, a) for (s, a, sc) in self.scoped_entries if sc in mod_tags]
        matched_slot = [(s, a) for (s, a, sl, sc) in self.slot_entries
                        if sl == slot and (sc is None or sc in mod_tags)]
        if not matched and not matched_slot:
            return self
        return BuildSource(
            _entries=self._entries + matched + matched_slot,
            source_log=self.source_log
            + [e for e in self.scoped_log if e.scope in mod_tags]
            + [e for e in self.slot_log if e.slot == slot and (e.scope is None or e.scope in mod_tags)],
            consumed_stats=self.consumed_stats,
            _recording=self._recording,
            # Carry the overlays forward so a materialized source can still fold (defensive; offense only
            # reads _entries/source_log/total so this does not affect output).
            scoped_entries=self.scoped_entries,
            scoped_log=self.scoped_log,
            slot_entries=self.slot_entries,
            slot_log=self.slot_log,
        )

    def total(self, stat: str) -> float:
        if self._recording:
            self.consumed_stats.add(stat)
        return sum(v for s, v in self._entries if s == stat)

    def all_stats(self) -> set[str]:
        return {s for s, _ in self._entries}

    def main_hand_flat(self, dtype: str, which: str) -> float:
        """Sum of the MAIN-HAND (weapon1) weapon-base flat damage for `dtype` ('min'|'max'), from source_log
        entries tagged weapon_slot == 'weapon1'. Used to scope a main-hand-only additional modifier (e.g. Rosa
        Born to Cleanse) to the main-hand weapon's share of an attack hit."""
        key = f"{dtype}_dmg_gear_flat_{which}"
        return sum(e.amount for e in self.source_log if e.stat == key and e.weapon_slot == "weapon1")


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
    # Editable calc-target ("dummy") stats as FRACTIONS: {level, armor, fire_res, cold_res, lightning_res,
    # erosion_res}. None → offense uses its historical Lv85 constants.
    target_config: dict | None = None
    # Unified condition state: boolean conditions store True/False, numeric store float.
    condition_state: dict[str, float | bool] = field(default_factory=dict)
    gear:            list[dict] = field(default_factory=list)  # GearEngineItem dicts
    character:       list[dict] = field(default_factory=list)  # CharacterStatContribution dicts
    memory_effects:  list[str]  = field(default_factory=list)  # DEPRECATED: now pre-resolved server-side
    spirit_effects:  list[str]  = field(default_factory=list)  # DEPRECATED: now pre-resolved server-side
    # Pre-resolved pact-spirit / hero-memory contributions (server._resolve_effect_modifiers). Same shape as
    # custom_contributions plus an optional `condition` gate (translated expr) — applied/gated in aggregate().
    spirit_contributions: list[dict] = field(default_factory=list)
    memory_contributions: list[dict] = field(default_factory=list)
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
    # Pre-resolved talent-tree NODE + SLATE contributions (unified resolver, server.resolve_nodes). Same
    # shape as core_talent_contributions; amounts pre-scaled by points; conditionals gated via condition_expr.
    node_contributions: list[dict] = field(default_factory=list)
    # Parsed-but-UNSCALED aura/Focus buffs (server.aura_resolver) + per-aura meta. engine.utility scales them by
    # the fully-aggregated Aura Effect inside the compute loop and folds them in as source_type "aura".
    aura_buffs: list[dict] = field(default_factory=list)
    aura_meta: dict = field(default_factory=dict)
    # Active curses (server.curse_resolver.resolve_curses) + per-curse meta. engine.curse_resolver.apply_curses
    # scales them by Curse Effect inside the compute loop and bakes the *_curse_taken enemy-vulnerability pools.
    curses: list[dict] = field(default_factory=list)
    curse_meta: dict = field(default_factory=dict)
    # Parsed-but-UNSCALED empower (Euphoria) buffs + per-empower meta. engine.utility.apply_empower_buffs scales
    # them by Empower Skill Effect inside the compute loop and folds them in (source_type "empower").
    empower_buffs: list[dict] = field(default_factory=list)
    empower_meta: dict = field(default_factory=dict)
    # Parsed-but-UNSCALED elixir buffs + per-elixir meta. engine.utility.apply_elixir_buffs scales them by Elixir
    # Effect inside the compute loop and folds them in player-wide (source_type "elixir"). Full uptime assumed.
    elixir_buffs: list[dict] = field(default_factory=list)
    elixir_meta: dict = field(default_factory=dict)
    # Hero trait (Erika Lightning Shadow, …). For traits with a bespoke engine.hero_traits module the
    # module owns resolution; trait_contributions is (re)computed each loop pass by the module and folded
    # by aggregate() like spirit/memory contributions. For non-bespoke traits the server pre-resolves
    # trait_effects into trait_contributions directly.
    trait_id: str | None = None
    trait_slot_levels: list[int] = field(default_factory=list)       # [base, lv45, lv60, lv75], each 1-5
    advanced_trait_selections: list[str] = field(default_factory=list)
    trait_contributions: list[dict] = field(default_factory=list)
    # Licorice Note (Sage): skill_id of the Empower/Curse the trait prepares (Pungent cross-apply target).
    licorice_prepared_skill: str | None = None
    # Uptime calc mode: "max" (default; assume-max/legacy behavior) | "real" (compute ramp via engine.uptime).
    uptime_mode: str = "max"
    # Generalized "inflicts Numbed" effects from non-support sources (talents/gear/slates/custom mods),
    # built server-side by engine.ailment_inflict. Same shape as the support cond_effects: floor numbed_stacks
    # + enable enemy_numbed, gated by hit damage type. `numbed_blocked` hard-overrides (H "cannot inflict").
    inflict_cond_effects: list = field(default_factory=list)
    numbed_blocked: bool = False


@dataclass
class StatResult:
    """Output of engine.compute()."""
    stat_map:            dict                    # {stat_key: {display_name, total, sources, ...}}
    condition_maximums:  dict[str, float]        # {condition_key: derived_max}
    clamp_report:        dict[str, dict]         # {key: {"requested": v, "applied": v}}
    offense:             dict | None = None      # OffenseResult as dict, or None if no skill
    defense:             dict | None = None      # DefenseResult as dict
    recovery:            dict | None = None      # RecoveryResult as dict (restoration/regain/regen/temp/EHP)
    consumption:         dict | None = None      # ConsumptionResult as dict (self-consume drains + consumed-recently)
    skill_cost:          dict | None = None      # SkillCostResult as dict (active skill per-cast Mana/Life cost breakdown)
    skill_slots:         list[dict] | None = None  # per-slot summary: slot, skill_id, skill_name, level, effective_level, supported
    consumed_stats:      list[str] = field(default_factory=list)  # stat keys the offense/defense/derive passes actually read for this build
    target_stats:        dict | None = None       # calc-target armor/resist (base + effective after pen) + active enemy debuffs
    slot_offense:        dict | None = None       # {slot: OffenseResult dict} per active skill slot; headline `offense` = main slot
    blessings:           list | None = None        # per-blessing display summary (stacks/max/effects); golden-neutral
    aura_summaries:      list | None = None        # per-aura display summary (Aura Effect, granted buffs, NYI)
    empower_summaries:   list | None = None        # per-empower display summary (Empower Effect, granted buffs, NYI)
    elixir_summaries:    list | None = None        # per-elixir display summary (Elixir Effect, granted buffs, timing, NYI)
    curse_summaries:     list | None = None        # per-curse display summary (Curse Effect, limit, debuff value)
    curse_conflict:      dict | None = None         # set when active curses exceed the limit (needs resolution)
    warnings:            list | None = None         # general build diagnostics (e.g. an ineffective/dead curse)
    reservation:         dict | None = None         # mana/life sealing: totals + per-skill seal breakdowns
    numbed:              dict | None = None          # Numbed ailment box: base/stacks/duration/effect pools + uptime
    referenced_conditions: list[str] = field(default_factory=list)  # condition keys any build mod references (gate on/off) — UI hides the rest
    auto_conditions:     dict[str, dict] = field(default_factory=dict)  # engine-activated (not user-set) conditions → {value, source} for the Config "auto" badge
