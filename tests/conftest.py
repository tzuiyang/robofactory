import json
from dataclasses import replace
from pathlib import Path

import pytest

from rstream.catalog import Catalog
from rstream.intake import Requirements


@pytest.fixture
def seed_catalog():
    """The real seed catalog — everything unverified, so nothing is quotable."""
    return Catalog.load()


@pytest.fixture
def verified_catalog():
    """Seed catalog with verification forced on, to exercise the happy path.

    A fixture, never a runtime flag: in production only a human sets verified.
    """
    c = Catalog.load()
    return Catalog([replace(p, verified=True) for p in c.query(allow_unverified=True)])


@pytest.fixture
def deep_catalog(verified_catalog):
    """A catalog with enough actuator depth to produce genuinely distinct tiers.

    Exists because the seed catalog's three actuators collapse into one tier —
    which is the correct behaviour, but means it cannot exercise tier downgrade.
    Real tiering depends on catalog depth; this fixture makes that explicit.
    """
    from rstream.catalog.schema import ActuatorSpec, Dimensions, Part, PartKind

    parts = verified_catalog.query(allow_unverified=True)
    for i, (torque, price) in enumerate(
        [(9.0, 150.0), (16.0, 300.0), (30.0, 520.0), (55.0, 900.0), (90.0, 1500.0)]
    ):
        parts.append(Part(
            id=f"act.t{i}", kind=PartKind.ACTUATOR, manufacturer="PLACEHOLDER",
            part_number=f"PLACEHOLDER-ACT-T{i}", description=f"test actuator {torque} Nm",
            price_usd=price, mass_kg=0.2 + i * 0.2,
            dimensions=Dimensions(50 + i * 10, 30, 60 + i * 10, keepout_length_mm=10),
            actuator=ActuatorSpec(stall_torque_nm=torque * 2, rated_torque_nm=torque,
                                  max_speed_rad_s=5.0, gear_ratio=100),
            verified=True,
        ))
    return Catalog(parts)


@pytest.fixture
def req():
    return Requirements(
        task="pick 0.8 kg parts from a tray and place them into a fixture",
        payload_kg=0.8,
        reach_m=0.45,
        budget_usd=9000.0,
    )


@pytest.fixture
def small_req():
    """A machine that is actually inside what we build: under 3,000 USD in parts.

    With placeholder prices that means roughly a 0.35 m reach at 0.5 kg. Past
    that the shoulder jumps an actuator class and one part takes half the parts
    budget — see `test_cost_ceiling_blocks_a_machine_we_would_not_build`.
    """
    from rstream.capabilities import Capability
    return Requirements(
        task="pick small parts off a bench and set them into a tray",
        payload_kg=0.5,
        reach_m=0.35,
        budget_usd=9000.0,
        capabilities={Capability.MANIPULATION, Capability.GRASPING},
    )
