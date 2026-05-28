# Changelog

## [Unreleased]

### New Features
- **Custom Mods panel** — freeform modifier text input in the Calcs screen feeds the full stat engine as if the modifier were on gear.
  - Supports any stat in the system: flat values, percentage increases, range expressions (`50-80 physical damage`), and multi-stat lines.
  - "increased / reduced / more / less" verbs are stripped before matching so natural game text resolves correctly.
  - Live preview via `/api/resolve-mod` shows ✓ / ✗ resolve status as you type.
  - Per-mod status rows show the resolved stat display name or flag unrecognized mods.
  - Custom mods persist in the build save and are labeled "Custom Config" in the stats breakdown.

### Improvements
- **CSR stat taxonomy** — Critical Strike Rating stats now correctly separate weapon-sourced flat CSR from general flat CSR, mirroring how gear physical damage and ring flat adds are separated.
  - New stat `weapon_crit_rating_flat`: flat CSR from weapon implicits/explicits, scaled exclusively by `attack_crit_rating_gear` and `attack_crit_rating_mh`.
  - `attack_crit_rating_flat` remains for talent/ring/non-weapon flat CSR.
  - `attack_crit_rating_gear` and `attack_crit_rating_mh` are now strictly % multipliers on the weapon's own CSR pool, not summed with flat sources.
- **CSR display names corrected** — all Critical Strike Rating stats now use full in-game text:
  - `attack_crit_rating_gear` → "Attack Critical Strike Rating for this Gear"
  - `attack_crit_rating_mh` → "Critical Strike Rating for the Main-Hand Weapon"
  - Spirit Magi entries → "Spirit Magi Critical Strike Rating (Flat)"
- **DPS display** — Calcs screen now shows only **DPS vs Target Dummy**; raw total DPS is still computed but not displayed since enemy values outside the target dummy are unknown.

### Bug Fixes
- Fixed CSR display names using abbreviated "Crit Rating" instead of the in-game wording "Critical Strike Rating".
- Fixed weapon base CSR implicit (`500 Critical Strike Rating`) incorrectly mapping to `attack_crit_rating_gear` (a % increase) instead of a flat CSR stat — it now maps to `weapon_crit_rating_flat`.
- Fixed `attack_crit_rating_gear` being summed into the flat CSR pool; it is a % multiplier on weapon CSR only and must not participate in the flat additive sum.
- Fixed expression override `+(#) % attack critical strike rating` capturing the general attack CSR increase and mapping it to the gear-specific stat — the override now requires the "for this gear" suffix so the general form falls through to fuzzy matching and resolves to `attack_crit_rating_inc`.

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
