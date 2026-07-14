from __future__ import annotations
import math
import re
from engine.affix_identity import affix_identity
from engine.models import BuildInput, BuildSource, SourceEntry


def _emit(source: BuildSource, stat: str, amount: float, scope: str | None, entry: SourceEntry,
          slot: int | None = None) -> None:
    """Route a contribution 3 ways: slot-local → add_slotted (folds only into that slot's offense pass);
    else scoped → add_scoped (folds per-skill via materialize_for_skill); else → add_with_source (the
    existing global path). The entry carries slot/scope so source-attribution stays correct. Identical to
    the old 2-way behavior when slot is None (the only case outside per-slot supports)."""
    if slot is not None:
        source.add_slotted(stat, amount, slot, scope, entry)
    elif scope:
        entry.scope = scope
        source.add_scoped(stat, amount, scope, entry)
    else:
        source.add_with_source(stat, amount, entry)

# NOTE: pact-spirit / hero-memory resolution moved to server._resolve_effect_modifiers (the unified
# pool-strict path). The aggregator now only APPLIES the pre-resolved contributions (see
# _apply_effect_contribs); the old _MEMORY_STAT_LOOKUP / alias / multi tables were retired.


# Base effects granted per point of Fervor Rating, each multiplied by Fervor Effect
# (fervor_effect_inc). Today just generic Critical Strike Rating; extend as items add more.
#   (stat_key, amount_per_point, source_text)
_FERVOR_BASE_EFFECTS: list[tuple[str, float, str]] = [
    ("crit_rating_inc", 0.02, "+2% Critical Strike Rating per Fervor Rating"),
]

# Numbed: base additional Lightning Damage the TARGET takes per stack, scaled by Numbed Effect
# (numbed_effect_inc). Modelled engine-side like Fervor — the per-stack value lives here, not on the
# condition. A core talent can override this base (e.g. +11%) — not wired yet (core talents
# unmodelled). Source: glossary id 762 / TLI Help DB …/Statuses/Ailment/Numbed.md.
_NUMBED_BASE_PER_STACK = 0.05

# ── Six Gods' Blessings ───────────────────────────────────────────────────────
# Each blessing grants a per-stack BASE effect, scaled by its user-set stack count. Stacks of ONE
# blessing ADD (Focus 4 → +20% additional damage as a single factor, like Numbed). Source: TLI Help DB
# /Battle Mechanics/Statuses/Six Gods' Blessings. Note the wording split: damage is "additional"
# (multiplicative pool), but Agility's "Attack Speed and Cast Speed" is unqualified = the increased pool.
#   blessing_condition_key → [(stat_key, per_stack_amount, source_text), ...]   (% stored as fractions)
_BLESSING_DEFAULT_EFFECTS: dict[str, list[tuple[str, float, str]]] = {
    "focus_blessings": [
        ("dmg_additional", 0.05, "+5% additional damage per Focus Blessing"),
    ],
    "agility_blessings": [
        ("attack_speed_inc", 0.04, "+4% Attack Speed per Agility Blessing"),
        ("cast_speed_inc",   0.04, "+4% Cast Speed per Agility Blessing"),
        ("dmg_additional",   0.02, "+2% additional damage per Agility Blessing"),
    ],
    "tenacity_blessings": [
        ("dmg_taken_additional", -0.04, "-4% additional Damage Taken per Tenacity Blessing"),
    ],
}
_BLESSING_LABELS: dict[str, str] = {
    "focus_blessings": "Focus Blessing",
    "agility_blessings": "Agility Blessing",
    "tenacity_blessings": "Tenacity Blessing",
}

# Override hook: a core talent / belt blend can "Change the base effect of X Blessing to:" a different
# per-stack effect, which REPLACES the default above. Each override flag (a boolean condition set
# server-side when the granting talent/blend is present, after dedup) maps to one-or-more
# (blessing_key, new effect list) pairs — a single flag can re-base several blessings at once (Divine
# Grace re-bases all three). The application loop below swaps in the override whenever its flag is active.
# Wired SS12 overrides:
#   Sacrifice    (core_sacrifice)  → Tenacity becomes offensive: +8% additional damage per stack
#   Divine Grace (divine_grace, an aromatic belt blend) → Focus/Agility/Tenacity each grant +4%
#                additional damage AND -4% additional Damage Taken per stack
# Mind Focus (Focus → flat Physical = 1% Max Mana to Attacks/Spells) needs a post-derive max-mana step;
# deferred to v2.
#   override_flag → [(blessing_key, [(stat_key, per_stack_amount, source_text), ...]), ...]
_BLESSING_OVERRIDES: dict[str, list[tuple[str, list[tuple[str, float, str]]]]] = {
    "core_sacrifice": [
        ("tenacity_blessings", [
            ("dmg_additional", 0.08, "+8% additional damage per Tenacity Blessing (Sacrifice)"),
        ]),
    ],
    "divine_grace": [
        ("focus_blessings", [
            ("dmg_additional", 0.04, "+4% additional damage per Focus Blessing (Divine Grace)"),
            ("dmg_taken_additional", -0.04, "-4% additional Damage Taken per Focus Blessing (Divine Grace)"),
        ]),
        ("agility_blessings", [
            ("dmg_additional", 0.04, "+4% additional damage per Agility Blessing (Divine Grace)"),
            ("dmg_taken_additional", -0.04, "-4% additional Damage Taken per Agility Blessing (Divine Grace)"),
        ]),
        ("tenacity_blessings", [
            ("dmg_additional", 0.04, "+4% additional damage per Tenacity Blessing (Divine Grace)"),
            ("dmg_taken_additional", -0.04, "-4% additional Damage Taken per Tenacity Blessing (Divine Grace)"),
        ]),
    ],
}

def blessings_summary(active_booleans, numeric_vals, source) -> list[dict]:
    """Per-blessing display summary: current stacks, max stacks, and the (post-override) per-stack effects.
    Reuses the same tables the aggregator applies, so the panel always matches what's actually granted."""
    out: list[dict] = []
    for bkey, default_effects in _BLESSING_DEFAULT_EFFECTS.items():
        stacks = float((numeric_vals or {}).get(bkey, 0.0) or 0.0)
        short = bkey.replace("_blessings", "")
        maximum = 4.0 + source.total(f"max_{short}_blessing_stacks_flat")
        effects = default_effects
        for flag, pairs in _BLESSING_OVERRIDES.items():
            if flag not in (active_booleans or frozenset()):
                continue
            ov = next((eff for tb, eff in pairs if tb == bkey), None)
            if ov is not None:
                effects = ov
                break
        out.append({
            "type": bkey,
            "label": _BLESSING_LABELS.get(bkey, bkey),
            "stacks": stacks,
            "max": maximum,
            "overridden": effects is not default_effects,
            "effects": [{"stat": sk, "per_stack": per, "total": per * stacks, "text": text}
                        for sk, per, text in effects],
        })
    return out


# Flat base effects granted while dual wielding (gated by the auto-set 'dual_wielding' condition).
# Fixed amounts — not scaled (an item can convert the block-chance portion to block ratio, but that
# conversion isn't modeled yet). Block chance isn't consumed by the engine yet (block defense NYI).
#   (stat_key, amount, source_text)   — % stats stored as fractions
_DUAL_WIELD_BASE_EFFECTS: list[tuple[str, float, str]] = [
    ("attack_block_chance_inc", 0.30, "+30% Attack Block Chance (Dual Wield)"),
    ("attack_speed_additional", 0.10, "+10% additional Attack Speed (Dual Wield)"),
]

# Hasten (community name; game tooltip "Quickness", glossary id 10000106): a keyword buff granting +8%
# ADDITIONAL Attack/Cast/Move Speed (+ Mobility-Skill CDR, a non-DPS sub-effect not separately modeled — no
# stat key). Applied while the auto-set 'has_hasten' condition is on. The "+N% when having Hasten" gear
# PAYOFF lines (increased pool) are separate contributions parsed off their own gear text — not here.
_HASTEN_BASE_EFFECTS: list[tuple[str, float, str]] = [
    ("attack_speed_additional",   0.08, "+8% additional Attack Speed (Hasten)"),
    ("cast_speed_additional",     0.08, "+8% additional Cast Speed (Hasten)"),
    ("movement_speed_additional", 0.08, "+8% additional Movement Speed (Hasten)"),
]

# Attack Aggression (glossary id 10000100): "Additionally increases Attack Speed and Attack Damage by 5%.
# Increases Movement Speed by 10%." AS/attack-dmg are the ADDITIONAL pool; Move Speed is the increased pool.
# Gained on attack-skill cast → applied while the auto-set 'attack_aggression' condition is on.
_ATTACK_AGGRESSION_BASE_EFFECTS: list[tuple[str, float, str]] = [
    ("attack_speed_additional", 0.05, "+5% additional Attack Speed (Attack Aggression)"),
    ("attack_dmg_additional",   0.05, "+5% additional Attack Damage (Attack Aggression)"),
    ("movement_speed_inc",      0.10, "+10% Movement Speed (Attack Aggression)"),
]

_NODE_TYPE_LABELS = {
    "micro": "Micro",
    "medium": "Medium",
    "legendary_medium": "Legendary",
}

_SLATE_KIND_LABELS = {
    "pedigree":                       "Pedigree",
    "fallen_starlight":               "Starlight",
    "corner_of_divinity":             "Corner",
    "spark_of_moth_fire":             "Moth",
    "when_sparks_set_prairie_ablaze": "Prairie",
}

_COPY_SLATE_KINDS = frozenset({"spark_of_moth_fire", "when_sparks_set_prairie_ablaze"})
_MOTH_DELTAS: dict[str, tuple[int, int]] = {
    "above": (-1, 0),
    "below": (1, 0),
    "left":  (0, -1),
    "right": (0, 1),
}

def _slate_positions(slate: dict) -> list[tuple[int, int]]:
    # cells are stored as absolute board positions, not relative offsets
    return [tuple(c) for c in slate.get("cells", [])]

def _node_type_display(node_type: str) -> str:
    return _NODE_TYPE_LABELS.get(node_type, node_type.replace("_", " ").title())

def _normalize_node_type(raw: str) -> str:
    """Normalize season node_type strings to filter recipe keys.

    Season data: "Micro Talent", "Medium Talent", "Legendary Medium Talent"
    Filter keys: "micro", "medium", "legendary_medium"
    """
    s = raw.lower().replace(" talent", "").strip().replace(" ", "_")
    return s

# node_id format: "{tree_slug}_c{col}_r{row}"
_NODE_ID_RE = re.compile(r"^(.+)_c\d+_r\d+$")


def _tree_slug_from_node_id(node_id: str) -> str | None:
    m = _NODE_ID_RE.match(node_id)
    return m.group(1) if m else None


def _eval_condition(
    expr,
    active_booleans: frozenset[str],
    numeric_vals: dict[str, float],
) -> bool | float:
    """Evaluate a condition expression.

    Returns True/False for boolean/comparison ops.
    Returns a float multiplier for 'per' scaling ops (0.0 means skip contribution).
    """
    if expr is None:
        return True
    if isinstance(expr, str):
        return expr in active_booleans
    if "const" in expr:               # benign always-on clause (e.g. "when casting a skill")
        return expr["const"]
    if "and" in expr:
        # Mixed per-scaling + boolean gate ("for each X while Y"): every boolean must hold (else skip),
        # and the per-scaling floats MULTIPLY. Return the product (gated), or True if there are no floats.
        prod, saw_float = 1.0, False
        for e in expr["and"]:
            r = _eval_condition(e, active_booleans, numeric_vals)
            if isinstance(r, bool):
                if not r:
                    return False
            else:
                if r == 0.0:
                    return 0.0
                saw_float = True
                prod *= r
        return prod if saw_float else True
    if "or" in expr:
        return any(_eval_condition(e, active_booleans, numeric_vals) for e in expr["or"])
    if "not" in expr:
        return not _eval_condition(expr["not"], active_booleans, numeric_vals)
    if "op" in expr:
        op = expr["op"]
        if op == "per":
            divisor = float(expr.get("divisor", 1))
            val = numeric_vals.get(expr["key"], 0.0)
            return float(math.floor(val / divisor)) if divisor > 0 else 0.0
        lhs = numeric_vals.get(expr["key"], 0.0)
        rhs = expr["value"]
        return (lhs >= rhs if op == ">=" else lhs > rhs if op == ">" else
                lhs <= rhs if op == "<=" else lhs < rhs if op == "<" else
                lhs == rhs if op == "==" else False)
    return False


def _extract_cond_keys(expr, out: set) -> None:
    """Collect every condition key an expression references (regardless of whether it currently holds), so the UI
    can hide conditions no build mod references. Mirrors the expression shapes in _eval_condition; `const` is a
    benign always-on clause (no key)."""
    if expr is None:
        return
    if isinstance(expr, str):
        out.add(expr)
        return
    if not isinstance(expr, dict) or "const" in expr:
        return
    if "and" in expr:
        for e in expr["and"]:
            _extract_cond_keys(e, out)
    elif "or" in expr:
        for e in expr["or"]:
            _extract_cond_keys(e, out)
    elif "not" in expr:
        _extract_cond_keys(expr["not"], out)
    elif "key" in expr:
        out.add(expr["key"])


def _apply_effect_contribs(source, contribs, source_type, label, active_booleans, numeric_vals,
                           stamp=None):
    """Apply pre-resolved pact-spirit / hero-memory contributions (server._resolve_effect_modifiers).
    Gates on the optional translated `condition` exactly like the gear-contribution loop: boolean → on/off,
    'per'/float → scale the amount (capped if the expr carries a cap). Scoped contributions route to
    add_scoped via _emit."""
    for contrib in contribs:
        stat = contrib.get("stat_key")
        if not stat:
            continue
        amount = float(contrib.get("amount", 0))
        cond = contrib.get("condition")
        _extract_cond_keys(cond, source.referenced_conditions)
        if cond is not None:
            cond_result = _eval_condition(cond, active_booleans, numeric_vals)
            if isinstance(cond_result, float):
                if cond_result == 0.0:
                    continue
                amount *= cond_result
                if isinstance(cond, dict) and "cap" in cond:
                    amount = min(amount, float(cond["cap"]))
            elif not cond_result:
                continue
        entry = SourceEntry(stat=stat, amount=amount, source_type=source_type, label=label,
                            text=contrib.get("text", ""), points=1,
                            source_name=contrib.get("source"),
                            pooling_uuid=stamp(contrib.get("text")) if stamp else None)
        # slot-local contributions (e.g. Licorice Note's per-scent-bottle Elixir Effect) route to add_slotted;
        # default None → unchanged global/scoped behavior for every existing trait/spirit/memory contribution.
        _emit(source, stat, amount, contrib.get("scope"), entry, slot=contrib.get("slot"))


def aggregate(
    build: BuildInput,
    season_trees: dict[str, dict],
    filter_data: dict,
    active_booleans: frozenset[str] | None = None,
    numeric_vals: dict[str, float] | None = None,
    identity_index: dict[str, str] | None = None,
) -> BuildSource:
    """
    Collect all stat contributions from talent nodes and slates into a BuildSource.

    season_trees:    {tree_slug: season_tree_dict} — pre-loaded season tree data
    filter_data:     the node_type_filter.json dict with a "recipes" key
    active_booleans: derived from build.condition_state by the fixed-point engine; if None, derived here
                     for backward-compat single-call usage — pre-seeded from each condition's catalog
                     default (models.conditions.condition_defaults()) then overlaid with
                     build.condition_state, so an explicit value (including an explicit 0/False) always
                     wins and only a truly absent key falls back to its default
    numeric_vals:    numeric condition values (clamped) for scaling/threshold evaluation; same
                     catalog-default pre-seed + overlay applies when None
    identity_index:  affix_identity(text) → minted pooling_uuid (engine/identity_index.py); None
                     (tests/legacy) → entries stay uuid-less and pool by text identity as before
    """
    source = BuildSource()
    # Attach the index for offense's pool_identity — the pooling key is a PURE function of each
    # entry's text through this index, so same-wording entries key identically regardless of which
    # emit path produced them (see engine/modifier_lines.pool_identity).
    source.identity_index = identity_index

    # Stamp a DEFINITION-level contribution's minted pooling identity. Applied ONLY to the gear /
    # character / spirit / memory / trait / custom loops below — NEVER to supports, core talents, or
    # node/slate contributions: those carry deliberately-unique minted-suffix texts (`|item_id|role`,
    # `|core|<name>`, `|tag|node_id`) so per-instance copies MULTIPLY; a definition-level uuid would
    # collapse them into ADD (a DPS regression). Suffixed texts can't hit the index anyway (it holds
    # only catalog lines), but the rule is enforced here, not left to that accident.
    def _stamp(text) -> str | None:
        if not identity_index or not text:
            return None
        return identity_index.get(affix_identity(text))

    # Backward-compat single-call derivation (the fixed-point loop in engine.compute normally pre-derives
    # and passes both views via its own _derive_views, which applies the SAME catalog-default fallback).
    # Pre-seeded from each condition's catalog default, then overlaid with build.condition_state — an
    # explicit value (including an explicit 0/False) always wins; only a truly ABSENT key falls back.
    if active_booleans is None or numeric_vals is None:
        from models.conditions import condition_defaults
        bool_defaults, numeric_defaults = condition_defaults()
    if active_booleans is None:
        active_booleans = {k for k, v in bool_defaults.items() if v}
        for k, v in build.condition_state.items():
            if isinstance(v, bool):
                if v:
                    active_booleans.add(k)
                else:
                    active_booleans.discard(k)
        active_booleans = frozenset(active_booleans)
    if numeric_vals is None:
        numeric_vals = dict(numeric_defaults)
        for k, v in build.condition_state.items():
            if not isinstance(v, bool) and isinstance(v, (int, float)):
                numeric_vals[k] = float(v)

    # Talent-tree nodes + slate slots (incl. Moth/Prairie copy) are now resolved server-side through the
    # unified resolver (engine.node_resolver.resolve_nodes) and injected as build.node_contributions,
    # consumed in the node-contributions loop below — no more precomputed recipes.

    # ── Equipped gear affixes ──────────────────────────────────────────────────
    for contrib in (c for item in build.gear for c in item.get("contributions", [])):
        stat = contrib.get("stat")
        if not stat:
            continue
        cond = contrib.get("condition")
        _extract_cond_keys(cond, source.referenced_conditions)
        if cond is not None:
            cond_result = _eval_condition(cond, active_booleans, numeric_vals)
            if isinstance(cond_result, float):
                if cond_result == 0.0:
                    continue
                scaled = contrib.get("display_value", 0) * cond_result
                if isinstance(cond, dict) and "cap" in cond:
                    scaled = min(scaled, float(cond["cap"]))
                contrib = {**contrib, "display_value": scaled}
            elif not cond_result:
                continue
        val = contrib.get("display_value", 0)
        unit = contrib.get("unit", "")
        amount = val / 100.0 if unit == "%" else float(val)
        _gslot = contrib.get("slot")
        slot_label = (_gslot or "item").replace("1", " 1").replace("2", " 2").title()
        entry = SourceEntry(
            stat=stat,
            amount=amount,
            source_type="gear",
            label=f"Gear · {slot_label}",
            # Affix raw_text is the per-affix pooling identity (Option A); fall back to item name.
            text=contrib.get("text") or contrib.get("item_name", ""),
            # Item NAME for the breakdown "Source Name" column + item-tooltip match (distinct from `text`).
            source_name=contrib.get("item_name") or None,
            points=1,
            # Preserve weapon identity so offense can scope a main-hand-only modifier to the weapon1 base.
            weapon_slot=_gslot if _gslot in ("weapon1", "weapon2") else None,
            pooling_uuid=_stamp(contrib.get("text") or contrib.get("item_name", "")),
        )
        _emit(source, stat, amount, contrib.get("scope"), entry)

    # ── Character contributions (energy base/gear/level/prism) ─────────────────
    for contrib in build.character:
        stat = contrib.get("stat")
        if not stat:
            continue
        amount = float(contrib.get("amount", 0))
        entry = SourceEntry(
            stat=stat,
            amount=amount,
            source_type="character",
            label=f"Character · {contrib.get('label', '')}",
            text=contrib.get("text", ""),
            points=1,
            pooling_uuid=_stamp(contrib.get("text")),
        )
        source.add_with_source(stat, amount, entry)

    # ── Pact Spirit + Hero Memory contributions (pre-resolved server-side) ─────
    # Resolved by server._resolve_effect_modifiers (the unified pool-strict path; replaces the old
    # _MEMORY_STAT_LOOKUP). Spirit→memory order preserved (multiplicative-pool order); conditional effects
    # gated in _apply_effect_contribs.
    _apply_effect_contribs(source, build.spirit_contributions, "pact_spirit", "Pact Spirit", active_booleans, numeric_vals, stamp=_stamp)
    _apply_effect_contribs(source, build.memory_contributions, "hero_memory", "Hero Memory", active_booleans, numeric_vals, stamp=_stamp)
    # Hero-trait contributions: for a bespoke trait these are recomputed each pass by its hero_traits module
    # (loop-top) so MS↔Numbed coupling converges; folded here BEFORE the Numbed block so additional Numbed
    # Effect is in source when numbed_lightning_taken is computed.
    _apply_effect_contribs(source, getattr(build, "trait_contributions", None) or [],
                           "hero_trait", "Hero Trait", active_booleans, numeric_vals, stamp=_stamp)

    # ── Custom mod contributions ──────────────────────────────────────────────
    for contrib in build.custom_contributions:
        stat = contrib.get("stat_key")
        if not stat:
            continue
        amount = float(contrib.get("amount", 0))
        cond = contrib.get("condition")            # gate split off server-side (e.g. "vs Low Life enemies")
        _extract_cond_keys(cond, source.referenced_conditions)
        if cond is not None:
            cond_result = _eval_condition(cond, active_booleans, numeric_vals)
            if isinstance(cond_result, float):
                if cond_result == 0.0:
                    continue
                amount *= cond_result
            elif not cond_result:
                continue
            if isinstance(cond, dict) and "cap" in cond:
                amount = min(amount, float(cond["cap"]))
        entry = SourceEntry(
            stat=stat,
            amount=amount,
            source_type="custom",
            label="Custom Config",
            text=contrib.get("text", ""),
            points=1,
            pooling_uuid=_stamp(contrib.get("text")),
        )
        _emit(source, stat, amount, contrib.get("scope"), entry)

    # ── Support skill contributions ───────────────────────────────────────────
    # Pre-resolved from the main skill's attached supports (engine/support_resolver.py). Each carries a
    # UNIQUE text (support id + role), so offense's per-affix pooling treats every support line as its
    # own multiplicative factor — confirmed in-game (they all multiply; nothing sums).
    for contrib in getattr(build, "attached_support_contributions", []) or []:
        stat = contrib.get("stat_key")
        if not stat:
            continue
        amount = float(contrib.get("amount", 0))
        cond = contrib.get("condition")            # gated specific-tier line ("…when only 1 enemy nearby")
        _extract_cond_keys(cond, source.referenced_conditions)
        if cond is not None:
            cond_result = _eval_condition(cond, active_booleans, numeric_vals)
            if isinstance(cond_result, float):
                if cond_result == 0.0:
                    continue
                amount *= cond_result
            elif not cond_result:
                continue
            # Capped per-condition contributions (e.g. Desperation "…up to 38%"): clamp after the per/×
            # scaling, mirroring the gear loop and _apply_effect_contribs.
            if isinstance(cond, dict) and "cap" in cond:
                amount = min(amount, float(cond["cap"]))
        entry = SourceEntry(
            stat=stat,
            amount=amount,
            source_type="support",
            label=contrib.get("label", "Support"),
            text=contrib.get("text", ""),
            source_name=contrib.get("source_name"),
            points=1,
        )
        # A support belongs to its host skill's SLOT (default 1) — fold only into that slot's offense so
        # two same-skill setups never share supports. slot=1 keeps single-slot DPS byte-identical.
        _emit(source, stat, amount, contrib.get("scope"), entry, slot=contrib.get("slot"))

    # ── Core-talent contributions (roadmap #4) ────────────────────────────────
    # Pre-resolved + deduped server-side (server.resolve_core_talents): every granted core talent,
    # slate core, legendary-granted talent, and equipped belt blend, counted exactly ONCE. Each carries
    # a UNIQUE text (|core|<name>), so distinct talents' additional-damage lines multiply in offense's
    # per-affix pool. A `condition_expr` (translated from the talent's conditional clause) gates/scales
    # the contribution in-loop against the converged conditions — boolean → on/off, 'per' → ×floor(val).
    for contrib in getattr(build, "core_talent_contributions", []) or []:
        if contrib.get("set_value"):
            continue   # final-override set-values are applied in compute's derive step, not added here
        stat = contrib.get("stat_key")
        if not stat:
            continue
        amount = float(contrib.get("amount", 0))
        cond = contrib.get("condition_expr")
        _extract_cond_keys(cond, source.referenced_conditions)
        if cond is not None:
            cond_result = _eval_condition(cond, active_booleans, numeric_vals)
            if isinstance(cond_result, float):
                if cond_result == 0.0:
                    continue
                amount *= cond_result
            elif not cond_result:
                continue
        _emit(source, stat, amount, contrib.get("scope"), SourceEntry(
            stat=stat,
            amount=amount,
            source_type="core_talent",
            label=contrib.get("label", "Core Talent"),
            text=contrib.get("text", ""),
            source_name=contrib.get("tree"),   # granting tree → UI colors the source by tree branch
            points=1,
        ))

    # ── Talent-tree node + slate contributions (unified resolver, server.resolve_nodes) ───────────────
    # Pre-resolved + points-scaled; conditional lines gated/scaled in-loop against the converged conditions
    # exactly like core talents. Replaces the old recipe-based node/slate loops.
    for contrib in getattr(build, "node_contributions", []) or []:
        stat = contrib.get("stat_key")
        if not stat:
            continue
        amount = float(contrib.get("amount", 0))
        cond = contrib.get("condition_expr")
        _extract_cond_keys(cond, source.referenced_conditions)
        if cond is not None:
            cond_result = _eval_condition(cond, active_booleans, numeric_vals)
            if isinstance(cond_result, float):
                if cond_result == 0.0:
                    continue
                amount *= cond_result
            elif not cond_result:
                continue
        src_type = "slate" if "|slate|" in contrib.get("text", "") else "talent"
        _emit(source, stat, amount, contrib.get("scope"), SourceEntry(
            stat=stat, amount=amount, source_type=src_type,
            label=contrib.get("label", "Talent"), text=contrib.get("text", ""), points=1,
        ))

    # ── Isomorphic Arms (God of Machines): minions inherit the Main-Hand Weapon's bonuses ─────────────────
    # Glossary "Applied Weapon Bonuses": the weapon's Base Damage + affixes transfer to minions, but NOT its
    # Base Attack Speed / Base Critical Strike Rating. Transfer the main-hand (weapon1) gear contributions to the
    # minion pools via the STRICT remap — which implements that rule for free: base damage (physical_dmg_gear_flat)
    # + affix increased/additional/crit/AS map to their minion pools, while the intrinsic weapon_attack_speed /
    # weapon_crit_rating_flat have no minion equivalent and are DROPPED (never leaked to the player). Runs after
    # core-talent + node contributions so the flag (from either) is set.
    if source.total("minions_inherit_mainhand_weapon") > 0:
        from engine.minion_offense import to_minion_stat_strict
        for _item in build.gear:
            for _c in _item.get("contributions", []):
                if _c.get("slot") != "weapon1":       # main-hand
                    continue
                _st = _c.get("stat")
                _mk = to_minion_stat_strict(_st) if _st else None
                if _mk is None:                        # base AS/crit + anything without a minion twin → not transferred
                    continue
                _v = _c.get("display_value", 0)
                _amt = _v / 100.0 if _c.get("unit") == "%" else float(_v)
                if _amt == 0.0:
                    continue
                source.add_with_source(_mk, _amt, SourceEntry(
                    stat=_mk, amount=_amt, source_type="core_talent", label="Isomorphic Arms",
                    source_name="Isomorphic Arms", text=f"Main-Hand Weapon: {_st}"))

    # ── Fervor mechanics ──────────────────────────────────────────────────────
    # Fervor's BASE effects scale per point of Fervor Rating AND are multiplied by Fervor Effect
    # (fervor_effect_inc). Today the only base effect is +2% (generic) Critical Strike Rating per
    # point; future items may add further base effects that scale the same way — they'd just be
    # added to _FERVOR_BASE_EFFECTS below. Driven off the user-set fervor_rating condition for now
    # (later this may be gated behind the hero trait that grants it). crit_rating_inc is generic
    # (read by both attack and spell crit). fervor_effect_inc is a fraction (0.5 = +50%).
    fervor_rating = float((numeric_vals or {}).get("fervor_rating", 0.0) or 0.0)
    if fervor_rating > 0:
        fervor_effect_mult = 1.0 + source.total("fervor_effect_inc")
        for stat_key, per_point, label_text in _FERVOR_BASE_EFFECTS:
            amount = per_point * fervor_rating * fervor_effect_mult
            source.add_with_source(stat_key, amount, SourceEntry(
                stat=stat_key, amount=amount, source_type="condition",
                label="Fervor Rating", text=label_text, points=1,
            ))

    # ── Numbed (enemy vulnerability) ──────────────────────────────────────────
    # Numbed raises the TARGET's Lightning Damage taken by a base +5% per stack, scaled by Numbed
    # Effect. Stacks ADD (10 × 5% → +50%). Baked into a lightning-tagged stat consumed by offense's
    # enemy-vulnerability stage (NOT the attacker's additional pool). Driven off the user-set
    # numbed_stacks condition (the sustained-stack ramp from Max ES+Life is a later refinement).
    numbed_stacks = float((numeric_vals or {}).get("numbed_stacks", 0.0) or 0.0)
    if numbed_stacks > 0:
        # Conductive (core talent / belt blend) re-bases Numbed from +5% to +11% Lightning Damage taken
        # per stack; Numbed-Effect scaling still multiplies on top. Flag set server-side when present.
        conductive = "core_conductive" in (active_booleans or frozenset())
        base_per_stack = 0.11 if conductive else _NUMBED_BASE_PER_STACK
        # Numbed Effect: increased SUMS into one pool; additional follows the standard additional rule —
        # each DISTINCT source is its own ×(1+x) factor (same-text positives sum), like every other
        # additional pool in the engine. base × (1+Σinc) × Π(1+additional_i).
        from engine.offense import additional_total_product
        per_stack = (base_per_stack
                     * (1.0 + source.total("numbed_effect_inc"))
                     * additional_total_product(source, "numbed_effect_additional"))
        amount = per_stack * numbed_stacks
        text = (f"+{base_per_stack * 100:.0f}% Lightning Damage taken per Numbed stack"
                + (" (Conductive)" if conductive else ""))
        source.add_with_source("numbed_lightning_taken", amount, SourceEntry(
            stat="numbed_lightning_taken", amount=amount, source_type="condition",
            label="Numbed Stacks", text=text, points=1,
        ))

    # ── Frostbite (enemy vulnerability) ───────────────────────────────────────
    # Frostbitten enemies take +1% additional Cold Damage per Frostbite Rating, capped at 120 (the rating
    # above 120 is IGNORED here); Frostbite Effect scales the magnitude. Condensed Frost adds a SEPARATE
    # +0.35%/point for the rating OVER 120 (cap +28%), NOT scaled by Frostbite Effect. frostbite_rating is the
    # auto-derived numeric condition (compute loop). Baked into a cold-tagged stat read by offense's
    # enemy-vulnerability stage. Both pieces are "additional Cold taken" → one additive pool (Tyra-confirmed).
    if "enemy_frostbitten" in (active_booleans or frozenset()):
        rating = float((numeric_vals or {}).get("frostbite_rating", 0.0) or 0.0)
        if rating > 0:
            base = min(rating, 120.0) * 0.01 * (1.0 + source.total("frostbite_effect_inc"))
            over = 0.0
            if "condensed_frost" in (active_booleans or frozenset()) and rating > 120.0:
                over = min((rating - 120.0) * 0.0035, 0.28)   # Condensed Frost, cap +28%
            amount = base + over
            if amount:
                source.add_with_source("frostbite_cold_taken", amount, SourceEntry(
                    stat="frostbite_cold_taken", amount=amount, source_type="condition",
                    label="Frostbite Rating",
                    text=f"+{base * 100:.1f}% Cold Damage taken (Frostbite Rating {rating:.0f})"
                         + (f" +{over * 100:.1f}% (Condensed Frost)" if over else ""),
                    points=1,
                ))

    # ── Bonus propagation: Play Safe (Cast Speed → Spell Burst Charge Speed) ──────
    # When granted (flag stat present), the player's cast-speed INCREASED total and EACH cast-speed
    # ADDITIONAL affix are ALSO applied to Spell Burst Charge Speed (Tyra: charge restoration time =
    # 2 / (1 + chargeSpeed_inc) / Π(1 + chargeSpeed_additional_i)). Spell Burst charge speed isn't consumed
    # by the engine yet, so this populates the stats ready for when it is, without affecting DPS today.
    if source.total("cast_speed_to_spell_burst_charge") > 0:
        # Propagate EACH cast-speed source individually (not one lumped factor), keeping its ORIGINAL attribution
        # (source type / tree node / name) so the charge-speed breakdown shows each as the real cast-speed node —
        # and tree nodes still highlight in the mini-tree on hover. The text notes it's propagated via Play Safe.
        # Snapshot first — add_with_source appends to source_log (don't mutate during iteration).
        cs_inc = [e for e in source.source_log if e.stat == "cast_speed_inc" and e.amount]
        for e in cs_inc:
            source.add_with_source("spell_burst_charge_speed_inc", e.amount, SourceEntry(
                stat="spell_burst_charge_speed_inc", amount=e.amount, source_type=e.source_type,
                label=e.label, text=f"{e.text} → Spell Burst Charge Speed (Play Safe)",
                source_name=e.source_name, points=e.points))
        cs_add = [e for e in source.source_log if e.stat == "cast_speed_additional" and e.amount]
        for e in cs_add:
            source.add_with_source("spell_burst_charge_speed_additional", e.amount, SourceEntry(
                stat="spell_burst_charge_speed_additional", amount=e.amount, source_type=e.source_type,
                label=e.label, text=f"{e.text} → Spell Burst Charge (Play Safe)",
                source_name=e.source_name, points=e.points))

    # ── Bonus propagation: Insatiable Greed (coeff × Attack Speed → Spell Burst Charge Speed) ──
    # Like Play Safe but ×coefficient (150% for Insatiable Greed): each attack-speed source × coeff → charge speed,
    # preserving attribution. Must run AFTER Play Safe so the charge-speed total is complete for the Solid River
    # charge→burst-damage block below.
    ig_coeff = source.total("attack_speed_to_spell_burst_charge")
    if ig_coeff > 0:
        as_inc = [e for e in source.source_log if e.stat == "attack_speed_inc" and e.amount]
        for e in as_inc:
            source.add_with_source("spell_burst_charge_speed_inc", e.amount * ig_coeff, SourceEntry(
                stat="spell_burst_charge_speed_inc", amount=e.amount * ig_coeff, source_type=e.source_type,
                label=e.label, text=f"{e.text} → Spell Burst Charge Speed (Insatiable Greed)",
                source_name=e.source_name, points=e.points))
        as_add = [e for e in source.source_log if e.stat == "attack_speed_additional" and e.amount]
        for e in as_add:
            source.add_with_source("spell_burst_charge_speed_additional", e.amount * ig_coeff, SourceEntry(
                stat="spell_burst_charge_speed_additional", amount=e.amount * ig_coeff, source_type=e.source_type,
                label=e.label, text=f"{e.text} → Spell Burst Charge (Insatiable Greed)",
                source_name=e.source_name, points=e.points))

    # ── Bonus propagation: Solid River (Spell Burst Charge Speed → additional Spell Burst Hit Damage) ──
    # "For every +X% Spell Burst Charge Speed, +Y% additional Hit Damage for skills cast by Spell Burst, up to +Z%."
    # Stepwise (floor) over the post-propagation charge-speed total, capped at Z. Feeds the spell_burst tag pool.
    sr_coeff = source.total("charge_speed_to_spell_burst_hit_dmg")
    sr_per = source.total("charge_speed_to_spell_burst_hit_dmg_per")
    if sr_coeff > 0 and sr_per > 0:
        cs_total = source.total("spell_burst_charge_speed_inc")
        sr_cap = source.total("charge_speed_to_spell_burst_hit_dmg_cap")
        steps = int(cs_total / sr_per)   # floor; "for every +X%"
        amount = steps * sr_coeff
        if sr_cap > 0:
            amount = min(amount, sr_cap)
        if amount:
            source.add_with_source("spell_burst_hit_dmg_additional", amount, SourceEntry(
                stat="spell_burst_hit_dmg_additional", amount=amount, source_type="legendary_gear",
                label="Solid River", text="Solid River: Spell Burst Charge Speed → Spell Burst Hit Damage",
                source_name="Solid River", points=1))

    # ── Bonus propagation: Gale (increased Projectile Speed → additional Projectile Damage) ──
    # additional Projectile Damage = coeff × increased Projectile Speed, as its OWN multiplicative factor
    # (unique text → distinct affix in offense's per-affix pool). FLAGGED for in-game pooling verification.
    gale_coeff = source.total("proj_speed_to_proj_dmg")
    if gale_coeff > 0:
        amount = gale_coeff * source.total("projectile_speed_inc")
        if amount:
            source.add_with_source("projectile_dmg_additional", amount, SourceEntry(
                stat="projectile_dmg_additional", amount=amount, source_type="core_talent",
                label="Core · Gale", text="Gale: Projectile Speed → additional Projectile Damage", points=1))

    # ── Bonus propagation: Movement Speed bonus → Attack/Cast Speed / Cooldown Recovery ──
    # The shared "bonus" is the total movement-speed boost = increased pool × additional pool − 1
    # (reduces to just the increased fraction when there's no additional, so no behavior change).
    ms_inc = (1.0 + source.total("movement_speed_inc")) * (1.0 + source.total("movement_speed_additional")) - 1.0
    if ms_inc:
        for tgt, dest in (("attack_speed", "attack_speed_inc"), ("cast_speed", "cast_speed_inc"),
                          ("cdr", "cdr_speed_inc")):
            coeff = source.total(f"movement_bonus_to_{tgt}")
            if coeff > 0:
                amt = coeff * ms_inc
                source.add_with_source(dest, amt, SourceEntry(
                    stat=dest, amount=amt, source_type="talent",
                    label="Movement Speed Share", text=f"Movement Speed bonus → {dest}", points=1))

    # ── Six Gods' Blessings ───────────────────────────────────────────────────
    # Apply each blessing's per-stack base effect × its user-set stack count. Stacks ADD (one summed
    # entry per stat → one factor). The default effect can be REPLACED by an active override (none wired
    # yet — see _BLESSING_OVERRIDES). Distinct blessings' "additional damage" lines carry distinct text,
    # so the per-affix pool multiplies them. Driven off the user-set *_blessings conditions for now.
    for bkey, default_effects in _BLESSING_DEFAULT_EFFECTS.items():
        stacks = float((numeric_vals or {}).get(bkey, 0.0) or 0.0)
        if stacks <= 0:
            continue
        effects = default_effects
        for flag, pairs in _BLESSING_OVERRIDES.items():
            if flag not in (active_booleans or frozenset()):
                continue
            override_effects = next((eff for tb, eff in pairs if tb == bkey), None)
            if override_effects is not None:
                effects = override_effects
                break
        label = _BLESSING_LABELS.get(bkey, bkey)
        for stat_key, per_stack, text in effects:
            amount = per_stack * stacks
            source.add_with_source(stat_key, amount, SourceEntry(
                stat=stat_key, amount=amount, source_type="condition",
                label=label, text=text, points=1,
            ))

    # ── Dual wielding base effects ────────────────────────────────────────────
    # Granted while wielding two one-handed weapons (the 'dual_wielding' condition is auto-set by the
    # planner from gear). Fixed amounts, not scaled.
    if "dual_wielding" in (active_booleans or frozenset()):
        for stat_key, amount, label_text in _DUAL_WIELD_BASE_EFFECTS:
            source.add_with_source(stat_key, amount, SourceEntry(
                stat=stat_key, amount=amount, source_type="condition",
                label="Dual Wielding", text=label_text, points=1,
            ))

    # ── Hasten & Attack Aggression buff base effects ──────────────────────────
    # Boolean keyword buffs, auto-set in compute when the build has a granting line ("Has Hasten" / "Gain
    # Attack Aggression …"). Fixed additional-pool amounts (distinct source text → their own multiplicative
    # factors in offense). The dual-wield block above is the template.
    if "has_hasten" in (active_booleans or frozenset()):
        for stat_key, amount, label_text in _HASTEN_BASE_EFFECTS:
            source.add_with_source(stat_key, amount, SourceEntry(
                stat=stat_key, amount=amount, source_type="condition",
                label="Hasten", text=label_text, points=1,
            ))
    if "attack_aggression" in (active_booleans or frozenset()):
        for stat_key, amount, label_text in _ATTACK_AGGRESSION_BASE_EFFECTS:
            source.add_with_source(stat_key, amount, SourceEntry(
                stat=stat_key, amount=amount, source_type="condition",
                label="Attack Aggression", text=label_text, points=1,
            ))

    # ── Aim / Euphoria buff base effects ──────────────────────────────────────
    # The Aim skill grants Euphoria: "Ranged and Beam Skills +N% additional damage AND +N% additional Ailment
    # Damage, but -16% Attack and Cast Speed" for 6s (auto-set aim_active from a "Triggers Lv. K Aim …" line).
    # N scales with the Aim LEVEL: +35% at Lv20, -1%/level below → (15 + level)%. The -16% AS/CS is GLOBAL and
    # constant at all levels. Per the skill text, Euphoria is NOT affected by Empower — and aggregator base
    # effects are fixed (never empower-scaled), so this is inherently correct. The +damage lines are Ranged/Beam
    # scoped via add_scoped: dmg_additional (affects hit+ailment) for "+additional damage", plus ailment_dmg_
    # additional (ailment-only) for the separate "+additional Ailment Damage" — each applied to both tags.
    if "aim_active" in (active_booleans or frozenset()):
        _aim_lvl = float((numeric_vals or {}).get("aim_level", 20.0) or 0.0)
        _aim_pct = (15.0 + _aim_lvl) / 100.0
        for stat_key in ("attack_speed_inc", "cast_speed_inc"):
            source.add_with_source(stat_key, -0.16, SourceEntry(
                stat=stat_key, amount=-0.16, source_type="condition",
                label="Aim (Euphoria)", text="-16% Attack and Cast Speed (Aim)", points=1,
            ))
        for tag in ("ranged", "beam"):
            source.add_scoped("dmg_additional", _aim_pct, tag, SourceEntry(
                stat="dmg_additional", amount=_aim_pct, source_type="condition",
                label="Aim (Euphoria)", points=1,
                text=f"+{_aim_pct:.0%} additional Damage for {tag.title()} Skills (Aim Lv {int(_aim_lvl)})"))
            source.add_scoped("ailment_dmg_additional", _aim_pct, tag, SourceEntry(
                stat="ailment_dmg_additional", amount=_aim_pct, source_type="condition",
                label="Aim (Euphoria)", points=1,
                text=f"+{_aim_pct:.0%} additional Ailment Damage for {tag.title()} Skills (Aim Lv {int(_aim_lvl)})"))

    # ── Origin of Thunder (Spirit Magus summoner buff) ────────────────────────
    # Summoning a Thunder Magus grants the SUMMONER "Origin of Thunder": +6% additional Attack AND Cast Speed
    # (constant at all levels) + additional damage scaling with the summon level (2.5% @ Lv1 → 7.25% @ Lv20,
    # +0.25%/level). Both magnitudes scale by Origin of Spirit Magus Effect = (1 + inc) × (1 + additional) —
    # the engine-wide effect-scalar convention. Gated by origin_of_thunder (compute auto-sets it + the level
    # when a Thunder Magus is slotted). Emitted GLOBAL (all skills) via add_with_source, like Aim's AS/CS.
    if "origin_of_thunder" in (active_booleans or frozenset()):
        _ot_lvl = float((numeric_vals or {}).get("origin_of_thunder_level", 20.0) or 20.0)
        _origin_factor = ((1.0 + source.total("spirit_magi_origin_effect_inc"))
                          * (1.0 + source.total("spirit_magi_origin_effect_additional")))
        _ot_speed = 0.06 * _origin_factor
        _ot_dmg = (2.5 + max(0.0, _ot_lvl - 1.0) * 0.25) / 100.0 * _origin_factor
        for _sk, _lbl in (("attack_speed_additional", "Attack"), ("cast_speed_additional", "Cast")):
            source.add_with_source(_sk, _ot_speed, SourceEntry(
                stat=_sk, amount=_ot_speed, source_type="condition",
                label="Origin of Thunder", source_name="Thunder Magus", points=1,
                text=f"+{_ot_speed * 100:.2g}% additional {_lbl} Speed (Origin of Thunder)"))
        source.add_with_source("dmg_additional", _ot_dmg, SourceEntry(
            stat="dmg_additional", amount=_ot_dmg, source_type="condition",
            label="Origin of Thunder", source_name="Thunder Magus", points=1,
            text=f"+{_ot_dmg * 100:.3g}% additional damage (Origin of Thunder Lv {int(_ot_lvl)})"))

    # ── Support-granted buff / debuff base effects (roadmap #2) ────────────────
    _booleans = active_booleans or frozenset()

    # Paralysis: +15% increased damage taken (GLOBAL, all types). The auto-derive (Grudge etc.) sets
    # enemy_paralyzed. Baked into paralysis_dmg_taken, which offense's enemy-vulnerability stage applies
    # to every damage type — so the whole build's DPS on that enemy benefits, not just the granting skill.
    if "enemy_paralyzed" in _booleans:
        source.add_with_source("paralysis_dmg_taken", 0.15, SourceEntry(
            stat="paralysis_dmg_taken", amount=0.15, source_type="condition",
            label="Paralysis", text="+15% increased Damage Taken (Paralysis)", points=1,
        ))

    # Frail: "Additionally increases Spell Damage taken by 15%" — Spell-form scoped. enemy_affected_by_frail
    # is user-set (auto-derive from "Inflicts Frail …" affixes is a follow-up). Scaled by Frail Effect; the
    # offense enemy-vulnerability stage applies frail_spell_taken only when the skill deals Spell damage.
    if "enemy_affected_by_frail" in _booleans:
        _amt = 0.15 * (1.0 + source.total("frail_effect_inc"))
        source.add_with_source("frail_spell_taken", _amt, SourceEntry(
            stat="frail_spell_taken", amount=_amt, source_type="condition",
            label="Frail", text="+15% additional Spell Damage Taken (Frail)", points=1,
        ))

    # Infiltration: "Additionally increases <Fire/Cold/Lightning> Damage taken by 13%" — per element type,
    # scaled by that element's Infiltration Effect. (No Erosion Infiltration exists.)
    for _elem in ("fire", "cold", "lightning"):
        if f"enemy_affected_by_{_elem}_infiltration" in _booleans:
            _amt = 0.13 * (1.0 + source.total(f"{_elem}_infiltration_effect_inc"))
            _name = _elem.capitalize()
            source.add_with_source(f"{_elem}_infiltration_taken", _amt, SourceEntry(
                stat=f"{_elem}_infiltration_taken", amount=_amt, source_type="condition",
                label=f"{_name} Infiltration",
                text=f"+13% additional {_name} Damage Taken ({_name} Infiltration)", points=1,
            ))

    # Electric Overload buff (granted on Critical Strike): +15% additional Lightning Damage.
    if "electric_overload" in _booleans:
        source.add_with_source("lightning_dmg_additional", 0.15, SourceEntry(
            stat="lightning_dmg_additional", amount=0.15, source_type="condition",
            label="Electric Overload", text="+15% additional Lightning Damage (Electric Overload buff)", points=1,
        ))

    # (Willpower's compounding per-stack buff is resolved in support_resolver.resolve_standard_supports,
    # where the support's level is known — its per-stack % is level-specific, e.g. 5.6% at Lv16.)

    return source
