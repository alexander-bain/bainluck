"""#7582: a futures leg the venue will not quote stops printing its fossil price.

WHAT A READER SAW, measured on production 2026-09-22 08:3xZ — sixteen days after
the issue was filed, unchanged, and still the second and third favourites on the
board. ``/futures/3971707`` (*Super League Rugby Championship*):

    Hull Kingston Rovers   33.0%   on a stored book of 0.1900 / 0.4700
    Wigan Warriors         29.5%   on a stored book of 0.1900 / 0.4000

Kalshi's own answer for ``KXSLRCHAMP-26-HKR``, same morning, is
``yes_bid 0.0000 / yes_ask 0.9600 / last_price 0.0000`` — an empty book. Eleven
of the board's fourteen legs were frozen at ``2026-09-06 05:46:08.358811``, all
eleven at that single microsecond, while three siblings were rewritten at
``05:51:52`` that same morning. A poll pass stamps every row it touches with one
``now``, which is what makes that column readable as a pass at all — so eleven
rows sharing one microsecond a fortnight old is one pass, long gone.

THE MECHANISM, AND WHY EVERY EVIDENCE RULE ALREADY SHIPPED ACQUITS IT.
``_fetch_kalshi_prices`` dropped an unpriceable market with a bare ``continue``,
so ``_write_prices`` never saw the ticker and left BOTH the stored price and the
stored ``last_updated`` where the last pass that could price them put them. The
row is then a fossil in which ``yes_bid``, ``yes_ask``, ``last_price`` and the
probability are all frozen TOGETHER, so every screen that screens an unsupported
price reads a healthy two-sided book and spares it. ``price_is_unsupported``
spares Hull KR for exactly this reason. Nothing shipped asked whether the
evidence was CURRENT.

THE GAME POLLER HAS HAD THIS RULE SINCE #4356 (``_clear_outcome_price``); the
futures path never did, and that asymmetry is the whole issue.

═══ 🔴 WHAT THESE TESTS CAN AND CANNOT PROVE, STATED UP FRONT ═══

The clear's five safety conditions live in the UPDATE's WHERE clause, and
``_WriteSession`` — the fake every sibling test in this module uses — returns
``rowcount=1`` for any statement without evaluating anything. **A behavioural
assertion on that fake is therefore VACUOUS for all five**: it passes whether or
not the conditions are in the statement. Pretending otherwise would be worse
than not testing them, because the file would read as covering them.

So this file is split, and the split is labelled:

* ``TestTheClearFires`` / ``TestTheClearIsGatedOnAPricedSibling`` — real control
  flow, decided in Python, which the fake CAN answer. The outage gate is here and
  it is the load-bearing one.
* ``TestTheConditionsAreInTheStatement`` — the five conditions and the seven
  written columns, pinned on the COMPILED SQL. This proves the predicate is
  present and correct, not that Postgres applies it; Postgres applying a WHERE is
  not ours to test. ``test_the_compiled_read_can_fail`` is the control that keeps
  this half from being satisfied by a substring that is always there.
* ``TestTheGraceIsTheSharedConstant`` — the seven-day bound is #7537's
  ``OBSERVATION_LAG_DAYS``, read from the bind parameter the statement actually
  carries, so a local literal cannot drift away from the serve-time rule a reader
  meets on the same board.

═══ WHY THE OUTAGE GATE IS THE ONE TO SEVER FIRST ═══

Codex ruled on 2026-09-20, on #7537, that an old snapshot is not by itself proof
a venue stopped quoting: a leg last written days ago "is equally compatible with
a still-quoted leg whose ingestion has failed". The clear answers that by firing
only on a board where THIS pass priced at least one sibling — a SPLIT within one
pass, which is evidence about the legs rather than about us. Sever that gate and
a bad afternoon at our end blanks boards fleet-wide; it is the difference between
this arm and a wall-clock rule, so it gets the most direct test in the file.

═══ THE POPULATION, measured 2026-09-22 08:4xZ ═══

Over open tier-1/2 boards whose newest leg stamp is inside 24h (i.e. boards the
poller demonstrably still visits), legs more than ``OBSERVATION_LAG_DAYS``
behind their own board's newest stamp:

    fossil legs                      9,039   on 1,147 boards
      still carrying a price         2,746
        blocked: is_winner TRUE        329
        blocked: calibration line      881
        blocked: api_settlement      1,975
      passing all three conditions     684

The three safety conditions block 3,185 rows between them. They are not
belt-and-braces; they are most of the population.

🔴 BUT 684 IS NOT THIS SHIP'S REACH, and the difference is the scoping. The
flag is set in ``_fetch_kalshi_prices`` and nowhere else, so only the Kalshi
half is reachable:

    kalshi      250   on 59 boards    (129 at >= 20%, 56 at >= 99%)  <- this ship
    polymarket  434   on 190 boards   (329 at >= 20%)                <- NOT this ship

And 250 is an UPPER bound even for Kalshi: a leg reaches the clear only if the
venue's quote fails ``_kalshi_yes_probability`` outright (the ``prob is None``
arm). A leg refused one step later by the empty-book guard inside
``_write_prices`` is still a fossil and is still left standing — that guard is
on the SHARED writer, fires for both venues, and is unmeasured for Polymarket,
so it is named as the residual on #7582 rather than widened here.

The measured specimens for the reachable half: board 3971707 (Hull KR 33%,
Wigan 29.5%, eleven legs at one microsecond) and board 109279, *Who will
release a new song this year?*, whose legs for Fred again.., mgk, BLACKPINK,
Khalid, ROSALÍA and others have each read **100%** since April 2026 on a board
repriced this morning.
"""

import inspect
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects import postgresql

from app.tasks import futures_price_refresh as fpr
from app.utils.market_staleness import OBSERVATION_LAG_DAYS
from tests.test_futures_price_refresh_counts_declines_5869 import _Result

#: The measured specimen's two shapes, to the digit, as Kalshi quoted them.
#: Leeds is the sibling that CAN be priced and is what makes the pass a split;
#: Hull KR is the leg the venue lists ``active`` and will not quote.
def _leeds():
    return {
        "external_id": "KXSLRCHAMP-26-LEE",
        "probability": 0.305,
        "yes_bid": 0.25,
        "yes_ask": 0.36,
        "last_price": 0.30,
    }


def _hull_kr():
    return {
        "external_id": "KXSLRCHAMP-26-HKR",
        "probability": None,
        "venue_quotes_no_price": True,
        "yes_bid": 0.0,
        "yes_ask": 0.96,
        "last_price": 0.0,
    }


class _ClearSession:
    """Records the statements ``_write_prices`` issues, and answers nothing.

    Deliberately NOT a row store. See the file docstring: a fake that answered a
    WHERE would be a second implementation of the predicate under test, and the
    assertions it satisfied would be assertions about the fake.
    """

    def __init__(self, rows):
        self.rows = list(rows)
        self.updates = []
        self.inserts = 0

    async def execute(self, statement, params=None):
        sql = str(statement).lstrip().upper()
        if sql.startswith("SELECT ID, EXTERNAL_ID FROM FUTURES_OUTCOMES"):
            return _Result(self.rows)
        if sql.startswith("INSERT INTO FUTURES_ODDS_SNAPSHOTS"):
            self.inserts += 1
        elif sql.startswith("UPDATE FUTURES_OUTCOMES"):
            self.updates.append(statement)
        return _Result(rowcount=1)

    def clears(self):
        """The UPDATEs that are clears — the ones carrying the guard clause.

        Selected on ``calibration_probability``, which appears in this module's
        WHERE clauses nowhere else, so a price write can never be counted here.
        """
        out = []
        for st in self.updates:
            text = str(st.compile(dialect=postgresql.dialect()))
            if "calibration_probability IS NULL" in text:
                out.append(st)
        return out


_BOARD = 3971707
_ROWS = ((11, "KXSLRCHAMP-26-LEE"), (12, "KXSLRCHAMP-26-HKR"))


class TestTheClearFires:
    async def test_the_measured_specimen_has_its_price_taken_down(self):
        session = _ClearSession(_ROWS)
        stats: dict = {}
        written = await fpr._write_prices(
            session, _BOARD, "kalshi", [_leeds(), _hull_kr()], stats
        )
        assert written == 1, "the priced sibling must still be written"
        assert len(session.clears()) == 1
        assert stats["legs_cleared_venue_unpriced"] == 1

    async def test_no_snapshot_is_written_for_a_cleared_leg(self):
        """``futures_odds_snapshots`` records observed PRICES.

        There is no price here, and a NULL-probability row would land in
        calibration's input. The game poller's clear writes none either.
        """
        session = _ClearSession(_ROWS)
        written = await fpr._write_prices(
            session, _BOARD, "kalshi", [_leeds(), _hull_kr()], {}
        )
        assert written == 1
        assert session.inserts == 1, "exactly one snapshot — Leeds', not Hull KR's"

    def test_the_counter_is_initialised_so_a_quiet_pass_reports_a_zero(self):
        """Gotcha #53: "we looked and cleared nothing" must not read as "we never
        looked".

        Asserted against the stats block of the task itself, not the whole
        module, so the literal this reads cannot be satisfied by the sentence in
        a comment somewhere else in a 3,300-line file.
        """
        block = inspect.getsource(fpr._refresh_stale_futures_prices)
        assert '"legs_cleared_venue_unpriced": 0' in block


class TestTheClearIsGatedOnAPricedSibling:
    """🔴 The safety argument. Sever this and our own outage blanks the board."""

    async def test_a_board_this_pass_could_not_price_at_all_is_left_alone(self):
        session = _ClearSession(_ROWS)
        stats: dict = {}
        written = await fpr._write_prices(
            session,
            _BOARD,
            "kalshi",
            [_hull_kr(), dict(_hull_kr(), external_id="KXSLRCHAMP-26-LEE")],
            stats,
        )
        assert written == 0
        assert session.clears() == [], (
            "with no sibling priced this pass the split is not evidence about "
            "the legs — it is compatible with our own ingestion failing"
        )
        assert stats.get("legs_cleared_venue_unpriced", 0) == 0

    async def test_the_control_one_priced_sibling_is_enough(self):
        """Without this the assertion above is satisfied by a clear that never
        fires at all."""
        session = _ClearSession(_ROWS)
        stats: dict = {}
        await fpr._write_prices(
            session, _BOARD, "kalshi", [_leeds(), _hull_kr()], stats
        )
        assert stats["legs_cleared_venue_unpriced"] == 1


class TestTheFetchSeparatesSilenceFromSettlement:
    """The two ``continue``s in ``_fetch_kalshi_prices`` must never merge.

    A settled leg's quote is a settlement artifact and its price is a RESULT,
    which "settled means settled" keeps on the page. An unquoted leg is the
    venue saying nothing. Asserted on the source of the one function that
    produces the flag, because the distinction is a branch and not a value.
    """

    def test_the_answered_leg_is_not_flagged_unpriceable(self):
        source = inspect.getsource(fpr._fetch_kalshi_prices)
        answered = source.index("venue_answered(market.result)")
        flag = source.index('"venue_quotes_no_price": True')
        between = source[answered:flag]
        assert "_kalshi_yes_probability" in between, (
            "the unpriceable branch must sit AFTER the answered-leg branch, so a "
            "settled leg returns before it can be flagged"
        )

    def test_polymarket_cannot_reach_the_clear(self):
        """``_write_prices`` is shared by both venues; the flag is Kalshi's only.

        Scoped to this ship deliberately. The empty-book decline inside
        ``_write_prices`` creates fossils by the same mechanism and is named as
        the residual on #7582, but it fires for BOTH venues and was not measured
        for Polymarket, so widening it is a separately-sized change.
        """
        assert "venue_quotes_no_price" not in inspect.getsource(
            fpr._fetch_polymarket_prices
        )

    async def test_an_unflagged_none_price_is_still_a_decline_not_a_clear(self):
        """The pre-existing ``prob is None`` refusal in the writer is untouched:
        it counts and leaves the row alone. Only the FLAG authorises a clear."""
        session = _ClearSession(_ROWS)
        stats: dict = {}
        await fpr._write_prices(
            session,
            _BOARD,
            "kalshi",
            [_leeds(), {"external_id": "KXSLRCHAMP-26-HKR", "probability": None}],
            stats,
        )
        assert stats["legs_declined_out_of_range"] == 1
        assert session.clears() == []
        assert stats.get("legs_cleared_venue_unpriced", 0) == 0


async def _compiled_clear():
    session = _ClearSession(_ROWS)
    await fpr._write_prices(session, _BOARD, "kalshi", [_leeds(), _hull_kr()], {})
    (clear,) = session.clears()
    return clear.compile(dialect=postgresql.dialect())


class TestTheConditionsAreInTheStatement:
    """Pinned on the compiled SQL. See the file docstring for why not on a fake.

    Each condition names the sibling condition in ``_clear_outcome_price`` it
    reproduces, so the two rules cannot drift into being different rules.
    """

    @pytest.mark.parametrize(
        "clause,why",
        [
            (
                "futures_outcomes.current_probability IS NOT NULL",
                "idempotent — a cleared leg is not restamped every hour, and "
                "`routes/playoffs.py` reads `last_updated` as a liveness gate",
            ),
            (
                "futures_outcomes.calibration_probability IS NULL",
                "never wipe a captured closing line — calibration's evidence, "
                "and the one condition ELIGIBLE_OUTCOMES_SQL does NOT apply",
            ),
            (
                "futures_outcomes.is_winner IS NOT true",
                "never un-price a crowned row (gotcha #21)",
            ),
            (
                "futures_outcomes.resolution_source IS DISTINCT FROM",
                "#5246's half — a leg the venue resolved NO carries "
                "is_winner = FALSE and sails through the crown test",
            ),
            (
                "futures_outcomes.last_updated <",
                "the grace: a leg keeps its last price for OBSERVATION_LAG_DAYS",
            ),
        ],
    )
    async def test_the_where_clause_carries(self, clause, why):
        assert clause in str(await _compiled_clear()), why

    @pytest.mark.parametrize(
        "column",
        [
            "current_probability",
            "current_american_odds",
            "current_yes_bid",
            "current_yes_ask",
            "probability_change_24h",
        ],
    )
    async def test_every_price_column_is_taken_down_together(self, column):
        """A fossil is frozen across ALL of these at once, which is why each
        one acquits it on its own. Leaving any behind leaves a screen a reason
        to believe the row."""
        assert f"{column}=%({column})s" in str(await _compiled_clear())

    async def test_both_stamps_are_written(self):
        sql = str(await _compiled_clear())
        assert "last_updated=now()" in sql
        assert "price_changed_at=CASE WHEN" in sql, (
            "a price going away IS a change — and the ordinary move in this same "
            "file stamps, so an unstamped clear would be the only unstamped write"
        )

    async def test_the_compiled_read_can_fail(self):
        """The control for this whole class. Without it every assertion above is
        satisfied by a substring that is present in any UPDATE."""
        sql = str(await _compiled_clear())
        assert "futures_outcomes.market_tier" not in sql
        assert "is_winner IS true" not in sql


class TestTheGraceIsTheSharedConstant:
    async def test_the_bound_is_observation_lag_days_and_not_a_local_literal(self):
        """#7537's constant, read off the bind parameter the statement carries.

        The serve-time rule a reader meets on this same board withholds the leg
        at ``OBSERVATION_LAG_DAYS``; the writer takes it down at the same bound.
        Two numbers for one question is how a board starts disagreeing with
        itself — and this one governs a WITHHOLD, so the constant was chosen at
        the far end of its plateau for margin. A literal here could drift off it
        silently.
        """
        compiled = await _compiled_clear()
        floor = compiled.params["last_updated_1"]
        lag = datetime.now(timezone.utc) - floor
        assert abs(lag - timedelta(days=OBSERVATION_LAG_DAYS)) < timedelta(minutes=5)

    def test_the_module_reads_the_constant_by_name(self):
        assert "OBSERVATION_LAG_DAYS" in inspect.getsource(fpr._write_prices)
