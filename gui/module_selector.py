import tkinter as tk

BG        = "#1a1a2e"
ACCENT    = "#e94560"
BTN_BG    = "#0f3460"
BTN_FG    = "#e0e0e0"
BTN_DIS   = "#2a2a3e"
FG_DIS    = "#444455"
FG_HEADER = "#e0e0e0"

MODULES = [
    ("Passive Tree", True),
    ("Items",        False),
    ("Slates",       False),
]


class ModuleSelector(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app
        self._build()

    def _build(self):
        # Title
        tk.Label(
            self, text="TLI Passive Planner",
            font=("Segoe UI", 22, "bold"),
            bg=BG, fg=ACCENT,
        ).pack(pady=(60, 8))

        tk.Label(
            self, text="Select a module to begin",
            font=("Segoe UI", 11),
            bg=BG, fg=FG_HEADER,
        ).pack(pady=(0, 40))

        # Module buttons
        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.pack()

        for label, enabled in MODULES:
            if enabled:
                btn = tk.Button(
                    btn_frame,
                    text=label,
                    font=("Segoe UI", 13, "bold"),
                    bg=BTN_BG, fg=BTN_FG,
                    activebackground=ACCENT,
                    relief="flat", bd=0,
                    padx=40, pady=16,
                    cursor="hand2",
                    command=self._on_passive_tree,
                )
            else:
                btn = tk.Button(
                    btn_frame,
                    text=f"{label}  (coming soon)",
                    font=("Segoe UI", 11),
                    bg=BTN_DIS, fg=FG_DIS,
                    relief="flat", bd=0,
                    padx=40, pady=14,
                    state="disabled",
                )
            btn.pack(pady=8, ipadx=8)

    def _on_passive_tree(self):
        self.app.show_tree_selector()
