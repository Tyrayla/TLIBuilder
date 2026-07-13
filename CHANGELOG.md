# Changelog

## [Unreleased]

### New damage mechanics
- **Damage over Time (skill-DoTs)** — the engine now models the ongoing tick damage of skills that deal Damage over Time directly, rather than only a skill's Hit component. First two skills: **Mind Control** (Erosion) and **Path of Flames** (Fire). Validated against the training dummy to within ~±10% (worst observed case 6%); a small residual on top of *increased*-damage modifiers is still unexplained and under investigation, so treat DoT DPS numbers as an estimate rather than an exact figure for now.
- **DoT damage scoping expanded**: type-matched "X Damage" sources (e.g. Erosion Damage, Fire Damage) and "Elemental Damage" (Fire/Cold/Lightning, excludes Erosion) now correctly scale a matching skill-DoT, and above-max-skill-level scaling now applies to DoT the same way it already applies to Hit damage.

### Hero traits
- **Selena's SS13 hero trait "Dance of the Deep"** is now selectable (tree + node text). Its damage/mechanics are **not yet modeled** — too many unknown mechanics (Crimson Tide, Dance Step/Eternal Sleep, Crimson Shade summons, Ominous Curse, Terra Charge, Catalyst: Ground) to model accurately before SS13's in-game data is available. Selecting it has no effect on computed stats yet; tracked in `data/verification/dance-of-the-deep.json`.

### Internal / docs
- Filed 5 tracked-not-fixed limitations surfaced while building the DPS-coverage audit (`backend/engine/coverage.py`) to `docs/BACKLOG.md` §8: tooltip-suppression risk to coverage's "modeled" signal, a real (separate) live-engine bug in `support_mapper._strip_support_target` that drops clauses 2+ on supports like `fragile_resurrection`, a hand-maintained hero-trait advanced-pick mirror with no drift guard, an engine→server layering violation, and a `**kwargs` loophole in the build-gated-param detector. Cross-linked in `data/verification/restoration-subsystem.json` and `data/verification/activation-mediums.json`.

### Fixes
- **Rhythm activation medium's movement-damage rate is now tier-correct**: the per-meter bonus was hardcoded to a flat 3% at every tier; it's now sourced per-level from the crawled data (3% / 3% / 2% / 2% for levels 0–3), correcting a prior overstatement at tiers 2–3.
- **"Cannot inflict Numbed"** no longer overrides a manual Numbed toggle — it now only suppresses the engine's automatic application, matching how Frostbite already behaves. (Only affects builds with both a manual Numbed toggle and a "cannot inflict Numbed" source active.)
- Importing a malformed or too-new build code now shows a clear error message instead of failing silently or crashing.

---

## [0.5.5] - 2026-06-26

### New skill
- **Chromatic Shot** with its canvas supports **Lightchaser** (Magnificent) and **Splendor** (Noble) — compulsory damage-type conversion (a random element each cast, modeled as the expected average across Fire/Cold/Lightning), shotgunning projectiles with a per-element damage breakdown. Validated to within ~0.5% of in-game.

### Cast-speed breakpoints
- **Tangles** now follow the game's whole-tick **cast-speed breakpoints** (30 ticks/sec): the Tangle panel shows ticks-per-cast and tells you exactly how much **Increased or Additional** cast speed reaches the next breakpoint.
- **Spell Burst** breakpoint helper now shows both the Increased and Additional speed needed (charge speed, or cast speed with Play Safe), combining the labels when both reach the same breakpoint.

### Config
- **Auto-inflicted conditions** your build guarantees (e.g. Splendor inflicting Numbed/Frostbite/Ignite, and the derived Frostbite Rating) now appear in Config automatically, tagged with their source. A new Settings toggle locks them or leaves them editable.
- Cleaner numeric inputs — no more clunky "/ max"; the cap shows on hover. "Shots on Target" is now **Projectile Hits** and tracks your projectile count.

### Performance
- **Much snappier** stat updates: disabling an aura, or opening a skill/support catalog, no longer lags — the headline DPS updates immediately and the catalog's per-item comparisons are batched into one request. Season data is now cached, making bulk computes ~3.6× faster. (Big win on the web version too.)

### Fixes
- Running the dev and installed app at the same time no longer cross-wires their saved builds (separate backend ports).
- Importing a current build no longer shows a bogus "older version" warning.
- **Erosion is no longer treated as Elemental** for "on Elemental hit" effects — Elemental is Fire/Cold/Lightning only.

## [0.5.4] - 2026-06-26

### Hero traits
- **Fixed missing nodes** — several hero-trait nodes weren't showing up at all (e.g. Wind Stalker's Cat's Punches, Incarnation of the Gods' Incarnation, Frostbitten Heart's Glacial Night, Zealot of War's Ceasefire/Extreme Heat/Eternal Flames, Creative Genius's Auto-Ingenuity Program & Multi-Coupling Equation, and more). All recovered.
- **Cleaner node layout** — levels now line up consistently (a single-option level no longer floats higher than the others), guaranteed/always-granted nodes are shown on top, and per-rank nodes show only the **selected rank** in their tooltip instead of every rank at once.
- **Creative Genius** now displays its real structure: a guaranteed node plus separate pick groups per level, shown as combined "pick one" bubbles that fan out to the options when clicked (with the chosen option's tooltip on hover).
- **Community trait names** — the hero-trait dropdown now shows each trait's community shorthand (e.g. "Thea 1", "Bing 2") and is **sorted by release order**.
- **Cat's Punches** (Wind Stalker) is now calculated — its Initial Multistrike Count scaling and additional damage are modeled.

## [0.5.3] - 2026-06-26

### New damage mechanics
- **Spell Burst** — eligible Spells charge up and auto-recast in a burst, modeled on the game's 30-per-second server tick, with manual vs. auto-trigger handling and per-support burst-damage bonuses.
- **Tangles** — the Spell Tangle skill type: your spell is cast by attached tangles, with Tangle Damage, Tangle Damage Enhancement, attached count, and Dormant Entanglement.
- **Curses** — curse application from skills and gear, per-type damage-taken amplification scaled by Curse Effect, a curse limit with an over-limit resolver, and per-curse breakdowns.
- **Empower skills** — Euphoria buffs from slotted Empower skills scaled by Empower Skill Effect, including Well-Fought Battle and Mass Effect.
- **Channeled skills** — a channeled-DPS framework (stack ramp and refresh) plus two new modeled skills, **Icebound Beam** and **Howling Gale**, and their canvas supports.
- **Multistrike** — full attack-speed and chain model.

### Hero traits
- **Erika** — Lightning Shadow (Numbed).
- **Rosa** — High Court Chariot (No Guard, Block Ratio, Holy Domain).

### Build management
- **Web version** — TLI Builder now runs in the browser at **tlibuilder.com**; your builds save locally in the browser.

### Config screen (was Conditionals + Calcs)
- Renamed **Stats → Calcs** and **Conditionals → Config**, with the old Calcs page folded in.
- Conditions now **auto-hide** unless your build actually uses them — toggle **Show all** to see every option.
- **Editable enemy / target stats** per loadout: pick a level dummy or customize armor and per-type resistances.
- A free-form **Custom Modifiers** editor — type one modifier per line, each line color-coded by whether it's recognized, with a hover tooltip.

### Calcs / Player Stats
- New boxes for **Numbed**, ailments, and crowd control; a **channeled** panel; and per-skill **Skill Effects** (projectile speed, penetration, jumps, and base mana cost).
- **Enemy Multiplier** and effective-resistance display, plus an enemy-type lever for enemy-count weighting.

### Quality of life
- **Global UI scale** slider and a **draggable sidebar** width.
- **Roll-tier badges** (T1/T2/…) on gear and hero-memory tooltips.
- **Share Feedback** button (Discord) on the main menu.
- Slate inventory: add-to-inventory and right-click remove/delete.

### Experimental (new — still being verified; please report any issues)
- **Loadouts** — multiple full-build variants inside one build, each able to inherit from a shared base, swappable from a sidebar dropdown.
- **Notes inline links** — type `@` in build notes to link an item, talent node, skill, hero trait, pact spirit, memory, or condition; shown as a colored chip with its tooltip on hover.
- **Pact Fates, Kismets, Dual Kismets, and Undetermined Fates** — install onto spirit nodes to replace their effects, with global limits and expansion slots.
- **Ethereal Prisms (24)** and the **Inverse Image** prism — craftable passive-tree items, including reflected-copy damage.
- **Hero traits:** Erika **Wind Stalker**, Rosa **Unsullied Blade** (spell-to-attack, Mercury Baptism), and Selena **Sing with the Tide** (Tide effects, Bard).

### Fixes
- Skill and support tooltips no longer wrongly mark modeled mechanics as "not implemented."
- Fixed craft base types failing to load.
- Removed the deprecated Debug Stats page.

---

## [0.5.2] - 2026-06-16

### Mana / Life sealing & reservation
- Auras, Focus, and Spirit Magus skills now **seal Mana / Life** when active. Full reservation math: base seal × support Mana Multipliers ÷ ((1 + Σ increased) × (1 + Σ additional)) Sealed Mana Compensation — with increased and additional tracked as separate multiplicative pools.
- **Seal Conversion** routes a seal onto Life (off Max Life) with its compensation penalty; **Off the Beaten Track** (95% support multiplier + support levels); **Ward** (Energy Shield from sealed pools); **Lunar Eclipse** (imparted seal + damage per Mana sealed).
- Player Stats shows **Sealed / Unsealed (Available) Life and Mana** with insufficient-pool warnings and clickable per-skill reservation breakdowns. Sealed + Unsealed always sum to Max and round against the player to match in-game; Energy Shield is truncated to match.
- Socketing rules: a base aura/support and its **Precise** variant are now mutually exclusive, and the same support can't be socketed twice on one skill.

### Auras & Focus as build buffs
- Equipped, enabled **Aura and Focus** skills now grant their buffs to the build, scaled by Aura Effect, flowing into the same stat pools offense and defense read. Per-aura buff breakdowns surface any not-yet-modeled lines.

### Updates & Settings
- **One-click silent updates** — no installer wizard, folder picker, or UAC prompt. After Download, "Restart & Install" relaunches straight onto the new version (a dirty build still prompts to save first).
- New **Settings overlay** (gear button in the sidebar and the build list) with a **Stable / Nightly** release-channel toggle, so you can opt into frequent nightly patches.
- Deleting a build now asks for confirmation first.

### Skills & supports
- Full **skill-data reimport** from the recrawl: deduplicated lines, detailed level-aware descriptions, and seal amounts.
- Rebuilt skill/support tooltips with structured, level-aware lines; a support **sort dropdown**; passive-skill DPS-delta sorting and a catalog **refresh button**.
- Supports and offense are computed **per skill slot** (no cross-slot contamination), with a Full-DPS sidebar and per-skill contribution toggles.
- Fixed Attack Focus phantom damage and mapped additional support lines.

### Talent tree, slates & stats
- **Bundled game icons** for talents, hero traits, pact spirits, and core talents; cross-tree **node search** on the overview.
- **Slate Board** rework: saved-slate inventory, floating tooltips, live editing, unified divinity-slate art, and affix tiers.
- **Stats screen v2**: three-column category layout, real source names, per-weapon sources, and crit shown as a tooltip.
- Character level is now driven by the level condition (default 90).

### Quality of life
- Custom title bar with logo and a dark window frame.
- Clearing a conditional's value resets it to its default; brighter, roomier talent tree.

---

## [0.5.1] - 2026-06-13

### Fixed
- Updating the app now refreshes the bundled game data. Previously an update kept the data copied at first install, so after updating the calculator could fail — skills showed no damage and every stat appeared inactive. Your saved builds are preserved.

---

## [0.5.0] - 2026-06-13

### Damage calculation
- Per-skill damage engine for **Berserking Blade, Focused Slash, Moon Strike, and Chain Lightning**, plus their **Magnificent/Noble (canvas) supports**. In-app badges mark every modifier as Consumed (working), Inactive (modeled, not for your skill), Unconsumed (not wired), or NYI, so anything not yet modeled is obvious at a glance.
- Verified against in-game dummy testing (2-minute Recount average), generally within ~3%; the remaining gap is mostly buff/debuff uptime, crit variance, and wide roll ranges.
- Mechanics modeled: Steep Strike / Sweep Slash, crit and crit damage, double/triple/quadruple damage, shotgun (Chain Lightning: Merge / Web), Chain Lightning: Augmentation, Lucky, Willpower, Fervor, main-stat damage bonus, and blessings (Focus/Agility/Tenacity).
- Damage-type conversion (e.g. Lightning to Cold); Elemental split into Fire/Cold/Lightning.
- Enemy mitigation: armor plus elemental/erosion resistance and all penetration types (can go negative to amplify), plus enemy debuffs (Numbed, Frail, Infiltration, Paralysis) shown in a target enemy-stats panel.
- Dual-wielding base effects.

### Skills and supports
- Enable/disable toggles on every active/passive skill and each individual support, saved with the build.
- Each support is calculated local to its skill slot, so separate setups don't cross-contaminate.
- Support Rank (1-5) and Tier controls, roll sliders, and explicit per-line rolls.

### Core talents and belt blends
- Core talents modeled and applied, shown on every tree with badges and a preview.
- Belt blend (Blending Ritual) selection via a searchable picker.

### Gear and crafting
- Gear modifiers are fully resolved and surfaced (nothing silently dropped), with engine badges shown in the affix and belt-blend pickers and the item preview before you add the item.
- Damage-delta previews on gear, multi-slot swaps, list reordering, and a live customization preview.
- Craft no-affix white items; suffix affix tiers; per-item Energy Shield / Armor / Evasion scaling.

### Stats, badges, and quality of life
- New interactive Player Stats screen with clickable source breakdowns.
- Derived stats (total Life, Energy Shield, Mana, and more) and a dedicated Energy Shield panel.
- Modifier badges app-wide with a clear four-state taxonomy (Consumed / Inactive / Unconsumed / NYI).
- DPS Delta previews on mods, nodes, and gear.
- Conditionals manager (low life, enemy debuffs, life %, proximity, and more), settable and auto-derived, with a tidier layout.
- Custom Mods panel; pact-spirit per-node and spirit-total DPS on hover; shared tooltips and broad UI revamps.

---

## [0.4.0] - 2026-05-28

### New Features
- **Calcs screen** — new Calcs tab in the sidebar with a full damage breakdown for the active skill in slot 1.
  - Per-hit-form display: effectiveness %, proc chance, average hit pre- and post-crit, DPS contribution per form.
  - Blended **Total DPS** and **vs Target Dummy** DPS (applies target dummy's baseline mitigation: 50% physical armor; 30% armor + 30% elemental/erosion resistance for non-physical damage).
  - Crit Chance, Crit Multiplier, Steep Strike Chance, and Attacks per Second displayed below the form breakdown.
  - NYI badge list shows which modifiers are not yet wired so numbers are always clearly partial rather than silently wrong.
  - Unsupported skills show a clear "not yet supported" state with no zeroed numbers.
- **Offense engine** — explicit per-skill damage pipeline. Only skills registered in the engine produce calculations; all others show NYI rather than a partial or guessed result.
  - **Berserking Blade** fully supported: Sweep Slash and Steep Strike as mutually exclusive hit forms; skill's intrinsic +20% Steep Strike chance passive parsed from skill data.
  - Above-max-level effectiveness scaling: ×1.10 per level for levels max+1 to max+10, ×1.08 per level beyond that (compound).
  - Tag-filtered increased damage pool: all `*_dmg_inc` stats from the talent tree whose tags intersect the skill's tag set are summed into a single additive multiplier. Generic (untagged) stats always apply.
  - Crit formula: final CSR ÷ 10000 = crit chance (100 CSR = 1%).
- **Legendary gear corruption** — Corruption dropdown (None / Desecration / Mutation) on legendary items that have a corroded variant.
  - **Desecration** — toggle up to 2 explicit modifiers to their corroded tier; affected rows highlight in purple and stats update immediately.
  - **Mutation** — select one slot-specific mutation implicit from the craft base pool; appears in purple above regular implicits and contributes to stats.
- **Legendary random affix pools** — placeholder "Random X" explicits now show an enabled dropdown listing all valid options. Selecting eagerly swaps the affix; range sliders appear for numeric affixes. Selection persists across save/load.
- **Craft item corruption** — Corruption dropdown (None / Desecration / Mutation) on crafted items.
  - **Desecration** — per-slot toggle (max 2) upgrades to T0+; T0+ is excluded from the dropdown unless the slot is already corroded.
  - **Mutation** — replaces both base slots from the corrosion pool with range sliders for numeric modifiers.
- **Dev data inspector** — browser tool at `/api/dev/inspect/` for exploring season JSON files: field discovery, variant exploration, filtered queries, syntax-highlighted output.

### Improvements
- **Weapon implicit stat parsing** — crafted weapon base types (Physical Damage, Attack Speed, Critical Strike Rating) now resolve to engine stat keys and feed the damage calculation correctly.
- **Dev-mode API gating** — `/api/dev/*` routes return 404 in packaged builds.
- **Legendary corrosion toggle redesigned** — inline 7×7 px square to the left of modifier text; active = solid purple, inactive = dim border.

### Bug Fixes
- Fixed tag-filtered increased damage from talent nodes not applying to skill damage — `inc_total` was a hardcoded 0.0 placeholder; now reads all matching `*_dmg_inc` stats from the talent tree filtered by skill tags.
- Fixed Berserking Blade showing 0% Steep Strike chance — the skill's intrinsic `+20% Steep Strike` passive was not being parsed from skill data.
- Fixed crafted weapon implicits (Physical Damage, Attack Speed, CSR) not contributing to engine stats — `affix_kind: 'implicit'` affixes have no resolved stat keys and were silently skipped by the payload builder.
- Fixed skills cache always empty — `_get_skills_data()` was reading the wrong root key (`"items"` instead of `"skills"`) from `_skills.json`, causing offense calculation to never run.
- Fixed crit chance always 100% for any weapon with CSR — the formula used `raw_csr / 100` instead of `/ 10000` (500 CSR should be 5%, not 500%).
- Fixed mutation affix pool not populating after reimporting craft base types — the reference store now refreshes immediately after a successful DevTools import.
- Fixed mutation affixes having no stat contribution — `corrosion_base` entries are now parsed with `parse_affix_text` at import time.
- Fixed craft modifier dropdown grouping fixed-value tiers separately from range-value tiers — tier groups are now keyed on a normalized expression with all numeric literals replaced by `#`.
- Fixed leaving Desecration mode clearing the selected modifier — slot now downgrades to the best non-corroded tier rather than clearing.
- Fixed blessing stack conditions having min_base and max_base swapped.

---

## [0.3.2] - 2026-05-25

### New Features
- **Conditions framework revamp** — condition system rebuilt on a fixed-point iteration engine. Numeric conditions (blessing/channeled stacks, enemy ailment/wilt/torment counts, trauma stacks) are now first-class with dynamic build-driven maximums. Boolean conditions support compound expressions (`and`/`or`/`not`/threshold operators). Per-stack scaling recipes can reference numeric condition values. Load-time validation rejects unknown or mistyped condition keys at startup rather than silently computing wrong values.
- **Data-driven Conditionals screen** — BuildOverviewScreen now renders entirely from the server's condition definitions. Numeric conditions show spinners with engine-derived maximums. Auto-derived active flags (`tenacity_active`, `agility_active`, `focus_active`) display as read-only indicators rather than user-toggleable checkboxes. Clamp warnings appear inline when a user's entered value exceeds the current build's dynamic maximum.

### Improvements
- **Unified `conditionState`** — replaces the previous split of `conditions: string[]` + `conditionValues: Record`. All condition values (boolean and numeric) now live in a single `conditionState` map on build, store, and API payload. Old builds are migrated automatically on load.
- **Build code migration** — `SCHEMA_VERSION` bumped to 2; old codes carrying `conditions`/`conditionValues` are migrated to `conditionState` transparently on import.

### Bug Fixes
- Fixed condition values not being preserved correctly across engine passes when a talent-derived maximum was lower than the user's entered stack count — the engine now clamps and reports clamped values rather than computing at the unclamped input.
- Fixed test fixture for `test_round_trip_rehydrates_legendary_gear` using a flat `affixes` shape instead of the real `variants` catalog format, which caused the round-trip test to fail on a correct rehydration path.
- **Support skill levels** — support skills now have level controls. Normal supports range from 1–40. Activation Medium, Magnificent, and Noble supports range from 0–2 (default 1). Old saves default to level 20 / `support_skill` type on load.
- **Support skill detail panel** — the description panel for a selected support now shows only the advanced/effect lines rather than the full raw description text.
- **Vorax gear slot enforcement** — Vorax items now auto-assign to their correct slot type on creation (e.g. Head limb → Helmet) and can only be dragged to valid slots, matching the behaviour of legendary and crafted items.
- **Slate board state preserved on navigation** — switching screens via the sidebar no longer discards uncommitted slate changes; state is now synced to session on every board mutation rather than only on "Done".
- **Moth/Prairie slate copy in stat calculations** — fixed two bugs: (1) the board position map was built with doubled anchor offsets because cells are stored as absolute board positions; (2) all slots were being copied instead of only the bottom slot, which is what the mechanic specifies.
- Fixed nine stale stat enum references in `node_modifier_pool.py` (`CRIT_DMG` → `CRIT_DMG_INC`, `PHYSICAL_` prefix additions) that prevented all backend tests from collecting.
- Fixed `coreTalentSelections` typed as `Record<number, string>` — JSON keys are always strings; changed to `Record<string, string>` and updated the `sanitizeSlot` migration guard accordingly.
- Fixed `'conditional'` missing from the `UnresolvedStat.reason` union type, causing a spurious TypeScript error in DevToolsScreen.
- Fixed "What's New" update dialog showing raw HTML tags — release notes are now rendered as HTML with styled headings, lists, and code spans.

---

## [0.3.1] - 2026-05-25

### Bug Fixes
- Fixed pact spirit outer/main skill being counted twice in stat calculations — outer effects now come from the selected rank's modifiers only, not the base slot effect.
- Fixed gear stats missing after importing a build via build code or share link — legendary items are now fully rehydrated with a flat affixes list on decode.
- Fixed notes, hero traits, hero memories, and pact spirits not being saved — extra fields were silently dropped by Pydantic v2; resolved with `extra='allow'` on `BuildRequest`.

### Security
- Path traversal guard on build IDs and season names in the Python backend.
- `shell.openExternal` restricted to `http://` and `https://` URLs only.
- Renderer sandbox enabled.
- Share service responses capped at 512 KB; `tli1_` prefix validated before decode.

### Other
- Windows Start Menu and taskbar now show the TLI Builder icon instead of the default Electron icon.

---

## [0.3.0] - 2026-05-24

### New Features
- **Share via Link** — export tab now includes a "Share via Link" button that uploads the build code to the share service and returns a short URL. Both import fields (overlay and build select screen) accept either a raw `tli1_` code or a share link.
- **Crafted/Vorax item re-edit** — previously crafted and Vorax items in the build can now be reopened and edited directly from the gear screen instead of having to re-craft from scratch.
- **Instant screen navigation** — all season-global catalogs (legendary gear, craft bases, grafts, hero traits, hero memories, conditions) are now prefetched once at app init. Returning to GearScreen, HeroTraitScreen, BuildOverviewScreen, and PactSpiritScreen is instant after the first load.

### Improvements
- **Dual-value and range-multi affix display** — gear affixes that represent two separate ranges (dual-stat) or split min/max values now display and compute correctly.
- **Hero memory stat coverage** — alias lookups and multi-stat mappings added for hero memory modifiers that previously returned no stat contribution.
- **Stat resolver extended** — ~60 new stat enum values added; crit damage keys renamed for consistency; new override entries and normalization fixes for edge-case modifier text.

### Bug Fixes
- Fixed gear stat resolution for crafted items loaded from a saved build (affix `stat_key` fields were not being rehydrated on build open).
- Fixed Content Security Policy blocking outbound requests to the share service (`https://api.tlibuilder.com` added to `connect-src`).

---

## [0.2.0] - 2025-12-01

- Hero Memories and Pact Spirits features
- Version display, Check for Update, and About buttons on main menu

## [0.1.1] - 2025-11-15

- Auto-updater, dev mode gating, and packaging config fixes

## [0.1.0] - 2025-11-10

- Initial release
