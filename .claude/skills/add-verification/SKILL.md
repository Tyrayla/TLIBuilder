---
name: add-verification
description: Create or update a Verification Database entry (data/verification/<id>.json) whenever an engine mechanic ships — defaults to status "unverified" so modeled-but-untested coverage is visible and never drifts. Use at the end of add-skill/add-stat/add-condition/add-hero-trait/add-support, or when porting an in-game verification result. Scaffold + checklist; approval-gated.
---

# add-verification

Keeps the Verification Knowledge Base in lockstep with the engine. **Every shipped mechanic gets an entry** —
even an empty one (status `unverified`) — so the KB never silently falls behind. **Approval-gated.**

Source of truth: `data/verification/<id>.json` (one file per entry). It is served in-app at
`/api/verification-db` and rendered to markdown by `backend/tools/gen_verification_docs.py`. Schema + live
examples: `data/verification/collapse.json` (confirmed), `spell-burst.json` (partial).

## 1. Decide the entry
- **id** — kebab-case, matches the mechanic/skill (e.g. `wind-rhythm`, `licorice-note`). One entry per mechanic;
  a skill used by several mechanics is listed under each relevant entry's `skills`.
- **status** — default **`unverified`** (engine models it, no in-game test yet). Use `pending` if a test is
  queued in `docs/INGAME_VERIFICATION_BACKLOG.md`; `partial`/`confirmed` only with real data; `failed` if a
  test disproved the model (record the fix in `notes`).
- Check for an existing entry first — **update it, don't duplicate.**

## 2. Propose (do not write yet)
Fill `templates/entry.json` (in this skill folder):
- `title`, `skills`, `tags` (grep vocabulary: `tick-rounding`, `breakpoint`, `damage-pool`, `conversion`,
  `uptime`, `trigger`, `step-function`, `rhythm`, `methodology`, …).
- `sources` — ALWAYS cite the engine module + any test + relevant `memory:` note, so the mechanic is
  replicable from the entry alone. This is the point of an unverified entry.
- `backlogId` — cross-link if a backlog test exists.
- Leave `setup`/`dataPoints`/`formula` empty for `unverified` (that's expected — do NOT invent numbers).
Show the owner the filled JSON for sign-off.

## 3. Apply (after approval)
- [ ] Write `data/verification/<id>.json`.
- [ ] Regenerate docs: `py -3.12 backend/tools/gen_verification_docs.py` (updates `docs/verification/README.md`
      + `<id>.md` — generated artifacts, never hand-edited).

## 4. Verify
- The `engine-verify` skill's drift-check step reports any registered skill / new subsystem lacking an entry —
  make sure this new entry clears it.
- Do **not** commit. Surface anything uncertain to the owner ([[feedback_flag_uncertainties]]).
