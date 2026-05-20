# Stat Audit — Modifier Verification

> Working document. Delete after review is complete, or keep to track future mismatches.
>
> **Purpose:** Lists every modifier text found in the talent snapshot that either
> (a) has no matching stat in `stat.py`, or
> (b) maps to a stat whose name/semantics appear wrong for TLI.
>
> **How to use:** Answer YES / NO / RENAME in the `[ ]` column.
> - YES → add new stat key to `stat.py` + `stat_meta.py` + `node_modifier_pool.py`
> - NO → intentionally out of scope (skip)
> - RENAME → existing stat key needs a rename (note new key)

---

## ① Stats currently in stat.py that appear INCORRECT

These are flagged because the game uses different terminology than the key name implies.

| Current key | Issue | Suggestion |
|---|---|---|
| `LIFE_LEECH_RATE` | TLI has no life leech. Game shows "Life Regain" and "Life Restoration". | Rename to `LIFE_REGAIN` or `LIFE_REGAIN_INC` |
| `COOLDOWN_REDUCTION_INC` | Game shows "Cooldown Recovery Speed" not "reduction". | Rename to `COOLDOWN_RECOVERY_SPEED_INC` |

---

## ② Stats in stat.py that need VERIFICATION

These exist but their game names may differ from what the snapshot shows.

| Current key | Game text seen | Match? |
|---|---|---|
| `LIFE_REGEN_FLAT` | "+X Life Regeneration" — unclear if flat or rate | Verify |
| `LIFE_REGEN_INC` | "+X% Life Regeneration Speed" | Likely OK but name could be `_SPEED_` |
| `MANA_REGEN_INC` | "+X% Mana Regeneration Speed" | Same as above |
| `MAX_LIFE` | "+40 Max Life", "+80 Max Life" (flat, no %) | OK if treated as flat |
| `MAX_MANA` | "+15 Max Mana", "+30 Max Mana" (flat) | OK if treated as flat |
| `ARMOR` | "+450 Armor" (flat) | OK |

---

## ③ Missing Stats — Damage

Modifier texts from the snapshot with no stat in `stat.py`.

### Generic Damage
| [ ] | Modifier text example | Suggested key |
|---|---|---|
| [ ] | +9% Ailment Damage | `ailment_dmg_inc` |
| [ ] | +9% Damage Over Time | `dot_dmg_inc` |
| [ ] | +9% damage for Channeled Skills | `channeled_dmg_inc` |
| [ ] | +9% damage for Triggered Skills | `triggered_dmg_inc` |
| [ ] | +9% Tangle Damage | `tangle_dmg_inc` |
| [ ] | +9% Trauma Damage | `trauma_dmg_inc` |
| [ ] | +9% Spirit Magus Skill Damage | `spirit_magi_dmg_inc` |
| [ ] | +10% additional Base Damage for Two-Handed Weapons | `two_handed_dmg_additional` |
| [ ] | +12% damage dealt when holding a Shield | `shield_dmg_additional` |

### Minion Damage Variants
| [ ] | Modifier text example | Suggested key |
|---|---|---|
| [ ] | +18% Minion Fire Damage | `minion_fire_dmg_inc` |
| [ ] | +18% Minion Cold Damage | `minion_cold_dmg_inc` |
| [ ] | +18% Minion Lightning Damage | `minion_lightning_dmg_inc` |
| [ ] | +18% Minion Erosion Damage | `minion_erosion_dmg_inc` |
| [ ] | +18% Physical Damage for Minions | `minion_physical_dmg_inc` |
| [ ] | +12% additional Max Damage for Minions | `minion_dmg_additional` *(note: `MINION_DMG_ADDITIONAL` already exists — verify if same)* |
| [ ] | +8% additional Minion Damage if Synthetic Troop cast recently | conditional — skip for now? |

### Critical Strike (Type-specific)
| [ ] | Modifier text example | Suggested key |
|---|---|---|
| [ ] | +15% Projectile Critical Strike Damage | `projectile_crit_dmg` |
| [ ] | +15% Projectile Critical Strike Rating | `projectile_crit_rating_flat` |
| [ ] | +15% Sentry Skill Critical Strike Damage | `sentry_crit_dmg` |
| [ ] | +15% Sentry Skill Critical Strike Rating | `sentry_crit_rating_flat` |
| [ ] | +5% Spell Critical Strike Damage | `spell_crit_dmg` *(already as `SPELL_CRIT_DMG`?)* |
| [ ] | +14% Critical Strike Damage against enemies affected by Ailments | conditional — skip? |

---

## ④ Missing Stats — Life / Defense

| [ ] | Modifier text example | Suggested key |
|---|---|---|
| [ ] | +5% Life Regain | `life_regain_inc` *(replace `LIFE_LEECH_RATE`)* |
| [ ] | -15% additional Life Regain Interval | `life_regain_interval_reduction` |
| [ ] | +4% Life Regeneration Speed | `life_regen_speed_inc` *(or rename `LIFE_REGEN_INC`)* |
| [ ] | +8% Injury Buffer | `injury_buffer_inc` |
| [ ] | +8% Injury Buffer if triggered Life Regain recently | conditional — skip? |
| [ ] | +X% Max Energy Shield | `max_energy_shield_inc` |
| [ ] | +75 Max Energy Shield (flat) | `max_energy_shield` |
| [ ] | +5% Energy Shield Regain | `energy_shield_regain_inc` |
| [ ] | +7% Energy Shield Regain | (same as above) |
| [ ] | +4% Energy Shield Charge Speed | `energy_shield_charge_speed_inc` |
| [ ] | +5% Energy Shield Regain (Shield) | conditional — skip? |
| [ ] | +8% Barrier Absorption Rate | `barrier_absorption_rate_inc` |
| [ ] | +40% Barrier Shield | `barrier_shield_inc` |
| [ ] | +8% Cooldown Recovery Speed | `cooldown_recovery_speed_inc` |
| [ ] | +5% Life Regen / +X Max Life (all already in stat.py) | verify coverage |
| [ ] | +3% Sealed Mana Compensation | `sealed_mana_compensation_inc` |
| [ ] | +8% Sealed Mana Compensation | (same as above) |

---

## ⑤ Missing Stats — Defense Rating

| [ ] | Modifier text example | Suggested key |
|---|---|---|
| [ ] | +3% Defense | `defense_inc` *(TLI has a "Defense" rating stat?)* |
| [ ] | +9% Evasion (flat equiv) | `evasion_inc` |
| [ ] | +450 Evasion (flat) | `evasion` |
| [ ] | +4% Attack Block Chance | `attack_block_chance` |
| [ ] | +4% Spell Block Chance | `spell_block_chance` |
| [ ] | +5% Block Ratio | `block_ratio` |
| [ ] | +4% Max Fire Resistance | `max_fire_resistance` |
| [ ] | +25% Defense from Shield | `shield_defense_inc` |
| [ ] | +40% Defense gained from Chest Armor | conditional — skip? |

---

## ⑥ Missing Stats — Speed & Cooldowns

| [ ] | Modifier text example | Suggested key |
|---|---|---|
| [ ] | +3% Attack and Cast Speed | `attack_cast_speed_inc` *(combined stat)* |
| [ ] | +3% Attack Speed | `attack_speed_inc` *(already in stat.py — why unresolved?)* |
| [ ] | +3% Cast Speed | `cast_speed_inc` *(already in stat.py — why unresolved?)* |
| [ ] | +2% Movement Speed | `movement_speed_inc` *(already in stat.py — check display name match)* |
| [ ] | +9% Focus Speed | `focus_speed_inc` |
| [ ] | +3% additional Attack Speed when performing Multistrikes | conditional — skip? |
| [ ] | +6% Warcry Cooldown Recovery Speed | `warcry_cooldown_recovery_speed_inc` |
| [ ] | +8% Cooldown Recovery Speed | `cooldown_recovery_speed_inc` *(see also ①)* |
| [ ] | +2% Skill Effect Duration | `skill_effect_duration_inc` |
| [ ] | +6% Skill Area | `skill_area_inc` |

---

## ⑦ Missing Stats — Ailments & Status Effects

| [ ] | Modifier text example | Suggested key |
|---|---|---|
| [ ] | +3% chance to Ignite targets | `ignite_chance` |
| [ ] | +12% Ignite chance for Minions | `minion_ignite_chance` |
| [ ] | +3% chance to inflict Damaging Ailments | `damaging_ailment_chance` |
| [ ] | +3% chance to inflict Trauma | `trauma_chance` |
| [ ] | +6% Wilt chance | `wilt_chance` |
| [ ] | +6% Wilt Duration | `wilt_duration_inc` |
| [ ] | +8% Frostbite Effect | `frostbite_effect_inc` |
| [ ] | +2 to Max Frostbite Rating | `max_frostbite_rating` |
| [ ] | +6% Affliction Effect | `affliction_effect_inc` |
| [ ] | +6 Affliction inflicted per second | `affliction_per_second` |
| [ ] | +8% Affliction Effect (Minions) | `minion_affliction_effect_inc` |
| [ ] | +8 Affliction/second by Minions | `minion_affliction_per_second` |
| [ ] | +8% Deterioration Chance | `deterioration_chance` |
| [ ] | +8% Deterioration Damage | `deterioration_dmg_inc` |
| [ ] | -15% additional Deterioration Duration | `deterioration_duration_reduction` |
| [ ] | +9% Ailment Damage | `ailment_dmg_inc` *(see §③)* |
| [ ] | +20% Numbed Effect | `numbed_effect_inc` |
| [ ] | +20% Frostbite Effect | (see above) |
| [ ] | +5% chance to inflict Slow on hit | `slow_chance` |
| [ ] | +20% chance to Blind target on hit | `blind_chance` |
| [ ] | +80% Paralysis Effect (Two-Handed) | `paralysis_effect_inc` |
| [ ] | +50% Weaken chance (conditional) | conditional — skip? |

---

## ⑧ Missing Stats — Minion Support

| [ ] | Modifier text example | Suggested key |
|---|---|---|
| [ ] | +14% Minion Max Life | `minion_max_life_inc` |
| [ ] | +3% Minion Attack and Cast Speed | `minion_attack_cast_speed_inc` |
| [ ] | +3% Minion Life Regeneration Speed | `minion_life_regen_speed_inc` |
| [ ] | +6% Minion Multistrike chance | `minion_multistrike_chance` |
| [ ] | +4% Synthetic Troop Double Damage chance | already exists as `SYNTH_DOUBLE_DMG_CHANCE` — verify |
| [ ] | +1 to Max Summonable Synthetic Troops | `max_synth_troops` |
| [ ] | +1 Command per second | `command_per_second` |
| [ ] | +8% Armor DMG Mitigation Penetration for Minions | `minion_armor_pen` |

---

## ⑨ Missing Stats — Game-Specific Buffs / Mechanics

| [ ] | Modifier text example | Suggested key |
|---|---|---|
| [ ] | +4% Fervor Effect | `fervor_effect_inc` |
| [ ] | +20% Fervor Effect | (same) |
| [ ] | +16% Blur Effect | `blur_effect_inc` |
| [ ] | +6% Warcry Effect | `warcry_effect_inc` |
| [ ] | +8% Elixir Skill Effect | `elixir_skill_effect_inc` |
| [ ] | +20% Elixir Skill Effect | (same) |
| [ ] | +20% Spell Burst Charge Speed | `spell_burst_charge_speed_inc` |
| [ ] | +6% Reaping Duration | `reaping_duration_inc` |
| [ ] | +6% Reaping Recovery Speed | `reaping_recovery_speed_inc` |
| [ ] | +50% chance to gain Blur when Reaping | conditional — skip? |
| [ ] | +5% Tangle Duration | `tangle_duration_inc` |
| [ ] | +6% Multistrike Chance | `multistrike_chance` |
| [ ] | +10% Knockback Chance | `knockback_chance` |
| [ ] | +15% Knockback Distance | `knockback_distance_inc` |
| [ ] | +2% Crowd Control Effects | `cc_effect_inc` |
| [ ] | +3% Injury Buffer | (see §④) |
| [ ] | +4% Curse Effect | `curse_effect_inc` |
| [ ] | +8% Curse Skill Area | `curse_skill_area_inc` |
| [ ] | +16% Curse Skill Area | (same) |
| [ ] | +4% Aura Effect | `aura_effect_inc` |
| [ ] | +2% Aura Effect (micro) | (same) |
| [ ] | +20% Mark Effect | `mark_effect_inc` |
| [ ] | +30% Ill Omen Cumulative Efficiency | `ill_omen_efficiency_inc` |
| [ ] | +33% Demolisher Charge Restoration Speed | `demolisher_charge_speed_inc` |
| [ ] | +9% Spirit Magus Skill Damage | `spirit_magi_dmg_inc` *(see §③)* |
| [ ] | +24% Spirit Magus Ultimate Damage | `spirit_magi_ultimate_dmg_inc` |
| [ ] | +4% Origin of Spirit Magus effect | `spirit_magi_origin_effect_inc` |
| [ ] | +1 Spirit Magus Skill Level | `spirit_magi_skill_level` |
| [ ] | +1 Passive Skill Level | `passive_skill_level` |
| [ ] | +1 Empower Skill Level | `empower_skill_level` |
| [ ] | +3 Defensive Skill Level | `defensive_skill_level` |
| [ ] | +1 Persistent Skill Level | `persistent_skill_level` |
| [ ] | +10 / +5 to All Stats | `all_stats_flat` *(adds STR+DEX+INT equally)* |

---

## ⑩ Stats already in stat.py but NOT matching in the filter

The `node_type_filter` shows only 22 matched stats. Many stat.py entries like `attack_dmg_inc`, `spell_dmg_inc`, `dmg_inc`, etc. are **not appearing in matched stats**, meaning the filter builder's word-overlap scoring is failing to match them.

This is a filter-builder problem, not a missing stat problem. The display names in `stat_meta.py` may need tuning for better word-overlap matching.

Unmatched (but present in stat.py) — likely display name word mismatch:
- `attack_dmg_inc` — snapshot text: "+18% Attack Damage" — check display_name
- `spell_dmg_inc` — snapshot text: "+18% Spell Damage"
- `dmg_inc` — snapshot text: "+12% damage" / "+18% damage"
- `melee_dmg_inc` — snapshot text: "+18% Melee Damage"
- `area_dmg_inc` — snapshot text: "+18% Area Damage"
- `projectile_dmg_inc` — snapshot text: "+18% Projectile Damage"
- `minion_dmg_inc` — snapshot text: "+18% Minion Damage"
- `cold_dmg_inc` — snapshot text: "+18% Cold Damage"
- `fire_dmg_inc` — snapshot text: "+18% Fire Damage"
- `lightning_dmg_inc` — snapshot text: "+18% Lightning Damage"
- `erosion_dmg_inc` — snapshot text: "+18% Erosion Damage"
- `elemental_dmg_inc` — snapshot text: "+18% Elemental Damage"
- `physical_dmg_inc` — snapshot text: "+18% Physical Damage"
- `attack_speed_inc` — snapshot text: "+6% Attack Speed"
- `cast_speed_inc` — snapshot text: "+6% Cast Speed"
- `movement_speed_inc` — snapshot text: "+4% Movement Speed"
- `max_life_inc` — snapshot text: "+2% Max Life"
- `max_mana_inc` — snapshot text: "+6% Max Mana"

**Root cause:** The filter builder strips stop words including "increased" but snapshot texts use "Damage" as the core word. The `STAT_META.display_name` for `attack_dmg_inc` is probably something like "Attack Damage Increased" and the overlap scoring may be working differently than expected. Fixing the display names in `stat_meta.py` to match snapshot wording should fix these automatically when the filter is rebuilt.
