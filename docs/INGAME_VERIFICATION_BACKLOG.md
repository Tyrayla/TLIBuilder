# In-Game Verification Backlog

Mechanics the **TLI Builder** engine models that need confirming against the live game. Each entry is
self-contained so a helper can run it without knowing the codebase. **You configure the build, read
ONE specified field, and report the value + your support rolls + a screenshot — you do not need to do
any math.** The owner verifies against the engine.

---

## Tester quick-start (read once)

**The target dummy.** Use the standard dummy: **Level 85, 50% Armor, 30% Elemental/Erosion
resistance.** Confirm it's this one — a different dummy mitigates differently and breaks the numbers.

**Standard isolation build (unless a test says otherwise).** Strip everything that isn't being tested:
- **0 gear, no Pact Spirits, no Hero Memories/Traits, no talent nodes, no slates.**
- Spirits/attributes add a hidden "Damage Bonus %" (main-stat damage) the engine does **not** model —
  leaving them on will make in-game read higher than the app. Keep them off.
- Only the **skill + the support(s) named in the test** should be active.

**Which number to read — THIS MATTERS, they are different:**

| Field | Where | What it is | Use it for |
|---|---|---|---|
| **Total Spell Damage** (min–max range) | Skill tooltip → Damage | Per-**hit** damage, dummy-mitigated. **Not** affected by cast rate or shotgun/multi-hit. | Per-hit damage mechanics (effectiveness, additional-damage lines, Augmentation, Numbed). |
| **Spell DPS** | Skill tooltip → Damage | Theoretical single-target DPS = per-hit × cast rate × crit, mitigated. **Excludes** shotgun/multi-hit. | Cast-rate / crit / Lucky-EV checks. |
| **Average DPS in a span of time** | Damage Recount, **≥2-min** test | **Actual** sustained DPS — includes multi-hit/shotgun and uptime/downtime. | Shotgun / total-DPS checks. |

Notes: Recount runs **below** tooltip Spell DPS for single-hit skills (downtime), and **above** it for
multi-hit/shotgun (extra hits). **Lucky** raises the average but **not** the displayed min–max range.

**Prefer ratios.** Where a test gives a "bare vs with-support" comparison, read **both** and the ratio
is what's checked — ratios cancel out the dummy mitigation, so they're robust even if your rolls differ
from the engine's tier-average.

**How to report.** Fill the test's RESULT block: the observed value(s), **your support's exact rolls
and level/rank/tier** (read them from the support's detail panel — e.g. "Augmentation +5.7% per Jump,
rank 5, tier 1"), the skill level, and a screenshot of the panel you read. Paste it back to the owner.

---

## Test template (copy for new tests)

```
### [ID] — [Mechanic]
- Status: ⬜ Pending
- Setup: <exact build to configure>
- READ: <exact screen + field>
- Why this field: <one line>
- Expected: <formula + worked example at tier-average> (±tolerance)
- RESULT:
  - Observed: ____
  - Support roll(s) / rank / tier used: ____
  - Skill level: ____
  - Screenshot: ____
  - Notes: ____
```

Status legend: ⬜ Pending · ✅ Verified · ❌ Failed (engine wrong) · 🔶 Partial / needs retest.

---

## Tests

### CL-EFF-01 — Spell added-damage effectiveness
- Status: ✅ Verified (owner, within in-game read)
- Setup: Chain Lightning, no supports. Note its base `Total Spell Damage`, then add a ring with a flat
  "+X–Y lightning damage **to spells**" and note it again.
- READ: Skill tooltip → **Total Spell Damage** (range), bare vs with-ring.
- Why: confirms the listed base is **not** scaled by the 136% effectiveness, but the added flat **is**.
- Expected: max increases by `Y × 1.36 × 0.49` (0.49 = lightning dummy mitigation). The base is unchanged.
- RESULT: confirmed (12–236 base; +2–58 ring → +39 max = 58×1.36×0.49).

### CL-POOL-01 — Support additional-damage lines multiply
- Status: ✅ Verified (owner, 2 tests, <0.5%)
- Setup: a skill + one Magnificent + one Noble support that both carry "+% additional damage for the
  supported skill". Read bare, then with supports; vary their ranks.
- READ: Skill tooltip → **Total Spell Damage** (range), compute the ratio.
- Why: each line is its own ×(1+x) factor — confirms they MULTIPLY (not sum).
- Expected: two same-worded +20% universals → ×1.44 (not ×1.40). Universal × specific → multiply.
- RESULT: confirmed multiplicative (Split Firebolt: rank-1→5 gave exactly ×1.20 on top of an active +20%).

### CL-NUMBED-01 — Numbed lightning vulnerability
- Status: ⬜ Pending
- Setup: Chain Lightning, no supports. Read bare, then apply **Numbed** to the dummy and read with a
  known stack count (or set it as high as you can sustain and count the stacks).
- READ: Skill tooltip → **Total Spell Damage** (range), bare vs Numbed; report the **stack count**.
- Why: Numbed should raise outgoing **lightning** damage by **+5% per stack** (×1.50 at 10 stacks),
  lightning only.
- Expected: ratio = `1 + 0.05 × stacks` (e.g. 10 stacks → ×1.50). ±2%.
- RESULT:
  - Observed (bare / Numbed / stacks): ____
  - Skill level: ____  Screenshot: ____  Notes: ____

### CL-RANK-01 — Support universal-line rank table
- Status: ⬜ Pending
- Setup: Chain Lightning + one Magnificent or Noble support that has "+% additional damage for the
  supported skill". Read `Total Spell Damage` at the support's **rank 1, 3, and 5** (keep tier fixed).
- READ: Skill tooltip → **Total Spell Damage** (range); ratios between ranks.
- Why: confirms the universal line scales R1 0% / R2 4% / R3 8% / R4 14% / R5 20%.
- Expected: rank1→3 ratio ×1.08, rank1→5 ratio ×1.20, rank3→5 ratio ×1.111. ±1%.
- RESULT:
  - Observed (r1 / r3 / r5): ____   Tier used: ____   Skill level: ____   Screenshot: ____

### CL-SHOTGUN-01 — Merge + Web shotgun hit count
- Status: 🔶 Partial (owner saw ~3 hits visually; numeric DPS not yet confirmed)
- Setup: Chain Lightning + **Web (Magnificent)** + **Merge (Noble)**, no other jumps. Compare the
  Recount DPS to the same build with Merge removed.
- READ: **Damage Recount → Average DPS in a span of time** (≥2-min test). Also count the lightning
  bolts hitting the dummy per cast if visible.
- Why: Web spawns 1 chain per Jump; Merge lands them on the same target. On a lone dummy:
  hits = `1 + total_jumps`; each extra hit deals 20% (Merge's 80% falloff). 2 base Jumps → 3 hits → ×1.40 DPS.
- Expected: equipping Merge alongside Web multiplies total DPS by `1 + total_jumps × 0.20` (×1.40 at 2
  jumps), on top of the support damage lines. ±5% (Recount variance). Confirm the **hit count = 3**.
- RESULT:
  - Observed (Web only / Web+Merge, ≥2min each): ____
  - Hit count seen: ____   Jumps on skill: ____   Skill level: ____   Screenshot: ____

### CL-SHOTGUN-02 — Shotgun scales with +Jumps
- Status: ⬜ Pending (needs a +Jumps source — gear/talent)
- Setup: CL + Web + Merge, then add a known "+N Jumps" source. Compare Recount DPS before/after.
- READ: **Damage Recount → Average DPS in a span of time** (≥2-min).
- Why: hits = `1 + total_jumps`, so +Jumps should add 20% DPS each.
- Expected: adding +N Jumps changes the shotgun multiplier from `1+2×0.20` to `1+(2+N)×0.20`. Report N.
- RESULT:
  - Observed (base jumps / +N jumps): ____   N = ____   Skill level: ____   Screenshot: ____

### CL-AUG-01 — Augmentation per-Jump (multiplies)
- Status: ⬜ Pending  ·  *engine modelled, NOT yet game-verified*
- Setup: Chain Lightning + **Augmentation (Magnificent)** only. No other jumps. Read `Total Spell
  Damage` bare, then with Augmentation.
- READ: Skill tooltip → **Total Spell Damage** (range). (Augmentation has no shotgun, so the per-hit
  range is the clean signal.)
- Why: confirms the per-Jump line compounds as `(1+per)^jumps` (NOT additive `per × jumps`), and the
  universal +rank line multiplies on top.
- Expected: ratio = `(1 + rank_table[rank]) × (1 + per)^total_jumps`.
  Worked example — rank 5, tier 1 (per ≈ 5.7%), 2 base Jumps: `1.20 × 1.057² = ×1.341`.
  **Discriminator:** additive per-jump would give `1.20 × (1 + 0.057×2) = ×1.337` — close, so report
  the range to ~3 sig figs and your exact `per` roll. ±1%.
- RESULT:
  - Observed (bare / with Augmentation): ____
  - Augmentation per-Jump roll / rank / tier: ____   Jumps on skill: ____   Skill level: ____   Screenshot: ____

### CL-AUG-02 — Augmentation scales with +Jumps
- Status: ⬜ Pending (needs a +Jumps source)
- Setup: CL + Augmentation, then add "+N Jumps". Read `Total Spell Damage` before/after the +Jumps.
- READ: Skill tooltip → **Total Spell Damage** (range).
- Why: the exponent is the jump count → more jumps should compound harder.
- Expected: the Augmentation factor goes from `(1+per)^2` to `(1+per)^(2+N)`. Report N and your `per` roll.
- RESULT:
  - Observed (base / +N jumps): ____   N = ____   per roll: ____   Skill level: ____   Screenshot: ____

### CL-LUCKY-01 — Lucky Damage expected-value uplift
- Status: ⬜ Pending  ·  *engine modelled, NOT yet game-verified*
- Setup: Chain Lightning + **Lucky (Noble)** only.
- READ: **TWO fields from the skill tooltip** — the **Total Spell Damage** range AND the **Spell DPS**.
- Why: Lucky rolls damage twice and keeps the higher. It does **not** change the min–max **range**, but
  it **raises the average/DPS**. So the lift shows in Spell DPS, not in the range.
- Expected: with Lucky on, `Spell DPS` should exceed `(range midpoint × cast rate × crit factor)` by the
  Lucky factor `(min + ⅔·R) / (min + ½·R)` computed from the displayed range `[min,max]`, `R = max−min`.
  For Chain Lightning's wide range this is large (~+25–30%). Report the **range, Spell DPS, cast rate,
  and crit %** shown so the factor can be backed out. ±3%.
- RESULT:
  - Observed (Total Spell Damage range / Spell DPS / cast rate / crit%): ____
  - Lucky rank / tier: ____   Skill level: ____   Screenshot: ____   Notes: ____

---

## How results are ingested
Owner: for each returned RESULT, recompute the engine's prediction for the **tester's exact rolls/level**
(not the tier average) and compare to the observed field. Mark ✅/❌/🔶, and on ❌ note the engine fix.
Until the explicit-roll feature lands (see `project_skill_tooltips_and_rolls`), the app uses each tier's
**midpoint**, so expect ~1% absolute drift from a tester's specific roll — verify the **ratio/scaling
behaviour**, not the absolute number.
