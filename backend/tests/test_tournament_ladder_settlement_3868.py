"""#3868 — a tournament ladder stops offering odds on a round already played.

THE DEFECT, AS THE READER MET IT
--------------------------------
`/sport/tennis/atp`, 2026-09-07, phone width. The card "US OPEN 2026: TO REACH
QUARTERFINALS (MEN'S SINGLES)" read:

    Carlos Alcaraz   78%      Novak Djokovic  58%

Alcaraz was already IN that quarterfinal — the same page's own FINISHED list
showed him beating Tommy Paul — and Djokovic was out of it. Polymarket had
settled both legs: `GET /events/910151`, 39 of 44 children `closed=true`,
Alcaraz `["1","0"]`, Djokovic `["0","1"]`.

TWO CAUSES, ONE RAIL, AND THE SECOND ONE IS THE INTERESTING ONE
---------------------------------------------------------------
**(a) The rail could not see a result.** `get_markets_by_conditions` applies a
`closed=false` filter the caller never asked for, so the instant a leg settled
it stopped being returned at all — it landed in `not_returned`, nothing was
written, and the last LIVE price froze. Djokovic's sub-market leg was refreshed
to 0.470 at 08:50Z and settled at the venue minutes later; 0.470 was the last
thing this rail would ever have written to it.

**(b) The rail could not see the row the page renders.** One Gamma event is
written into this database TWICE: a `polymarket_sub_market` row per child (keyed
`external_id = <condition>`, legs `<condition>_yes` / `<condition>_no`) and a
`polymarket_event` PARENT ladder row (keyed by the Gamma event id, one leg per
child under the BARE `<condition>`). The register pins the sub-markets and the
writer keyed its lookup on the MARKET's external_id, so it reached those and
only those. `/sport/tennis/atp` renders the parent. Measured on production:
sub-market leg refreshed 2026-09-06 22:33Z, ladder leg carrying the SAME
condition last written 2026-08-25 18:17Z. Thirteen days, one condition, two
rows, one writer.

The side-of-book test is the hinge of (b): it read the outcome NAME and skipped
anything that was neither "Yes" nor "No". Every ladder leg is named for a
player, so even a lookup that found those rows would have written none of them.
"""

import contextlib
from datetime import datetime, timezone

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Update
from sqlalchemy.sql.elements import TextClause

# Imported as MODULES, not as names: the last test in this file has to reach
# into `app.tasks.tournament_price_refresh` with monkeypatch, and a file that
# does both `import x` and `from x import y` binds the same module two ways.
import app.services.polymarket_api as poly_api
import app.tasks.tournament_price_refresh as rail
import app.utils.tournament_register as reg

SETTLED_YES_BAR = rail.SETTLED_YES_BAR
SETTLED_NO_BAR = rail.SETTLED_NO_BAR
leg_side = rail.leg_side
settled_yes_probability = rail.settled_yes_probability

CID = "0x3d060eff715e0aa1d15e3758ec37866519686f88c7e0cb0704314d8c844e3e2e"

#: The ladder leg — the row `/sport/tennis/atp` renders. Bare condition id,
#: named for the player. The row that read 78%.
LADDER_ID = 221651252
#: The sub-market legs the register pins and the old lookup could already reach.
SUB_YES_ID, SUB_NO_ID = 221651178, 221651179


def _market(**kw) -> "poly_api.PolymarketMarket":
    defaults = dict(
        condition_id=CID,
        question=(
            "Will Carlos Alcaraz advance to the Quarterfinals in "
            "Men's Singles at the 2026 US Open?"
        ),
        outcomes=["Yes", "No"],
        outcome_prices=[0.775, 0.225],
        best_bid=0.77,
        best_ask=0.78,
        last_trade_price=0.775,
        active=True,
        closed=False,
    )
    defaults.update(kw)
    return poly_api.PolymarketMarket(**defaults)


class _Result:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def all(self):
        return self._rows

    def fetchall(self):
        return self._rows

    def scalar(self):
        return None

    def scalar_one_or_none(self):
        return None

    def first(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return self

    @property
    def rowcount(self):
        return len(self._rows)

    def __iter__(self):
        return iter(self._rows)


class RecordingSession:
    """Answers the writer's two lookups separately, and records every write.

    The split matters: the ORM `select` is the MARKET-keyed lookup that could
    already reach the sub-market legs, and the `text()` one is #3868's
    condition-keyed lookup that reaches the ladder leg. A double that answered
    both with the same rows could not tell the two causes apart.
    """

    def __init__(self, *, market_keyed=(), condition_keyed=()):
        self.statements: list[object] = []
        self._market_keyed = list(market_keyed)
        self._condition_keyed = list(condition_keyed)

    async def execute(self, stmt, *args, **kwargs):
        self.statements.append(stmt)
        if isinstance(stmt, TextClause):
            return _Result(self._condition_keyed)
        if getattr(stmt, "is_select", False):
            return _Result(self._market_keyed)
        return _Result()

    async def commit(self):
        return None

    async def rollback(self):
        return None


def _stats() -> dict:
    return {
        "outcomes_updated": 0,
        "snapshots_written": 0,
        "unpriced": 0,
        "volume_observed": 0,
        "legs_settled": 0,
        "closed_without_result": 0,
        "legs_reached_by_condition": 0,
    }


async def _run(monkeypatch, market, *, market_keyed=(), condition_keyed=()):
    session = RecordingSession(
        market_keyed=market_keyed, condition_keyed=condition_keyed
    )

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    import app.tasks.base as base

    monkeypatch.setattr(base, "get_task_session", _fake_session)

    stats = _stats()
    await rail._write_refreshed_prices(
        [market], stats, now=datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
    )
    return session, stats


def _outcome_writes(session) -> dict[int, dict]:
    """``outcome_id -> bound params`` for every UPDATE of an outcome row."""
    out: dict[int, dict] = {}
    for stmt in session.statements:
        if not isinstance(stmt, Update):
            continue
        table = getattr(stmt, "table", None)
        if table is None or table.name != "futures_outcomes":
            continue
        params = stmt.compile(dialect=postgresql.dialect()).params
        oid = params.get("id_1")
        if oid is not None:
            out[oid] = params
    return out


def _condition_lookup_sql(session) -> str:
    """The text of the condition-keyed lookup, or "" if it was never issued."""
    for stmt in session.statements:
        if isinstance(stmt, TextClause) and "futures_outcomes" in str(stmt):
            return " ".join(str(stmt).split())
    return ""


# ---------------------------------------------------------------------------
# The two pure decisions
# ---------------------------------------------------------------------------


class TestAClosedBookIsAResultNotAPrice:
    """`settled_yes_probability` — the whole settlement decision, in one place."""

    def test_a_closed_yes_settlement_is_one(self):
        assert settled_yes_probability(_market(closed=True, outcome_prices=[1.0, 0.0])) == 1.0

    def test_a_closed_no_settlement_is_zero(self):
        assert settled_yes_probability(_market(closed=True, outcome_prices=[0.0, 1.0])) == 0.0

    def test_an_open_book_is_never_a_settlement(self):
        """However extreme. Alcaraz sat at 0.9995 for a DAY before he settled."""
        assert settled_yes_probability(_market(closed=False, outcome_prices=[0.9995, 0.0005])) is None

    def test_a_closed_book_between_the_bars_names_no_winner(self):
        """Void, mis-settled, or caught mid-settlement — never guessed at.

        Djokovic's leg read 0.470 forty minutes before it closed. If this
        returned a number for the in-between case, a rail that caught a market
        mid-settlement would crown whoever happened to be ahead.
        """
        assert settled_yes_probability(_market(closed=True, outcome_prices=[0.470, 0.530])) is None

    def test_the_bars_are_the_polymarket_sync_rails_own(self):
        """One venue, one settlement test — two rails may not disagree."""
        import inspect

        from app.tasks import polymarket

        src = inspect.getsource(polymarket._sync_polymarket_resolved_status)
        assert f"yes_price >= {SETTLED_YES_BAR}" in src
        assert f"yes_price <= {SETTLED_NO_BAR}" in src

    def test_a_closed_book_with_no_prices_is_not_a_settlement(self):
        assert settled_yes_probability(_market(closed=True, outcome_prices=[])) is None


class TestWhichSideOfTheBookARowIs:
    """`leg_side` — cause (b)'s hinge."""

    def test_a_ladder_leg_named_for_a_player_is_the_yes_side(self):
        """THE REGRESSION. This returned None and the row was skipped."""
        assert leg_side("Carlos Alcaraz", CID, CID) == "yes"

    def test_the_suffixed_legs_keep_resolving(self):
        assert leg_side("Yes", f"{CID}_yes", CID) == "yes"
        assert leg_side("No", f"{CID}_no", CID) == "no"

    def test_the_name_still_answers_when_there_is_no_id(self):
        assert leg_side("Yes", None, CID) == "yes"
        assert leg_side("No", "", CID) == "no"

    def test_a_row_that_names_no_side_is_still_refused(self):
        """Not a licence to write anything: an unrecognisable row is skipped."""
        assert leg_side("Carlos Alcaraz", "some-other-id", CID) is None

    def test_the_no_suffix_is_read_before_the_yes_suffix(self):
        """`…_no` must never fall through to the bare-id arm and read as Yes."""
        assert leg_side("Carlos Alcaraz", f"{CID}_no", CID) == "no"


# ---------------------------------------------------------------------------
# The class guard — acceptance 3 of #3868
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestASettledLegStopsServingAFractionalProbability:

    async def test_a_closed_yes_market_crowns_the_ladder_leg(self, monkeypatch):
        """`closed=true` + `["1","0"]` ⇒ is_winner, 1.0, api_settlement.

        On the LADDER row — the one the page renders — reached only through the
        condition-keyed lookup #3868 added.
        """
        session, stats = await _run(
            monkeypatch,
            _market(closed=True, outcome_prices=[1.0, 0.0]),
            condition_keyed=[(LADDER_ID, "Carlos Alcaraz", CID)],
        )
        writes = _outcome_writes(session)
        assert LADDER_ID in writes, "the ladder leg was never written"
        row = writes[LADDER_ID]
        assert row["current_probability"] == 1.0
        assert row["is_winner"] is True
        assert row["resolution_source"] == "api_settlement"
        assert stats["legs_settled"] == 1

    async def test_a_closed_no_market_zeroes_the_ladder_leg(self, monkeypatch):
        """Djokovic: 58% for a quarterfinal he is out of becomes 0%."""
        session, stats = await _run(
            monkeypatch,
            _market(closed=True, outcome_prices=[0.0, 1.0]),
            condition_keyed=[(LADDER_ID, "Novak Djokovic", CID)],
        )
        row = _outcome_writes(session)[LADDER_ID]
        assert row["current_probability"] == 0.0
        assert row["is_winner"] is False
        assert row["resolution_source"] == "api_settlement"

    async def test_both_copies_of_one_condition_are_written_together(self, monkeypatch):
        """The ladder leg and the sub-market legs stop disagreeing.

        A pass that graded one copy and not the other would leave the page and
        the tournament hub telling a reader two different things about the same
        match, which is the state production was actually in.
        """
        session, stats = await _run(
            monkeypatch,
            _market(closed=True, outcome_prices=[1.0, 0.0]),
            market_keyed=[(SUB_YES_ID, "Yes", f"{CID}_yes"), (SUB_NO_ID, "No", f"{CID}_no")],
            condition_keyed=[(LADDER_ID, "Carlos Alcaraz", CID)],
        )
        writes = _outcome_writes(session)
        assert set(writes) == {LADDER_ID, SUB_YES_ID, SUB_NO_ID}
        assert writes[LADDER_ID]["current_probability"] == 1.0
        assert writes[SUB_YES_ID]["current_probability"] == 1.0
        # The No leg is the complement and loses.
        assert writes[SUB_NO_ID]["current_probability"] == 0.0
        assert writes[SUB_NO_ID]["is_winner"] is False
        assert stats["legs_settled"] == 3

    async def test_the_ladder_leg_is_counted_as_newly_reachable(self, monkeypatch):
        """Zero on a first run would mean #3868's user-visible half never shipped."""
        _session, stats = await _run(
            monkeypatch,
            _market(closed=True, outcome_prices=[1.0, 0.0]),
            market_keyed=[(SUB_YES_ID, "Yes", f"{CID}_yes")],
            condition_keyed=[(LADDER_ID, "Carlos Alcaraz", CID)],
        )
        assert stats["legs_reached_by_condition"] == 1

    async def test_a_row_both_lookups_return_is_written_once(self, monkeypatch):
        """The two lookups overlap by design; the writes must not."""
        session, stats = await _run(
            monkeypatch,
            _market(closed=True, outcome_prices=[1.0, 0.0]),
            market_keyed=[(SUB_YES_ID, "Yes", f"{CID}_yes")],
            condition_keyed=[(SUB_YES_ID, "Yes", f"{CID}_yes")],
        )
        assert stats["legs_settled"] == 1
        assert stats["outcomes_updated"] == 1
        assert stats["legs_reached_by_condition"] == 0
        assert set(_outcome_writes(session)) == {SUB_YES_ID}

    async def test_a_closed_book_naming_no_winner_grades_nothing_and_says_so(
        self, monkeypatch
    ):
        """Caught mid-settlement: no grade, no price, and a counter that shows it."""
        session, stats = await _run(
            monkeypatch,
            _market(closed=True, outcome_prices=[0.470, 0.530]),
            condition_keyed=[(LADDER_ID, "Novak Djokovic", CID)],
        )
        assert _outcome_writes(session) == {}
        assert stats["closed_without_result"] == 1
        assert stats["legs_settled"] == 0

    async def test_an_open_market_is_priced_and_never_graded(self, monkeypatch):
        """The refresh half is unchanged: a live book moves the number only."""
        session, stats = await _run(
            monkeypatch,
            _market(closed=False, outcome_prices=[0.885, 0.115]),
            condition_keyed=[(LADDER_ID, "Alexander Zverev", CID)],
        )
        row = _outcome_writes(session)[LADDER_ID]
        assert row["current_probability"] == pytest.approx(0.885)
        assert "is_winner" not in row
        assert "resolution_source" not in row
        assert stats["legs_settled"] == 0
        assert stats["outcomes_updated"] == 1


@pytest.mark.asyncio
class TestTheConditionKeyedLookupKeepsItsSafetyClauses:
    """What the double CANNOT check, asserted structurally instead.

    🔴 THE LIMIT OF THE DOUBLE ABOVE, STATED RATHER THAN PAPERED OVER. The
    `RecordingSession` answers a `TextClause` by returning canned rows; it does
    not execute the SQL. So a mutation that neuters the predicate — measured:
    splicing `WHERE false --` into it — leaves all nineteen behavioural tests
    green, because they never asked Postgres anything. Deleting the lookup
    outright IS caught (five of them fail), which is the regression that
    actually happens; a predicate rewritten to select nothing is not.

    These read the statement itself, so the three clauses that stop this lookup
    doing harm cannot be dropped in silence. They are the reason a widened
    lookup is safe at all:

    * **`api_settlement`** — a graded row is never re-priced or re-graded. Same
      refusal `_sync_polymarket_resolved_status` makes.
    * **`is_winner IS NOT TRUE`** — CERT-452's per-outcome bound. Never `= FALSE`:
      the column is nullable with `default=False`, so FALSE cannot tell "lost"
      from "nobody has looked".
    * **the duplicate-leg guard** — Q487. A `_yes`/`_no` leg sitting on the SAME
      market as its own bare row is a duplicate and must not be written; our two
      copies are on DIFFERENT markets and both are real.
    """

    async def test_the_lookup_is_issued_at_all(self, monkeypatch):
        session, _stats = await _run(
            monkeypatch,
            _market(),
            condition_keyed=[(LADDER_ID, "Carlos Alcaraz", CID)],
        )
        assert _condition_lookup_sql(session), (
            "no condition-keyed lookup was issued — the ladder copy of every "
            "pinned condition is unreachable again (#3868 cause b)"
        )

    async def test_it_never_touches_a_graded_row(self, monkeypatch):
        session, _stats = await _run(monkeypatch, _market(), condition_keyed=[])
        assert (
            "COALESCE(fo.resolution_source, '') <> 'api_settlement'"
            in _condition_lookup_sql(session)
        )

    async def test_it_keeps_the_cert_452_winner_bound(self, monkeypatch):
        session, _stats = await _run(monkeypatch, _market(), condition_keyed=[])
        sql = _condition_lookup_sql(session)
        assert "fo.is_winner IS NOT TRUE" in sql
        assert "is_winner = FALSE" not in sql.upper().replace("IS NOT TRUE", "")

    async def test_it_keeps_the_q487_duplicate_leg_guard(self, monkeypatch):
        from app.utils.winner_field_coherence import DUPLICATE_CONDITION_LEG_SQL

        session, _stats = await _run(monkeypatch, _market(), condition_keyed=[])
        expected = " ".join(DUPLICATE_CONDITION_LEG_SQL.split())
        assert expected in _condition_lookup_sql(session)

    async def test_it_addresses_all_three_conventions_of_one_condition(
        self, monkeypatch
    ):
        """Bare, `_yes` and `_no` — the three ways one condition is stored."""
        session, _stats = await _run(monkeypatch, _market(), condition_keyed=[])
        assert (
            "fo.external_id IN (:cid, :cid_yes, :cid_no)"
            in _condition_lookup_sql(session)
        )


class TestTheRailAsksTheVenueForResults:
    """Cause (a): the fetch itself. Without this flag nothing above can fire."""

    @pytest.mark.asyncio
    async def test_the_fetch_includes_closed_markets(self, monkeypatch):
        asked = {}

        class _Service:
            async def get_markets_by_conditions(
                self, conditions, batch_size=None, include_closed=False
            ):
                asked["include_closed"] = include_closed
                return [_market()]

            async def close(self):
                return None

        monkeypatch.setattr(
            reg,
            "load_register",
            lambda *a, **k: {
                "reaches": [
                    {
                        "sources": [
                            {
                                "source": "polymarket",
                                "market_external_id": CID,
                                "outcome_id": LADDER_ID,
                            }
                        ]
                    }
                ]
            },
        )
        monkeypatch.setattr(poly_api, "PolymarketAPIService", lambda *a, **k: _Service())
        # The liveness filter reads the DB; fail-open is its documented
        # behaviour and is not what this test is about.
        monkeypatch.setattr(rail, "_live_conditions", _identity)

        async def _noop_writer(markets, stats, *, now):
            stats["snapshots_written"] += 1

        monkeypatch.setattr(rail, "_write_refreshed_prices", _noop_writer)

        await rail._refresh_registered_tournament_prices()
        assert asked["include_closed"] is True, (
            "the rail asked Gamma with the default closed=false filter, so a "
            "settled leg is invisible to it and its last live price is frozen"
        )


async def _identity(conditions):
    return list(conditions)
