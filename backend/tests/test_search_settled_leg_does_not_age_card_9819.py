"""A ROW THE CARD PRINTS AS A RESULT NO LONGER SETS THE AGE OF A SEARCH CARD. #9819.

═══ WHAT WAS SEEN ═══

`/search?q=cubs`, 09-30: the open NLDS board (60087232) read **"18h ago"** over
Padres / Braves / Cubs prices written 1-5 minutes earlier. Its two authoritative
winners (Dodgers, Brewers: `is_winner=true, api_settlement`) print as `Won`, not as
prices, and their grade stamps from the day before won `_served_prices_as_of`'s
`min`.

═══ THE RULE, AND THE SPECIMEN IT DELIBERATELY LEAVES ALONE ═══

A served, unwithheld row is left out of the age exactly when FuturesCard draws it
as `Won`/`Lost`: `_search_row_prints_a_verdict`, a mirror of `outcomeRowVerdict`
(`frontend/components/futures/OutcomeRow.tsx`). Every row the card draws as a
number keeps its vote.

So the open ALCS board (60087229, `?q=yankees`, 10-02) KEEPS its "Sep 23": Toronto
is `is_winner=false, api_settlement` at 0%, and an open market prints only
authoritative WINNERS (#6082), so the card shows Toronto as a numeric 0%. That 0%
is on screen, and so is its age. Freshening the footer while the old number stays
visible would be the flattering half of #6018. (Sol's mounted-contract receipt,
`artifacts/9819-mounted-contributor-contract-20261002/HANDBACK.md`.)

═══ THE PAIR ═══

`wire_specimens()` serializes three boards through the real search formatter.
`frontend/__tests__/fixtures/searchAge9819.json` is that output, checked in, and
`frontend/__tests__/components/futuresCardSearchAgeVerdict9819.test.tsx` mounts the
real FuturesCard on it and reads the row text and the footer together. The test
here fails if the formatter and the fixture drift apart, so the jest test can only
ever be reading what this backend serves.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from app.routes.events import (
    _format_futures_for_search,
    _search_row_prints_a_verdict,
    _served_prices_as_of,
)


UTC = timezone.utc

FRESH = datetime(2026, 10, 2, 11, 47, 6, tzinfo=UTC)
LIVE_MIN = datetime(2026, 10, 2, 11, 15, 0, tzinfo=UTC)
TORONTO_AT = datetime(2026, 9, 23, 10, 31, 12, tzinfo=UTC)
NLDS_WRITTEN = datetime(2026, 9, 30, 11, 48, 14, tzinfo=UTC)
NLDS_WON_AT = datetime(2026, 9, 29, 17, 36, 22, tzinfo=UTC)
GRADED_AT = datetime(2026, 9, 28, 3, 2, 0, tzinfo=UTC)

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "frontend/__tests__/fixtures/searchAge9819.json"
)

#: The wire keys FuturesCard reads for the rows and the footer.
CARD_ROW_KEYS = ("id", "name", "probability", "is_winner", "resolution_source")


class _Outcome:
    def __init__(
        self,
        oid,
        last_updated,
        prob,
        *,
        name="Leg",
        is_winner=False,
        resolution_source=None,
    ):
        self.id = oid
        self.last_updated = last_updated
        self.name = name
        self.current_probability = prob
        self.current_yes_bid = None
        self.current_yes_ask = None
        self.current_american_odds = None
        self.rank = None
        self.probability_change_24h = None
        self.external_id = f"ext-{oid}"
        self.is_winner = is_winner
        self.resolution_source = resolution_source


class _Market:
    def __init__(self, outcomes, **kw):
        self.outcomes = outcomes
        self.updated_at = kw.get("updated_at", FRESH)
        self.id = kw.get("id", 60087229)
        self.name = kw.get("name", "MLB Playoffs: Team to advance to ALCS")
        self.sport = None
        self.category = "championship"
        self.llm_sport_category = "baseball"
        self.market_tier = 5
        self.market_type = "field"
        self.status = kw.get("status", "open")
        self.source = "polymarket"
        self.resolution_date = None
        self.mutually_exclusive = False


def _alcs(toronto_source="api_settlement", toronto_won=False, toronto_prob=0.0):
    """60087229 as served on 10-02: four live legs and Toronto, graded 0%."""
    return _Market(
        [
            _Outcome(224051327, FRESH, 0.58, name="Cleveland Guardians"),
            _Outcome(231082156, FRESH, 0.52, name="New York Yankees"),
            _Outcome(231082155, LIVE_MIN, 0.465, name="Tampa Bay Rays"),
            _Outcome(232072952, FRESH, 0.42, name="Chicago White Sox"),
            _Outcome(
                232072954,
                TORONTO_AT,
                toronto_prob,
                name="Toronto Blue Jays",
                is_winner=toronto_won,
                resolution_source=toronto_source,
            ),
        ]
    )


def _nlds():
    """60087232 on 09-30: two authoritative `Won` legs graded the day before."""
    return _Market(
        [
            _Outcome(1, NLDS_WON_AT, 1.0, name="Los Angeles Dodgers",
                     is_winner=True, resolution_source="api_settlement"),
            _Outcome(2, NLDS_WON_AT, 1.0, name="Milwaukee Brewers",
                     is_winner=True, resolution_source="api_settlement"),
            _Outcome(3, NLDS_WRITTEN, 0.79, name="San Diego Padres"),
            _Outcome(4, NLDS_WRITTEN, 0.75, name="Atlanta Braves"),
            _Outcome(5, NLDS_WRITTEN, 0.21, name="Chicago Cubs"),
        ],
        id=60087232,
        name="MLB Playoffs: Team to advance to NLCS",
    )


def _resolved():
    """A settled board: every printed row is a graded `Won`/`Lost`."""
    return _Market(
        [
            _Outcome(11, GRADED_AT, 1.0, name="Seattle Mariners",
                     is_winner=True, resolution_source="api_settlement"),
            _Outcome(12, GRADED_AT, 0.0, name="Houston Astros",
                     is_winner=False, resolution_source="api_settlement"),
        ],
        id=60087111,
        name="MLB Playoffs: AL West winner",
        status="resolved",
    )


def _served(market):
    return [{"id": o.id} for o in market.outcomes]


def _card_wire(payload: dict) -> dict:
    return {
        "id": payload["id"],
        "name": payload["name"],
        "status": payload["status"],
        "prices_updated_at": payload["prices_updated_at"],
        "top_outcomes": [
            {k: o.get(k) for k in CARD_ROW_KEYS} for o in payload["top_outcomes"]
        ],
    }


def wire_specimens() -> dict:
    """The three boards exactly as the search formatter serves them to the card."""
    return {
        "nlds": _card_wire(_format_futures_for_search(_nlds())),
        "alcs": _card_wire(_format_futures_for_search(_alcs())),
        "resolved": _card_wire(_format_futures_for_search(_resolved())),
    }


class TestTheProductionSpecimens:
    def test_the_nlds_card_is_not_aged_by_the_rows_it_prints_as_won(self):
        market = _nlds()
        assert _served_prices_as_of(market, _served(market)) == NLDS_WRITTEN.isoformat()

    def test_the_alcs_card_keeps_torontos_age_because_it_prints_0_percent(self):
        """Open board, graded loser: the card draws a number, so it dates the card."""
        market = _alcs()
        assert _served_prices_as_of(market, _served(market)) == TORONTO_AT.isoformat()

    def test_a_resolved_card_of_only_results_has_no_mark(self):
        market = _resolved()
        assert _served_prices_as_of(market, _served(market)) is None


class TestTheMirrorOfOutcomeRowVerdict:
    """Each arm of `outcomeRowVerdict`, through the age it decides."""

    def test_an_open_authoritative_winner_prints_won_at_any_price(self):
        # The card's rule reads the grade, never the price: a tier-3 `true`
        # at 0.40 still prints `Won`, so its stamp leaves the age.
        market = _alcs(toronto_won=True, toronto_prob=0.40)
        assert _served_prices_as_of(market, _served(market)) == LIVE_MIN.isoformat()

    def test_an_open_winner_on_a_non_authoritative_source_keeps_its_price(self):
        market = _alcs(toronto_source="clean_resolution", toronto_won=True)
        assert _served_prices_as_of(market, _served(market)) == TORONTO_AT.isoformat()

    def test_an_open_winner_on_an_unknown_source_keeps_its_price(self):
        market = _alcs(toronto_source="someone_new", toronto_won=True)
        assert _served_prices_as_of(market, _served(market)) == TORONTO_AT.isoformat()

    def test_a_retraction_never_prints_a_verdict(self):
        market = _alcs(toronto_source="ungradeable_result", toronto_won=True)
        assert _served_prices_as_of(market, _served(market)) == TORONTO_AT.isoformat()

    def test_a_served_null_source_prints_the_price(self):
        """Column-default `False` with no source: #6195's printed 0%."""
        market = _alcs(toronto_source=None)
        assert _served_prices_as_of(market, _served(market)) == TORONTO_AT.isoformat()

    def test_a_null_is_winner_prints_the_price(self):
        market = _alcs(toronto_won=None)
        assert _served_prices_as_of(market, _served(market)) == TORONTO_AT.isoformat()

    def test_on_a_resolved_board_a_graded_loser_prints_lost(self):
        assert _search_row_prints_a_verdict(
            _Outcome(1, GRADED_AT, 0.0, is_winner=False,
                     resolution_source="api_settlement"),
            True,
        )

    def test_on_a_resolved_board_a_tier_1_grade_still_prints_a_verdict(self):
        # Resolved markets take any graded row (the card's last line); only the
        # retraction and a missing grade refuse.
        assert _search_row_prints_a_verdict(
            _Outcome(1, GRADED_AT, 1.0, is_winner=True,
                     resolution_source="clean_resolution"),
            True,
        )
        assert not _search_row_prints_a_verdict(
            _Outcome(1, GRADED_AT, 1.0, is_winner=True,
                     resolution_source="ungradeable_result"),
            True,
        )


class TestThePairedWire:
    def test_the_served_payload_carries_the_age_and_still_prints_toronto(self):
        payload = _format_futures_for_search(_alcs())
        assert payload["prices_updated_at"] == TORONTO_AT.isoformat()
        names = [o["name"] for o in payload["top_outcomes"]]
        assert "Toronto Blue Jays" in names

    def test_the_frontend_fixture_is_exactly_what_this_formatter_serves(self):
        """The jest half mounts FuturesCard on this file; it must be our wire."""
        assert FIXTURE.exists(), (
            f"{FIXTURE} missing: write json.dumps(wire_specimens(), indent=2, "
            "sort_keys=True) to it"
        )
        assert json.loads(FIXTURE.read_text()) == wire_specimens()
