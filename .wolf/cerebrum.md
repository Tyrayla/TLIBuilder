# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-05-20

## User Preferences

<!-- How the user likes things done. Code style, tools, patterns, communication. -->

## Key Learnings

- **Project:** tli-builder
- **Description:** TLI Builder — talent tree build planner for The Last Immortal
- **TLI terminology:** "Life Regain" not "Life Leech"; "Cooldown Recovery Speed" not "Cooldown Reduction"; "Life Regeneration Speed" for regen rate stats.
- **Test runner:** `py -3.12 -m pytest tests/` from backend/. All 73 tests pass. `requirements-dev.txt` in backend/ has pytest.
- **node_type_filter matched vs total:** Only 22 stats matched originally. Root causes were (1) display_names used "Increased X" but snapshot text says just "X", (2) stop word collision for _inc/_additional variants. Both fixed: display_names now match snapshot plain text, _STOP_WORDS reduced to {"of","the","a","an"}.
- **node_type_filter_builder candidate pool:** Builder uses STAT_META (all ~180 stats) as candidates, NOT NODE_MODIFIER_POOL. The pool's min/max values were never used in build_filter — it was only acting as a whitelist, blocking newly-added stats.
- **node_type_filter scoring:** Jaccard `overlap/|union|` instead of `overlap/len(dn_words)`. Longer/more-specific display names win over generic single-word ones automatically. Threshold 0.5.
- **stat-audit.md:** Completed by user. All YES/RENAME/NO decisions applied — stat.py and stat_meta.py now have ~180 enum members covering damage, ailments, life/mana/ES, defense, buffs, gear, and utility stats. node_modifier_pool.py updated for ARMOR→ARMOR_FLAT rename.
- **Stat renames from audit:** MAX_LIFE→MAX_LIFE_FLAT, MAX_MANA→MAX_MANA_FLAT, ARMOR→ARMOR_FLAT, COOLDOWN_REDUCTION_INC→CDR_SPEED_INC. LIFE_LEECH_RATE removed entirely. STRENGTH/DEXTERITY/INTELLIGENCE → _FLAT variants, _INC added.
- **Flat-vs-inc bug pattern:** Any stat that exists only as a flat variant will absorb % modifier texts (Jaccard tiebreaker needs both flat and inc to exist to route correctly). When a % stat displays as a tiny decimal, check whether the _inc variant is missing from stat.py.
- **LIFE_REGEN_INC semantics:** Repurposed — now stores "% of max life per second" (e.g. 0.6%). LIFE_REGEN_SPEED_INC stores the speed multiplier (+4% Life Regeneration Speed).

## User Preferences

- Never commit without asking first ("Don't send random commits ever, ask me if you feel something should be committed first before doing so")
- Hero trait is_pick_one_from_two: `false` = radio group (pick 1 at that unlock_level among all `false` traits), `true` = sub-row pick-1 submenu at that unlock_level. NOT a pair/sibling relationship.
- Hero Trait screen layout: dropdown for hero/variant selection in header, horizontal columns (one per unlock_level 45/60/75), circles with name inside, hover/click shows floating info card. Base trait is on LEFT, always-selected, vertically centered.
- Hero trait base level: set by RARITY of the hero trait item (Normal/white=L1, Rare/purple=L2, Ultimate/red=L3). A "+2 trait level" modifier can push higher (up to L5). Artificial Moon appears at level 5. NOT derived from character level.
- Hero memories: physical items socketed into trait slots. Types: Origin (LV45), Discipline (LV60), Progress (LV75). A special mod allows a different type to be socketed in the base slot, leveling up the base trait. Advanced traits at 45/60/75 unlock when the respective memory is socketed.
- Hero trait rarity levels: White(Normal)=L1, Blue(Magic)=?, Purple(Rare)=L2, Orange(Epic)=?, Red(Ultimate)=L3. Magic and Epic mapping is unknown. +2 modifier can raise level further.

## Key Learnings (continued)

- **IPC proxy pattern:** All renderer→backend API calls go through `ipcMain.handle('api-request', ...)` in the main process. The renderer calls `window.api!.apiRequest(method, path, body)`. This removes the need for `webSecurity: false` and eliminates the mixed-content warning from `file://` loading HTTP resources. Browser dev mode falls back to direct HTTP fetch when `window.api?.apiRequest` is undefined.
- **`window.api` type must be optional (`api?:`)** in `src/preload/index.d.ts` so `window.api?.apiRequest` passes the TS2774 check. Use `window.api!.method()` inside branches already guarded by an `if (ipcMode)` check.
- **`FormData` file upload over IPC:** Renderer reads `File` as `new Uint8Array(await file.arrayBuffer())`, passes through IPC, main process does `new Blob([Buffer.from(fileBytes)])` to reconstruct for Node's FormData. Direct `new Blob([fileBytes])` fails TS type check in tsconfig.node.json (ArrayBufferLike vs ArrayBuffer).

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->
- [2026-05-20] builds_manager API: `load()` not `load_builds()`, `save_build(dict)` not `save_build(id, name, ...)`, `_DIR` not `BUILDS_DIR`. Always read the actual file before writing tests against it.
- [2026-05-20] pytest is installed on Python 3.12 (py -3.12) but not 3.10 on this machine. Tests run with `py -3.12 -m pytest` from backend/. A requirements-dev.txt exists for installing to whichever Python is used.

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->
