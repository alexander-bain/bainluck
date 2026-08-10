"""#1625 — membership on a golf tournament page is proven, not inferred lexically.

Two layers are asserted here:

1. `app/utils/golf_membership` must agree with the Codex corpus
   `golf_event_membership_contract` case for case. The corpus is the oracle; if
   the implementation drifts from it, the product and the eval disagree about
   what belongs on a major page, and only one of them is user-visible.
2. `_assemble_completed_winner_field` must actually apply it — the two named
   production symptoms (The Masters crowning "PGA Tour", a chess player ranked
   #1) must be absent from the assembled field.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.utils.golf_membership import (
    evaluate_membership,
    is_foreign_domain,
    is_prop_outcome,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS = REPO_ROOT / "tests" / "evals" / "fixtures" / "golf_event_membership_contract.json"


def _corpus_cases():
    if not CORPUS.exists():  # corpus lands with the Codex commit; skip rather than fail red
        return []
    return json.loads(CORPUS.read_text())["cases"]


@pytest.mark.skipif(not CORPUS.exists(), reason="golf membership corpus not present on this base")
@pytest.mark.parametrize("case", _corpus_cases(), ids=lambda c: c["id"])
def test_implementation_agrees_with_the_corpus_oracle(case):
    """The shipped authority and the eval oracle must not be able to disagree."""
    assert evaluate_membership(case["input"]) == case["expected"], case["id"]


class TestForeignDomains:
    @pytest.mark.parametrize(
        "name",
        [
            "Norway Chess Masters Winner",
            "Rodeo Masters Champion",
            "PBA Basketball Masters Winner",
            "Masters of the Air Movie Award Winner",
        ],
    )
    def test_named_production_offenders_are_foreign(self, name):
        assert is_foreign_domain(name) is True

    @pytest.mark.parametrize(
        "name",
        [
            "The Masters Tournament Winner",
            "PGA Championship Winner",
            "KPMG Women's PGA Championship Winner",
            "PGA Tour Truist Championship Winner",
        ],
    )
    def test_real_golf_markets_are_not(self, name):
        """The other direction (gotcha #43): suppression must not eat the page."""
        assert is_foreign_domain(name) is False


class TestPropOutcomes:
    @pytest.mark.parametrize("name", ["PGA Tour", "pga tour", " United States ", "Yes", "Europe"])
    def test_a_tour_or_country_is_never_a_champion(self, name):
        assert is_prop_outcome(name) is True

    @pytest.mark.parametrize("name", ["Scottie Scheffler", "Rory McIlroy", "Nelly Korda"])
    def test_golfers_are_not_props(self, name):
        assert is_prop_outcome(name) is False


def _outcome(name, prob=0.05, winner=False):
    return SimpleNamespace(
        name=name,
        current_probability=prob,
        calibration_probability=None,
        opening_probability=prob,
        current_american_odds=None,
        is_winner=winner,
    )


def _market(mid, name, outcomes, source="sportsbook"):
    return SimpleNamespace(id=mid, name=name, source=source, outcomes=outcomes)


class TestAssembledSettledField:
    """The authority has to be APPLIED, not merely available."""

    def test_a_tour_is_never_crowned_champion(self):
        from app.routes.golf import _assemble_completed_winner_field

        markets = [
            _market(1, "The Masters Tournament Winner", [
                _outcome("Scottie Scheffler", 0.12, winner=True),
                _outcome("Rory McIlroy", 0.09),
                _outcome("PGA Tour", 0.99),
            ]),
        ]
        golfers, *_ = _assemble_completed_winner_field(markets)
        names = [g["name"] for g in golfers]

        assert "PGA Tour" not in names
        assert names[0] == "Scottie Scheffler"

    def test_a_chess_market_contributes_nobody(self):
        from app.routes.golf import _assemble_completed_winner_field

        markets = [
            _market(1, "The Masters Tournament Winner", [
                _outcome("Scottie Scheffler", 0.12, winner=True),
            ]),
            _market(2, "Norway Chess Masters Winner", [
                _outcome("Magnus Carlsen", 0.40, winner=True),
            ]),
        ]
        golfers, *_ = _assemble_completed_winner_field(markets)
        names = [g["name"] for g in golfers]

        assert "Magnus Carlsen" not in names
        assert names == ["Scottie Scheffler"]

    def test_the_real_field_survives(self):
        """Both directions: the page must still render its actual champions."""
        from app.routes.golf import _assemble_completed_winner_field

        markets = [
            _market(1, "The Masters Tournament Winner", [
                _outcome("Scottie Scheffler", 0.12, winner=True),
                _outcome("Rory McIlroy", 0.09),
                _outcome("Ludvig Aberg", 0.07),
            ]),
        ]
        golfers, *_ = _assemble_completed_winner_field(markets)

        assert [g["name"] for g in golfers] == ["Scottie Scheffler", "Rory McIlroy", "Ludvig Aberg"]
        assert golfers[0]["probability"] == 1.0
        assert golfers[1]["probability"] == 0.0

    def test_a_graded_winner_outside_the_authoritative_field_is_dropped(self):
        """#1625's inversion: `is_winner` must not buy membership.

        With a DataGolf field of 20+, a graded name that DataGolf never listed used
        to be kept by the `or v.get("won")` clause. A champion outside the field
        means the field or the linkage is wrong, and crowning them hides that.
        """
        from app.routes.golf import _assemble_completed_winner_field

        dg_outcomes = [_outcome(f"DG Golfer {i}", 0.01) for i in range(22)]
        markets = [
            _market(1, "The Masters Tournament Winner", dg_outcomes, source="datagolf"),
            _market(2, "The Masters Tournament Winner", [
                _outcome("Magnus Carlsen", 0.40, winner=True),
            ], source="kalshi"),
        ]
        golfers, *_ = _assemble_completed_winner_field(markets)
        names = [g["name"] for g in golfers]

        assert "Magnus Carlsen" not in names
        assert len(names) == 22
