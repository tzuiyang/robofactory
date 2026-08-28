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
        + [x["what"] for x in out["shopping_list"]]
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


def test_over_budget_design_is_shown_with_its_price(serve_mod, verified_catalog,
                                                    tmp_path, monkeypatch):
    """A machine that costs more than the person hoped is still a real machine.

    The budget is a number they told us, not a law of physics. "Not quite
    buildable" was the wrong answer to "this costs $3,900" — it is buildable, and
    the price is the single most useful thing we can say.
    """
    monkeypatch.setattr(serve_mod, "CATALOG", verified_catalog)
    monkeypatch.setattr(serve_mod, "RUNS_DIR", tmp_path)
    g = GuidedIntake()
    for k, v in [("task", "pick up small parts and put them in a bin"),
                 ("object", "machined part"),
                 ("weight_refine", "lighter than a phone"), ("area", "a desk"),
                 ("budget", "under $3,000"), ("confirm", "yes, that's right")]:
        g.answer(k, v)
    out = serve_mod.result_payload(g)

    failed = {c["name"] for c in out["internal"]["checks"] if c["status"] == "fail"}
    assert failed == {"budget"}, f"expected only the budget check to fail, got {failed}"
    assert out["ok"] is True
    assert out["machine"]
    assert out["over_budget"] and "3,000" in out["over_budget"]
    assert out["price"], "we know the number here, so we say it"


def test_every_blocking_check_has_plain_language(serve_mod):
    """No blocking path may fall through to the generic 'we can't build this'.

    That fallback tells the person nothing they can act on, and it fired on a
    laundry-folding request whose only problem was that it cost $900 too much.
    """
    from rstream.dialogue import plain_failure

    generic = plain_failure("something with no mapping at all")
    samples = [
        "cost_target: parts cost 3,104 USD exceeds the 3,000 USD ceiling for a "
        "machine we build",
        "cost_target: top of the quoted range (12,000 USD) exceeds the 10,000 USD ceiling",
        "reach: model reaches 0.300 m from base, requirement 0.700 m",
        "torque_margin[shoulder]: 0.80x rated over 90.0 Nm required at shoulder",
        "panel_volume: components need 4000 cm^3 (keepout incl.), tier provides "
        "2228 cm^3 usable at 55% packing",
        "panel_largest_part: largest component envelope (300, 100, 90) mm does not "
        "fit the tier",
        "catalog_verified: unverified parts cannot be quoted: act.large",
    ]
    unmapped = [m for m in samples if plain_failure(m) == generic]
    assert not unmapped, f"these blocking failures have no plain-language message: {unmapped}"


def test_cost_is_explained_once_not_twice(serve_mod, intake, tmp_path, monkeypatch):
    """Both notes answer "what does it cost?". Stacked, the screen said "we can't
    price this" twice in a row."""
    monkeypatch.setattr(serve_mod, "DEMO_MODE", True)
    monkeypatch.setattr(serve_mod, "RUNS_DIR", tmp_path)
    for answers in (
        [("task", "fold laundry"), ("object", "t-shirt"),
         ("weight_refine", "lighter than a phone"), ("area", "a dining table"),
         ("budget", "under $3,000"), ("confirm", "yes, that's right")],
        [("task", "pick up small parts and put them in a bin"),
         ("object", "machined part"), ("weight_refine", "lighter than a phone"),
         ("area", "a laptop"), ("budget", "under $3,000"),
         ("confirm", "yes, that's right")],
    ):
        g = GuidedIntake()
        for k, v in answers:
            g.answer(k, v)
        out = serve_mod.result_payload(g)
        if not out.get("ok"):
            continue
        shown = [x for x in (out.get("price"), out.get("price_withheld"),
                             out.get("over_budget")) if x]
        assert len(shown) == 1, f"expected exactly one cost note, got {len(shown)}"


def test_the_result_says_what_to_order(serve_mod, intake, verified_catalog,
                                       tmp_path, monkeypatch):
    """A person cannot order "a rotating shoulder joint".

    The whole product is a parts list someone can actually buy from. Until now the
    result screen described the machine in prose and stopped, so the one thing it
    exists to deliver was the one thing it did not show.
    """
    monkeypatch.setattr(serve_mod, "CATALOG", verified_catalog)
    monkeypatch.setattr(serve_mod, "RUNS_DIR", tmp_path)
    out = serve_mod.result_payload(intake)

    bom = out["shopping_list"]
    assert bom, "the result must list what to order"
    for row in bom:
        assert row["qty"] >= 1
        assert row["manufacturer"] and row["part_number"], "you order by part number"
        assert row["order_as"].lower().count(row["manufacturer"].lower()) == 1, (
            f"manufacturer repeated in the order label: {row['order_as']!r}")
        assert row["url"], f"{row['part_number']} has no link to buy it from"
        assert row["line_usd"] == pytest.approx(row["unit_usd"] * row["qty"])
    assert out["parts_subtotal_usd"] == pytest.approx(
        sum(r["line_usd"] for r in bom))


def test_unverified_parts_are_listed_but_flagged(serve_mod, intake, tmp_path,
                                                 monkeypatch):
    """Part numbers and links are facts; unchecked prices are not.

    Showing the list is how someone finds out whether this is a $300 project or a
    $3,000 one. Showing a *total* as though it were a quote is what
    `catalog_verified` exists to prevent, so the subtotal is withheld instead.
    """
    monkeypatch.setattr(serve_mod, "DEMO_MODE", True)
    monkeypatch.setattr(serve_mod, "RUNS_DIR", tmp_path)
    out = serve_mod.result_payload(intake)

    assert out["shopping_list"], "the parts are real even when unchecked"
    assert all(r["confirmed"] is False for r in out["shopping_list"])
    assert all(r["url"] for r in out["shopping_list"])
    assert out["parts_subtotal_usd"] is None, "no total from unverified parts"
    assert out["price"] is None


def test_every_catalog_part_can_be_ordered(seed_catalog):
    """A part with no link is a part nobody can buy. It has no business being in
    a catalog whose entire purpose is that the output is orderable."""
    missing = [p.id for p in seed_catalog.query(allow_unverified=True)
               if not p.source_url]
    assert not missing, f"no vendor link on: {missing}"
