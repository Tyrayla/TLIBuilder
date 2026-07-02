"""Generator for docs/SUPPORT_MODELING_SPEC.md — the PER-SUPPORT modeling spec for standard
support_skill / activation_medium supports (roadmap #2). Encodes the canonical line-template → engine
model mapping the resolver will implement, plus the Attack/Spell tag-gate, so Tyra can verify each
support before coding.

Run:  py -3.12 backend/tools/support_spec_gen.py   (reads existing doc to PRESERVE Tyra annotations,
then rewrites docs/SUPPORT_MODELING_SPEC.md per-support, every line listed)

Value formats:  support_skill modifier is the progression KEY, VALUE is fraction(s) ('a/b'=a÷b,
comma=multiple, '2,3'=min,max). activation_medium is a single 'name' blob with inline ranges.

Tag-gate (Tyra rule 2026-06-10): gate on Attack/Spell ONLY — a support tagged Spell (and not Attack)
applies to spell skills only; tagged Attack (not Spell) → attack skills only; neither → any skill.
Other tags (Melee/Projectile/Area/element) do NOT gate. "Not everything needs to match."
"""
from __future__ import annotations
import json, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))  # backend/ → engine.support_lines
from engine.support_lines import parse_support

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
_SKILLS = os.path.join(_ROOT, "data", "seasons", "SS12", "_skills.json")
_OUT = os.path.join(_ROOT, "docs", "SUPPORT_MODELING_SPEC.md")

M, C, N, D, S = "model", "cond", "needs", "defer", "skip"
STATUS_LABEL = {M: "✅ model", C: "🔶 conditional", N: "⚠️ needs decision", D: "⏭️ defer", S: "⬜ skip", "UNMAPPED": "❓ UNMAPPED"}

RULES: list[tuple[str, str, str, str]] = [
    (r"adds?\s*#-#\s*cold damage", M, "cold_{cat}_dmg_flat_min/max", "added flat; value = min,max"),
    (r"adds?\s*#-#\s*erosion damage", M, "erosion_{cat}_dmg_flat_min/max", "added flat; value = min,max"),
    (r"adds?\s*#-#\s*fire damage", M, "fire_{cat}_dmg_flat_min/max", "added flat; value = min,max"),
    (r"adds?\s*#-#\s*lightning damage", M, "lightning_{cat}_dmg_flat_min/max", "added flat; value = min,max"),
    (r"add\s*#-#\s*physical damage", M, "physical_{cat}_dmg_flat_min/max", "added flat; value = min,max"),
    (r"adds?\s*#%? of physical damage as fire", D, "—", "damage conversion → roadmap #5"),
    (r"additional\s*lightning\s*damage for the supported", M, "lightning_dmg_additional", ""),
    (r"additional\s*fire\s*damage for the supported", M, "fire_dmg_additional", ""),
    (r"additional\s*cold\s*damage for the supported", M, "cold_dmg_additional", ""),
    (r"additional\s*elemental\s*damage for the supported", M, "elemental_dmg_additional", ""),
    (r"additional\s*physical\s*damage for the supported", M, "physical_dmg_additional", ""),
    (r"additional\s*area\s*damage for the supported", M, "area_dmg_additional", ""),
    (r"additional\s*melee\s*damage for the supported", M, "melee_dmg_additional", ""),
    (r"additional\s*trauma\s*damage for the supported", M, "trauma_dmg_additional", ""),
    (r"additional\s*ailment\s*damage\s*for the supported", N, "ailment_dmg_additional?", "defer until ailment DPS modeled (Tyra)"),
    (r"additional\s*damage over time\s+(for|against)", N, "dot_dmg_additional?", "defer until DoT modeled (Tyra)"),
    (r"numbed\s*enem", C, "dmg_additional", "flat when enemy_numbed + per-stack via numbed_stacks (auto-derived)"),
    (r"for every\s*#?\s*fervor rating", C, "dmg_additional (+crit_rating_inc)", "BOTH scale per fervor_rating (auto-derived) — see annotation"),
    (r"for each stack of\s*focus blessing", C, "dmg_additional", "scaled per focus_blessings stack, capped"),
    (r"to cursed enemies", C, "dmg_additional", "gated by enemy_cursed"),
    (r"for every type of\s*ailment", C, "dmg_additional", "(1+x)^(ailment-type count) — needs an ailment-type-count numeric condition"),
    (r"for each stack of\s*ignite", C, "ignite_dmg_additional", "scaled per ignite_stacks, capped (+capture ignite-stacks-inflicted & ignite-chance stats)"),
    (r"damage over time against enemies with\s*max\s*affliction", N, "dot_dmg_additional?", "defer until DoT modeled (Tyra)"),
    (r"more damage to enemies with more life", D, "erosion_dmg_additional", "scales with enemy Life — needs enemy-life model"),
    (r"additional damage for the supported skill when it lands a critical strike", N, "dmg_additional", "crit-weighted: ×(1 + crit_chance·x) — model this (Tyra)"),
    (r"types of\s*elemental\s*damage, the next use", D, "elemental_dmg_additional", "next-use conditional — defer"),
    (r"damage increase per wave", D, "barrage_dmg_per_wave_inc", "wave mechanic — capture as stat now (Tyra)"),
    (r"hit damage for skills cast by\s*spell burst", D, "spell_burst_hit_dmg_additional", "Spell Burst → roadmap #7"),
    (r"additional attack and cast speed for the supported", M, "attack_speed_additional + cast_speed_additional", ""),
    (r"attack and cast speed for the supported", M, "attack_speed_inc + cast_speed_inc", ""),
    (r"attack speed for the supported", M, "attack_speed_inc", ""),
    (r"critical strike rating for the supported", M, "crit_rating_inc", ""),
    (r"additional skill area for the supported", M, "skill_area_inc", ""),
    (r"skill area for the supported", M, "skill_area_inc", ""),
    (r"additional projectile speed for the supported", M, "projectile_speed_inc", ""),
    (r"steep\s*strike\s*chance", M, "steep_strike_chance", ""),
    (r"^[+\-]?#% additional damage for the supported skill$", M, "dmg_additional", "generic (all types)"),
]
_COMPILED = [(re.compile(p), st, sk, nt) for p, st, sk, nt in RULES]
_SKIP_KW = re.compile(
    r"minion|aura effect|buff effect|sealed mana|cooldown recovery|duration|knockback|blinding|"
    r"charging progress|energy shield|movement speed|armor|restoration|focus speed|terra charge|"
    r"demolisher|multistrike|wilt|paralyze|spirit mag|combo finisher|penetration|immunity|"
    r"of current life|effect every time|auras|prepares|willpower|instruction|locked-on|trigger|"
    r"sentr|min channeled|growth|severe injury|resonance|tangle|track|wind rhythm|rhythm|root|"
    r"standing still|stopping moving|starting to move|max multistrike|hp is lower|life is lower|"
    r"affliction\s*grants|grants an\s*additional|origin of spirit|effect for the supported|"
    r"combo finisher amplification|wave interval|aura amplification|transfers|"
    r"stacks of buffs|after moving", re.I)


def _tmpl(k: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[0-9]+(?:[.,][0-9]+)?", "#", k)).strip()


def _classify(template: str) -> tuple[str, str, str]:
    low = template.lower()
    for rx, st, sk, nt in _COMPILED:
        if rx.search(low):
            return st, sk, nt
    if _SKIP_KW.search(low):
        return S, "—", "behavioral / non-hit-damage"
    return "UNMAPPED", "?", "no rule matched — decision needed"


_ANN_PATH = os.path.join(_ROOT, "docs", "_support_annotations.json")


def _load_annotations() -> dict[str, str]:
    """Tyra notes keyed by support name, from docs/_support_annotations.json (edited by Tyra,
    regeneration-proof — not parsed back out of the generated doc)."""
    try:
        d = json.load(open(_ANN_PATH, encoding="utf-8"))
        return {k: v for k, v in d.items() if not k.startswith("_") and v}
    except FileNotFoundError:
        return {}


def main() -> None:
    skills = (lambda d: d.get("skills", d) if isinstance(d, dict) else d)(json.load(open(_SKILLS, encoding="utf-8")))
    ann_by_support = _load_annotations()

    out = ["# Standard Support Skill — Modeling Spec (per-support)",
           "",
           "Per-support engine model for roadmap #2. Generated by `backend/tools/support_spec_gen.py` "
           "from SS12 data; Tyra annotations preserved in the **📝** column. **Goal: model each support "
           "WHOLE** — every line becomes a damage contribution, a new stat, a new condition/buff, or a "
           "captured-but-inert stat (never silently dropped).",
           "",
           "**Status:** ✅ model now · 🔶 conditional (auto-derived) · ⚠️ needs a stat/condition decision · "
           "⏭️ defer to a later roadmap item · ⬜ skip / capture-as-stat (not hit damage today).",
           "",
           "**Tag-gate (Attack/Spell only):** a support tagged **Spell** (not Attack) applies to spell "
           "skills only; **Attack** (not Spell) → attack skills only; **neither** → any skill. Other tags "
           "(Melee/Projectile/Area/element) do NOT gate. Each support's gate is shown in its heading.",
           "",
           "_Added-flat `{cat}` = the supported skill's category (spell|attack), substituted at resolve time._",
           "",
           "## Tag-gating — what it changes (demonstration on Chain Lightning `[Spell, Lightning, Chain]`)",
           "",
           "Today every attached support's contributions apply unconditionally. With the gate, a support "
           "applies only if its Attack/Spell tag is compatible with the main skill:",
           "",
           "| Support | Tags | Gate | On Chain Lightning (a spell)? |",
           "|---|---|---|---|",
           "| Control Spell | Spell, Support | spell-only | ✅ applies |",
           "| Electric Overload | Lightning, Support | any skill | ✅ applies |",
           "| Added Cold Damage | Cold, Support | any skill | ✅ applies (adds cold to a lightning spell) |",
           "| Nova Shot | Projectile, Vertical, Support | any skill | ✅ applies (Projectile doesn't gate) |",
           "| Steamroll | Attack, Melee, Area, Support | attack-only | ❌ filtered out (CL is a spell) |",
           "| Precision Strike | Attack, … | attack-only | ❌ filtered out |",
           "",
           "So the gate's net effect is: **Attack-tagged supports drop off spell builds, and Spell-tagged "
           "supports drop off attack builds** — element/projectile/melee/area tags never filter. "
           "(Implementation: pass the main skill's category into the resolver — already needed for "
           "added-flat — and skip a support whose gate conflicts.)",
           ""]

    for stype, label in (("support_skill", "support_skill"), ("activation_medium_skill", "activation_medium")):
        sup = sorted([s for s in skills if s.get("skill_type") == stype], key=lambda s: (s.get("name") or "").lower())
        cnt: dict[str, int] = {}
        out.append(f"## {label} — {len(sup)} supports")
        out.append("")
        for s in sup:
            name = s.get("name") or s.get("item_id")
            parsed = parse_support(s)
            tags = ", ".join(t for t in (s.get("skill_tags") or []) if t.lower() != "support") or "—"
            out.append(f"### {name}  ·  _{parsed.gate}_  ·  gate-text: {parsed.gate_text or '—'}  ·  tags: {tags}")
            note = ann_by_support.get(name)
            if note:
                out.append(f"> 📝 **Tyra:** {note}")
            out.append("")
            out.append("| Line | Kind | Lv1 | Status | Engine model | Notes |")
            out.append("|---|---|---|---|---|---|")
            for ln in parsed.lines:
                st, sk, nt = _classify(ln.template)
                cnt[st] = cnt.get(st, 0) + 1
                kind = "scale" if ln.scaling else "flat"
                lv1 = (ln.tier_values.get(1) or "") if ln.scaling else ""
                txt = ln.text if len(ln.text) <= 80 else ln.text[:77] + "…"
                out.append(f"| {txt} | {kind} | {lv1} | {STATUS_LABEL.get(st, st)} | `{sk}` | {nt} |")
            out.append("")
        out.append(f"**{label} line counts:** " + " · ".join(f"{STATUS_LABEL.get(k,k)} {v}" for k, v in sorted(cnt.items(), key=lambda x: -x[1])))
        out.append("")

    # New-infrastructure checklist (curated from Tyra annotations + decisions).
    out += [
        "## New infrastructure to build (from the annotations)",
        "",
        "**New stats (capture even if inert today):**",
        "- `ignite_stacks_inflicted_flat` — additional Ignite stacks *inflicted* (≠ max stacks) [Additional Ignite]",
        "- `ignite_chance`, `ignite_max_stacks_flat` — Ignite chance / cap [Additional Ignite]",
        "- `trauma_inflict_chance` — % chance to inflict Trauma [Deep Wounds]",
        "- `min_channeled_stacks_flat` — +N Min Channeled Stacks [Channel Preparation]",
        "- `wave_interval` / per-wave damage — capture Carpet Bombardment's wave modifiers as stats",
        "- `ailment_duration` — −ailment-duration downside [Ailment Termination] (relevant later)",
        "",
        "**New conditions / buffs:**",
        "- `electric_overload` — support-granted buff (a condition) → +15% additional Lightning Damage when active [Electric Overload]",
        "- ailment-type-count numeric condition → drives `(1+x)^count` [Ailment Termination]",
        "",
        "**New mechanics / rules:**",
        "- **Support tag-gate (Attack/Spell)** — general rule for all basic supports (demo above)",
        "- **Crit-weighted additional** — `×(1 + crit_chance·x)` for on-crit lines [Critical Strike Damage Increase]",
        "- **Multi-scaler lines** — one line → several stats off one condition (additional dmg + crit rating per Fervor) [Attack Focus]",
        "- **Negative modifiers** as first-class — −100% increased Crit [Control Spell], −wave interval, etc.",
        "- **Wave mechanic** (Carpet Bombardment) — larger; capture stats now, model later",
        "",
        "**Deferred until their system exists:** Ailment-additional & DoT-additional stats (ailment/DoT DPS), "
        "Spell Burst (#7), damage conversion (#5), Tangles (#6), enemy-Life scaling.",
    ]
    with open(_OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print(f"wrote {_OUT} — {len(ann_by_support)} Tyra annotations attached")


if __name__ == "__main__":
    main()
