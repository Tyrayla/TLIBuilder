from dataclasses import dataclass, field


@dataclass
class CoreTalent:
    id: str
    name: str
    effects: list[str] = field(default_factory=list)
    icon_url: str | None = None   # CDN url; UI pairs on its basename to a bundled talent_tree webp


@dataclass
class CoreTalentSlot:
    threshold: int          # total points required to unlock this slot
    options: list[CoreTalent]
    selected_id: str | None = None
