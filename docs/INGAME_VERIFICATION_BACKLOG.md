# In-Game Verification Backlog

Mechanics the **TLI Builder** engine models that need confirming against the live game. Each entry is
self-contained so a helper can run it without knowing the codebase. **You configure the build, run a
timed Damage Recount, and report the number + your support rolls + a screenshot — you do not need to
do any math.** The owner verifies against the engine.

---

## Tester quick-start (read once)

**The target dummy.** Use the standard dummy: **Level 85, 50% Armor, 30% Elemental/Erosion
resistance.** Confirm it's this one — a different dummy mitigates differently and breaks the numbers.

**Standard isolation build (unless a test says otherwise).** Strip everything that isn't being tested:
- **0 gear, no Pact Spirits, no Hero Memories/Traits, no talent nodes, no slates.**
- Spirits/attributes add a hidden "Damage Bonus %" (main-stat damage) the engine does **not** model —
  leaving them on makes in-game read higher than the app. Keep them off.
- Only the **skill + the support(s) named in the test** should be active.

**THE metric — Damage Recount → "Average DPS in a span of time", over a span of ≥60s.**
That's total damage ÷ total time across a continuous parse. Longer is steadier; do **at least 60s**
(90–120s is better). This is the number every test compares against.

**Do NOT read the skill tooltip for verification.** It is unreliable as a source of truth:
- It does **not** reflect debuffs on the enemy — e.g. **Numbed** never changes the tooltip.
- It does **not** include multi-hit / **shotgun** (Merge/Web), so it understates those builds.
- It does **not** show **Lucky**'s expected-value uplift (Lucky doesn't change the displayed range).
- Various other factors are omitted.

Treat the tooltip as, at most, a rough sanity check — never the recorded result.

**Use ratios.** Where a test says "bare vs with-X", run **two** ≥60s parses (one each) and report both —
the ratio is what's checked, and it cancels the dummy mitigation and the un-modelled main-stat bonus,
so it's robust even if your rolls differ from the engine's tier-average.

**How to report.** Fill the test's RESULT block: the Recount **Average DPS (span)** value(s) and the
**Duration** of each parse, your support's exact **rolls + rank + tier** (from the support detail panel,
e.g. "Augmentation +5.7% per Jump, rank 5, tier 1"), the skill level, and a screenshot of the Recount
panel. Paste it back to the owner.

---

## Test template (copy for new tests)

```
### [ID] — [Mechanic]
- Status: ⬜ Pending
- Setup: <exact build to configure>
- Run: <which parses, e.g. "bare ≥60s, then with X ≥60s">
- Expected: <ratio/value + formula> (±tolerance)
- RESULT:
  - Recount Avg DPS (span) + Duration, per parse: ____
  - Support roll(s) / rank / tier: ____
  - Skill level: ____
  - Screenshot: ____
  - Notes: ____
```

Status legend: ⬜ Pending · ✅ Verified · ❌ Failed (engine wrong) · 🔶 Partial / needs retest.
Default tolerance: **±3%** (Recount combat variance; tighten with longer parses).

---

## Tests

### CL-BASE-01 — Baseline Chain Lightning DPS
- Status: ✅ Verified (owner, within ~1%)
- Setup: Chain Lightning only, standard isolation build. Note the skill level.
- Run: one ≥60s parse.
- Expected: matches the app's DPS for the same level (the app shows the engine number directly).
- RESULT: confirmed (L14 + 1 support read 160 span-avg vs engine 158).

### CL-POOL-01 — Support additional-damage lines multiply
- Status: ✅ Verified (owner; re-confirm via Recount when convenient)
- Setup: Chain Lightning + one Magnificent + one Noble support, both carrying "+% additional damage for
  the supported skill". Vary their **ranks** (e.g. both rank 1 vs both rank 5).
- Run: a ≥60s parse at each rank config.
- Expected: each line is its own ×(1+x) factor — two +20% universals → ×1.44 (NOT additive ×1.40).
- RESULT: confirmed multiplicative.

### CL-RANK-01 — Support universal-line rank table
- Status: ⬜ Pending
- Setup: Chain Lightning + one support that has "+% additional damage for the supported skill". Keep its
  tier fixed; change only its **rank**.
- Run: ≥60s parses at **rank 1, rank 3, rank 5**.
- Expected: rank1→3 ratio ×1.08, rank1→5 ×1.20, rank3→5 ×1.111 (table: R1 0 / R2 4 / R3 8 / R4 14 / R5 20%).
- RESULT:
  - Recount Avg DPS (span) + Duration @ r1 / r3 / r5: ____
  - Tier used: ____   Skill level: ____   Screenshot: ____

### CL-NUMBED-01 — Numbed lightning vulnerability
- Status: ⬜ Pending  ·  *tooltip can't show this (enemy debuff); stacks ramp/decay — see notes*
- Setup: Chain Lightning only. CL self-inflicts Numbed by hitting, so a clean "0 stacks" baseline isn't
  available. Approach: parse continuously so Numbed pins near **max (10)**, watch the dummy's stack
  indicator to confirm the **sustained** count, and compare to the app with **Numbed Stacks** set to that
  same count.
- Run: one ≥60s parse, continuous casting. Record the sustained stack count observed.
- Expected: Numbed adds **+5% lightning damage taken per stack** (×1.50 at 10). The Recount should sit
  ~×(1 + 0.05 × sustained_stacks) above the same build with Numbed Stacks = 0 in the app. ±5% (ramp noise).
- RESULT:
  - Recount Avg DPS (span) + Duration: ____
  - Sustained Numbed stacks observed: ____   Skill level: ____   Screenshot: ____   Notes: ____

### CL-SHOTGUN-01 — Merge + Web shotgun
- Status: 🔶 Partial (owner saw ~3 hits visually; numeric DPS not yet confirmed)
- Setup: Chain Lightning + **Web (Magnificent)** + **Merge (Noble)**. Compare to the same build with
  **Merge removed** (Web only).
- Run: ≥60s parse Web-only, then ≥60s parse Web+Merge. Also count the bolts hitting the dummy per cast.
- Expected: adding Merge multiplies total DPS by `1 + total_jumps × 0.20` (×1.40 at 2 base Jumps), on top
  of the damage lines. Hit count should be `1 + total_jumps` (= 3 at 2 jumps). ±5%.
- RESULT:
  - Recount Avg DPS (span) + Duration, Web-only / Web+Merge: ____
  - Hit count seen: ____   Jumps on skill: ____   Skill level: ____   Screenshot: ____

### CL-SHOTGUN-02 — Shotgun scales with +Jumps
- Status: ⬜ Pending (needs a "+N Jumps" source — gear/talent)
- Setup: CL + Web + Merge, then add a known "+N Jumps". Compare Recount before/after.
- Run: ≥60s parse at base jumps, then ≥60s with +N Jumps. Report N.
- Expected: shotgun multiplier goes `1 + 2×0.20` → `1 + (2+N)×0.20`.
- RESULT:
  - Recount Avg DPS (span) + Duration, base / +N: ____   N = ____   Skill level: ____   Screenshot: ____

### CL-AUG-01 — Augmentation per-Jump magnitude
- Status: ⬜ Pending  ·  *engine modelled, NOT yet game-verified*
- Setup: Chain Lightning + **Augmentation (Magnificent)** only (no shotgun — Augmentation excludes Web).
- Run: ≥60s parse bare, then ≥60s with Augmentation.
- Expected: ratio = `(1 + rank_table[rank]) × (1 + per)^total_jumps`. At rank 5, tier-1 per ≈ 5.7%,
  2 base Jumps → `1.20 × 1.057² = ×1.341`. ±3%.
- Note: at only 2 jumps, compounding (×1.341) and additive (×1.337) are <0.5% apart — this test confirms
  the **magnitude**, not the compounding. Use **CL-AUG-02** to prove compounding.
- RESULT:
  - Recount Avg DPS (span) + Duration, bare / with Augmentation: ____
  - Augmentation per-Jump roll / rank / tier: ____   Jumps on skill: ____   Skill level: ____   Screenshot: ____

### CL-AUG-02 — Augmentation compounds with jump count (discriminator)
- Status: ⬜ Pending (needs a large "+N Jumps" source)
- Setup: CL + Augmentation, with as many **+Jumps** as you can stack. Compare bare vs Augmentation at
  that high jump count.
- Run: ≥60s parse bare, then ≥60s with Augmentation, at the high jump count. Report total jumps and `per`.
- Expected: Augmentation factor = `(1 + per)^total_jumps`. This is the real test of **compounding**:
  e.g. at 8 jumps, `1.057⁸ ≈ ×1.56` vs additive `1 + 0.057×8 ≈ ×1.46` (~7% apart, clearly distinguishable). ±3%.
- RESULT:
  - Recount Avg DPS (span) + Duration, bare / with Augmentation: ____
  - Total jumps: ____   per roll / rank / tier: ____   Skill level: ____   Screenshot: ____

### CL-LUCKY-01 — Lucky Damage expected-value uplift
- Status: ⬜ Pending  ·  *engine modelled, NOT yet game-verified · tooltip can't show this*
- Setup: Chain Lightning + **Lucky (Noble)** only.
- Run: ≥60s parse with Lucky. You can't turn Lucky off in-game on this support, so compare against the
  **app's** prediction for the same build with Lucky on vs off.
- Expected: Lucky rolls damage twice and keeps the higher → it raises the **actual DPS** (Recount) by the
  expected-value factor `(min + ⅔·R)/(min + ½·R)` over Chain Lightning's flat spread — large for CL's wide
  range (~**+25–30%**). The Recount should sit that much above the same build's no-Lucky app prediction.
  ±5%.
- RESULT:
  - Recount Avg DPS (span) + Duration: ____
  - Lucky rank / tier: ____   Skill level: ____   Screenshot: ____   Notes: ____

---

## How results are ingested
Owner: for each returned RESULT, configure the same build in the app (matching the tester's exact
rolls/level/rank/tier) and compare the engine DPS to the reported Recount **span average**. Mark
✅/❌/🔶; on ❌ note the engine fix. Until the explicit-roll feature lands (see
`project_skill_tooltips_and_rolls`), the app uses each tier's **midpoint**, so expect ~1% absolute drift
from a tester's specific roll — verify the **ratio/scaling behaviour**, not the absolute number. All
comparisons use the Recount **Average DPS in a span of time** (≥60s); the tooltip is not a source of truth.
