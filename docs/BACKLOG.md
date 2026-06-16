# TLI Builder — Outstanding Backlog

Compiled 2026-06-15 (end of the auras/badge session). Grouped by area; the first sections are the freshest
follow-ups, the later sections are standing items pulled from project memory.

## Next session (owner-set order)
1. **Full re-import of all skill types** from the clean recrawl, with the support-line dedup step + tooltip
   verification (§5).
2. **Phase 2 reservation / sealing** (§3).
3. **Nightly release system** via the staging branch + **improve auto-update** — research alternatives to the
   current Windows updater tool (§8).

## 1. Auras / buffs (direct follow-ups from this session)
- **Verify the 7 aura review items in-game** (panel "Needs manual review"): Domain Expansion + Precise: Domain
  Expansion (area/ailment additional — Lv1 anchor unparseable, using flat Lv20; confirm Lv1 split), Fearless +
  Precise: Fearless (melee crit Lv1 anchor matched by stat only), Precise: Elemental Resistance (avoid-ailment
  flat Lv20). Fix the underlying simple-description data or accept flat.
- **Focus skills (Phase 1b)**: model Focus mechanics deferred this pass — Focus Pts, triggers, True Damage,
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
- **Audit empty-tag stats** that ride the generic pools (like the combo_starter_cast typo found this session)
  — confirm each is genuinely generic vs missing a scope/exclusive tag.

## 3. Reservation / sealing — Phase 2 (plan: docs/what-do-we-need-glimmering-acorn.md)
- Stat keys: `sealed_mana_compensation` (global + per-skill-class), `mana_multiplier`, `sealed_life_conversion`.
- Reservation math: `initial_seal = base_seal × Π(support mana_multiplier)`, `actual = initial/(1+compensation)`,
  sealed-life conversion (≥100% rule), `available_mana = max_mana − Σ sealed`, insufficient-mana flag.
- Support `mana_cost` field = Mana Multiplier % (110/100/250). **Off the Beaten Track**: +4 support level +
  fix support mana multiplier to 95%.
- UI: DefenseResult `reserved_mana`/`available_mana`/`sealed_life`/`sealed_mana_compensation`; Mana panel +
  the SkillFoundationPanel "Reservation (Sealing)" row; insufficient-mana warning.

## 4. Skill modeling / contributions
- **Non-main-skill damage contributions**: passive/active non-main skills contribute damage; auras/empower/
  curses (roadmap). Skills that seal Life/Mana apply reservation (needs the engine above).
- **Core-talent conversion lines** → then the general damage-type conversion system (all conversions currently
  tracked-NYI). Owner to explain each conversion line.
- **Hook up ALL standard talent nodes** + model more skills (goal: a playable build accurate into the millions
  of DPS). Next-session order: conversions → standard nodes → non-active-skill contributions.
- **Skill viewer deep modeling**: per-skill empower/duration/cooldown, reservation/aura/AoE, per-skill
  mechanics; cross-skill buff DPS with damage-skill marking.
- **Skill list audit**: prune active/passive catalogs (minion + out-of-game skills appearing).
- **Absorb / Reservation engine** (stubbed NYI) — overlaps §3.
- **Fervor gating**: add a "Have Fervor" source; gate base Fervor application instead of unconditional.

## 5. Data / crawler / import
- **Full re-import of all skill types** from the clean recrawl (only passives imported so far). Supports come
  back with DUPLICATED effect lines — add a dedup step, then verify support tooltips don't break.
- **Crawler & import rework** (DB scraper): reimport + schema rework across importers/backend.
- **Dreamweaver spirit** (paused): pending crawler data rework (merged modifier lines; ~75 spirits affected).
- **Master glossary expansion**: keep data/master_glossary.json in sync; expand Help DB glossary terms.
- **Revisit ~22 unmapped support DPS lines** (ailment/DoT, Tendonslicer, Projectile Penetration) with
  conditions active + autoderive/canvas resolvers.

## 6. UI / screens
- **Per-slot/Berserking frontend toggle UI** (backend done; enable/disable primitive exists).
- **Conditionals screen revamp**: category-style titled-card panels (match the Stats screen); merge Calc into
  Conditionals → rename "Config".
- **Slate Board**: saved-slates inventory (like Gear) + a consolidated view summing every placed slate's lines.
- **Roll tier tooltips** (T1/T2/…) on gear + hero-memory tooltips (hero-memory has `tier`; gear needs plumbing).
- **Skill tooltips**: level/tier data, support DPS-delta preview, user-set exact rolls within a tier; declutter
  (too dense — focus shown info).
- **Deprecated StatsScreen.tsx** (debug dump) — remove or fold; real screen is PlayerStatsScreen.tsx.
- **Source tagging**: add a tag/type column to Player Stats source attribution.

## 7. Stats engine v2 (open items)
- Source coloring (crafted gear by rarity #mods, talents by tree branch); hero-memory base values by rarity
  (owner has hand-gathered data); per-weapon dual-wield crit/damage display; verify Numbed×Grudge/Infiltration
  stacking; offense/hit revamp (skill-specific section, projectiles).

## 8. Infra / release / hosting
- **Release process**: beta/nightly channel off a staging GitHub + weekly main releases; investigate
  auto-update without the Windows installer step.
- **Web-hosted version**: host web + desktop simultaneously — needs a doc on reducing hosted-Python load +
  minimizing backend↔frontend chatter (cache by build hash, client-side derivations) + an audit of auth,
  storage, CORS, cost.
- **Package size** (deferred): ~280–310 MB; levers filed (gzip data −16 MB, trim PyInstaller −20 MB).

## Display rounding (in-game matching)
- **Global display truncation (option B)** — the game appears to *truncate* every displayed decimal (verified:
  Energy Shield 78.81 → 78; an earlier value 287.64 → 287). We currently apply this only to the **reservation
  pools + Energy Shield** on PlayerStatsScreen (option A: Unsealed = `floor(Max − Sealed)`, Sealed = `Max −
  Unsealed` so they sum to Max and round against the player; ES `floor`ed). Revisit whether to switch the whole
  app's number formatting (`fmtNum`, percents, DPS) to truncate to match the game everywhere — bigger change,
  needs goldens/tests re-checked. Confirm the game truncates other stat types first (DPS, %, attributes).
- **1-life floor (unconfirmed)** — the persistent "1 life" seen when fully sealed was traced to a chestpiece
  `+1 Max Life` affix, not necessarily a game floor mechanic. Re-test a full-seal build **without** any flat
  +Max Life gear: if Life stops at exactly 1 (vs hitting 0), add `usable = max(1, Max − Sealed)` (flat, applied
  after all increases/additionals); same question for Mana.

## Sealing follow-ups (found during Phase 2 build)
- **Moon Strike: Lunar Eclipse (Noble)** — special seal mechanic not covered by the core reservation model:
  the support itself seals 10% Max Mana (on an active skill), makes the host cost no mana, and grants
  "+1% additional damage per 100 Mana sealed (up to +57-60%)". Needs a support-sourced seal + a
  damage-per-sealed-mana stat wired into offense. Deferred from the core sealing pass.
