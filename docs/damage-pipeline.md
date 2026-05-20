# Damage Pipeline

## Calculation Philosophy

Damage calculations should flow through layered stages.

Avoid isolated one-off calculations.

Prefer reusable pipelines and shared modifier systems.

---

# Standard Damage Flow

1. Base Damage
2. Added/Flat Damage
3. Increased/Reduced Modifiers
4. More/Less Multipliers
5. Damage Conversion
6. Crit Calculations
7. Resistance/Mitigation
8. Final Damage

---

# Rules

- All scaling should use centralized modifier aggregation
- Avoid duplicating increase/more logic
- Derived stats should remain reusable
- Damage types should follow shared calculation stages

---

# Future Systems

Planned support:
- ailments
- triggered skills
- conversions
- penetration
- resistance reduction
- buffs/debuffs
- snapshotting
- conditional modifiers