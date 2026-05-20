# Modifier Architecture

The modifier system consists of three layers:

1. Raw Imported Data
2. Normalized Modifier Definitions
3. Engine Evaluation

These layers should remain separated.

---

# Raw Imported Data

Imported seasonal JSON files contain:
- human-readable effect strings
- source-specific affixes
- parsed numeric ranges
- metadata from the game client

These structures are not considered engine-ready.

Examples:
- item affixes
- talent effects
- buff descriptions
- skill text

Different systems may contain entirely different modifier pools and wording structures.

This is expected.

---

# Normalized Modifier Definitions

The importer pipeline should normalize raw imported data into canonical modifier representations.

The normalized layer provides:
- shared stat identifiers
- standardized operations
- consistent value structures
- reusable tags/categories
- UI metadata

This layer acts as the bridge between imported game data and engine calculations.

---

# Engine Evaluation

The engine evaluates normalized modifiers through shared aggregation pipelines.

The engine should not depend on:
- raw item text
- talent wording
- source-specific formatting

The engine should operate on normalized modifier semantics only.

---

# Canonical Stat Semantics

Raw imported text should eventually normalize into canonical semantic stat identifiers.

Examples:

Raw:
- "+9% Damage"
- "+12% Sentry Damage"
- "+(30–40)% Gear Physical Damage"

Normalized:
- damage.generic.increased
- damage.sentry.increased
- damage.physical.gear.increased

The engine should operate primarily on canonical stat semantics rather than human-readable imported text.

This allows:
- reusable aggregation pipelines
- source-independent calculations
- scalable stat relationships
- simplified debugging
- dynamic UI grouping/filtering

The importer pipeline is responsible for translating raw imported text into normalized semantic modifier definitions.

---

# Modifier Metadata

Normalized modifiers should support metadata for:
- UI grouping
- filtering
- categorization
- display ordering
- source restrictions
- conditional evaluation

Examples:
- category
- subgroup
- tags
- display labels
- source type
- pipeline stage

Example conceptual metadata:

- category: offense
- subgroup: physical_damage
- tags: [physical, damage]
- pipeline_stage: increased_reduced

Metadata should remain data-driven whenever possible.

Avoid hardcoded UI grouping logic.

The UI layer should preferably consume modifier metadata dynamically for:
- grouped displays
- stat filtering
- searchable modifiers
- dynamic stat panels
- tooltip generation