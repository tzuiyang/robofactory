"""The swappable-backend contract.

If these fail, the seam has leaked and publishing later means a rewrite.
"""

import inspect

import pytest

from rstream.cad import CADBackend, NullBackend, PlacedPart, View, get_backend
from rstream.cad.fusion import FusionBackend, FusionNotConnected


def test_all_backends_implement_the_full_interface():
    for name in ("null", "fusion"):
        b = get_backend(name)
        assert isinstance(b, CADBackend)
    abstract = {n for n, m in inspect.getmembers(CADBackend, inspect.isfunction)
                if getattr(m, "__isabstractmethod__", False)}
    for cls in (NullBackend, FusionBackend):
        missing = [n for n in abstract if not hasattr(cls, n)]
        assert not missing, f"{cls.__name__} missing {missing}"


def test_no_cad_specific_types_cross_the_seam():
    """Only neutral geom types may appear in CADBackend signatures."""
    for name, method in inspect.getmembers(CADBackend, inspect.isfunction):
        if name.startswith("_"):
            continue
        sig = inspect.signature(method)
        text = str(sig)
        for banned in ("adsk", "Fusion", "onshape", "OCC", "TopoDS"):
            assert banned not in text, f"{name}{sig} leaks {banned}"


def test_fusion_without_transport_fails_loudly():
    with pytest.raises(FusionNotConnected):
        FusionBackend().open_design("scratch")


def test_fusion_guard_is_present_in_generated_scripts():
    """The golden rule: never modify a document this backend did not create."""
    from rstream.cad.fusion import GUARD
    assert "GOLDEN RULE" in GUARD
    assert "Refusing to modify" in GUARD


def test_unauthored_archetype_raises_rather_than_returning_empty():
    b = FusionBackend(transport=lambda s: "{}")
    b.open_design("scratch")
    with pytest.raises(NotImplementedError, match="has not been authored"):
        b.instantiate_archetype("arm.3dof", {"reach_m": 0.4})


def test_null_backend_reports_it_cannot_check_interference():
    assert NullBackend().supports_interference is False


def test_null_backend_catches_slot_collisions():
    b = NullBackend()
    b.open_design("x")
    with pytest.raises(ValueError, match="slot collision"):
        b.place_parts([PlacedPart("a", "slot_0", ""), PlacedPart("b", "slot_0", "")])


def test_panel_envelope_requires_a_panel():
    with pytest.raises(RuntimeError, match="place_panel"):
        NullBackend().panel_envelope()


def test_unknown_backend_name_is_rejected():
    with pytest.raises(ValueError, match="unknown CAD backend"):
        get_backend("solidworks")
