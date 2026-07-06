# Minion Modifier Coverage — audit

What's hooked up for minions, and what isn't yet. Gear and talent minion mods both flow through the shared
`engine/mod_parser.py`; talent/core-talent contributions inject **globally** and already reach the minion offense
(no remap needed). Supports and the Isomorphic-Arms weapon transfer convert player stats → minion stats via
`engine.minion_offense.to_minion_stat[_strict]`.

## ✅ Now wired (this pass)

**Parser** (`mod_parser.py`) — minion affixes resolve to minion pools, never leak to the player:
- Trailing minion-scope peel: `"… for/by Minions [summoned by the supported skill]"` / `"… for Spirit Magi"` →
  resolve the core, **strict**-remap each result to its minion stat; anything with no minion twin is DROPPED
  (surfaced red), never passed through to the player.
- `"+N% [additional] Minion Attack and Cast Speed"` → BOTH `minion_attack_speed_*` + `minion_cast_speed_*`.
- `"Adds N-M [Base] <Type> Damage to Minions"` → `minion_<type>_dmg_flat_min/max`.
- `"Minion Damage penetrates N% <type> Resistance"` → `minion_elemental_pen` / `minion_<type>_pen_inc`.
- `"+N% additional Damage Taken by Minions / Spirit Magi"` → `minion_dmg_taken_additional` (no player leak).
- `"+N% chance for Minions to deal Double Damage"` → `minion_double_dmg_chance` (was Synthetic-Troop stat).
- Guard: `tests/test_minion_mod_coverage.py`.

**Consumption** (`minion_offense.py` / `thunder_magus.py`):
- **Minion penetration** now applied in the minion mitigation path (`_minion_target_mitigation`) — minion damage
  penetrates with the MINION's pen (`minion_armor_pen`, `minion_elemental_pen`, `minion_<type>_pen_inc`), NOT the
  player's. New typed stats `minion_cold/lightning/erosion_pen_inc`.
- **Spirit-Magi damage/crit** (`spirit_magi_dmg_inc/_additional`, `spirit_magi_crit_rating_flat`) — carried the
  `spirit_magi` tag (which the minion offense skips), now **folded** into the generic minion pools by the magus
  module (`fold_spirit_magi_pools`), scoped to magi only.
- **Empower Effect** — the Euphoria buff scales by `spirit_magi_empower_effect_additional` (minion/magi only).
- **Remap bridges**: player↔minion damage infix (`{type}_{attack|spell}_dmg_*` and `{type}_dmg_gear_*`), typed pen
  (`fire_pen ↔ minion_fire_pen_inc`), weapon affix AS/crit (`attack_speed_gear/_mh`, `attack_crit_rating_gear/_mh`).

**Isomorphic Arms** (`god_of_machines_isomorphic_arms`): weapon transfer (glossary "Applied Weapon Bonuses" 173)
— main-hand Base Damage + affixes → minion pools; base `weapon_attack_speed`/`weapon_crit_rating_flat` correctly
do NOT transfer (no minion twin). `"+30% additional Spell Damage for Minions when wielding a Wand/Tin Staff"`
resolves + gates on the existing `wielding_wand_or_tin_staff` condition.

## 🔴 Not hooked up yet (flagged)

### Needs a NEW minion stat (mod would resolve once the stat exists)
- `minion_cdr_speed_additional` — "additional Cooldown Recovery Speed for Minions" (only the *increased* pool exists).
- generic minion **ultimate** CDR — "additional Cooldown Recovery Speed for the Ultimate of Minions" (only the
  Spirit-Magus-specific `spirit_magi_cdr_speed_inc` exists).
- `minion_max_life_additional` — "additional Minion Max Life / Life for Minions".
- `minion_max_life_as_es_pct` — "Adds N% of Max Life to Minion Energy Shield".
- minion **damage conversions** — "Adds N% of Physical Damage as <Type> to (Synthetic Troop) Minions".
- `+1 to the initial Multistrike Count for Spirit Magi`, `Projectile Flight Duration for Minions`,
  `additional Hit Damage for Minions`, `additional Synthetic Troop Minion Damage`, Merged-Spirit-Magi lines.

### Transfer/remap coverage gaps (no minion twin → dropped + flagged, e.g. Isomorphic-Arms weapon affixes)
Mechanic stats with no `minion_*` equivalent, so they don't transfer to a minion: **beam count/length**
(`extra_beams_flat`, `beam_length_additional`), **jumps/chains** (`extra_jumps_flat`), **projectile speed /
horizontal penetration** (`projectile_speed_inc`, `horizontal_projectile_penetration_flat`),
`max_life_as_es_pct`. (Add `minion_*` twins if/when a minion needs these.)

### Resolves but INERT (badges "modeled" yet changes nothing — needs a subsystem, NOT this pass)
- **Minion defense / life / EHP** (feeds the deferred right-column): `minion_max_life_inc`, `minion_life_regain_inc`,
  `minion_es_regain_inc`, `minion_life_regen_speed_inc`, `minion_dmg_taken_additional`,
  `minion_regain_shared_to_player`. ("Life Regain and ES Regain for Minions" also only partially resolves.)
- **Minion ailment / DoT**: `minion_ignite_chance`, `minion_trauma_chance`, `minion_damaging_ailment_chance`,
  `minion_affliction_effect_inc`, `minion_affliction_per_second_flat`.
- **Minion multistrike**: `minion_multistrike_chance`, `minion_multistrike_increasing_dmg_inc`.
- **Minion duration / skill-level / area / movement**: `minion_duration_inc` (summon lifetime),
  `minion_skill_level`, `minion_skill_area_inc` (Growth surfaces a display value but this pool is unread),
  `minion_movement_speed_inc`, `summon_skill_cast_speed_additional`.
- **Spirit-Magi Ultimate** (Full Bloom NYI): `spirit_magi_ultimate_dmg_inc/_additional`, `spirit_magi_cdr_speed_inc`.

### Known modeling limitations
- `minion_spell_dmg_additional` folds into the **generic** minion additional pool (spell isn't a damage-type tag),
  so "Spell Damage for Minions" applies to a magus's attacks too (Isomorphic-Arms effect 1 on an attack magus).
  Needs spell/attack skill-type scoping in the minion offense.
- Conditional/scaling minion mods ("per N Minions", "recently summoned", "at Low Life", per-Blessing/Elixir, "vs
  Ailment-affected") resolve their base but need condition wiring for the scaling clause.
- "Isometric Arms" is actually **Isomorphic Arms** (name corrected).
