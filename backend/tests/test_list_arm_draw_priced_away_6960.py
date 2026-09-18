"""#6960 — the LIST formatter stops serving an away probability it cannot source.

## The defect, measured on production 2026-09-18 13:5xZ

`1 − P(home)` is *"the home team does not win"*, which on a draw-priced sport is
**away win OR draw**. #5271 withheld that fabrication in native and #6238
withheld it in `get_event`, the detail route. `_format_event_with_aggregated_odds`
— which serves `GET /api/events` and `GET /api/events/search` — was in neither
scope and went on serving it.

Two endpoints, one column, the same rows, stable across repeat calls:

    15305234  Brighton v Arsenal          list 0.8033   detail None
    15305206  Brentford v Chelsea         list 0.6321   detail None
    15313996  Lamontville v Kaizer Chiefs list 0.7750   detail None

Every one is exactly `1 − hero_probability`. On 15313996 the fixture's own
Polymarket three-way, rendered in "Other Markets" on that event's page, prices
**Kaizer Chiefs 47% · Draw 32% · Lamontville 23%** — the draw's 32 points had
been handed in full to the away team, and the page therefore contradicted
itself in one screenshot.

Priced rows whose served pair summed to exactly 1.0000, one list call each:
`soccer_epl` 10/10 · `soccer_spain_la_liga` 12/12 · `soccer_italy_serie_a`
10/10. `americanfootball_nfl` 17/17 — correct, a two-way sport, and untouched.

The comment block immediately above the unguarded hero line had already named
this failure in writing:

    Q441/#1495 — SECOND ARM. This formatter serves the list/debug surfaces
    while `get_event` serves the detail page; they are two independent copies
    of the same six lines, and fixing one is how a lane ships half a fix.

## What is asserted, and why in both directions

The withhold is opt-in per sport AND per pair, so the REFUSAL direction is
asserted as hard as the withhold (gotcha #43, and `away_is_the_complement`'s own
argument). Deleting a real away price is the mirror-image defect of printing a
fabricated one:

* a **two-way sport** keeps its away number and its 100-summing pair;
* a **sourced soccer pair** that is not a complement keeps its away number;
* a **settled** hero keeps both sides, including a draw's 0.5/0.5 — those sum to
  1.0 and a purely numeric test would delete the losing side of a finished
  match. "Settled means settled" outranks this issue: a result is not a price.

`TestTheTwoArmsAgree` is the durable one. The per-site tests above it would all
pass again if a future edit reintroduced the derive at one site only; that class
is exactly what shipped this defect twice, so the last test asserts the two
formatters against each other on one row rather than each against a constant.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.models import Event, Sport
from app.routes import events as events_route
from app.utils.draw_priced_winner import printable_away, sport_prices_a_draw

EVENT_ID = 15313996
HOME = "Lamontville Golden Arrows"
AWAY = "Kaizer Chiefs"

# The production reading this file was written from.
SOCCER_HOME_PROB = 0.225
FABRICATED_AWAY = 0.775
MARKET_AWAY = 0.465  # what the fixture's own three-way actually prices


def _offset(hours: float) -> datetime:
    """Anchor OFFSET FIRST, never truncated after (gotcha #44)."""
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def _event(
    sport_key: str,
    home_prob: float,
    *,
    status: str = "scheduled",
    hours: float = 8,
    opening: tuple | None = None,
    scores: tuple | None = None,
) -> Event:
    event = Event(
        id=EVENT_ID,
        sport_id=1,
        home_team_name=HOME,
        away_team_name=AWAY,
        commence_time=_offset(hours),
        status=status,
        win_probability_sources={"polymarket": {"value": home_prob, "type": "market"}},
    )
    if opening is not None:
        event.opening_home_probability, event.opening_away_probability = opening
    if scores is not None:
        event.home_score, event.away_score = scores
        event.completed_at = _offset(hours)
    event.sport = Sport(id=1, key=sport_key, name=sport_key)
    return event


def _odds_data(home_prob: float) -> dict:
    """The shape `_format_event_with_aggregated_odds` reads for `current_odds`."""
    return {
        "aggregated": {
            "home_probability": home_prob,
            "away_probability": round(1.0 - home_prob, 6),
            "home_spread": -0.5,
            "over_under": 2.5,
            "projected_home_score": 1.0,
            "projected_away_score": 1.0,
            "bookmaker_count": 6,
        },
        "captured_at": _offset(-1),
        "snapshots": [],
    }


# ── THE PREMISE ──────────────────────────────────────────────────────────────


def test_the_sports_under_test_are_the_ones_the_rule_is_about():
    """Without this the soccer tests below could pass on a two-way sport."""
    assert sport_prices_a_draw("soccer_other") is True
    assert sport_prices_a_draw("soccer_epl") is True
    assert sport_prices_a_draw("americanfootball_nfl") is False


# ── THE WITHHOLD ─────────────────────────────────────────────────────────────


class TestTheListFormatterWithholds:
    def test_current_odds_does_not_serve_the_complement(self):
        """🔴 Kaizer Chiefs served at 0.775 over a board pricing them 0.465."""
        response = events_route._format_event_with_aggregated_odds(
            _event("soccer_other", SOCCER_HOME_PROB), _odds_data(SOCCER_HOME_PROB)
        )
        current = response["current_odds"]

        assert current["home_probability"] == pytest.approx(
            SOCCER_HOME_PROB
        ), "the home leg is not the defect and must survive untouched"
        assert current["away_probability"] is None, (
            "the list formatter served `1 - home` as the away team's price; "
            f"the fixture's own three-way prices them {MARKET_AWAY}"
        )

    def test_the_top_level_hero_does_not_serve_the_complement(self):
        """🔴 `hero_probability_away` — the field native and My Stuff bind to."""
        response = events_route._format_event_with_aggregated_odds(
            _event("soccer_other", SOCCER_HOME_PROB), None
        )

        assert response["hero_probability"] == pytest.approx(SOCCER_HOME_PROB)
        assert (
            response["hero_probability_away"] is None
        ), f"served {FABRICATED_AWAY} for {AWAY} on production 2026-09-18"

    def test_a_complement_opening_pair_is_withheld_too(self):
        """The stored pair can itself be a complement; the detail arm withholds it."""
        event = _event(
            "soccer_epl",
            SOCCER_HOME_PROB,
            status="in_progress",
            hours=-2,
            opening=(0.30, 0.70),
        )
        opening = events_route._format_event_with_aggregated_odds(event, None)[
            "opening_odds"
        ]

        assert opening["home_probability"] == pytest.approx(0.30)
        assert opening["away_probability"] is None


# ── THE REFUSAL, WHICH IS THE OTHER HALF OF THE RULE ─────────────────────────


class TestTheListFormatterRefusesToWithhold:
    def test_a_two_way_sport_keeps_its_pair(self):
        """NFL 17/17 complement pairs on production are CORRECT and must stay."""
        response = events_route._format_event_with_aggregated_odds(
            _event("americanfootball_nfl", 0.28), _odds_data(0.28)
        )

        assert response["current_odds"]["away_probability"] == pytest.approx(0.72)
        assert response["hero_probability_away"] == pytest.approx(0.72)
        assert (
            response["current_odds"]["home_probability"]
            + response["current_odds"]["away_probability"]
        ) == pytest.approx(1.0)

    def test_a_sourced_soccer_opening_pair_keeps_its_away_number(self):
        """Deleting a real away price is the mirror-image defect (#1011 de-vig)."""
        event = _event(
            "soccer_epl",
            SOCCER_HOME_PROB,
            status="in_progress",
            hours=-2,
            opening=(0.3107, 0.4216),  # sums 0.7323 — a real three-way board
        )
        opening = events_route._format_event_with_aggregated_odds(event, None)[
            "opening_odds"
        ]

        assert opening["away_probability"] == pytest.approx(
            0.4216
        ), "a de-vigged away price is sourced, not fabricated"

    def test_a_settled_draw_keeps_both_sides(self):
        """0.5/0.5 sums to 1.0 and a numeric test would delete half a result."""
        event = _event(
            "soccer_epl",
            SOCCER_HOME_PROB,
            status="completed",
            hours=-3,
            scores=(1, 1),
        )
        response = events_route._format_event_with_aggregated_odds(event, None)

        assert response["hero_probability_source"] == "settled", (
            "the fixture is not exercising the settled arm — the exemption "
            "below would then be asserting nothing"
        )
        assert response["hero_probability_away"] is not None, (
            "settled means settled: a result is not a price and was never "
            "derived from the home number"
        )
        assert response["hero_probability"] == pytest.approx(0.5)
        assert response["hero_probability_away"] == pytest.approx(0.5)


# ── THE DURABLE ONE ──────────────────────────────────────────────────────────


class TestTheTwoArmsAgree:
    """One row, both formatters, same answer — the assertion the defect failed.

    #5271 fixed native, #6238 fixed the detail route, and each time the guard
    was written against a constant rather than against the other arm, so the
    remaining arm stayed invisible. This binds them together instead.
    """

    @pytest.mark.parametrize(
        "sport_key,home_prob",
        [
            ("soccer_other", SOCCER_HOME_PROB),
            ("soccer_epl", 0.1967),  # Brighton v Arsenal, list served 0.8033
            ("americanfootball_nfl", 0.28),
            ("baseball_mlb", 0.47),
        ],
    )
    def test_the_list_away_is_what_the_detail_rule_would_serve(
        self, sport_key, home_prob
    ):
        served = events_route._format_event_with_aggregated_odds(
            _event(sport_key, home_prob), None
        )["hero_probability_away"]

        expected = printable_away(round(1.0 - home_prob, 6), home_prob, sport_key)

        assert served == (pytest.approx(expected) if expected is not None else None), (
            f"{sport_key}: the list arm and the detail rule disagree on one "
            "row — which is the whole defect, not a detail of it"
        )
