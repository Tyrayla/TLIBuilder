import tkinter as tk
from trees.registry import TREES


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.configure(bg="#1a1a2e")
        self.root.minsize(1100, 680)
        self._current: tk.Frame | None = None
        self.selected_trees: list[str | None] = [None, None, None, None]
        self.show_module_selector()

    # ── Screen switching ───────────────────────────────────────────────────────

    def show(self, frame_cls, **kwargs):
        if self._current:
            self._current.destroy()
        self._current = frame_cls(self.root, self, **kwargs)
        self._current.pack(fill="both", expand=True)

    def show_module_selector(self):
        from gui.module_selector import ModuleSelector
        self.show(ModuleSelector)

    def show_tree_selector(self):
        from gui.tree_selector import TreeSelector
        self.show(TreeSelector)

    def show_tree_viewer(self, tree):
        from gui.tree_viewer import TreeViewer
        self.root.title(f"TLI Planner — {tree.name}")
        self.show(TreeViewer, tree=tree)
