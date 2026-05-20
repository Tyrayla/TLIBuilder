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
- **Stat renames from audit:** MAX_LIFE→MAX_LIFE_FLAT, MAX_MANA→MAX_MANA_FLAT, ARMOR→ARMOR_FLAT, COOLDOWN_REDUCTION_INC→CDR_SPEED_INC. LIFE_LEECH_RATE removed entirely.
- **LIFE_REGEN_INC semantics:** Repurposed — now stores "% of max life per second" (e.g. 0.6%). LIFE_REGEN_SPEED_INC stores the speed multiplier (+4% Life Regeneration Speed).

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->
- [2026-05-20] builds_manager API: `load()` not `load_builds()`, `save_build(dict)` not `save_build(id, name, ...)`, `_DIR` not `BUILDS_DIR`. Always read the actual file before writing tests against it.
- [2026-05-20] pytest is installed on Python 3.12 (py -3.12) but not 3.10 on this machine. Tests run with `py -3.12 -m pytest` from backend/. A requirements-dev.txt exists for installing to whichever Python is used.

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->
