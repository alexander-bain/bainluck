"""#11948: the served collection carries the complete field at venue prices."""

import pytest

from tests import test_midterms_kalshi_grade_reaches_served_card as proof
from tests.test_midterms_kalshi_grade_reaches_served_card import served  # noqa: F401

PRICES = [
    ("Nebraska", 0.91),
    ("Kansas", 0.1205),
    ("Texas", 0.115),
    ("Florida", 0.095),
    ("Nevada", 0.0905),
    ("Pennsylvania", 0.07),
]
PRICES += [(f"State {index}", 0.01) for index in range(17)] + [
    ("Zero-priced state", 0.0)
]


@pytest.fixture
def full_field(monkeypatch):
    monkeypatch.setitem(proof.KALSHI_OUTCOMES, 108629, PRICES)
    original = proof._market

    def market(*args, **kwargs):
        row = original(*args, **kwargs)
        if row.id == 108629:
            row.mutually_exclusive = True
        return row

    monkeypatch.setattr(proof, "_market", market)


def test_full_http_read_carries_all_24_prices_without_scaling_the_top_five(
    served, full_field
):
    _, read = served
    _, cards = read()
    outcomes = cards[108629]["top_outcomes"]
    assert len(outcomes) == 24
    assert {o["name"]: o["probability"] for o in outcomes} == dict(PRICES)
    assert outcomes[0]["name"] == "Nebraska"
    assert outcomes[0]["probability"] == 0.91
    assert sum(o["probability"] for o in outcomes) > 1
    assert len({o["id"] for o in outcomes}) == 24


def test_the_detail_pages_withheld_price_stays_withheld_without_scaling_other_legs(
    served, full_field, monkeypatch
):
    original = proof._database

    def database(*args, **kwargs):
        db, refused = original(*args, **kwargs)
        refused[108629] = {10862900}
        return db, refused

    monkeypatch.setattr(proof, "_database", database)
    _, read = served
    _, cards = read()
    outcomes = {o["name"]: o["probability"] for o in cards[108629]["top_outcomes"]}
    assert len(outcomes) == 24
    assert outcomes["Nebraska"] is None
    assert outcomes["Kansas"] == 0.1205
    assert outcomes["Zero-priced state"] == 0
