# TLI Builder

A Torchlight Infinite build creation program.

---

## Requirements

| Tool | Version |
|------|---------|
| Python | 3.10+ |
| Node.js | 18+ |
| npm | 9+ |

---

## Setup

### 1. Install Python dependencies

```bash
pip install fastapi uvicorn pydantic python-multipart
```

### 2. Install Node dependencies

```bash
npm install
```

---

## Running in Development

Start the app with a single command from the project root:

```bash
npm run dev
```

This launches both the Electron window and the Python backend (`server.py`) automatically. The backend runs on port 8765 by default.

To see verbose logs from both processes:

```bash
npm run dev:verbose
```

---

## Project Structure

```
TLICalc/
├── server.py                  # FastAPI backend — tree data, builds, season API
├── trees/                     # Python talent tree definitions (one file per tree)
│   └── registry.py            # Master list of all trees
├── models/                    # Data models (PassiveTree, PassiveNode, Stat, etc.)
├── persistence/               # JSON file managers (builds, seasons, node stats, etc.)
├── tools/                     # Utilities (season importer, snapshot differ, etc.)
├── data/
│   ├── seasons/               # Imported season data (one folder per season)
│   │   └── Season 12 Lunaria/ # Example: one JSON file per tree
│   └── ...                    # node_stats.json, node_modifiers.json, etc.
└── src/
    ├── main/                  # Electron main process
    ├── preload/               # Electron preload bridge
    └── renderer/src/          # React frontend
        ├── api/client.ts      # All API calls
        ├── screens/           # Full-page views (BuildOverview, TreeViewer, etc.)
        └── components/        # Shared UI components
```

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

---

## Building a Distributable

```bash
npm run build:win
```

Output goes to `dist/`. The packaged app bundles the Python backend and launches it automatically — no separate Python install needed on the target machine (when built with PyInstaller integration).
