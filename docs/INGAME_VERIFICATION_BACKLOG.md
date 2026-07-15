# In-Game Verification Backlog

> **This doc is the pending test *queue*.** Confirmed/partial results (and modeled-but-untested coverage)
> live in the **Verification Knowledge Base**: `data/verification/*.json` → `docs/verification/README.md`,
> viewable in-app via the main-menu **Verification Database** button. When a test here is confirmed, port its
> RESULT into a KB entry (`/add-verification`) and update the entry's status. Backlog IDs (e.g. `DEMOLISHER-01`)
> are cross-linked from the KB entries.

Mechanics the **TLI Builder** engine models that need confirming against the live game. Each entry is
self-contained so a helper can run it without knowing the codebase. **You configure the build, run a
timed Damage Recount, and report the number + your support rolls + a screenshot — you do not need to
do any math.** Tyra verifies against the engine.

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
panel. Paste it back to Tyra.

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

### WIND-RHYTHM-01 — Wind Rhythm cast rate + server breakpoints
- Status: 🔶 Modeled from Tyra's wrc-six calculator; confirm against the live game.
- Model: Wind Rhythm triggers off a per-tier **base cooldown** (L0 0.5 / L1 0.6 / L2 0.7 / L3 0.8 s), sped by CDR +
  a share of Cast Speed. `final_cast = cast_speed_inc × (1 + cast_speed_additional)`;
  `raw = base / (1 + cdr_speed_inc + wind_bonus × final_cast) / (1 + cdr_speed_additional)`; tick-quantized
  `server = ceil(raw × 30) / 30` (30 Hz, like Tangle/Spell Burst). Additional cast speed is MULTIPLICATIVE.
- Checks:
  1. **Base cooldown per tier** — with 0 CDR / 0 cast speed, the trigger interval = the tier's base (0.5–0.8 s),
     tick-rounded (e.g. 0.5 → 15 ticks → 0.5 s; 0.6 → 18 ticks).
  2. **Cast-speed → CDR conversion** — the wind bonus % of your cast-speed bonus feeds CDR: e.g. base 0.5, wind 40%,
     +100% increased cast → raw 0.5/(1+0.4×1.0)=0.357 → 11 ticks → 0.367 s. Confirm cast speed speeds the trigger.
  3. **Additional cast speed is multiplicative** — +X% additional cast multiplies the increased before the wind
     conversion (Tyra: +10% additional shifted the cast breakpoint 350→318 = ÷1.1). Confirm in-game.
  4. **Server breakpoints** — the rate only steps at whole-tick crossings; confirm the CDR% / cast-speed% /
     wind-bonus% to the next faster tick match the app's Wind Rhythm panel (mirrors wrc-six.vercel.app).
- RESULT (per check): Recount Avg DPS (span) + Duration; the wind-bonus roll + tier; CDR%/cast%; Screenshot.

### CL-BASE-01 — Baseline Chain Lightning DPS
- Status: ✅ Verified (Tyra, within ~1%)
- Setup: Chain Lightning only, standard isolation build. Note the skill level.
- Run: one ≥60s parse.
- Expected: matches the app's DPS for the same level (the app shows the engine number directly).
- RESULT: confirmed (L14 + 1 support read 160 span-avg vs engine 158).

### CL-POOL-01 — Support additional-damage lines multiply
- Status: ✅ Verified (Tyra; re-confirm via Recount when convenient)
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
- Status: 🔶 Partial (Tyra saw ~3 hits visually; numeric DPS not yet confirmed)
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
- Status: ✅ Verified (Tyra, 2026-06-10) — all within ±5% of the in-game average (most within ±2%)
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
- Status: ✅ Verified (Tyra, 2026-06-10) → engine fixed
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

### EMPOWER-01 — Empower (Euphoria) buffs (multiple checks)
- Status: ⏳ Needs in-game testing (empower shipped 2026-06-17 with assumed rules)
- The engine ASSUMES the following; each needs confirming:
  1. **Euphoria stacks across empower skills.** Slot 2+ empower skills — do all their Euphoria buffs apply at once,
     or is only one Euphoria active at a time? Engine assumes they all stack (no limit).
  2. **Empower Skill Effect pooling.** increased sums, additional multiplies ((1+inc)×(1+additional)). Confirm.
  3. **Mass Effect charges.** "10.5% effect per +1 Charge, up to 31.5%" — confirm it scales with the empower skill's
     Max Charges (cooldown skills only; +1 from Mass Effect). Report base charges of a few empower skills.
  4. **Uptime.** Engine treats the buff as always-on (100%); real uptime/duration is unmodeled.
- Method: a spell main skill + Secret Origin Unleash (+15% Spell) vs the standard dummy; Recount span-average.

### TANGLE-01 — Tangle DPS model (multipliers across multiple setups)
- Status: ⬜ Pending — **verify the whole Tangle model against the live game across several different setups**
  to confirm each multiplier behaves correctly (not just one build).
- Setup: a Spell + **Spell Tangle** vs the standard dummy. Then vary ONE thing at a time and re-parse:
  1. **Count.** Base (1 attached) → add "+1 apply additional Tangle to enemies" (gear/Peculiar Vibe). Expected
     total DPS **×2** (each tangle is a full caster, no penalty). Also try +2 apply with ≥3 Max Tangle Quantity.
  2. **Tangle Damage Enhancement.** Add a known "+X% Tangle Damage Enhancement"; expected **×(1 + X)**. Add a
     SECOND enhancement source; expected additive within itself (56%+56% → ×2.12), NOT multiplicative.
  3. **Additional Tangle Damage.** Add "+X% additional Tangle Damage"; expected its own multiplicative factor,
     SEPARATE from enhancement.
  4. **Plain Tangle Damage / Tangle Crit.** Confirm "+X% Tangle Damage" lands in the increased pool and "+N Tangle
     Critical Strike Rating" raises the tangle's crit.
  5. **Dormant Entanglement.** With Max Tangle Quantity > attached (≥1 inactivated) + Dormant enabled, expected
     +40% **additional** Tangle Damage per inactivated tangle.
  6. **Cast speed.** Confirm the tangle trigger rate scales 1:1 with the spell's cast rate.
- Confirm in-game: **base attached-per-enemy = 1** and base **Max Tangle Quantity = 2** (Help DB); the player can't
  manually cast the skill while a Tangle activator is enabled (use only spawns tangles, always a new one).
- RESULT (per sub-test): Recount Avg DPS (span) + Duration, before/after; the mod + its roll; Skill level; Screenshot.

---

### TANGLE-02 — Per-Tangle modifier scaling + Magister generate nodes
- Status: ⬜ Pending — verify the newly-wired "per (in)activated Tangle" scaling and the Magister generate-Tangle
  nodes against the live game.
- Setup: a Spell + **Spell Tangle** vs the standard dummy. Then:
  1. **Per activated Tangle.** Equip a line like *Dormant Entanglement gains an additional effect: +(100–120) Spell
     Crit Rating and +(12–15)% additional damage on Critical Strike **for each activated Tangle***. Confirm the bonus
     scales by the number of **attached** tangles (×count) — raise the attach count (+apply-additional-Tangle) and
     confirm the bonus grows proportionally. The engine reads the derived effective count (default = the attach cap;
     the "Active Tangles" Config field lowers it).
  2. **Per inactivated Tangle.** With Max Tangle Quantity > attached (≥1 inactivated), confirm a "+X per inactivated
     Tangle" line scales by (placeable − attached).
  3. **Active Tangles field.** Confirm the Config "Active Tangles on Target" field left blank/0 uses the full attach
     cap (shown as the greyed placeholder), and that typing a lower number scales both DPS and the per-tangle bonuses
     down.
  4. **Magister Focus-Blessing node** ("Gains 1 stack of Focus Blessing when activating Spell Burst or generating
     Tangle"): confirm Focus Blessing sits at max on a tangle/spell-burst build (engine models it as full uptime).
  5. **Magister ES-charge node** ("immediately starts Charging Energy Shield on generate"): currently **recognized
     but NYI** (no ES-recharge model) — badges Unconsumed. Note the in-game ES behaviour for when that model lands.
- RESULT (per sub-test): Recount Avg DPS (span) + Duration, before/after; the mod + its roll; count; Screenshot.

---

### DEMOLISHER-01 — Demolisher Charge (Groundshaker) model (multiple checks)
- Status: 🔶 Partially modeled — the subsystem is shipped (uncommitted); several assumptions need a live confirm.
  Tyra has already pinned the Collapse step function in prior testing (see below); the rest is unverified.
- Setup: **Groundshaker** vs the standard dummy. Note skill level, weapon, and every socketed support + its tier/rank.
  Model recap (what the engine now does):
  - Restoration = **base 3 s ÷ (1 + Σ Demolisher Charge Speed increased)** — INCREASED pool only, smooth real-time.
  - Primary fissure (227% WAD) lands **every cast**; secondary explosion (1135% WAD) only on a **charged** cast
    (charged_rate = min(cast_rate, 1/restoration)). Rhythm mode: cast_rate = 1/R. Manual: cast_rate = APS.
  - Every-cast-charged breakpoint: (1 + increased) ≥ 3 ÷ cadence. The Demolisher panel surfaces "+X% to sustain" or
    "-X% droppable".
- Checks:
  1. **Smooth vs tick-quantized restoration.** Confirm restoration is NOT hard-rounded to 30 Hz ticks (the model
     assumes smooth real-time, unlike Spell Burst / Tangle). Vary Demolisher Charge Speed increased and confirm the
     charged-cast rate scales smoothly (no tick plateaus).
  2. **Increased-only restoration.** Confirm Demolisher Charge Speed **additional** (if any source exists) does NOT
     speed restoration — only increased does.
  3. **Rhythm breakpoint.** At a fixed Rhythm interval R, find the charge-speed increased at which the secondary fires
     on every cast; expected at (1 + increased) = 3/R. Confirm dropping below re-introduces the mismatch (secondary
     uptime = R ÷ restoration).
  4. **Frequent Quake 5-hit.** Confirm the max-spread fissure, instead of exploding, deals **5 fissure hits** (1 + 4×0.4 s)
     each = a primary-fissure hit — so the FQ secondary total ≈ the single 1135% explosion (5 × 227%), before Collapse.
     Confirm FQ's **+(66–68)% additional Hit Damage** applies to the fissure hits.
  5. **Cripple scope.** Confirm the **−90% additional damage while the fissure spreads** hits the **primary fissure**
     (and, with FQ, the fissure ticks) but **NOT the secondary explosion** (Tyra-observed 46 vs 319 on the primary:
     319 × 0.10 × 1.45 ≈ 46). Confirm the **+(44–46)% consume** bonus applies to the whole charged cast.
  6. **Collapse step function.** Already Tyra-pinned: **Collapse% = floor(1.6/R) × 0.5 × roll**, needs FQ persistence
     + auto/rhythm overlap; boundaries at R = 1.6/n (0.8 and 0.4 time-average between floors). Re-confirm opportunistically.
  7. **Wrathful Vault movement→AS.** The stat is surfaced but its APPLICATION is a follow-up (movement→AS not wired).
     Note the in-game jump-cast cadence + how much Movement Speed → Attack Speed for when that model lands.
- RESULT (per check): Recount Avg DPS (span) + Duration, before/after; the mod + its roll; R / charge-speed; Screenshot.

---

### SPELLBURST-01 — Spell Burst DPS model + 30/s tick behaviour (multiple checks)
- Status: 🔶 Partially verified — **combined total DPS matched in-game to within 1.2% over a 4-min test** with matching
  gear (manual triggering, at the **39-charge-tick** breakpoint). Remaining checks below (M-vs-M+1 count, the
  charge-speed breakpoint dead-zone shape, auto-trigger, per-support burst bonuses) still ⬜.
- Setup: an eligible Spell (no cooldown, not channeled) with **+Max Spell Burst** gear, vs the standard dummy. Use the
  Recount span average (≥60 s), not the tooltip. Vary ONE thing at a time:
  1. **Casts per burst — M vs M+1.** Burst once and count the separate Spell Burst damage numbers per trigger. The app
     assumes **M + 1** (the triggering cast counts). Confirm whether it's M or M+1.
  2. **No damage cap.** Raise Max Spell Burst high (e.g. 3 → 7 → 14). DPS should scale **linearly with (M+1)** with no
     plateau (the app applies no cap).
  3. **Charge-limited regime.** Fast cast, slow charge (no Charge Speed). Recount DPS ÷ per-cast ≈ `(M+1) / T` with
     `T ≈ 2 s`. Confirm **base charge time = 2 s** and the **Play Safe** Cast-Speed → Charge-Speed propagation.
  4. **Charge-speed breakpoints (the key tick check).** Finely raise Spell Burst Charge Speed. The app predicts
     **hard-rounded dead zones** (charge speed inside a tick band gives 0 gain; crossing to the next whole 30 Hz tick
     jumps it). If DPS instead rises **smoothly** with every 1% charge speed, Spell Burst is NOT hard-rounded after all
     → switch its charge to the smooth+cap model. (This single test validates the breakpoint vs smooth decision.)
  5. **Cast-limited (manual) regime.** Auto-trigger OFF; drop cast speed below `1/T`. Casts/sec should fall to about
     `(M+1) × cast_rate` (the cast gate). Near `cast ≈ charge` look for the ~50% "Scenario-C" drop (a burst waits for
     the next cast after the charge tick).
  6. **Auto-trigger.** With Burst Activation / Solid River, bursts should fire the instant charge fills (independent of
     your cast cadence) → bursts/sec = `30 / charge_ticks`.
  7. **Burst-only damage pools.** Add a "+X% additional Hit Damage for skills cast by Spell Burst" support; confirm it
     lifts ONLY burst-cast damage (inert with `spell_burst_active` off). For **Heart of Flame** confirm +%/stack
     consumed scales with M (cap 6); for **Prairie Fire** confirm the +%/activation ramp and its cap.
- Also confirm globally (tick model): **everything caps at 30/s** (incl. DoT — the app uses 30, not 31), and that
  general channeled skills scale **smoothly** (only the named breakpoint mechanisms — minions/Reap/Wind Rhythm/Split
  Shot Rapid Advance — hard-round).
- RESULT (per sub-test): Recount Avg DPS (span) + Duration, before/after; the mod + its roll; Max Spell Burst; cast &
  charge speed; Skill level; Screenshot.

---

### SPELLBURST-02 — Auto-trigger + charge sources (second pass)
- Status: 🔶 Partially verified — a **Solid River spell-burst build matched in-game within 2%** (Tyra, 2026-06-18),
  confirming the auto-trigger + charge model. Remaining sub-checks below still ⬜.
  1. **Burst Activation** support → auto-trigger (instant; headline = burst-only, no between-burst casts).
  2. **Solid River** → auto-trigger ONLY when Burst Charge Recovery Speed ≥ ~230–250% of base (drops to manual below
     it). Confirm the exact threshold. Also its **charge→burst-damage**: "+Y% per +X% charge speed, up to +Z%" steps at
     each +X% and caps at Z. And its Vorax'd copy (same line on another item) behaves identically.
  3. **Insatiable Greed** (currently via custom mod): 150% of Attack Speed bonuses shorten the Spell Burst charge.
  4. **Squiddle/Squidnova**: now modeled (base +16% burst hit damage buff + Effect scaling) — moved to SPELLBURST-03.
- RESULT: Recount Avg DPS (span) before/after each; the mod + roll; charge & cast speed; Max Spell Burst; Screenshot.

---

### SPELLBURST-03 — Spell Burst loose ends (Squidnova buff, skill area, sustain, Destiny kismets)
- Status: ⬜ Unverified. Newly modeled this pass; each item below carries an approximation to confirm in-game.
  1. **Squidnova base buff**: the buff itself = **+16% additional Hit Damage for skills cast by Spell Burst** (glossary),
     now modeled (was unmodeled — only the flag + the rank +Spell Damage line existed). **Squidnova Effect (+25/50%)
     scales ONLY this +16%** (→ +20%/+24%); confirm it does NOT also scale the separate "+% Spell Damage when having
     Squidnova" rank line (engine assumes it does not). Confirm the +1 Max Spell Burst (rank 6) is a flat +1 (unscaled).
  2. **Skill-Area-per-Burst** (Prairie Fire "+20% Skill Area … up to 10", Kismet Ripple "+X% per activation"): modeled
     as DISPLAY-only Skill Area (scales by Max Spell Burst M, capped) — it does NOT change DPS in the engine. Confirm
     Skill Area isn't expected to move single-target DPS (if it does via more shotgun overlap, that's a separate model).
  3. **Burst-activation sustain**: "Loses 50% current Mana on Spell Burst" (Surging Inspiration) / "Restores 10% Lost
     Life+ES on Spell Burst" (Solid River) — modeled as **per burst TRIGGER × the burst rate** (once per sequence, NOT
     per burst cast), folded into Net Mana/Life Recovery. Confirm it keys off the trigger and the magnitude tracks the
     burst rate. (Known limitation: the mana drain doesn't yet feed the in-loop steady-state Mana% solve — Net shows it
     at the current Mana%.)
  4. **Destiny "Spell Burst Upper Limit"**: "+N to Upper Limit" → +N Max Spell Burst; "Halves Upper Limit" → floor(M/2).
     Confirm Upper Limit == Max Spell Burst and the halving floors.
  5. **Flash Flood "+8% AS/CS per Spell Burst triggered recently, up to 40%"**: modeled from the burst rate
     (bursts recently = rate × 4s, floored, capped at 5 stacks → +40%), converged as a feedback loop. Confirm the "4s
     recently" window and that it caps at +40%.
  6. **Perched River "Critical Strikes have the Unlucky effect"**: modeled as a crit-CHANCE effect — the crit chance is
     rolled twice and the WORSE kept → effective chance = p² (Lucky variant = 1−(1−p)²). The displayed Crit Chance shows
     the effective value with the Kismet as a source. Confirm it's chance (not crit-damage) and the p² magnitude.
     Also generalized: per-type Unlucky DAMAGE (roll twice keep lower, mirrors Lucky) is wired for all 5 types +
     "Damage triggers Unlucky" / "<Type> Damage is Unlucky", in case such lines appear. Recognized-but-NYI:
     "-5% additional damage taken on Spell Burst Charge" (no EHP/damage-taken model).
- RESULT (per sub-item): Recount Avg DPS / Net Recovery before-after; the mod + roll; Max Spell Burst; burst rate; Screenshot.

---

### SKILLCOST-01 — Skill mana/life cost model (multiple checks)
- Status: ⬜ Unverified. The engine now models each skill's per-cast Mana (and Arcane→Life) cost and folds it into
  **Net Mana/Life Recovery** as a SEPARATE drain (never "Consumed"). Formula assumed (Tyra best-guess), needs
  confirming: `cost = (base + flat Skill Cost) × Π(support mana multipliers) × (1 + increased − reduced)`.
- Sub-checks (each: note the skill's in-game Mana/Life cost per cast, your mods/rolls, cast/attack rate, screenshot):
  1. **Base + cast rate**: a flat-cost skill (e.g. Chromatic Shot) alone — confirm per-cast cost and that cost/sec =
     per-cast × your cast/attack rate (attacks→APS, casts & channeled→cast rate).
  2. **Support multipliers**: add Noble/Magnificent/basic supports (each ~110% Mana Multiplier) — confirm they
     **multiply** the cost (×1.10 each), not add.
  3. **Formula order (KEY)**: a "+N Skill Cost" flat source + a big "+X% Skill Cost" — does the flat get scaled by the
     % (engine assumes `(base+flat)×(1+inc)`) or added at the end? **Awakening Skull** is the marquee case: Arcane
     (100% Mana Cost → Life Cost) + its inflated +(400-500)% / +(30-40) Skill Cost → confirm the **Life cost per cast**
     (engine predicts ≈ (base+~35)×~5.5 paid as Life) and that it drives a life death-spiral verdict.
  4. **Frozen Lotus** ("Skills no longer cost Mana"): confirm base cost → 0, BUT a separate "+N Skill Cost" still
     costs (Frozen Lotus zeroes the BASE only, not the final value).
  5. **Percentage-base skills**: **Moon Strike** ("1%") — confirm it's 1% of Max Mana per use (scaling with
     multipliers); **Bull's Rage** ("15%") — confirm it's 15% of Max Mana paid as **Life** (intrinsic conversion; the
     engine currently DEFERS this Bull's-Rage life-conversion — flag if it matters).
  6. **Triggered skills**: confirm triggered skills (Tangle/Spell Burst/Activation Medium/Preparation) pay **no** mana
     cost. (The engine currently can't detect per-slot trigger state — it counts every enabled active skill's cost, so
     this is the gap to confirm/scope.)
  7. **"Consumed recently"?**: confirm whether paying a skill's Mana/Life cost counts toward "X Mana/Life consumed
     recently" for per-N-consumed affixes (Glacier/Compensatory) + threshold gates. The engine currently says **no**
     (cost is excluded from consumed-recently) — verify.
- RESULT: per sub-check — the in-game per-cast cost (Mana and/or Life), your supports/mods + rolls, cast/attack rate,
  Max Mana, before/after Net Mana/Life Recovery, Screenshot.

---

### SHADOW-01 — Shadow Strike delivery model (multiple checks)
- Status: 🔶 Partial. Solo (N=0) vs +Haunt Lv20 (N=2) Recount pair measured 2026-07-15 — see
  `data/verification/shadow-strike.json`. Checks 1 and 2 below have supporting evidence; checks 3–5 remain ⬜.
- Setup: **Thunder Spike** vs the standard dummy. Base build has 0 Shadow Quantity (Shadows only appear via gear/talent/support). Add shadow sources one at a
  time (**Haunt** support = +2 Shadow Quantity; **Frantic Shadow** legendary = +1; **Despised Shadow**
  legendary = 33% chance +3/+4 Shadows + additional Shadow Damage; **Ronin `ronin_c6_r2`** talent = +1).
- Checks:
  1. **Falloff shape.** 🔶 Partial. The N=0→N=2 (Haunt) ratio (≈2.30–2.32 measured vs 2.3184 predicted) supports
     the magnitude of the FIRST −70% falloff step, but a flat-per-shadow model and a compounding-chain model
     predict the identical value at N=2 — they only diverge at N=3. Still needs an **N=3 config** (e.g. Haunt +
     Frantic Shadow) to distinguish flat (1 : 1.30 : 1.60) from compounding (1 : 1.30 : 1.51) at N=1 vs N=2 vs N=3.
  2. **Player-hit independence.** 🔶 Supported (not fully isolated). The same N=0→N=2 ratio is consistent with the
     player's own hit being a clean, unaffected additive term. Note the ratio doesn't perfectly cancel — the solo
     run sat at 1 Numbed stack and the Haunt run averaged ≈1.5 (see SHADOW-02), so a small Numbed-difference
     component rides along; a dedicated isolation test (same Numbed state, vary only shadow count) would close
     this fully.
  3. **Despised Shadow proc granularity.** Equip Despised Shadow (33% chance +3/+4 Shadows "when using the
     Shadow Strike skill"). Confirm the chance rolls **per cast** (not per fight, not a persistent buff) and
     that Shadows gained from the proc last only that cast (not carried into the next cast). The engine models
     this as a per-cast expected-value mix `(1−p)·f(N_base) + p·f(N_base+k)`.
  4. **Shadow count cap.** Stack multiple sources (Haunt + Frantic Shadow + Despised Shadow + Ronin node) to
     reach a high Shadow Quantity. Confirm whether the game caps the total Shadow count at some maximum (the
     engine currently applies none).
  5. **Multistrike / cast-multiplier inheritance.** With a Multistrike-capable build, confirm whether Shadows
     also fire on each Multistrike (proportionally increasing shadow hits) or only on the primary cast. Same
     question for any other cast-multiplier mechanic active on Thunder Spike.
  6. **NEW (added 2026-07-15) — Shadows applying Thunder Spike's inherent Numbed.** Owner-reported: in the
     +Haunt Lv20 run, Numbed stacks alternated 1↔2 (~50% uptime on 2), where the player's own True Body hit
     accounts for the base 1 stack and a Shadow hit appears to independently apply an additional stack. Confirm
     directly (e.g. isolate: does the second stack appear only when a Shadow visibly connects?) and get the
     actual per-Shadow proc rate/interval, not just the inferred average. Unmodeled — see
     `data/verification/shadow-strike.json` NYI list.
     **CONFOUND to exclude before attributing this to shadows (accuracy council, 2026-07-15):** the equipped
     hero trait in both measurement runs, Erika's "Lightning Shadow" tier 1 (`_hero_traits.json:2718`), can
     itself inflict Numbed via "Feline Figure" procs — triggered by movement-based Electrify stacks (1 stack
     per 3 m moved within 1 s, up to 3), independently of Thunder Spike or Shadows. Before crediting the Haunt
     run's 1↔2 alternation solely to shadow hits, this follow-up test must exclude Feline Figure (e.g. confirm
     the player was stationary / Electrify inactive throughout the parse).
- RESULT (per check): Recount Avg DPS (span) + Duration, per Shadow-count config; shadow sources equipped +
  their rolls; Shadow count observed (in-game UI, if shown); Skill level; Screenshot.

### SHADOW-02 — Thunder Spike skill specifics
- Status: 🔶 Partial. Solo + Haunt Lv20 Recount pair measured 2026-07-15 — see `data/verification/thunder-spike.json`.
  Check 1 supported; check 2 supported in aggregate only; check 3 (Rumbling Thunder) still ⬜ — Setup B used
  Haunt, not Rumbling Thunder.
- Setup: **Thunder Spike** alone vs the standard dummy, no supports (isolate the base skill first), then add
  **Rumbling Thunder (Noble)** for check 3.
- Checks:
  1. **Base WAD.** 🔶 Supported. Solo Recount 349 vs engine 340.34 (−2.5%, no correction — solo Numbed sits at a
     genuine flat 1 stack). Supports the magnitude of 277% WAD at Lv20 to within measurement noise (aggregate
     evidence, not an isolation test). Compare against the character-sheet tooltip is explicitly out of scope —
     see `training-dummy.json` doctrine.
  2. **Intrinsic conversion + inherent Numbed.** 🔶 Supported in aggregate only (this pair did not isolate
     conversion or Numbed-on-hit individually — e.g. no run with Numbed suppressed). Confirm 100% of the
     skill's Physical Damage displays/behaves as Lightning Damage (no separate Physical component), and that
     True Body hits inflict 1 stack of Numbed on the target (interval 1s) with NO gear/support required — this
     is a skill-inherent effect, not optional. Watch the dummy's Numbed stack indicator ramp on repeated hits.
  3. **Rumbling Thunder uptime + default-on sanity.** Socket Rumbling Thunder (Noble). The tier-1 line reads
     "+(45–48)% additional Lightning Damage dealt by the skill to the enemy for 2 s" on a True Body hit. The
     engine currently models this as ALWAYS active (default-on assumption: continuous casting → ~permanent
     uptime). Confirm: (a) does a single Thunder Spike cast actually keep the buff up continuously against a
     standing dummy at your attack speed, or does uptime fall short of 100% at low attack speed? (b) is the
     buff per-enemy (relevant vs multiple targets) or a single global buff? Compare Recount DPS with Rumbling
     Thunder socketed vs a same-tier universal "+45% additional damage" support as a sanity check on magnitude.
- RESULT (per check): Recount Avg DPS (span) + Duration; skill level; supports + rolls; sustained Numbed stack
  count observed; Screenshot.

## How results are ingested
Tyra: for each returned RESULT, configure the same build in the app (matching the tester's exact
rolls/level/rank/tier) and compare the engine DPS to the reported Recount **span average**. Mark
✅/❌/🔶; on ❌ note the engine fix. The explicit-roll feature has landed (per-support roll sliders), so
the app can now match a tester's exact rolls — enter them to compare absolute numbers; otherwise the app
defaults to each tier's **midpoint** (~1% drift), so verify the **ratio/scaling behaviour**. All
comparisons use the Recount **Average DPS in a span of time** (≥60s); the tooltip is not a source of truth.
