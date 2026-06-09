# Additional-Damage Pooling — model & rework plan

Status: **design confirmed, implementation pending in-game verification.** Captures the decisions
from the 2026-06-08 discussion. The immunity tripwire (§6) is the only part shipped so far.

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
  normalized text) from any sources **add** into that one factor. *(Owner-confirmed: Gravel +
  Sun-shooter Long Bow, both `+X% additional Projectile Damage`, ADD.)*
- **Negatives are a separate concern from positives** (owner-confirmed). A bounded negative affix
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

## 6. Immunity tripwire (SHIPPED)

`engine/guards.py::check_damage_taken_immunity`, called at the end of `compute.py`'s fixed-point
loop. Raises `ImmunityThresholdError` if any single damage-taken stat reaches ≥100% reduction
(amplify-style `dmg_taken` stats: `1 + total ≤ 0`; reduction-style: `1 − total ≤ 0`). This is a
forward-looking guard so the unmodelled multiplicative case is surfaced loudly instead of silently
zeroing damage. No current build trips it. (`taken_as` conversions are excluded.)

## 7. Open items — verify in-game before building §2/§5

1. **Positives multiply across distinct affixes.** Easiest test: dummy DPS `D0`; add one big
   distinct additional (`+50%`) → expect `×1.50`; add a second differently-worded additional of the
   same type → `×2.00` (add) vs `×2.25` (multiply). 25% gap is unmistakable.
2. **Identical-wording positives add** (Gravel + Sun-shooter Long Bow) — confirmed verbally; spot-check.
3. **Negative: shared-cap bounded adds, distinct/unbounded multiply.** Stack identical bounded
   debuffs (shared cap → add) vs two distinct debuffs (multiply); confirm no immunity.
4. **"(multiplies)" compounding** vs default per-stack at high stack counts.

## 8. Out of scope (for now)

Compass / map modifiers (owner wants these modelled eventually, not now). The per-affix math above
still applies to on-character negatives (legendary drawbacks, talent `−X%`), which are almost always
single-instance.
