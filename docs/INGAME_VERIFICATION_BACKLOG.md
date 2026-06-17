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
- The engine **now models** the main-stat "Damage Bonus %" (0.5% damage per point of the skill's main
  attribute) — see **MAINSTAT-01**. Stripping gear/spirits removes their attribute contributions so the
  app and game both fall to the character's base attributes; configure the same attributes in the app.
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
the ratio is what's checked, and it cancels the dummy mitigation and any constant main-stat bonus,
so it's robust even if your rolls or attributes differ from the engine's.

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

### MAINSTAT-01 — Main-stat Damage Bonus
- Status: ⬜ Pending  ·  *engine now modelled, NOT yet game-verified*
- Setup: Chain Lightning only (main stats Dexterity + Intelligence). Note your **Dexterity** and
  **Intelligence** totals from the character sheet, and the skill level. No supports.
- Run: one ≥60s parse. Also note the in-game **"Damage Bonus %"** shown on the attribute panel, if visible.
- Expected: each point of a main-stat attribute grants **+0.5% damage**, multi-main-stat skills **sum**
  the attributes → bonus = `(Dex + Int) × 0.5%`. The app's *Player Stats → Damage Bonus* row should equal
  this, and the in-game Damage Bonus % (if shown) should match. ±3%.
- RESULT:
  - Recount Avg DPS (span) + Duration: ____
  - Dexterity / Intelligence totals: ____   In-game Damage Bonus %: ____   Skill level: ____   Screenshot: ____

### BLESSING-01 — Blessing base effects + additive stacking
- Status: ⬜ Pending  ·  *engine modelled (user-set stacks), NOT yet game-verified*
- Setup: Any modelled skill. Acquire **Focus Blessing** stacks (and separately **Agility Blessing**).
  In the app, set **Focus Blessings** to the same stack count under Conditions.
- Run: ≥60s parse at **0 stacks**, then ≥60s at **max (4) stacks** of Focus. (Repeat for Agility if testing it.)
- Expected: Focus = **+5% additional damage per stack**, stacks **ADD** → ×1.20 at 4 stacks (NOT 1.05⁴).
  Agility = **+4% Attack & Cast Speed and +2% additional damage per stack** (×1.08 additional + speed at 4).
  Focus and Agility additional-damage pools **multiply** with each other. ±3%.
- RESULT:
  - Recount Avg DPS (span) + Duration, 0 / max stacks: ____
  - Blessing tested + stack count: ____   Skill level: ____   Screenshot: ____   Notes: ____

### STDSUP-01 — Standard support skills (Chain Lightning L16, no gear/talents)
- Status: ✅ Verified (owner, 2026-06-10) — all within ±5% of the in-game average (most within ±2%)
- Setup: Chain Lightning L16 only; dummy 50% armor / 30% elemental resist. Each support at Lv16.
- Method: compare the engine `total_dps_vs_target` to the Recount span-average (the in-game *Total Spell
  Damage* range is post-mitigation = engine pre-mit × dummy mitigation, lightning/cold ×0.49, physical ×0.50).
- RESULT (in-game best sample → engine, % diff):
  - Base CL: 204 → 195.9 (−4.0%) · Control Spell (+additional, −100% crit): 261 → 258.9 (−0.8%)
  - High Voltage (lightning additional + auto-Numbed): 226 → 236.1 (+4.5%) · Added Cold: 253 (2 min) → 248.4 (−1.8%)
  - Added Physical: 248 → 250.0 (+0.8%) · Quick Decision (cast speed): 246 → 239.9 (−2.5%)
  - Crit Rating: 207 (4 min) → 205.9 (−0.5%)
  - Note: 60s parses for the two crit/added-cold cases read ~+10% high (variance); 2–4 min parses converged.

### SPEED-01 — Additional attack/cast speed stacks multiplicatively
- Status: ✅ Verified (owner, 2026-06-10) → engine fixed
- Test: 1.5/s base weapon + 10% additional Attack Speed (Dual Wield) + 22.5% additional (Quick Decision)
  → **2.02/s** in-game = ×1.10×1.225 (multiplicative), not ×1.325 (additive).
- Fix: additional attack/cast speed now pools PER-AFFIX (distinct sources multiply); `_speed_additional_product`.

### CURSE-01 — Curse stacking / limit / pooling (multiple checks)
- Status: ⏳ Needs in-game testing (curses shipped 2026-06-17 with assumed rules)
- The engine currently ASSUMES the following; each needs confirming:
  1. **Over-limit precedence.** With more curses than your curse limit, which one(s) apply? Believed "most recent
     applied". Test: apply two curses (e.g. Vulnerability then Scorch) with limit 1, observe which is active on the
     enemy. (The app makes you pick manually for now.)
  2. **Same curse, different levels.** Apply the same curse from two sources at different levels (e.g. a Lv1 slotted
     curse + a Lv20 gear-triggered curse). Believed: **only the highest level applies** (no stacking). Confirm.
  3. **Different curses pooling.** Two different damage-taken curses on one enemy (e.g. Timid all-hit + Vulnerability
     physical) — do their "+X% additional damage taken" lines **multiply** or add? Engine multiplies. Test on a
     physical skill: record DPS with neither / Timid only / Vulnerability only / both, compare to ×(1.39)(1.39).
  4. **Curse Effect scaling.** +X% Curse Effect — does it scale the damage-taken line linearly (engine: Base × (1 +
     Curse Effect))? Test base vs +Curse Effect.
  5. **Noble/Magnificent on curses.** Confirm "+additional damage for the supported skill" on a curse support does
     nothing (curses deal no hit damage) — engine treats it as inert.
- Method: physical or single-element skill vs the standard dummy; Recount span-average; report the number per case.

---

## How results are ingested
Owner: for each returned RESULT, configure the same build in the app (matching the tester's exact
rolls/level/rank/tier) and compare the engine DPS to the reported Recount **span average**. Mark
✅/❌/🔶; on ❌ note the engine fix. The explicit-roll feature has landed (per-support roll sliders), so
the app can now match a tester's exact rolls — enter them to compare absolute numbers; otherwise the app
defaults to each tier's **midpoint** (~1% drift), so verify the **ratio/scaling behaviour**. All
comparisons use the Recount **Average DPS in a span of time** (≥60s); the tooltip is not a source of truth.
