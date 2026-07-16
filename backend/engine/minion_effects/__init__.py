"""Bespoke minion DPS modules. Importing this package registers each module's handler into
`engine.minion_offense.MINION_MODULES`, so a minion deals damage ONLY when a module here owns it (unmodelled
minions stay NYI). Add a module + one line here to model a new minion.

Each module exposes `OWNER_ID` (the summon/module skill item_id) and `handler(source, owner, base_stats,
level, count) -> list[OffenseResult]`.
"""
from engine.minion_offense import MINION_MODULES
from engine.minion_effects import thunder_magus as _thunder_magus

_MODULES = (_thunder_magus,)

for _m in _MODULES:
    MINION_MODULES[_m.OWNER_ID] = _m.handler
