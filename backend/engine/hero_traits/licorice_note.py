"""Sage — Licorice Note (trait_id "licorice_note").

Built around **Scent Bottles** (elixir slots) and **Elixir Skill Effect**. The DPS payoff is a set of Elixir-Effect
bonuses (slot-specific to the Scent Bottles) plus a **cross-apply** that grants a portion of the Basic Scent
Bottle's *increased* Elixir Effect to ONE prepared Empower/Curse skill. Built on the shipped elixir system; all
effects flow through the existing elixir/empower/curse pipelines via slot-scoped stat contributions.

Tyra-confirmed modeling (2026-06-27):
- Scent-bottle bonuses are SLOT-SPECIFIC: Basic Scent Bottle = active slot 2; Special Scent Bottle = active slot 3
  (only when "Licorice Tincture Blend" is picked at L75). Bonuses that say "for Elixir Skills from a Scent Bottle"
  are emitted slot-scoped to those slots; bonuses that just say "Elixir Skill Effect" are global.
- Wording rule [[reference_bonus_vs_additional]]: "Bonus" = INCREASED pool only; lines that say "additional" → the
  additional pool. So Pungent's basis = slot-2 `elixir_effect_inc` and its output = `*_effect_inc`; Everlasting
  Nectar reads increased Life/Mana and outputs `elixir_effect_inc`; Artificial Moon / Scent of Ambition say
  "additional" → `elixir_effect_additional`.
- Pungent prepares ONE random installed Empower OR Curse; the cross-apply goes to that single skill, slot-scoped to
  it (never global). Auto-selected when exactly one eligible; the user designates one when >1 (no bonus until set).
  A medium-priority warning fires when an Activation Medium is equipped (a medium-triggered skill isn't prepared by
  the trait → no bonus — a common pitfall).
- Temporal effects carry an uptime multiplier (`_FULL_UPTIME = 1.0` now; the hook for future real-uptime modes).

NYI (surfaced, not dropped): the restoration "cannot be removed" line, and Twinspine Flower (reaping, pending).
"""
from __future__ import annotations

TRAIT_ID = "licorice_note"

_SLOT_BASE, _SLOT_45, _SLOT_60, _SLOT_75 = 0, 1, 2, 3
_BASIC_SCENT_SLOT = 2
_SPECIAL_SCENT_SLOT = 3
_FULL_UPTIME = 1.0   # uptime convention: 100% in Full Uptime mode; one-line hook per effect for real-uptime later

_ARTIFICIAL_MOON_EFFECT = 0.12
_SCENT_OF_AMBITION = [0.24, 0.27, 0.30, 0.33, 0.36]
_SCENT_OF_AMBITION_DURATION = -0.30
_NECTAR_RATIO = [1.0, 1.2, 1.4, 1.6, 1.8]
_NECTAR_CAP = [0.60, 0.70, 0.80, 0.90, 1.00]
_PUNGENT_RATIO = [2.0, 2.3, 2.6, 2.9, 3.2]
_PUNGENT_EMPOWER_CAP = [0.70, 1.00, 1.30, 1.60, 1.90]
_PUNGENT_CURSE_CAP = [0.50, 0.70, 0.90, 1.10, 1.30]
# Elixir of Immortality: excess Life/Mana Restoration → Temporary Life/Mana (every 3 excess → 2 temp, capped at
# IMMORTALITY_TEMP_CAP % of Base Max Life/Mana); +damage per Temporary Life = 5% of Base Max Life OR Temporary
# Mana = Base Max Mana, up to the cap.
_IMMORTALITY_TEMP_CAP = [0.20, 0.25, 0.30, 0.40, 0.50]   # % of Base Max Life/Mana
_IMMORTALITY_DMG_PER_UNIT = [0.01, 0.015, 0.02, 0.025, 0.03]
_IMMORTALITY_DMG_CAP = [0.10, 0.15, 0.20, 0.25, 0.30]
_IMMORTALITY_LIFE_UNIT = 0.05    # 1 unit = 5% of Base Max Life


def _tier(slot_levels, idx):
    lvl = slot_levels[idx] if idx < len(slot_levels) else 1
    return max(0, min(4, int(abs(lvl)) - 1))


def _enabled(slot_levels, idx):
    lvl = slot_levels[idx] if idx < len(slot_levels) else 1
    return lvl >= 1


def _scent_bottle_slots(slot_levels, picks) -> set[int]:
    slots = {_BASIC_SCENT_SLOT}
    if "Licorice Tincture Blend" in picks and _enabled(slot_levels, _SLOT_75):
        slots.add(_SPECIAL_SCENT_SLOT)
    return slots


def _eligible_skills(build_input) -> list[tuple]:
    """(skill_id, name, slot, kind) for each enabled installed Empower + Curse — the Pungent-preparable set."""
    out: list[tuple] = []
    for sid, m in (getattr(build_input, "empower_meta", None) or {}).items():
        if m.get("enabled", True):
            out.append((sid, m.get("name", sid), m.get("slot"), "empower"))
    for c in (getattr(build_input, "curses", None) or []):
        if c.get("enabled", True):
            out.append((c.get("skill_id"), c.get("curse_name", c.get("skill_id")), c.get("slot"), "curse"))
    return out


def _designated(build_input):
    """The (sid, name, slot, kind) that receives Pungent's cross-apply, or None. Auto when exactly one eligible;
    the user's `licorice_prepared_skill` pick when >1; None if >1 and no valid pick (→ no bonus, surfaced in UI)."""
    elig = _eligible_skills(build_input)
    if not elig:
        return None
    if len(elig) == 1:
        return elig[0]
    pick = getattr(build_input, "licorice_prepared_skill", None)
    return next((e for e in elig if e[0] == pick), None)


def apply(*, build_input, condition_state, ls_state, uptime_mode, slot_levels, advanced_picks, **_):
    picks = set(advanced_picks or [])
    slot_levels = list(slot_levels or [1, 1, 1, 1])
    if not _enabled(slot_levels, _SLOT_BASE):          # base node disabled → whole trait off
        return {"contributions": []}
    base_lvl = slot_levels[_SLOT_BASE]
    c: list[dict] = []

    def add(stat, amt, text, source, slot=None):
        d = {"stat_key": stat, "amount": amt, "text": text, "source": source}
        if slot is not None:
            d["slot"] = slot
        c.append(d)

    sb_slots = _scent_bottle_slots(slot_levels, picks)

    # ── Artificial Moon (base L5): +12% ADDITIONAL Elixir Effect, slot-scoped to each Scent Bottle slot ──
    if abs(base_lvl) >= 5:
        for s in sorted(sb_slots):
            add("elixir_effect_additional", _ARTIFICIAL_MOON_EFFECT,
                f"Artificial Moon: +12% additional Elixir Skill Effect (Scent Bottle, slot {s})",
                "Artificial Moon", slot=s)

    # ── Scent of Ambition (L60 pick): global ADDITIONAL Elixir Effect (uptime) + −30% additional Elixir Duration ──
    if "Scent of Ambition" in picks and _enabled(slot_levels, _SLOT_60):
        t = _tier(slot_levels, _SLOT_60)
        amt = _SCENT_OF_AMBITION[t] * _FULL_UPTIME
        add("elixir_effect_additional", amt,
            f"Scent of Ambition: +{amt * 100:.0f}% additional Elixir Skill Effect (after casting elixirs)",
            "Scent of Ambition")
        add("elixir_duration_additional", _SCENT_OF_AMBITION_DURATION,
            "Scent of Ambition: -30% additional Elixir Skill Effect Duration", "Scent of Ambition")

    # ── Elixir of Immortality (L60 pick): excess Restoration → Temporary Life/Mana (capped) → +additional damage.
    # Excess restoration is stashed in-loop (compute.py). Temporary pools are a separate used-first barrier emitted
    # as temporary_life/mana_flat (the recovery stage displays them); damage scales per Temp Life=5% Base Max Life
    # (or Temp Mana = Base Max Mana). ──
    if "Elixir of Immortality" in picks and _enabled(slot_levels, _SLOT_60):
        t = _tier(slot_levels, _SLOT_60)
        base_life = float(ls_state.get("base_max_life", 0.0))
        base_mana = float(ls_state.get("base_max_mana", 0.0))
        excess_life = float(ls_state.get("excess_life_restoration", 0.0))
        excess_mana = float(ls_state.get("excess_mana_restoration", 0.0))
        temp_life = min(excess_life * 2.0 / 3.0, _IMMORTALITY_TEMP_CAP[t] * base_life)
        temp_mana = min(excess_mana * 2.0 / 3.0, _IMMORTALITY_TEMP_CAP[t] * base_mana)
        if temp_life > 1e-9:
            add("temporary_life_flat", temp_life, f"Elixir of Immortality: {temp_life:.0f} Temporary Life "
                f"(excess Life Restoration, cap {_IMMORTALITY_TEMP_CAP[t] * 100:.0f}% Base Max Life)", "Elixir of Immortality")
        if temp_mana > 1e-9:
            add("temporary_mana_flat", temp_mana, f"Elixir of Immortality: {temp_mana:.0f} Temporary Mana", "Elixir of Immortality")
        units = (temp_life / (_IMMORTALITY_LIFE_UNIT * base_life) if base_life > 0 else 0.0) \
            + (temp_mana / base_mana if base_mana > 0 else 0.0)
        dmg = min(units * _IMMORTALITY_DMG_PER_UNIT[t], _IMMORTALITY_DMG_CAP[t])
        if dmg > 1e-9:
            add("dmg_additional", dmg, f"Elixir of Immortality: +{dmg * 100:.0f}% additional damage "
                f"({units:.0f} Temporary units, cap {_IMMORTALITY_DMG_CAP[t] * 100:.0f}%)", "Elixir of Immortality")

    # ── Everlasting Nectar (L75 pick): INCREASED Elixir Effect from increased Life/Mana (capped) ──
    if "Everlasting Nectar" in picks and _enabled(slot_levels, _SLOT_75):
        t = _tier(slot_levels, _SLOT_75)
        lm = float(ls_state.get("life_mana_bonus", 0.0))           # max(increased Life, increased Mana)
        amt = min(lm * _NECTAR_RATIO[t], _NECTAR_CAP[t])
        if amt > 1e-9:
            add("elixir_effect_inc", amt,
                f"Everlasting Nectar: +{amt * 100:.0f}% Elixir Skill Effect "
                f"({lm * 100:.0f}% Life/Mana bonus × {_NECTAR_RATIO[t]:.1f}, cap {_NECTAR_CAP[t] * 100:.0f}%)",
                "Everlasting Nectar")

    # ── Pungent Stimulant Salt (L45 guaranteed): cross-apply slot-2 INCREASED Elixir Effect to the ONE designated
    #    Empower/Curse, slot-scoped to it, in the INCREASED pool (capped per type) ──
    if _enabled(slot_levels, _SLOT_45):
        t = _tier(slot_levels, _SLOT_45)
        des = _designated(build_input)
        if des is not None:
            sid, name, slot, kind = des
            basis = float(ls_state.get("sb_elixir_effect", 0.0))   # slot-2 increased Elixir Effect (the "Bonus")
            cap = _PUNGENT_EMPOWER_CAP[t] if kind == "empower" else _PUNGENT_CURSE_CAP[t]
            amt = min(basis * _PUNGENT_RATIO[t] * _FULL_UPTIME, cap)
            if amt > 1e-9 and slot is not None:
                stat = "empower_effect_inc" if kind == "empower" else "curse_effect_inc"
                add(stat, amt,
                    f"Pungent Stimulant Salt: +{amt * 100:.0f}% {kind.title()} Effect (prepared {name}; "
                    f"{basis * 100:.0f}% Elixir Effect × {_PUNGENT_RATIO[t]:.1f}, cap {cap * 100:.0f}%)",
                    "Pungent Stimulant Salt", slot=slot)

    return {"contributions": c}


def stash(*, source, ls_state, inflict_aps=None, **_):
    """Capture converged scalars the next pass reads: slot-2 increased Elixir Effect (Pungent basis) and the
    highest increased Life/Mana bonus (Everlasting Nectar). Both are INCREASED pools per the wording rule."""
    ls_state["sb_elixir_effect"] = source.materialize_for_skill(set(), slot=_BASIC_SCENT_SLOT).total("elixir_effect_inc")
    ls_state["life_mana_bonus"] = max(source.total("max_life_inc"), source.total("max_mana_inc"))
    # Base Max pools for Elixir of Immortality (Temporary pool caps + damage units read these next pass) and Max ES
    # for Pixie Tear.
    ls_state["base_max_life"] = source.total("max_life")
    ls_state["base_max_mana"] = source.total("max_mana")
    ls_state["max_energy_shield"] = source.total("max_energy_shield")


# Supports that "prepare"/trigger their host skill (so Pungent doesn't prepare it → no cross-apply): any Activation
# Medium, plus the normal spell Preparation supports.
_PREP_SUPPORT_ITEMS = frozenset({"preparation", "channel_preparation"})


def _is_prep_support(sup) -> bool:
    iid = str(sup.get("item_id") or "")
    return (iid.startswith("activation_medium") or sup.get("skill_type") == "activation_medium_skill"
            or iid in _PREP_SUPPORT_ITEMS)


def status_lines(*, slot_levels, advanced_picks, attached_supports=None, skills_input=None, skills_by_id=None,
                 prepared_skill=None, **_):
    """One row per trait line (working / informational / warning / nyi). The Pungent pitfall warning names the
    buffed Empower/Curse AND the exact Activation Medium / Preparation support on its slot that intercepts it."""
    picks = set(advanced_picks or [])
    slot_levels = list(slot_levels or [1, 1, 1, 1])
    out: list[dict] = []

    def row(text, source, status):
        out.append({"text": text, "source": source, "status": status})

    row("Basic Scent Bottle = active slot 2: its elixir receives the Sage Elixir-Effect bonuses.",
        "Licorice Note", "working")
    row("Basic Scent Bottle: 2 Ingredients (1 Damage + 1 Defense) — Ingredient effects NYI (Phase 2).",
        "Licorice Note", "nyi")
    row("Restoration Effect from Elixir Skills cannot be removed — restoration subsystem NYI.",
        "Licorice Note", "nyi")

    if abs(slot_levels[_SLOT_BASE]) >= 5:
        row("Artificial Moon: +12% additional Elixir Skill Effect for Scent Bottle elixirs.",
            "Artificial Moon", "working")

    if _enabled(slot_levels, _SLOT_45):
        row("Pungent Stimulant Salt: cross-applies the Basic Scent Bottle's increased Elixir Effect to ONE "
            "prepared Empower/Curse (capped).", "Pungent Stimulant Salt", "working")
        row("Pungent randomly prepares ONE installed Empower/Curse while a Basic Scent Bottle elixir is active; "
            "only that prepared skill receives the bonus.", "Pungent Stimulant Salt", "informational")
        row("Pungent: +1 Utility Ingredient (Charge restoration) — Ingredient effects NYI (Phase 2).",
            "Pungent Stimulant Salt", "nyi")
        # Pitfall: an Empower/Curse triggered by an Activation Medium OR a Preparation support on its slot isn't
        # "prepared" by the trait → no cross-apply. Name the buffed skill + the exact intercepting source.
        prep_by_slot: dict = {}
        for sup in (attached_supports or []):
            if sup.get("enabled", True) and _is_prep_support(sup):
                nm = ((skills_by_id or {}).get(sup.get("item_id")) or {}).get("name") or sup.get("item_id")
                prep_by_slot.setdefault(sup.get("slot", 1), []).append(nm)
        # Eligible Empower/Curse skills (the Pungent-preparable set), with their slots.
        eligible = []
        for sk in (skills_input or []):
            if not sk.get("enabled", True):
                continue
            tags = ((skills_by_id or {}).get(sk.get("skill_id")) or {}).get("skill_tags") or []
            kind = "Empower" if "Empower" in tags else ("Curse" if "Curse" in tags else None)
            if kind:
                nm = ((skills_by_id or {}).get(sk.get("skill_id")) or {}).get("name") or sk.get("skill_id")
                eligible.append((sk.get("skill_id"), nm, sk.get("slot"), kind))
        for sid, nm, slot, kind in eligible:
            srcs = prep_by_slot.get(slot)
            if not srcs:
                continue
            designated = " (your designated prepared skill)" if sid == prepared_skill else ""
            row(f"{nm} ({kind}, slot {slot}){designated} is triggered by {', '.join(srcs)} — Pungent does not "
                f"'prepare' it, so it gains NO cross-applied Elixir Effect. Remove that Activation Medium / "
                f"Preparation, or leave the Empower/Curse for the trait to prepare.", "Pungent Stimulant Salt", "warning")

    if "Scent of Ambition" in picks and _enabled(slot_levels, _SLOT_60):
        t = _tier(slot_levels, _SLOT_60)
        row(f"Scent of Ambition: +{_SCENT_OF_AMBITION[t] * 100:.0f}% additional Elixir Skill Effect (after casting "
            f"elixirs) − 30% additional Elixir Skill Effect Duration.", "Scent of Ambition", "working")
    if "Elixir of Immortality" in picks and _enabled(slot_levels, _SLOT_60):
        row("Elixir of Immortality: excess Restoration → Temporary Life/Mana (used-first barrier) → +additional "
            "damage per Temporary unit (capped).", "Elixir of Immortality", "working")

    if "Everlasting Nectar" in picks and _enabled(slot_levels, _SLOT_75):
        row("Everlasting Nectar: a portion of your increased Max Life/Mana also applies to (increased) Elixir Skill "
            "Effect (capped).", "Everlasting Nectar", "working")
    if "Licorice Tincture Blend" in picks and _enabled(slot_levels, _SLOT_75):
        row("Licorice Tincture Blend: Special Scent Bottle = active slot 3 (also receives Scent Bottle "
            "Elixir-Effect bonuses).", "Licorice Tincture Blend", "working")
        row("Special Scent Bottle: 1 Ingredient — Ingredient effects NYI (Phase 2).",
            "Licorice Tincture Blend", "nyi")

    return out
