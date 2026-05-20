# Stat Audit — Modifier Verification

> Working document. Delete after review is complete, or keep for future mismatches.
>
> **Purpose:** Lists every modifier text found in the talent snapshot that either
> (a) has no matching stat in `stat.py`, or
> (b) maps to a stat whose name/semantics appear wrong for TLI.
>
> **How to fill in:**
> - **Answer** column: write `YES`, `NO`, or `RENAME` for each row
>   - `YES` → add new stat key to `stat.py` + `stat_meta.py` + `node_modifier_pool.py`
>   - `NO` → intentionally out of scope, skip
>   - `RENAME` → existing stat key needs a rename (note the new key in Notes)
>   - `SKIP` → conditional/situational, defer for now
> - **Notes** column: optional — write any reasoning, corrections, or rename targets

---

## ① Stats currently in stat.py that appear INCORRECT

| Answer | Notes | Current key | Issue |
|---|---|---|---|
|NO | Remove this stat.| `LIFE_LEECH_RATE` | TLI has no life leech. Game shows "Life Regain" and "Life Restoration". |
|RENAME | Rename to "CDR_SPEED_INC" | `COOLDOWN_REDUCTION_INC` | Game shows "Cooldown Recovery Speed" not "reduction". |

---

## ② Stats in stat.py that need VERIFICATION

| Answer | Notes | Current key | Game text seen |
|---|---|---|---|
|Y |Exists as both a flat "Regenerate 20 life per second" and a "Regenerate 0.6% Life per second". Need 2 categories for this. Name other LIFE_REGEN_PCT | `LIFE_REGEN_FLAT` | "+X Life Regeneration" — unclear if flat or rate |
|YES | | `LIFE_REGEN_INC` | "+X% Life Regeneration Speed" |
|Y | | `MANA_REGEN_INC` | "+X% Mana Regeneration Speed" |
|RENAME | rename to MAX_LIFE_FLAT| `MAX_LIFE` | "+40 Max Life", "+80 Max Life" (flat, no %) |
|RENAME | rename to MAX_MANA_FLAT | `MAX_MANA` | "+15 Max Mana", "+30 Max Mana" (flat) |
|RENAME | rename to ARMOR_FLAT| `ARMOR` | "+450 Armor" (flat) |

---

## ③ Missing Stats — Damage

### Generic Damage
| Answer | Notes | Modifier text example | Suggested key |
|---|---|---|---|
|Y | | +9% Ailment Damage | `ailment_dmg_inc` |
|Y | | +9% Damage Over Time | `dot_dmg_inc` |
|Y | | +9% damage for Channeled Skills | `channeled_dmg_inc` |
|Y | | +9% damage for Triggered Skills | `triggered_dmg_inc` |
|Y | | +9% Tangle Damage | `tangle_dmg_inc` |
|Y | | +9% Trauma Damage | `trauma_dmg_inc` |
|Y | | +9% Spirit Magus Skill Damage | `spirit_magi_dmg_inc` |
|RENAME |This stat is weird, it modifies the base damage of a weapon (ie if a weapon does an avg hit of 500, this multiplies that base value by 1.1. RENAME TO TWO_HANDED_BASE_DMG_ADDITIONAL) | +10% additional Base Damage for Two-Handed Weapons | `2h_dmg_additional` |
| RENAME|rename to shield_dmg_inc | +12% damage dealt when holding a Shield | `shield_dmg_additional` |

### Minion Damage Variants
| Answer | Notes | Modifier text example | Suggested key |
|---|---|---|---|
|Y | | +18% Minion Fire Damage | `minion_fire_dmg_inc` |
|Y | | +18% Minion Cold Damage | `minion_cold_dmg_inc` |
|Y | | +18% Minion Lightning Damage | `minion_lightning_dmg_inc` |
|Y | | +18% Minion Erosion Damage | `minion_erosion_dmg_inc` |
|Y | | +18% Physical Damage for Minions | `minion_physical_dmg_inc` |
|RENAME |This affects the max damage a minion does. So if their range is 10-20, it would take the 20 and multiply by 1.12 and make that the new max. Rename to minion_dmg_max| +12% additional Max Damage for Minions | `minion_dmg_additional` *(verify vs existing `MINION_DMG_ADDITIONAL`)* |
|N |Skip for now, will revist full conditional stats later | +8% additional Minion Damage if Synthetic Troop cast recently | conditional |

### Critical Strike (Type-specific)
| Answer | Notes | Modifier text example | Suggested key |
|---|---|---|---|
|Y | | +15% Projectile Critical Strike Damage | `projectile_crit_dmg` |
|Rename |This is an increase (obvious through the % sign). Should be projectile_crit_rating_inc | +15% Projectile Critical Strike Rating | `projectile_crit_rating_flat` |
|Y | | +15% Sentry Skill Critical Strike Damage | `sentry_crit_dmg` |
| |This is an increase (obvious through the % sign). Should be sentry_crit_rating_inc | +15% Sentry Skill Critical Strike Rating | `sentry_crit_rating_flat` |
|Y |Issues with caps sensitivity but matching otherwise should be disgarded. Caps/no caps doesn't matter. | +5% Spell Critical Strike Damage | `spell_crit_dmg` *(check vs existing `SPELL_CRIT_DMG`)* |
|N |Skip and revisit conditionals later | +14% Critical Strike Damage against enemies affected by Ailments | conditional |

---

## ④ Missing Stats — Life / Defense

| Answer | Notes | Modifier text example | Suggested key |
|---|---|---|---|
|Y | | +5% Life Regain | `life_regain_inc` *(replaces `LIFE_LEECH_RATE`)* |
|Rename |rename to life_regain_interval_additional | -15% additional Life Regain Interval | `life_regain_interval_reduction` |
|Y |Make life regen_inc refer to "regenerate 0.6% Life" and life_regen_speed_inc refer to this stat | +4% Life Regeneration Speed | `life_regen_speed_inc` *(or rename `LIFE_REGEN_INC`)* |
|Y | | +8% Injury Buffer | `injury_buffer_inc` |
|N |Revisit conditionals | +8% Injury Buffer if triggered Life Regain recently | conditional |
|Y | | +X% Max Energy Shield | `max_energy_shield_inc` |
|Rename |Rename to max _energy_shield_flat | +75 Max Energy Shield (flat) | `max_energy_shield` |
|Y | | +5% Energy Shield Regain | `energy_shield_regain_inc` |
|Y | | +4% Energy Shield Charge Speed | `energy_shield_charge_speed_inc` |
|Y | | +8% Barrier Absorption Rate | `barrier_absorption_rate_inc` |
|Y | | +40% Barrier Shield | `barrier_shield_inc` |
|RENAME |stat should be called cdr_speed_inc | +8% Cooldown Recovery Speed | `cooldown_recovery_speed_inc` *(see also ①)* |
|Y | | +3% Sealed Mana Compensation | `sealed_mana_compensation_inc` |

---

## ⑤ Missing Stats — Defense Rating

| Answer | Notes | Modifier text example | Suggested key |
|---|---|---|---|
|Y |The torchlight infinite defense stat covers armor, evasion, and energy shield and functions as an additive pool with the other sources. | +3% Defense | `defense_inc` *(TLI combined defense stat?)* |
|Y | | +9% Evasion | `evasion_inc` |
|Rename |rename to evasion_flat | +450 Evasion (flat) | `evasion` |
|rename |rename to attack_block_chance_inc | +4% Attack Block Chance | `attack_block_chance` |
|rename |rename to spell_block_chance_inc | +4% Spell Block Chance | `spell_block_chance` |
|rename |rename to block_ratio_inc | +5% Block Ratio | `block_ratio` |
|rename | | +4% Max Fire Resistance | `max_fire_resistance` |
|Y | | +25% Defense from Shield | `shield_defense_inc` |

---

## ⑥ Missing Stats — Speed & Cooldowns

| Answer | Notes | Modifier text example | Suggested key |
|---|---|---|---|
|Y |This is a combined stat and should be split into 3% attack_speed_inc and 3% cast_speed_inc | +3% Attack and Cast Speed | `attack_cast_speed_inc` *(combined stat)* |
|Y |Mismatch due to caps | +3% Attack Speed | `attack_speed_inc` *(already in stat.py — display name mismatch?)* |
|Y |Mismatch due to caps | +3% Cast Speed | `cast_speed_inc` *(already in stat.py — display name mismatch?)* |
|Y |Mismatch due to caps | +2% Movement Speed | `movement_speed_inc` *(already in stat.py — display name mismatch?)* |
|Y | | +9% Focus Speed | `focus_speed_inc` |
|Rename |rename to warcry_cdr_speed_inc | +6% Warcry Cooldown Recovery Speed | `warcry_cooldown_recovery_speed_inc` |
|Y | | +2% Skill Effect Duration | `skill_effect_duration_inc` |
|Y | | +6% Skill Area | `skill_area_inc` |

---

## ⑦ Missing Stats — Ailments & Status Effects

| Answer | Notes | Modifier text example | Suggested key |
|---|---|---|---|
|Y | | +3% chance to Ignite targets | `ignite_chance` |
|Y | | +12% Ignite chance for Minions | `minion_ignite_chance` |
|Y | | +3% chance to inflict Damaging Ailments | `damaging_ailment_chance` |
|Y | | +3% chance to inflict Trauma | `trauma_chance` |
|Y | | +6% Wilt chance | `wilt_chance` |
|Y | | +6% Wilt Duration | `wilt_duration_inc` |
|Y | | +8% Frostbite Effect | `frostbite_effect_inc` |
|Rename |max_frostbite_rating_flat | +2 to Max Frostbite Rating | `max_frostbite_rating` |
|Y | | +6% Affliction Effect | `affliction_effect_inc` |
|Rename |affliction_per_second_flat | +6 Affliction inflicted per second | `affliction_per_second` |
|Y | | +8% Minion Affliction Effect | `minion_affliction_effect_inc` |
|Rename |add _flat at the end | +8 Affliction/second by Minions | `minion_affliction_per_second` |
|Y | | +8% Deterioration Chance | `deterioration_chance` |
|Y | | +8% Deterioration Damage | `deterioration_dmg_inc` |
|Rename |rename to deterioration_duration_additional | -15% additional Deterioration Duration | `deterioration_duration_reduction` |
|Y | | +20% Numbed Effect | `numbed_effect_inc` |
|Y | | +5% chance to inflict Slow on hit | `slow_chance` |
|Y | | +20% chance to Blind target on hit | `blind_chance` |
|Rename |Rename to 'paralysis_effect_2h_inc | +80% Paralysis Effect (Two-Handed) | `paralysis_effect_2h_inc` |

---

## ⑧ Missing Stats — Minion Support

| Answer | Notes | Modifier text example | Suggested key |
|---|---|---|---|
|Y | | +14% Minion Max Life | `minion_max_life_inc` |
|Rename |This mod needs to be split into its respective categories| +3% Minion Attack and Cast Speed | `minion_attack_cast_speed_inc` |
|Y | | +3% Minion Life Regeneration Speed | `minion_life_regen_speed_inc` |
|Y | | +6% Minion Multistrike chance | `minion_multistrike_chance` |
|Y |Caps matching issue, its the same mod as synth_double_dmg_chance | +4% Synthetic Troop Double Damage chance | *(verify vs existing `SYNTH_DOUBLE_DMG_CHANCE`)* |
|Rename |Rename to max_synth_troops_flat | +1 to Max Summonable Synthetic Troops | `max_synth_troops` |
|Rename |Rename to command_per_second_flat | +1 Command per second | `command_per_second` |
|Y | | +8% Armor DMG Mitigation Penetration for Minions | `minion_armor_pen` |

---

## ⑨ Missing Stats — Game-Specific Buffs / Mechanics

| Answer | Notes | Modifier text example | Suggested key |
|---|---|---|---|
|Y | | +4% Fervor Effect | `fervor_effect_inc` |
|Y | | +16% Blur Effect | `blur_effect_inc` |
|Y | | +6% Warcry Effect | `warcry_effect_inc` |
|Rename |remove the skill as its a weird addition not present in other types of increased effect. Rename to elixir_effect_inc | +8% Elixir Skill Effect | `elixir_skill_effect_inc` |
|Y | | +20% Spell Burst Charge Speed | `spell_burst_charge_speed_inc` |
|Y | | +6% Reaping Duration | `reaping_duration_inc` |
|Y | | +6% Reaping Recovery Speed | `reaping_recovery_speed_inc` |
|Y | | +5% Tangle Duration | `tangle_duration_inc` |
|Y | | +6% Multistrike Chance | `multistrike_chance` |
|Y | | +10% Knockback Chance | `knockback_chance` |
|Y | | +15% Knockback Distance | `knockback_distance_inc` |
|Y | | +2% Crowd Control Effects | `cc_effect_inc` |
|Y | | +4% Curse Effect | `curse_effect_inc` |
|Y | | +8% Curse Skill Area | `curse_skill_area_inc` |
|Y | | +4% Aura Effect | `aura_effect_inc` |
|Y | | +20% Mark Effect | `mark_effect_inc` |
|Y | | +30% Ill Omen Cumulative Efficiency | `ill_omen_efficiency_inc` |
|Y | | +33% Demolisher Charge Restoration Speed | `demolisher_charge_speed_inc` |
|Y | | +24% Spirit Magus Ultimate Damage | `spirit_magi_ultimate_dmg_inc` |
|Y | | +4% Origin of Spirit Magus effect | `spirit_magi_origin_effect_inc` |
|Y | | +1 Spirit Magus Skill Level | `spirit_magi_skill_level` |
|Y | | +1 Passive Skill Level | `passive_skill_level` |
|Y | | +1 Empower Skill Level | `empower_skill_level` |
|Y | | +3 Defensive Skill Level | `defensive_skill_level` |
|Y | | +1 Persistent Skill Level | `persistent_skill_level` |
|Y |Correct, adds to str, dex, int equally (10 to each) | +10 to All Stats | `all_stats_flat` *(adds STR+DEX+INT equally)* |

---

## ⑩ Stats already in stat.py but NOT matching in the filter

These are not missing stats — they exist but the filter builder's word-overlap scoring fails to match them because the `display_name` in `stat_meta.py` doesn't align with the snapshot wording. **Fix: tune the display names in `stat_meta.py` to match the snapshot text, then rebuild the filter.**

| Answer | Notes | stat.py key | Snapshot text | Likely display name fix |
|---|---|---|---|---|
|Y | | `attack_dmg_inc` | "+18% Attack Damage" | display_name should be "Attack Damage" |
|Y | | `spell_dmg_inc` | "+18% Spell Damage" | "Spell Damage" |
|Y | | `dmg_inc` | "+12% damage" / "+18% damage" | "Damage" |
|Y | | `melee_dmg_inc` | "+18% Melee Damage" | "Melee Damage" |
|Y | | `area_dmg_inc` | "+18% Area Damage" | "Area Damage" |
|Y | | `projectile_dmg_inc` | "+18% Projectile Damage" | "Projectile Damage" |
|Y | | `minion_dmg_inc` | "+18% Minion Damage" | "Minion Damage" |
|Y | | `cold_dmg_inc` | "+18% Cold Damage" | "Cold Damage" |
|Y | | `fire_dmg_inc` | "+18% Fire Damage" | "Fire Damage" |
|Y | | `lightning_dmg_inc` | "+18% Lightning Damage" | "Lightning Damage" |
|Y | | `erosion_dmg_inc` | "+18% Erosion Damage" | "Erosion Damage" |
|Y | | `elemental_dmg_inc` | "+18% Elemental Damage" | "Elemental Damage" |
|Y | | `physical_dmg_inc` | "+18% Physical Damage" | "Physical Damage" |
|Y | | `attack_speed_inc` | "+6% Attack Speed" | "Attack Speed" |
|Y | | `cast_speed_inc` | "+6% Cast Speed" | "Cast Speed" |
|Y | | `movement_speed_inc` | "+4% Movement Speed" | "Movement Speed" |
|Y | | `max_life_inc` | "+2% Max Life" | "Max Life" |
|Y | | `max_mana_inc` | "+6% Max Mana" | "Max Mana" |

---

## ⑪ Missing Stats — Legendary Gear Affixes (not in talent nodes)

> Stats below appear in `_legendary_gear.json` and are not yet in `stat.py`.
> Stats already listed in sections ③–⑨ above are noted as "see above" and not repeated.
> Unique/conditional legendary effects (trigger skills, replace skill, unique buffs) are excluded — those are not generic trackable stats.
>
> Gear introduces two extra concepts:
> - **Gear-base stats** (e.g. `gear_physical_dmg_inc`) — values baked into the gear item itself, separate from the general pool
> - **Damage taken** reductions — gear can grant mitigation to the player's own incoming damage

### Damage (New to gear, not in talent audit)
| Answer | Notes | Modifier text example | Suggested key |
|---|---|---|---|
|Y | | +(40–60)% Ignite Damage | `ignite_dmg_inc` |
|Y | | +(50–150)% Wilt Damage | `wilt_dmg_inc` |
|Rename |Needs to be split into two categories for min_max flat damages | Adds (X–Y) Base Ignite Damage (flat) | `ignite_dmg_flat` |
|Rename |Needs to be split into two categories for min_max flat damages | Adds (X–Y) Base Wilt Damage (flat) | `wilt_dmg_flat` |
|Rename |Needs to be split into two categories for min_max flat damages | Adds (X–Y) Base Ailment Damage (flat) | `ailment_dmg_flat` |
|Rename |Needs to split into min/max versions of phys for attacks and spells separately | Adds (X–Y) Physical Damage to Attacks and Spells (flat) | `physical_atk_spell_dmg_flat_min` / `_max` |
|Rename |needs to split into min/max versions of all 3 elements and their respective attack/spell type | Adds (X–Y) Fire/Cold/Lightning Damage to Attacks and Spells | *(per-element flat — see existing `fire_attack_dmg_flat_min` etc.)* |
|N |Skip conditional for now | +(60–70)% additional Beam Skill Damage while standing still | conditional — skip? |
|Rename |This is the combo finisher additional multiplier. Rename to combo_finisher_additional | +(45–55)% Combo Finisher Amplification | `combo_finisher_amplification_inc` |
|Renanme |This is the multistrike additional multiplier but it works in a specific way with how multistrikes work. More context will be given later, rename to multistrike_dmg_additional | Multistrikes deal (40–60)% increasing damage | `multistrike_dmg_scaling_inc` |
|Rename |Barrage_dmg_additional. This stat needs a note to revisit and verify in game later | Barrage Skills +(50–60)% damage increase per wave | `barrage_dmg_per_wave_inc` |

### Gear-Base Stats (gear item values, distinct from general pool)
| Answer | Notes | Modifier text example | Suggested key |
|---|---|---|---|
|Y | | +(30–40)% Gear Physical Damage | `gear_physical_dmg_inc` |
|Y | | +(50–60)% gear Energy Shield | `gear_energy_shield_inc` |
|Rename |Rename gear_energy_shield_flat | +(130–180) gear Energy Shield (flat) | `gear_energy_shield` |
|Rename |Same stat as above | +272 gear Energy Shield (flat) | *(same as above)* |
|Rename |rename max_energy_shield_flat. Mentioned in talents sections | +35 Max Energy Shield (flat, non-gear) | `max_energy_shield` *(see also §④)* |
|Y |see talents section. Same stat, should match | +25% Max Energy Shield | `max_energy_shield_inc` *(see also §④)* |

### Life / Mana / Energy Shield (gear variants)
| Answer | Notes | Modifier text example | Suggested key |
|---|---|---|---|
|Y |see talents | +(12–15)% Life Regain | `life_regain_inc` *(see §④)* |
|N |skip conditionals for now | +(15–20)% Life Regain and Shield Regain for Combo Finishers | conditional — skip? |
|Y |see talents | +(8–16)% Energy Shield Regain | `energy_shield_regain_inc` *(see §④)* |
|Y |this is life regen flat | Regenerates (15–20) Life per second | `life_regen_flat` *(verify vs existing)* |
|Y |this is what mana regen flat looks like | Regenerates (200–240) Mana per second | `mana_regen_flat` *(verify vs existing)* |
|Rename |Rename to mana_regen_pct | Regenerates (2–3)% Mana per second | `mana_regen_pct_inc` *(different from flat)* |
|Rename |rename to mana_before_life_inc | (5–8)% of damage is taken from Mana before Life | `mana_before_life_pct` |
|N |Skip unique effects. These will become flags eventually that are enabled/disabled based on items equipped | Double Life Regain | unique effect — skip |
|Y |See talents | +(8–12)% Injury Buffer | `injury_buffer_inc` *(see §④)* |
|Rename |rename to life_on_skill_use_flat | Restores (16–20) Life when using skills. Interval: 0.2 s | `life_on_skill_use` |
|Y| | Restores 5% of Life on defeat | `life_on_defeat_pct` |

### Defense / Mitigation (gear variants)
| Answer | Notes | Modifier text example | Suggested key |
|---|---|---|---|
|Y |see talents where defense is explained further | +(21–30)% Defense | `defense_inc` *(see §⑤)* |
| |See above | +40% Defense | *(same)* |
|Y |See talents | +20% additional Barrier Shield | `barrier_shield_inc` *(see §④)* |
| |See above | +50% Barrier Shield | *(same)* |
|Y |see talents | +(8–12)% Reaping Duration | `reaping_duration_inc` *(see §⑨)* |
|Y |see talents | +(94–100)% Reaping Recovery Speed | `reaping_recovery_speed_inc` *(see §⑨)* |
|Rename |Rename to slow_effect_received_inc. This is an increased/reduced modifier.| (-70–50)% Slow Effect received | `slow_effect_received_reduction` |
|Y | | +(8–10)% Intimidating Effect | `intimidating_effect_inc` |

### Damage Taken Modifiers (player mitigation from gear)
| Answer | Notes | Modifier text example | Suggested key |
|---|---|---|---|
|Rename |dmg_taken_additional. This goes positive and negative | -8% additional damage taken | `dmg_taken_reduction` |
|Rename |physical_dmg_taken_additional | -4% additional Physical Damage taken | `physical_dmg_taken_reduction` *(exists in talent snapshot too)* |
| Rename|elemental_dmg_taken_additional | -4% additional Elemental Damage taken | `elemental_dmg_taken_reduction` |
|Rename |trauma_dmg_taken_inc | -40% Trauma Damage (taken) | `trauma_dmg_taken_reduction` |
|Rename |dot_dmg_taken_additional | -40% additional Damage Over Time taken | `dot_dmg_taken_reduction` |
|N |conditional skip | -10% additional damage taken when an Elite is Nearby | conditional — skip? |
|N|Conditional, skip for now. | -12% additional damage dealt by Blinded enemies | `blind_dmg_reduction` |

### Skill Mechanics (gear variants)
| Answer | Notes | Modifier text example | Suggested key |
|---|---|---|---|
|Y |see talents | +(10–20)% Skill Area | `skill_area_inc` *(see §⑥)* |
|Y |see talents | +(5–10)% Skill Effect Duration | `skill_effect_duration_inc` *(see §⑥)* |
|Y | | +(30–40) Skill Cost (negative = reduction) | `skill_cost_flat` |
|Y | | -10 Skill Cost | `skill_cost_flat` *(negative value)* |
|Y | | +(400–500)% Skill Cost | `skill_cost_inc` |
|Y |see talents | +(20–30)% Focus Speed | `focus_speed_inc` *(see §⑥)* |
|Y |see talents | +(20–30)% Spell Burst Charge Speed | `spell_burst_charge_speed_inc` *(see §⑨)* |
|Y |see talents | +(24–30)% Warcry Effect | `warcry_effect_inc` *(see §⑨)* |
|Rename |see talents for rename info | +(10–15)% Elixir Skill Effect | `elixir_skill_effect_inc` *(see §⑨)* |
|Y |see talents | +(40–60)% Affliction Effect | `affliction_effect_inc` *(see §⑦)* |
|Y |see talents | +(20–30)% Ill Omen Cumulative Efficiency | `ill_omen_efficiency_inc` *(see §⑨)* |
|Y | | +(12–20)% Sealed Mana Compensation | `sealed_mana_compensation_inc` *(see §④)* |
|Y | | Restoration Skills: +(30–40)% Restoration Effect | `restoration_effect_inc` |
|Rename |max_charges_flat | +(1–2) Max Charges | `max_charges` |
|Rename |max_spell_burst_flat | +1 Max Spell Burst | `max_spell_burst` |
|Rename |projectile_quantity_flat | Projectile Quantity +(1–2) | `projectile_quantity` |
|Rename |horizontal_projectile_penetration_flat | +2 Horizontal Projectile Penetration(s) | `horizontal_projectile_penetration` |
|Rename |jumps_flat | +1 Jumps | `extra_jumps` |
|Rename |max_tangle_quantity_flat | +2 Max Tangle Quantity | `max_tangle_quantity` |

### Minion / Summoner (gear variants)
| Answer | Notes | Modifier text example | Suggested key |
|---|---|---|---|
|Y | | +(20–30)% Minion Duration | `minion_duration_inc` |
|Y |physique is model size. Not a really important stat for calculations but may affect aoe? Needs testing | +(20–30)% Physique for Minions | `minion_physique_inc` *(unclear what Physique is in TLI)* |
|Rename |max_sentry_quantity_flat | Max Sentry Quantity +1 | `max_sentry_quantity` |
|Y | | +(8–16)% Life Regain for Minions | `minion_life_regain_inc` |
|Y |see talents | + (8–12) Command per second | `command_per_second` *(see §⑧)* |
|Rename |max_command_flat | -20 Max Command | `max_command` *(flat — does this exist?)* |

### Conversion / Reflection (gear-specific mechanics)
| Answer | Notes | Modifier text example | Suggested key |
|---|---|---|---|
|Y |same as the already implemented stat | Adds (8–10)% of Physical Damage as Fire Damage | `physical_as_fire` *(verify vs existing `PHYSICAL_AS_FIRE`)* |
|Y |same as the already implemented stat | Adds (8–10)% of Physical Damage as Lightning Damage | `physical_as_lightning` *(verify vs existing)* |
|Y |will give 40% as each element. Can be named elemental | Adds 40% of Physical Damage as Fire, Cold, and Lightning Damage | `physical_as_elemental` |
|Rename |Should have a cold_taken_as_fire_inc and lightning_taken_as_fire_inc, etc and variants for all elements. Should split into both stats and feed same value for stats like this. | Converts (50–70)% of Cold and Lightning Damage taken to Fire | `cold_lightning_taken_as_fire` |
|Y | | +(150–300) Physical Damage Reflection | `physical_dmg_reflection` |
|Y |Split up all dmg type reflections and mods will feed into relevant types | +(60–80) Fire/Lightning Damage Reflection | `fire_dmg_reflection` / `lightning_dmg_reflection` |
|Y | | +(15–20)% All Stats | `all_stats_inc` |
|Y |see talents | +(15–20) to All Stats (flat) | `all_stats_flat` *(see §⑨)* |
