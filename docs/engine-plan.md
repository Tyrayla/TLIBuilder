# TLIBuilder Calculation Engine — Implementation Plan

> Written: 2026-05-20  
> Scope: First-pass damage calculation engine wired to talent nodes, core talents, and slates.  
> Engine lives entirely in `backend/engine/`. The frontend is a consumer only.

---

## Table of Contents

1. [Damage Formula Reference](#1-damage-formula-reference)
2. [Stacking Rules Reference](#2-stacking-rules-reference)
3. [Stat Enum Gaps to Fill](#3-stat-enum-gaps-to-fill)
4. [StatMeta Expansion](#4-statmeta-expansion)
5. [Engine Folder Structure](#5-engine-folder-structure)
6. [Data Models — engine/models.py](#6-data-models--enginemodelspy)
7. [StatAggregator — engine/aggregator.py](#7-stataggregator--engineaggregatorpy)
8. [PipelineCalculator — engine/pipeline.py](#8-pipelinecalculator--enginepipelinepy)
9. [Resolver — engine/resolver.py](#9-resolver--engineresolverpy)
10. [API Endpoint](#10-api-endpoint)
11. [Implementation Order (Checklist)](#11-implementation-order-checklist)
12. [Out of Scope for First Pass](#12-out-of-scope-for-first-pass)

---

## 1. Damage Formula Reference

```
Final Damage =
  (Base + Flat)
  × (1 + Σ increased)
  × (1 + Σ add_generic)
  × (1 + Σ add_attack)       ← only if skill has Attack tag
  × (1 + Σ add_spell)        ← only if skill has Spell tag
  × (1 + Σ add_melee)        ← only if skill has Melee tag
  × (1 + Σ add_area)         ← only if skill has Area tag
  × (1 + Σ add_projectile)   ← only if skill has Projectile tag
  × (1 + Σ add_fire)         ← only if skill has Fire damage type
  × (1 + Σ add_cold)         ← only if skill has Cold damage type
  × (1 + Σ add_lightning)    ← only if skill has Lightning damage type
  × (1 + Σ add_erosion)      ← only if skill has Erosion damage type
  × (1 + Σ add_physical)     ← only if skill has Physical damage type
  × attr_factor
  × skill_multiplier
  × crit_factor
  × (1 + total_double_dmg_chance)   ← Hit only; expected value form
  × mitigation_factor
```

Each `(1 + Σ add_X)` bucket is its own independent multiplicative stage.  
Different categories multiply with each other; same-category sources sum inside the same bucket.

### Increased bucket

All `*_DMG_INC` stats that apply to the skill sum into a **single** additive pool:
```
increased_total = Σ(DMG_INC) + Σ(ATTACK_DMG_INC if attack) + Σ(SPELL_DMG_INC if spell)
                + Σ(PHYSICAL_DMG_INC if physical) + Σ(FIRE_DMG_INC if fire) + ...
factor = (1 + increased_total)
```

### Attribute factor

Each main attribute contributes **0.5% additional damage per point** for tag-matched skills.
Multiple applicable attributes sum their totals before applying the single factor:
```
relevant_attr_points = Σ(attribute_value for each attribute that matches a skill tag)
attr_factor = (1 + relevant_attr_points × 0.005)
```
STR → Physical/Attack skills  
DEX → Attack/Projectile skills  
INT → Spell/Elemental skills  
(exact tag↔attribute mapping to be confirmed in-game)

### Skill multiplier (levels 31+)

Each extra skill level at 31+ is an **independent** ×1.08 multiplier per level:
```
extra_levels = (base_level + bonus_levels) - 30   # only if > 0
skill_multiplier = 1.08 ** max(0, extra_levels)
```
"Multiplies" tagged sources also use independent multiplication, not the additive buckets.

### Critical strike factor

```
CSR_final = base_CSR × (1 + Σ crit_rating_inc) × (1 + Σ crit_rating_additional_1) × ...
crit_chance = min(CSR_final / 100.0, 1.0)
crit_dmg_multiplier = 1.50 + Σ(CRIT_DMG) + Σ(ATTACK_CRIT_DMG if attack) + ...
crit_factor = 1.0 + crit_chance × (crit_dmg_multiplier - 1.0)
```
Default crit damage: 150% (i.e. ×1.5 on a crit).

### Double damage factor (Hit only, expected value)

```
total_double_chance = Σ(DOUBLE_DMG_CHANCE) + Σ(ATTACK_DOUBLE_DMG_CHANCE if attack) + ...
double_factor = (1 + total_double_chance)   ← clamp chance to [0, 1] before adding
```

### Mitigation

**Elemental (Fire/Cold/Lightning/Erosion):**
```
effective_resistance = max(0.0, enemy_resistance - penetration)
mitigation = (1 - effective_resistance)
```
Penetration lowers the resistance value used in the calc only; does not change the enemy's stat.

**Physical:**
```
mitigation = (1 - armor / (armor + some_k_constant))   ← k to be confirmed
```
Physical has armor mitigation only; no resistance.

---

## 2. Stacking Rules Reference

| Type | How they stack | Example |
|---|---|---|
| Increased / Reduced | All additive in one pool | 20% inc + 30% inc = 50% inc → ×1.5 |
| Additional (same category) | Additive within bucket | 20% add_attack + 20% add_attack = ×1.4 |
| Additional (different categories) | Multiply across buckets | 20% add_attack × 20% add_fire = 1.2 × 1.2 = ×1.44 |
| Skill levels 31+ | Each level independent multiply | Lv31+2 = ×1.08² = ×1.1664 |
| Crit rating (inc) | Additive inside increased bucket | — |
| Crit rating (additional) | Each source its own × bucket | — |
| Double damage chances | Additive (one check) | 20% + 30% = 50% chance |
| Penetration sources | Additive total | 10% pen + 10% pen = 20% pen applied to resistance |

---

## 3. Stat Enum Gaps to Fill

Add these to `backend/models/stat.py` and matching entries to `stat_meta.py`.

**Do NOT add `_MORE` multiplier stats.** TLI has no separate "more" bucket. `ADDITIONAL` stats ARE the multiplicative layer. The `_MORE` naming is PoE-specific and does not map to this game.

### Life (add to `# ── Life` section)
```python
MAX_LIFE                = "max_life"                # flat max life
MAX_LIFE_INC            = "max_life_inc"            # % increased max life
LIFE_REGEN_FLAT         = "life_regen_flat"         # flat life regen per second
LIFE_REGEN_INC          = "life_regen_inc"          # % increased life regen
LIFE_LEECH_RATE         = "life_leech_rate"         # % life leeched on hit
```

### Mana (add to `# ── Mana` section)
```python
MAX_MANA                = "max_mana"
MAX_MANA_INC            = "max_mana_inc"
MANA_REGEN_FLAT         = "mana_regen_flat"
MANA_REGEN_INC          = "mana_regen_inc"
SKILL_COST_REDUCTION    = "skill_cost_reduction"    # flat/% reduction
```

### Utility (add to `# ── Utility` section)
```python
MOVEMENT_SPEED_INC      = "movement_speed_inc"
COOLDOWN_REDUCTION_INC  = "cooldown_reduction_inc"
```

### Minion / Sentry gaps (confirm in-game before adding)
- Sentry damage inc is likely missing  
- Spirit Magi stats need investigation  
- Synthetic troops may have more stats

---

## 4. StatMeta Expansion

Expand the `StatMeta` dataclass in `backend/models/stat_meta.py` to support engine evaluation and richer UI metadata.

### New dataclass definition
```python
@dataclass(frozen=True)
class StatMeta:
    display_name:    str
    category:        str
    modifier_type:   str           # see types below
    unit:            str  = ""     # "" | "%" | "/s"
    subgroup:        str  = ""     # e.g. "fire_damage", "crit", "speed"
    pipeline_stage:  str  = ""     # see stage table below
    tags:            tuple = ()    # skill tags this stat applies to: ("attack",) ("fire",) etc.
    affects:         tuple = ()    # ("hit",) | ("hit","dot") | ("all",) | ("hit","dot","secondary","reflect")
    stacking_rule:   str  = ""     # "additive" | "independent" | "additive_chance"
    ui_priority:     int  = 50     # 1-100, lower = show first
    source_types:    tuple = ()    # see source types list below
```

### modifier_type values (canonical)
- `"base_stat"` — attributes (STR/DEX/INT)
- `"added_flat"` — raw additive flat (flat lightning damage, flat life)
- `"increased"` — additive % pool: goes into the single (1 + Σinc) factor
- `"additional"` — independent multiplicative bucket; each distinct stat is its own factor
- `"chance"` — additive probability (double dmg, crit chance)
- `"skill_level"` — additive level bonus (sums before skill_multiply stage)
- `"skill_multiply"` — independent ×1.08 per point (levels 31+, or `(multiplies)` tagged sources)
- `"penetration"` — additive resistance reduction at calculation time
- `"crit_rating"` — feeds into CSR calculation
- `"crit_damage"` — feeds into crit damage multiplier

**Note:** There is NO `"more"` type. TLI's "additional" = PoE's "more". Do not add `_MORE` stats.

### pipeline_stage values (used by engine)
| Stage constant | What it feeds |
|---|---|
| `"base"` | Skill's own base damage at its level |
| `"added_flat"` | Flat damage ranges summed into base |
| `"increased_reduced"` | Single `(1 + Σinc - Σred)` factor |
| `"additional"` | Each stat is its own `(1 + Σwithin_stat)` factor; different stats multiply |
| `"attribute"` | `(1 + total_attr_points × 0.005)` factor for tag-matched skills |
| `"skill_level"` | Additive level sum; used to derive levels_above_30 |
| `"skill_multiply"` | `1.08^n` per extra level 31+ (also `(multiplies)` tagged sources) |
| `"crit_rating"` | CSR calculation → crit_chance |
| `"crit_damage"` | Crit multiplier; default 150% |
| `"double_damage"` | `(1 + Σchance)` Hit-only expected value factor |
| `"penetration"` | Enemy effective resistance reduction; applies to Hit/DoT/Secondary/Reflect |
| `"mitigation"` | Final factor: armor (physical) or resistance (elemental) |

### source_types values (first-pass covered vs. future)
| Value | Covered in first pass |
|---|---|
| `"talent_node"` | Yes |
| `"core_talent"` | Partial (no recipe mapping yet) |
| `"slate"` | Yes |
| `"legendary_gear"` | No |
| `"normal_gear"` | No |
| `"hero_memory"` | No |
| `"hero_trait"` | No |
| `"pactspirit"` | No |
| `"new_god_talent"` | No |
| `"skill"` | No (skill provides base, not modifiers) |
| `"buff"` | No |

### Example updated entries
```python
Stat.ATTACK_DMG_ADDITIONAL: StatMeta(
    display_name  = "Additional Attack Damage",
    category      = "Attack",
    modifier_type = "additional",
    unit          = "%",
    subgroup      = "attack_damage",
    pipeline_stage= "additional",
    tags          = ("attack",),
    affects       = ("hit", "dot"),
    stacking_rule = "additive",       # additive within this bucket; separate from DMG_ADDITIONAL
    ui_priority   = 10,
    source_types  = ("talent_node", "core_talent", "slate"),
),

Stat.DMG_ADDITIONAL: StatMeta(
    display_name  = "Additional Damage",
    category      = "Generic",
    modifier_type = "additional",
    unit          = "%",
    subgroup      = "generic_damage",
    pipeline_stage= "additional",
    tags          = (),               # applies to all damage
    affects       = ("hit", "dot"),
    stacking_rule = "additive",       # additive with other DMG_ADDITIONAL; × with ATTACK_DMG_ADDITIONAL
    ui_priority   = 5,
    source_types  = ("talent_node", "core_talent", "slate"),
),

Stat.FIRE_PEN: StatMeta(
    display_name  = "Fire Penetration",
    category      = "Fire",
    modifier_type = "penetration",
    unit          = "%",
    subgroup      = "fire_damage",
    pipeline_stage= "penetration",
    tags          = ("fire",),
    affects       = ("hit", "dot", "secondary", "reflect"),
    stacking_rule = "additive",
    ui_priority   = 30,
    source_types  = ("talent_node", "core_talent", "slate"),
),

Stat.DMG_INC: StatMeta(
    display_name  = "Increased Damage",
    category      = "Generic",
    modifier_type = "increased",
    unit          = "%",
    subgroup      = "generic_damage",
    pipeline_stage= "increased_reduced",
    tags          = (),               # applies to all damage; pools with all other increased stats
    affects       = ("hit", "dot"),
    stacking_rule = "additive",
    ui_priority   = 1,
    source_types  = ("talent_node", "core_talent", "slate"),
),
```

---

## 5. Engine Folder Structure

```
backend/engine/
    __init__.py
    models.py        # Pure data classes: inputs/outputs; no logic
    aggregator.py    # StatAggregator: reads build sources → raw stat totals
    pipeline.py      # PipelineCalculator: applies formula stages in order
    resolver.py      # Public entry point: BuildInput → ComputedResult
```

No circular imports. `models.py` imports nothing from engine. `aggregator.py` imports only models.  
`pipeline.py` imports only models. `resolver.py` orchestrates the other three.

---

## 6. Data Models — engine/models.py

```python
from dataclasses import dataclass, field

@dataclass
class SkillConfig:
    name:           str
    skill_type:     str              # "attack" | "spell"
    tags:           list[str]        # ["attack", "melee", "fire", "area", ...]
    damage_types:   list[str]        # ["fire", "physical", "lightning", ...]
    base_level:     int
    extra_levels:   int = 0          # from +skill level sources; engine adds build levels on top
    base_dmg_min:   float = 0.0
    base_dmg_max:   float = 0.0
    base_csr:       float = 0.0      # base critical strike rating

@dataclass
class EnemyConfig:
    fire_resistance:       float = 0.0
    cold_resistance:       float = 0.0
    lightning_resistance:  float = 0.0
    erosion_resistance:    float = 0.0
    armor:                 float = 0.0

@dataclass
class BuildSource:
    """Flat list of (stat_value, amount) pairs collected from all build sources."""
    entries: list[tuple[str, float]] = field(default_factory=list)

    def add(self, stat: str, amount: float) -> None:
        self.entries.append((stat, amount))

    def total(self, stat: str) -> float:
        return sum(v for s, v in self.entries if s == stat)

@dataclass
class ComputedResult:
    avg_hit:          float = 0.0
    crit_chance:      float = 0.0
    crit_multiplier:  float = 1.5
    effective_dps:    float = 0.0
    breakdown:        dict  = field(default_factory=dict)  # stage_name → factor value

@dataclass
class BuildInput:
    """
    Passed to resolver.compute(). Contains everything needed to run the pipeline.
    Talent nodes come from the full season tree loaded at request time.
    """
    slots:      list[dict | None]   # TreeSlot dicts from the saved build
    slates:     list[dict]          # SavedSlate dicts from the saved build
    skill:      SkillConfig
    enemy:      EnemyConfig
    season:     str                 # active season name for data lookups
```

---

## 7. StatAggregator — engine/aggregator.py

Reads from all build sources and produces a `BuildSource` (flat stat total list).

### Input sources (first pass)
1. **Talent nodes** — allocated nodes from each `TreeSlot.nodeStates`
2. **Core talents** — _currently no normalized stat mapping; skip for first pass or use effect string fallback_
3. **Slates** — each `CreatorSlot.selectedNodeId` maps to a talent node (use same recipe lookup as talent nodes)

### Talent node aggregation algorithm

```
For each slot in build.slots (non-null):
  tree_name = slot["treeName"]
  node_states = slot["nodeStates"]   # {node_id: current_points}

  Load season tree data for (season, tree_name)
  Load node_type_filter recipes for tree_name

  For each (node_id, current_points) in node_states where current_points > 0:
    Find the node in season tree → get node_type, max_points
    rank_index = current_points - 1   # 0-indexed
    recipes = filter["recipes"][tree_name][node_type]

    For each recipe in recipes:
      value = recipe["values"][rank_index]
      build_source.add(recipe["stat"], value)
```

### Slate aggregation algorithm

```
For each placed_slate in build.slates:
  For each slot in placed_slate.slots where slot.selectedNodeId is not None:
    node_id = slot.selectedNodeId
    Determine which tree owns this node (parse prefix from node_id: "treeslug_cN_rN")
    Load season tree data for that tree
    Find node → get node_type, max_points
    recipes = filter["recipes"][tree_name][node_type]
    For each recipe in recipes:
      value = recipe["values"][0]   # slates always use rank-1 (1 point)
      build_source.add(recipe["stat"], value)
```

### Attribute aggregation

Attributes come from talent nodes too — `Stat.STRENGTH`, `Stat.DEXTERITY`, `Stat.INTELLIGENCE` are in the recipes. They will be collected normally by the talent node loop. The pipeline reads them from `BuildSource`.

### Skill level aggregation

Sum all relevant skill level stats and store total in BuildSource:
```
all_skill_level  = build_source.total("all_skill_level")
attack_skill_lvl = build_source.total("attack_skill_level")   # if skill is attack
...etc
extra_levels = base extra_levels + all_skill_level + matching_type_level + matching_tag_level
```

---

## 8. PipelineCalculator — engine/pipeline.py

Runs the damage formula in strict stage order. Reads from `BuildSource` + `SkillConfig` + `EnemyConfig`.

### Stage 1 — Base + Flat

```python
flat_min = skill.base_dmg_min
flat_max = skill.base_dmg_max

# Add flat elemental damage from gear/nodes if skill has matching type
for dmg_type in skill.damage_types:
    flat_min += build.total(f"{dmg_type}_attack_dmg_flat_min")  # or spell variant
    flat_max += build.total(f"{dmg_type}_attack_dmg_flat_max")

avg_base = (flat_min + flat_max) / 2
```

### Stage 2 — Increased/Reduced (`increased_reduced`)

All `*_DMG_INC` stats matching the skill sum into **one additive pool**:
```python
inc = build.total("dmg_inc")
if "attack" in skill.tags:  inc += build.total("attack_dmg_inc")
if "spell"  in skill.tags:  inc += build.total("spell_dmg_inc")
if "melee"  in skill.tags:  inc += build.total("melee_dmg_inc")
if "area"   in skill.tags:  inc += build.total("area_dmg_inc")
if "projectile" in skill.tags: inc += build.total("projectile_dmg_inc")
for dmg_type in skill.damage_types:
    inc += build.total(f"{dmg_type}_dmg_inc")

inc_factor = 1.0 + inc
```

### Stage 3 — Additional (independent buckets)

Each stat key that maps to `pipeline_stage = "additional"` and whose tags match the skill is its own factor:

```python
additional_factors = []

buckets = [
    ("dmg_additional",          lambda: True),
    ("attack_dmg_additional",   lambda: "attack"      in skill.tags),
    ("spell_dmg_additional",    lambda: "spell"       in skill.tags),
    ("melee_dmg_additional",    lambda: "melee"       in skill.tags),
    ("area_dmg_additional",     lambda: "area"        in skill.tags),
    ("projectile_dmg_additional", lambda: "projectile" in skill.tags),
    ("minion_dmg_additional",   lambda: "minion"      in skill.tags),
    ("physical_dmg_additional", lambda: "physical"    in skill.damage_types),
    ("fire_dmg_additional",     lambda: "fire"        in skill.damage_types),
    ("cold_dmg_additional",     lambda: "cold"        in skill.damage_types),
    ("lightning_dmg_additional",lambda: "lightning"   in skill.damage_types),
    ("erosion_dmg_additional",  lambda: "erosion"     in skill.damage_types),
    ("elemental_dmg_additional",lambda: any(t in skill.damage_types for t in ("fire","cold","lightning","erosion"))),
    ("sentry_dmg_additional",   lambda: "sentry"      in skill.tags),
]

for stat_key, condition in buckets:
    if condition():
        val = build.total(stat_key)
        if val != 0:
            additional_factors.append(1.0 + val)
```

### Stage 4 — Attribute factor

```python
relevant_attrs = 0
# Map tags to attributes (to be validated in-game):
if "attack" in skill.tags or "physical" in skill.damage_types:
    relevant_attrs += build.total("strength")
if "attack" in skill.tags or "projectile" in skill.tags:
    relevant_attrs += build.total("dexterity")
if "spell" in skill.tags or any(t in ("fire","cold","lightning","erosion") for t in skill.damage_types):
    relevant_attrs += build.total("intelligence")

attr_factor = 1.0 + relevant_attrs * 0.005
```

### Stage 5 — Skill multiplier

```python
all_lvl    = build.total("all_skill_level")
active_lvl = build.total("active_skill_level")
type_lvl   = build.total(f"{skill.skill_type}_skill_level")  # attack_ or spell_
tag_lvls   = sum(build.total(f"{t}_skill_level") for t in skill.tags if t not in ("attack","spell"))

total_extra = skill.extra_levels + int(all_lvl) + int(active_lvl) + int(type_lvl) + int(tag_lvls)
effective_level = skill.base_level + total_extra
levels_above_30 = max(0, effective_level - 30)
skill_multiplier = 1.08 ** levels_above_30
```

### Stage 6 — Critical strike

```python
# CSR
base_csr    = skill.base_csr + build.total("attack_crit_rating_flat")  # or spell variant
csr_inc     = build.total("attack_crit_rating_inc")                     # or spell variant
# Additional crit rating: each source that specifies "additional" for crit rating
# (Currently no separate additional crit rating stats exist — confirm in-game)
csr_final   = base_csr * (1.0 + csr_inc)
crit_chance = min(csr_final / 100.0, 1.0)

# Crit damage
crit_dmg = 1.50
crit_dmg += build.total("crit_dmg")
if "attack" in skill.tags: crit_dmg += build.total("attack_crit_dmg")
if "spell"  in skill.tags: crit_dmg += build.total("spell_crit_dmg")
for dmg_type in skill.damage_types:
    crit_dmg += build.total(f"{dmg_type}_crit_dmg")

crit_factor = 1.0 + crit_chance * (crit_dmg - 1.0)
```

### Stage 7 — Double damage (Hit only, expected value)

```python
dd_chance = build.total("double_dmg_chance")
if "attack" in skill.tags: dd_chance += build.total("attack_double_dmg_chance")
if "spell"  in skill.tags: dd_chance += build.total("spell_double_dmg_chance")
if "minion" in skill.tags: dd_chance += build.total("minion_double_dmg_chance")

dd_chance = min(dd_chance, 1.0)   # clamp; technically can exceed 100% → still factor 2
double_factor = 1.0 + dd_chance
```

### Stage 8 — Mitigation

```python
mitigation_factor = 1.0
for dmg_type in skill.damage_types:
    if dmg_type == "physical":
        # armor formula — k constant TBD
        k = 1000
        eff_armor = enemy.armor * (1 - build.total("armor_pen"))
        mit = eff_armor / (eff_armor + k)
        mitigation_factor *= (1.0 - mit)
    else:
        pen = build.total(f"{dmg_type}_pen") + build.total("elemental_pen")
        eff_res = max(0.0, getattr(enemy, f"{dmg_type}_resistance") - pen)
        mitigation_factor *= (1.0 - eff_res)
```

### Combine all stages

```python
avg_hit = avg_base
avg_hit *= inc_factor
for f in additional_factors:
    avg_hit *= f
avg_hit *= attr_factor
avg_hit *= skill_multiplier
avg_hit *= crit_factor
avg_hit *= double_factor
avg_hit *= mitigation_factor

breakdown = {
    "avg_base":        avg_base,
    "inc_factor":      inc_factor,
    "additional":      additional_factors,
    "attr_factor":     attr_factor,
    "skill_multiplier":skill_multiplier,
    "crit_chance":     crit_chance,
    "crit_multiplier": crit_dmg,
    "crit_factor":     crit_factor,
    "double_factor":   double_factor,
    "mitigation":      mitigation_factor,
    "avg_hit":         avg_hit,
}
```

---

## 9. Resolver — engine/resolver.py

Public entry point. Loads data, calls aggregator, calls pipeline, returns result.

```python
def compute(build_input: BuildInput) -> ComputedResult:
    # 1. Load node_type_filter recipes
    filter_data = node_type_filter_builder.load_filter()

    # 2. Load season tree data for all trees in the build
    season_trees = {}
    for slot in build_input.slots:
        if slot:
            tree_slug = slug(slot["treeName"])
            season_trees[tree_slug] = season_manager.load_season_tree(build_input.season, tree_slug)

    # 3. Aggregate stats
    build_source = aggregate(build_input, season_trees, filter_data)

    # 4. Run pipeline
    result = run_pipeline(build_source, build_input.skill, build_input.enemy)

    return result
```

---

## 10. API Endpoint

Add to `backend/server.py`:

```python
class SkillConfigRequest(BaseModel):
    name:          str
    skill_type:    str           # "attack" | "spell"
    tags:          list[str]
    damage_types:  list[str]
    base_level:    int
    extra_levels:  int = 0
    base_dmg_min:  float = 0.0
    base_dmg_max:  float = 0.0
    base_csr:      float = 0.0

class EnemyConfigRequest(BaseModel):
    fire_resistance:      float = 0.0
    cold_resistance:      float = 0.0
    lightning_resistance: float = 0.0
    erosion_resistance:   float = 0.0
    armor:                float = 0.0

class EngineComputeRequest(BaseModel):
    slots:   list[SlotData | None]
    slates:  list[dict] = []
    skill:   SkillConfigRequest
    enemy:   EnemyConfigRequest = EnemyConfigRequest()

@app.post("/api/engine/compute")
def engine_compute(req: EngineComputeRequest):
    from engine.resolver import compute
    from engine.models import BuildInput, SkillConfig, EnemyConfig
    result = compute(BuildInput(
        slots=...,
        slates=req.slates,
        skill=SkillConfig(**req.skill.model_dump()),
        enemy=EnemyConfig(**req.enemy.model_dump()),
        season=season_manager.get_active_season() or "",
    ))
    return result
```

Client-side API method to add to `client.ts`:
```typescript
engineCompute: (payload: EngineComputePayload) =>
  post<ComputedResult>('/engine/compute', payload),
```

---

## 11. Implementation Order (Checklist)

### Phase 1 — Data model prep
- [ ] Add missing Life/Mana/Utility stats to `backend/models/stat.py`
- [ ] Expand `StatMeta` dataclass fields in `backend/models/stat_meta.py` (add: subgroup, pipeline_stage, tags, affects, stacking_rule, ui_priority, source_types)
- [ ] Update all existing `STAT_META` entries with new fields (pipeline_stage, tags, affects, stacking_rule, subgroup)
- [ ] Add new stat entries to `STAT_META` for new Life/Mana/Utility stats

### Phase 2 — Engine skeleton
- [ ] Create `backend/engine/__init__.py` (empty)
- [ ] Create `backend/engine/models.py` with `SkillConfig`, `EnemyConfig`, `BuildSource`, `BuildInput`, `ComputedResult`

### Phase 3 — Aggregator
- [ ] Create `backend/engine/aggregator.py`
- [ ] Implement talent node → recipe lookup → `BuildSource` population
- [ ] Implement slate slot → recipe lookup (same logic, rank-1 always)
- [ ] Implement skill level summing helper

### Phase 4 — Pipeline
- [ ] Create `backend/engine/pipeline.py`
- [ ] Implement each stage function individually (flat, increased, additional, attr, skill_mult, crit, double, mitigation)
- [ ] Implement `run_pipeline()` that calls them in order and returns `ComputedResult`

### Phase 5 — Resolver
- [ ] Create `backend/engine/resolver.py`
- [ ] Wire data loading + aggregator + pipeline into `compute()` entry point

### Phase 6 — API
- [ ] Add `EngineComputeRequest`, `SkillConfigRequest`, `EnemyConfigRequest` to `server.py`
- [ ] Add `POST /api/engine/compute` endpoint
- [ ] Add `engineCompute` to `src/renderer/src/api/client.ts`

### Phase 7 — Smoke test
- [ ] Call the endpoint manually via browser DevTools or a test script
- [ ] Verify a simple fire spell build produces a sensible avg_hit number
- [ ] Check breakdown dict for each factor to confirm formula is applied in order

---

## 12. Out of Scope for First Pass

These are planned but deferred:

| Feature | Notes |
|---|---|
| Core talent stat mapping | Core talents currently have no recipe mapping in node_type_filter. Need a separate parse pass or manual mapping. |
| Legendary gear aggregation | Gear has its own stat format and affix structure. Separate aggregation path needed. |
| New god talent aggregation | Similar to core talents — no current normalized mapping. |
| Ailments / DoT | Separate pipeline needed; shares penetration logic. |
| Damage conversion | E.g. physical → fire via physical_as_fire stats. Needs conversion pipeline stage. |
| Conditional modifiers | If X then +Y damage. Needs a condition evaluator. |
| Snapshotting | Stat values captured at cast time. |
| Minion / Sentry sub-pipelines | Minion damage runs its own separate formula pass with minion-specific stats. |
| Multiple damage types (split damage) | Skills that deal e.g. 50% fire + 50% lightning need the pipeline run twice with weights. |
| DPS vs avg hit | Need attack speed / cast speed aggregation for full DPS output. |
| UI integration | The `/api/engine/compute` result display panel in BuildOverviewScreen. |

---

*End of plan.*
