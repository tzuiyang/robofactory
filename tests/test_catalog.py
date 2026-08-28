import pytest

from rstream.catalog import Catalog, PartKind, UnverifiedPartError
from rstream.catalog.schema import Dimensions, Geometry


@pytest.fixture
def catalog():
    return Catalog.load()


def test_seed_catalog_loads(catalog):
    assert len(catalog) > 0


def test_unverified_parts_are_not_quotable_by_default(catalog):
    """The 'never invent a part number' rule, enforced in code."""
    assert catalog.query() == []
    assert catalog.query(allow_unverified=True) != []


def test_assert_quotable_rejects_unverified(catalog):
    parts = catalog.query(allow_unverified=True)
    with pytest.raises(UnverifiedPartError):
        catalog.assert_quotable(parts)


def test_unknown_part_raises_with_actionable_message(catalog):
    with pytest.raises(KeyError, match="never invented at runtime"):
        catalog.get("act.doesnotexist")


def test_torque_filter_excludes_undersized(catalog):
    strong = catalog.query(kind=PartKind.ACTUATOR, min_torque_nm=20.0, allow_unverified=True)
    assert all(p.actuator.rated_torque_nm >= 20.0 for p in strong)
    assert len(strong) < len(catalog.query(kind=PartKind.ACTUATOR, allow_unverified=True))


def test_keepout_is_included_in_envelope():
    d = Dimensions(100, 50, 20, keepout_length_mm=25)
    assert d.envelope_mm == (125, 50, 20)
    assert d.envelope_volume_m3 > (100 * 50 * 20) * 1e-9


def test_mesh_geometry_is_rejected():
    """A mesh has no planar face to mate against."""
    with pytest.raises(ValueError, match="mesh formats"):
        Geometry(step_path="/parts/servo.stl")
    Geometry(step_path="/parts/servo.step")  # accepted


def test_actuator_must_carry_spec():
    from rstream.catalog.schema import Part
    with pytest.raises(ValueError, match="ActuatorSpec"):
        Part(id="x", kind=PartKind.ACTUATOR, manufacturer="m", part_number="p",
             description="", price_usd=1.0, dimensions=Dimensions(1, 1, 1), mass_kg=0.1)
