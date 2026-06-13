from __future__ import annotations
import math
import re
from engine.models import BuildInput, BuildSource, SourceEntry


def _emit(source: BuildSource, stat: str, amount: float, scope: str | None, entry: SourceEntry) -> None:
    """Route a contribution: scoped → add_scoped (folds per-skill via materialize_for_skill); unscoped →
    add_with_source (the existing path). The entry carries the scope so source-attribution stays correct."""
    if scope:
        entry.scope = scope
        source.add_scoped(stat, amount, scope, entry)
    else:
        source.add_with_source(stat, amount, entry)

# NOTE: pact-spirit / hero-memory resolution moved to server._resolve_effect_modifiers (the unified
# pool-strict path). The aggregator now only APPLIES the pre-resolved contributions (see
# _apply_effect_contribs); the old _MEMORY_STAT_LOOKUP / alias / multi tables were retired.

_ELEMENTAL_TYPES = {"fire", "cold", "lightning", "erosion"}

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
        ("dmg_taken_additional", -0.04, "-4% Damage Taken per Tenacity Blessing"),
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
#                additional damage AND -4% Damage Taken per stack
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
            ("dmg_taken_additional", -0.04, "-4% Damage Taken per Focus Blessing (Divine Grace)"),
        ]),
        ("agility_blessings", [
            ("dmg_additional", 0.04, "+4% additional damage per Agility Blessing (Divine Grace)"),
            ("dmg_taken_additional", -0.04, "-4% Damage Taken per Agility Blessing (Divine Grace)"),
        ]),
        ("tenacity_blessings", [
            ("dmg_additional", 0.04, "+4% additional damage per Tenacity Blessing (Divine Grace)"),
            ("dmg_taken_additional", -0.04, "-4% Damage Taken per Tenacity Blessing (Divine Grace)"),
        ]),
    ],
}

# Flat base effects granted while dual wielding (gated by the auto-set 'dual_wielding' condition).
# Fixed amounts — not scaled (an item can convert the block-chance portion to block ratio, but that
# conversion isn't modeled yet). Block chance isn't consumed by the engine yet (block defense NYI).
#   (stat_key, amount, source_text)   — % stats stored as fractions
_DUAL_WIELD_BASE_EFFECTS: list[tuple[str, float, str]] = [
    ("attack_block_chance_inc", 0.30, "+30% Attack Block Chance (Dual Wield)"),
    ("attack_speed_additional", 0.10, "+10% additional Attack Speed (Dual Wield)"),
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


def _apply_effect_contribs(source, contribs, source_type, label, active_booleans, numeric_vals):
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
                            text=contrib.get("text", ""), points=1)
        _emit(source, stat, amount, contrib.get("scope"), entry)


def aggregate(
    build: BuildInput,
    season_trees: dict[str, dict],
    filter_data: dict,
    active_booleans: frozenset[str] | None = None,
    numeric_vals: dict[str, float] | None = None,
) -> BuildSource:
    """
    Collect all stat contributions from talent nodes and slates into a BuildSource.

    season_trees:    {tree_slug: season_tree_dict} — pre-loaded season tree data
    filter_data:     the node_type_filter.json dict with a "recipes" key
    active_booleans: derived from build.condition_state by the fixed-point engine; if None,
                     derived here for backward-compat single-call usage
    numeric_vals:    numeric condition values (clamped) for scaling/threshold evaluation
    """
    source = BuildSource()

    if active_booleans is None:
        active_booleans = frozenset(
            k for k, v in build.condition_state.items()
            if isinstance(v, bool) and v
        )
    if numeric_vals is None:
        numeric_vals = {
            k: float(v) for k, v in build.condition_state.items()
            if not isinstance(v, bool) and isinstance(v, (int, float))
        }

    # Talent-tree nodes + slate slots (incl. Moth/Prairie copy) are now resolved server-side through the
    # unified resolver (engine.node_resolver.resolve_nodes) and injected as build.node_contributions,
    # consumed in the node-contributions loop below — no more precomputed recipes.

    # ── Equipped gear affixes ──────────────────────────────────────────────────
    for contrib in (c for item in build.gear for c in item.get("contributions", [])):
        stat = contrib.get("stat")
        if not stat:
            continue
        cond = contrib.get("condition")
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
        slot_label = (contrib.get("slot") or "item").replace("1", " 1").replace("2", " 2").title()
        entry = SourceEntry(
            stat=stat,
            amount=amount,
            source_type="gear",
            label=f"Gear · {slot_label}",
            # Affix raw_text is the per-affix pooling identity (Option A); fall back to item name.
            text=contrib.get("text") or contrib.get("item_name", ""),
            points=1,
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
        )
        source.add_with_source(stat, amount, entry)

    # ── Pact Spirit + Hero Memory contributions (pre-resolved server-side) ─────
    # Resolved by server._resolve_effect_modifiers (the unified pool-strict path; replaces the old
    # _MEMORY_STAT_LOOKUP). Spirit→memory order preserved (multiplicative-pool order); conditional effects
    # gated in _apply_effect_contribs.
    _apply_effect_contribs(source, build.spirit_contributions, "pact_spirit", "Pact Spirit", active_booleans, numeric_vals)
    _apply_effect_contribs(source, build.memory_contributions, "hero_memory", "Hero Memory", active_booleans, numeric_vals)

    # ── Custom mod contributions ──────────────────────────────────────────────
    for contrib in build.custom_contributions:
        stat = contrib.get("stat_key")
        if not stat:
            continue
        amount = float(contrib.get("amount", 0))
        entry = SourceEntry(
            stat=stat,
            amount=amount,
            source_type="custom",
            label="Custom Config",
            text=contrib.get("text", ""),
            points=1,
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
        entry = SourceEntry(
            stat=stat,
            amount=amount,
            source_type="support",
            label=contrib.get("label", "Support"),
            text=contrib.get("text", ""),
            points=1,
        )
        _emit(source, stat, amount, contrib.get("scope"), entry)

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
        per_stack = base_per_stack * (1.0 + source.total("numbed_effect_inc"))
        amount = per_stack * numbed_stacks
        text = (f"+{base_per_stack * 100:.0f}% Lightning Damage taken per Numbed stack"
                + (" (Conductive)" if conductive else ""))
        source.add_with_source("numbed_lightning_taken", amount, SourceEntry(
            stat="numbed_lightning_taken", amount=amount, source_type="condition",
            label="Numbed Stacks", text=text, points=1,
        ))

    # ── Bonus propagation: Play Safe (Cast Speed → Spell Burst Charge Speed) ──────
    # When granted (flag stat present), the player's cast-speed INCREASED total and EACH cast-speed
    # ADDITIONAL affix are ALSO applied to Spell Burst Charge Speed (owner: charge restoration time =
    # 2 / (1 + chargeSpeed_inc) / Π(1 + chargeSpeed_additional_i)). Spell Burst charge speed isn't consumed
    # by the engine yet, so this populates the stats ready for when it is, without affecting DPS today.
    if source.total("cast_speed_to_spell_burst_charge") > 0:
        cs_inc = source.total("cast_speed_inc")
        if cs_inc:
            source.add_with_source("spell_burst_charge_speed_inc", cs_inc, SourceEntry(
                stat="spell_burst_charge_speed_inc", amount=cs_inc, source_type="core_talent",
                label="Core · Play Safe", text="Cast Speed increased → Spell Burst Charge Speed", points=1))
        # Snapshot first — add_with_source appends to source_log (don't mutate during iteration).
        cs_add = [e for e in source.source_log if e.stat == "cast_speed_additional" and e.amount]
        for e in cs_add:
            source.add_with_source("spell_burst_charge_speed_additional", e.amount, SourceEntry(
                stat="spell_burst_charge_speed_additional", amount=e.amount, source_type="core_talent",
                label="Core · Play Safe", text=f"{e.text} → Spell Burst Charge", points=1))

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
