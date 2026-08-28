"""An actuator's role is a hard constraint, not a preference.

The end-to-end user test on 2026-08-28 returned a BOM that put `act.drive` — the
continuous-rotation wheel gearmotor — in the *elbow* of a bench-mounted arm,
because selection filtered on torque and speed alone and every actuator shared
one PartKind. It read as a plausible parts list and described an unbuildable
machine. These tests pin both directions.
"""

from dataclasses import replace

import pytest

from rstream.capabilities import Capability
from rstream.catalog import ActuatorRole, Catalog, PartKind
from rstream.config import InfeasibleError, build
from rstream.intake import Requirements


def _actuators(cfg, tier="good"):
    return [l.part for l in cfg.tiers[tier].lines if l.part.actuator]


def test_drive_motor_never_lands_on_an_arm_joint(verified_catalog, small_req):
    cfg = build(small_req, verified_catalog)
    picked = _actuators(cfg)
    assert picked, "the arm must select at least one actuator"
    assert all(p.actuator.role is ActuatorRole.JOINT for p in picked), (
        "a bench arm has no wheels; every actuator on it must be able to hold "
        f"position, got {[(p.id, p.actuator.role.value) for p in picked]}"
    )


def test_wheeled_base_still_gets_the_drive_motor(verified_catalog):
    req = Requirements(
        task="drive around a warehouse carrying small boxes",
        payload_kg=2.0, reach_m=0.3, budget_usd=3000.0, workspace_m=6.0,
        capabilities={Capability.MOBILITY},
    )
    cfg = build(req, verified_catalog)
    drive_axes = [l for l in cfg.joint_loads if l.sizing_basis == "traction"]
    assert drive_axes, "a mobility request must produce a traction-sized axis"
    picked = _actuators(cfg)
    assert any(p.actuator.role is ActuatorRole.DRIVE for p in picked), (
        "the wheels need a drive gearmotor, not a high-ratio joint servo: "
        f"got {[(p.id, p.actuator.role.value) for p in picked]}"
    )


def test_role_is_a_hard_filter_in_the_query(verified_catalog):
    joint = verified_catalog.query(kind=PartKind.ACTUATOR,
                                   actuator_role=ActuatorRole.JOINT)
    drive = verified_catalog.query(kind=PartKind.ACTUATOR,
                                   actuator_role=ActuatorRole.DRIVE)
    assert joint and drive, "the seed catalog must carry both roles"
    assert not set(p.id for p in joint) & set(p.id for p in drive)


def test_unmarked_actuator_defaults_to_joint(verified_catalog):
    """The conservative default: an unmarked part must not be usable as a wheel
    motor, because that failure is silent. The reverse shows up as a slow robot."""
    from rstream.catalog.schema import ActuatorSpec
    spec = ActuatorSpec(stall_torque_nm=4.0, rated_torque_nm=2.0, max_speed_rad_s=5.0)
    assert spec.role is ActuatorRole.JOINT


def test_no_drive_actuator_in_catalog_fails_loudly_rather_than_substituting(
        verified_catalog):
    joint_only = Catalog([p for p in verified_catalog.query(allow_unverified=True)
                          if not (p.actuator and p.actuator.role is ActuatorRole.DRIVE)])
    req = Requirements(
        task="drive around a warehouse carrying small boxes",
        payload_kg=2.0, reach_m=0.3, budget_usd=3000.0, workspace_m=6.0,
        capabilities={Capability.MOBILITY},
    )
    with pytest.raises(InfeasibleError, match="drive actuator"):
        build(req, joint_only)
