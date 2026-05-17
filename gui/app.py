import tkinter as tk
from persistence import save_manager
from trees.registry import TREES


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.configure(bg="#1a1a2e")
        self.root.minsize(900, 500)
        self._current: tk.Frame | None = None

        saved = save_manager.load()
        if saved:
            self._restore(saved)
        else:
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
        self.root.title(f"TLI Passive Planner — {tree.name}")
        self.show(TreeViewer, tree=tree)

    # ── Save restore ───────────────────────────────────────────────────────────

    def _restore(self, saved: dict):
        tree_name = saved.get("tree")
        node_points = saved.get("nodes", {})

        entry = TREES.get(tree_name)
        if entry is None:
            save_manager.clear()
            self.show_module_selector()
            return

        tree = entry["builder"]()
        for node_id, pts in node_points.items():
            node = tree.nodes.get(node_id)
            if node is not None:
                node.current_points = min(pts, node.max_points)

        self.show_tree_viewer(tree)
