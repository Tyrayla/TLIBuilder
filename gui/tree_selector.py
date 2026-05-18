import tkinter as tk
from trees.registry import TREES
from gui.sidebar import ActiveTreesSidebar

BG          = "#1a1a2e"
ACCENT      = "#e94560"
FG_HEADER   = "#e0e0e0"
FG_NAME     = "#ffffff"
BG_BLOCKED  = "#1e1e2a"
FG_BLOCKED  = "#444455"
OUT_BLOCKED = "#2a2a3a"

GROUPS = [
    ("God of Might",         ["The Brave", "Onslaughter", "Warlord", "Warrior"]),
    ("Goddess of Hunting",   ["Marksman", "Bladerunner", "Druid", "Assassin"]),
    ("Goddess of Knowledge", ["Magister", "Arcanist", "Elementalist", "Prophet"]),
    ("God of War",           ["Shadowdancer", "Ronin", "Ranger", "Sentinel"]),
    ("Goddess of Deception", ["Shadowmaster", "Psychic", "Warlock", "Lich"]),
    ("God of Machines",      ["Machinist", "Steel Vanguard", "Alchemist", "Artisan"]),
]

PRIMARIES = {g[0] for g in GROUPS}


class TreeSelector(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app
        self._card_btns: dict[str, tk.Button] = {}
        self._card_borders: dict[str, tk.Frame] = {}
        self._status_label: tk.Label | None = None
        self._sidebar: ActiveTreesSidebar | None = None
        self._build()

    # ── Build ──────────────────────────────────────────────────────────────────

    def _build(self):
        nav = tk.Frame(self, bg=BG)
        nav.pack(fill="x", padx=12, pady=(10, 0))
        tk.Button(
            nav, text="← Back",
            font=("Segoe UI", 9), bg=BG, fg=FG_HEADER,
            activebackground="#0f3460", activeforeground=FG_HEADER,
            relief="flat", bd=0, cursor="hand2",
            command=self.app.show_module_selector,
        ).pack(side="left")

        tk.Label(
            self, text="Select a Passive Tree",
            font=("Segoe UI", 18, "bold"),
            bg=BG, fg=ACCENT,
        ).pack(pady=(16, 4))

        self._status_label = tk.Label(
            self, text="", font=("Segoe UI", 9, "italic"),
            bg=BG, fg="#ff6b6b", anchor="w", padx=14)
        self._status_label.pack(fill="x")

        panel = tk.Frame(self, bg=BG)
        panel.pack(fill="both", expand=True, padx=8, pady=(4, 8))

        self._sidebar = ActiveTreesSidebar(panel, self.app, on_overview=None)
        self._sidebar.pack(side="left", fill="y", padx=(0, 8))

        self._build_grid(panel)

    def _build_grid(self, parent):
        grid_frame = tk.Frame(parent, bg=BG)
        grid_frame.pack(side="left", fill="both", expand=True)

        for col_idx in range(6):
            grid_frame.columnconfigure(col_idx, weight=1, minsize=145)
        for row_idx in range(5):
            grid_frame.rowconfigure(row_idx, weight=1, minsize=110)

        for col_idx, (primary, secondaries) in enumerate(GROUPS):
            self._make_card(grid_frame, primary, TREES[primary]["color"], col_idx, 0)
            for row_idx, name in enumerate(secondaries, start=1):
                self._make_card(grid_frame, name, TREES[name]["color"], col_idx, row_idx)

    def _make_card(self, parent, name: str, color: str, col: int, row: int):
        border = tk.Frame(parent, bg=color, padx=2, pady=2)
        border.grid(row=row, column=col, padx=5, pady=4, sticky="nsew")
        self._card_borders[name] = border

        card = tk.Frame(border, bg="#111122", padx=6, pady=6)
        card.pack(fill="both", expand=True)

        tk.Frame(card, bg=color, height=28).pack(fill="x", pady=(0, 6))

        tk.Label(
            card, text=name,
            font=("Segoe UI", 10, "bold"),
            bg="#111122", fg=FG_NAME,
            wraplength=130, justify="center",
        ).pack(expand=True)

        btn = tk.Button(
            card, text="Select",
            font=("Segoe UI", 9, "bold"),
            fg="#ffffff",
            activebackground=ACCENT,
            relief="flat", bd=0, padx=8, pady=4,
            command=lambda n=name: self._select(n),
        )
        btn.pack(pady=(4, 0))
        self._card_btns[name] = btn

        self._update_card(name)

    # ── Select / deselect ──────────────────────────────────────────────────────

    def _has_valid_primary(self) -> bool:
        return self.app.selected_trees[0] is not None

    def _get_primary_group(self) -> set[str]:
        primary = self.app.selected_trees[0]
        if primary is None:
            return set()
        for p, secs in GROUPS:
            if p == primary:
                return set(secs)
        return set()

    def _has_valid_secondary(self) -> bool:
        return self.app.selected_trees[1] is not None

    def _is_blocked(self, name: str) -> bool:
        trees = self.app.selected_trees
        if name in PRIMARIES:
            # Slot 0 is taken by a different primary
            return trees[0] is not None
        group = self._get_primary_group()
        if name in group:
            if trees[0] is None:
                return True  # No primary yet
            if trees[1] is None:
                return False  # Slot 1 is open — this tree can fill it
            # Slot 1 taken; this tree can still go into slots 2 or 3
            return trees[2] is not None and trees[3] is not None
        # Foreign secondary: needs primary + matched secondary, and a free slot 2 or 3
        if trees[0] is None or trees[1] is None:
            return True
        return trees[2] is not None and trees[3] is not None

    def _refresh_all_cards(self):
        for name in self._card_btns:
            self._update_card(name)

    def _select(self, name: str):
        trees = self.app.selected_trees
        slot = next((i for i, t in enumerate(trees) if t == name), None)

        if slot is not None:
            # Removing — cascade based on which slot
            if slot == 0:
                for i in range(4):
                    trees[i] = None
            elif slot == 1:
                trees[1] = None
                # Promote any group subtree sitting in slots 2/3 up to slot 1
                group = self._get_primary_group()
                for i in [2, 3]:
                    if trees[i] is not None and trees[i] in group:
                        trees[1] = trees[i]
                        trees[i] = None
                        break
            else:
                trees[slot] = None
            self._refresh_all_cards()
            self._sidebar.refresh()
        elif self._is_blocked(name):
            if name in PRIMARIES:
                self._set_status("Only 1 base tree allowed. Remove your current base tree first.")
            elif trees[0] is None:
                self._set_status("Select a base tree first.")
            else:
                self._set_status("Select a tree from your base group for slot 2 first.")
        else:
            # Adding — assign to the correct slot
            if name in PRIMARIES:
                trees[0] = name
            elif name in self._get_primary_group():
                if trees[1] is None:
                    trees[1] = name
                else:
                    for i in [2, 3]:
                        if trees[i] is None:
                            trees[i] = name
                            break
            else:
                for i in [2, 3]:
                    if trees[i] is None:
                        trees[i] = name
                        break
            self._refresh_all_cards()
            self._sidebar.refresh()
            tree_obj = TREES[name]["builder"]()
            self.app.show_tree_viewer(tree_obj)

    def _update_card(self, name: str):
        is_sel = name in self.app.selected_trees
        is_blocked = self._is_blocked(name)
        color = TREES[name]["color"]

        btn = self._card_btns.get(name)
        border = self._card_borders.get(name)

        if is_sel:
            if btn:
                btn.config(text="Remove", bg=ACCENT, fg="#ffffff",
                           state="normal", cursor="hand2")
            if border:
                border.config(bg=ACCENT)
        elif is_blocked:
            if btn:
                btn.config(text="Select", bg=BG_BLOCKED, fg=FG_BLOCKED,
                           state="disabled", cursor="")
            if border:
                border.config(bg=OUT_BLOCKED)
        else:
            if btn:
                btn.config(text="Select", bg=color, fg="#ffffff",
                           state="normal", cursor="hand2")
            if border:
                border.config(bg=color)

    def _set_status(self, message: str):
        if self._status_label:
            self._status_label.config(text=message)
            self.after(3000, lambda: self._status_label.config(text=""))
