"""#6196 — a settled ladder keeps the lines that did NOT come in.

## The ship

A settled totals card is headed **"EACH LINE VS THE FINAL"** and then lists only
the lines that cleared. The lines the game failed to reach are not drawn as
`not cleared` — they are absent from the payload, so the card cannot draw them
and a reader cannot tell they were ever offered.

After this change a settled ladder serves BOTH halves of its own question: the
rungs that cleared at 1.0 and the rungs that did not at 0.0, each carrying the
grade that proves it.

## 🔴 Measured on production before building

`/events/14637256` (Giants 28 Cowboys 20, Final), read 2026-09-14 19:0xZ from
`GET /api/events/14637256/game-markets` — *after* both halves of #6169 were
live. Eleven settled totals markets on this one event hold **83 tier-2+ graded
losing rungs between them, and ZERO of them reach the payload**:

    market                       winners   graded losers   served
    Dallas vs New York: Total Points   9          10          9
    1st Half Total                     6           7          6
    2nd Half Total                     8           5          8
    1st Quarter Total                  2           8          2
    2nd Quarter Total                  5           5          5
    3rd Quarter Total                  5           5          5
    4th Quarter Total                  4           6          4
    Team Total                        14          14         …
    1st Half Team Total                7          14         …
    Team Total Yards                   3           7          …
    Total Touchdowns                   5           2          …

Seven ladders visible on one page and not one "not cleared" row among them. The
served game-total ladder is *exactly* its nine winners — `27.5 … 47.5`, all
`1.0` — and the ten lines above the 48-point final (`48.5 … 69.5`, every one
`is_winner=False`, `api_settlement`, stored `0.000000`) are gone.

## 🔴 One line dropped them, and #6169 did not put it there

`_enforce_monotonicity` opens by filtering `prob > 0`. That is correct while the
ladder is LIVE — a 0% rung is a dead quote and showing it is noise — and wrong
the moment the question is answered, because a settled 0.0 is not a price that
decayed, it is the ANSWER "this line did not come in".

This is older than both halves of #6169 and neither caused it; the full-game
card has graded since #3769 and has been serving losers-free ladders throughout.
What #6169 did was move `Over 38.5` from a stuck `0.5` to its true `0.0`, at
which point this filter took the row — a correct fix making one instance of an
older defect more visible. The drop is also why #6169's own tests had to prove
three separate claims by ASSERTING AN ABSENCE; those three are strengthened to
assert values in `test_a_settled_ladder_rung_serves_its_verdict_6169.py`, and one
of them had pinned this defect outright.

## 🔴 The doctrine is #4845's, one bucket over

The spreads path already solved exactly this: `_deep_otm_spreads` →
`_window_closed_items`, where a deep-OTM rung whose window is provably over
reaches the reader verdict-only rather than vanishing. Its comment names the
shape — *"Atlanta -1.5 first 5 innings" is absent from a page carrying its
sibling "Tampa Bay -1.5": one side of the same question, at 0.01, silently
gone.* The totals path never got that rescue, and it is the harsher of the two:
the spreads floor at least routes its casualties into a collection, while this
comprehension drops the row outright.

## 🔴 Why `_verdict_is_provable` and not `is_winner is False`

On a VOIDED market the venue grades every leg a loser and none a winner, so a
tier-3 `is_winner=False` there proves nothing and its 0.0 must stay dropped —
that predicate's docstring measures 389 such markets across 163 events in a
trailing fortnight. Every class below therefore has its negative twin: a live
ladder's 0.0 still goes, an ungraded 0.0 still goes, a tier-1 `ungradeable_result`
retraction still goes, and a voided market's legs still go. A change that
readmits every zero is as wrong as no change at all, and only the pair tells them
apart.

## Why the real endpoint

`_enforce_monotonicity` is a closure inside a 900-line builder, and the filter
under test runs ~500 lines before the payload is assembled — between them sit
the dedup, the sport-range guard, `_match_scope_totals`, the capping walk and
the `_window_open` suppression, any of which could drop a readmitted row. These
tests drive the real `_build_game_markets` against a doubled session so the
subject is what a reader is SERVED, not what one comprehension returns.
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

#: The production game-total ladder, verbatim (market 58728463,
#: `KXNFLTOTAL-26SEP13DALNYG`, `resolved`, read 2026-09-14 19:1xZ).
#: `(threshold, current_probability, is_winner, resolution_source)`.
#: The game finished 48 points, so the ladder turns over between 47.5 and 48.5.
GAME_TOTAL_LADDER = (
    (27.5, 1.0, True, "api_settlement"),
    (30.5, 1.0, True, "api_settlement"),
    (33.5, 1.0, True, "api_settlement"),
    (36.5, 1.0, True, "api_settlement"),
    (39.5, 1.0, True, "api_settlement"),
    (42.5, 1.0, True, "api_settlement"),
    (45.5, 1.0, True, "api_settlement"),
    (46.5, 1.0, True, "api_settlement"),
    (47.5, 1.0, True, "api_settlement"),
    (48.5, 0.0, False, "api_settlement"),   # ← the final was 48; from here down
    (49.5, 0.0, False, "api_settlement"),   #   every line is a LOSER, and every
    (50.5, 0.0, False, "api_settlement"),   #   one of them was dropped.
    (51.5, 0.0, False, "api_settlement"),
    (54.5, 0.0, False, "api_settlement"),
    (57.5, 0.0, False, "api_settlement"),
    (60.5, 0.0, False, "api_settlement"),
    (63.5, 0.0, False, "api_settlement"),
    (66.5, 0.0, False, "api_settlement"),
    (69.5, 0.0, False, "api_settlement"),
)

CLEARED = tuple(t for t, _p, won, _s in GAME_TOTAL_LADDER if won)
DID_NOT_CLEAR = tuple(t for t, _p, won, _s in GAME_TOTAL_LADDER if not won)

#: What production served for this ladder before the change: the winners, and
#: nothing else. Held as data so the "before" stays quotable once it is gone.
SERVED_BEFORE = CLEARED

#: The 2nd-half ladder from the same page (market 60075100). #6169 repaired the
#: PRICES on this one; the losing rungs were still dropped afterwards.
HALF_TOTAL_LADDER = (
    (7.5, 0.5, True, "game_score"),
    (10.5, 1.0, True, "api_settlement"),
    (14.5, 1.0, True, "api_settlement"),
    (17.5, 1.0, True, "api_settlement"),
    (20.5, 1.0, True, "api_settlement"),
    (21.5, 1.0, True, "api_settlement"),
    (24.5, 1.0, True, "api_settlement"),
    (28.5, 0.0, False, "api_settlement"),
    (31.5, 0.0, False, "api_settlement"),
    (38.5, 0.5, False, "game_score"),
)


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


def _market(*, id=601, name="Dallas vs New York: Total Points",
            external_id="KXNFLTOTAL-26SEP13DALNYG", status="resolved"):
    market = MagicMock()
    market.id, market.name, market.external_id = id, name, external_id
    market.event_id, market.category, market.status = 42, "game_prop", status
    market.source, market.sport_id = "kalshi", 1
    market.llm_sport_category = "americanfootball"
    market.commence_time = KICKOFF
    market.group_id = market.group_type = None
    market.market_metadata = None
    market.market_tier = 5
    return market


def _half_market(*, id=602, status="resolved"):
    return _market(
        id=id,
        name="DAL Cowboys vs NY Giants: 2nd Half Total",
        external_id="KXNFL2HTOTAL-26SEP13DALNYG",
        status=status,
    )


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


def _ladder_outcomes(ladder, *, market_id=601, label="points scored", first_id=700):
    return [
        _outcome(
            id=first_id + i,
            market_id=market_id,
            name=f"Over {threshold} {label}",
            prob=prob,
            is_winner=won,
            resolution_source=source,
        )
        for i, (threshold, prob, won, source) in enumerate(ladder)
    ]


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


def _half_total_rungs(payload):
    """`{threshold: row}` for the served 2H total ladder."""
    return {
        pm["threshold"]: pm
        for pm in payload.get("period_markets", [])
        if pm.get("market_type") == "half_total"
    }


# ─────────────────────────────────────────────────────────────────────────────
# THE SHIP
# ─────────────────────────────────────────────────────────────────────────────


class TestASettledLadderShowsBothHalvesOfItsQuestion:
    def test_the_ten_lines_the_game_did_not_reach_are_served(self):
        """🔴 The required regression, on the measured ladder verbatim.

        Nineteen rungs were stored and nine were served. All nineteen now are.
        """
        rungs = _game_total_rungs(
            _payload([_market()], _ladder_outcomes(GAME_TOTAL_LADDER))
        )

        assert set(rungs) >= set(CLEARED), (
            f"fixture did not build the specimen ladder: {sorted(rungs)}"
        )
        missing = [t for t in DID_NOT_CLEAR if t not in rungs]
        assert missing == [], (
            f"lines the game did not reach are still dropped: {missing} "
            f"(production served only {list(SERVED_BEFORE)})"
        )
        for threshold in DID_NOT_CLEAR:
            assert rungs[threshold]["over_probability"] == 0.0, (
                f"Over {threshold} did not come in and is served "
                f"{rungs[threshold]['over_probability']}"
            )

    def test_the_lines_that_cleared_still_read_as_cleared(self):
        """#6169's ship is not disturbed by #6196's."""
        rungs = _game_total_rungs(
            _payload([_market()], _ladder_outcomes(GAME_TOTAL_LADDER))
        )
        for threshold in CLEARED:
            assert rungs[threshold]["over_probability"] == 1.0, (
                f"Over {threshold} cleared and is served "
                f"{rungs[threshold]['over_probability']}"
            )

    def test_the_served_ladder_is_no_longer_winners_only(self):
        """🔴 The defect stated as the property that made it invisible.

        Every rung production served carried `is_winner=True`. A card headed
        "each line vs the final" whose every row is a winner is not reporting a
        result, it is reporting a selection.
        """
        rungs = _game_total_rungs(
            _payload([_market()], _ladder_outcomes(GAME_TOTAL_LADDER))
        )
        verdicts = {r["is_winner"] for r in rungs.values()}
        assert verdicts == {True, False}, (
            f"the ladder serves only {verdicts} — production served only "
            f"{{True}} across all seven ladders on this page"
        )
        assert len(rungs) == len(GAME_TOTAL_LADDER) == 19
        assert sum(1 for r in rungs.values() if r["is_winner"]) == 9
        assert sum(1 for r in rungs.values() if r["is_winner"] is False) == 10

    def test_a_losing_rung_carries_what_the_card_needs_to_say_not_cleared(self):
        """The render half of #6169 draws `not cleared` off these two keys
        (#4788: a row with no `resolution_source` prints no verdict). Serving
        the row without them would move the blank card one layer down."""
        rungs = _game_total_rungs(
            _payload([_market()], _ladder_outcomes(GAME_TOTAL_LADDER))
        )
        loser = rungs[48.5]
        assert loser["is_winner"] is False
        assert loser["resolution_source"] == "api_settlement"
        assert loser["threshold"] == 48.5
        assert loser["outcome_name"] == "Over 48.5 points scored"

    def test_the_half_ladder_keeps_its_losers_too(self):
        """The second ladder on the same page, and the one #6169 photographed.

        `Over 38.5` was served at 50% before #6169, dropped after it, and reads
        0.0 now. `28.5` and `31.5` were dropped throughout.
        """
        rungs = _half_total_rungs(
            _payload(
                [_half_market()],
                _ladder_outcomes(HALF_TOTAL_LADDER, market_id=602,
                                 label="2H points scored", first_id=800),
            )
        )
        for threshold in (28.5, 31.5, 38.5):
            assert threshold in rungs, f"Over {threshold} is still dropped"
            assert rungs[threshold]["over_probability"] == 0.0
            assert rungs[threshold]["is_winner"] is False

    def test_the_served_ladder_is_still_monotone(self):
        """Readmitting rows must not produce a ladder that contradicts itself:
        P(Over X) may not RISE as X gets harder."""
        rungs = _game_total_rungs(
            _payload([_market()], _ladder_outcomes(GAME_TOTAL_LADDER))
        )
        probs = [rungs[t]["over_probability"] for t in sorted(rungs)]
        assert probs == sorted(probs, reverse=True), f"ladder is not monotone: {probs}"


# ─────────────────────────────────────────────────────────────────────────────
# THE OTHER DIRECTION — readmitting every zero is not a fix
#
# Each test here fails if the `> 0` filter is simply deleted, which is the one
# mutation that satisfies every test above.
# ─────────────────────────────────────────────────────────────────────────────


class TestAZeroThatIsNotAVerdictStillGoes:
    def test_a_live_ladders_zero_rung_is_still_dropped(self):
        """🔴 The anti-strawman. #921's behaviour is unchanged while the
        question is open: a 0% rung on a live game is a dead quote, not an
        answer, and the reader is not shown it."""
        live_ladder = (
            (27.5, 0.60, None, None),
            (48.5, 0.0, None, None),
        )
        rungs = _game_total_rungs(
            _payload(
                [_market(status="open")],
                _ladder_outcomes(live_ladder),
                event=_event(status="live"),
            )
        )
        assert 27.5 in rungs, f"fixture built {sorted(rungs)}"
        assert 48.5 not in rungs, "a live 0% quote was published as a verdict"

    def test_an_ungraded_zero_on_a_finished_game_is_still_dropped(self):
        """A finished game is not enough — the ROW must carry a grade. An
        ungraded 0.0 is the stale quote this filter has always existed for."""
        ladder = (
            (27.5, 1.0, True, "api_settlement"),
            (48.5, 0.0, None, None),
        )
        rungs = _game_total_rungs(_payload([_market()], _ladder_outcomes(ladder)))
        assert rungs[27.5]["over_probability"] == 1.0
        assert 48.5 not in rungs, "an ungraded 0.0 was served as a verdict"

    def test_a_tier_one_retraction_at_zero_is_still_dropped(self):
        """`ungradeable_result` is a RETRACTION, tier 1 — a reading of a price,
        never an answer (#5411). It does not buy a row back onto the page."""
        ladder = (
            (27.5, 1.0, True, "api_settlement"),
            (48.5, 0.0, False, "ungradeable_result"),
        )
        rungs = _game_total_rungs(_payload([_market()], _ladder_outcomes(ladder)))
        assert rungs[27.5]["over_probability"] == 1.0
        assert 48.5 not in rungs, "a tier-1 retraction was served as a verdict"

    def test_a_voided_markets_zero_leg_is_still_dropped(self):
        """🔴 The `_verdict_is_provable` half, and the reason the predicate is
        not `_row_is_graded_at_verdict_tier` alone.

        A void grades EVERY leg a loser and none a winner, so `Over 48.5` here
        is tier-3, definite and unanimous — and settles nothing. Readmitting it
        would tell a reader that a line failed in a game that was never scored.

        🔴 THE SURVIVING 0.5 LEG IS THE FIXTURE, NOT DECORATION. An earlier
        draft voided the whole ladder to 0.0 and passed against every mutant,
        including the deletion of the filter it exists to guard — because
        `has_no_real_price` (#921 slice 2, ~500 lines upstream) drops a market
        whose every outcome is null or zero, so the rows never reached the
        filter at all and the test proved nothing. A real void does not look
        like that: #6169's specimen, `/events/15311870`, carried all 45 legs at
        exactly `0.500000`. One live-looking leg is what puts this ladder in
        front of the code under test.
        """
        voided = (
            (27.5, 0.5, False, "clob_authoritative"),
            (48.5, 0.0, False, "clob_authoritative"),
        )
        rungs = _game_total_rungs(_payload([_market()], _ladder_outcomes(voided)))
        assert 27.5 in rungs, (
            "fixture did not survive `has_no_real_price` — this test is vacuous "
            "without a non-zero leg"
        )
        assert 48.5 not in rungs, (
            "a voided market's leg was served as a verdict: "
            f"{rungs.get(48.5, {}).get('over_probability')}"
        )

    def test_the_same_row_is_kept_or_dropped_on_its_market_having_a_winner(self):
        """The pair that isolates the predicate: one ladder, one changed fact.

        Identical thresholds, identical tier, identical 0.0 on the rung under
        test — the only difference is whether the market produced a winner, and
        that alone decides whether its 0.0 is a verdict or the residue of a void.
        """
        settled = (
            (27.5, 1.0, True, "clob_authoritative"),
            (48.5, 0.0, False, "clob_authoritative"),
        )
        voided = (
            (27.5, 0.5, False, "clob_authoritative"),
            (48.5, 0.0, False, "clob_authoritative"),
        )
        kept = _game_total_rungs(_payload([_market()], _ladder_outcomes(settled)))
        dropped = _game_total_rungs(
            _payload([_market(id=605)], _ladder_outcomes(voided, market_id=605))
        )
        assert kept[48.5]["over_probability"] == 0.0, "the settled loser was dropped"
        assert 27.5 in dropped, "the voided fixture did not reach the filter"
        assert 48.5 not in dropped, "the voided loser was served as a verdict"


# ─────────────────────────────────────────────────────────────────────────────
# THE DONATION — a readmitted 0.0 now reaches the capping walk
# ─────────────────────────────────────────────────────────────────────────────


class TestASettledZeroDonatesLikeAnyOtherRung:
    def test_it_caps_an_ungraded_neighbour_above_it_and_keeps_it_visible(self):
        """Before #6196 a settled 0.0 never reached this pass, so an ungraded
        rung above it kept its own price. Now it inherits 0.0 — which is the
        arithmetic and not a guess: these are rungs of ONE ladder, so if 48.5
        did not come in then 54.5 did not either.

        The capped row stays on the page (the filter has already run by then)
        and carries no grade, so it prints no verdict and reads as the absent
        price it is.
        """
        ladder = (
            (27.5, 1.0, True, "api_settlement"),
            (48.5, 0.0, False, "api_settlement"),
            (54.5, 0.35, None, None),
        )
        rungs = _game_total_rungs(_payload([_market()], _ladder_outcomes(ladder)))

        assert rungs[48.5]["over_probability"] == 0.0
        assert 54.5 in rungs, "the capped neighbour left the page"
        assert rungs[54.5]["over_probability"] == 0.0, "a stale 0.35 outlived its ladder"
        assert rungs[54.5]["observed_at_basis"] == "capped_to_sibling"
        assert rungs[54.5]["is_winner"] is None, "an ungraded row must claim no verdict"

    def test_a_settled_zero_is_not_itself_rewritten(self):
        """#6169's exemption still holds in the presence of the readmitted rows:
        a graded rung states what happened and is never capped to a sibling."""
        rungs = _game_total_rungs(
            _payload([_market()], _ladder_outcomes(GAME_TOTAL_LADDER))
        )
        capped = [t for t, r in rungs.items()
                  if r.get("observed_at_basis") == "capped_to_sibling"]
        assert capped == [], f"a verdict was rewritten to a sibling's price: {capped}"
