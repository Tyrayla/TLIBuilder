# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-05-20T12:08:39.290Z
> Files: 141 tracked | Anatomy hits: 0 | Misses: 0

## ./

- `.gitignore` — Git ignore rules (~19 tok)
- `build.bat` (~80 tok)
- `CLAUDE.md` — OpenWolf (~57 tok)
- `dev-err.txt` (~48 tok)
- `dev-out.txt` (~244 tok)
- `DEVELOPMENT.md` — Development Notes (~406 tok)
- `electron.vite.config.ts` (~120 tok)
- `main.py` — main (~149 tok)
- `package-lock.json` — npm lock file (~62938 tok)
- `package.json` — Node.js package manifest (~394 tok)
- `README.md` — Project documentation (~446 tok)
- `server.py` — API: GET, POST, DELETE (7 endpoints) (~8128 tok)
- `TLI Planner - Shortcut.lnk` (~249 tok)
- `TLI Planner.spec` — -*- mode: python ; coding: utf-8 -*- (~272 tok)
- `tsconfig.json` — TypeScript configuration (~34 tok)
- `tsconfig.node.json` — /*", "src/preload/**/*"], (~66 tok)
- `tsconfig.web.json` — /*", "src/preload/index.d.ts"], (~76 tok)

## .claude/

- `settings.json` (~1439 tok)

## .claude/rules/

- `openwolf.md` (~313 tok)

## data/

- `node_modifier_pool.py` — ── MANUAL COMPLETION REQUIRED ──────────────────────────────────────────────── (~3961 tok)
- `node_modifiers.json` (~1248 tok)
- `node_stats.json` (~66 tok)
- `node_type_filter.json` (~37992 tok)
- `save.json` (~202 tok)
- `talent_snapshot.json` (~60479 tok)

## data/seasons/

- `.active` (~4 tok)

## data/seasons/SS12 Lunaria/

- `_legendary_gear.json` (~171991 tok)
- `_new_god_talents.json` (~668 tok)
- `alchemist.json` (~2867 tok)
- `arcanist.json` (~2638 tok)
- `artisan.json` (~2742 tok)
- `assassin.json` (~2788 tok)
- `bladerunner.json` — Declares of (~2790 tok)
- `druid.json` (~2441 tok)
- `elementalist.json` — Declares of (~2897 tok)
- `god_of_machines.json` (~2825 tok)
- `god_of_might.json` (~2550 tok)
- `god_of_war.json` (~2263 tok)
- `goddess_of_deception.json` (~2708 tok)
- `goddess_of_hunting.json` (~2609 tok)
- `goddess_of_knowledge.json` (~2546 tok)
- `lich.json` (~2622 tok)
- `machinist.json` (~2625 tok)
- `magister.json` (~2847 tok)
- `marksman.json` (~2673 tok)
- `onslaughter.json` (~2637 tok)
- `prophet.json` (~2813 tok)
- `psychic.json` (~2433 tok)
- `ranger.json` (~2818 tok)
- `ronin.json` (~2460 tok)
- `sentinel.json` (~2592 tok)
- `shadowdancer.json` (~2786 tok)
- `shadowmaster.json` (~2766 tok)
- `steel_vanguard.json` — Declares of (~2814 tok)
- `the_brave.json` (~2774 tok)
- `warlock.json` — Declares of (~2925 tok)
- `warlord.json` (~2893 tok)
- `warrior.json` (~2663 tok)

## data/trees/

- `goddess_of_hunting.json` (~1343 tok)
- `goddess_of_knowledge.json` (~1391 tok)

## gui/

- `__init__.py` (~0 tok)
- `app.py` — App: show, show_module_selector, show_tree_selector, show_tree_viewer (~321 tok)
- `module_selector.py` — Declares ModuleSelector (~495 tok)
- `sidebar.py` — ActiveTreesSidebar: refresh (~866 tok)
- `tree_selector.py` — Declares TreeSelector (~2520 tok)
- `tree_viewer.py` — CanvasTooltip: refresh (~13587 tok)

## models/

- `__init__.py` (~0 tok)
- `character_sheet.py` — ── NO MANUAL WORK REQUIRED ─────────────────────────────────────────────────── (~533 tok)
- `core_talent.py` — class: is_selected, selected_talent (~161 tok)
- `node_modifier_def.py` — ── NO MANUAL WORK REQUIRED ─────────────────────────────────────────────────── (~247 tok)
- `passive_node.py` — NodeType: display, column_label, is_full, is_empty (~462 tok)
- `passive_tree.py` — PassiveTree: add_node, add_connection, add_core_talent_slot, nodes_in_column + 5 more (~1216 tok)
- `stat_contribution.py` — ── NO MANUAL WORK REQUIRED ─────────────────────────────────────────────────── (~173 tok)
- `stat_meta.py` — ── MANUAL COMPLETION REQUIRED ──────────────────────────────────────────────── (~4306 tok)
- `stat.py` — ── MANUAL COMPLETION REQUIRED ──────────────────────────────────────────────── (~2395 tok)

## out/main/

- `index.js` — path: resolvePort, waitForPort, killPortProcess, startPython, createWindow (~1939 tok)

## out/preload/

- `index.js` — Declares electron (~64 tok)

## out/renderer/

- `index.html` — TLI Planner (~119 tok)

## out/renderer/assets/

- `index-Bpkao4nB.css` — Styles: 76 rules, 8 vars (~2443 tok)
- `index-C9Xb06Mt.js` — getDefaultExportFromCjs: F, escape, q + 4 more (~72288 tok)

## persistence/

- `__init__.py` (~0 tok)
- `builds_manager.py` — URL configuration (~738 tok)
- `node_modifiers_manager.py` — URL configuration (~295 tok)
- `node_stats_manager.py` — URL configuration (~370 tok)
- `save_manager.py` — URL configuration (~226 tok)
- `season_manager.py` — URL configuration (~1191 tok)
- `snapshot_manager.py` — URL configuration (~151 tok)
- `tree_config_manager.py` — URL configuration (~746 tok)

## src/main/

- `index.ts` — isDev: resolvePort, waitForPort, killPortProcess, startPython, createWindow (~2021 tok)

## src/preload/

- `index.d.ts` — Declares Window (~40 tok)
- `index.ts` (~64 tok)

## src/renderer/

- `index.html` — TLI Planner (~102 tok)

## src/renderer/src/

- `App.tsx` — emptySession — uses useState, useEffect (~3715 tok)
- `index.css` — Styles: 93 rules, 8 vars (~4027 tok)
- `main.tsx` (~70 tok)
- `treeGroups.ts` — Exports GROUPS, isPrimary, getSubtrees, getPrimaryFor + 5 more (~1134 tok)

## src/renderer/src/api/

- `client.ts` — Exports getApiBase, initApi, TreeSlot, Build + 32 more (~3532 tok)

## src/renderer/src/components/

- `SlotSidebar.tsx` — SlotSidebar (~1020 tok)

## src/renderer/src/screens/

- `BuildOverviewScreen.tsx` — BuildOverviewScreen — uses useState, useEffect (~1803 tok)
- `BuildSelectScreen.tsx` — slotSummary — uses useState, useEffect (~822 tok)
- `DevToolsScreen.tsx` — DIFF_COLOR — uses useState, useEffect (~7087 tok)
- `SlateScreen.tsx` — ── Board ───────────────────────────────────────────────────────────────────── (~17123 tok)
- `TreeSelectorScreen.tsx` — ORDINALS — uses useEffect (~1858 tok)
- `TreeViewerScreen.tsx` — COLS — uses useState, useCallback, useEffect (~7783 tok)

## tools/

- `__init__.py` (~0 tok)
- `node_type_filter_builder.py` — URL configuration (~1857 tok)
- `season_importer.py` — make_node_id, build_slug_map, import_nodes, extract_nodes_from_file (~1924 tok)
- `snapshot_diff.py` — diff_snapshots (~1957 tok)
- `talent_parser.py` — parse_document (~2378 tok)

## trees/

- `__init__.py` (~0 tok)
- `alchemist.py` — build_tree (~1620 tok)
- `arcanist.py` — build_tree (~1606 tok)
- `artisan.py` — build_tree (~1603 tok)
- `assassin.py` — build_tree (~1604 tok)
- `bladerunner.py` — build_tree (~1679 tok)
- `druid.py` — build_tree (~1431 tok)
- `elementalist.py` — build_tree (~1734 tok)
- `god_of_machines.py` — build_tree (~1578 tok)
- `god_of_might.py` — build_tree (~1427 tok)
- `god_of_war.py` — build_tree (~1311 tok)
- `goddess_of_deception.py` — build_tree (~1537 tok)
- `goddess_of_hunting.py` — build_tree (~1426 tok)
- `goddess_of_knowledge.py` — build_tree (~1462 tok)
- `lich.py` — build_tree (~1492 tok)
- `machinist.py` — build_tree (~1561 tok)
- `magister.py` — build_tree (~1662 tok)
- `marksman.py` — build_tree (~1650 tok)
- `onslaughter.py` — build_tree (~1608 tok)
- `prophet.py` — build_tree (~1602 tok)
- `psychic.py` — build_tree (~1498 tok)
- `ranger.py` — build_tree (~1646 tok)
- `registry.py` — builder (~949 tok)
- `ronin.py` — build_tree (~1482 tok)
- `sentinel.py` — build_tree (~1534 tok)
- `shadowdancer.py` — build_tree (~1612 tok)
- `shadowmaster.py` — build_tree (~1683 tok)
- `steel_vanguard.py` — build_tree (~1581 tok)
- `the_brave.py` — build_tree (~1606 tok)
- `warlock.py` — build_tree (~1626 tok)
- `warlord.py` — build_tree (~1586 tok)
- `warrior.py` — build_tree (~1648 tok)
