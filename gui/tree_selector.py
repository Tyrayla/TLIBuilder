import tkinter as tk
from trees.registry import TREES

BG        = "#1a1a2e"
ACCENT    = "#e94560"
FG_HEADER = "#e0e0e0"
FG_NAME   = "#ffffff"
FG_DIM    = "#888899"

CARD_W    = 140
PORTRAIT_H = 110


class TreeSelector(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app
        self._build()

    def _build(self):
        # Back button — top left
        nav = tk.Frame(self, bg=BG)
        nav.pack(fill="x", padx=12, pady=(10, 0))
        tk.Button(
            nav, text="← Back",
            font=("Segoe UI", 9), bg=BG, fg="#e0e0e0",
            activebackground="#0f3460", activeforeground="#e0e0e0",
            relief="flat", bd=0, cursor="hand2",
            command=self.app.show_module_selector,
        ).pack(side="left")

        tk.Label(
            self, text="Select a Passive Tree",
            font=("Segoe UI", 18, "bold"),
            bg=BG, fg=ACCENT,
        ).pack(pady=(20, 6))

        tk.Label(
            self, text="This choice is saved and will be loaded on next launch.",
            font=("Segoe UI", 9, "italic"),
            bg=BG, fg=FG_DIM,
        ).pack(pady=(0, 30))

        cards_frame = tk.Frame(self, bg=BG)
        cards_frame.pack()

        for name, meta in TREES.items():
            self._make_card(cards_frame, name, meta["color"])

    def _make_card(self, parent, name: str, color: str):
        # Outer border frame uses tree color
        border = tk.Frame(parent, bg=color, padx=2, pady=2)
        border.pack(side="left", padx=10)

        card = tk.Frame(border, bg="#111122", width=CARD_W, padx=8, pady=10)
        card.pack()
        card.pack_propagate(False)
        card.config(width=CARD_W, height=260)

        # Portrait placeholder
        portrait = tk.Canvas(card, width=CARD_W - 16, height=PORTRAIT_H,
                             bg=color, highlightthickness=0)
        portrait.pack(pady=(0, 8))
        cx = (CARD_W - 16) // 2
        portrait.create_text(cx, PORTRAIT_H // 2, text="?",
                              font=("Segoe UI", 28, "bold"), fill="#ffffff")

        # Tree name
        tk.Label(
            card, text=name,
            font=("Segoe UI", 9, "bold"),
            bg="#111122", fg=FG_NAME,
            wraplength=CARD_W - 12,
            justify="center",
        ).pack(pady=(0, 10))

        # 5 placeholder talent circles
        dots = tk.Frame(card, bg="#111122")
        dots.pack()
        for _ in range(5):
            c = tk.Canvas(dots, width=20, height=20, bg="#111122", highlightthickness=0)
            c.pack(side="left", padx=2)
            c.create_oval(2, 2, 18, 18, outline=color, fill="#1a1a2e", width=2)

        # Select button
        btn = tk.Button(
            card,
            text="Select",
            font=("Segoe UI", 9, "bold"),
            bg=color, fg="#ffffff",
            activebackground=ACCENT,
            relief="flat", bd=0,
            padx=10, pady=6,
            cursor="hand2",
            command=lambda n=name: self._select(n),
        )
        btn.pack(pady=(12, 0))

    def _select(self, tree_name: str):
        from trees.registry import TREES
        tree = TREES[tree_name]["builder"]()
        self.app.show_tree_viewer(tree)
