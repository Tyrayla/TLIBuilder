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

## Building a Distributable

```bash
npm run build:win
```

Output goes to `dist/`. The packaged app bundles the Python backend and launches it automatically — no separate Python install needed on the target machine (when built with PyInstaller integration).
