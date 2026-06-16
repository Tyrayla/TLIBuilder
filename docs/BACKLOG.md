# TLI Builder — Outstanding Backlog

Grouped by area. Pruned 2026-06-16 after the 0.5.2 release.

## Shipped in 0.5.2 (removed from the open list)
Mana/Life sealing & reservation (incl. Lunar Eclipse) · auras & Focus as build buffs · nightly channel + silent
auto-update + Settings overlay · full skill-data reimport · display rounding option A (sealed/unsealed + ES match
in-game) · slate inventory + Add-to-Inventory + right-click delete/remove + consolidated bonus view (SlateOverview)
· structured level-aware skill/support tooltips · update-banner no longer pushes the footer off-screen · Dreamweaver
spirit working after the reimport.

**Dropped (decided against):** global display truncation (option B) and the 1-life reservation floor.

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

## 7. Infra / hosting
- **Web-hosted version**: host web + desktop simultaneously — needs a doc on reducing hosted-Python load +
  minimizing backend↔frontend chatter (cache by build hash, client-side derivations) + an audit of auth,
  storage, CORS, cost. *(Assessment in progress — see docs/ web-hosting notes.)*
- **Package size** (deferred): ~280–310 MB; levers filed (gzip data −16 MB, trim PyInstaller −20 MB).
