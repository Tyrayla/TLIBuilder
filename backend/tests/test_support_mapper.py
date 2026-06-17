"""Tests: engine/support_mapper — value parsing + damage/stat line emission (P2 foundation)."""
import json, os
import pytest
from engine.support_lines import parse_support
from engine.support_mapper import (parse_value, map_via_parser, map_added_flat, map_capture_line,
                                   map_conditional_line, map_autoderive_line)

_SKILLS = os.path.join(os.path.dirname(__file__), "..", "..", "data", "seasons", "SS12", "_skills.json")


def _by_name():
    d = json.load(open(_SKILLS, encoding="utf-8"))
    skills = d.get("skills", d) if isinstance(d, dict) else d
    return {s.get("name"): s for s in skills}


class TestParseValue:
    def test_fraction(self):
        assert parse_value("37/5") == [pytest.approx(7.4)]
        assert parse_value("31/2") == [pytest.approx(15.5)]

    def test_range(self):
        assert parse_value("2,3") == [pytest.approx(2.0), pytest.approx(3.0)]

    def test_value_and_cap(self):
        assert parse_value("27/10,54/5") == [pytest.approx(2.7), pytest.approx(10.8)]

    def test_negative(self):
        assert parse_value("-15") == [pytest.approx(-15.0)]


class TestDamageEmission:
    def setup_method(self):
        self.skills = _by_name()

    def _lines(self, name):
        return parse_support(self.skills[name]).lines

    def test_generic_additional(self):
        # Multiple Projectiles: scaling "7.4% additional damage" → dmg_additional 0.074 at Lv1
        ln = next(l for l in self._lines("Multiple Projectiles") if l.scaling)
        c = map_via_parser(ln, 1)
        assert len(c) == 1 and c[0].stat_key == "dmg_additional"
        assert c[0].amount == pytest.approx(0.074)

    def test_type_additional_lightning(self):
        ln = next(l for l in self._lines("High Voltage") if l.scaling)
        c = map_via_parser(ln, 1)
        assert c[0].stat_key == "lightning_dmg_additional" and c[0].amount == pytest.approx(0.103)

    def test_negative_skill_area_and_proj_speed(self):
        # Nova Shot: -15% Skill Area → skill_area_inc -0.15; +15% additional Projectile Speed → new stat
        lines = self._lines("Nova Shot")
        area = next(map_via_parser(l, 1) for l in lines if "skill area" in l.template)
        assert area[0].stat_key == "skill_area_inc" and area[0].amount == pytest.approx(-0.15)
        spd = next(map_via_parser(l, 1) for l in lines if "projectile speed" in l.template)
        assert spd[0].stat_key == "projectile_speed_additional" and spd[0].amount == pytest.approx(0.15)

    def test_attack_and_cast_speed_splits(self):
        ln = next(l for l in self._lines("Quick Mobility") if "attack and cast speed" in l.template)
        c = map_via_parser(ln, 1)
        assert {x.stat_key for x in c} == {"attack_speed_inc", "cast_speed_inc"}

    def test_flat_negative_downside(self):
        # Steamroll: flat "-15% Attack Speed for the supported skill" → attack_speed_inc -0.15
        ln = next(l for l in self._lines("Steamroll") if "attack speed" in l.template and not l.scaling)
        c = map_via_parser(ln, 1)
        assert c[0].stat_key == "attack_speed_inc" and c[0].amount == pytest.approx(-0.15)

    def test_non_damage_line_returns_empty(self):
        ln = next(l for l in self._lines("High Voltage") if "inflicts numbed" in l.template)
        assert map_via_parser(ln, 1) == []


class TestAddedFlat:
    def setup_method(self):
        self.skills = _by_name()

    def _scale(self, name):
        return next(l for l in parse_support(self.skills[name]).lines if l.scaling)

    def test_added_cold_spell(self):
        c = map_added_flat(self._scale("Added Cold Damage"), 1, "spell")
        assert {x.stat_key for x in c} == {"cold_spell_dmg_flat_min", "cold_spell_dmg_flat_max"}
        assert next(x.amount for x in c if x.stat_key.endswith("min")) == pytest.approx(2.0)
        assert next(x.amount for x in c if x.stat_key.endswith("max")) == pytest.approx(3.0)

    def test_added_cold_attack_category(self):
        c = map_added_flat(self._scale("Added Cold Damage"), 1, "attack")
        assert {x.stat_key for x in c} == {"cold_attack_dmg_flat_min", "cold_attack_dmg_flat_max"}

    def test_no_category_no_emit(self):
        assert map_added_flat(self._scale("Added Cold Damage"), 1, None) == []


class TestCapture:
    def setup_method(self):
        self.skills = _by_name()

    def _flat(self, name, kw):
        return next(l for l in parse_support(self.skills[name]).lines if kw in l.template and not l.scaling)

    def test_projectile_quantity_inert(self):
        c = map_capture_line(self._flat("Multiple Projectiles", "projectile quantity"), 1)
        assert c[0].stat_key == "projectile_quantity_flat" and c[0].modeled is False

    def test_shadow_quantity(self):
        c = map_capture_line(self._flat("Haunt", "shadow quantity"), 1)
        assert c[0].stat_key == "max_shadow_quantity_flat"

    def test_refractions_and_beam_length(self):
        lines = parse_support(self.skills["Refracted Prism"]).lines
        ref = next(map_capture_line(l, 1) for l in lines if "refraction" in l.template)
        assert ref[0].stat_key == "extra_beams_flat"
        bl = next(map_capture_line(l, 1) for l in lines if "beam length" in l.template)
        assert bl[0].stat_key == "beam_length_additional" and bl[0].amount == pytest.approx(-0.10)

    def test_ignite_stacks_and_chance(self):
        lines = parse_support(self.skills["Additional Ignite"]).lines
        st = next(map_capture_line(l, 1) for l in lines if "stack(s) of ignite" in l.template)
        assert st[0].stat_key == "ignite_stacks_inflicted_flat" and st[0].amount == pytest.approx(1.0)
        ch = next(map_capture_line(l, 1) for l in lines if "ignite chance" in l.template)
        assert ch[0].stat_key == "ignite_chance" and ch[0].amount == pytest.approx(0.15)

    def test_cannot_inflict_multi_flag(self):
        ln = next(l for l in parse_support(self.skills["Elemental Fusion"]).lines if "cannot inflict" in l.template)
        keys = {x.stat_key for x in map_capture_line(ln, 1)}
        assert {"cannot_inflict_ignite", "cannot_inflict_frostbite", "cannot_inflict_numbed"} <= keys


class TestConditional:
    def setup_method(self):
        self.skills = _by_name()

    def _scale(self, name):
        return next(l for l in parse_support(self.skills[name]).lines if l.scaling)

    def test_grudge_gated_on_cursed(self):
        ln = next(l for l in parse_support(self.skills["Grudge"]).lines if "cursed enem" in l.template)
        assert map_conditional_line(ln, 1, {"enemy_cursed": False}) == []
        c = map_conditional_line(ln, 1, {"enemy_cursed": True})
        assert c[0].stat_key == "dmg_additional" and c[0].amount == pytest.approx(0.105)  # 21/2 = 10.5%

    def test_electric_punishment_flat_plus_per_stack(self):
        ln = self._scale("Electric Punishment")
        # base 10.5% (when numbed) + 1% per Numbed stack × 3 = 13.5%
        c = map_conditional_line(ln, 1, {"numbed_stacks": 3})
        assert c[0].stat_key == "dmg_additional" and c[0].amount == pytest.approx(0.135)

    def test_attack_focus_per_fervor(self):
        ln = self._scale("Attack Focus")  # 1.65% additional damage per 10 Fervor Rating
        c = map_conditional_line(ln, 1, {"fervor_rating": 100})
        assert c[0].stat_key == "dmg_additional" and c[0].amount == pytest.approx(0.165)  # 1.65%×(100/10)

    def test_overload_focus_blessing_bucket(self):
        ln = self._scale("Overload")  # 3.05% additional per Focus Blessing stack
        c = map_conditional_line(ln, 1, {"focus_blessings": 4})
        assert c[0].stat_key == "dmg_additional" and c[0].amount == pytest.approx(0.122)  # 3.05%×4

    def test_additional_ignite_per_stack_capped(self):
        ln = self._scale("Additional Ignite")  # 2.7% per Ignite stack, up to 10.8%
        assert map_conditional_line(ln, 1, {"ignite_stacks": 2})[0].amount == pytest.approx(0.054)
        assert map_conditional_line(ln, 1, {"ignite_stacks": 10})[0].amount == pytest.approx(0.108)  # capped

    def test_ailment_termination_multiplies_count(self):
        ln = self._scale("Ailment Termination")  # 6.7% additional per ailment type (multiplies)
        c = map_conditional_line(ln, 1, {"ailment_type_count": 3})
        assert c[0].stat_key == "dmg_additional" and c[0].amount == pytest.approx(1.067 ** 3 - 1)


class TestAutoDerive:
    def setup_method(self):
        self.skills = _by_name()

    def _flat(self, name, kw):
        return next(l for l in parse_support(self.skills[name]).lines if kw in l.template and not l.scaling)

    def test_high_voltage_numbed_gated_lightning(self):
        e = map_autoderive_line(self._flat("High Voltage", "inflicts numbed"))
        keys = {x.condition_key: x for x in e}
        assert keys["enemy_numbed"].mode == "set_true" and keys["enemy_numbed"].requires_dtype == "lightning"
        assert keys["numbed_stacks"].mode == "max" and keys["numbed_stacks"].value == 1.0

    def test_glacial_freeze_frostbite_gated_cold(self):
        e = map_autoderive_line(self._flat("Glacial Freeze", "inflicts frostbite"))
        assert e[0].condition_key == "enemy_frostbitten" and e[0].requires_dtype == "cold"

    def test_grudge_paralyze_requires_cursed(self):
        ln = next(l for l in parse_support(self.skills["Grudge"]).lines if "paralyze" in l.template)
        e = map_autoderive_line(ln)
        assert e[0].condition_key == "enemy_paralyzed" and e[0].requires_cond == "enemy_cursed"

    def test_electric_overload_buff(self):
        ln = next(l for l in parse_support(self.skills["Electric Overload"]).lines if "buff on critical" in l.template)
        e = map_autoderive_line(ln)
        assert e[0].condition_key == "electric_overload" and e[0].mode == "set_true"

    def test_willpower_stacks_gated_standing_still(self):
        ln = next(l for l in parse_support(self.skills["Willpower"]).lines if "stack of buff" in l.template)
        e = map_autoderive_line(ln)
        assert e[0].condition_key == "willpower_stacks" and e[0].value == 6.0 and e[0].requires_cond == "standing_still"

    def test_damage_line_has_no_autoderive(self):
        ln = next(l for l in parse_support(self.skills["High Voltage"]).lines if l.scaling)
        assert map_autoderive_line(ln) == []
