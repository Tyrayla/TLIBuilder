# TLI Builder — Outstanding Backlog

Grouped by area. Pruned 2026-06-16 after the 0.5.2 release and the web launch.

## Shipped in 0.5.2 (removed from the open list)
Mana/Life sealing & reservation (incl. Lunar Eclipse) · auras & Focus as build buffs · nightly channel + silent
auto-update + Settings overlay · full skill-data reimport · display rounding option A (sealed/unsealed + ES match
in-game) · slate inventory + Add-to-Inventory + right-click delete/remove + consolidated bonus view (SlateOverview)
· structured level-aware skill/support tooltips · update-banner no longer pushes the footer off-screen · Dreamweaver
spirit working after the reimport.

## Shipped — Web-hosted version (2026-06-16)
TLI Builder runs in the browser at **tlibuilder.com** (Cloudflare Pages app + `tlibuilder-data` Pages project for
catalogs/icons/engine-data; info page at **about.tlibuilder.com** off the `gh-pages` branch). The pure-Python engine
runs in a Pyodide Web Worker (Path B: `import server` with bundled fastapi/pydantic wheels); catalogs/icons load from
the data CDN. Builds + last-session save persist client-side via **main-thread IndexedDB** (the worker snapshots
`/persist` and the main thread owns storage; in-worker IDBFS was unreliable in Brave). Verified in Chrome/Edge/Brave.
Merged to `dev`. Cloudflare Web Analytics enabled. **Remaining (optional):** see §7.

**Dropped (decided against):** global display truncation (option B) and the 1-life reservation floor.

## 0c. Tangles (core shipped 2026-06-17 — follow-ups)
Shipped: the **Tangle skill type**. A Spell becomes a Tangle via an activator support (**Spell Tangle** /
**Activation Medium: Tangle**, NOT Manifold); it's then cast by N attached tangles (each a full caster) instead of
the player, so **Tangle DPS = single-cast offense × attached_count × (1 + Σ Tangle Damage Enhancement)**. Engine:
`offense.calculate_offense(tangle=…)` adds the `"tangle"` mod tag (so `tangle_dmg_inc` / `tangle_dmg_additional` /
`tangle_crit_rating_flat` apply via existing tag pools) + folds the count + enhancement multipliers into the DPS
totals like `cast_multiplier`; `compute._offense_for_slot` detects the activator and sizes the counts
(`attached = min(1 + extra_tangle_applied_flat, 2 + max_tangle_quantity_flat)`, default 1). New stats:
`tangle_dmg_additional`, `tangle_dmg_enhancement_additional` (separate additive-within-itself multiplier),
`tangle_crit_rating_flat`, `tangle_attach_range_inc`. **Dormant Entanglement** (+40% additional Tangle Damage per
inactivated tangle) via user condition or the `has_dormant_entanglement_flag` (Acquaintance / gear). Conditions:
`active_tangles` (lower-only override), `has_dormant_entanglement`. Fixed: "Tangle Damage Enhancement" was
mis-mapping to `tangle_dmg_inc` (now `tangle_dmg_enhancement_additional`). Dedicated Tangle panel + auditable
×count/×enhancement annotation in the Skill Hit Damage breakdown.
- **USE vs CAST filtering (deferred):** tangle triggers are CASTS, not USES — USE-gated buffs/procs should not apply
  to tangle casts. v1 applies all player buffs (may slightly over-count). Build the USE/CAST gate later.
- **"+X per activated Tangle" node lines** (e.g. Movement Speed per activated tangle) — not yet scaled by the active
  count (the `active_tangles` condition exists; wire the per-activated-tangle node contributions to it).
- **Magister "when generating Tangle …" trigger nodes** (start ES charging / gain Focus Blessing on generate) — the
  trigger-on-generate mechanic isn't modeled.
- **Manifold "spawns all at once" + multi-enemy clear / attach prioritization** — positioning/clear, not boss DPS.
- **Dormant Entanglement exploit (far future):** fast cast speed makes a tangle briefly inactive while its
  projectiles are mid-air, feeding the +40% per inactivated — needs projectile-travel simulation; not worth doing.
- See docs/INGAME_VERIFICATION_BACKLOG.md (TANGLE-01) for verification items.

## 0a. Empower skills (core shipped 2026-06-17 — follow-ups)
- **★ HIGH PRIORITY — many empower skills lack progression tables in the data.** Their per-level scaling isn't
  present, so the resolver can only interpolate from the Lv1 (simple) and Lv20 (detailed) anchors and can't scale
  accurately (or past Lv20). Work out / import the missing empower progression tables (data + importer), then the
  resolver can use real per-level values instead of the 2-point interpolation. Blocks accurate empower numbers.
Shipped: empower (Euphoria) PLAYER buffs from slotted empower skills, parsed like auras (Lv1/Lv20 interpolation),
scaled by **Empower Skill Effect** (new `empower_effect_inc`/`empower_effect_additional`, global + slot-local),
emitted as typed/scoped player damage stats so they ride the conversion-aware offense pipeline. Empower-only support
gate; **Well-Fought Battle** (user-set casts, default max 3) + **Mass Effect** (charge-scaled). Per-skill **charges**
helper (`skill_charges.py`: cooldown→base 1, else none; ambiguous cooldowns surfaced). Per-empower Player Stats panel.
Engine: `empower_resolver.py`, `utility.apply_empower_buffs`. Buffs assumed 100% uptime; Euphoria assumed to stack.
- **NYI (surfaced):** minion/Sentry/Spirit-Magi/ally-targeted empowers (no minion/party engine); per-enemy/per-Mark/
  "for every stack of Focus Blessing"/"Each buff grants … Stacks up to N" conditional stacking; `empower_skill_level`
  contribution; the Aim "-16% Attack and Cast Speed" compound only captures cast speed.
- **Euphoria uptime/decay/refresh** assumed 100% — model real uptime later.
- **Skill charges**: cooldown is now a **structured field** the importer writes (`cooldown`/`charges`/`duration`/
  `icon_url` sourced from the recrawl; charges default to **1** for any cooldown skill). All 20 empower skills now
  carry a cooldown, so Mass Effect scales correctly. Remaining: explicit **multi-charge counts aren't auto-detected**
  (the text's "charge" mentions are mostly Demolisher/Terra resource mechanics, not max-charge counts) — default 1
  may undercount the few skills with a real >1 base; fill those when found. Mass Effect's per-charge level-scaling
  still uses the displayed (Lv1) value (approximate). **Durations** are captured structurally: a convenience scalar
  `duration` (the skill's own "Lasts N s") plus a full `durations` list classified by kind — `skill` / `entity`
  (sentry/remnant/terra lifetimes) / `per_stack` (per-stack buff duration + max_stacks, e.g. Speed Phantom's 1.2 s
  Euphoria) / `interval` (tick/proc period) / `duration_mod` / `window` (DoT/HoT). Collect-everything: 203 entries
  across 165 skills, **not consumed by the engine yet** — stored for future uptime/display. NOT captured: bare
  fragment lines (a lone "1 s" the crawler split out) and a few rare projectile/area phrasings. `icon_url` stored,
  not used yet. The eventual consumer is **real uptime** (duration vs cooldown; per-stack/conditional buffs are
  hit-gated, so don't naively treat a per-stack duration as a skill-wide window).
- **Per-skill Empower Effect scoping** ("+X% Empower Skill Effect for <skill>", ethereal prism) currently applies
  globally — add skill→slot scoping.
- **"Affects allies" flag (NEW request, forward-looking):** a per-buff-source boolean (auras, empower, eventually
  minions) marking whether the buff also benefits allies — default false; almost all auras + some empowers do. No
  consumer today (party-play DPS isn't modeled); design + wire it WITH party-play so it isn't a dead field. Decide
  user-set toggle vs data-derived when building it.
- See docs/INGAME_VERIFICATION_BACKLOG.md (EMPOWER-01) for verification items.

## 0b. ★ NEXT — False "Unrecognized (NYI)" / "Inactive" on tooltips & badges
**Do this BEFORE Spell Burst + Tangles.** Skill/support tooltips (and possibly other mod badges) flag lines as
**Unrecognized (NYI)** or **Inactive** even when the mechanic IS handled or is one we model. Confirmed examples
(Chain Lightning build):
- **Chain Lightning skill tooltip**: "+2 Jumps for this skill" → *Unrecognized (NYI)* (jumps are a real, modeled
  mechanic — should resolve or at least not read as unrecognized).
- **Jump support tooltip**: "+2 Jumps for the supported skill" → *Inactive* (its "additional damage" line resolves
  Consumed, but the jumps line is mislabeled).
- **Lightning to Cold support tooltip**: "Converts 50% of the supported skill's Lightning Damage to Cold Damage" →
  *Unrecognized (NYI)* (conversion lines — see §3 conversions).
- Pattern: a line shown in a TOOLTIP gets its own recognize/badge pass that doesn't see what the engine actually
  applies (or doesn't know jumps/conversion are modeled), so it falsely reads NYI/Inactive. Audit the tooltip line
  classifier (`tooltip.py` `_kind_for` / badge resolver) vs the real resolver/consumable_universe so a line that is
  applied (or is a known-modeled mechanic like Jumps) isn't tagged Unrecognized. Tie into the badge taxonomy
  ([[project_badge_unification]]) — this is the inverse failure of "never silently drop": here we falsely cry NYI.

## 0. Curses (core shipped 2026-06-17 — follow-ups)
Shipped: curse application (slotted curse skills + curse-applying gear affixes), per-final-type damage-taken
amplification (Vulnerability/Scorch/Biting Cold/Electrocute/Corruption + Timid all-hit) scaled by Curse Effect
(increased) + Additional Curse Effect (multiplicative), curse limit (`max_curses_flat`) with the Hekate cap
(`curse_limit_cap_flat`), over-limit conflict + Conditionals dropdown resolver, auto-set `enemy_cursed`, curse-only
support gate (Terrain of Malice), per-curse Player Stats panel. Engine: `backend/engine/curse_resolver.py`,
`_enemy_vuln_mult`. Consolidated the duplicate `max_curse_flat`→`max_curses_flat`.
- **Shackles of Malice** (curse *consumer*: +25% Hit Damage per curse on the enemy, removes curses) + its 4
  dedicated supports (Defile/Mutual Destruction/Spite/Vendetta) — deferred. `curse_effect_additional` is already
  modeled (Defile's line resolves) so wiring Shackles later is incremental. Needs a "curses-on-enemy count".
- **Affix-applied curses beyond gear**: only gear affixes are detected today. Hero-trait/graft curse application
  (e.g. Banquet of Bliss "cursed by Lv N Scorch") isn't auto-collected yet — add the same `_extract_affix_curse`
  scan to those resolution paths.
- **NYI curse lines**: Entangled Pain (DoT — no DoT engine), Dazzled (movement/Blind), ailment-chance lines
  ("+10% chance to Trauma/Wilt/Ignite"). Surfaced NYI, not dropped.
- **Curse uptime/duration**: "Lasts 5 s" / "+% Curse Duration" not modeled — assumes permanent uptime. Model real
  uptime eventually.
- **Curse Skill Area**: `curse_skill_area_inc` resolves (Terrain of Malice / talents) but is a display stub — no AoE
  modeling yet.
- In-game verification items filed in docs/INGAME_VERIFICATION_BACKLOG.md (over-limit precedence, additional-vs-
  increased pooling, same-curse highest-level rule, Noble/Magnificent additional-damage-on-curse, multiplicative
  Additional Curse Effect once a 2nd source exists).

## 1. Auras / buffs
- **Verify the 7 aura review items in-game** (panel "Needs manual review"): Domain Expansion + Precise: Domain
  Expansion (area/ailment additional — Lv1 anchor unparseable, using flat Lv20; confirm Lv1 split), Fearless +
  Precise: Fearless (melee crit Lv1 anchor matched by stat only), Precise: Elemental Resistance (avoid-ailment
  flat Lv20). Fix the underlying simple-description data or accept flat.
- **Focus skills (Phase 1b)**: model Focus mechanics deferred so far — Focus Pts, triggers, True Damage,
  Focus Speed. ~87 aura NYI lines are mostly Focus. Ensure Focus skills get full damage-support access (see §2).
- **Magus (minion) passives**: deferred from the aura buff path; model when minions are modeled.
- **Aura parser gaps (NYI)**: "additional Ailment Damage dealt by Projectiles" / the "dealt by Projectiles"
  (no "Skills") scope form; Domain Expansion's multi-line "Skill Area when ≥8 enemies within 10m" conditional.
- **Stacking-buff generation**: Cruelty-style "gain N stacks on defeat / hitting Elite" are NYI (user sets
  stacks manually). Auto-derive stack counts later.
- **sweep_slash_additional_dmg**: wire its legendary mod line + a form-scoped reader (mirror steep_strike);
  currently parked unwired in `_FORM_SCOPED_ADDITIONAL`.

## 2. Modifier badges / exclusive tagging
- **Expand `_EXCLUSIVE_SKILL_TAGS`** beyond `minion` (candidates: sentry/trap/warcry/totem subsystems) — needs
  in-game verification. Audit skills/supports/modifiers for correct exclusive tags in stat_meta.
- **Audit empty-tag stats** that ride the generic pools (like the combo_starter_cast typo) — confirm each is
  genuinely generic vs missing a scope/exclusive tag.

## 3. Skill modeling / contributions
- **Hook up ALL standard talent nodes** + model more skills (goal: a playable build accurate into the millions
  of DPS). Order: conversions → standard nodes → non-active-skill contributions.
- **Core-talent conversion lines** → then the general damage-type conversion system (all conversions currently
  tracked-NYI). Owner to explain each conversion line.
- **Non-main-skill damage contributions**: passive/active non-main skills contribute damage; auras/empower/
  curses (the reservation engine they depend on now exists).
- **Skill viewer deep modeling**: per-skill empower/duration/cooldown, reservation/aura/AoE, per-skill
  mechanics; cross-skill buff DPS with damage-skill marking.
- **Skill list audit**: prune active/passive catalogs (minion + out-of-game skills appearing).
- **Fervor gating**: add a "Have Fervor" source; gate base Fervor application instead of unconditional.

## 4. Data / crawler / import
- **Crawler & import rework** (DB scraper): reimport + schema rework across importers/backend.
- **Master glossary expansion**: keep data/master_glossary.json in sync; expand Help DB glossary terms.
- **Revisit ~22 unmapped support DPS lines** (ailment/DoT, Tendonslicer, Projectile Penetration) with
  conditions active + autoderive/canvas resolvers.

## 5. UI / screens
- **★ Engine↔frontend display-fidelity audit (NEW initiative).** There are disconnects between how the engine
  computes and how the frontend displays — the Stats screen / skill selector should eventually mirror the backend
  math EXACTLY so the numbers are auditable line-by-line. First instance found + fixed 2026-06-17: the Skill Hit
  Damage breakdown computed per-form / per-type DPS from `hit_forms[].dps_vs_target` (which excludes the
  `cast_multiplier`) but compared it against `total_dps_vs_target` (which includes it), so "% of Total" and "Type
  Contribution" both read `1/cast_multiplier` (e.g. 56% for a pure-lightning Chain Lightning with the Merge+Web
  same-target shotgun). Fixed by applying `cast_multiplier` in the breakdown + surfacing the shotgun multiplier.
  TODO: sweep the whole offense/defense/derive → display path for similar mismatches (multipliers applied to totals
  but not to the per-line breakdown, proportional-attribution rounding, anything the UI recomputes instead of
  reading from the engine). Goal: the engine emits the breakdown, the frontend just renders it.
- **Landing/main screen — add a Discord feedback link**: revisit the app's main screen/landing page (BuildSelectScreen)
  so it contains a direct, visible link to the community Discord for feedback/bug reports/sharing. Pairs with the
  existing About modal's about.tlibuilder.com link; consider a small footer/header social row (Discord + site).
- **BUG (open): skill-slot search menus unresponsive** — owner reports the skill-slot search/picker stops responding
  entirely, possibly after deleting a build (trigger unconfirmed). Investigate stale state / dangling overlay or
  unreset picker state on build delete. See `.wolf/buglog.json` (bug-skill-slot-search-unresponsive).
- **Per-slot/Berserking frontend toggle UI** (backend done; enable/disable primitive exists).
- **Conditionals screen revamp**: category-style titled-card panels (match the Stats screen); merge Calc into
  Conditionals → rename "Config".
- **Roll tier tooltips** (T1/T2/…) on gear + hero-memory tooltips (hero-memory has `tier`; gear needs plumbing).
- **Deprecated StatsScreen.tsx** (debug dump) — remove or fold; real screen is PlayerStatsScreen.tsx.
- **Source tagging**: add a tag/type column to Player Stats source attribution.
- **Settings overlay follow-ups**: wire the greyed number-separator + decimal-precision controls; theme/accent;
  move "Show NYI flags" here; build defaults (default level / dummy level); restore-last-build; Open data folder /
  Reset settings / Reset app data.

## 6. Stats engine v2 (open items)
- Source coloring (crafted gear by rarity #mods, talents by tree branch); hero-memory base values by rarity
  (owner has hand-gathered data); per-weapon dual-wield crit/damage display; verify Numbed×Grudge/Infiltration
  stacking; offense/hit revamp (skill-specific section, projectiles).
- **Stats-screen offense rework — separate the "delivery multiplier" breakdowns.** The Skill Hit Damage area folds
  the same-target shotgun (`cast_multiplier`) and the Tangle attached-count into the DPS as flat multipliers shown
  only as small inline annotations. Rework the offense display so these "how the hit is delivered N times" multipliers
  (shotgun hits, tangle count, future per-cast/trigger mechanics) get their own clearly-separated breakdown area
  distinct from the per-hit damage breakdown (base × increased × additional × crit). Pairs with the engine↔frontend
  display-fidelity audit (§5).

## 7. Infra / hosting
- **Web-hosted version — SHIPPED** (see the top of this doc). Open follow-ups: redeploy automation (currently
  manual `wrangler`/drag-drop of `dist-web/` + `web-data/`); revisit the optional pure-compute extraction below if
  web init time/payload ever becomes a problem.
- **Package size** (deferred): ~280–310 MB; levers filed (gzip data −16 MB, trim PyInstaller −20 MB).
- **Refactor the `server.py` monolith** (~3300 lines): split into focused modules (affix/line parsing, line→stat
  matcher tables, endpoints, request models) with a **single source of truth for line→stat mapping** so duplicate
  parsers can't drift — the `max_curse_flat` vs `max_curses_flat` split (two parsers, same concept, two keys) was
  exactly this class of bug.
- **Aggressively cache parsed lines** to cut recompute latency (the lag between editing a build and seeing updated
  damage). `parse_mod` / `_parse_custom_mod_text` re-runs over every line each recompute; memoize by line text (the
  mapping is pure given the text) so repeated lines across gear/talents/supports + successive recomputes are
  near-free. Pairs with the build-hash result-cache idea.
- **Web compute: extract a pure `compute_stat_sheet(dict)->dict`** (future optimization). The web build runs the
  engine in Pyodide by reusing the whole backend (`import server`) with bundled fastapi/pydantic wheels (Path B,
  chosen for low risk). Extracting the orchestration + helper closure out of the 3242-line `server.py` into a
  fastapi-free module would shave ~2 MB (cached) + ~1 s one-time init off the web worker. Only worth it if web
  init/payload becomes a problem.
