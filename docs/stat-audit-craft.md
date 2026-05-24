# Stat Audit — Craft Affixes (Unresolved)

> Generated 2026-05-23.
> Affix texts from craft base types that have no matching stat lookup.
> Coverage: **5768/6216 (93%) affixes resolved**
>
> **How to fill in the Answer column:**
> - `YES` → add new stat key (use Suggested Key or write your own in Notes)
> - `NO` → out of scope, skip entirely
> - `MULTI` → maps to multiple existing stats (add to MULTI_STAT_OVERRIDES)
> - `OVERRIDE` → maps to an existing single stat (add to EXPRESSION_STAT_OVERRIDES)
> - `SKIP` → conditional/situational, defer for now

Total unresolved patterns: **74**

---

| # | Pattern | Count | Suggested Key | Answer | Notes |
|---|---------|-------|---------------|--------|-------|
| 1 | `Adds ((#)) - ((#)) Elemental Damage to the gear -# % Gear Physical Damage` | 60 | | | |
| 2 | `-# % additional Damage Over Time taken when having at least # Evasion` | 27 | | | |
| 3 | `-# % additional Damage Over Time taken when you have at least # Max Energy Shield` | 27 | | | |
| 4 | `-# % additional Damage Over Time taken when having at least # Armor` | 27 | | | |
| 5 | `Reaps (#.(#).#) s of Trauma Damage when dealing Damage Over Time. The effect has a # s Recovery Time against the same target` | 16 | | | |
| 6 | `Enemies have a ((#)) % chance to explode when defeated by an Attack or Spell, dealing True Damage equal to ((#)) % of their Max Life to enemies within a # m radius` | 13 | | | |
| 7 | `+((#)) % Spell Burst Charge Speed +# % chance to immediately gain # stack(s) of Spell Burst Charge when using a skill. Interval: #s` | 12 | | | |
| 8 | `Triggers Lv. ((#)) Aim while standing still. Interval: # s` | 12 | | | |
| 9 | `+((#)) % additional Minion Damage when you have ((#)) Minion(s)` | 12 | | | |
| 10 | `(-#--#) % additional damage dealt by Nearby enemies` | 12 | | | |
| 11 | `+((#)) % Combo Damage Enhancement if the Combo Finisher cast recently consumes at least # Combo Point(s)` | 12 | | | |
| 12 | `Reaps (#.(#).#) s of Wilt Damage when dealing Damage Over Time. The effect has a # s Recovery Time against the same target` | 12 | | | |
| 13 | `Reaps (#.(#).#) s of Ignite Damage when dealing Damage Over Time. The effect has a # s Recovery Time against the same target` | 12 | | | |
| 14 | `+((#)) % Critical Strike Rating against Traumatized enemies -# % additional Hit Damage` | 9 | | | |
| 15 | `+((#)) % Blur Effect # % chance to gain Blur per ((#)) m you move` | 9 | | | |
| 16 | `+((#)) % additional Fire Damage and +((#)) % Fire Penetration when you have at least # stack(s) of Tenacity Blessing` | 9 | | | |
| 17 | `+((#)) % additional Lightning Damage and +((#)) % Lightning Penetration when you have at least # stack(s) of Agility Blessing` | 9 | | | |
| 18 | `+((#)) % additional Cold Damage and +((#)) % Cold Penetration when you have at least # stack(s) of Focus Blessing` | 9 | | | |
| 19 | `+((#)) % chance to gain # stack of Agility Blessing on defeat` | 9 | | | |
| 20 | `+((#)) % chance to gain # stack of Focus Blessing on defeat` | 9 | | | |
| 21 | `+((#)) % chance to gain # stack of Tenacity Blessing on defeat` | 9 | | | |
| 22 | `+((#)) % Sealed Mana Compensation for Steadfast` | 8 | | | |
| 23 | `+((#)) % Sealed Mana Compensation for Nimbleness` | 8 | | | |
| 24 | `+((#)) % Sealed Mana Compensation for Energy Fortress` | 8 | | | |
| 25 | `Gains a stack of Fortitude when using a Melee Skill (-#--#) % additional damage taken` | 4 | | | |
| 26 | `(-#--#) % additional damage taken at Low Mana` | 4 | | | |
| 27 | `Reaps (#.(#).#) s of Damage Over Time when dealing Damage Over Time. The effect has a # s Recovery Time against the same target` | 4 | | | |
| 28 | `+((#)) % additional damage when channeling` | 3 | | | |
| 29 | `Has Hasten +((#)) % Attack Speed, Cast Speed, and Movement Speed when having Hasten` | 3 | | | |
| 30 | `Triggers Lv. ((#)) Brisk Wind upon starting to move. Interval: # s` | 3 | | | |
| 31 | `+# % chance to Paralyze the target on hit` | 3 | | | |
| 32 | `+# % additional Fire Damage and +((#)) % Fire Penetration when you have at least # stack(s) of Tenacity Blessing` | 3 | | | |
| 33 | `+# % additional Lightning Damage and +((#)) % Lightning Penetration when you have at least # stack(s) of Agility Blessing` | 3 | | | |
| 34 | `+# % additional Cold Damage and +((#)) % Cold Penetration when you have at least # stack(s) of Focus Blessing` | 3 | | | |
| 35 | `+# Jumps +((#)) % additional damage for every Jump (multiplies)` | 3 | | | |
| 36 | `+((#)) % additional damage while having Fervor` | 3 | | | |
| 37 | `+((#)) % Blur Effect Gains Blur for # s after losing Blur` | 3 | | | |
| 38 | `Gains Attack Aggression when casting an Attack Skill +((#)) % Attack Aggression Effect` | 3 | | | |
| 39 | `Gains Spell Aggression when casting a Spell Skill +((#)) % Spell Aggression Effect` | 3 | | | |
| 40 | `+# % Max Mana. +((#)) Skill Cost` | 3 | | | |
| 41 | `Gains Attack Aggression when Minions land a Critical Strike +((#)) % additional Minion Damage` | 3 | | | |
| 42 | `Gains Spell Aggression when Minion Spells land a Critical Strike +((#)) % additional Minion Damage` | 3 | | | |
| 43 | `+((#)) % chance to launch one more wave when casting a Barrage Skill` | 2 | | | |
| 44 | `Regenerates ((#)) % Life per second when taking Damage Over Time` | 2 | | | |
| 45 | `+((#)) % damage per stack of any Blessing` | 2 | | | |
| 46 | `+# % damage per # stats` | 2 | | | |
| 47 | `Have Fervor +# % additional damage` | 2 | | | |
| 48 | `+((#)) % additional damage against Traumatized enemies` | 2 | | | |
| 49 | `+((#)) % additional skill damage when Demolisher Charge is consumed` | 2 | | | |
| 50 | `Eliminates enemies under ((#)) % Life upon inflicting damage` | 2 | | | |
| 51 | `+((#)) % additional Attack Damage after standing still for #s. -# % additional Attack Speed` | 2 | | | |
| 52 | `+((#)) % Gear Attack Speed. (-#--#) % additional Attack Damage` | 1 | | | |
| 53 | `+((#)) % additional Evasion while moving` | 1 | | | |
| 54 | `When dealing damage, inflicts Lightning Infiltration . Interval for each enemy: # s When Minions deal damage, inflicts Lightning Infiltration . Interval for each enemy: # s +((#)) % Lightning Infiltration Effect` | 1 | | | |
| 55 | `+# % Attack Speed and Movement Speed for every ((#)) % of Attack or Spell Block` | 1 | | | |
| 56 | `+((#)) % additional Max Energy Shield while moving` | 1 | | | |
| 57 | `Inflicts Cold Infiltration when dealing damage. Interval for each enemy: # s When Minions deal damage, inflicts Cold Infiltration . Interval for each enemy: # s +((#)) % Cold Infiltration Effect` | 1 | | | |
| 58 | `+# % Cast Speed and Skill Area for every # % of Spell Block` | 1 | | | |
| 59 | `+# % Sealed Mana Compensation for Steadfast` | 1 | | | |
| 60 | `+# % Sealed Mana Compensation for Nimbleness` | 1 | | | |
| 61 | `+# % Sealed Mana Compensation for Energy Fortress` | 1 | | | |
| 62 | `[Beacon] +# Max Spell Burst +# % additional damage` | 1 | | | |
| 63 | `+# % Max Mana. +# Skill Cost` | 1 | | | |
| 64 | `+((#)) % additional damage for Main-Hand Weapons` | 1 | | | |
| 65 | `+((#)) % additional damage against Frozen enemies` | 1 | | | |
| 66 | `+# % chance to gain # stack of Tenacity Blessing when casting a skill. Interval: # s` | 1 | | | |
| 67 | `+# % chance to gain # stack of Focus Blessing when casting a Summon Skill. Interval: # s` | 1 | | | |
| 68 | `+((#)) % additional Spirit Magus Enhanced Skill Damage and Ailment Damage dealt by Enhanced Skills` | 1 | | | |
| 69 | `+((#)) % additional damage for Synthetic Troop Minions when having at least # Command` | 1 | | | |
| 70 | `+((#)) % additional Armor while moving` | 1 | | | |
| 71 | `When dealing damage, inflicts Fire Infiltration . Interval for each enemy: # s When Minions deal damage, inflicts Fire Infiltration . Interval for each enemy: # s +((#)) % Fire Infiltration Effect` | 1 | | | |
| 72 | `+# % Critical Strike Rating and Critical Strike Damage for every # % of Attack Block` | 1 | | | |
| 73 | `While Reconjuring , Spirit Magi regenerate ((#)) % Life per second` | 1 | | | |
| 74 | `Gains Hasten when Minions land a Critical Strike +((#)) % additional Minion Attack and Cast Speed` | 1 | | | |
