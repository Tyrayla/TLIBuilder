# Changelog

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
