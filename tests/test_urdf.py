"""URDF export — the design record in the syntax a simulator reads.

Every check here is something a simulator would otherwise discover at load time,
which is the expensive place to discover it. The structural ones (one root, no
orphans, no link with two parents, non-zero mass) are exactly what `check_urdf`
and Gazebo's parser reject on, reimplemented so the suite catches them without a
dependency.
"""

import shutil
import subprocess
import xml.etree.ElementTree as ET

import pytest

from rstream.capabilities import Capability
from rstream.config import build
from rstream.export import URDFError, urdf_document
from rstream.intake import Requirements
from rstream.modules import LIBRARY, ModuleKind


@pytest.fixture
def arm_cfg(verified_catalog, small_req):
    return build(small_req, verified_catalog)


@pytest.fixture
def rover_cfg(verified_catalog):
    req = Requirements(
        task="drive around and tell me what it sees",
        payload_kg=0.5, reach_m=0.3, budget_usd=9000.0, workspace_m=4.0,
        capabilities={Capability.MOBILITY, Capability.VISION,
                      Capability.AUDIO_OUT, Capability.ONBOARD_COMPUTE},
    )
    return build(req, verified_catalog)


def _root(cfg, tier="good"):
    return ET.fromstring(urdf_document(cfg, tier))


# --- structure ---------------------------------------------------------------

def test_exactly_one_root_link(arm_cfg, rover_cfg):
    for cfg in (arm_cfg, rover_cfg):
        r = _root(cfg)
        links = {l.get("name") for l in r.findall("link")}
        children = {j.find("child").get("link") for j in r.findall("joint")}
        assert len(links - children) == 1, "a URDF is a tree with one root"


def test_no_link_has_two_parents(arm_cfg, rover_cfg):
    for cfg in (arm_cfg, rover_cfg):
        children = [j.find("child").get("link") for j in _root(cfg).findall("joint")]
        assert len(children) == len(set(children))


def test_every_joint_endpoint_exists(arm_cfg, rover_cfg):
    for cfg in (arm_cfg, rover_cfg):
        r = _root(cfg)
        links = {l.get("name") for l in r.findall("link")}
        for j in r.findall("joint"):
            assert j.find("parent").get("link") in links
            assert j.find("child").get("link") in links


def test_every_link_is_simulatable(arm_cfg, rover_cfg):
    """Gazebo refuses a zero-mass link and behaves oddly around zero inertia."""
    for cfg in (arm_cfg, rover_cfg):
        for link in _root(cfg).findall("link"):
            inertial = link.find("inertial")
            assert inertial is not None, f"{link.get('name')} has no inertial"
            assert float(inertial.find("mass").get("value")) > 0
            inertia = inertial.find("inertia")
            for axis in ("ixx", "iyy", "izz"):
                assert float(inertia.get(axis)) > 0
            assert link.find("collision") is not None


def test_the_control_panel_is_not_inside_the_base(arm_cfg):
    """It is off the kinematic tree, so it defaulted to the origin and put a
    240 mm box through the middle of the base."""
    r = _root(arm_cfg)
    panel = next(j for j in r.findall("joint")
                 if j.find("child").get("link") == "control_panel")
    xyz = [float(v) for v in panel.find("origin").get("xyz").split()]
    assert any(abs(v) > 0.1 for v in xyz), "the panel is stacked on the base"


# --- the numbers -------------------------------------------------------------

def test_joint_limits_come_from_the_selected_actuators(arm_cfg):
    """The whole point. Most hand-written URDFs invent effort and velocity
    limits because no motor has been picked; here one has."""
    chosen = {}
    for line in arm_cfg.tiers["good"].lines:
        if line.part.actuator:
            for label in line.joints:
                chosen[label] = line.part

    r = _root(arm_cfg)
    moving = [j for j in r.findall("joint") if j.get("type") != "fixed"]
    assert moving, "an arm must have moving joints"
    for j in moving:
        label = j.find("child").get("link")
        part = chosen.get(label)
        assert part is not None, f"no actuator recorded for {label}"
        limit = j.find("limit")
        assert float(limit.get("effort")) == pytest.approx(
            part.actuator.rated_torque_nm)
        assert float(limit.get("velocity")) == pytest.approx(
            part.actuator.max_speed_rad_s)


def test_joint_offsets_match_the_sized_link_lengths(arm_cfg):
    """The simulated arm must not out-reach the arm we sized. A joint module
    that offset its child would add reach without adding moment arm."""
    lengths = sorted(round(i.params["length_m"], 6)
                     for i in arm_cfg.topology.instances
                     if i.module.kind is ModuleKind.LINK)
    offsets = sorted(round(float(j.find("origin").get("xyz").split()[0]), 6)
                     for j in _root(arm_cfg).findall("joint")
                     if float(j.find("origin").get("xyz").split()[0]) > 0)
    assert offsets == lengths


def test_a_wheeled_base_gets_both_wheels(rover_cfg):
    """Two DOF means two wheels. Nothing mounts to a wheel, so the tree walk
    cannot place them and the base would roll on nothing."""
    r = _root(rover_cfg)
    wheels = [j for j in r.findall("joint") if j.get("type") == "continuous"]
    assert len(wheels) == 2
    ys = sorted(float(j.find("origin").get("xyz").split()[1]) for j in wheels)
    assert ys[0] == pytest.approx(-ys[1]), "wheels must straddle the chassis"


def test_reach_discrepancy_is_reported_not_hidden(arm_cfg):
    """Link lengths sum to ~1.08x the quoted reach (TODO.md). Anyone measuring
    the model has to be told before they measure."""
    doc = urdf_document(arm_cfg, "good")
    assert "quoted reach" in doc


def test_a_mobile_base_is_not_judged_on_reach(rover_cfg):
    """It carries a reach figure it never uses; comparing against it reported a
    false 0.00x."""
    assert "quoted reach" not in urdf_document(rover_cfg, "good")


# --- refusing to emit rubbish ------------------------------------------------

def test_a_broken_topology_raises_rather_than_emitting(arm_cfg):
    arm_cfg.topology.instances[2].parent = "does_not_exist"
    with pytest.raises(URDFError, match="does not exist"):
        urdf_document(arm_cfg, "good")


def test_every_module_declares_a_frame():
    """A module without one silently exports as a 60 mm cube at the origin."""
    default = LIBRARY["base.fixed"].frame.__class__()
    unset = [m.id for m in LIBRARY.values() if m.frame == default]
    assert not unset, f"modules with no authored frame: {unset}"


def test_the_file_says_what_it_does_not_verify(arm_cfg):
    doc = urdf_document(arm_cfg, "good")
    assert "CONCEPT MODEL" in doc
    for claim in ("tolerance", "wiring", "control stability"):
        assert claim in doc


# --- the real parser ---------------------------------------------------------

#: `check_urdf` ships with urdfdom, the C++ library ROS and Gazebo actually use
#: to read URDF. Everything above is our reading of the spec, written from the
#: outside; this is the ground truth. Skipped rather than required, so the suite
#: still runs on a machine without it — but when it is present it is the check
#: that matters.
CHECK_URDF = shutil.which("check_urdf") or shutil.which(
    "check_urdf", path="/opt/homebrew/bin:/usr/local/bin")
needs_urdfdom = pytest.mark.skipif(
    CHECK_URDF is None, reason="urdfdom not installed (brew install urdfdom)")


def _check_urdf(doc: str, tmp_path, name: str):
    f = tmp_path / f"{name}.urdf"
    f.write_text(doc)
    r = subprocess.run([CHECK_URDF, str(f)], capture_output=True, text=True)
    assert r.returncode == 0, f"check_urdf rejected {name}:\n{r.stderr or r.stdout}"
    assert "Successfully Parsed XML" in r.stdout
    return r.stdout


@needs_urdfdom
def test_gazebos_own_parser_accepts_an_arm(arm_cfg, tmp_path):
    out = _check_urdf(urdf_document(arm_cfg, "good", "arm"), tmp_path, "arm")
    assert "root Link: base" in out


@needs_urdfdom
def test_gazebos_own_parser_accepts_a_rover(rover_cfg, tmp_path):
    """The wheels are attached outside the generic tree walk, which is exactly
    the kind of hand-placed structure a parser catches and a unit test does not."""
    out = _check_urdf(urdf_document(rover_cfg, "good", "rover"), tmp_path, "rover")
    assert "root Link: drive_base" in out
    assert "wheel_left" in out and "wheel_right" in out


@needs_urdfdom
def test_gazebos_own_parser_accepts_a_mobile_manipulator(verified_catalog, tmp_path):
    """Wheels and a full arm chain hanging off one root — the shape most likely
    to produce two roots or an orphan."""
    req = Requirements(
        task="drive around and pick things up", payload_kg=1.0, reach_m=0.5,
        budget_usd=9000.0, workspace_m=5.0,
        capabilities={Capability.MOBILITY, Capability.MANIPULATION,
                      Capability.GRASPING, Capability.VISION},
    )
    cfg = build(req, verified_catalog)
    out = _check_urdf(urdf_document(cfg, "good", "mm"), tmp_path, "mm")
    assert "root Link: drive_base" in out
    assert "end_effector" in out
