"""#6239 — a totals rung built from an UNDER leg is graded on the OVER axis.

## The ship

On `/events/14637256` (Cowboys 20 @ Giants 28, Final, 48 points) the settled
game-total ladder's 52.5 rung was served, verbatim from production at
22:10:41Z:

    { "outcome_name": "Under", "threshold": 52.5, "over_probability": 0.0,
      "is_winner": true, "resolution_source": "poly_total_score",
      "market_name": "Cowboys vs. Giants: O/U 52.5", "_market_id": 58293398 }

A rung that says, in one row, that the over did not happen (`0.0`) and that it
won (`is_winner: true`), about a line a 48-point game never came near. After
this change that row reads `is_winner: false` beside its `0.0`.

## 🔴 The row was HALF inverted, which is why it refutes itself

`_build_game_markets` normalises every totals leg onto the over axis —
`over_prob = 1 - p` for an Under, and #6169's `_settled_over_probability`
inverts the verdict that replaces it once a rung is settled. The GRADE beside
it was spread raw (`**_grade`), straight off the leg's own database row. So the
number spoke about the Over and the verdict spoke about the Under, in the same
row, keyed by the same threshold.

Read back from production, market 58293398:

| source | outcome | is_winner | current_probability |
|---|---|---|---|
| polymarket | `Over` | false | 0.005 |
| polymarket | `Under` | **true** | 0.999 |

The Under leg is the one that reaches the ladder (its sibling loses the
threshold dedup), so the served ladder carried the Under's verdict under an
Over-keyed rung.

## What a reader sees today — stated honestly

The false verdict is **not printed**: web `MarketMapSection` and iOS
`TotalPointsSpectrumView` both grade these rungs off the final score, not off
the served row, so the card says "Over 52.5 — not cleared", which is true of
the game. This is a payload lie with no rendered symptom *yet*, and it becomes
one the moment any consumer reads the served verdict — the direction #6196,
#6205 and #2089 are all pushing this ladder.

## 🔴 The unprovable branch WITHHOLDS, it does not invert

`_verdict_is_provable` exists because on a voided market the venue grades every
leg a loser and none a winner (measured 2026-09-14: 389 markets across 163
events, trailing 14 days). Flipping a losing Under there would publish
`is_winner: true` — a fabricated certainty nobody earned, the exact class
#6169's repair was built to refuse. So an unprovable inverted row serves
`is_winner: None` and KEEPS its `resolution_source`: the grade is real, it
simply does not decide the over. The client rule (`outcomeRowVerdict`, #4788)
refuses on `is_winner == null` before it reads the source, so nothing prints —
and the source is what the #1588 window filter reads to tell a settled row from
a stale quote, so dropping it would take voided period rungs off the ladder
entirely. `TestTheWithheldRowStaysOnTheLadder` pins that, because it is the one
side effect of this change a reader could actually see.

Every class below therefore has its negative twin — a non-inverted row is
untouched, a voided Under keeps its price and states no verdict, a tier-1
retraction is not inverted, and the winning-sibling direction is asserted so
the repair cannot be satisfied by nulling every grade.

## Why the real endpoint

Same rig as `test_a_settled_ladder_rung_serves_its_verdict_6169.py`: these
drive the real `_build_game_markets` against a doubled session, so the subject
is the served payload after classification, dedup, the sport-range guard and
the monotonicity pass, in the order production runs them.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes import events as events_route
from app.routes.events import _game_markets_cache

NOW = datetime(2026, 9, 14, 3, 40, tzinfo=timezone.utc)
KICKOFF = datetime(2026, 9, 14, 0, 20, tzinfo=timezone.utc)
FINAL_AT = datetime(2026, 9, 14, 3, 28, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _clear_cache():
    _game_markets_cache.clear()
    yield
    _game_markets_cache.clear()


def _result(scalar=None, rows=None, all_rows=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = rows or []
    result.all.return_value = all_rows if all_rows is not None else []
    return result


def _poly_total(*, id=58293398, threshold=52.5, status="resolved"):
    """The specimen market: Polymarket puts the line in the MARKET name and
    leaves the outcomes a bare "Over"/"Under" (#1976 §5)."""
    market = MagicMock()
    market.id = id
    market.name = f"Cowboys vs. Giants: O/U {threshold}"
    market.external_id = "0x9f2c1e5ab7d3"
    market.event_id, market.category, market.status = 42, "game_prop", status
    market.source, market.sport_id = "polymarket", 1
    market.llm_sport_category = "americanfootball"
    market.commence_time = KICKOFF
    market.group_id = market.group_type = None
    market.market_metadata = None
    market.market_tier = 5
    return market


def _kalshi_total(*, id=58728463, status="resolved"):
    market = MagicMock()
    market.id = id
    market.name = "Dallas vs New York: Total Points"
    market.external_id = "KXNFLTOTAL-26SEP13DALNYG"
    market.event_id, market.category, market.status = 42, "game_prop", status
    market.source, market.sport_id = "kalshi", 1
    market.llm_sport_category = "americanfootball"
    market.commence_time = KICKOFF
    market.group_id = market.group_type = None
    market.market_metadata = None
    market.market_tier = 5
    return market


def _outcome(*, id, market_id, name, prob, is_winner=None, resolution_source=None):
    outcome = MagicMock()
    outcome.id, outcome.market_id, outcome.name = id, market_id, name
    outcome.current_probability = prob
    outcome.opening_probability = 0.5
    outcome.is_winner = is_winner
    outcome.resolution_source = resolution_source
    outcome.last_updated = NOW
    return outcome


def _event(*, status="completed"):
    event = MagicMock()
    event.id, event.status, event.sport_id = 42, status, 1
    event.sport = MagicMock()
    event.sport.key = "americanfootball_nfl"
    event.home_team_name, event.away_team_name = "Dallas Cowboys", "New York Giants"
    event.home_score, event.away_score = 20, 28
    event.commence_time = KICKOFF
    event.completed_at = FINAL_AT if status == "completed" else None
    event.box_score_data = None
    event.period, event.game_clock = (
        ("Final", None) if status == "completed" else ("3rd Quarter", "6:32")
    )
    return event


def _db(markets, outcomes):
    rows = [
        SimpleNamespace(
            id=o.id,
            observed_at=NOW - timedelta(minutes=30),
            price_changed_at=None,
            resolution_source=None,
            current_probability=None,
        )
        for o in outcomes
    ]
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _result(scalar=_db.event),
            _result(rows=[]),          # #2693 folded_event_ids
            _result(rows=markets),
            _result(all_rows=[]),      # polymarket parent groups
            _result(rows=[]),          # unlinked fallback
            _result(rows=outcomes),
            _result(all_rows=rows),    # #4970 the observation load
        ]
    )
    return db


def _payload(markets, outcomes, *, event=None):
    _db.event = event if event is not None else _event()
    response, _status, _ids = asyncio.run(
        events_route._build_game_markets(42, _db(markets, outcomes))
    )
    return response


def _game_total_rungs(payload):
    """`{threshold: row}` for the served full-game total ladder."""
    return {t["threshold"]: t for t in payload.get("totals", [])}


def _half_market(*, id=60075100, status="resolved"):
    """A WINDOW-BOUNDED ladder — the population the #1588 filter owns."""
    market = _kalshi_total(id=id, status=status)
    market.name = "DAL Cowboys vs NY Giants: 2nd Half Total"
    market.external_id = "KXNFL2HTOTAL-26SEP13DALNYG"
    return market


def _half_total_rungs(payload):
    """`{threshold: row}` for the served 2H total ladder."""
    return {
        pm["threshold"]: pm
        for pm in payload.get("period_markets", [])
        if pm.get("market_type") == "half_total"
    }


def _specimen(*, under_won=True, source="poly_total_score", sibling_source="poly_total_score"):
    """Market 58293398 as production holds it: two bare legs, one threshold."""
    market = _poly_total()
    return [market], [
        _outcome(id=901, market_id=market.id, name="Under", prob=0.999,
                 is_winner=under_won, resolution_source=source),
        _outcome(id=902, market_id=market.id, name="Over", prob=0.005,
                 is_winner=not under_won, resolution_source=sibling_source),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# THE SHIP
# ─────────────────────────────────────────────────────────────────────────────


class TestTheVerdictTakesTheAxisOfTheNumberBesideIt:
    def test_the_winning_under_rung_is_served_as_an_over_that_lost(self):
        """🔴 The specimen, verbatim: `over_probability 0.0` + `is_winner true`.

        Asserted as a PAIR and not as a lone flag, because the defect was never
        one wrong field — it was two fields describing opposite sides of the
        same line.
        """
        markets, outcomes = _specimen()
        rungs = _game_total_rungs(_payload(markets, outcomes))

        assert 52.5 in rungs, "the settled 52.5 rung was dropped"
        row = rungs[52.5]
        # The threshold dedup keeps one leg and it is the Under — the same leg
        # production served at 22:10:41Z. Asserted, never assumed: if the
        # sibling ever won the dedup this test would grade an Over row and pass
        # on a payload that still carried the defect.
        assert row["outcome_name"] == "Under", (
            f"this test grades the UNDER leg; it served {row['outcome_name']}"
        )
        assert row["over_probability"] == 0.0
        assert row["is_winner"] is False, (
            "a 0% over was served as a WINNER — the Under leg's own verdict "
            f"under an Over-keyed rung: {row['is_winner']}"
        )
        assert row["resolution_source"] == "poly_total_score", (
            "a provable inversion keeps its source; withholding it here would "
            "hide a real grade from #4788's client rule"
        )

    def test_a_losing_under_becomes_the_over_that_won(self):
        """The other direction on the same market, so the repair cannot be
        satisfied by refusing to serve a `true`."""
        markets, outcomes = _specimen(under_won=False)
        row = _game_total_rungs(_payload(markets, outcomes))[52.5]

        assert row["outcome_name"] == "Under", (
            f"this test grades the UNDER leg; it served {row['outcome_name']}"
        )
        assert row["over_probability"] == 1.0
        assert row["is_winner"] is True
        assert row["resolution_source"] == "poly_total_score"

    def test_no_served_rung_contradicts_its_own_number(self):
        """The invariant the specimen broke, over a ladder mixing both axes.

        A provable rung states one thing: either the over happened or it did
        not. `is_winner: true` beside `0.0` — or `false` beside `1.0` — is a row
        arguing with itself whichever way a client reads it.
        """
        poly = _poly_total()
        kalshi = _kalshi_total()
        outcomes = [
            _outcome(id=901, market_id=poly.id, name="Under", prob=0.999,
                     is_winner=True, resolution_source="poly_total_score"),
            _outcome(id=902, market_id=poly.id, name="Over", prob=0.005,
                     is_winner=False, resolution_source="poly_total_score"),
            _outcome(id=910, market_id=kalshi.id, name="Over 27.5 points scored",
                     prob=1.0, is_winner=True, resolution_source="api_settlement"),
            _outcome(id=911, market_id=kalshi.id, name="Over 47.5 points scored",
                     prob=1.0, is_winner=True, resolution_source="api_settlement"),
            _outcome(id=912, market_id=kalshi.id, name="Over 48.5 points scored",
                     prob=0.0, is_winner=False, resolution_source="api_settlement"),
            _outcome(id=913, market_id=kalshi.id, name="Over 69.5 points scored",
                     prob=0.0, is_winner=False, resolution_source="api_settlement"),
        ]
        rungs = _game_total_rungs(_payload([poly, kalshi], outcomes))

        assert len(rungs) >= 4, f"the ladder collapsed: {sorted(rungs)}"
        for threshold, row in sorted(rungs.items()):
            if row["is_winner"] is True:
                assert row["over_probability"] != 0.0, (
                    f"rung {threshold} won at 0%: {row}"
                )
            if row["is_winner"] is False and row["resolution_source"] is not None:
                assert row["over_probability"] != 1.0, (
                    f"rung {threshold} lost at 100%: {row}"
                )
        # …and the ladder still reads as the game did: 48 points scored.
        assert rungs[47.5]["is_winner"] is True
        assert rungs[48.5]["is_winner"] is False
        assert rungs[52.5]["is_winner"] is False


class TestAnOverLegIsUntouched:
    """The negative population. An un-inverted row's leg and its axis are the
    same statement, so the repair must be invisible to every Kalshi ladder —
    otherwise "grade the axis" has quietly become "drop the grade"."""

    def test_a_winning_over_keeps_its_verdict_and_its_source(self):
        kalshi = _kalshi_total()
        outcomes = [
            _outcome(id=910, market_id=kalshi.id, name="Over 27.5 points scored",
                     prob=1.0, is_winner=True, resolution_source="api_settlement"),
            _outcome(id=912, market_id=kalshi.id, name="Over 48.5 points scored",
                     prob=0.0, is_winner=False, resolution_source="api_settlement"),
        ]
        rungs = _game_total_rungs(_payload([kalshi], outcomes))

        assert rungs[27.5]["is_winner"] is True
        assert rungs[27.5]["resolution_source"] == "api_settlement"
        assert rungs[48.5]["is_winner"] is False
        assert rungs[48.5]["resolution_source"] == "api_settlement"

    def test_an_ungraded_ladder_still_carries_the_no_verdict_shape(self):
        """A live market: both keys `None`, both axes, unchanged by this
        change — `_settled_grade_fields`' contract is upstream of it."""
        kalshi = _kalshi_total(status="open")
        poly = _poly_total(status="open")
        outcomes = [
            _outcome(id=910, market_id=kalshi.id, name="Over 27.5 points scored",
                     prob=0.80),
            _outcome(id=901, market_id=poly.id, name="Under", prob=0.35),
        ]
        rungs = _game_total_rungs(
            _payload([kalshi, poly], outcomes, event=_event(status="live"))
        )

        assert rungs[27.5]["is_winner"] is None
        assert rungs[27.5]["resolution_source"] is None
        assert rungs[52.5]["is_winner"] is None
        assert rungs[52.5]["resolution_source"] is None
        assert rungs[52.5]["over_probability"] == 0.65, "a live Under still inverts"


class TestAVoidedUnderStatesNothing:
    """🔴 The branch that must WITHHOLD rather than invert.

    On a voided market the venue grades every leg a loser, so a losing Under
    there is not evidence that the over happened. Inverting it would print the
    fabricated 100% `_verdict_is_provable` was written to refuse (#6169) —
    `/events/15311870`, 45 legs all `is_winner=False` at `clob_authoritative`.
    """

    def test_both_legs_graded_losers_serve_no_verdict_and_keep_the_price(self):
        market = _poly_total()
        outcomes = [
            _outcome(id=901, market_id=market.id, name="Under", prob=0.5,
                     is_winner=False, resolution_source="clob_authoritative"),
            _outcome(id=902, market_id=market.id, name="Over", prob=0.5,
                     is_winner=False, resolution_source="clob_authoritative"),
        ]
        rows = [
            t for t in _payload([market], outcomes).get("totals", [])
            if t["threshold"] == 52.5
        ]
        assert rows, "the voided rung left the ladder entirely"
        row = rows[0]
        # 🔴 The dedup keeps ONE leg per threshold and it is the Under here
        # (measured on this fixture, and the same leg production served at
        # 22:10:41Z). Asserted rather than branched on, so this test can never
        # pass by quietly grading the sibling instead of the subject.
        assert row["outcome_name"] == "Under", (
            f"this class grades the UNDER leg; the ladder served {row['outcome_name']}"
        )
        assert row["over_probability"] == 0.5, (
            f"a voided market was served as a certainty: {row['over_probability']}"
        )
        assert row["is_winner"] is None, (
            "a losing Under on a VOIDED market was inverted into a 100% "
            "nobody earned"
        )
        assert row["resolution_source"] == "clob_authoritative", (
            "the grade is real and only the AXIS is unknowable — and the "
            "#1588 window filter reads this key to tell a settled row from a "
            "stale quote (see TestTheWithheldRowStaysOnTheLadder)"
        )

    def test_a_lone_losing_under_with_no_winner_anywhere_states_nothing(self):
        """The one-sided form of the same void, where no sibling can rescue the
        threshold — so the withholding is observable on its own row."""
        market = _poly_total()
        outcomes = [
            _outcome(id=901, market_id=market.id, name="Under", prob=0.03,
                     is_winner=False, resolution_source="api_settlement"),
        ]
        row = _game_total_rungs(_payload([market], outcomes))[52.5]

        assert row["over_probability"] == 0.97, "a void is still a price"
        assert row["is_winner"] is None
        assert row["resolution_source"] == "api_settlement"


class TestTheWithheldRowStaysOnTheLadder:
    """🔴 The one side effect of this change a reader could see, pinned.

    A withheld verdict keeps its `resolution_source`, and that is not a detail:
    the #1588 window filter reads that key to tell a settled row from a stale
    quote, so a period rung that gave it up would leave the ladder entirely
    rather than merely stop claiming a winner. That is the #6196 direction in
    reverse — a settled ladder must keep its rungs — and it is invisible in the
    full-game fixtures above, because only a window-bounded market is filtered.

    Built as the FIRST draft of this repair actually behaved: nulling both keys
    reddened `test_a_lone_losing_leg_with_no_winner_anywhere_keeps_its_price`
    in #6169's suite, which is how the disappearance was found.
    """

    def test_a_voided_period_under_keeps_its_rung_its_price_and_no_verdict(self):
        market = _half_market()
        outcomes = [
            _outcome(id=920, market_id=market.id, name="Under 10.5 2H points scored",
                     prob=0.03, is_winner=False, resolution_source="api_settlement"),
        ]
        rungs = _half_total_rungs(_payload([market], outcomes))

        assert 10.5 in rungs, (
            "the voided period rung vanished from the ladder — a withheld "
            "verdict must not withhold the ROW (#1588 reads the source)"
        )
        assert rungs[10.5]["over_probability"] == 0.97
        assert rungs[10.5]["is_winner"] is None
        assert rungs[10.5]["resolution_source"] == "api_settlement"

    def test_a_provable_period_under_is_inverted_and_kept(self):
        """The twin, one market-state over: a PROVABLE Under on the same
        window-bounded ladder states the over's answer and keeps its rung.

        🔴 The two rungs are at different thresholds on purpose. A winning
        `Over 10.5` at the SAME line wins the threshold dedup, and then this
        test would grade the sibling and pass whatever the Under row said —
        the vacuous form of exactly the assertion it exists to make.
        """
        market = _half_market()
        outcomes = [
            _outcome(id=920, market_id=market.id, name="Under 45.5 2H points scored",
                     prob=0.97, is_winner=True, resolution_source="api_settlement"),
            _outcome(id=921, market_id=market.id, name="Over 10.5 2H points scored",
                     prob=0.97, is_winner=True, resolution_source="api_settlement"),
        ]
        rungs = _half_total_rungs(_payload([market], outcomes))

        assert 45.5 in rungs, "the provable period rung vanished from the ladder"
        assert rungs[45.5]["outcome_name"].startswith("Under"), (
            f"this test grades the UNDER leg; it served {rungs[45.5]['outcome_name']}"
        )
        assert rungs[45.5]["over_probability"] == 0.0
        assert rungs[45.5]["is_winner"] is False
        assert rungs[45.5]["resolution_source"] == "api_settlement"
        assert rungs[10.5]["is_winner"] is True, "the Over rung is untouched"


class TestTheTierBoundaryIsTheDocumentedOne:
    """A tier-1 grade is a reading of a price, not an answer, so it is not
    inverted either — the same boundary `_settled_over_probability` keeps, and
    `test_a_settled_leg_takes_no_live_price_5411` is why it is asserted in both
    directions rather than assumed."""

    def test_a_tier_one_retraction_on_an_under_is_not_inverted(self):
        market = _poly_total()
        outcomes = [
            _outcome(id=901, market_id=market.id, name="Under", prob=0.62,
                     is_winner=True, resolution_source="ungradeable_result"),
            _outcome(id=902, market_id=market.id, name="Over", prob=0.38,
                     is_winner=False, resolution_source="ungradeable_result"),
        ]
        rows = [
            t for t in _payload([market], outcomes).get("totals", [])
            if t["threshold"] == 52.5
        ]
        assert rows, "the tier-1 rung left the ladder entirely"
        row = rows[0]
        assert row["outcome_name"] == "Under", (
            f"this class grades the UNDER leg; the ladder served {row['outcome_name']}"
        )
        assert row["over_probability"] == 0.38, "a tier-1 row keeps its price"
        assert row["is_winner"] is None, (
            "a retraction was inverted into a verdict about the over"
        )
        assert row["resolution_source"] == "ungradeable_result"

    def test_a_tier_two_grade_on_an_under_is_inverted(self):
        """The twin: one tier up, the same row states the over's answer. Without
        this pair a change that refuses everything would pass the test above."""
        markets, outcomes = _specimen(source="game_score", sibling_source="game_score")
        row = _game_total_rungs(_payload(markets, outcomes))[52.5]

        assert row["is_winner"] is False
        assert row["resolution_source"] == "game_score"
        assert row["over_probability"] == 0.0
