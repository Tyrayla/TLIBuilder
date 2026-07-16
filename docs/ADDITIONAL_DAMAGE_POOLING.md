# Additional-Damage Pooling — model & rework plan

Status: **design confirmed (verbally), Option A implementation greenlit.** Captures the decisions
from the 2026-06-08 discussion. The core rule — distinct additional affixes **multiply** — is
Tyra-confirmed verbally; an in-game DPS spot-check (§7.1) is still queued for when servers return,
but implementation proceeds now. The immunity tripwire (§6) is the only part shipped so far.

## 1. Source of truth (TLI Help Database, authoritative)

- `Battle Mechanics/Base Mechanics/Damage Related/Damage Calculation.md`:
  > damage = Base Damage × (1 + all damage increase percentages) × (1 + additional damage increase
  > percentage 1) × (1 + additional damage increase percentage 2)...
- `Battle Mechanics/Base Mechanics/Others/Stacks and Multiplication Rules.md`:
  > Unless specially noted, the additional bonuses of the same affix are added together. When the
  > additional bonuses of an affix are multiplied together, the affix will be marked with "multiplies."

So: **increased → one shared pool**; **each additional → its own `×(1+x)` factor**; **same affix
adds, different affixes multiply**; a per-stack affix marked **"(multiplies)"** compounds internally.

## 2. Confirmed model

`damage = base × (1 + Σ increased) × Π[ additional factors ]`, where additional factors are:

- **One `(1 + Σ positive)` factor per affix identity**, tag-scoped. Identical affixes (by
  normalized text) from any sources **add** into that one factor. *(Tyra-confirmed: Gravel +
  Sun-shooter Long Bow, both `+X% additional Projectile Damage`, ADD.)*
- **Negatives are a separate concern from positives** (Tyra-confirmed). A bounded negative affix
  with a shared stack cap accumulates **additively within its own factor** (e.g. compass
  `−2%/stack, up to 30` → one `×0.40` factor), and that factor then **multiplies** against other
  distinct negative/positive factors. **Distinct or unbounded negatives multiply** (this is what
  prevents stacked debuffs from summing past −100% to immunity).
- **Per-stack scaling inside a factor:** default `amount = per × stacks`; with the **"(multiplies)"**
  keyword, `amount = (1 + per)^stacks − 1`. *(Real example: `Aeterna Martyr` — "+(17–20)% additional
  Trauma Damage (multiplies) for each Critical Strike…". Our committed talent scaling uses the
  default `per × stacks`, which is correct for the non-multiplies case.)*

## 3. Identity key = normalized text

`modifier_id` is unusable — **null 11,148×** in season data vs a few dozen populated. Normalized
text (lowercase + collapse whitespace + strip number, i.e. the existing `_override_key`) is the
pooling key. It correctly unifies formatting variants (trailing space / case) and separates genuine
differences ("…One-Handed Weapon" vs "…Two-Handed Weapon"; plain vs "…for the supported skill").
Note: the plain unqualified `+X% additional damage` essentially does **not** exist standalone —
nearly every additional affix is qualified (conditional / scoped / scaling / type-specific), which
is itself strong evidence for per-affix factors.

## 4. Where the current engine is wrong

`offense.py` pools `additional` by **stat key** (`prod(1 + source.total(key) …)`), so distinct
affixes sharing a key (e.g. Bladerunner per-weapon + generic + warcry, all `attack_dmg_additional`)
**sum** when they should **multiply**, and positives/negatives of one key are merged. We already
split *some* specials into their own keys (`post_mobility_dmg_additional`, `two_handed_base_…`),
which is the right instinct but not general.

## 5. Options considered (A chosen)

- **A — pool by affix identity (normalized text).** Self-maintaining; covers conditional, scoped
  ("for the supported skill"), and scaling ("for every X") splits automatically. Chosen.
- **B — pool by (stat_key, condition).** Cheaper but can't split *unconditional* distinct affixes.
- **C — one stat key per special affix.** Correct only by exhaustive manual curation; enum sprawl.

A is the only self-maintaining, fully-correct option. Implementation = group the `additional`
computation by the source entries' normalized `text` (carried in `SourceEntry.text`) instead of by
`source.total(stat_key)`, keeping tag-scoping, with positives summed per identity and each negative
contribution/affix as its own factor.

## 5b. Option A — SHIPPED for hit damage (2026-06-09)

Per-affix pooling is live in `engine/offense.py` (the `/engine/stats` path): `_build_additional_factors`
groups `source.source_log` by `(stat_key, affix_identity(text))` — positives per identity sum into one
factor, each negative is its own factor — and `_additional_product` applies the existing tag-scope
predicates. Identity = `engine/affix_identity.py::affix_identity` (strips signs/ranges/`%`/`#`
placeholder/punctuation; keeps the hyphen). `add()`-only contributions (no source_log) reconcile by
stat-key, preserving legacy behavior. Gear now threads affix `raw_text` (renderer
`statsPayload._buildItemContributions` → `GearAffixContribution.text` → `aggregator` SourceEntry).
Legacy `pipeline.py` / `/engine/compute` marked DEPRECATED. Tests: `TestAdditionalPooling` in
`tests/test_engine_offense.py` (real affix strings; ★ cases empirically fail under old stat-key
pooling: 1.16/1.03/−0.20 vs 1.1664/1.026/0.16). Auditor: `tools/audit_affix_identities.py`.

STILL pooled by stat-key (FUTURE, marked in offense.py): attack-speed additional; damage-taken
additional; `extra_additional` application; "(multiplies)" per-stack compounding.

## 5c. Minted-identity key — SHIPPED (2026-07-07, modifier-identity migration)

The pooling key is now the scraper-minted `pooling_uuid` where one exists:
`pooling_uuid = uuid5(4d8c3c25-940d-453e-be66-21a9d603aa0e, affix_identity(text))`, minted by
tlidb-scraper (its `canonical_template` is a byte-for-byte matched pair with
`engine/affix_identity.py` — neither side may change alone; coordinated two-repo change + fixture
refreeze + scraper seed migration required). Every imported catalog line stores a slim
`{text, uuid, pooling_uuid, modifier_id}` (see `engine/modifier_lines.py`; plain-string runtime
view unwrapped at the `season_manager` load boundary).

At runtime `engine/identity_index.py` builds `affix_identity(text) → pooling_uuid` over the stored
season files, and the pool sites key by `pool_identity(entry, index) = index.get(identity,
identity)` — a PURE function of the text, so same-wording entries key identically regardless of
emit path, and minted-suffix per-instance texts (supports `|id|role`, nodes `|tag|id`, cores
`|core|<name>`) miss the index and keep multiplying. Provably partition-identical to
`affix_identity` — gates: `tests/test_pooling_partition.py` (frozen partition + index-equivalence),
`tests/test_scraper_parity_gate.py` (cross-repo, template-join), `tests/test_identity_crosscheck.py`
(every stored uuid recomputes from its text; DELETE AT SS13 — after that the scraper's freeze store,
not recomputation, is the source of truth). `affix_identity` remains the fallback for uuid-less
lines (custom rolls, engine-minted texts) and the dev-time cross-check for one season; keying on
the uuid is what lets CN/RU/KO texts attach to the same identities later.

**Note on `(multiplies)`:** the keyword IS on 24+ real legendary affixes (e.g. Marksman Bracers
`+X% additional damage dealt by Horizontal Projectiles after each Jump (multiplies)`), but **none
resolve to a stat yet — all NYI** (no `stat_key`, so the renderer skips them and they contribute
nothing). So the engine never reaches the compounding path today, and there is no current bug. When
such an affix is modelled it needs: a stat for the scoped additional damage, a per-stack count
condition (e.g. jumps), and the compounding mode `(1+per)^stacks − 1`.

## 6. Immunity tripwire (SHIPPED)

`engine/guards.py::check_damage_taken_immunity`, called at the end of `compute.py`'s fixed-point
loop. Raises `ImmunityThresholdError` if any single damage-taken stat reaches ≥100% reduction
(amplify-style `dmg_taken` stats: `1 + total ≤ 0`; reduction-style: `1 − total ≤ 0`). This is a
forward-looking guard so the unmodelled multiplicative case is surfaced loudly instead of silently
zeroing damage. No current build trips it. (`taken_as` conversions are excluded.)

## 7. Verification status (in-game checks queued; implementation not blocked)

1. **Positives multiply across distinct affixes.** ✅ **Verbally confirmed (Tyra, 2026-06-08).**
   In-game DPS spot-check still queued for when servers return: dummy DPS `D0`; add one big distinct
   additional (`+50%`) → expect `×1.50`; add a second differently-worded additional of the same type
   → `×2.00` (add) vs `×2.25` (multiply). 25% gap is unmistakable.
2. **Identical-wording positives add** (Gravel + Sun-shooter Long Bow) — ✅ confirmed verbally; spot-check.
3. **Negative: shared-cap bounded adds, distinct/unbounded multiply.** ✅ confirmed verbally; spot-check.
   Stack identical bounded debuffs (shared cap → add) vs two distinct debuffs (multiply); confirm no immunity.
4. **"(multiplies)" compounding** vs default per-stack at high stack counts — still to verify in-game.

## 8. Out of scope (for now)

Compass / map modifiers (Tyra wants these modelled eventually, not now). The per-affix math above
still applies to on-character negatives (legendary drawbacks, talent `−X%`), which are almost always
single-instance.

**Core talents are NOT a pooling concern — dedup at source.** The affix-identity audit flags
item-granted core talents (legendary affixes prefixed with a `[Keyword]`, e.g. `[Thunderclap]` on
*Illusory Ocean Silk - Thunder*, `[Penetrating]`/`[Translucent]` on *Grasp of Truth*) against the
plain selected/skill version. A core talent is **unique**: granted + selected (or granted by multiple
items) it must apply **exactly once** — never add or multiply. This is a SOURCE-LEVEL dedup upstream
of the additional pooling, NOT a normalizer change (stripping the bracket would wrongly make them add).
Currently moot — the engine doesn't apply `coreTalentSelections` and these affixes are NYI. Build the
dedup when core talents + item-granting are modelled. See auto-memory `project_core_talent_uniqueness`.
