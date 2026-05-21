# Stat Audit — Unmatched Modifier Texts

> Generated 2026-05-20 from last filter rebuild.
> These modifier texts appear in the talent snapshot but have no matching stat in `stat.py`.
>
> **How to fill in:**
> - **Answer** column: `YES`, `NO`, or `SKIP`
>   - `YES` → add new stat key to `stat.py` + `stat_meta.py`
>   - `NO` → intentionally out of scope, skip
>   - `SKIP` → conditional/situational, defer for now
> - **Notes** column: write the suggested stat key or any reasoning
>   - `%` texts → key usually ends in `_inc`
>   - Flat texts → key usually ends in `_flat`
>
> Total: 171 unique unmatched texts (100 reviewable, 71 conditional)

---

## ① Minion

### % Modifier Texts

| Answer | Notes | Modifier text | Suggested key |
|---|---|---|---|
| SKIP | | +1% Minion Attack and Cast Speed for every 2 Command owned | |
| SKIP | | +1% Minion Fire Damage per 12 Strength | |
| | | +12% Ignite chance for Minions | `minion_ignite_chance` |
| | | +12% Minion Skill Area | `minion_skill_area_inc` |
| | | +12% chance for Minions to inflict Damaging Ailments | `minion_damaging_ailment_chance` |
| | | +12% chance for Minions to inflict Trauma | `minion_trauma_chance` |
| | | +24% chance for Minions to inflict Damaging Ailments | `minion_damaging_ailment_chance` |
| | | +4% chance for Synthetic Troop Minions to deal Double Damage | `synth_double_dmg_chance` |
| | | +6% Ignite chance for Minions | `minion_ignite_chance` |
| | | +6% Minion Skill Area | `minion_skill_area_inc` |
| | | +6% chance for Minions to inflict Damaging Ailments | `minion_damaging_ailment_chance` |
| | | +6% chance for Minions to inflict Trauma | `minion_trauma_chance` |
| | | -40% additional damage taken by Synthetic Troop Minions | `synth_troop_dmg_taken_additional` |

---

## ② Spirit Magus

### % Modifier Texts

| Answer | Notes | Modifier text | Suggested key |
|---|---|---|---|
| | | +12% Spirit Magus Ultimate Damage and Ailment Damage dealt by Ultimate. | `spirit_magi_ultimate_dmg_inc` |
| | | +2% chance for Spirit Magi to use an Enhanced Skill | `spirit_magi_enhanced_skill_chance` |
| | | +24% Spirit Magus Ultimate Damage and Ailment Damage dealt by Ultimate. | `spirit_magi_ultimate_dmg_inc` |
| | | +27% Spirit Magus Ultimate Damage and Ailment Damage dealt by Ultimate. | `spirit_magi_ultimate_dmg_inc` |
| | | +4% chance for Spirit Magi to use an Enhanced Skill | `spirit_magi_enhanced_skill_chance` |
| | | +6% chance for Spirit Magi to use an Enhanced Skill | `spirit_magi_enhanced_skill_chance` |
| | | +9% Spirit Magus Ultimate Cooldown Recovery Speed | `spirit_magi_cdr_speed_inc` |
| | | -80% additional damage taken by Spirit Magi | `spirit_magi_dmg_taken_additional` |

### Flat Modifier Texts

| Answer | Notes | Modifier text | Suggested key |
|---|---|---|---|
| | | +1 to Max Spirit Magi In Map | `max_spirit_magi_flat` |

---

## ③ Ailments

### % Modifier Texts

| Answer | Notes | Modifier text | Suggested key |
|---|---|---|---|
| SKIP | | +12% additional Trauma Damage dealt by Critical Strikes | |
| | | +12% chance to avoid Elemental Ailments | `elemental_ailment_avoid_chance` |
| | | +16% Trauma Reaping Duration | `trauma_reaping_duration_inc` |
| SKIP | | +2% Movement Speed for each activated Tangle | |
| | | +20% chance to avoid Elemental Ailments | `elemental_ailment_avoid_chance` |
| | | +3% chance to Ignite targets | `ignite_chance` |
| | | +3% chance to avoid Elemental Ailments | `elemental_ailment_avoid_chance` |
| | | +3% chance to inflict Damaging Ailments | `damaging_ailment_chance` |
| | | +3% chance to inflict Trauma | `trauma_chance` |
| | | +30% chance to inflict Damaging Ailments | `damaging_ailment_chance` |
| | | +6% chance to Ignite targets | `ignite_chance` |
| | | +6% chance to inflict Damaging Ailments | `damaging_ailment_chance` |
| | | +6% chance to inflict Trauma | `trauma_chance` |
| | | +7% chance to avoid Elemental Ailments | `elemental_ailment_avoid_chance` |
| | | +8% additional Deterioration Damage | `deterioration_dmg_inc` |
| | | +8% chance to Ignite targets | `ignite_chance` |
| | | +8% chance to inflict Trauma | `trauma_chance` |
| | | -4% to the Max Life and Energy Shield thresholds for inflicting Numbed | `numbed_threshold_inc` |

---

## ④ Critical Strike

### % Modifier Texts

| Answer | Notes | Modifier text | Suggested key |
|---|---|---|---|
| SKIP | | +25% chance to Mark the enemy on Critical Strike | |
| SKIP | | +5% Spell Critical Strike Damage per stack of Focus Blessing owned (Max Divinity | |

---

## ⑤ Projectile

### % Modifier Texts

| Answer | Notes | Modifier text | Suggested key |
|---|---|---|---|
| | | +9% Sentry Projectile Speed | `sentry_projectile_speed_inc` |

### Flat Modifier Texts

| Answer | Notes | Modifier text | Suggested key |
|---|---|---|---|
| | | +1 to Parabolic Projectile Splits quantity | `parabolic_projectile_splits_flat` |

---

## ⑥ Sentry

### % Modifier Texts

| Answer | Notes | Modifier text | Suggested key |
|---|---|---|---|
| | | +10% Sentry Duration | `sentry_duration_inc` |
| | | +18% Sentry Skill Area | `sentry_skill_area_inc` |
| | | +20% Sentry Duration | `sentry_duration_inc` |
| | | +7% Sentry Skill Area | `sentry_skill_area_inc` |
| | | -25% additional Sentry Start Time | `sentry_start_time_additional` |
| | | -8% additional Sentry Start Time | `sentry_start_time_additional` |

### Flat Modifier Texts

| Answer | Notes | Modifier text | Suggested key |
|---|---|---|---|
| | | +1 Sentry quantity that can be deployed at a time | `max_sentry_quantity_flat` |

---

## ⑦ Damage

### % Modifier Texts

| Answer | Notes | Modifier text | Suggested key |
|---|---|---|---|
| SKIP | | +1% Fire Damage per 12 Strength | |
| SKIP | | +10% additional damage for 4s after using Mobility Skills | |
| | | +12% additional Max Damage | `dmg_max_additional` |
| SKIP | | +15% additional damage taken by enemies in Proximity | |
| | | +18% damage for Channeled Skills | `channeled_dmg_inc` |
| | | +2% additional Max Damage | `dmg_max_additional` |
| SKIP | | +20% Spell Damage at Low Mana | |
| SKIP | | +20% additional Evasion on Spell Damage | |
| SKIP | | +25% damage dealt to Nearby enemies | |
| SKIP | | +25% damage to Distant enemies | |
| | | +3% chance to avoid damage | `dmg_avoid_chance` |
| SKIP | | +5% damage and +1% Movement Speed for 4 s on defeat. Stacks up to 8 time(s) (Max | |
| SKIP | | +6% damage for every +1 additional Max Channeled Stack(s) | |
| | | +9% damage for Channeled Skills | `channeled_dmg_inc` |
| | | +9% damage for Triggered Skills | `triggered_dmg_inc` |

---

## ⑧ Life

### % Modifier Texts

| Answer | Notes | Modifier text | Suggested key |
|---|---|---|---|
| SKIP | | +2% Life Regeneration Speed per stack of Tenacity Blessing owned | |
| SKIP | | +2% additional Attack Speed for each time you have Regained in the last 8s. Stacks up | |
| SKIP | | +2% additional Cast Speed for each time you have Regained in the last 8s. Stacks up to | |
| | | -8% additional Energy Shield Regain Interval | `energy_shield_regain_interval_additional` |

### Flat Modifier Texts

| Answer | Notes | Modifier text | Suggested key |
|---|---|---|---|
| SKIP | | +1 Max Life per 5 Strength | |

---

## ⑨ Defense

### % Modifier Texts

| Answer | Notes | Modifier text | Suggested key |
|---|---|---|---|
| SKIP | | +1% Armor for every 24 Strength | |
| SKIP | | +1% Evasion per 24 Dexterity | |
| | | +15% Energy Shield gained from Shield | `shield_energy_shield_inc` |
| | | +40% Defense gained from Chest Armor | `chest_defense_inc` |
| SKIP | | +6% Armor per stack of Tenacity Blessing owned | |
| SKIP | | +6% Evasion per stack of Agility Blessing owned | |
| | | -15% additional Energy Shield Charge Interval | `energy_shield_charge_interval_additional` |

### Flat Modifier Texts

| Answer | Notes | Modifier text | Suggested key |
|---|---|---|---|
| SKIP | | +2 Max Energy Shield per 5 Intelligence | |

---

## ⑩ Mana & Energy

### Flat Modifier Texts

| Answer | Notes | Modifier text | Suggested key |
|---|---|---|---|
| SKIP | | +1 Mana per 6 Intelligence | |
| | | -4 Attack Skill Cost | `attack_skill_cost_flat` |

---

## ⑪ Speed & Cooldown

### % Modifier Texts

| Answer | Notes | Modifier text | Suggested key |
|---|---|---|---|
| SKIP | | +1% Attack and Cast Speed per 40 Dexterity | |
| SKIP | | +1% Movement Speed per 10 Fervor Rating | |
| | | +3% Attack and Cast Speed for Channeled Skills | `channeled_attack_cast_speed_inc` |

---

## ⑫ Buffs & Mechanics

### % Modifier Texts

| Answer | Notes | Modifier text | Suggested key |
|---|---|---|---|
| SKIP | | +100% chance to gain Blur on defeat | |
| | | +32% chance to Multistrike | `multistrike_chance` |
| | | +6% chance to Multistrike | `multistrike_chance` |

### Flat Modifier Texts

| Answer | Notes | Modifier text | Suggested key |
|---|---|---|---|
| | | +4 to the minimum number of enemies affected by Warcry | `warcry_min_targets_flat` |

---

## ⑬ Utility

### Flat Modifier Texts

| Answer | Notes | Modifier text | Suggested key |
|---|---|---|---|
| | | +1 Focus Skill Level | `focus_skill_level` |

---

## ⑭ Other

### % Modifier Texts

| Answer | Notes | Modifier text | Suggested key |
|---|---|---|---|
| | | +10% Agility Blessing Duration | `agility_blessing_duration_inc` |
| | | +10% Focus Blessing Duration | `focus_blessing_duration_inc` |
| | | +10% Tenacity Blessing Duration | `tenacity_blessing_duration_inc` |
| | | +40% additional Beam Length | `beam_length_additional` |

### Flat Modifier Texts

| Answer | Notes | Modifier text | Suggested key |
|---|---|---|---|
| | | +1 to All Skills' Levels | `all_skill_level` |
| | | +1 to Max Agility Blessing Stacks | `max_agility_blessing_stacks_flat` |
| | | +1 to Max Channeled Stacks | `max_channeled_stacks_flat` |
| | | +1 to Max Focus Blessing Stacks | `max_focus_blessing_stacks_flat` |
| | | +1 to Max Tenacity Blessing Stacks | `max_tenacity_blessing_stacks_flat` |
| | | +10 to All Stats | `all_stats_flat` |
| | | +5 to All Stats | `all_stats_flat` |

---

## ⑮ Conditionals (defer)

> These texts contain conditional language (when/if/while/recently/against).
> Answer `SKIP` for all unless you want to handle them now.

| Answer | Notes | Modifier text |
|---|---|---|
| SKIP | | +10% Attack Damage while Tenacity Blessing is active |
| SKIP | | +10% Movement Speed while Blur is active |
| SKIP | | +10% Spell Damage when having Focus Blessing |
| SKIP | | +10% additional Sentry Damage if Sentry Skill is not used in the last 1 s |
| SKIP | | +10% additional damage against Frozen enemies |
| SKIP | | +10% additional damage when having both Sealed Mana and Life |
| SKIP | | +10% damage while Focus Blessing is active |
| SKIP | | +100% chance to gain a stack of Focus Blessing upon inflicting damage to a Frostbitten |
| SKIP | | +12% Attack Damage when holding a Two-Handed Weapon |
| SKIP | | +12% Attack and Cast Speed when channeled stacks have not reached cap |
| SKIP | | +12% Minion Damage if a Synthetic Troop Skill has been cast recently |
| SKIP | | +12% Spell Damage when holding a Shield |
| SKIP | | +12% damage dealt when holding a Shield |
| SKIP | | +12% damage if you have Regained in the last 8s |
| SKIP | | +12% damage if you have defeated an enemy recently |
| SKIP | | +12% damage if you have taken damage recently |
| SKIP | | +12% damage while an Elixir Skill is active |
| SKIP | | +14% Critical Strike Damage against enemies affected by Ailments |
| SKIP | | +14% Minion Critical Strike Damage against enemies affected by Ailments |
| SKIP | | +16% damage against Cursed enemies |
| SKIP | | +18% Attack Damage when holding a One-Handed Weapon |
| SKIP | | +18% Attack Damage while Dual Wielding |
| SKIP | | +2% Fire Penetration against Ignited enemies |
| SKIP | | +2% Minion Fire Penetration against Ignited enemies |
| SKIP | | +20% Attack and Cast Speed when at Full Mana |
| SKIP | | +20% Sentry Damage when moving |
| SKIP | | +20% chance to Blind the target on hit |
| SKIP | | +20% chance to gain Blur when inflicting crowd control effects |
| SKIP | | +24% Attack Damage if you have Regained in the last 8s |
| SKIP | | +24% Spell Damage if you have Regained in the last 8s |
| SKIP | | +24% Spell Damage when holding a Shield |
| SKIP | | +25% Critical Strike Damage Mitigation against Blinded enemies |
| SKIP | | +25% additional damage against Low Life enemies |
| SKIP | | +25% chance to gain 1 stacks of Tenacity Blessing when taking damage. Interval: 1 s |
| SKIP | | +3% Attack Speed and Cast Speed when having Agility Blessing |
| SKIP | | +3% additional Attack Speed when performing Multistrikes |
| SKIP | | +35% Armor if you have Blocked recently |
| SKIP | | +4% Attack Block Chance when holding a Shield |
| SKIP | | +4% Attack and Cast Speed when holding a Shield |
| SKIP | | +4% Cast Speed when Focus Blessing is active |
| SKIP | | +4% Defense when holding a Shield |
| SKIP | | +40% Attack Critical Strike Rating when holding a Two-Handed Weapon |
| SKIP | | +40% Skill Area if Main Skill is not used in the last 2 s |
| SKIP | | +40% damage if you have Blocked recently |
| SKIP | | +5% Block Ratio when holding a Shield |
| SKIP | | +5% additional Attack Damage for each unique type of weapon equipped while Dual |
| SKIP | | +5% chance to inflict Slow on hit |
| SKIP | | +50% chance to Weaken nearby enemies when triggering any skill (Max Divinity Effect: |
| SKIP | | +50% chance to gain Blur when Reaping |
| SKIP | | +50% damage against Low Life enemies |
| SKIP | | +6% Attack Speed while Dual Wielding |
| SKIP | | +6% additional Attack Speed if you have dealt a Critical Strike recently (Max Divinity |
| SKIP | | +6% additional Attack Speed while Dual Wielding |
| SKIP | | +6% additional Cast Speed if you have dealt a Critical Strike recently (Max Divinity |
| SKIP | | +60% Projectile Damage against enemies in proximity |
| SKIP | | +60% damage while standing still |
| SKIP | | +7% Evasion while Agility Blessing is active |
| SKIP | | +8% Injury Buffer if you have triggered Life Regain in the last 8s |
| SKIP | | +8% additional Attack Damage if you have used a Warcry Skill in the last 8s |
| SKIP | | +8% additional Attack Damage when holding a One-Handed Weapon |
| SKIP | | +8% additional Max Energy Shield if you have triggered Shield Regain in the last 8s (Max |
| SKIP | | +8% additional Minion Damage if a Synthetic Troop Skill has been cast recently |
| SKIP | | +8% additional Physical Damage while having Fervor |
| SKIP | | +8% additional damage against Cursed enemies |
| SKIP | | +8% additional damage if you have lost Life recently |
| SKIP | | +8% damage against Cursed enemies |
| SKIP | | +80% inflicted Paralysis Effect when holding a Two-Handed Weapon |
| SKIP | | +9% Attack Damage when holding a One-Handed Weapon |
| SKIP | | +9% Attack Damage while Dual Wielding |
| SKIP | | -5% additional Elemental Damage taken for every type of Elemental Damage recently |
| SKIP | | -8% All Resistance when the enemy has max Affliction |
