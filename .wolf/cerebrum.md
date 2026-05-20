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
- **node_type_filter matched vs total:** Only 22 stats matched in the snapshot (out of many in stat.py). The filter_builder's word-overlap scoring fails on many stats because display_names in stat_meta.py don't align with snapshot wording. Fixing display_names and rebuilding the filter will improve coverage substantially.
- **stat-audit.md:** Created at docs/stat-audit.md. Contains: wrong stats in stat.py (section ①), suspect stats (②), and ~100 missing modifier texts organized by category (③–⑩). User needs to go through it and flag YES/NO/RENAME per entry.

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->
- [2026-05-20] builds_manager API: `load()` not `load_builds()`, `save_build(dict)` not `save_build(id, name, ...)`, `_DIR` not `BUILDS_DIR`. Always read the actual file before writing tests against it.
- [2026-05-20] pytest is installed on Python 3.12 (py -3.12) but not 3.10 on this machine. Tests run with `py -3.12 -m pytest` from backend/. A requirements-dev.txt exists for installing to whichever Python is used.

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->
