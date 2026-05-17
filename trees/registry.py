from models.passive_tree import PassiveTree
from trees import knowledge
from trees import (
    the_brave, onslaughter, warlord, warrior,
    marksman, bladerunner, druid, assassin,
    magister, arcanist, elementalist, prophet,
    shadowdancer, ronin, ranger, sentinel,
    shadowmaster, psychic, warlock, lich,
    machinist, steel_vanguard, alchemist, artisan,
)


def _empty(name: str):
    def builder(): return PassiveTree(name)
    return builder


TREES: dict[str, dict] = {
    # God of Might
    "God of Might":         {"color": "#8B6914", "builder": _empty("God of Might")},
    "The Brave":            {"color": "#8B6914", "builder": the_brave.build_tree},
    "Onslaughter":          {"color": "#8B6914", "builder": onslaughter.build_tree},
    "Warlord":              {"color": "#8B6914", "builder": warlord.build_tree},
    "Warrior":              {"color": "#8B6914", "builder": warrior.build_tree},
    # Goddess of Hunting
    "Goddess of Hunting":   {"color": "#2D6B2D", "builder": _empty("Goddess of Hunting")},
    "Marksman":             {"color": "#2D6B2D", "builder": marksman.build_tree},
    "Bladerunner":          {"color": "#2D6B2D", "builder": bladerunner.build_tree},
    "Druid":                {"color": "#2D6B2D", "builder": druid.build_tree},
    "Assassin":             {"color": "#2D6B2D", "builder": assassin.build_tree},
    # Goddess of Knowledge
    "Goddess of Knowledge": {"color": "#1E3A8A", "builder": knowledge.build_tree},
    "Magister":             {"color": "#1E3A8A", "builder": magister.build_tree},
    "Arcanist":             {"color": "#1E3A8A", "builder": arcanist.build_tree},
    "Elementalist":         {"color": "#1E3A8A", "builder": elementalist.build_tree},
    "Prophet":              {"color": "#1E3A8A", "builder": prophet.build_tree},
    # God of War
    "God of War":           {"color": "#8B1A1A", "builder": _empty("God of War")},
    "Shadowdancer":         {"color": "#8B1A1A", "builder": shadowdancer.build_tree},
    "Ronin":                {"color": "#8B1A1A", "builder": ronin.build_tree},
    "Ranger":               {"color": "#8B1A1A", "builder": ranger.build_tree},
    "Sentinel":             {"color": "#8B1A1A", "builder": sentinel.build_tree},
    # Goddess of Deception
    "Goddess of Deception": {"color": "#6B2D8B", "builder": _empty("Goddess of Deception")},
    "Shadowmaster":         {"color": "#6B2D8B", "builder": shadowmaster.build_tree},
    "Psychic":              {"color": "#6B2D8B", "builder": psychic.build_tree},
    "Warlock":              {"color": "#6B2D8B", "builder": warlock.build_tree},
    "Lich":                 {"color": "#6B2D8B", "builder": lich.build_tree},
    # God of Machines
    "God of Machines":      {"color": "#0E7490", "builder": _empty("God of Machines")},
    "Machinist":            {"color": "#0E7490", "builder": machinist.build_tree},
    "Steel Vanguard":       {"color": "#0E7490", "builder": steel_vanguard.build_tree},
    "Alchemist":            {"color": "#0E7490", "builder": alchemist.build_tree},
    "Artisan":              {"color": "#0E7490", "builder": artisan.build_tree},
}
