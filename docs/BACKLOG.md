# TLI Builder — Outstanding Backlog

Grouped by area. Pruned 2026-06-16 after the 0.5.2 release and the web launch. Revised 2026-07-10: §4's
"Dropped ungated/conditional support damage lines" entry was audited and found to be largely wrong — see that
entry for the corrected split (5 already wired, 7 re-filed under §3 as blocked on unmodeled host skills, 1
closed-bug note on a run-on-sentence parser bug affecting exactly 1 entity in the field the resolver actually
reads (`progression[].values.name`) — corrected down from an interim "6 entities" count, itself corrected down
from an original "~50").

> **Verification Knowledge Base:** confirmed in-game behavior + modeled-but-untested coverage now lives in
> `data/verification/*.json` (source of truth), rendered to `docs/verification/README.md` and viewable in-app
> via the main-menu **Verification Database** button. The pending test *queue* stays in
> `docs/INGAME_VERIFICATION_BACKLOG.md`. Add/update entries with the `/add-verification` skill.

## ★ NEXT (Tyra, 2026-06-18)
1. **Release TONIGHT** with all the Spell Burst + Tangle + craft-fix work. **Main-menu / landing-page update** so the
   **Discord link** (feedback sharing) is easy to find — do this as part of the release.
2. **Hero Traits** (after the release) — implement **one ENTIRE hero trait at a time (all its nodes)**, not piecemeal.
   (Ingenuity Overload / Creative Genius = Bing2 hero trait — its Spell Burst spike mechanic lands here.)
   - **Selena SS13 — Dance of the Deep: SELECTION-ONLY, tracked (2026-07-12).** Node text transcribed verbatim into
     `data/seasons/SS13/_hero_traits.json` (`trait_id: dance_of_the_deep`, root at level 15; adjacency-gated tree,
     one allocation point per socketed Hero Memory at levels 45/60/75) so the tree is browsable/selectable, but
     **no DPS/mechanic effect is modeled** — no `hero_traits/dance_of_the_deep.py` module exists yet. Too many
     interlocking unknown mechanics (Crimson Tide, Dance Step / Eternal Sleep, Crimson Shade summons, Ominous
     Curse, Terra Charge, Catalyst: Ground) to model reliably from owner-supplied pre-launch screenshots alone —
     SS13 isn't on tlidb yet (season launches ~2026-07-16). Model once real in-game/tlidb data exists. See
     `data/verification/dance-of-the-deep.json` (status `unverified`).

## Optimization options (audit 2026-06-26)
Perf pain was orchestration, not the engine (a single compute is ~0.03s). Catalog damage-delta storm already
fixed (defer-behind-headline + `/api/engine/stats-batch`, commit 7c1fd09). Tiers below from a read-only audit.

**Tier A — quick wins (DONE 2026-06-26):**
- ✅ Backend per-request caching — `load_filter()` (520 KB, reparsed every compute) + season trees now cached per
  season (`server.py _cached_filter`, `season_manager._season_trees_cache`). Batch of 30 builds 1.18s → 0.33s (3.6×).
- ✅ Dedup damage-type constants — FE `src/renderer/src/utils/damageTypes.ts`, BE `backend/engine/constants.py`
  (`DAMAGE_TYPES`, `ELEMENTAL`=fcl, `NON_PHYSICAL`=fcle). Behavior-neutral.
- ✅ Dropped lodash-es (inline `deepEqual`/`debounce` in `src/renderer/src/utils/fn.ts`).
- ⏸ STRETCH (deferred): cache `resolve_nodes` by `(slots,slates,prisms)` hash — re-resolved identically across a
  delta batch. Marginal for typical small trees; revisit if big-tree delta batches feel slow.
- ⚠ FLAG to Tyra: several engine sites name a `{fire,cold,lightning,erosion}` set "elemental" (now `NON_PHYSICAL`).
  TLI "Elemental" excludes Erosion — confirm whether those erosion-inclusive uses are intentional or a latent bug.

**Tier B — web responsiveness (NEXT):**
- Visible-only catalog deltas — compute only on-screen catalog rows (passive/support **and** gear/spirit), more on
  scroll. Attacks the web compute-floor (75 Pyodide builds). Needs viewport tracking on the catalog lists.
- Lean `/engine/stats-batch` response — offense + a damage fingerprint instead of full stat maps (`sources` ×75 is
  the big worker-transfer cost on web). Pairs with visible-only.
- Catalog virtualization — active-skill catalog renders up to ~700 DOM rows (no windowing); gear catalog similar.

**Tier C — big web projects (LATER):**
- Cache Pyodide runtime + engine-data bundle in IndexedDB — web cold-load is ~2-5s every visit → near-instant.
- Port build-code encode (`backend/build_code.py`) to TypeScript — skip the backend round-trip on export/save.

**Tier D — polish (LATER):**
- Lazy-load heavy screens (React.lazy) + keep any dev-only screen out of the prod bundle.
- Debounce IndexedDB persist writes (web) — smoother rapid edits.
- Minor render memoization (BreakdownCtx value object, `TreeNode` `React.memo`, MasonryGrid measure deps) — low
  priority (Calcs breakdowns are already lazy/hover-only).

## Tooling / release — "What's New" changelog modal (low priority)
The update "What's New in <version>" modal has two issues (seen on 0.5.3-nightly.3; not urgent):
1. **Raw HTML shown as text** — the body renders `<p>…</p>` / `<br />` literally instead of as formatted lines
   (changelog HTML is being escaped/displayed verbatim, not rendered).
2. **Unhelpful auto-generated content** — it pulls raw git commit messages, including merge commits with conflict
   markers (e.g. "Merge dev into main for release 0.5.2 / # Conflicts: CHANGELOG.md package.json src/main/index.ts").
   Should show curated release notes (or at least filter out merge/conflict noise).
Fix: render the changelog as HTML (or convert to plain text) and source it from a curated CHANGELOG section per
release rather than raw commit subjects.

## Shipped in 0.5.2 (removed from the open list)
Mana/Life sealing & reservation (incl. Lunar Eclipse) · auras & Focus as build buffs · nightly channel + silent
auto-update + Settings overlay · full skill-data reimport · display rounding option A (sealed/unsealed + ES match
in-game) · slate inventory + Add-to-Inventory + right-click delete/remove + consolidated bonus view (SlateOverview)
· structured level-aware skill/support tooltips · update-banner no longer pushes the footer off-screen · Dreamweaver
spirit working after the reimport.

## Shipped — Web-hosted version (2026-06-16)
TLI Builder runs in the browser at **tlibuilder.com** (Cloudflare Pages app + `tlibuilder-data` Pages project for
catalogs/icons/engine-data; info page at **about.tlibuilder.com** off the `gh-pages` branch). The pure-Python engine
runs in a Pyodide Web Worker (Path B: `import server`; fastapi/pydantic wheels are micropip-installed at init, not
vendored); catalogs/icons load from
the data CDN. Builds + last-session save persist client-side via **main-thread IndexedDB** (the worker snapshots
`/persist` and the main thread owns storage; in-worker IDBFS was unreliable in Brave). Verified in Chrome/Edge/Brave.
Merged to `dev`. Cloudflare Web Analytics enabled. **Remaining (optional):** see §7.

**Dropped (decided against):** global display truncation (option B) and the 1-life reservation floor.

## 0d. Spell Burst + global 30/s tick model (core shipped 2026-06-18 — follow-ups)
Shipped: the **Spell Burst** spell mechanic + the **server-tickrate model**. An eligible Spell (no cooldown, not
channeled/sentry/combo/triggered) bursts inherently once **Max Spell Burst (M) ≥ 1**; an enabler support (Raging
Storm / Wax and Wane / Psychic Burst) grants it to otherwise-ineligible skills. At full charge a cast consumes all M
stacks and auto-recasts the spell M times — the triggering cast also counts, so **casts/burst = M + 1** (no damage
cap, every stack is a full cast). Folded into `total_dps` as the final `spell_burst_mult` (mirrors `cast_multiplier` /
`tangle_mult`). Engine: `offense.calculate_offense(spell_burst=…)` adds the `"spell_burst"` mod tag (so
`spell_burst_hit_dmg_additional` applies only to burst casts); `compute._offense_for_slot` detects eligibility + sizes
M. Conditions: `spell_burst_active` (default on — off → normal-cast DPS) and `spell_burst_auto_trigger` (instant at
full charge vs cast-gated — this IS the burst/combined toggle).
- **Combined manual model (Tyra 2026-06-18).** **Manual** triggering = the player keeps casting between bursts →
  `total = burst casts (M+1 per proc, with the spell_burst pool) + the normal casts in between (no pool)`. The two are
  surfaced distinctly (`spell_burst_dps` / `non_spell_burst_dps`, both vs-target too) and shown under the DPS total as
  "Spell Burst: X / Non Spell Burst: Y". **Auto-trigger** (Solid River / Burst Activation) = burst-only (no manual
  casting → `non_spell_burst_dps = 0`); turning auto on is the toggle that drops the between-burst casts.
  `spell_burst_mult = (burst casts + normal casts ÷ sb_pool_factor) ÷ aps`, so the breakdown table still reconciles
  with a single scalar. (Auto pure-burst = `(M+1)·bursts/sec ÷ aps`.)
- **Tick model — `engine/tick.py` (30 Hz, Tyra-confirmed cap, NOT 31).** Two regimes: (1) **smooth + hard cap** —
  the default for player rates; `cap_rate(raw)=min(raw,30)` is applied per-caster to `aps` in offense (rarely binds).
  (2) **hard-rounded breakpoints** — `period_ticks(s)=ceil(s×30)` + `rate_from_ticks(n)=30/n`, an **explicit,
  manually-approved per-mechanism opt-in**. Spell Burst charge is the FIRST opted-in user (its charge is a server-timed
  whole-tick countdown → charge-speed dead zones between integer ticks).
- **Charge:** `T = 2 s ÷ (1 + Σ charge_speed_inc) ÷ Π(1 + charge_speed_additional)`; Play Safe feeds Cast Speed into
  those pools (aggregator, already shipped). **Surging Inspiration** = alternative fill `T_eff = min(T, M / surging_rate)`
  where `surging_rate = aps × spell_burst_chance_gain_stacks_flat` (expected stacks/cast) — **shape flagged for in-game
  verify**. Auto bursts/sec = `30 / charge_ticks`; manual waits for the next cast at/after the charge tick (cast-cadence
  aligned, the Scenario-C ~50% trap when cast≈charge).
- **Per-support ramped burst-damage bonuses (Tyra §7, mid-roll constants — VERIFY):** Heart of Flame (+10.5%/stack
  consumed, ×min(M,6)) and Prairie Fire (+18%/activation, assumed at-cap ×6) are hand-modeled in a registry in
  `compute._offense_for_slot` (`_SPELL_BURST_BONUS_SUPPORTS`); the flat "for skills cast by Spell Burst" lines map via
  `mod_parser`. **Confirm the per-stack/per-activation percentages and whether casts/burst is M or M+1 in-game.**
- **Auto-trigger + charge sources (SHIPPED 2026-06-18, second pass).** Auto-trigger is now **stat-driven** so the mod
  lines badge Consumed: `spell_burst_auto_trigger_flag` (Burst Activation support line, unconditional) and
  `spell_burst_auto_charge_threshold` (Solid River's conditional "Burst Charge Recovery Speed ≥ N% of base" line);
  offense enables auto when the flag is set or `charge_factor ≥ threshold`. **Vorax** works for free (a graft carrying
  either line parses through the same matcher). **Insatiable Greed** (`attack_speed_to_spell_burst_charge`, 1.5):
  aggregator propagates each Attack-Speed source × coeff into the charge-speed pools (like Play Safe). **Solid River
  charge→burst-damage** (`charge_speed_to_spell_burst_hit_dmg` + `_per`/`_cap`): stepwise `floor(charge_inc/per)×bonus`
  capped, into the spell_burst pool. **Squiddle/Squidnova**: `has_squidnova` condition auto-enables when Squiddle is
  equipped (`has_squidnova_flag`); gated "+Spell Damage" + rank-6 "+1 Max Spell Burst" apply.
  - **SHIPPED — general named-buff ("Gains <buff>") gear expansion.** A "Gains <NamedBuff>" affix (`affix_kind:"special"`,
    e.g. "Seals 10% Max Mana. Gains Insatiable Greed") is dropped by the frontend to `unresolved_texts`; the backend
    gear-unresolved loop (`server.py`) now `_expand_named_buffs` it — splitting compound clauses and substituting the
    glossary description by name (`_GLOSSARY_BY_NAME` from `master_glossary.json`) — then resolves each clause via the
    authoritative parser. So Insatiable Greed's "150% of Attack Speed → Spell Burst Charge Speed" applies straight from
    gear (no custom mod needed), and every other named buff now resolves too (upholds never-silently-drop). NOTE: graft
    (Vorax) special affixes resolve via `_resolve_affix` (not the unresolved channel) — if a Vorax'd named buff needs
    the same treatment, extend the graft path similarly.
  - **DEFERRED — Squidnova Effect scaling.** `squidnova_effect_inc` ("+25/50% Squidnova Effect") is parsed but does not
    yet scale the Squidnova-sourced Spell Damage (within-spirit dependency). Wire + verify the scaling shape.
  - **Ingenuity Overload** = the Bing **Creative Genius** hero trait (resource/spike: +200% one-shot Max Spell Burst +
    Ingenuity Essence, and a "+15% charge speed for 10s" buff) → lands with the **hero-trait** work, not here.
  - **minion Spell Burst** — needs the minion engine.
- **More breakpoint mechanisms reuse `tick.period_ticks` (each MANUALLY opted-in — Tyra approval per mechanism):**
  **minions** (attack-time-in-ticks; Iris2 merged Magus +40% DPS at 7→5 ticks; **Rock Magus Ultimate 6-tick bug** —
  5 & 7 ok, 6 not), **Reap** (server-timed; **900 CDR → 10 Reaps/s** cap), **Wind Rhythm** / auto-triggers
  (ticks-per-proc), **Split Shot — Rapid Advance Canvas ONLY** (channeled-transform; raw APS 15→29 stays flat/worse,
  **30 doubles** — general channeled skills are NOT hard-rounded). Keep them OUT of the opt-in set until confirmed.
- **USE vs CAST gate (deferred, shared with Tangle):** the M auto-recasts are CASTs, not USEs.
- See docs/INGAME_VERIFICATION_BACKLOG.md (SPELLBURST-01) for verification items.

## 0e. CLOSED — DoT damage-scoping + above-max expansion (shipped 2026-07-10)
Tyra confirmed two general mechanics 2026-07-10 (see `data/verification/dot-model.json`'s notes): (1) above-max-
level scaling (`_above_max_mult`) applies to every damage form, DoT included, not just hit; (2) the "X Damage"
(hit+DoT) / "X Damage over Time" (DoT-only) / "Elemental Damage" (fire/cold/lightning, excludes Erosion) scoping
rule. Engine wired both same-day (`backend/engine/offense.py::compute_dot` gained `above_mult` +
`_dot_type_increased_keys`/`_dot_type_additional_keys` — see `.wolf/buglog.json` ids
`dot-above-max-level-scaling-not-applied`, `dot-type-scoped-damage-pools-missing`). **`backend/tests/test_dot.py`
now covers this (36 tests across 11 classes, full backend suite green at 2812 passed)** — the stale-test flip this
entry used to track is done; nothing open here. `spell_dmg_additional` on the DoT additional pool remains
explicitly EXCLUDED (unmeasured, the deliberate conservative default — see `data/verification/dot-model.json`'s
open verification item).

## 0f. Shadow Strike + Thunder Spike (core shipped 2026-07-15 — follow-ups)
Shipped: the **Shadow Strike delivery model** (Help DB `shadow-strike`; master_glossary 136 "Phantom") and the
**Thunder Spike** skill (registered in `skill_resolver._REGISTRY`; previously unregistered skills compute
`total_dps = 0.0`). N Shadows repeat the player's own attack; the falloff coefficient is 70% (first Shadow full
damage, each further Shadow additionally −70%), folded into `total_dps` as a delivery multiplier
`shadow_mult = 1 + (1 + 0.30·(N−1))·(1 + Σ shadow_dmg_additional)`; player hit is independent of the shadow
falloff chain. **This flat (non-compounding) falloff shape is now CONFIRMED** via a dedicated N=3 in-game
measurement (RUN C, 2026-07-15 — flat model matched within 0.3%, a compounding-chain alternative was rejected
by >8%; see `data/verification/shadow-strike.json`). Despised Shadow's "33% chance to gain +3 Shadows" is modeled as a per-cast expected-value mix
(owner-approved 2026-07-15). Thunder Spike itself: 205%→277% WAD Lv1–20, an intrinsic 100% Physical→Lightning
conversion (the first skill-intrinsic conversion in the engine — `ResolvedSkill.intrinsic_convert`), and an
inherent Numbed-on-True-Body-hit (1 stack, interval 1s, wired via a skill-scoped `ConditionEffect` since
`ailment_inflict.scan_numbed_inflict` only scans gear/talent/custom-mod text, not a skill's own tooltip line).
Rumbling Thunder's "+45–48% additional Lightning on True Body hit for 2s" is modeled DEFAULT ON (owner-approved
assumption: continuous casting vs a boss → ~permanent uptime) — needs in-game confirmation. **Numbed-uptime
formula CONFIRMED same day (2026-07-15, later): shadows do NOT apply Thunder Spike's inherent Numbed at all**
(N-independence + direct-proof test, superseding an earlier same-day "shadow-applied source-group" hypothesis —
see the Explicitly NYI list below); the observed 1↔2 alternation is fully explained by the player's own hit
cadence against Numbed's independent-stacking window, `E[stacks](aps) = 2.0·aps / ceil(1.0·aps)`, reconciling
all three RECOUNT runs within 0.25%. **Phase 2 is now IMPLEMENTED** (auto-derived fractional `numbed_stacks`
floor, `backend/engine/compute.py`; verified solo manual +0.23% vs measured 349, zero golden fixture changes,
2 stale tests updated). Line-based Numbed-inflict sources are a separate, distinct mechanism (refresh
semantics via a constant floor, not the inherent's window formula): **High Voltage is CONFIRMED CORRECTLY
MODELED** (its own flat cadence-independent floor already matches the owner's observations); **Numb
Magnificent** and **Everburn Thunderfire** (SS12 legendary girdle — exists in our data) remain open/unmodeled
for Thunder Spike specifically — see below. Full detail: `data/verification/shadow-strike.json`,
`data/verification/thunder-spike.json`; `docs/INGAME_VERIFICATION_BACKLOG.md` SHADOW-01/02.

**Explicitly NYI** (owner decisions 2026-07-15 — listed so they're never silently dropped):
- **Frantic Shadow** "X% chance to gain +Y% Attack Speed for Zs when Shadows hit enemies" and **Numb
  Magnificent** "30% chance to inflict Numbed … when the supported skill's Shadows hit an enemy" — both need
  shadow-hit-count expected-value modeling before they can be wired; this EV model is the shared unlock for
  both proc lines.
- **Tremble Noble** on-crit "+(66–71)% Numbed Effect for 2s" buff — unmodeled.
- **Tracking Area entirely unmodeled**: Thunder Spike's own "100% of Skill Area increase/decrease also applied
  to Shadows' Tracking Area, up to 100%", the dedicated `+% Shadow(s) Tracking Area` stat family, Dual Kismet:
  Ghost Bee ("+50% Shadow Tracking Area +50% Shadow Strike Skill Area"), and Charging Warcry's "+20% Tracking
  Area for Shadow Strike Skills while the skill lasts" — no AoE/targeting model exists to consume any of it.
- **Charging Warcry** "4% additional damage and Ailment Damage per enemy affected" for Shadow Strike skills —
  per-enemy-affected scaling unmodeled.
- **Frost Spike / Double Thrusts** — the other two Shadow Strike skills — remain unregistered in
  `skill_resolver._REGISTRY`; Thunder Spike is the only one live in v1. Detection is tag-driven off the
  "Shadow Strike" skill tag (not hardcoded to `thunder_spike`), so both light up automatically once registered
  — no Shadow-Strike-specific code needed when that happens.
- **Numbed stack-alternation uptime — CONFIRMED FORMULA (2026-07-15, later same day); Phase 2 IMPLEMENTED
  same session.** Owner-measured 2026-07-15: in-game Numbed alternates 1↔2 stacks; the engine models a
  flat 1 stack. Superseding all earlier candidates (shadow-applied source-group, discrete phase-slot,
  interval-alignment — see history below), a later-same-day **N-independence + direct-proof test** established
  that Shadows contribute NOTHING to Thunder Spike's inherent on-hit Numbed line at any tested count (Rhythm
  0.7s at N=2 and N=4 shadows bounced 1↔2 identically to the N=0 solo baseline; positioning the main True Body
  to miss while Shadows — larger Tracking Area — hit produced 0 stacks). The entire 1↔2 alternation is instead
  explained by the player's own hit cadence against Numbed's independent-stacking window: `E[stacks](aps) =
  2.0·aps / ceil(1.0·aps)` (I=1s tooltip interval, D=2s master_glossary 762 default duration — "the duration of
  each stack is calculated independently" corroborates the model). This CONFIRMED formula reconciles all three
  2026-07-15 RECOUNT runs (solo, +Haunt, RUN C N=3 — all same 1.5 APS baseline) within 0.25%, using a single
  shadow-count-independent average instead of the earlier per-run bespoke corrections. **Phase 2 is now
  IMPLEMENTED this same working session**: the formula is auto-derived as the fractional `numbed_stacks` floor
  (replacing the flat-1 default) in `backend/engine/compute.py`. Verified: solo manual ≈1.5 aps → E=1.5 →
  +0.23% vs measured 349; zero golden fixture changes; 2 stale tests updated by testing to match.
- **Shadow-applied inherent Numbed — REFUTED (2026-07-15, later same day), retained here for history.** An
  earlier same-day hypothesis (structure known: 1 sustained stack from the character + at most 1 from the
  shadows/clones collectively, capped at 2, three calibration points N=1 avg ≈1.33 / N=2 avg ≈1.5 / N=4 <2) and
  a subsequent Rhythm-cadence discriminating test that refuted a discrete phase-slot candidate
  (`.wolf/memory.md` 2026-07-15 "Part B re-derivation") in favor of an interval-alignment candidate were BOTH
  superseded the same day by the N-independence + direct-proof test above, which shows Shadows never apply the
  inherent line at all — only the player's own True Body hit does, via the independent-stacking window model.
  Neither the source-group structure nor the interval-alignment candidate should be engine-implemented; both
  are retained in `data/verification/shadow-strike.json` / `thunder-spike.json` for their record of the
  reasoning process. The separate falloff-shape question (flat vs compounding per-shadow damage delivery) is
  unaffected and remains CONFIRMED FLAT via a dedicated N=3 measurement (RUN C, 2026-07-15).
- **Line-based Numbed-inflict sources — two distinct mechanisms, correctly distinguished by engine analysis
  (2026-07-15, later same day).** Owner's explicit caution held: the inherent refutation above does NOT
  generalize to these — they are a genuinely separate mechanism (refresh semantics via a constant floor, not
  the inherent's window formula). **Numb Magnificent**'s "30% chance to inflict Numbed … when the supported
  skill's Shadows hit an enemy" (2026-07-15 sampled stack ranges: 2 shadows 1–6 mode≈4, 4 shadows 1–9 possibly
  10) still needs the same shadow-hit-count EV modeling as Frantic Shadow's Attack Speed proc — remains
  unmodeled. **High Voltage** (`high_voltage`, generic support_skill, "Inflicts Numbed when the supported
  skill deals Hit Lightning Damage", unconditional on-hit) is **CONFIRMED CORRECTLY MODELED**: the engine
  already applies a flat cadence-independent `numbed_stacks` floor of 1 via `support_mapper.py::map_autoderive_line`
  (the `inflicts? numbed` branch, ~line 260, explicitly commented `# High Voltage` — support-skill lines never
  enter `ailment_inflict`'s scan pool, which covers gear/talent/custom/spirit/memory text only), exactly
  matching the owner's observation (shadows-only hits sustain exactly 1 stack, never 2); the cap-at-2 combined
  with the main hit falls out of the existing `max()` ConditionEffect machinery (floors don't sum) — no gap
  here. **Everburn Thunderfire** (`everburn_thunderfire`, SS12 legendary girdle — **exists in our SS12 data**,
  correcting an earlier same-day "likely uncrawled SS13" note): "Inflicts 1 additional stack(s) of Numbed."
  Owner-observed bounce shift to 2↔4 (shadow-independent +2 offset) is strong independent supporting evidence
  for the confirmed window model (a doubled payload per application) — **but is currently NYI for Thunder
  Spike specifically**: `ailment_inflict`'s pattern-C needs a paired inflict trigger in its own scan, and
  Thunder Spike's intrinsic trigger isn't wired into that system, so equipped alone on a Thunder Spike build it
  is silently inert in the engine today. Filed as an explicit NYI/verification item (never silently drop).
  See `data/verification/shadow-strike.json` and `data/verification/thunder-spike.json` notes for full detail.
- **Despised Shadow's proc chance is USE-gated, not CAST-gated (owner-stated, 2026-07-15) — SHIPPED
  same-day.** The "33% chance to gain +N Shadows when using the Shadow Strike skill" line does NOT proc off
  triggered casts (Rhythm/Instruction activation-medium triggers on Thunder Spike are CASTs, not USEs — the
  standard USE-vs-CAST restriction applies). Originally logged as a known model limitation (the per-cast
  expected-value mix applied unconditionally on every cast, overstating DPS for AM-triggered Thunder Spike
  builds equipped with Despised Shadow); **IMPLEMENTED 2026-07-15, same batch**:
  `backend/engine/compute.py` (~1353–1364) zeroes `shadow_chance_pct` whenever the slot is trigger-driven
  (`trigger_interval` or `wind_rhythm_base_cooldown` > 0, the same detection Demolisher already uses),
  leaving `max_shadow_quantity_flat` (flat grants like Haunt/Frantic Shadow) unaffected — manual-use builds
  are unchanged, only AM/Rhythm-triggered slots are gated off. 3 new tests, full suite 3772/0. This was the
  **first measured instance** of the USE/CAST distinction mattering for a modeled mechanic — same deferral
  class as Spell Burst's USE-vs-CAST gate (§0d) and Tangle's (§0c), both still open. See
  `data/verification/shadow-strike.json`.
- **Core Organ slot-page crawl: assessed and declined (owner decision, 2026-07-15).** Considered while
  gathering Despised Shadow / Vorax grafting data for this Shadow Strike work — a dedicated crawl of per-slot
  Core Organ pages (`tlidb-crawler`). Owner declined: crafting costs aren't data the engine uses; the Core
  Organ item itself doesn't matter (only the legendary name it unlocks); multi-slot applicability is already
  captured (e.g. the Vorax chest page already lists all eligible chest/gloves directly). Not re-proposing.

## 0g. Crit-multiplier per-source breakdown (shipped 2026-07-28 — follow-ups)
Shipped (commit `e0c02db`, `team1-live`): the crit-DAMAGE per-mana-consumed term (Tyrant's Iron Fist,
`crit_dmg_inc_per_mana_consumed`) moved from a display-only post-loop fold in `offense.py` into an in-loop
injection into the real `crit_dmg_inc` pool inside `compute.py`'s consumption loop, so it now shows a labeled
breakdown source instead of being folded invisibly into the total. Two follow-ups surfaced during that work,
explicitly out of scope of it:
1. **Consistency, engine-lane — move `crit_rating_inc_per_mana_consumed` in-loop too.** The crit-RATING sibling
   (`offense.py:1583-1588`) is still a post-loop fold — no breakdown source, and it's now the lone post-loop
   holdout among the per-consumed folds. Follow-up: move it in-loop the same way, so it also earns a breakdown
   source. Same pattern as the crit-damage change; will need a filled `.claude/rules/engine-task-spec.md` before
   any code is written.
2. **Pre-existing latent bug, bug-221 class — spell_dmg / mana_regen per-consumed loop doesn't mark `consumed_stats`.**
   The shared spell_dmg / mana_regen per-mana consumption loop in `compute.py` (around line 889) does NOT mark its
   stat keys in `consumed_stats`, so Compensatory Life / mana-regen-per-mana-consumed affixes badge "Inactive" in
   the UI despite actually contributing to the computed stats. Pre-existing, not introduced by and out of scope of
   the crit-multiplier work above. Fix: mark those keys consumed the same way the other per-consumed folds already do.

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

## 0b. RESOLVED — False "Unrecognized (NYI)" / "Inactive" on tooltips & badges
**RESOLVED (Tyra confirmed 2026-06-26).** The tooltip line classifier / badge resolver no longer falsely flags
modeled mechanics (jumps, conversions, etc.) as NYI/Inactive. Kept below for history.

Skill/support tooltips (and possibly other mod badges) flag lines as
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
- **Core-talent line IMPLEMENTATIONS** (the general damage-type conversion system is DONE — shipped 2026-06-11).
  These remaining core-talent lines are mostly NOT conversions — they're **bonus-sharing** (like Gale's
  proj-speed→proj-dmg, already live) or other per-talent mechanics to wire/fix (Arcane/Ward/Joined Force/Rebirth/
  Co-resonance/Rock/True Flame/United Stand), several blocked on subsystems (skill-cost, sealed-mana/reservation,
  regain, EHP). Treat as per-talent implementations, not a conversion effort.
- **Non-main-skill damage contributions**: passive/active non-main skills contribute damage; auras/empower/
  curses (the reservation engine they depend on now exists).
- **Skill viewer deep modeling**: per-skill empower/duration/cooldown, reservation/aura/AoE, per-skill
  mechanics; cross-skill buff DPS with damage-skill marking.
- **Skill list audit**: prune active/passive catalogs (minion + out-of-game skills appearing).
- **Fervor gating**: add a "Have Fervor" source; gate base Fervor application instead of unconditional.
- **Model 6 host skills to unlock their gated support lines (re-filed from §4 2026-07-10, EXPLICIT — do not
  forget).** Each support below carries a conditional / per-stack / per-X "additional damage for the supported
  skill" line that the resolver currently drops as untranslatable — but in every case the real blocker is that
  the HOST skill has no `skill_resolver._REGISTRY` entry at all (`total_dps = 0.0` regardless of the support), so
  fixing the gate alone would produce zero visible change:
  - `inexhaustible_barrage` — **best value**: one host skill unlocks BOTH `inexhaustible_barrage_fatal_pursuit_noble`
    ("+27–29% when using a gun") and `inexhaustible_barrage_landslide_noble` ("−5–−4% when using a cannon"). The
    gun/cannon gate follows the existing manual-boolean precedent of `holding_two_handed` / `holding_one_handed` /
    `dual_wielding` in `data/conditions.json` (category "Equipment") — no weapon-type auto-derivation exists
    anywhere in the engine.
  - `scorching_beam` — **worst value**: needs a full Icebound-Beam-style `ChanneledSpec` (reset behavior, burst +
    continuous forms) built from scratch. Once it exists, `scorching_beam_supercharge_magnificent`'s ("+6–6.4% per
    channeled stack") per-channeled-stack line falls out of the already-existing `IntrinsicAdditional` mechanism
    for free — but a modelling decision on the steady-state/at-cap assumption is needed first.
  - `lightning_shot_crossed_lightning_noble` — "+42–44% when ≥240 Dexterity" (+ per-Dex Chain qty): the gate needs
    a new Dexterity-threshold condition (seed `dexterity_total` in `compute.py` alongside the existing
    `dexterity_ge_strength`, plus `_COND_PATTERNS` entries). Small and reusable catalogue-wide. NOTE: a separate
    run-on-sentence parser bug affecting this support was fixed 2026-07-10 (§4 closed-bug note) — that bug is
    closed; the Dex gate remains open.
  - `blazing_bullet_ignition_point_noble` — "+43–45% when bonus+additional Skill Area ≥ 120%": can reuse the
    `(1+Σinc)·Π(1+add)−1` helper currently private to `skill_effects/berserking_blade.py::emit_rampage`; extract
    it to a shared utility.
  - `path_of_flames` — **being modelled right now** as part of the Damage-over-Time engine work (it is the control
    skill for Mind Control). Once registered, `path_of_flames_raging_boil_noble`'s ("+8–8.5% per Elite passed
    while channeling, stacks 8") gate still needs a novel proximity/trigger subsystem — lowest priority.
  - `focused_shot_aspire_magnificent` — "+7.5–8% per use while 100 Fervor, stacks 6": needs a per-use stacking
    buff with hysteresis (activates at 100 Fervor, deactivates below 50). No precedent in the engine. Cheapest
    approximation if picked up: a manual user-set stack count (0–6), the way `berserking_blade_stacks` works —
    flagged as a simplification, not a full trigger simulation.

## 4. Data / crawler / import
- **Crawler & import rework** — DONE. Scraper built; importer/schema rework complete; data reimported in
  split-line (atomic modifier/slot) format.
- **Crawler-side talent-tree differ upgrade — enable node-level season-diff precision (owner: data-scraper /
  `tlidb-crawler` repo, follow-up, not blocking).** Found while scoping the `season_impact.py` engine-impact mapper
  expansion. The season-diff artifact from `tlidb-crawler/tools/season_diff/` currently diffs talent trees only at
  **whole-tree granularity** — `generic_diff.py::diff_generic_entity` indexes by the top-level
  `entity:talent_tree:{name}` uuid (24 trees, one uuid each) and does a positional recursive deep-diff producing
  `field_changes: [{path, before, after, status}]` with paths like `$.nodes[3].effects[0].text`. Individual talent
  nodes do carry their own stable `uuid` locally (e.g. `data/seasons/SS12/warrior.json` `nodes[].uuid`) and effects
  have `pooling_uuid`, but the crawler's generic differ never exposes them — a node reorder shifts every subsequent
  list index, so path-based node identity is unreliable. Consequence: builder-side `season_impact.py` can only
  surface talent-tree impact at whole-tree/text-parse granularity, not per-node. **Ethereal Prism is worse** — it's
  a single singleton entity (`entity:ethereal_prism:ethereal_prism`), so any change makes the whole catalog "reworked"
  with no per-talent identity. Fix: give `talent_tree` a dedicated differ that indexes `nodes[]` by `uuid` and
  `effects[]` by `pooling_uuid` — the way `skill_diff.py` / `gear_diff.py` already do for skills and gear — instead
  of falling through to `generic_diff.py`. Prerequisite for trustworthy node-level engine-impact rows.
- **Master glossary expansion**: keep data/master_glossary.json in sync; expand Help DB glossary terms.
- **Revisit ~22 unmapped support DPS lines** (ailment/DoT, Tendonslicer, Projectile Penetration) with
  conditions active + autoderive/canvas resolvers.
- **Dropped ungated/conditional support damage lines — AUDITED 2026-07-10, most of this entry was WRONG.** The
  previous version of this entry listed twelve supports as "dropped because the resolver can't translate their
  gate." A full audit (driven the real pipeline end-to-end, not read off comments) found that's only true for
  one of them — the rest are either already wired, or blocked on a much bigger hole (an unmodeled host skill)
  than the gate itself. Corrected below so the genuinely-open items aren't silently lost.

  **Already wired — remove from any "dropped" list:**
  - `berserking_blade_desperation_magnificent` — wired via `skill_effects/berserking_blade.py::desperation_contribution`
    (CONTRIB_HOOK), gated on the auto-derived `life_lost_pct` condition (`backend/engine/compute.py:922-929`).
  - `focused_slash_duel_magnificent` — wired through the GENERIC resolver; `server.py`'s `_COND_PATTERNS`
    (`backend/server.py:2133`) already translates "only 1 enemy nearby" → `{"key":"enemies_nearby","op":"==","value":1}`.
    Covered by `test_duel_gates_on_single_enemy`.
  - `split_shot_collaboration_noble` — wired in `skill_effects/split_shot.py::apply_slot_effects` (slot-local,
    per-Projectile-Quantity).
  - `split_shot_rapid_advance_noble` — wired via `IntrinsicAdditional(rating_key="max_channeled_stacks_flat")`
    plus the channel transform.
  - `moon_strike_lunar_eclipse_noble` — wired in `backend/engine/utility.py:462-470` (`apply_reservation` detects
    "mana sealed" + "up to", interpolates the cap by rank via `_seal_dmg_cap`). Measured end-to-end: Moon Strike
    base 2535.59 DPS → 3042.71 DPS with Lunar Eclipse rank 1 and 20000 Max Mana — exactly the +20% predicted from
    2000 sealed Mana. Its source comment and test docstring were stale ("DEFERRED") and have been corrected too
    (see `.wolf/buglog.json` id `docs-moon-strike-lunar-eclipse-stale-deferred-claim`).

  **The remaining seven are NOT blocked on their gate — their HOST SKILL is unmodeled.** Six host skills have no
  `skill_resolver._REGISTRY` entry and compute `total_dps = 0.0` regardless of any support attached:
  `blazing_bullet`, `focused_shot`, `inexhaustible_barrage`, `lightning_shot`, `path_of_flames`, `scorching_beam`.
  The untranslatable support gate is downstream of that much larger hole — fixing the gates first would produce
  zero visible change. **Re-filed under §3 "Skill modeling / contributions"** (the "model more skills" bullet;
  do not re-add them here) with the verbatim in-game line text preserved so they aren't silently lost.

  **Closed bug (2026-07-10):** `lightning_shot_crossed_lightning_noble`'s progression line in
  `data/seasons/SS12/_skills.json` is a run-on of two sentences with no separator ("...stacking up to 6 time(s)
  When having at least 240 Dexterity, +(42–44)% additional damage..."). `_split_condition` matched "for every"
  *inside* the first clause, so `cond_part` swallowed the entire second sentence and the untranslatable compound
  zeroed the whole line — silently destroying the `+1 Chain Lightning Quantity` grant as well as the damage clause.
  Fixed in `backend/engine/support_resolver.py` (`_RUNON_SENTENCE_RE`, line 117, splits sentences before
  condition-splitting), with a regression test in `backend/tests/test_crossed_lightning_runon.py`. **Correction
  2026-07-10:** the "6 entities" figure above was itself wrong — it came from a text scan across the whole skill
  entry, not the field the code reads. `_RUNON_SENTENCE_RE` (`support_resolver.py:300`) is applied only to
  `full_line`, read from `progression[].values.name` — and in that field, across all of SS12, exactly **one**
  entity carries the glue pattern: `lightning_shot_crossed_lightning_noble` (3 tiers, `_skills.json:62610, 62616,
  62622`). The other five previously listed (`ice_shot_ice_blast_magnificent`, `shockwave_warcry`,
  `summon_erosion_magus`, `summon_fire_magus`, `summon_spider_tank_focus_fire_noble`) contain "time(s)" in
  `raw_text` / `description_lines` only — fields this code path never reads — and are unaffected by it.
  Crossed Lightning's host skill `lightning_shot` is not in `skill_resolver._REGISTRY` (see `.wolf/buglog.json`
  id `bug-crossed-lightning-runon-progression-line-drops-quantity-grant`), so this fix changes no DPS today.

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
  - **Second instance flagged (2026-07-15, engine agent, during Shadow Strike/Thunder Spike verification):**
    `OffenseResult.total_dps` already includes enemy-vulnerability effects (e.g. Numbed) in its computation, while
    only armor/resist mitigation is deferred to the separate `total_dps_vs_target` field — a field-semantics
    ambiguity (does "vs target" mean "with target mitigation" or "with all target-dependent effects"?) worth
    picking up as part of this audit. Not yet triaged for a specific display bug; flagged so it isn't lost.
- **Landing/main screen — add a Discord feedback link**: revisit the app's main screen/landing page (BuildSelectScreen)
  so it contains a direct, visible link to the community Discord for feedback/bug reports/sharing. Pairs with the
  existing About modal's about.tlibuilder.com link; consider a small footer/header social row (Discord + site).
- **BUG (open): skill-slot search menus unresponsive** — Tyra reports the skill-slot search/picker stops responding
  entirely, possibly after deleting a build (trigger unconfirmed). Investigate stale state / dangling overlay or
  unreset picker state on build delete. See `.wolf/buglog.json` (bug-skill-slot-search-unresponsive).
- **Per-slot/Berserking frontend toggle UI** (backend done; enable/disable primitive exists).
- **Conditionals screen revamp**: category-style titled-card panels (match the Stats screen); merge Calc into
  Conditionals → rename "Config".
- **Roll tier tooltips** (T1/T2/…) on gear + hero-memory tooltips — DONE (`affixTypeLabel(type, tier)`).
- **Slate inventory + summed-bonus overview** — DONE (shipped 2026-06-15; SlateOverview + saved-slates panel).
- **Deprecated StatsScreen.tsx** (debug dump) — remove or fold; real screen is PlayerStatsScreen.tsx.
- **Source tagging**: add a tag/type column to Player Stats source attribution.
- **Settings overlay follow-ups**: wire the greyed number-separator + decimal-precision controls; theme/accent;
  move "Show NYI flags" here; build defaults (default level / dummy level); restore-last-build; Open data folder /
  Reset settings / Reset app data.
- **Deferred test coverage — BuildSelectScreen folder feature.** Component-level coverage for the stateful DnD/CRUD
  handlers: `reorderBuilds`, `reorderFolders`, `nestFolder`, `assignBuildToFolder`, `handleDeleteFolderConfirm`
  (reparenting/pruning), `handleDeleteSelected` (partial-failure reconciliation), `handleMoveSelectedTo`,
  `persistManifest` (PUT-failure recovery), and App.tsx's `assignNewBuildToFolder`. Approach: extract pure
  state-transition pieces into exported helpers (mirroring `sortBuilds`/`sortFolders`) for unit tests, or RTL
  flows. Deferred from the 2026-07-15 review council (correctness reviewer flagged; pure helpers are covered,
  handlers are not).
- **Deferred test coverage — TreeViewerScreen.tsx preview-guard sites.** 5 `previewMode` store-mutation guard sites
  (`if (!previewMode)` gating `updateSlotNodeStates`/`updateSlotCoreTalentSelections`); only 2 are covered by a
  behavioral test (the node-allocate interaction path, `src/renderer/src/__tests__/App.previewWiring.test.tsx`).
  The other 3 remain untested: `handleReset`, `handleCoreTalentSelect`, and the prism-overlay `onUpdatePlaced`
  re-validation path. Accepted gap, not urgent — the 2 tested sites cover the primary/most-traveled interaction —
  tracked so it isn't forgotten (2026-07-31).
- **SlateScreen.tsx — shared lookup-helper cleanup (crash-fix review, 2026-08-02).** The 2026-08-02 crash fix added
  ~13 individual guard sites across 4 lookup tables (`LEGENDARY_META`, `LEGENDARY_ORIENTATIONS`, `SLOT_CONFIG`,
  `MOTH_DELTA`) — each call site does its own `?? fallback`. A shared helper (e.g. `legendaryMeta(kind)` /
  `orientationsFor(kind)` style lookup functions) would read cleaner than the current inline repetition.
  Readability cleanup, not urgent.
- **SlateScreen.tsx — `handleRotate` divide-by-zero site is currently unreachable, but undocumented (crash-fix
  review, 2026-08-02).** `handleRotate` does `(creator.orientationIndex + 1) % getOrientationCount(creator.kind)`,
  and `getOrientationCount()` now returns `0` for an unrecognized kind (part of the same crash fix) — a `%0` would
  produce `NaN`. Currently unreachable because the Rotate button is gated on `count > 1`, so this can't be hit with
  the present UI. Worth a defensive comment at the `%` site noting that invariant, or a regression test, so a
  future refactor that changes the gating condition doesn't silently reopen the NaN path.

## 6. Stats engine v2 (open items)
- Source coloring (crafted gear by rarity #mods, talents by tree branch); hero-memory base values by rarity
  (Tyra has hand-gathered data); per-weapon dual-wield crit/damage display; verify Numbed×Grudge/Infiltration
  stacking; offense/hit revamp (skill-specific section, projectiles).
- **Stats-screen offense rework — separate the "delivery multiplier" breakdowns.** The Skill Hit Damage area folds
  the same-target shotgun (`cast_multiplier`) and the Tangle attached-count into the DPS as flat multipliers shown
  only as small inline annotations. Rework the offense display so these "how the hit is delivered N times" multipliers
  (shotgun hits, tangle count, future per-cast/trigger mechanics) get their own clearly-separated breakdown area
  distinct from the per-hit damage breakdown (base × increased × additional × crit). Pairs with the engine↔frontend
  display-fidelity audit (§5).
- **Rebuild DoT type-key derivation from `STAT_META`, not string-building (non-blocking, design-consistency).**
  `backend/engine/offense.py`'s `_dot_type_increased_keys`/`_dot_type_additional_keys` build stat-key STRINGS
  (`f"{dtype}_dmg_inc"`, etc.) and only check they exist in `_ALL_STAT_KEYS`, rather than filtering `STAT_META` on
  `pipeline_stage` + `"dot" in affects` the way the hit stage's `_HIT_INC_STATS` does. Correct for all 5 damage
  types today (the naming convention happens to line up with the metadata), but a future `"dot"`-tagged stat that
  doesn't follow the `{type}_dmg_inc`/`{type}_dot_dmg_inc` naming pattern would be silently missed — the same
  "invisible drift" class of bug the codebase generally guards against. Rebuild the derivation from a `STAT_META`
  filter mirroring the hit stage, reusing `_applies_to_dtype`, so a new stat is picked up (or correctly excluded)
  by its declared metadata instead of by name-matching. Latent risk only — no known incorrect behavior today for
  the next DoT type (cold/lightning/physical) that ships.

## 8. DPS-coverage audit (`backend/engine/coverage.py`) — known limitations (owner-approved, 2026-07-12)
The build-independent "is this entity DPS-modeled" roll-up (Axis A: skill/trait/gear `'full'`/`'partial'`/`'none'`,
distinct from Axis B's per-build `consumed_stats`) shipped 2026-07-12. These are tracked-not-fixed decisions made
while building it — see `data/verification` cross-links below where the item touches a modeled mechanic.
1. **Coverage inherits display-tooltip line-suppression (systemic).** `coverage.py`'s `_reduce_tooltip_lines`
   derives "modeled" from the display tooltip's per-line `badge_text`/`coverage` fields, which intentionally
   suppress/blank lines in several places (guarded supports, activation mediums) for legitimate display reasons.
   That suppression can hide a genuinely-unmodeled mechanic from the coverage audit, risking a `'full'` overclaim.
   A coverage-local carve-out was added for activation mediums (see `data/verification/activation-mediums.json`)
   so this particular case doesn't currently misfire, but the robust fix is for coverage to derive `'full'` from
   a POSITIVE per-line wiring signal rather than trusting the tooltip's suppression. This is the reason a few edge
   cases needed targeted carve-outs instead of a single general rule.
2. **`support_mapper._strip_support_target` truncates glued clauses in the LIVE engine — real, pre-existing DPS
   bug, not just a coverage artifact.** Its regex `r'...for/of the supported skill\b.*$'` consumes to end-of-
   string at the FIRST match, so on any support whose clauses each independently end in "...the supported skill"
   (e.g. `fragile_resurrection`: `-26% Restoration Duration for the supported skill` followed by `+10% additional
   damage taken during the supported skill's restoration effect`), clauses 2+ are silently dropped from the
   actual DPS/stat computation, not merely from coverage's view of it. `coverage.py` works around this with its
   own clause splitter (`_split_coverage_clauses`, mirroring the truncation boundary) so the AUDIT sees every
   clause independently — but the live engine still only ever applies the first. Needs its own fix + review
   (blast radius: `support_lines._FLAT_SPLIT` calibration, since that splitter's `(?<!skill)` guard is what
   produces the glued blob in the first place). Cross-link: `data/verification/restoration-subsystem.json`
   (notes the Restoration-effect/duration formula this bug sits inside).
3. **`coverage.py`'s `_ALL_ADVANCED_PICKS` is a hand-maintained mirror** of every hero-trait module's advanced-
   pick names (used to probe `trait_coverage` at a maximal, pick-everything state), with no drift-guard test. A
   future hero-trait module that adds a new advanced pick without also updating this tuple would under-probe
   that trait's coverage (a pick-gated warning/NYI branch could go unseen). Add a drift-guard test mirroring
   `test_consumable_universe.py`'s aggregator scan, or derive the tuple programmatically from the hero_traits
   modules instead of hand-copying their literal pick-name lists.
4. **Engine→server layering violation.** `backend/engine/coverage.py` imports resolver helpers
   (`_resolve_affix`, `_affix_stat_keys`, `_resolve_gear_affix_clauses`, `_resolve_skill_line_keys`) FROM
   `backend/server.py` via lazy in-function imports, specifically to dodge a circular import (`server.py` also
   imports `engine.coverage`). Architecturally backwards — engine code shouldn't reach up into the server layer.
   Relocate those resolvers into an engine-level module (or a shared resolver module both `server.py` and
   `coverage.py` import from) so the dependency points the right direction.
5. **`build_gated_status_params` `**kwargs` loophole.** The trait-coverage build-gated-param detector
   (`hero_traits.build_gated_status_params`) uses `inspect.signature` on each trait's `status_lines` and excludes
   `VAR_KEYWORD` params from the "this trait reads build-specific context" check. A future trait module that
   reads build-specific state via `**kw.get('main_skill_tags')` instead of a named parameter would slip past the
   detector undetected, letting `trait_coverage` claim `'full'` for a trait that actually has an unseen build-
   gated warning branch. Add a lint/test guard (e.g. flag any `status_lines` signature that accepts `**kwargs`
   at all, forcing an explicit named-param audit).
6. **RESOLVED 2026-07-12 — Rhythm activation medium per-meter damage rate was hardcoded.**
   `engine/skill_effects/activation_medium.py`'s `apply_slot_effects` `rhythm_move_cap` branch used to always
   compute `dmg_additional = min(0.03 × meters, cap)` — a flat 3%/metre regardless of tier — even though the
   crawled per-tier rate is actually **3% / 3% / 2% / 2%** (Rhythm tiers 0–3; confirmed in
   `data/seasons/SS12/_skills.json`'s `activation_medium_rhythm` progression: "+3% additional damage for every
   1m..." at tiers 0/3, "+2%" at tiers 1/2), so tiers 2–3 overstated the movement-damage bonus by 50% relative
   (3% modeled vs 2% real). **Fixed**: the rate is now parsed per-level from the crawled progression data instead
   of hardcoded, mirroring `WIND_RHYTHM_BASE_COOLDOWN`'s per-tier dict pattern. See
   `data/verification/activation-mediums.json` (status unchanged at `unverified` — this is a data-fidelity
   correction, not a new in-game measurement) and `.wolf/buglog.json` id
   `activation-medium-coverage-always-none-blanked-tooltip`.
7. **Still open — Rhythm/Instruction's "-80% additional damage for manually used Supported Skill" penalty is
   unmodeled.** Confirmed real text on `activation_medium_rhythm` and `activation_medium_instruction` (all tiers,
   `data/seasons/SS12/_skills.json`). The engine's cast-rate/trigger-interval model represents these mediums as
   **100% AM-triggered** (pinned by `test_trigger_interval_overrides_cast_rate_generically`) with no notion of a
   player manually casting the supported skill in between triggers, so there's nothing for this penalty to hook
   into. This is exactly why `activation_medium_rhythm` correctly reads `'partial'` (not `'full'`) coverage — the
   gap is honestly reported, not silently dropped. **Owner decision (2026-07-12): deferred** — safe to assume
   nobody manually casts on this build; revisit far down the line if that assumption changes. (Same open-ended
   deferral class as Spell Burst's USE-vs-CAST gate in §0d, Tangle's in §0c.)
8. **AM coverage now derives from real wiring, not the blanked display tooltip (shipped 2026-07-12).**
   `engine.tooltip.build_tooltip` blanket-clears `badge_text` on every non-universal line for any
   `activation_medium_*` item (by design — AMs are wired through `activation_medium.py`'s roll parser, not the
   generic text→stat resolver), which used to leave `coverage.py`'s `_reduce_tooltip_lines` with zero checkable
   lines per AM item, so **all 28 activation mediums read `'none'` regardless of how well-modeled they actually
   were**. Fixed with a dedicated path, `coverage.py::_am_coverage` (+ `_am_rule_applied_and_consumed`), that
   re-derives each item's real rolls straight from `activation_medium.parse_am_rolls`/`_classify` and checks each
   against `apply_slot_effects`'s own if/elif dispatch (mirrors it exactly, including which `special` branches
   fire regardless of a rule's own `wired` flag). Result across SS12's 28 activation mediums: **7 full, 20
   partial, 1 none**. This is the AM-specific resolution of item 1 above ("coverage inherits display-tooltip
   line-suppression") — cross-reference that entry; the general risk it describes is why AMs needed this
   carve-out in the first place. See `data/verification/activation-mediums.json` (updated same day) and
   `.wolf/buglog.json` id `activation-medium-coverage-always-none-blanked-tooltip`.
9. **New additive field: `resolved_keys` on `/api/legendary-gear` affixes (shipped 2026-07-12).**
   `server._affix_resolved_keys(resolved, raw_text)` exposes the same build-independent stat-key resolution
   `engine.coverage._affix_is_modeled` already used internally (primary `_affix_stat_keys`, falling back to
   `_resolve_gear_affix_clauses` only on total silence), now surfaced per-affix so a **gear-catalog HOVER** (an
   item not equipped in the current build) can badge which affixes the engine actually reads without needing the
   build-scoped `gear_mod_statuses` unresolved set (which only ever covers what's equipped). Wired into every
   affix on both the variants-dict and legacy flat response shapes of `GET /api/legendary-gear`; **not** added to
   the lightweight `/api/legendary-gear-index` (carries no affix data at all). Empty list = unrecognized affix.
   Known asymmetry (same one `_affix_is_modeled` already flags): a curse-infliction clause resolves to no plain
   stat key at all — it feeds `engine.curse_resolver.apply_curses` structurally — so a curse-only affix's
   `resolved_keys` is always `[]` here even though `_affix_is_modeled` treats it as modeled by a documented
   judgment call; don't read an empty `resolved_keys` list as "unmodeled" for those. Renderer consumer:
   `ModifierBadge.tsx`'s `gearStatus` now falls back to `resolved_keys` when a keyless catalog-hover affix isn't
   in the equipped-build unresolved set (`undefined` → unchanged/fail-open behavior for an older backend). See
   `.wolf/buglog.json` ids `legendary-gear-affix-resolved-keys-catalog-hover` and
   `gear-catalog-hover-affix-blank-badge-no-equipped-build-scope`.

## 9. Conditions engine — condition default-fallback fix (2026-07-14, uncommitted) — follow-ups
An engine fix (uncommitted) changed how absent `condition_state` keys resolve: the engine now falls back to
a condition's CATALOG DEFAULT (`data/conditions.json` `default_value`) instead of reading a missing key as
0/False — previously silently dropping modifiers gated on it (e.g. Dreamweaver's on-hit stacking elemental
pen) on existing builds. Every catalog default is now active-by-default whenever its source is present. The
accuracy review surfaced two follow-ups:
1. **`mercury_points` default = 100 is unsourced.** `data/conditions.json`'s `default_value: 100` has no
   supporting entry in `data/master_glossary.json` or the TLI Help Database. Now that absent conditions
   evaluate at their catalog default, 100 is applied by default wherever Mercury Points gates a modifier.
   Needs an in-game verification pass to confirm 100 is the correct default (upper limit / full-uptime
   assumption) before it's trusted as more than a placeholder.
2. **Compounding-defaults effect is undocumented.** With the absent→default fallback, ALL catalog defaults
   (stacking-pen at max, `enemies_nearby=1` single-target, `current_life_pct`/`enemy_life_pct=100`, various
   `_stacks` maxima, etc.) are now simultaneously active by default in a single DPS number. Each individual
   default traces to a source, but no doc addresses the combined baseline assumption. Worth a verification/
   documentation pass so the default-DPS scenario (what's silently assumed with zero Conditions input) is
   explicit somewhere.

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
  engine in Pyodide by reusing the whole backend (`import server`; fastapi/pydantic micropip-installed at init —
  Path B, chosen for low risk; owner decision 2026-08-03: keep fastapi for desktop/web consistency). Shipping-weight
  pass 2026-08-03: backend-py.zip ships a tools/ allowlist only, engine-data.zip skips CDN-catalog-only files, and
  the zip URL carries a ?v= content hash (replaced the cache:'reload' every-visit re-download workaround — do not
  re-add it). Extracting the orchestration + helper closure out of the 3242-line `server.py` into a
  fastapi-free module would shave ~2 MB (cached) + ~1 s one-time init off the web worker. Only worth it if web
  init/payload becomes a problem.
