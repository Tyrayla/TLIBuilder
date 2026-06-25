"""Pact Fates/Kismets catalog parsing (tools/destiny_catalog.categorize_destiny)."""
from tools.destiny_catalog import categorize_destiny

# New crawler shape: effects in `implicit[]`, boilerplate/tier in `detail[]`.
def _it(name, implicit, tier_word):
    return {"name": name, "icon_url": "x.webp", "implicit": implicit,
            "detail": [f"Install to replace a {tier_word} Talent Node", "Additional items will be consumed when removing this"]}


_RAW = {"items": [
    _it("Micro Fate: Fire Resistance", ["+(5–7) % Fire Resistance"], "Micro"),
    _it("Medium Fate: Attack Damage", ["+(28–36) % Attack Damage"], "Medium"),
    _it("Kismet: Guillotine", ["+(4–6) % Steep Strike chance. +(4–6) % additional Steep Strike Damage"], "Medium"),
    _it("Dual Kismet: Solid Rock",
        ["Activates the following effects when there are 2 of this Kismet on the same pact page: Gains a stack of Fortitude when using a Melee Skill +2 Max Fortitude Stacks"], "Medium"),
    {"name": "Undetermined Fate", "icon_url": "u.webp", "implicit": [],
     "detail": ["Can be installed in an Undetermined Fate Slot to replace the original effects and unlock several additional Fate Slots (up to 5)."]},
]}


def test_kinds_tiers_and_effect():
    c = categorize_destiny(_RAW)
    by = {i["short_name"]: i for i in c["items"]}
    assert by["Fire Resistance"]["kind"] == "micro_fate" and by["Fire Resistance"]["node_tier"] == "micro"
    assert by["Fire Resistance"]["effect_text"] == "+(5–7) % Fire Resistance"      # straight from implicit
    assert by["Attack Damage"]["kind"] == "medium_fate" and by["Attack Damage"]["node_tier"] == "medium"
    assert by["Guillotine"]["kind"] == "kismet" and by["Guillotine"]["node_tier"] == "medium"
    sr = by["Solid Rock"]
    assert sr["kind"] == "dual_kismet" and sr["node_tier"] == "medium"
    # Dual-kismet "Activates … 2 …:" intro stripped, leaving the effect.
    assert sr["effect_text"].startswith("Gains a stack of Fortitude")
    assert "Activates the following" not in sr["effect_text"]
    assert by["Fire Resistance"]["icon_url"] == "x.webp"


def test_pools_split_by_tier_and_undetermined():
    c = categorize_destiny(_RAW)
    assert [i["short_name"] for i in c["micro"]] == ["Fire Resistance"]
    assert {i["short_name"] for i in c["medium"]} == {"Attack Damage", "Guillotine", "Solid Rock"}
    assert c["undetermined"] and c["undetermined"]["kind"] == "undetermined"


def test_real_season_data():
    import json, os
    path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "seasons", "SS12", "_destiny.json")
    c = categorize_destiny(json.load(open(path, encoding="utf-8")))
    from collections import Counter
    kinds = Counter(i["kind"] for i in c["items"])
    assert kinds["micro_fate"] == 50 and kinds["medium_fate"] == 41
    assert kinds["kismet"] == 46 and kinds["dual_kismet"] == 54 and kinds["undetermined"] == 1
    assert len(c["micro"]) == 50 and len(c["medium"]) == 141
    # every non-undetermined fate must parse to an effect (a blank one = a crawler data gap to fix), every item
    # has an icon, and no dual-kismet intro leaks into the effect.
    real = [i for i in c["items"] if i["kind"] != "undetermined"]
    blank = [i["name"] for i in real if not i["effect_text"]]
    assert not blank, f"fates with no effect (crawler gap): {blank}"
    assert all(i["icon_url"] for i in c["items"])
    assert all("Activates the following" not in i["effect_text"] for i in real)
