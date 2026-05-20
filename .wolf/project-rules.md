# TLIBuilder

TLIBuilder is a Torchlight Infinite-style build planner and calculator.

The application consists of:
- Python backend server
- React frontend
- Electron desktop shell

The project supports multiple seasons and stores game data in structured JSON files imported into the application through importer systems.

---

# Core Architecture Rules

## Separation of Concerns

- All calculation logic belongs inside `/engine`
- UI components must NEVER contain combat calculations
- Persistence managers must NEVER contain calculation logic
- Importers are responsible for translating raw game data into normalized internal structures
- Data JSON files are the authoritative source for game data

---

# Data System

## Seasonal Data

Game data is stored per season in structured JSON files.

Examples include:
- Legendary gear
- Talent tree nodes
- Talent tree connections
- Node positions
- Passive effects
- Skill data
- Modifier data
- Other imported game systems

The importer pipeline is responsible for:
- Loading raw data
- Normalizing structures
- Validating references
- Creating lookup maps/indexes when needed

The engine should consume imported/normalized data rather than hardcoded values.

NEVER hardcode:
- item stats
- talent effects
- scaling values
- node connections
- modifier definitions
- skill metadata

Always attempt to retrieve data from imported JSON structures first.

---

# Calculation Engine Rules

## Engine Goals

The calculation engine must:
- Avoid duplicated logic
- Use centralized stat aggregation
- Be deterministic and testable
- Support future extensibility
- Remain data-driven
- Minimize side effects

---

# Damage System Rules

All damage calculations belong under `/engine`.

Examples:
- hit damage
- ailment damage
- crit calculations
- resistance calculations
- penetration
- conversion
- scaling modifiers
- triggered effects
- buffs/debuffs

The engine should prefer reusable calculation pipelines over isolated formulas.

Avoid:
- duplicated modifier handling
- duplicated scaling pipelines
- isolated one-off calculations

Prefer:
- shared modifier systems
- reusable stat aggregation
- layered calculation stages
- centralized scaling logic

---

# Recommended Engine Structure

/engine
  /stats
  /damage
  /ailments
  /defense
  /modifiers
  /pipeline
  /conditions
  /utils

---

# Stat Aggregation Philosophy

Stats should flow through layered aggregation stages.

Example:
1. Base values
2. Added values
3. Increased/reduced modifiers
4. More/less multipliers
5. Conversion
6. Crit calculations
7. Resistance/mitigation
8. Final damage

Avoid mixing unrelated stages together.

---

# Persistence Rules

Persistence managers are responsible for:
- saving builds
- loading builds
- tree configurations
- season state
- user preferences

Persistence managers should NOT:
- calculate combat values
- contain business logic
- mutate engine state unexpectedly

---

# Frontend Rules

React components should:
- remain presentation-focused
- consume computed engine output
- avoid embedded calculation logic
- avoid duplicating modifier behavior

Complex calculations should be delegated to the engine.

---

# Workflow Rules

Before implementing major features:
1. Analyze existing architecture
2. Identify affected systems/files
3. Propose implementation plan
4. Minimize unrelated refactors
5. Reuse existing pipelines whenever possible

---

# Coding Style

- Prefer pure functions
- Prefer strong typing
- Avoid hidden side effects
- Keep systems modular
- Keep formulas centralized
- Use descriptive naming
- Avoid magic numbers
- Favor composition over duplication

---

# Performance Goals

The engine should eventually support:
- fast recalculation
- partial recomputation
- scalable modifier evaluation
- cached derived values where appropriate

Avoid premature optimization, but maintain extensible architecture.

---

# Important Constraints

Do not:
- duplicate formula implementations
- hardcode imported game data
- place combat logic inside UI
- tightly couple systems unnecessarily

Always prefer:
- reusable systems
- centralized logic
- data-driven architecture
- importer-backed data access