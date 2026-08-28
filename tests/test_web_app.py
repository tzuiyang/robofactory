"""The app users touch must be the pipeline, not a shortcut around it.

Until 2026-08-28 `serve.py` called `config.build()` directly and forced
`verified=True` on every part, so the web path had no L4 gate, wrote no design
record, and quoted prices from placeholder part numbers — while `demo.py`, which
nobody ships, ran the real thing. These tests pin the app to `pipeline.run()`.
"""

import importlib.util
from dataclasses import replace
from pathlib import Path

import pytest

from rstream.catalog import Catalog
from rstream.dialogue import GuidedIntake

ROOT = Path(__file__).resolve().parents[1]

ANSWERS = [
    ("task", "pick up small parts and put them in a bin"),
    ("object", "machined part"),
    ("weight_refine", "lighter than a phone"),
    ("area", "a laptop"),
    ("budget", "under $3,000"),
    ("confirm", "yes, that's right"),
]


@pytest.fixture
def serve_mod():
    spec = importlib.util.spec_from_file_location("_serve", ROOT / "serve.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def intake():
    g = GuidedIntake()
    for k, v in ANSWERS:
        g.answer(k, v)
    return g


def test_app_does_not_ship_a_verified_override(serve_mod):
    """The catalog the app serves is the catalog on disk, unedited."""
    assert serve_mod.DEMO_MODE is False, "demo mode must never default on"
    assert serve_mod.CATALOG.stats()["verified"] == Catalog.load().stats()["verified"], (
        "serve.py must not re-stamp verified on parts no human has checked")


def test_unverified_catalog_blocks_the_quote(serve_mod, intake):
    """The seed catalog is 100% unverified, so there is no price to show."""
    out = serve_mod.result_payload(intake)
    assert out["ok"] is False
    assert out.get("price") is None
    assert "confirming prices" in out["message"], (
        "the customer must be told the parts are unchecked, not that their "
        f"machine is too big: {out['message']!r}"
    )


def test_verified_catalog_reaches_the_human_gate(serve_mod, intake, verified_catalog,
                                                 tmp_path, monkeypatch):
    monkeypatch.setattr(serve_mod, "CATALOG", verified_catalog)
    monkeypatch.setattr(serve_mod, "RUNS_DIR", tmp_path)
    out = serve_mod.result_payload(intake)

    assert out["ok"] is True
    assert out["outcome"] == "awaiting_human_review", (
        "the app must stop at the human gate — never past it")
    assert out["price"], "a design that cleared the gate gets a price"

    # The record is the unit of persistence and the dataset. No record, no flywheel.
    assert (tmp_path / f"{out['record_id']}.json").exists()


def test_every_l4_check_reaches_the_engineering_view(serve_mod, intake,
                                                     verified_catalog, tmp_path,
                                                     monkeypatch):
    monkeypatch.setattr(serve_mod, "CATALOG", verified_catalog)
    monkeypatch.setattr(serve_mod, "RUNS_DIR", tmp_path)
    checks = serve_mod.result_payload(intake)["internal"]["checks"]

    names = {c["name"] for c in checks}
    assert {"catalog_verified", "reach", "interference"} <= names

    # A skipped check is never a pass. The null backend has no B-rep, and the
    # screen an engineer signs off on has to say so.
    interference = next(c for c in checks if c["name"] == "interference")
    assert interference["status"] == "skipped"


def test_customer_view_carries_no_engineering_detail(serve_mod, intake,
                                                     verified_catalog, tmp_path,
                                                     monkeypatch):
    monkeypatch.setattr(serve_mod, "CATALOG", verified_catalog)
    monkeypatch.setattr(serve_mod, "RUNS_DIR", tmp_path)
    out = serve_mod.result_payload(intake)
    customer = " ".join(
        [out["machine"], out["speed"], out["price"] or ""]
        + out["parts"] + out["abilities"] + out["caveats"]
    ).lower()
    for word in ("dof", "torque", "nm", "actuator", "kinematic", "revolute"):
        assert word not in customer.split(), f"{word!r} leaked into the customer view"


def test_unpriceable_design_is_still_shown(serve_mod, intake, tmp_path, monkeypatch):
    """"Unverified parts cannot be quoted" is a rule about the price, not the design.

    The machine, its parts and its cycle time are all still true. Blanking the
    whole screen taught the person nothing and read as "we can't build this",
    which was false.
    """
    monkeypatch.setattr(serve_mod, "DEMO_MODE", True)
    monkeypatch.setattr(serve_mod, "RUNS_DIR", tmp_path)
    out = serve_mod.result_payload(intake)

    assert out["ok"] is True
    assert out["machine"] and out["parts"] and out["speed"]
    assert out["price"] is None, "an unverified BOM must never carry a number"
    assert out["price_withheld"], "and the screen must say why"
    assert out["outcome"] == "draft", (
        "the gate is not weakened — the design simply did not clear it")

    failed = [c["name"] for c in out["internal"]["checks"] if c["status"] == "fail"]
    assert failed == ["catalog_verified"], (
        "only the verification failure is tolerated this way; any other failure "
        f"must still blank the result, got {failed}")


def test_a_real_failure_still_blanks_the_result(serve_mod, tmp_path, monkeypatch):
    """A design that fails something other than verification gets no design screen."""
    monkeypatch.setattr(serve_mod, "DEMO_MODE", True)
    monkeypatch.setattr(serve_mod, "RUNS_DIR", tmp_path)
    g = GuidedIntake()
    for k, v in [("task", "move engine blocks around a workshop"),
                 ("object", "something else"), ("weight_refine", "heavier than that"),
                 ("area", "a garage"), ("budget", "under $3,000"),
                 ("confirm", "yes, that's right")]:
        g.answer(k, v)
    out = serve_mod.result_payload(g)
    assert out["ok"] is False
    assert "price" not in out or out["price"] is None
    assert out["message"]
