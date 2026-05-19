# Development Notes

## Building a Distributable

```bash
npm run build:win
```

Output goes to `dist/`. The packaged app bundles the Python backend and launches it automatically — no separate Python install needed on the target machine (when built with PyInstaller integration).

---

## Importing Season Data

Season data is imported from game JSON files (one per tree). Each file follows this format:

```json
{
  "tree": "alchemist",
  "version": "1.9",
  "nodes": [
    {
      "global_node_id": "alchemist_031",
      "tree": "alchemist",
      "node_category": "micro",
      "row": 3,
      "col": 7,
      "max_stacks": 3,
      "connections": [],
      "prerequisites": ["alchemist_027"],
      "effects": ["+9% Spell Damage"]
    }
  ]
}
```

**To import:**

1. Enable debug mode with **Ctrl+Shift+D**
2. Go to **Dev Tools → Seasons**
3. Enter a season name (e.g. `Season 12 Lunaria`)
4. Upload one or more tree JSON files
5. Click **Import**
6. Set the season as active via **Set Active** or via the season dropdown on the Build Overview screen

Season files are stored under `data/seasons/{season name}/` and persist between sessions.

---

## Debug Mode

Press **Ctrl+Shift+D** anywhere in the app to toggle debug mode. This unlocks:

- **Dev Tools** button on the build select screen — access to the season importer, snapshot tools, and node editor
- **Season dropdown** on the Build Overview screen — switch between active seasons
- **Debug toolbar** in the Tree Viewer — create/delete nodes, toggle connections, assign modifiers

Debug mode state is saved to `localStorage` and persists across restarts.
