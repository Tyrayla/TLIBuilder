"""Flame Slash canvas-support mechanics + the base skill's own Area-bonus-driven torrent count.

See .wolf/plans/flame-slash.md for the full research/design (owner-reviewed 2026-10-04). Both
mechanics below are emitted via `apply_slot_effects` (SKILL_ID="flame_slash"), which runs for EVERY
Flame Slash slot regardless of which supports are attached — it inspects `attached_supports` itself
to see whether Immediate Threat / Inverted Blaze are present, rather than routing through
GUARD_IDS/CONTRIB_HOOKS. Neither support needs GUARD_IDS: their universal "+20% additional damage"
line and Inverted Blaze's own flat tiered penalty are plain additional-damage text already
correctly captured by the generic support_mapper (confirmed in `support_baseline.json`) — guarding
either support here would only re-break what already works, for no benefit.

  - Steep Strike torrent count (base skill, no support needed): "For every 115% Area bonus for this
    skill, the number of fire torrents +2." Reads this slot's own aggregated Area bonus the same way
    Berserking Blade's Rampage already does (`skill_effects/berserking_blade.py`'s `emit_rampage`),
    and emits it as the slotted hit-count stat `flame_slash_torrent_count_flat` offense.py reads for
    the Steep Strike form (`SkillHitForm.scales_with_skill_area`; engine-change Q1, owner-approved
    2026-10-04: `torrent_count = 3 + 2 × floor(area_bonus / 1.15)`).
  - Immediate Threat (mag, slot 3 only): the universal +20% is generic (untouched). Its proximity-
    gated roll ("+(38–40)% ... to enemies within 3m") is NOT captured by the generic parser (no
    regex match for a distance-gated clause) — emitted here as a slotted `dmg_additional`, scaled
    LINEARLY by the new `enemy_distance_m` condition (owner design, 2026-10-04): the full tiered
    roll at <=3m, 0% at >=8m, linear in between. Default 0m (point-blank, owner-confirmed) → full
    roll absent any user input.
  - Inverted Blaze (noble, slot 5 only): the universal +20% and its own flat tiered penalty are both
    generic (untouched, confirmed in `support_baseline.json`). Its "fire torrents... return and
    knockback enemies they hit reversely" clause splits into two owner-clarified halves (2026-10-04,
    with a follow-up correction): the KNOCKBACK DIRECTION (pulls enemies in vs. the normal push) is
    cosmetic — zero DPS effect. The RETURN itself is a REAL second hit on the same enemy, in the
    SAME same-target shotgun group as the outbound torrents (architecturally mirrors Icebound Beam's
    Ring-Blade-stays-on-Icy-Blade precedent, not Chilling Spike's split-off precedent — Inverted
    Blaze's returns shotgun identically to the outbound torrents). The hit count is user-tunable via
    the new GLOBAL `inverted_blaze_returns` condition (owner: "should be global"), defaulting to this
    slot's own landed torrent hits, which also cap returns (owner-approved 2026-10-09).
"""

from __future__ import annotations
import math
import re

from engine.models import SourceEntry
from engine.skill_resolver import flame_slash_torrent_count
from engine.support_resolver import _progression_for_tier, _tier_value, _explicit_roll

SKILL_ID = "flame_slash"
IMMEDIATE_THREAT = "flame_slash_immediate_threat_magnificent"
INVERTED_BLAZE = "flame_slash_inverted_blaze_noble"

_NEAR_M = 3.0   # Immediate Threat: the full tiered roll applies at/within this distance
_FAR_M = 8.0    # Immediate Threat: zero bonus at/beyond this distance

# "...+(38–40) % additional damage to enemies within 3 m" (en-dash or hyphen; the tier roll itself).
_PROXIMITY_RE = re.compile(
    r"\(?\s*([\d.]+)\s*[–−\-]\s*([\d.]+)\s*\)?\s*%\s*additional\s+damage\s+to\s+enemies\s+within",
    re.I)
_RETURN_RE = re.compile(r"fire\s+torrents.*return.*knockback", re.I)


def _mid(m: "re.Match") -> float:
    return (float(m.group(1)) + float(m.group(2))) / 200.0


def _slot_area_bonus(source, mod_tags, slot: int) -> float:
    """This slot's own aggregated Skill Area bonus — identical formula to
    `berserking_blade.py`'s `emit_rampage` (read of the slot-materialized `skill_area_inc`
    increased-pool sum × `skill_area_additional`'s multiplicative product)."""
    eff = source.materialize_for_skill(mod_tags, slot)
    inc_sum = eff.total("skill_area_inc")
    add_prod = 1.0
    for e in eff.source_log:
        if e.stat == "skill_area_additional":
            add_prod *= (1.0 + e.amount)
    return (1.0 + inc_sum) * add_prod - 1.0


def apply_slot_effects(*, source, resolved, slot, condition_state, mod_tags, attached_supports,
                       skills_by_id, **_) -> dict:
    """Slot-local emissions for a Flame Slash slot: the Area-bonus-driven torrent count (always),
    Immediate Threat's linear proximity bonus, and Inverted Blaze's returning-torrent hit count."""
    area_bonus = _slot_area_bonus(source, mod_tags, slot)
    tc = flame_slash_torrent_count(area_bonus)
    source.add_slotted("flame_slash_torrent_count_flat", float(tc), slot, None, SourceEntry(
        stat="flame_slash_torrent_count_flat", amount=float(tc), source_type="skill",
        label="Flame Slash: Steep Strike", source_name=resolved.name,
        text=f"{tc} fire torrents at {area_bonus * 100:.0f}% Area bonus |flame_slash|torrent_count",
        points=1))

    def _hit_count(raw, default, minimum, maximum):
        if raw is None:
            return int(default)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return int(default)
        if not math.isfinite(value):
            return int(default)
        return max(minimum, min(maximum, int(value)))

    raw_hits = condition_state.get("flame_slash_torrent_hits")
    hits = _hit_count(raw_hits, tc, 1, tc)
    # Auto retains the original count path and default golden metadata.
    if raw_hits is not None:
        source.add_slotted("flame_slash_torrent_hits_flat", float(hits), slot, None, SourceEntry(
            stat="flame_slash_torrent_hits_flat", amount=float(hits), source_type="skill",
            label="Flame Slash: Steep Strike", source_name=resolved.name,
            text=f"{hits} of {tc} fire torrents hit the target |flame_slash|torrent_hits",
            points=1))
    source.referenced_conditions.add("flame_slash_torrent_hits")
    auto_conditions = {"flame_slash_torrent_hits": tc}
    condition_maximums = {"flame_slash_torrent_hits": tc}
    for sup in (attached_supports or []):
        # attached_supports is the BUILD-WIDE list (every skill slot's supports, flat) — scope to
        # THIS slot only, same convention every other bespoke module uses (e.g. icebound_beam.py,
        # howling_gale.py, focused_slash.py's `_cfg_for_slot`). Cross-model review (2026-10-04)
        # caught this missing filter: without it, Immediate Threat/Inverted Blaze attached to a
        # DIFFERENT Flame Slash slot (a build can equip Flame Slash in more than one slot with
        # different support loadouts — see test_per_slot_foundation.py) would incorrectly apply
        # here too. Also respects a disabled support (sup.get("enabled", True)).
        if sup.get("slot", 1) != slot or not sup.get("enabled", True):
            continue
        iid = sup.get("item_id")
        data = skills_by_id.get(iid) if skills_by_id else None
        if not data:
            continue
        if iid == IMMEDIATE_THREAT:
            entry = _progression_for_tier(data.get("progression"), _tier_value(sup.get("level")))
            line = str((entry.get("values") or {}).get("name", "")) if entry else ""
            m = _PROXIMITY_RE.search(line)
            if not m:
                continue
            roll = _explicit_roll(sup, line)
            roll_mid = roll if roll is not None else _mid(m)
            d = float(condition_state.get("enemy_distance_m", 0.0) or 0.0)
            frac = max(0.0, min(1.0, (_FAR_M - d) / (_FAR_M - _NEAR_M)))
            amt = roll_mid * frac
            if amt:
                name = data.get("name") or iid
                source.add_slotted("dmg_additional", amt, slot, None, SourceEntry(
                    stat="dmg_additional", amount=amt, source_type="support",
                    label=name, source_name=name,
                    text=(f"+{roll_mid * 100:.1f}% additional damage to enemies within {_NEAR_M:.0f}m "
                          f"(scaling to 0% at {_FAR_M:.0f}m; enemy at {d:.1f}m) "
                          f"|flame_slash|immediate_threat"),
                    points=1))
            source.referenced_conditions.add("enemy_distance_m")
        elif iid == INVERTED_BLAZE:
            auto_conditions["inverted_blaze_returns"] = hits
            condition_maximums["inverted_blaze_returns"] = hits
            raw = condition_state.get("inverted_blaze_returns")
            return_count = _hit_count(raw, hits, 0, hits)
            if return_count:
                name = data.get("name") or iid
                source.add_slotted("flame_slash_return_hits_flat", float(return_count), slot, None, SourceEntry(
                    stat="flame_slash_return_hits_flat", amount=float(return_count), source_type="support",
                    label=name, source_name=name,
                    text=(f"{return_count:.0f} returning fire-torrent hits (shotgunned with the "
                          f"outbound torrents) |flame_slash|inverted_blaze"),
                    points=1))
            source.referenced_conditions.add("inverted_blaze_returns")
    return {"auto_conditions": auto_conditions, "condition_maximums": condition_maximums}


# ── Modeled-line specs (badge stat-keys + roll ranges) — see skill_effects/howling_gale.py for the
# spec shape. Immediate Threat's proximity roll gets a real stat-key (its tier roll drives the slider
# the same way every other tiered support line does, via `_explicit_roll`); Inverted Blaze's return
# clause is `keys: []` (a recognized behavioral line with no numeric roll of its own — the actual hit
# count is resolved dynamically above, not parsed from this text).
LINE_SPECS = [
    {"support_ids": {IMMEDIATE_THREAT}, "phrase": _PROXIMITY_RE,
     "keys": ["dmg_additional"], "range_re": _PROXIMITY_RE},
    {"support_ids": {INVERTED_BLAZE}, "phrase": _RETURN_RE, "keys": [], "range_re": None},
]
