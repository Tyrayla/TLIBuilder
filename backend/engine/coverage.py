"""Build-independent, 3-state "is this entity DPS-modeled" roll-up — Axis A (engine models it) from
`../../.claude/plans/noble-purring-rabbit.md`, distinct from Axis B (this build's `consumed_stats`).

Every function returns ``(status, coverage_detail)`` where ``status`` is one of::

    'full'    — everything the engine can check about this entity resolves to a stat the engine
                actually CONSUMES somewhere (not merely "recognized").
    'partial' — supported/modeled in principle, but at least one piece is unmodeled/unconsumed.
    'none'    — not modeled at all.

``coverage_detail`` lists the human-readable unmodeled pieces (empty for 'full' and for skill/trait
'none' — a skill/trait has no partial detail worth naming when it's entirely unsupported; gear lists
the affix texts even at 'none' so the picker can show what's on the item).

STRICT constraint (owner sign-off, 2026-07-12): "modeled" means a stat the engine actually READS in a
calculation, not merely "the text parses to a stat_key". The single build-independent signal for that is
`engine.consumable_universe.consumable_universe()` — the same set the renderer's `ModifierBadge.classifyKeys`
already uses to split working/inactive (both "in the universe" → modeled) from unused/unrecognized (not in
the universe, or no key at all → NOT modeled). Never invents new classification — every check here is a
reduction over an EXISTING primitive (`resolve_skill`, `classify_intrinsic_line`, `build_tooltip`,
`hero_traits.has_module`/`status_lines`, `consumable_universe`, and the server's shared gear-affix resolver).

Conservative bias throughout: unsure → 'partial' (never silently overclaim 'full'); an item/skill/trait with
zero checkable pieces (no affixes, e.g.) is 'none', never 'full' by vacuous truth.
"""
from __future__ import annotations

import re
from functools import lru_cache

from engine.consumable_universe import consumable_universe


# Support/activation-medium skill_types: never members of `skill_resolver._REGISTRY` (that registry is
# ACTIVE-skill DPS handlers), so gating their coverage on `resolve_skill(...).supported` always reads 'none'
# regardless of how well-modeled the support actually is — a silent, permanent under-claim, and one that made
# the 2026-07-12 accuracy review's "can a support's unmodeled bespoke line read 'full' via a phrase collision"
# question moot only by accident (nothing could ever reach 'full'). These get their own coverage path below.
_SUPPORT_SKILL_TYPES = frozenset({
    "support_skill", "magnificent_support_skill", "noble_support_skill", "activation_medium_skill",
})


def _clause_resolves(clause: str, item_id: str | None, universe: frozenset[str]) -> bool:
    """True if this ONE clause resolves to >=1 confident, CONSUMED stat key. Isolated so a glued
    multi-clause line can gate on every clause independently (see `_reduce_tooltip_lines`)."""
    try:
        from server import _resolve_skill_line_keys
        # strict=True (2026-07-12): coverage only trusts a CONFIDENT resolution — an item-scoped
        # bespoke spec, a structured regex match (added-flat, conditional, capture), or a fuzzy
        # word-overlap hit with no leftover query words. A fuzzy hit that only matched because the
        # line shares an incidental token with a stat's display name (e.g. a mechanic sentence
        # containing the word "additional") does NOT count as modeled here — see
        # `_resolve_skill_line_keys`'s `strict` docstring and `resolve_effect_text_keys_strict`.
        keys = _resolve_skill_line_keys(clause, item_id, strict=True)
    except Exception:
        keys = []
    return bool(keys) and any(k in universe for k in keys)


# The exact boundary `support_mapper._strip_support_target` truncates at ('\s+(?:for|of)\s+(?:the
# supported|this) skill\b.*$' — everything from a "for/of the (supported/this) skill" phrase to the end
# of the string is dropped by the live resolver). Splitting a badge_text's clauses right AFTER this same
# phrase (plus a plain sentence period, always a safe boundary) is the minimal, high-confidence split:
# whatever sits on the far side of the live truncation point is EXACTLY the text the live engine's single
# confident key never accounted for, so it must resolve on its own to count as modeled.
#
# Deliberately narrower than `engine.tooltip._CLAUSE_SPLIT` (built for a different shape — tiered run-on
# `Descript` text — and NOT reused here on purpose): that splitter also breaks before a bare leading
# signed number or a "Buffs"/"Gains"/... keyword, which mis-splits shapes this function sees that
# `_CLAUSE_SPLIT`'s callers don't: a numeric RANGE ("Adds 2 - 3 Cold Damage…" → wrongly split into "Adds 2"
# + "- 3 Cold Damage…", neither of which resolves alone) and a "Buffs grant +N%…" line (wrongly split
# between "grant" and its own value into an orphan "Buffs grant" fragment). A false split manufactures a
# non-clause that can never resolve, flipping an honestly-'full' item to 'partial' for no real reason —
# worse than the overclaim this fix exists to close. Kept coverage-local (a plain copy of the boundary
# regex, not an import) so this can't accidentally start sharing drift with the live `_strip_support_target`
# pattern it's modeling.
_COVERAGE_CLAUSE_BOUNDARY = re.compile(
    r"(?<=\bfor the supported skill)\s+|(?<=\bfor this skill)\s+"
    r"|(?<=\bof the supported skill)\s+|(?<=\bof this skill)\s+|(?<=\.)\s+",
    re.I,
)


def _split_coverage_clauses(text: str) -> list[str]:
    """Split `text` at the `_strip_support_target` truncation boundary (plus sentence periods) into its
    distinct effect clauses. A line with no such boundary (the overwhelming majority — already atomic)
    returns a single-item list unchanged, so this is a no-op for those."""
    return [c.strip() for c in _COVERAGE_CLAUSE_BOUNDARY.split(text or "") if c and c.strip()]


def _reduce_tooltip_lines(skill_data: dict, tooltip: dict, universe: frozenset[str]) -> tuple[bool, list[str]]:
    """Shared reduction over a tooltip's lines for both an active skill and a support/activation-medium item:
    (any_checkable_line_seen, unmodeled_detail_texts). See `skill_coverage`'s docstring for the mechanic-vs-
    flavor split and the `item_id`-scoped resolution this relies on.

    2026-07-12 (glued-clause accuracy fix): a single `badge_text` can carry MULTIPLE distinct effect
    clauses glued with no split boundary the live resolver kept (e.g. a support whose 3 description_lines
    — "+10% Restoration effect for the supported skill", "-26% Restoration Duration for the supported
    skill", "+10% additional damage taken during the supported skill's restoration effect" — collapse into
    one `_FLAT_SPLIT` remainder because that splitter's `(?<!skill)` guard treats each "...skill <sign>N%"
    boundary as a value continuation, not a new clause). Resolving the WHOLE glued blob at once only ever
    reports the FIRST clause's key (the live support mapper's `_strip_support_target` truncates at the
    first "for/of the supported skill" match), so a line with a genuinely unresolved 2nd/3rd clause could
    read fully modeled off the 1st clause's key alone — a real overclaim (`fragile_resurrection`: clause 3,
    `+10% additional damage taken during...restoration`, resolves to `dmg_taken_additional`, a key
    `mod_parser.py` documents as TRACKED ONLY — never wired into any consumer, so never in
    `consumable_universe()`).

    Fix: split the badge_text into its distinct clauses with `_split_coverage_clauses` (a coverage-local
    splitter that mirrors the EXACT boundary `support_mapper._strip_support_target` truncates at, plus a
    plain sentence period — see that function's docstring for why it's narrower than, and NOT the same as,
    `engine.tooltip._split_clauses`) and require EVERY clause to independently resolve to a confident,
    consumed key. An already-atomic line (the overwhelming majority — one clause, no internal "for the
    supported skill" boundary) splits to itself unchanged, so this is a no-op for those. Any clause that
    fails is NOT modeled -> the line contributes to 'partial', and the unresolved clause(s) — not the whole
    glued blob — go to `coverage_detail` so the detail text names the actual gap.

    This is COVERAGE-LOCAL: `_FLAT_SPLIT`/`_strip_support_target`/the live resolver are UNCHANGED (they
    also drop clauses 2+ from the live DPS engine for lines like this — a real but separate, out-of-scope
    bug; see `.wolf/buglog.json`), so badges/`/api/map-modifiers`/DPS are unaffected by this fix."""
    item_id = skill_data.get("item_id")
    checked = False
    detail: list[str] = []
    for ln in tooltip.get("lines") or []:
        if ln.get("coverage") == "modeled":
            checked = True
            continue
        bt = (ln.get("badge_text") or "").strip()
        if not bt:
            continue  # no modifier claim on this line (flavor / intrinsic display / gate) -> not a mechanic
        checked = True
        clauses = _split_coverage_clauses(bt) or [bt]
        unresolved = [cl for cl in clauses if not _clause_resolves(cl, item_id, universe)]
        if not unresolved:
            continue  # every distinct clause resolves to a stat the engine actually reads -> modeled
        if len(clauses) > 1:
            detail.append("; ".join(unresolved))
        else:
            detail.append((ln.get("text") or bt).strip())
    return checked, detail


# ── Activation-medium coverage (2026-07-12, real wiring-derived path) ───────────────────────────
# PRIOR BUG: `engine.tooltip.build_tooltip`'s AM branch blanket-clears `badge_text` for EVERY non-universal
# line on ANY activation-medium item, on the premise "activation mediums are fully handled by the roll
# parser + wiring hook" (true — but that wiring lives in `activation_medium.py`, not in a `badge_text` the
# generic `_reduce_tooltip_lines` reduction can see). Because the tooltip blanks the line before that
# reduction ever runs, `_reduce_tooltip_lines` saw ZERO checkable lines for EVERY activation medium, so
# `skill_coverage` fell through to the support "no checkable line -> 'none'" guard unconditionally — all 28
# activation mediums read 'none' regardless of how well-modeled they actually are (a systematic
# under-claim, the mirror-image failure of the overclaim bugs this module otherwise guards against).
#
# Fix: give activation mediums their OWN coverage path, `_am_coverage` below, derived from the SAME
# machinery that actually wires them — `activation_medium.parse_am_rolls`/`_classify`/`_RANGE` — instead of
# the blanked tooltip. This also folds in (supersedes) the prior fixed-count carve-out: a clause with no
# `(lo-hi)` roll at any tier (Sentry's discrete count, Tangle's "Creates 1 additional Tangle", a flat
# non-tiered clause like Rhythm's "-80% ... manually used Supported Skill") is exactly the `_am_clause_
# modeled` no-`_RANGE`-match branch below, so it's checked once, not twice.
_AM_ALWAYS_APPLIED_SPECIALS = frozenset({"willpower_level"})
# Per-`special` stat key(s) `apply_slot_effects` actually emits for that branch REGARDLESS of the rule's own
# `wired` flag (mirrors that function's if/elif dispatch order exactly — see its source). `willpower_level`
# has no stat_key of its own (it injects a REAL support via `inject_supports`, a genuine DPS-affecting wire
# with nothing to look up in `consumable_universe()`), so it's a separate always-True case, not a keys entry.
_AM_SPECIAL_CONSUMED_KEYS: dict[str, tuple[str, ...]] = {
    "trigger_interval": ("trigger_interval",),
    "wind_share": ("wind_rhythm_share", "wind_rhythm_base_cooldown"),
    "rhythm_move_cap": ("dmg_additional",),
}


def _am_rule_applied_and_consumed(rule: dict, universe: frozenset[str]) -> bool:
    """True iff `activation_medium.apply_slot_effects` would ACTUALLY emit a universe-consumed stat for
    this ONE `_classify` rule dict — not merely "the rule carries a `stat_key`". `apply_slot_effects`'s
    if/elif ladder fires its `special`-keyed branches (trigger_interval / wind_share / rhythm_move_cap /
    willpower_level) REGARDLESS of the rule's own `wired` flag, and only falls through to the plain
    `elif stat_key and r.get("wired")` branch otherwise — so a rule with a `stat_key` but `wired=False`
    (`tangle_attach_range`'s `tangle_attach_range_inc`) is NEVER actually applied by that function even
    though the key itself is a real, CONSUMED stat elsewhere (`offense.py` reads
    `source.total("tangle_attach_range_inc")` for the display-only attach-range figure) — treating it as
    'modeled' here would be exactly the "recognized but nothing ever sets it" overclaim this module exists
    to catch. Likewise `trigger_rate_limit`/`time`/`radius`/`instruction_dmg`/the `misc:*` fallback: real
    values the module's own docstring calls "recorded, not wired"."""
    special = rule.get("special")
    if special in _AM_ALWAYS_APPLIED_SPECIALS:
        return True
    if special in _AM_SPECIAL_CONSUMED_KEYS:
        return any(k in universe for k in _AM_SPECIAL_CONSUMED_KEYS[special])
    stat_key = rule.get("stat_key")
    return bool(stat_key and rule.get("wired") and stat_key in universe)


# A bare (non-parenthesized) leading signed value — a discrete count ("+2 Sentries...", "-1 Sentries..."),
# an optional trailing "%", or a "Creates N additional <Noun>" clause — the FIXED shape `parse_am_rolls`'s
# `_RANGE` regex can never capture (no `(lo-hi)` substring), even when it sits INSIDE a sentence that also
# carries a real ranged roll (Sentry's "+2 Sentries that can be deployed..." lives in the same run-on
# sentence as its dmg/radius rolls; Burst Activation's "-40% Movement Speed for 2 s..." penalty likewise
# glues onto its Hit-Damage roll with no separating period). The `[+\-]` is never preceded by "(" in
# practice (a real range's own sign+lo digit is always immediately followed by "(", never a bare digit+
# unit+word), so this can't false-positive on a roll's own bounds.
_AM_FIXED_COUNT_RE = re.compile(r"[+\-]\s*\d+(?:\.\d+)?\s*%?\s+(?=[A-Za-z])|\bcreates?\s+\d+\s+additional\b", re.I)
_AM_FIXED_SNIPPET_STOP_RE = re.compile(r"\b(?:always|interval:|when|while)\b", re.I)


def _am_fixed_count_snippets(sent: str, range_matches: list) -> list[str]:
    """Human-readable snippets for every fixed-count claim in `sent` that ISN'T part of one of its own
    `range_matches` — the text runs from the count itself up to the next range match / stop keyword / end
    of sentence, so a caller can resolve/report just that claim rather than the whole run-on sentence."""
    out: list[str] = []
    for fm in _AM_FIXED_COUNT_RE.finditer(sent):
        if any(rm.start() <= fm.start() < rm.end() for rm in range_matches):
            continue
        tail = sent[fm.start():]
        end = len(tail)
        stop = _AM_FIXED_SNIPPET_STOP_RE.search(tail, 1)
        if stop:
            end = min(end, stop.start())
        for rm in range_matches:
            if rm.start() > fm.start():
                end = min(end, rm.start() - fm.start())
        snippet = tail[:end].strip()
        if snippet:
            out.append(snippet)
    return out


def _am_other_tier_clauses(skill_data: dict, base_t: int) -> list[str]:
    """Every OTHER tier's split clauses (`engine.tooltip._split_clauses`) — used ONLY by
    `_am_flat_at_base_tier_only` below (the "coincidentally flat at THIS tier" cross-check), never for the
    main modeled/unmodeled decision (which stays on the base tier's own unsplit sentence text — see
    `_am_base_tier_text`'s docstring for why splitting is unsafe there)."""
    from engine.tooltip import _split_clauses
    prog = skill_data.get("progression") or []
    levels = sorted({e.get("level") for e in prog if isinstance(e.get("level"), int)})
    tiers = [t for t in levels if t != 3] or levels
    by_tier = {e.get("level"): (e.get("values") or {}).get("name") or "" for e in prog}
    out: list[str] = []
    for t in tiers:
        if t == base_t:
            continue
        out.extend(_split_clauses(by_tier.get(t, "")))
    return out


def _am_flat_at_base_tier_only(snippet: str, other_tier_clauses: list[str]) -> bool:
    """True if `snippet` — a FIXED, non-parenthesized clause found at the base tier — is actually a real,
    already-wired roll that's simply flat (lo==hi) at this ONE tier, not a genuine `_RANGE`-miss gap: some
    OTHER tier has a template/token-similar clause (`engine.tooltip._is_dup`) that DOES carry a real
    `activation_medium._RANGE` match (an actual `(lo-hi)` NUMERIC range — NOT just a literal "(" substring:
    an English "(s)" plural marker, e.g. Channel's "sends 1 Instruction for every N stack(s) channeled",
    would false-positive on a bare "(" containment check, which is exactly the prior `_am_unmodeled_fixed_
    counts`'s check and a latent bug in it this fix also closes). Motionless's tier-1 "+10% additional
    damage" has no range only because lo==hi there — it's ranged, e.g. "(12-15) %", at every other tier —
    so `parse_am_rolls` DOES capture and wire it (from whichever tier supplies the range); flagging it here
    from the base tier's flat rendering alone would be a false, spurious gap."""
    from engine.tooltip import _is_dup
    from engine.skill_effects.activation_medium import _RANGE
    return any(_is_dup(snippet, oc) and _RANGE.search(oc) for oc in other_tier_clauses)


def _am_base_tier_text(skill_data: dict) -> tuple[int | None, str]:
    """(base_tier, raw_text) — the SAME per-tier text `activation_medium.parse_am_rolls` scans
    (`progression[tier]["values"]["name"]`), UNSPLIT. `base_tier` is None if the item has no selectable
    tiers. Kept unsplit deliberately (see `_am_coverage`'s docstring): splitting into display-oriented
    clauses (`engine.tooltip._split_clauses`) can sever a roll's descriptive lead-in from its own `(lo-hi)`
    value onto a sibling fragment (Rhythm's "...movement made during the trigger interval, up to" / "+(18-
    21) %." split), which breaks `_classify`'s "before"-text keyword match for that roll — the exact bug a
    first draft of this fix hit. Only a SENTENCE split (period-delimited) is used below, which never cuts
    inside a roll's own sentence for any item in the SS12 catalog (verified against all 28)."""
    prog = skill_data.get("progression") or []
    levels = sorted({e.get("level") for e in prog if isinstance(e.get("level"), int)})
    tiers = [t for t in levels if t != 3] or levels          # tier 3 = unselectable penalty tier
    if not tiers:
        return None, ""
    by_tier = {e.get("level"): (e.get("values") or {}).get("name") or "" for e in prog}
    base_t = 1 if 1 in tiers else tiers[0]
    return base_t, by_tier.get(base_t, "")


def _am_coverage(skill_data: dict, universe: frozenset[str]) -> tuple[str, list[str]]:
    """Build-independent coverage for ONE activation medium — replaces the tooltip-blanked default.

    Splits the item's own base-tier text (`_am_base_tier_text`) into SENTENCES (period-delimited, via
    `engine.tooltip._SENTENCE_SPLIT` — the gentlest split available, never severs a roll's own `(lo-hi)`
    value from the keyword context `_classify` needs to read it) rather than tooltip's display-oriented
    clause splitter. Per sentence:
      - No `(lo-hi)` roll at all -> a fixed/flat claim `parse_am_rolls`'s `_RANGE` regex structurally never
        sees (Sentry's discrete Sentry-count, Tangle's "Creates 1 additional Tangle", a flat non-tiered
        clause like Rhythm's "-80% ... manually used Supported Skill"). Not checkable at all if it carries
        no digit (`engine.tooltip._kind_for` — pure flavor/gate text, e.g. "Disabled while any Restoration
        Skill is active"); otherwise falls back to the same generic clause resolver the rest of this module
        uses (`_clause_resolves`) — this is the prior `_am_unmodeled_fixed_counts` carve-out, folded in here
        rather than run as a second pass.
      - >=1 `(lo-hi)` roll -> each is re-classified with `_classify` (the SAME call `parse_am_rolls` makes,
        `before`/`after` scoped to the FULL sentence so multi-roll run-ons — e.g. Boss's CDR+Duration+radius
        sentence, Preparation's "every (X-Y) s ... +(A-B)% additional Cooldown Recovery Speed" — keep the
        context each roll's keyword match needs) and checked via `_am_rule_applied_and_consumed`. Any
        unmodeled roll in the sentence contributes its own `desc` to `coverage_detail` (not the whole
        sentence — so a sentence mixing one modeled and one unmodeled roll, e.g. Sentry's dmg+radius run-on,
        names only the actual gap).
    Zero checkable sentences at all -> 'none' (vacuous truth, matches every other entity type here). Every
    sentence's every roll modeled, and every fixed sentence resolved -> 'full'. Otherwise 'partial'."""
    from engine.tooltip import _kind_for, _SENTENCE_SPLIT, _clean
    from engine.skill_effects.activation_medium import _RANGE, _classify
    item_id = skill_data.get("item_id")
    base_t, raw = _am_base_tier_text(skill_data)
    if base_t is None:
        return "none", []
    text = _clean(raw)
    if not text:
        return "none", []

    other_tier_clauses = _am_other_tier_clauses(skill_data, base_t)
    checked = False
    detail: list[str] = []
    for sent in _SENTENCE_SPLIT.split(text):
        sent = sent.strip()
        if not sent:
            continue
        matches = list(_RANGE.finditer(sent))
        if not matches:
            if _kind_for(sent) == "flavor":
                continue      # no digit at all -> pure flavor/gate text, not a mechanic claim
            checked = True
            if not _clause_resolves(sent, item_id, universe) and not _am_flat_at_base_tier_only(
                    sent, other_tier_clauses):
                detail.append(sent)
            continue
        checked = True
        for m in matches:
            unit = m.group(4) or ""
            after_head = sent[m.end():].split("(")[0]
            rule = _classify(sent[:m.start()], after_head, unit)
            if rule is None:
                detail.append(sent)
            elif not _am_rule_applied_and_consumed(rule, universe):
                detail.append(rule.get("desc") or sent)
        # A fixed-count claim can share a sentence with a real ranged roll (Sentry's "+2 Sentries..." lives
        # in the same run-on as its dmg/radius rolls) — `_RANGE.finditer` above only ever walks the ranged
        # rolls, so check separately for this shape too (folds in the prior fixed-count carve-out).
        for snippet in _am_fixed_count_snippets(sent, matches):
            if not _clause_resolves(snippet, item_id, universe) and not _am_flat_at_base_tier_only(
                    snippet, other_tier_clauses):
                detail.append(snippet)

    if not checked:
        return "none", []
    if detail:
        detail = _dedupe_detail(detail)
    return ("partial", detail) if detail else ("full", [])


def _dedupe_detail(items: list[str]) -> list[str]:
    """The SAME underlying gap can legitimately surface twice — once via a range's own `_classify` `desc`
    (which greedily grabs everything after the match up to the next literal `(` or 80 chars, so an
    un-parenthesized tail clause like Instruction's "-80% ... manually used Supported Skill" rides along
    inside an unrelated roll's `desc`), once via the dedicated fixed-count scan that finds that same tail
    clause on its own. Keep the LONGEST wording of each overlapping gap (drop any entry that's wholly
    contained in one already kept) rather than showing the same gap twice."""
    out: list[str] = []
    for d in sorted((x.strip() for x in items if x and x.strip()), key=len, reverse=True):
        if any(d in existing for existing in out):
            continue
        out.append(d)
    return out


# ── Skill ──────────────────────────────────────────────────────────────────────────────────────
def skill_coverage(skill_data: dict, tooltip: dict | None = None) -> tuple[str, list[str]]:
    """`resolve_skill(...).supported == False` -> 'none' (a support attached to it can't matter — the skill
    computes total_dps == 0.0). Supported: reduce over the tooltip's lines (same lines the /api/skills handler
    already builds via `engine.tooltip.build_tooltip` — pass the already-built dict in `tooltip` to avoid
    recomputing it; a standalone caller may omit it and this builds its own).

    A support/activation-medium item (`skill_type` in `_SUPPORT_SKILL_TYPES`) takes a SEPARATE path
    (2026-07-12): `resolve_skill`'s `_REGISTRY` membership check answers "can a support attached to THIS
    skill matter" for an ACTIVE skill — it doesn't apply to a support ITSELF (supports are never registry
    members, so gating on it would silently read every support as 'none'). A support's own coverage is
    judged purely by whether ITS OWN tooltip lines resolve to a consumed stat, same reduction as below, but
    'none' if the support has ZERO checkable lines at all (mirrors the gear-affix "no affixes -> never 'full'
    by vacuous truth" rule) rather than defaulting to 'full'.

    An activation medium (`is_activation_medium(item_id)`) takes a THIRD, separate path — `_am_coverage`
    (2026-07-12 fix) — instead of the tooltip-line reduction below: `engine.tooltip.build_tooltip` blanks
    `badge_text` on every non-universal AM line unconditionally (by design — AM items are wired through
    `activation_medium.py`'s roll parser, not the generic text resolver), so the reduction below would see
    zero checkable lines for literally every activation medium and always read 'none' regardless of actual
    modeling. `_am_coverage` re-derives real per-line coverage from that item's own wiring instead. See its
    docstring for the mechanic.

    Mechanic-vs-flavor split (uses ONLY existing tooltip signals, invents nothing new):
      - `line["coverage"] == "modeled"` -> counts as modeled. This is set by
        `skill_resolver.classify_intrinsic_line`, which is STRICTLY gated on real `ResolvedSkill` fields that
        genuinely feed `calculate_offense`/`compute_dot` (channeled stack caps, steep-strike, intrinsic
        per-rating additional pools, the per-skill `_SKILL_MODELED_PHRASES` table) — never a text-similarity
        guess. Kept as-is per owner sign-off: these are behavioral flags read directly by the offense/DoT
        stage, not a plain stat_key, so there's no separate "is it in consumable_universe" check to run —
        classify_intrinsic_line IS that check, expressed as Python control flow instead of a stat key.
      - `line["badge_text"]` falsy -> NOT a mechanic line, skipped (no coverage claim either way). By
        construction in `engine.tooltip`, badge_text is only cleared for: pure flavor/intro clauses, the
        intrinsic core damage/"Effectiveness of added damage" lines (the skill's own base, not a modifier),
        install-restriction/gate text, and buff trigger/duration clauses — never for a line making a real
        modifier claim. This is the tooltip module's OWN classification (`_kind_for`, `_BUFF_FLAVOR_RE`,
        `_GENERIC_FLAVOR_RE`, the `_lines_*` builders) — reused here, not reinvented.
      - `line["badge_text"]` truthy -> a genuine modifier-style claim. Resolve it via the SAME resolver the
        skill modifier badge uses (`server._resolve_skill_line_keys`, source='skill' in `/api/map-modifiers`),
        SCOPED to this item's own `item_id` (2026-07-12 accuracy fix — see `skill_effects.resolve_line_keys`'s
        docstring): a bespoke module's `_LINE_SPECS` phrase is plain text-similarity with no notion of which
        support it belongs to, so passing `item_id` stops a genuinely-unmodeled line on support A from
        phrase-colliding with an unrelated module B's spec and borrowing B's stat key (the
        `groundshaker_cripple_noble` case — its NYI "+30% additional Skill Area when the supported skill
        consumes Demolisher Charge" has no spec of its own and must NOT borrow Berserking Blade's Sweep key).
        If it resolves to >=1 stat key AND at least one of those keys is in `consumable_universe()` -> modeled
        (mirrors `ModifierBadge.classifyKeys`: universe membership is the build-independent "modeled" signal,
        working vs inactive is a build-specific detail this roll-up doesn't need). Otherwise — no keys at all
        (NYI/unrecognized) OR keys that resolve but sit outside the universe (recognized, never consumed
        anywhere) — the line counts as an UNMODELED mechanic -> 'partial', text logged to `coverage_detail`.
        This is the one spot a "genuinely ambiguous" line could exist (an oddly-worded clause the fuzzy
        resolver mismatches); per the conservative rule it falls into the same "no keys" bucket -> partial,
        never silently promoted to full.
    supported=True with zero unmodeled mechanic lines -> 'full'.
    """
    stype = skill_data.get("skill_type") or ""
    if stype not in _SUPPORT_SKILL_TYPES:
        from engine.skill_resolver import resolve_skill
        resolved = resolve_skill(skill_data)
        if not resolved.supported:
            return "none", []

    universe = consumable_universe()

    if stype in _SUPPORT_SKILL_TYPES:
        from engine.skill_effects.activation_medium import is_activation_medium
        if is_activation_medium(skill_data.get("item_id")):
            return _am_coverage(skill_data, universe)

    if tooltip is None:
        from engine.tooltip import build_tooltip
        tooltip = build_tooltip(skill_data)

    checked, detail = _reduce_tooltip_lines(skill_data, tooltip, universe)

    if stype in _SUPPORT_SKILL_TYPES and not checked:
        # A support with literally no checkable mechanic line (every line was flavor/gate/install-restriction
        # text) — never 'full' by vacuous truth. (Active skills keep the prior behavior: registry membership
        # already implies real modeling, so this guard is scoped to the newly-added support path only.)
        return "none", []

    return ("partial", detail) if detail else ("full", [])


# ── Hero trait ─────────────────────────────────────────────────────────────────────────────────
# Literal advanced-pick names checked (`"<Name>" in picks`) across every hero_traits/*.py module. Deliberately
# a flat UNION (not per-trait) — dispatch only reads the names its own module cares about, so passing every
# other trait's names too is harmless. Kept in sync by hand when a new trait module ships (mirrors the
# per-module hardcoded literal-string design already used inside hero_traits/*.py itself).
_ALL_ADVANCED_PICKS: tuple[str, ...] = (
    # high_court_chariot
    "Unbreakable Stand", "Whirlwind Advance", "Invulnerability", "Divine Intervention", "Desperation",
    "Improvision",
    # licorice_note
    "Licorice Tincture Blend", "Scent of Ambition", "Elixir of Immortality", "Everlasting Nectar",
    # lightning_shadow
    "Dazzling Lightning", "Electroplated Motif", "Swift as Lightning", "Charging Equation",
    # sing_with_the_tide
    "Undersea Ballad", "Sea Foam Nocturne", "Chantey of Sinking", "Murmurs of the Distant Tide",
    "Idyll of the Tide", "Wave Aria",
    # unsullied_blade
    "Utmost Devotion", "Born to Cleanse", "Cleanse Filth", "Boundless Sanctuary",
    # wind_stalker
    "Cat's Vision", "Interest", "Have Fun", "Cat's Scratch", "Cat's Punches", "Cat Dive",
)
_BAD_STATUS = {"warning", "nyi"}


def trait_coverage(trait_id: str | None) -> tuple[str, list[str]]:
    """`hero_traits.has_module(trait_id) == False` -> 'none' (`dance_of_the_deep` has no bespoke module, so
    this is 'none' with zero special-casing). Modeled: probe `status_lines` at a MAXIMAL, build-independent
    state — every slot at level 5 (so every "Artificial Moon"/tier-gated node line is surfaced) and every
    known advanced pick enabled (so pick-gated lines are surfaced too) — the conservative choice, since 'full'
    should mean "modeled no matter how the trait is built out", not just "modeled at the default state".
    `main_skill_tags`/`attached_supports`/`skills_input`/`skills_by_id`/`prepared_skill` are left at their
    defaults: those describe an interaction with ANOTHER equipped entity (the main skill, other slots) that
    is a build-specific fact, not a property of the trait itself, so they're out of scope for a
    single-argument, build-independent probe (see the report note on `sing_with_the_tide`). `season`
    (2026-07-16 architecture fix) IS supplied concretely — the real active season — because it's a global
    environment fact the probe can always answer, not a build-specific unknown; it's excluded from
    `build_gated_status_params` for the same reason (see `hero_traits._STATUS_BASE_PARAMS`).
    Any `status_lines` entry with status 'warning' or 'nyi' -> 'partial' (its text -> coverage_detail);
    none -> 'full', UNLESS `hero_traits.build_gated_status_params` says this trait's `status_lines` accepts
    build-specific inputs beyond the two universal ones (2026-07-12 accuracy fix): those left-at-default
    inputs can gate an ENTIRE warning branch (e.g. `sing_with_the_tide`'s Bard→Bard-Song main-skill-
    conversion warning, gated on `main_skill_tags is not None` — with NO engine code that actually discounts
    a converted main skill's DPS, this was a genuine gap reading as fully modeled) that this build-
    independent probe can never trip. Conservative rule: if such a gated param exists, this probe cannot
    prove there's no unseen warning, so it downgrades to 'partial' with an explanatory detail line instead
    of silently claiming 'full' by the absence of evidence. Detected structurally (function signature), not
    a hand-maintained per-trait list, so a new gated branch on any future trait is caught automatically.
    """
    from engine import hero_traits
    from persistence import season_manager

    if not hero_traits.has_module(trait_id):
        return "none", []

    lines = hero_traits.status_lines(
        trait_id,
        slot_levels=[5, 5, 5, 5],
        advanced_picks=list(_ALL_ADVANCED_PICKS),
        season=season_manager.get_active_season() or "",
        main_skill_tags=None, main_skill_name=None,
        attached_supports=None, skills_input=None, skills_by_id=None, prepared_skill=None,
    )
    bad = [ln for ln in (lines or []) if ln.get("status") in _BAD_STATUS]
    if bad:
        return "partial", [(ln.get("text") or "").strip() for ln in bad]

    gated = hero_traits.build_gated_status_params(trait_id)
    if gated:
        return "partial", [
            f"status_lines depends on build-specific context ({', '.join(gated)}) this build-independent "
            "probe leaves at default — a warning/NYI branch gated on it may exist without being surfaced "
            "here, so this trait is not claimed 'full'."
        ]
    return "full", []


# ── Legendary gear ─────────────────────────────────────────────────────────────────────────────
def _iter_affixes(item: dict) -> list[dict]:
    """Every DISTINCT affix dict (by raw_text) across every variant (implicits + explicits) of a full
    legendary item record (the `_legendary_gear.json` shape — NOT the lightweight
    `_legendary_gear_index.json` shape, which carries no affix data at all). Keeps the REAL affix dict
    (not just its text) so `_resolve_affix` sees the real `affix_kind`/`condition` — needed for base-weapon
    "special" lines (e.g. "73 - 73 Physical Damage") that only resolve correctly with their own affix_kind,
    not the generic "numeric" default `/api/map-modifiers` uses for arbitrary raw text."""
    seen: set[str] = set()
    out: list[dict] = []
    for variant in (item.get("variants") or {}).values():
        if not isinstance(variant, dict):
            continue
        for group in ("implicits", "explicits"):
            for aff in variant.get(group) or []:
                t = (aff.get("raw_text") or "").strip()
                if t and t not in seen:
                    seen.add(t)
                    out.append(aff)
    return out


def _affix_is_modeled(aff: dict, universe: frozenset[str]) -> bool:
    """True if this ONE affix resolves to >=1 stat key the engine actually reads (`consumable_universe`).
    Mirrors the exact two-step resolution `/api/map-modifiers` uses for `source: 'gear'` (server.py's
    `map_modifiers`) via the shared `server._affix_resolved_keys` (2026-07-12 — the SAME key list is now
    also exposed on `/api/legendary-gear`'s affixes as `resolved_keys`, so a catalog-hover badge and this
    coverage roll-up can never drift apart): the catalog's own per-mod resolver first (`_resolve_affix` +
    `_affix_stat_keys` — the richer single/multi/range/dual-stat + "special" base-weapon-line classifier
    that populates the affix badges the gear catalog actually shows), falling back to the clause-based
    resolver (`_resolve_gear_affix_clauses` — per-N-consumed / condition-gated clauses the single-line
    classifier doesn't split) ONLY when the primary resolver found no stat key at all. Curse infliction is
    the one thing `_affix_resolved_keys` can't report (it feeds `engine.curse_resolver.apply_curses`, a
    genuinely-modeled subsystem, but carries no plain stat_key of its own) — checked here separately, a
    judgment call flagged for review. Imported lazily (inside the function) to avoid a module-load-time
    circular import with `server.py`, which imports this module; by request time both modules are fully
    loaded.
    """
    from server import _resolve_affix, _affix_resolved_keys, _resolve_gear_affix_clauses

    resolved = _resolve_affix(aff)
    keys = _affix_resolved_keys(resolved, aff.get("raw_text") or "")
    if keys:
        return any(k in universe for k in keys)
    # No plain stat key at all (from either resolution step `_affix_resolved_keys` tries) — the one thing
    # left to check is a curse-infliction clause, which resolves to no stat_key by design.
    for cl in _resolve_gear_affix_clauses(aff.get("raw_text") or ""):
        if cl.get("curse"):
            return True
    return False


def legendary_coverage(item: dict) -> tuple[str, list[str]]:
    """STRICT definition (owner sign-off): "modeled" = the affix's stat key(s) are in `consumable_universe()`
    (the engine reads them somewhere), NOT merely "the text parses to a stat_key" — mirrors
    `ModifierBadge.classifyKeys` (working/inactive both count as modeled; unused/unrecognized don't).

    All affixes modeled -> 'full'. >=1 modeled and >=1 not -> 'partial' (the NOT-modeled affix texts in
    coverage_detail). Zero affixes on the item, or none of them modeled -> 'none' (never 'full' by vacuous
    truth on an item with no affixes at all).
    """
    universe = consumable_universe()
    affixes = _iter_affixes(item)
    if not affixes:
        return "none", []

    modeled_count = 0
    detail: list[str] = []
    for aff in affixes:
        if _affix_is_modeled(aff, universe):
            modeled_count += 1
        else:
            detail.append((aff.get("raw_text") or "").strip())

    if modeled_count == len(affixes):
        return "full", []
    if modeled_count == 0:
        return "none", detail
    return "partial", detail


# ── Season-scoped legendary cache (mirrors consumable_universe's @lru_cache; keyed on season so a season
# switch never sees another season's stale results) ─────────────────────────────────────────────────────
@lru_cache(maxsize=8)
def _legendary_coverage_by_season(season: str) -> dict[str, tuple[str, tuple[str, ...]]]:
    from persistence import season_manager

    data = season_manager.load_legendary_gear(season) or {}
    out: dict[str, tuple[str, tuple[str, ...]]] = {}
    for item in data.get("items", []):
        item_id = item.get("item_id")
        if not item_id:
            continue
        status, detail = legendary_coverage(item)
        out[item_id] = (status, tuple(detail))
    return out


def legendary_coverage_for_season(season: str, item_id: str) -> tuple[str, list[str]]:
    """O(1) per-item lookup after the season's first request this process (computes/caches every item's
    coverage once — the plan's "memoize per season, mirror consumable_universe's lru_cache")."""
    status, detail = _legendary_coverage_by_season(season).get(item_id, ("none", ()))
    return status, list(detail)


def invalidate_legendary_coverage_cache() -> None:
    """Call after any legendary-gear import/edit so a re-import's changed affixes aren't served stale
    coverage for the rest of the process lifetime. Clears every season's entry (cheap; imports are rare)."""
    _legendary_coverage_by_season.cache_clear()
