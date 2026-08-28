"""robotics_streamline — AI pre-sales concepting for custom robotics.

Layer map (see docs/architecture.md):
    L0 catalog/   parts + archetypes (offline, human-curated)
    L1 intake     requirements extraction            [not yet built]
    L2 sizing/    formulas + constrained BOM query
    L3 cad/       geometry, behind a swappable backend
    L4 validate/  deterministic gate -> vision gate  [not yet built]
    L5 present/   kinematic sim + BOM doc            [not yet built]
"""

__version__ = "0.1.0"
