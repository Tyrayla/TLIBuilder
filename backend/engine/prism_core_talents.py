"""Ethereal-Prism Core-Talent resolution (Plan B).

A placed Ethereal Prism can REPLACE the tree's Core Talent (named implicit), ADD an effect to it (Haze), or ADD a
named talent without replacing (do-not-replace, Slot 3). All are gated by the tree's core-talent point threshold (24).

Modelling rule (Tyra): **all-or-nothing** per talent — a talent contributes ONLY if its whole effect resolves
(generic stat parse) or it has a bespoke handler. Otherwise it contributes nothing and is badged NYI, so a
half-modelled talent never misleads the user. Two bespoke handlers exist: Unmatched Valor (fixed Fervor 130) and
Spell Ripple (true-damage proc); everything else goes through the generic parser.

Returns (contributions, set_conditions, statuses, replaced_tree_slugs):
  contributions       list[dict]  {stat_key, amount, text, label, condition_expr}
  set_conditions      dict        conditions forced on by a prism (e.g. unmatched_valor)
  statuses            list[dict]  {name, text, resolved, kind}  (working / nyi / locked badges)
  replaced_tree_slugs set[str]    trees whose native Core Talent a REPLACE prism supersedes (caller drops them)
"""
from __future__ import annotations
import re

from engine.core_talent_resolver import _classify_effect, _slug, _normalize

CORE_TALENT_THRESHOLD = 24
_LINE_SPLIT_RE = re.compile(r"\s+(?=[+-]\d)")
_PANEL_TAIL = "Advanced Talent Panel:"
_DNR_MARK = "no longer replace the original talent"


def _split_effect_lines(text: str) -> list[str]:
    return [s.strip() for s in _LINE_SPLIT_RE.split((text or "").strip()) if s.strip()]


def _tree_total_points(slots, tree_name: str) -> int:
    slug = _slug(tree_name)
    for slot in slots or []:
        if slot and _slug(slot.get("treeName", "")) == slug:
            return sum(int(v or 0) for v in (slot.get("nodeStates") or {}).values())
    return 0


# ── Bespoke handlers (talents the generic parser can't model) ────────────────────
def _bespoke_unmatched_valor(label):
    # "Has 130 point(s) of fixed Fervor Rating" — a flag consumed in compute.py (force fervor_rating=130, locked).
    return {"contribs": [], "set_conditions": {"unmatched_valor": True},
            "status": "Has 130 point(s) of fixed Fervor Rating"}


def _bespoke_spell_ripple(label):
    # "50% chance to spawn a Pulse dealing True Damage = 150% of Hit Damage" → effective 0.5×1.5 = 0.75 of hit
    # damage as true damage (read in offense.py, like Rosa's Mercury Baptism).
    return {"contribs": [{"stat_key": "spell_ripple_fraction", "amount": 0.75,
                          "text": "Spell Ripple: 50% chance, 150% of Hit Damage as True Damage |prism|spell_ripple",
                          "label": label, "condition_expr": None}],
            "set_conditions": {},
            "status": "Spell Skills: 50% chance to spawn a 150%-Hit-Damage True-Damage Pulse"}


_BESPOKE = {"Unmatched Valor": _bespoke_unmatched_valor, "Spell Ripple": _bespoke_spell_ripple}


def _resolve_lines_all_or_nothing(lines, label, short, parse_mod, translate_cond):
    """Resolve every line; return (contribs, ok). ok=False if ANY line is unresolved (caller drops all)."""
    out: list[dict] = []
    ok = True
    for ln in lines:
        cls = _classify_effect(ln, parse_mod, translate_cond)
        if cls["kind"] == "stat":
            for c in cls["contribs"]:
                out.append({"stat_key": c["stat_key"], "amount": c["amount"],
                            "text": f"{c.get('text', ln)} |prism|{short}", "label": label,
                            "condition_expr": cls["condition_expr"]})
        else:
            ok = False
    return out, (ok and bool(out))


def resolve_prism_core_talents(prisms, slots, desc_by_name, parse_mod, translate_cond):
    contribs: list[dict] = []
    set_conditions: dict = {}
    statuses: list[dict] = []
    replaced: set[str] = set()

    for prism in prisms or []:
        if prism.get("kind") != "ethereal_prism":
            continue
        eth = prism.get("ethereal") or {}
        implicit = eth.get("implicit", "") or ""
        short = eth.get("shortName", "") or ""
        tree_name = prism.get("treeName", "") or ""
        if re.search(r"effects of Random Affixes", implicit, re.I):
            continue  # Phantasmagoria amplify — no Core Talent change

        is_replace = implicit.startswith("Replaces the Core Talent")
        is_add = implicit.startswith("Adds an additional effect")
        if not (is_replace or is_add):
            continue
        adv = eth.get("advanced", "") or ""
        dnr = bool(adv) and _DNR_MARK in adv.lower()          # do-not-replace → additive, keeps native core
        label = f"{tree_name} · {short} (Prism)"
        name = f"{short} (Prism)"

        # Threshold gate (same 24-pt rule as a normal Core Talent).
        if _tree_total_points(slots, tree_name) < CORE_TALENT_THRESHOLD:
            statuses.append({"name": name, "text": f"Locked — allocate {CORE_TALENT_THRESHOLD} points to activate.",
                             "resolved": False, "kind": "locked"})
            continue

        # Effect lines: replace → the replacement talent's glossary description; add (Haze) → the chosen effect.
        if is_replace:
            lines = _split_effect_lines(desc_by_name.get(short, ""))
        else:
            i = implicit.find(_PANEL_TAIL)
            lines = _split_effect_lines(implicit[i + len(_PANEL_TAIL):] if i >= 0 else implicit)
        # Do-not-replace penalty (−15 All Stats / −5% Ele Res / −8% Defense) rides along as another line.
        if dnr:
            pen = adv.split("Mutated")[0].strip()
            if pen:
                lines = [pen] + lines

        # A pure replace (not do-not-replace) supersedes the tree's own selected Core Talent.
        suppress = is_replace and not dnr

        # Bespoke first (skips the generic parser).
        if short in _BESPOKE:
            res = _BESPOKE[short](label)
            contribs.extend(res["contribs"])
            set_conditions.update(res["set_conditions"])
            statuses.append({"name": name, "text": res["status"], "resolved": True, "kind": "stat"})
            # the do-not-replace penalty still applies generically
            if dnr:
                pen = adv.split("Mutated")[0].strip()
                pc, pok = _resolve_lines_all_or_nothing([pen] if pen else [], label, short, parse_mod, translate_cond)
                if pok:
                    contribs.extend(pc)
            if suppress:
                replaced.add(_slug(tree_name))
            continue

        # Generic all-or-nothing.
        resolved, ok = _resolve_lines_all_or_nothing(lines, label, short, parse_mod, translate_cond)
        if ok:
            contribs.extend(resolved)
            for ln in lines:
                statuses.append({"name": name, "text": ln, "resolved": True, "kind": "stat"})
            if suppress:
                replaced.add(_slug(tree_name))
        else:
            statuses.append({"name": name, "text": (desc_by_name.get(short, "") or implicit) or short,
                             "resolved": False, "kind": "unresolved"})
            # NYI talent contributes nothing AND does not suppress the native core (no silent loss).

    return contribs, set_conditions, statuses, replaced
