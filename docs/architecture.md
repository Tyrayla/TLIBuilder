# Architecture Overview

## Application Stack

- Python backend server
- React frontend
- Electron desktop shell

## Core Systems

### Importer
Responsible for:
- loading seasonal JSON data
- normalizing structures
- validating references
- generating lookup maps/indexes

### Engine
Responsible for:
- all combat calculations
- stat aggregation
- modifier evaluation
- derived stat computation
- damage pipelines

### Persistence
Responsible for:
- saving builds
- loading builds
- tree configurations
- user state/preferences

### Frontend
Responsible for:
- rendering UI
- displaying calculated values
- user interaction
- build editing

The frontend must not contain combat logic.

---

# Data Flow

Season JSON Files
→ Importer
→ Normalized Data Structures
→ Engine
→ Computed Build State
→ Frontend Rendering

---

# Architectural Constraints

- Combat logic belongs only in /engine
- Imported JSON data is the authoritative game-data source
- Modifier logic should remain centralized
- Avoid duplicated scaling pipelines
- Systems should remain deterministic and testable