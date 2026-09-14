"""#6205 — a settled period ladder keeps the rung that WON.

## The ship

A settled period-total card ("1st Quarter Total", "2nd Half Total") lists the
lines graded against the period's score. It was starting ABOVE its own bottom
rung: on `/events/14637256` six ladders each hold an `Over 3.5` at
`current_probability=1.000000, is_winner=true` and every served array begins at
6.5 or 7.5. 1st Quarter Total holds TWO winning rungs (3.5, 6.5) and served one.

After this change the winning rung is served and the reader sees the line that
came in.

## 🔴 Measured on production before building — the whole population, not a sample

`GET /api/admin/db-query`, 2026-09-14, over every period-total market linked to
an event (Kalshi period tickers `kx{league}{1h|2h|1q..4q}total`):
**1,619 markets / 16,369 outcome rows.**

    bound        rows dropped   of which graded WINNERS   contaminants caught
    FLOOR            1,472               1,166                    0
    CEILING              9                   6                    1

The floor was the borrowed `_SPORT_TEAM_TOTAL_RANGE` low end — a number derived
for a team's FULL GAME, applied to a quarter:

  * `americanfootball` floor 5 → ate 648 rows, 578 of them winners (every NFL
    period line at 2.5 and 3.5).
  * `basketball` floor 60 → ate 824 rows, 588 of them winners. That floor sits
    ABOVE most of the ladder, so Kalshi's own NBA quarter rungs
    (`KXNBA1QTOTAL-…`, 3.5 … 57.5) and every NCAAB/WNBA half line below 60 went
    with it.
  * `soccer` floor 0.5 → ate nothing; the observed minimum IS 0.5.

The ceiling, by contrast, earns its place: the single cross-sport contaminant in
the whole population is `KXNBA1HTOTAL-26MAR09NYKLAC` — an NBA first-half total,
thresholds 102.5–126.5 — linked to the MLS fixture LA Galaxy v NYCFC (event
5766535), and the soccer ceiling of 7 rejects all 9 of its rows.

## 🔴 Why the floor is replaced and not re-derived

At the low end a period total's magnitude carries no sport information. A
legitimate NFL quarter line and a foreign soccer half line are THE SAME NUMBER
(2.5), so any floor high enough to reject the second rejects the first. And
lowering `_SPORT_TEAM_TOTAL_RANGE` is not available either — that constant is
also the full-game team-total floor, so dragging it down reopens the cross-game
contamination step 7a exists to catch.

So the magnitude floor goes entirely — see the sweep note below for why no
replacement was written — and the protection the old floor CLAIMED is paid by an
exact test instead: the market's Kalshi ticker, when it names a league, must name
a league of THIS event's sport. Over the same 16,369 rows that is 1-for-1 on the
contaminant with zero false positives, where the floor was 0-for-1.

`test_the_low_magnitude_foreign_line_the_old_floor_pretended_to_catch` is the
one that matters: it is the case the floor was justified by and never met in
production, and it stays closed for the right reason.

## 🔴 Vacuity

These tests drive the REAL `_build_game_markets`, not the comprehension. #6196's
sweep is why: `has_no_real_price` drops all-null/all-zero markets ~500 lines
upstream, so a fixture built without live prices passes for a reason unrelated
to the predicate under test. Every ladder below carries real probabilities and
the guard sits between them and the payload.

Four mutants, each killed, and the two narrow ones killed by ONE test each —
which is what says the tests are separable rather than all riding one behaviour:

  * the parent (whole fix reverted)  → 4 tests
  * restore the team-total floor     → the same 4
  * delete the foreign-ticker check  → the low-magnitude foreign test, alone
  * drop the ceiling                 → the game-scope-number test, alone

The sweep's first run had TWO survivors and both were findings about this edit,
not about the tests. Dropping the ceiling left every test green, because the one
measured contaminant is rejected by the ticker test as well — so the ceiling got
a case only it can catch, built rather than found and labelled as such. And a
`threshold >= 0` clause in the first cut turned out to be unreachable: the
extractor's regex has no sign group. That clause was DELETED and its vacuous
test replaced by one that pins the reason.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes import events as events_route
from app.routes.events import _game_markets_cache

NOW = datetime(2026, 9, 14, 23, 0, tzinfo=timezone.utc)
KICKOFF = NOW - timedelta(hours=4)
FINAL_AT = NOW - timedelta(hours=1)


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


def _market(*, id, name, external_id, sport_category="americanfootball"):
    market = MagicMock()
    market.id, market.name, market.external_id = id, name, external_id
    market.event_id, market.category, market.status = 42, "game_prop", "resolved"
    market.source, market.sport_id = "kalshi", 1
    market.llm_sport_category = sport_category
    market.commence_time = KICKOFF
    market.group_id = market.group_type = None
    market.market_metadata = None
    market.market_tier = 5
    return market


def _outcome(*, id, market_id, name, prob, is_winner=None,
             resolution_source="api_settlement"):
    outcome = MagicMock()
    outcome.id, outcome.market_id, outcome.name = id, market_id, name
    outcome.current_probability = prob
    outcome.opening_probability = 0.5
    outcome.is_winner = is_winner
    outcome.resolution_source = resolution_source
    outcome.last_updated = NOW
    return outcome


def _ladder(market_id, rungs, *, label="1Q points scored", first_id=700):
    """`rungs` = [(threshold, prob, is_winner), …]."""
    return [
        _outcome(
            id=first_id + i,
            market_id=market_id,
            name=f"Over {threshold} {label}",
            prob=prob,
            is_winner=won,
        )
        for i, (threshold, prob, won) in enumerate(rungs)
    ]


def _event(*, sport_key="americanfootball_nfl", home="Dallas Cowboys",
           away="New York Giants", home_score=20, away_score=28):
    event = MagicMock()
    event.id, event.status, event.sport_id = 42, "completed", 1
    event.sport = MagicMock()
    event.sport.key = sport_key
    event.home_team_name, event.away_team_name = home, away
    event.home_score, event.away_score = home_score, away_score
    event.commence_time = KICKOFF
    event.completed_at = FINAL_AT
    event.box_score_data = None
    event.period, event.game_clock = "Final", None
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


def _period_rungs(payload, market_type="quarter_total"):
    """`{threshold: row}` for the served period ladder of one type."""
    return {
        pm["threshold"]: pm
        for pm in payload.get("period_markets", [])
        if pm.get("market_type") == market_type
    }


# ─────────────────────────────────────────────────────────────────────────────
# THE SHIP — the winning rung below the borrowed floor is served
# ─────────────────────────────────────────────────────────────────────────────


class TestASettledPeriodLadderKeepsTheRungThatWon:
    def test_the_nfl_first_quarter_winner_at_3_5_is_served(self):
        """The production specimen: two winners in the DB, one served.

        Event 14637256's 1st Quarter Total holds `Over 3.5` and `Over 6.5` both
        at is_winner=true; the `americanfootball` floor of 5 took the first.
        """
        market = _market(
            id=601,
            name="Dallas vs New York: 1st Quarter Total",
            external_id="KXNFL1QTOTAL-26SEP13DALNYG",
        )
        outcomes = _ladder(601, [
            (3.5, 1.0, True),
            (6.5, 1.0, True),
            (10.5, 0.0, False),
            (13.5, 0.0, False),
        ])

        rungs = _period_rungs(_payload([market], outcomes))

        assert 3.5 in rungs, (
            "the winning bottom rung is the whole ship; served rungs were "
            f"{sorted(rungs)}"
        )
        assert rungs[3.5]["over_probability"] == 1.0
        assert rungs[3.5]["is_winner"] is True
        # and it did not arrive by losing the rest of its own ladder
        assert sorted(rungs) == [3.5, 6.5, 10.5, 13.5]

    def test_the_nba_quarter_ladder_below_the_basketball_floor_is_served(self):
        """`basketball`'s floor of 60 sat ABOVE most of its own ladder.

        Kalshi ships `KXNBA1QTOTAL-…` from 3.5 up (measured: 3.5, 6.5, 7.5, 9.5,
        10.5, 13.5 all present and all graded winners on real NBA events), and a
        floor of 60 served none of them.
        """
        market = _market(
            id=602,
            name="Knicks vs Spurs: 1st Quarter Total",
            external_id="KXNBA1QTOTAL-26JUN03NYKSAS",
            sport_category="basketball",
        )
        outcomes = _ladder(602, [
            (3.5, 1.0, True),
            (13.5, 1.0, True),
            (31.5, 1.0, True),
            (45.5, 0.0, False),
            (63.5, 0.0, False),
        ])
        event = _event(
            sport_key="basketball_nba",
            home="San Antonio Spurs", away="New York Knicks",
            home_score=104, away_score=99,
        )

        rungs = _period_rungs(_payload([market], outcomes, event=event))

        assert {3.5, 13.5, 31.5} <= set(rungs), (
            "every rung below the old floor of 60 is a real NBA quarter line; "
            f"served rungs were {sorted(rungs)}"
        )
        assert all(rungs[t]["is_winner"] is True for t in (3.5, 13.5, 31.5))


# ─────────────────────────────────────────────────────────────────────────────
# WHAT THE GUARD STILL REFUSES
# ─────────────────────────────────────────────────────────────────────────────


class TestTheContaminantStillDoesNotReachTheReader:
    def test_the_measured_nba_half_total_on_an_mls_fixture_is_rejected(self):
        """The one real contaminant in the population, by ticker and threshold.

        `KXNBA1HTOTAL-26MAR09NYKLAC` linked to LA Galaxy v NYCFC. Two
        independent bounds reject it now — the soccer ceiling of 7 and the
        foreign-ticker test — and it must stay rejected when either is removed.
        """
        market = _market(
            id=603,
            name="New York vs Los Angeles C: First Half Total",
            external_id="KXNBA1HTOTAL-26MAR09NYKLAC",
            sport_category="basketball",
        )
        outcomes = _ladder(603, [
            (102.5, 0.9, True),
            (114.5, 0.6, True),
            (126.5, 0.2, False),
        ], label="1H points scored")
        event = _event(
            sport_key="soccer_usa_mls",
            home="Los Angeles G", away="New York City",
            home_score=2, away_score=1,
        )

        rungs = _period_rungs(_payload([market], outcomes, event=event),
                              market_type="half_total")

        assert rungs == {}, (
            "an NBA half total on an MLS fixture reaches no reader; "
            f"served {sorted(rungs)}"
        )

    def test_the_low_magnitude_foreign_line_the_old_floor_pretended_to_catch(self):
        """The hole a bare non-negative floor would open, closed exactly.

        A soccer first-half total (0.5/1.5/2.5) mislinked to an NFL event is the
        case the `americanfootball` floor of 5 was justified by. It is INSIDE
        the ceiling, so magnitude alone cannot reject it — and it cannot be
        rejected by magnitude anyway, because a real NFL quarter line lives at
        2.5 too (the test above serves one at 3.5). The ticker decides.
        """
        market = _market(
            id=604,
            name="LA Galaxy vs NYCFC: First Half Total",
            external_id="KXMLS1HTOTAL-26MAR09LANY",
            sport_category="soccer",
        )
        outcomes = _ladder(604, [
            (0.5, 0.8, True),
            (1.5, 0.5, False),
            (2.5, 0.2, False),
        ], label="1H goals scored")

        rungs = _period_rungs(_payload([market], outcomes),
                              market_type="half_total")

        assert rungs == {}, (
            "a soccer half total on an NFL page is rejected by its ticker, not "
            f"by its size; served {sorted(rungs)}"
        )

    def test_the_ceiling_alone_rejects_a_game_scope_number_in_a_period_slot(self):
        """🔴 MANUFACTURED SPECIMEN, and labelled as one.

        The mutant sweep found the measured contaminant above does NOT pin the
        ceiling: its NBA-ticker-on-an-MLS-fixture shape is rejected by the
        foreign-ticker test too, so dropping the ceiling left all seven tests
        green. The ceiling is pre-existing behaviour this ship deliberately
        preserves, so it needs a case only IT can catch — same sport, so the
        ticker test is silent, and a game-scope number sitting in a period slot.

        No such row exists in production today (the ceiling's entire measured
        yield is the 9 cross-sport rows), which is exactly why the specimen is
        built rather than found.
        """
        market = _market(
            id=605,
            name="Knicks vs Spurs: 1st Half Total",
            external_id="KXNBA1HTOTAL-26JUN03NYKSAS",
            sport_category="basketball",
        )
        outcomes = _ladder(605, [
            (55.5, 1.0, True),     # a real half line
            (220.5, 0.5, None),    # a full-GAME number in a half slot
        ], label="1H points scored")
        event = _event(
            sport_key="basketball_nba",
            home="San Antonio Spurs", away="New York Knicks",
            home_score=104, away_score=99,
        )

        rungs = _period_rungs(_payload([market], outcomes, event=event),
                              market_type="half_total")

        assert 220.5 not in rungs, (
            "a half total above a team's full-game total is not a half total; "
            f"served {sorted(rungs)}"
        )
        assert 55.5 in rungs, "and its legitimate sibling still arrives"

    def test_a_total_threshold_can_never_be_negative(self):
        """Why no magnitude FLOOR is owed, pinned at its cause.

        The first cut of this fix carried a `threshold >= 0` clause. The mutant
        sweep could not kill it: `_extract_threshold` matches
        `(\\d+(?:\\.\\d+)?)`, which has no sign group, so a total's threshold
        cannot be negative and the clause was unreachable. It was deleted.

        This test guards the REASON rather than the deleted code — give that
        regex a sign group and this fails, which is the moment the period guard
        would owe a floor again.
        """
        for name in ("Over -3.5 2Q points scored", "Under -1.5", "Spread -3.5"):
            got = events_route._extract_threshold(name)
            assert got is None or got >= 0, (
                f"{name!r} parsed to {got}; a negative total threshold is now "
                "reachable and the period guard needs a floor again"
            )


# ─────────────────────────────────────────────────────────────────────────────
# WHAT THE EXACT TEST DELIBERATELY DOES NOT DO
# ─────────────────────────────────────────────────────────────────────────────


class TestTheTickerTestOnlyEverAddsInformation:
    def test_a_polymarket_period_total_has_no_ticker_and_is_untouched(self):
        """No resolvable ticker ⇒ no opinion. It never guesses from absence.

        Polymarket carries a condition-id hash, not a league prefix, and its
        period totals must reach the reader exactly as before.
        """
        market = _market(
            id=606,
            name="Cowboys vs. Giants: 1st Quarter O/U 6.5",
            external_id="0xb7373206521f571e93ccbec6287b1df06f4f1eae37a381a00",
        )
        market.source = "polymarket"
        outcomes = [
            _outcome(id=760, market_id=606, name="Over", prob=1.0, is_winner=True),
            _outcome(id=761, market_id=606, name="Under", prob=0.0, is_winner=False),
        ]

        rungs = _period_rungs(_payload([market], outcomes))

        assert 6.5 in rungs, f"served {sorted(rungs)}"

    def test_a_sibling_league_of_the_same_sport_passes(self):
        """Cross-LEAGUE is the matcher's business (#2693), not this guard's.

        An NCAAF ticker on an NFL event is a matching question; this test only
        ever asks about the SPORT, so it must not fire here.
        """
        market = _market(
            id=607,
            name="Dallas vs New York: 1st Quarter Total",
            external_id="KXNCAAFB1QTOTAL-26SEP13DALNYG",
        )
        outcomes = _ladder(607, [(3.5, 1.0, True), (10.5, 0.0, False)])

        rungs = _period_rungs(_payload([market], outcomes))

        assert 3.5 in rungs and 10.5 in rungs, f"served {sorted(rungs)}"
