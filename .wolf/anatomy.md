# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-05-20
> Files: tracked | Anatomy hits: 0 | Misses: 0

## ./

- `.gitignore` — Git ignore rules (~90 tok)
- `CLAUDE.md` — OpenWolf (~57 tok)
- `DEVELOPMENT.md` — Development Notes (~406 tok)
- `electron.vite.config.ts` — Vite/Electron build config; renderer alias @renderer→src/renderer/src (~120 tok)
- `package-lock.json` — npm lock file (~62938 tok)
- `package.json` — Node.js package manifest (~394 tok)
- `README.md` — Project documentation (~446 tok)
- `tsconfig.json` — TypeScript configuration (~34 tok)
- `tsconfig.node.json` — TypeScript config for Node/Electron main (~66 tok)
- `tsconfig.web.json` — TypeScript config for renderer (~76 tok)

## .claude/

- `settings.json` (~1439 tok)

## .claude/rules/

- `openwolf.md` (~313 tok)

## backend/

- `server.py` — FastAPI app; loads TREES from data/trees_meta.json at startup; ~9 API endpoints (~7368 tok)

## backend/models/

- `__init__.py` (~0 tok)
- `core_talent.py` — class: is_selected, selected_talent (~161 tok)
- `node_modifier_def.py` — NodeModifierDef dataclass; used by node_modifier_pool.py (~247 tok)
- `node_modifier_pool.py` — NODE_MODIFIER_POOL dict: ~80 stats with micro/medium/legendary increments (~3961 tok)
- `passive_node.py` — NodeType: display, column_label, is_full, is_empty (~462 tok)
- `passive_tree.py` — PassiveTree: add_node, add_connection, add_core_talent_slot, nodes_in_column + 5 more (~1216 tok)
- `stat_contribution.py` — StatContribution dataclass; planned for future engine (~173 tok)
- `stat_meta.py` — STAT_META: stat display names and units (~4306 tok)
- `stat.py` — Stat enum: all game stat identifiers (~2395 tok)

## backend/persistence/

- `__init__.py` (~0 tok)
- `builds_manager.py` — load/save/delete builds from data/builds/ (~738 tok)
- `save_manager.py` — load/save/clear tree state in data/save.json (~226 tok)
- `season_manager.py` — list/get/set active season; load season tree/gear/talents from data/seasons/ (~1191 tok)
- `snapshot_manager.py` — exists/load/save talent_snapshot.json in data/ (~151 tok)
- `tree_config_manager.py` — snapshot/upsert_node/remove_node/toggle_connection for data/trees/ legacy config (~746 tok)

## backend/tools/

- `__init__.py` (~0 tok)
- `node_type_filter_builder.py` — build_filter(); outputs data/node_type_filter.json (~1857 tok)
- `season_importer.py` — make_node_id, build_slug_map, import_nodes, extract_nodes_from_file (~1931 tok)
- `snapshot_diff.py` — diff_snapshots (~1957 tok)
- `talent_parser.py` — parse_document (~2378 tok)

## data/

- `node_type_filter.json` — built by node_type_filter_builder; maps node_type→stats (~37992 tok)
- `save.json` — last saved tree state (~202 tok)
- `talent_snapshot.json` — canonical talent snapshot used by dev tools (~60479 tok)
- `trees_meta.json` — tree name → color mapping for all 30 trees (~413 tok)

## data/seasons/

- `.active` — name of the currently active season (~4 tok)

## data/seasons/SS12 Lunaria/

- `_legendary_gear.json` (~171991 tok)
- `_new_god_talents.json` (~668 tok)
- `alchemist.json` (~2867 tok)
- `arcanist.json` (~2638 tok)
- `artisan.json` (~2742 tok)
- `assassin.json` (~2788 tok)
- `bladerunner.json` (~2790 tok)
- `druid.json` (~2441 tok)
- `elementalist.json` (~2897 tok)
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
- `steel_vanguard.json` (~2814 tok)
- `the_brave.json` (~2774 tok)
- `warlock.json` (~2925 tok)
- `warlord.json` (~2893 tok)
- `warrior.json` (~2663 tok)

## docs/

- `architecture.md` — High-level project architecture overview
- `damage-pipeline.md` — Damage calculation pipeline design
- `importer-pipeline.md` — Season import pipeline
- `modifier-system.md` — Three-layer modifier system design (planned engine)
- `persistence.md` — Persistence layer overview

## out/main/

- `index.js` — Built Electron main process (~1939 tok)

## out/preload/

- `index.js` — Built preload script (~64 tok)

## out/renderer/

- `index.html` — Built renderer entry (~119 tok)

## src/main/

- `index.ts` — Electron main: startPython (spawns backend/server.py), createWindow, IPC get-python-port (~2021 tok)

## src/preload/

- `index.d.ts` — Window interface type declarations (~40 tok)
- `index.ts` — Electron preload: exposes window.api (~64 tok)

## src/renderer/

- `index.html` — Renderer entry HTML (~102 tok)

## src/renderer/src/

- `App.tsx` — Root component; session/screen state management (~3715 tok)
- `index.css` — Global styles; CSS vars (~4027 tok)
- `main.tsx` — Renderer entry point (~70 tok)
- `treeGroups.ts` — GROUPS, isPrimary, getSubtrees, getPrimaryFor + tree grouping helpers (~1134 tok)

## src/renderer/src/api/

- `client.ts` — API client: initApi, all typed API methods (~3232 tok)

## src/renderer/src/components/

- `SlotSidebar.tsx` — SlotSidebar component (~1020 tok)

## src/renderer/src/screens/

- `BuildOverviewScreen.tsx` — Build stat overview screen (~1803 tok)
- `BuildSelectScreen.tsx` — Build selection/management screen (~822 tok)
- `DevToolsScreen.tsx` — Dev tools: snapshot diff, season diff, import (~7087 tok)
- `SlateScreen.tsx` — Slate builder screen (~17123 tok)
- `TreeSelectorScreen.tsx` — Tree selector screen (~1858 tok)
- `TreeViewerScreen.tsx` — Tree viewer with node allocation and debug tools (~5884 tok)
