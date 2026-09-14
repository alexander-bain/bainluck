"""#6169 — a settled ladder rung serves its VERDICT, not its last live price.

## The ship

On `/events/14637256` (Giants 28 Cowboys 20, Sunday night, Final 03:28Z) the
2nd-half points map printed **`FINAL 27 points`** and, on the same card,
**`Over 7.5 · 10.5 · 14.5 · 17.5 · 20.5 · 21.5 · 24.5 — 50%`**: seven lines the
game had already cleared, served to the reader as a coin flip, beside a 1st-half
card reading 100% correctly.

After this change those rungs read 100% — the same answer their own database
rows have carried since 10:50:59Z.

## 🔴 The database was RIGHT and the payload was wrong

Measured on production 2026-09-14, market 60075100 (`KXNFL2HTOTAL`, `resolved`):

    Over  7.5   current_probability 0.5   is_winner True    game_score
    Over 10.5   current_probability 1.0   is_winner True    api_settlement
    Over 14.5 … 24.5   (five more)  1.0   is_winner True    api_settlement
    Over 28.5 / 31.5   0.0   is_winner False   api_settlement
    Over 38.5          0.5   is_winner False   game_score

`GET /api/events/14637256/game-markets` served every one of the eight surviving
rungs at `0.5`, and the six settled winners carried
`observed_at_basis: "capped_to_sibling"` — the payload naming its own culprit.
Ten consecutive fetches were identical, so this was never the per-dyno memo.

The chain, and it reproduces the served payload rung for rung:

1. two legs graded by `game_score` keep their last live price — that rail writes
   `is_winner` + `resolution_source` and not `current_probability`;
2. the `> 0` filter drops the two 0.0 rungs;
3. the `americanfootball` floor of 5 drops `Over 3.5`;
4. **`_enforce_monotonicity` walks ascending and caps every rung above the stuck
   `7.5` down to it** — six correct settled verdicts rewritten to 0.5.

**One stale rung launders six.** The coherence guard is what destroys the
settled answer: the pass that exists to catch an incoherent ladder instead
erased the rows that were right.

## 🔴 Why the fix is not "make every rail snap its price"

Measured over seven days on production: **21,446 of 21,524** `game_score` grades
and **452,988 of 651,130** `clean_resolution` grades carry an unsnapped price;
only `api_settlement` mostly snaps (8.2% unsnapped). A verdict is not a price
and the writers have never treated it as one, so the serving layer is where a
settled rung must stop quoting a leftover.

Population at the time of writing: **90 resolved ladders** on events completed in
the trailing week hold both a `0.5` and a `1.0` leg — the exact capping
condition, stated as an upper bound.

## 🔴 The distinction every test below runs in BOTH directions

The snap is keyed on **authority tier ≥ 2** (`resolution_authority.py`), never
on `resolution_source IS NOT NULL`. `test_a_settled_leg_takes_no_live_price_5411`
exists because a guard keyed on the looser test freezes the rows that most need
to move: both live US Open women's finalists carried `ungradeable_result` — tier
1, a RETRACTION — while their prices were a perfect live pair. A change that
refuses everything is as wrong as no change at all, and only the pair tells them
apart. Every class below therefore has its negative twin: a live ladder is still
capped, a tier-1 row still serves its price, an Under that won lands at 0.0 and
not at 1.0.

## Why the real endpoint

`_enforce_monotonicity` is a closure inside a 900-line builder; asserting on it
directly would prove nothing about what a reader is served. These tests drive
the real `_build_game_markets` against a doubled session — the rig
`test_a_game_market_row_carries_its_own_price_age_4970.py` establishes — so the
subject is the payload, through classification, dedup, the sport-range guard and
the monotonicity pass in the order production runs them.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes import events as events_route
from app.routes.events import _game_markets_cache
from app.utils.resolution_authority import (
    AUTHORITATIVE_SOURCES,
    DETERMINISTIC_SOURCES,
    TERMINAL_SOURCES,
    authority_tier,
)

NOW = datetime(2026, 9, 14, 3, 40, tzinfo=timezone.utc)
KICKOFF = datetime(2026, 9, 14, 0, 20, tzinfo=timezone.utc)
FINAL_AT = datetime(2026, 9, 14, 3, 28, tzinfo=timezone.utc)

#: The production ladder, verbatim (market 60075100, read 2026-09-14 14:45Z).
#: `(threshold, current_probability, is_winner, resolution_source)`.
SPECIMEN_LADDER = (
    (3.5, 1.0, True, "api_settlement"),
    (7.5, 0.5, True, "game_score"),          # the stale rung that launders six
    (10.5, 1.0, True, "api_settlement"),
    (14.5, 1.0, True, "api_settlement"),
    (17.5, 1.0, True, "api_settlement"),
    (20.5, 1.0, True, "api_settlement"),
    (21.5, 1.0, True, "api_settlement"),
    (24.5, 1.0, True, "api_settlement"),
    (28.5, 0.0, False, "api_settlement"),
    (31.5, 0.0, False, "api_settlement"),
    (38.5, 0.5, False, "game_score"),        # a settled LOSER at a coin flip
)

#: What production served for this ladder before the change: eight rungs, all
#: 0.5. Held as data so the "before" stays quotable after the defect is gone.
SERVED_BEFORE = {7.5: 0.5, 10.5: 0.5, 14.5: 0.5, 17.5: 0.5,
                 20.5: 0.5, 21.5: 0.5, 24.5: 0.5, 38.5: 0.5}


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


def _market(*, id=601, name="DAL Cowboys vs NY Giants: 2nd Half Total",
            external_id="KXNFL2HTOTAL-26SEP13DALNYG", status="resolved"):
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
    event.period, event.game_clock = ("Final", None) if status == "completed" else ("3rd Quarter", "6:32")
    return event


def _ladder_outcomes(ladder, *, market_id=601, label="2H points scored"):
    return [
        _outcome(
            id=700 + i,
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


class TestTheSettledLadderReadsAsSettled:
    def test_the_production_specimen_no_longer_serves_seven_cleared_lines_at_fifty(self):
        """🔴 The required regression, on the measured ladder verbatim."""
        rungs = _half_total_rungs(
            _payload([_market()], _ladder_outcomes(SPECIMEN_LADDER))
        )

        assert set(rungs) >= {7.5, 10.5, 14.5, 17.5, 20.5, 21.5, 24.5}, (
            f"fixture did not build the specimen ladder: {sorted(rungs)}"
        )
        coin_flips = {t: r["over_probability"] for t, r in rungs.items()
                      if r["over_probability"] == 0.5}
        assert coin_flips == {}, (
            f"cleared lines still served as a coin flip: {coin_flips} "
            f"(production served {SERVED_BEFORE})"
        )
        for threshold in (7.5, 10.5, 14.5, 17.5, 20.5, 21.5, 24.5):
            assert rungs[threshold]["over_probability"] == 1.0, (
                f"Over {threshold} cleared and is served "
                f"{rungs[threshold]['over_probability']}"
            )

    def test_the_stale_rung_is_the_one_that_was_never_snapped_and_it_is_repaired_here(self):
        """`game_score` wrote the verdict and not the price — tier 2 is enough.

        This is the rung the whole cascade hangs off: if the fix only covered
        tier 3, `Over 7.5` would still serve 0.5 and the card would print one
        coin flip beside six certainties.
        """
        rungs = _half_total_rungs(
            _payload([_market()], _ladder_outcomes(SPECIMEN_LADDER))
        )
        stale = rungs[7.5]
        assert stale["resolution_source"] == "game_score"
        assert authority_tier("game_score") == 2
        assert stale["over_probability"] == 1.0
        assert stale["is_winner"] is True

    def test_no_settled_rung_is_marked_as_capped_to_a_sibling(self):
        """The payload's own witness. Production carried this mark on all six."""
        rungs = _half_total_rungs(
            _payload([_market()], _ladder_outcomes(SPECIMEN_LADDER))
        )
        capped = {t: r for t, r in rungs.items()
                  if r.get("observed_at_basis") == "capped_to_sibling"}
        assert capped == {}, f"a verdict was rewritten to a sibling's price: {sorted(capped)}"

    def test_a_settled_loser_stops_being_a_coin_flip(self):
        """`Over 38.5` lost and was served 50%.

        It leaves the ladder rather than printing "0%", which is what the two
        `api_settlement` losers at 0.0 already do — the `> 0` filter is
        untouched by this change, so the served population of a settled ladder
        is decided by one rule for all of its rungs instead of by which rail
        happened to snap the price.
        """
        rungs = _half_total_rungs(
            _payload([_market()], _ladder_outcomes(SPECIMEN_LADDER))
        )
        assert 38.5 not in rungs, (
            f"a line the game did not clear is still priced: {rungs.get(38.5)}"
        )
        assert 28.5 not in rungs and 31.5 not in rungs, "the 0.0 rungs changed behaviour"


# ─────────────────────────────────────────────────────────────────────────────
# THE OTHER DIRECTION — a change that refuses everything is not a fix
# ─────────────────────────────────────────────────────────────────────────────


class TestNothingThatIsStillAQuestionIsTouched:
    def test_a_live_ladder_is_still_capped_exactly_as_before(self):
        """🔴 The anti-strawman. Without this, deleting the monotonicity pass
        outright passes every test above.

        Thinly traded rungs on a live game: P(Over 17.5) may not exceed
        P(Over 10.5), so the 0.72 is rewritten to 0.60 and marked.
        """
        live_ladder = (
            (10.5, 0.60, None, None),
            (17.5, 0.72, None, None),
        )
        rungs = _half_total_rungs(
            _payload(
                [_market(status="open")],
                _ladder_outcomes(live_ladder),
                event=_event(status="live"),
            )
        )
        assert set(rungs) == {10.5, 17.5}, f"fixture built {sorted(rungs)}"
        assert rungs[17.5]["over_probability"] == 0.60, "the cap did not fire"
        assert rungs[17.5]["observed_at_basis"] == "capped_to_sibling"
        assert rungs[10.5]["over_probability"] == 0.60
        assert "observed_at_basis" not in rungs[10.5]

    def test_a_retraction_is_not_a_verdict_and_keeps_its_live_price(self):
        """🔴 The #5411 distinction, on this rail.

        `ungradeable_result` is tier 1 — the venue never declared a side, and the
        row is explicitly reversible by evidence. Snapping it would publish a
        certainty nobody asserted, and capping it is still the ordinary price
        behaviour because a price is all it has.
        """
        assert "ungradeable_result" in TERMINAL_SOURCES
        assert authority_tier("ungradeable_result") < 2

        retracted = (
            (10.5, 0.60, False, "ungradeable_result"),
            (17.5, 0.72, True, "ungradeable_result"),
        )
        rungs = _half_total_rungs(
            _payload([_market()], _ladder_outcomes(retracted))
        )
        assert set(rungs) == {10.5, 17.5}, f"fixture built {sorted(rungs)}"
        assert rungs[10.5]["over_probability"] == 0.60, "a retraction was snapped to a verdict"
        assert rungs[17.5]["over_probability"] == 0.60, "a retraction escaped the cap"

    def test_a_guess_is_not_a_verdict(self):
        """Tier 0 is the poison class (#754). It may not become a certainty by
        travelling through the serving layer."""
        guessed = (
            (10.5, 0.60, False, "pass2_guess"),
            (17.5, 0.72, True, "multi_max_prob"),
        )
        rungs = _half_total_rungs(_payload([_market()], _ladder_outcomes(guessed)))
        assert rungs[10.5]["over_probability"] == 0.60
        assert rungs[17.5]["over_probability"] == 0.60

    def test_an_ungraded_row_on_a_resolved_market_is_not_read_as_a_loss(self):
        """The 6,032-row measurement in `_settled_grade_fields`'s docstring.

        `is_winner` defaults to `False` in Postgres, so an ungraded rung on a
        resolved market arrives here looking exactly like a loser. It carries no
        `resolution_source`, which is the whole gate — and what it must NOT do
        is become a published 0%.

        On a finished game #1588's closed-window rule gets there first and
        withholds it outright, which is the stronger answer and is the reason
        this reads as an absence rather than as a price: the two rules agree,
        and neither of them invents a verdict. The graded rung beside it is
        served, so this is not the whole ladder vanishing.
        """
        mixed = (
            (10.5, 1.0, True, "api_settlement"),
            (17.5, 0.44, False, None),   # the column DEFAULT, not a verdict
        )
        rungs = _half_total_rungs(_payload([_market()], _ladder_outcomes(mixed)))
        assert rungs[10.5]["over_probability"] == 1.0, "the graded rung should survive"
        assert 17.5 not in rungs, (
            f"an ungraded rung reached the reader: {rungs.get(17.5)}"
        )

    def test_an_ungraded_row_while_the_window_is_still_open_keeps_its_own_price(self):
        """The other side of the rule above — a live 2H line is still a question.

        Without this pair, "withhold every row with no verdict" passes the test
        above and empties every live period card on the site.
        """
        live_ladder = (
            (10.5, 0.44, None, None),
            (17.5, 0.31, None, None),
        )
        rungs = _half_total_rungs(
            _payload(
                [_market(status="open")],
                _ladder_outcomes(live_ladder),
                event=_event(status="live"),
            )
        )
        assert rungs[10.5]["over_probability"] == 0.44
        assert rungs[17.5]["over_probability"] == 0.31
        assert rungs[10.5]["is_winner"] is None, "an ungraded row published a verdict"


class TestOneUngradedNeighbourCannotUndoTheWholeRepair:
    """🔴 Why the snap alone is not the fix.

    The snap makes a fully-graded ladder monotone, so on the specimen the cap
    never fires again and the second half of this change looks redundant. It is
    not: `_enforce_monotonicity` runs ~400 lines BEFORE #1588's closed-window
    rule, so a rung that will never reach the reader is still standing when the
    cap is computed and can hand its price to every settled rung above it. The
    settled rows then keep that price and the donor disappears, leaving a page
    whose wrong number has no visible source at all.
    """

    def test_an_ungraded_rung_cannot_cap_the_settled_rung_above_it(self):
        ladder = (
            (10.5, 0.60, None, None),                  # dropped LATER, by #1588
            (17.5, 1.0, True, "api_settlement"),
        )
        rungs = _half_total_rungs(_payload([_market()], _ladder_outcomes(ladder)))
        assert 10.5 not in rungs, "fixture: the ungraded donor should be withheld"
        assert rungs[17.5]["over_probability"] == 1.0, (
            "a cleared line was capped to the price of a rung the reader never sees"
        )
        assert "observed_at_basis" not in rungs[17.5]

    def test_a_retracted_rung_cannot_cap_the_settled_rung_above_it(self):
        """The same shape with BOTH rows visible.

        `ungradeable_result` carries a `resolution_source`, so it survives
        #1588 and is served at its own live price — and it still may not
        rewrite the venue's settlement above it. The ladder ends up
        non-monotone on the page, which is the honest reading: one rung is a
        price, the other is a result, and they are not comparable.
        """
        ladder = (
            (10.5, 0.60, False, "ungradeable_result"),
            (17.5, 1.0, True, "api_settlement"),
        )
        rungs = _half_total_rungs(_payload([_market()], _ladder_outcomes(ladder)))
        assert set(rungs) == {10.5, 17.5}, f"fixture built {sorted(rungs)}"
        assert rungs[10.5]["over_probability"] == 0.60
        assert rungs[17.5]["over_probability"] == 1.0, (
            "a retraction overwrote a venue settlement"
        )
        assert "observed_at_basis" not in rungs[17.5]

    def test_the_settled_rung_still_donates_to_the_rungs_above_it(self):
        """The guard refuses the REWRITE of a verdict, not the pass itself.

        A settled rung stays the ceiling, so an ungraded rung above it is capped
        exactly as before — without this, "skip settled rows" could quietly mean
        "restart the ladder", and a live rung above a settled one would escape.
        """
        ladder = (
            (10.5, 1.0, True, "api_settlement"),
            (17.5, 0.60, False, "ungradeable_result"),
            (24.5, 0.90, False, "ungradeable_result"),
        )
        rungs = _half_total_rungs(_payload([_market()], _ladder_outcomes(ladder)))
        assert rungs[10.5]["over_probability"] == 1.0
        assert rungs[17.5]["over_probability"] == 0.60
        assert rungs[24.5]["over_probability"] == 0.60, "the cap stopped working"
        assert rungs[24.5]["observed_at_basis"] == "capped_to_sibling"


class TestTheAxisIsTheRowsOwn:
    def test_an_under_leg_that_won_is_an_over_that_did_not_happen(self):
        """🔴 The inversion, and getting it wrong prints the opposite answer.

        These rows are normalised onto the OVER axis before they are served, so
        a winning `Under 45.5` must land at 0.0 — and therefore leave the ladder
        — rather than at the 1.0 its own `is_winner` says.
        """
        market = _market(id=602, name="DAL Cowboys vs NY Giants: 2nd Half Total")
        outcomes = [
            _outcome(id=810, market_id=602, name="Under 45.5 2H points scored",
                     prob=0.97, is_winner=True, resolution_source="api_settlement"),
            _outcome(id=811, market_id=602, name="Over 10.5 2H points scored",
                     prob=1.0, is_winner=True, resolution_source="api_settlement"),
        ]
        rungs = _half_total_rungs(_payload([market], outcomes))

        assert 45.5 not in rungs, (
            "a winning UNDER was published as a certain OVER: "
            f"{rungs.get(45.5, {}).get('over_probability')}"
        )
        assert rungs[10.5]["over_probability"] == 1.0

    def test_a_losing_under_becomes_a_certain_over_when_its_market_produced_a_winner(self):
        """The same inversion in the direction that KEEPS a row, so the test
        above cannot be satisfied by dropping every Under.

        🔴 THE WINNING SIBLING IS PART OF THE FIXTURE, NOT DECORATION. An
        earlier draft of this test graded the Under a loser and gave the market
        no winner at all — which is the shape of a VOID, not of a settlement,
        and pinning 1.0 on it is what shipped a fabricated certainty to a live
        page. See `test_a_voided_market_keeps_its_price` below: these two are
        one rule read from both sides.
        """
        market = _market(id=603)
        outcomes = [
            _outcome(id=820, market_id=603, name="Under 10.5 2H points scored",
                     prob=0.03, is_winner=False, resolution_source="api_settlement"),
            _outcome(id=821, market_id=603, name="Over 10.5 2H points scored",
                     prob=0.97, is_winner=True, resolution_source="api_settlement"),
        ]
        rungs = _half_total_rungs(_payload([market], outcomes))
        assert rungs[10.5]["over_probability"] == 1.0


class TestAVoidedMarketDecidesNothing:
    """🔴 A graded LOSS is only evidence about the other side if something WON.

    Production, 2026-09-14, trailing 14 days: 389 markets across 163 events
    carry two or more tier-2+ graded losers and ZERO winners — NCAAF 46, NFL 41,
    MLB 40, esports 37, WTA 36, ATP 30, MLS 26. The live specimen was
    `/events/15311870` (Jeanjean v Quevedo): all 45 legs `is_winner=False`,
    `clob_authoritative`, every price exactly `0.500000`. Inverting those losing
    Unders printed `Over 21.5 / 22.5 / 23.5 — 100%` for a match nobody won.
    """

    def test_a_voided_market_keeps_its_price(self):
        """Both legs graded losers at tier 3: the venue refunded, so the page
        may not claim either side happened."""
        market = _market(id=604)
        outcomes = [
            _outcome(id=830, market_id=604, name="Under 10.5 2H points scored",
                     prob=0.5, is_winner=False, resolution_source="clob_authoritative"),
            _outcome(id=831, market_id=604, name="Over 10.5 2H points scored",
                     prob=0.5, is_winner=False, resolution_source="clob_authoritative"),
        ]
        rungs = _half_total_rungs(_payload([market], outcomes))
        assert rungs[10.5]["over_probability"] == 0.5, (
            "a voided market was served as a certainty: "
            f"{rungs[10.5]['over_probability']}"
        )

    def test_a_lone_losing_leg_with_no_winner_anywhere_keeps_its_price(self):
        """The one-sided form of the same void — the shape the original test
        mistook for a settlement."""
        market = _market(id=605)
        outcomes = [
            _outcome(id=840, market_id=605, name="Under 10.5 2H points scored",
                     prob=0.03, is_winner=False, resolution_source="api_settlement"),
        ]
        rungs = _half_total_rungs(_payload([market], outcomes))
        assert rungs[10.5]["over_probability"] == 0.97

    def test_a_voided_rung_is_still_capped_by_the_monotonicity_pass(self):
        """The exemption is for VERDICTS. A void carries no verdict, so it goes
        back to being an ordinary price and the coherence rule still owns it —
        otherwise the repair would quietly widen #6169's exemption to a
        population it was never argued for.
        """
        market = _market(id=606, name="DAL Cowboys vs NY Giants: 2nd Half Total")
        outcomes = [
            _outcome(id=850, market_id=606, name="Over 10.5 2H points scored",
                     prob=0.40, is_winner=False, resolution_source="clob_authoritative"),
            _outcome(id=851, market_id=606, name="Over 24.5 2H points scored",
                     prob=0.60, is_winner=False, resolution_source="clob_authoritative"),
        ]
        rungs = _half_total_rungs(_payload([market], outcomes))
        assert rungs[24.5]["over_probability"] == 0.40
        assert rungs[24.5]["observed_at_basis"] == "capped_to_sibling"

    def test_a_market_that_produced_a_winner_still_snaps_its_losers(self):
        """The reverse population, so the repair cannot be satisfied by simply
        refusing to serve every loss."""
        market = _market(id=607, name="DAL Cowboys vs NY Giants: 2nd Half Total")
        outcomes = [
            _outcome(id=860, market_id=607, name="Over 10.5 2H points scored",
                     prob=0.5, is_winner=True, resolution_source="game_score"),
            _outcome(id=861, market_id=607, name="Over 24.5 2H points scored",
                     prob=0.5, is_winner=False, resolution_source="game_score"),
        ]
        rungs = _half_total_rungs(_payload([market], outcomes))
        assert rungs[10.5]["over_probability"] == 1.0
        assert 24.5 not in rungs, "a graded loser must leave the ladder at 0.0"


class TestTheTierBoundaryIsTheDocumentedOne:
    def test_every_tier_three_and_tier_two_source_snaps_and_no_other_does(self):
        """The rule stated over the vocabulary rather than over two examples, so
        a source added to a tier later inherits the behaviour its tier means."""
        from app.routes.events import _row_is_graded_at_verdict_tier

        for source in AUTHORITATIVE_SOURCES | DETERMINISTIC_SOURCES:
            assert _row_is_graded_at_verdict_tier(
                {"is_winner": True, "resolution_source": source}
            ), f"{source} is a cited grade and must be served as one"

        for source in TERMINAL_SOURCES:
            assert not _row_is_graded_at_verdict_tier(
                {"is_winner": True, "resolution_source": source}
            ), f"{source} is terminal/soft and must keep its price"

    def test_the_row_shape_the_other_families_use_is_not_mistaken_for_a_verdict(self):
        """Prop rows reach the same pass carrying a raw `is_winner` with no
        source (`_grade_settled_prop` passes the column through). The tier test
        is what keeps them out — without it every ungraded prop on a finished
        page becomes a certainty."""
        from app.routes.events import _row_is_graded_at_verdict_tier

        assert not _row_is_graded_at_verdict_tier({"is_winner": False})
        assert not _row_is_graded_at_verdict_tier({"is_winner": True})
        assert not _row_is_graded_at_verdict_tier({})
        assert not _row_is_graded_at_verdict_tier(
            {"is_winner": None, "resolution_source": "api_settlement"}
        )
