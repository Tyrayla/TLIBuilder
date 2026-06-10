"""Tests: Core Talents (roadmap #4) — resolver collection/dedup/effect-classification (with injected
freeform-mod resolvers), the base-effect override flags in the aggregator (Sacrifice / Conductive /
Divine Grace), and the core_talent_contributions injection path (plain + conditional gating)."""
import re
import pytest

from engine.core_talent_resolver import resolve_core_talents, _classify_effect, _split_condition
from engine.aggregator import aggregate
from engine.models import BuildInput


# ── Lightweight injected resolvers (mirror the server's _parse_custom_mod_text / _translate_condition_expr
#    for the handful of strings exercised here — keeps these tests free of season-data loading) ──────
def parse_mod(text: str):
    m = re.match(r"^\s*([+-]?\d+(?:\.\d+)?)\s*(%?)\s+(.*)", text)
    if not m:
        return []
    val, pct, rest = float(m.group(1)), bool(m.group(2)), m.group(3).lower()
    amount = val / 100.0 if pct else val
    if "max mana" in rest:
        return [{"stat_key": "max_mana_inc", "amount": amount, "text": text}]
    if "spell damage" in rest:
        return [{"stat_key": "spell_dmg_additional", "amount": amount, "text": text}]
    return []


def translate_cond(text: str):
    t = text.lower()
    if "focus bless" in t:
        m = re.search(r"at least\s+(\d+)", t)
        return {"key": "focus_blessings", "op": ">=", "value": int(m.group(1))} if m else None
    return None


def _trees():
    return {"onslaughter": {
        "tree_name": "Onslaughter",
        "core_talents": [
            {"display_name_key": "onslaughter_sacrifice", "name": "Sacrifice",
             "effects": ["Changes the base effect of Tenacity Blessing to: +8% additional damage (Max Divinity Effect: 1)"]},
            {"display_name_key": "onslaughter_mana", "name": "Mana",
             "effects": ["+12 % additional Max Mana (Max Divinity Effect: 1)"]},
        ],
    }}


def _blends():
    return {"blends": [
        {"talent_id": "350003", "talent_type": "core", "talent_name": "Sacrifice",
         "effect_text": "Changes the base effect of Tenacity Blessing to: +8% additional damage"},
        {"talent_id": "350004", "talent_type": "core", "talent_name": "Conductive",
         "effect_text": "Changes the base effect of Numbed to: +11 % additional Lightning Damage taken"},
        {"talent_id": "370001", "talent_type": "aromatic", "talent_name": "Divine Grace",
         "effect_text": "Changes the base effect of all Blessings to: +4% additional damage and -4% additional damage taken per stack"},
        {"talent_id": "350045", "talent_type": "core", "talent_name": "Mana",
         "effect_text": "+12 % additional Max Mana"},
    ]}


def _resolve(slots=None, slates=None, gear=None):
    return resolve_core_talents(slots or [], slates or [], gear or [], _trees(), _blends(),
                                parse_mod, translate_cond)


class TestEffectClassify:
    def test_plain(self):
        cls = _classify_effect("+12 % additional Max Mana (Max Divinity Effect: 1)", parse_mod, translate_cond)
        assert cls["kind"] == "stat" and cls["condition_expr"] is None
        assert cls["contribs"][0]["stat_key"] == "max_mana_inc"
        assert cls["contribs"][0]["amount"] == pytest.approx(0.12)

    def test_override_targets(self):
        assert _classify_effect("Changes the base effect of Tenacity Blessing to: +8% additional damage", parse_mod, translate_cond) == {"kind": "override", "flag": "core_sacrifice"}
        assert _classify_effect("Changes the base effect of Numbed to: +11 % additional Lightning Damage taken", parse_mod, translate_cond) == {"kind": "override", "flag": "core_conductive"}
        assert _classify_effect("Changes the base effect of all Blessings to: +4% additional damage", parse_mod, translate_cond) == {"kind": "override", "flag": "divine_grace"}

    def test_deferred_mind_focus(self):
        assert _classify_effect("Changes the base effect of Focus Blessing to: Adds Physical Damage equal to 1% of Max Mana", parse_mod, translate_cond)["kind"] == "deferred"

    def test_conditional_translatable(self):
        cls = _classify_effect("+25 % additional Spell Damage when you have at least 5 Focus Blessing", parse_mod, translate_cond)
        assert cls["kind"] == "stat"
        assert cls["condition_expr"] == {"key": "focus_blessings", "op": ">=", "value": 5}

    def test_conditional_untranslatable_captured(self):
        # A real condition we can't model must NOT apply unconditionally — captured as unresolved.
        cls = _classify_effect("+25 % additional Spell Damage when the Energy Shield is not low", parse_mod, translate_cond)
        assert cls["kind"] == "unresolved"

    def test_special_nonnumeric_unresolved(self):
        assert _classify_effect("Refreshes Barrier when gaining Barrier", parse_mod, translate_cond)["kind"] == "unresolved"


class TestResolveSources:
    def test_tree_override(self):
        slots = [{"treeName": "Onslaughter", "nodeStates": {}, "coreTalentSelections": {"12": "onslaughter_sacrifice"}}]
        _c, flags, _s = _resolve(slots=slots)
        assert "core_sacrifice" in flags

    def test_tree_plain_contribution(self):
        slots = [{"treeName": "Onslaughter", "nodeStates": {}, "coreTalentSelections": {"12": "onslaughter_mana"}}]
        contribs, _f, _s = _resolve(slots=slots)
        c = next(x for x in contribs if x["stat_key"] == "max_mana_inc")
        assert c["amount"] == pytest.approx(0.12) and "|core|mana" in c["text"]

    def test_belt_blend_conductive(self):
        _c, flags, _s = _resolve(gear=[{"contributions": [], "belt_blend": "350004"}])
        assert "core_conductive" in flags

    def test_belt_blend_divine_grace(self):
        _c, flags, _s = _resolve(gear=[{"contributions": [], "belt_blend": "370001"}])
        assert "divine_grace" in flags

    def test_legendary_grant_by_name(self):
        contribs, _f, _s = _resolve(gear=[{"contributions": [], "granted_talents": ["Mana"]}])
        assert any(c["stat_key"] == "max_mana_inc" for c in contribs)

    def test_slate_core(self):
        slates = [{"slots": [{"isCore": True, "coreName": "Sacrifice",
                              "effects": ["Changes the base effect of Tenacity Blessing to: +8% additional damage"]}]}]
        _c, flags, _s = _resolve(slates=slates)
        assert "core_sacrifice" in flags

    def test_dedup_across_sources(self):
        # Sacrifice via tree AND belt blend → counted exactly once.
        slots = [{"treeName": "Onslaughter", "nodeStates": {}, "coreTalentSelections": {"12": "onslaughter_sacrifice"}}]
        _c, flags, statuses = _resolve(slots=slots, gear=[{"contributions": [], "belt_blend": "350003"}])
        assert flags == {"core_sacrifice"}
        assert [s["name"] for s in statuses] == ["Sacrifice"]


class TestAggregatorOverrides:
    def _agg(self, conds, contribs=None):
        return aggregate(
            BuildInput(slots=[], slates=[], season="t", condition_state=conds,
                       core_talent_contributions=contribs or []), {}, {},
            active_booleans=frozenset(k for k, v in conds.items() if isinstance(v, bool) and v),
            numeric_vals={k: float(v) for k, v in conds.items() if not isinstance(v, bool)},
        )

    def test_sacrifice_flips_tenacity_offensive(self):
        s = self._agg({"tenacity_blessings": 5, "core_sacrifice": True})
        assert s.total("dmg_additional") == pytest.approx(0.40)          # 0.08 × 5
        assert s.total("dmg_taken_additional") == pytest.approx(0.0)     # default −4%/stack gone

    def test_tenacity_default_without_flag(self):
        s = self._agg({"tenacity_blessings": 5})
        assert s.total("dmg_taken_additional") == pytest.approx(-0.20)   # −0.04 × 5

    def test_divine_grace_rebases_blessing(self):
        s = self._agg({"focus_blessings": 3, "divine_grace": True})
        assert s.total("dmg_additional") == pytest.approx(0.12)          # 0.04 × 3
        assert s.total("dmg_taken_additional") == pytest.approx(-0.12)   # −0.04 × 3

    def test_conductive_numbed_base(self):
        s = self._agg({"numbed_stacks": 10, "core_conductive": True})
        assert s.total("numbed_lightning_taken") == pytest.approx(1.10)  # 0.11 × 10
        s2 = self._agg({"numbed_stacks": 10})
        assert s2.total("numbed_lightning_taken") == pytest.approx(0.50)  # default 0.05 × 10


class TestContributionInjection:
    def _agg(self, contribs, conds=None):
        conds = conds or {}
        return aggregate(
            BuildInput(slots=[], slates=[], season="t", condition_state=conds,
                       core_talent_contributions=contribs), {}, {},
            active_booleans=frozenset(k for k, v in conds.items() if isinstance(v, bool) and v),
            numeric_vals={k: float(v) for k, v in conds.items() if not isinstance(v, bool)},
        )

    def test_plain_injected(self):
        s = self._agg([{"stat_key": "spell_dmg_additional", "amount": 0.25, "text": "x |core|t", "label": "Core · T", "condition_expr": None}])
        assert s.total("spell_dmg_additional") == pytest.approx(0.25)

    def test_conditional_gated_on(self):
        expr = {"key": "focus_blessings", "op": ">=", "value": 5}
        s = self._agg([{"stat_key": "spell_dmg_additional", "amount": 0.25, "text": "x |core|t", "label": "L", "condition_expr": expr}],
                      conds={"focus_blessings": 5})
        assert s.total("spell_dmg_additional") == pytest.approx(0.25)

    def test_conditional_gated_off(self):
        expr = {"key": "focus_blessings", "op": ">=", "value": 5}
        s = self._agg([{"stat_key": "spell_dmg_additional", "amount": 0.25, "text": "x |core|t", "label": "L", "condition_expr": expr}],
                      conds={"focus_blessings": 4})
        assert s.total("spell_dmg_additional") == pytest.approx(0.0)
