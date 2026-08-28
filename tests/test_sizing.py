import math

import pytest

from rstream.sizing import G, cycle_time, estimate_link_mass, joint_torque, move_time


def test_static_torque_matches_hand_calculation():
    # 2 kg at 1 m, massless link -> tau = m g L
    t = joint_torque(payload_kg=2.0, reach_m=1.0, link_mass_kg=0.0,
                     accel_rad_s2=0.0, safety_factor=1.0)
    assert t.static_nm == pytest.approx(2.0 * G * 1.0)
    assert t.dynamic_nm == pytest.approx(0.0)
    assert t.required_nm == pytest.approx(t.static_nm)


def test_link_mass_acts_at_centroid():
    """A uniform link contributes m*g*L/2, i.e. half a point mass at full reach."""
    with_link = joint_torque(0.0, 1.0, 2.0, accel_rad_s2=0.0, safety_factor=1.0)
    assert with_link.static_nm == pytest.approx(2.0 * G * 0.5)


def test_safety_factor_is_applied_and_reported():
    t = joint_torque(1.0, 0.5, 0.5, safety_factor=3.0)
    assert t.required_nm == pytest.approx((t.static_nm + t.dynamic_nm) * 3.0)
    assert t.safety_factor == 3.0
    assert any("safety factor" in a for a in t.assumptions)


def test_torque_rejects_impossible_inputs():
    with pytest.raises(ValueError):
        joint_torque(1.0, 0.0, 1.0)
    with pytest.raises(ValueError):
        joint_torque(-1.0, 1.0, 1.0)


def test_short_move_is_triangular_and_matches_closed_form():
    # Too short to reach cruise: t = 2*sqrt(d/a)
    m = move_time(0.05, max_speed_m_s=1.0, accel_m_s2=2.0)
    assert m.profile == "triangular"
    assert m.seconds == pytest.approx(2 * math.sqrt(0.05 / 2.0))


def test_long_move_is_trapezoidal_and_slower_than_pure_cruise():
    m = move_time(5.0, max_speed_m_s=1.0, accel_m_s2=2.0)
    assert m.profile == "trapezoidal"
    assert m.seconds > 5.0 / 1.0  # ramp time is not free


def test_zero_distance_is_zero_time():
    assert move_time(0.0, 1.0, 2.0).seconds == 0.0


def test_cycle_time_breakdown_sums_to_total():
    c = cycle_time(0.4, 0.4)
    assert sum(c.breakdown.values()) == pytest.approx(c.seconds_per_cycle)
    assert c.parts_per_hour == pytest.approx(3600.0 / c.seconds_per_cycle)


def test_cycle_time_states_its_exclusions():
    c = cycle_time(0.3, 0.3)
    assert any("excludes" in a for a in c.assumptions)


def test_link_mass_scales_with_reach():
    assert estimate_link_mass(1.0) > estimate_link_mass(0.5)


# --- per-joint load path ----------------------------------------------------

from rstream.capabilities import Capability
from rstream.sizing import MIN_MOMENT_ARM_M, chain_loads, worst_case
from rstream.topology import synthesize


def _arm_topology(reach_m=0.7):
    return synthesize({Capability.MANIPULATION, Capability.GRASPING},
                      payload_kg=0.5, reach_m=reach_m)


def test_torque_falls_off_down_the_chain():
    """A wrist holding a gripper is not doing the shoulder's job. If this ever
    goes flat, per-joint sizing has silently reverted to worst-case sizing."""
    loads = {l.label: l for l in chain_loads(_arm_topology(), payload_kg=0.5)}
    assert loads["shoulder"].torque.required_nm > loads["elbow"].torque.required_nm
    assert loads["elbow"].torque.required_nm > loads["wrist"].torque.required_nm


def test_moment_arm_shrinks_toward_the_tip():
    loads = {l.label: l for l in chain_loads(_arm_topology(), payload_kg=0.5)}
    assert loads["shoulder"].moment_arm_m > loads["elbow"].moment_arm_m
    assert loads["wrist"].moment_arm_m >= MIN_MOMENT_ARM_M


def test_only_the_effector_branch_carries_the_payload():
    loads = chain_loads(_arm_topology(), payload_kg=0.5)
    assert all(l.carries_payload for l in loads if l.sizing_basis == "cantilever")
    # and the distal mass strictly decreases toward the tip
    masses = [l.distal_mass_kg for l in loads if l.sizing_basis == "cantilever"]
    assert masses == sorted(masses, reverse=True)


def test_wheeled_base_is_sized_by_traction_not_by_the_arm_formula():
    """A drive wheel is a traction problem, and the numbers are nothing like a
    cantilever's. Sizing it with the arm formula put a 1,480 USD shoulder-class
    actuator on a 12 kg rover — the most expensive line in the BOM, chosen by a
    calculation that did not apply to it."""
    topo = synthesize({Capability.MOBILITY}, payload_kg=1.0, reach_m=0.0)
    loads = [l for l in chain_loads(topo, payload_kg=1.0) if l.module_id == "base.diffdrive"]
    assert len(loads) == 1
    drive = loads[0]
    assert drive.sizing_basis == "traction"
    assert drive.count == 2, "two wheels need two motors, not one"
    assert drive.detail["slip_margin"] > 0
    assert drive.detail["wheel_speed_rad_s"] > 0
    # a light rover on 100 mm wheels is a low-torque, high-speed problem
    assert drive.torque.required_nm < 10.0


def test_unmodelled_axes_are_not_given_a_fabricated_torque():
    """A gantry lead screw still has no model. It must come back as None, not as
    zero and not as the arm formula — a skipped calculation is never a pass."""
    topo = synthesize({Capability.MANIPULATION, Capability.GRASPING},
                      payload_kg=1.0, reach_m=0.4, workspace_is_planar=True)
    gantry = [l for l in chain_loads(topo, payload_kg=1.0) if l.module_id == "base.gantry"]
    assert gantry, "a gantry has actuated axes"
    assert all(l.torque is None and l.sizing_basis == "unmodelled" for l in gantry)


def test_worst_case_is_the_governing_joint():
    loads = chain_loads(_arm_topology(), payload_kg=0.5)
    w = worst_case(loads)
    assert w.required_nm == max(l.torque.required_nm for l in loads if l.torque)


def test_heavier_payload_raises_every_joint():
    light = {l.label: l.torque.required_nm for l in chain_loads(_arm_topology(), 0.2)}
    heavy = {l.label: l.torque.required_nm for l in chain_loads(_arm_topology(), 2.0)}
    assert all(heavy[k] > light[k] for k in light)


# --- traction ---------------------------------------------------------------

from rstream.sizing import drive_torque


def test_drive_torque_scales_with_wheel_radius():
    """Torque at the wheel is force x radius. Bigger wheels are a torque cost
    and a speed win, and the trade has to show up in the numbers."""
    small = drive_torque(20.0, 0.08)
    big = drive_torque(20.0, 0.20)
    assert big.torque.required_nm > small.torque.required_nm
    assert big.wheel_speed_rad_s < small.wheel_speed_rad_s


def test_grade_dominates_rolling_resistance():
    """Starting on a ramp is the sizing case, not cruising on the flat."""
    flat = drive_torque(20.0, 0.10, grade_deg=0.0)
    ramp = drive_torque(20.0, 0.10, grade_deg=10.0)
    assert ramp.torque.static_nm > flat.torque.static_nm * 2


def test_traction_limit_can_bind_before_the_motor_does():
    """On a slick floor or a steep grade the wheels slip, and no amount of extra
    motor fixes it. If this ever reports a margin >= 1 the gate stops catching
    designs that cannot put their force down."""
    slippery = drive_torque(40.0, 0.10, grade_deg=25.0, friction_coeff=0.15)
    assert slippery.slip_margin < 1.0
    assert slippery.tractive_force_n > slippery.traction_limit_n


def test_drive_estimate_states_what_it_excludes():
    d = drive_torque(20.0, 0.10)
    assert any("excludes" in a for a in d.torque.assumptions)
    assert any("grade" in a for a in d.torque.assumptions)


def test_drive_torque_rejects_impossible_inputs():
    for args in ((0.0, 0.1), (10.0, 0.0)):
        with pytest.raises(ValueError):
            drive_torque(*args)
    with pytest.raises(ValueError):
        drive_torque(10.0, 0.1, n_driven=0)
