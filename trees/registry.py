from models.passive_tree import PassiveTree
from trees import knowledge

# Each entry: display color + builder function.
# Builders for trees without nodes yet return an empty PassiveTree.

def _empty(name: str):
    def builder():
        return PassiveTree(name)
    return builder


TREES: dict[str, dict] = {
    "God of Might":         {"color": "#8B6914", "builder": _empty("God of Might")},
    "Goddess of Hunting":   {"color": "#2D6B2D", "builder": _empty("Goddess of Hunting")},
    "Goddess of Knowledge": {"color": "#1E3A8A", "builder": knowledge.build_tree},
    "God of War":           {"color": "#8B1A1A", "builder": _empty("God of War")},
    "Goddess of Deception": {"color": "#6B2D8B", "builder": _empty("Goddess of Deception")},
    "God of Machines":      {"color": "#0E7490", "builder": _empty("God of Machines")},
}
