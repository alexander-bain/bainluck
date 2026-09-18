"""#6919 — the venue settled it, we graded it, and the market row still said open.

THE DEFECT, AS THE READER MEETS IT
----------------------------------
`_write_refreshed_prices` is the condition-keyed refresh rail — the one door to a
Polymarket market that does NOT depend on the hourly poll. Since #3868 it reads
the venue's own settlement off `outcomePrices` and GRADES the legs with
`resolution_source='api_settlement'`, which is tier-3 authority.

It never wrote `futures_markets.status`. So the rail left rows in a state no
single writer can explain: every leg carries a winner, and the market row says
`open` with `settled_at IS NULL`. Measured on production 2026-09-18: **18
markets / 34 legs** wholly graded by this rail and still `status='open'`, 13 of
them condition-keyed and 11 linked to an event — i.e. on a game page, presented
as a question still being asked, under a result we had already written.

WHY THIS RAIL AND NOT THE POLL
------------------------------
`submarket_is_open` (#6734) is the status writer, and it lives only in
`_process_event_batch`, whose population is the newest 2,000 active+unclosed
Gamma events by `startDate` — the offset-2000 cap of #219E. Replayed against the
venue on 2026-09-18 (`artifacts-460/poll_reach.py`): that window reached back
**~11 hours**, and **218 of the 226** Gamma events on our live slate sat outside
it. For those the poll is not slow, it is absent, and the only other settlement
rail is a CLOB `market_resolved` websocket push with no reconciliation. This rail
is the reconciliation.

THE GATE IS NOT WIDENED
-----------------------
The status write is coupled to `settled_yes_probability` — the SAME decision that
already gates the grade, unchanged. A book that is open writes no status; a book
that is closed between the bars (void, mis-settled, caught mid-settlement) writes
no status and stays counted in `closed_without_result`. We never invent a
settlement; we write down the one we had already acted on.
"""

import contextlib
from datetime import datetime, timezone

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Update
from sqlalchemy.sql.elements import TextClause

import app.services.polymarket_api as poly_api
import app.tasks.tournament_price_refresh as rail

NOW = datetime(2026, 9, 18, 10, 30, tzinfo=timezone.utc)

#: The same condition and leg ids `test_tournament_ladder_settlement_3868.py`
#: uses, so the two files are talking about one row. The doubles below are
#: restated rather than imported: `backend/tests/` is not a package and no test
#: in this suite imports another, so an import here would be a new convention
#: for one file's convenience.
CID = "0x3d060eff715e0aa1d15e3758ec37866519686f88c7e0cb0704314d8c844e3e2e"
SUB_YES_ID, SUB_NO_ID = 221651178, 221651179


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


def _is_the_close(stmt) -> bool:
    """The deferred settlement UPDATE, told apart from the leg lookup.

    Both are `text()`, so `isinstance` cannot separate them; one is a SELECT
    against `futures_outcomes` and the other an UPDATE against
    `futures_markets`, and that is what we key on.
    """
    return (
        isinstance(stmt, TextClause)
        and "update futures_markets" in " ".join(str(stmt).split()).lower()
    )


class RecordingSession:
    """Records every statement; answers the writer's three statements apart.

    `closed_rows` is what the settlement UPDATE reports as `rowcount` — the
    number of market rows that actually MOVED. It defaults to 0 rather than to
    "however many legs you handed me", because the counter under test must be
    able to say "I closed nothing" on a pass that closed nothing (see
    `TestTheCounterCountsClosuresNotAttempts`).
    """

    def __init__(self, *, market_keyed=(), condition_keyed=(), closed_rows=0):
        self.statements: list[object] = []
        self.calls: list[tuple[object, dict]] = []
        self._market_keyed = list(market_keyed)
        self._condition_keyed = list(condition_keyed)
        self._closed_rows = closed_rows

    async def execute(self, stmt, *args, **kwargs):
        self.statements.append(stmt)
        self.calls.append((stmt, dict(args[0]) if args and args[0] else {}))
        if _is_the_close(stmt):
            return _Result([object()] * self._closed_rows)
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
        "markets_settled": 0,
        "closed_without_result": 0,
        "legs_reached_by_condition": 0,
    }


# ---------------------------------------------------------------------------
# The payload comes off the VENUE's wire and through the REAL parser.
#
# Rig 249: a hand-built DTO passes happily on both sides of a fix, because it
# cannot drop the field the fix rests on. `_parse_market` is what production
# runs, `outcomePrices` really does arrive as a stringified JSON array, and
# `closed` really is a separate key from `active` — so the specimen below fails
# for the same reasons production would.
# ---------------------------------------------------------------------------
def _venue_payload(**kw) -> dict:
    """A Gamma nested market, in Gamma's own shape and spelling."""
    payload = {
        "conditionId": CID,
        "question": "Will Carlos Alcaraz advance to the Quarterfinals?",
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["1", "0"]',
        "clobTokenIds": '["11", "22"]',
        "active": True,
        "closed": True,
        "acceptingOrders": False,
        "bestBid": None,
        "bestAsk": 0.009,
        "lastTradePrice": 0.995,
        "volume24hr": 1234.0,
    }
    payload.update(kw)
    return payload


def _parsed(**kw):
    market = poly_api.PolymarketAPIService()._parse_market(_venue_payload(**kw))
    assert market is not None, "the real parser refused the specimen"
    return market


async def _run(
    monkeypatch, market, *, market_keyed=(), condition_keyed=(), closed_rows=0
):
    session = RecordingSession(
        market_keyed=market_keyed,
        condition_keyed=condition_keyed,
        closed_rows=closed_rows,
    )

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    import app.tasks.base as base

    monkeypatch.setattr(base, "get_task_session", _fake_session)

    stats = _stats()
    markets = market if isinstance(market, list) else [market]
    await rail._write_refreshed_prices(markets, stats, now=NOW)
    return session, stats


def _market_writes(session) -> list[dict]:
    """Bound params of every UPDATE issued against `futures_markets`."""
    out: list[dict] = []
    for stmt in session.statements:
        if not isinstance(stmt, Update):
            continue
        table = getattr(stmt, "table", None)
        if table is None or table.name != "futures_markets":
            continue
        compiled = stmt.compile(dialect=postgresql.dialect())
        params = dict(compiled.params)
        params["_sql"] = " ".join(str(compiled).split())
        out.append(params)
    return out


def _close_writes(session) -> list[dict]:
    """The deferred settlement UPDATE, as `{_sql, **bound params}`.

    Since the parent-ladder repair the close is a single `text()` statement
    issued once per PASS, addressed through the legs. `_market_writes` above
    compiles ORM `Update` objects and cannot see it — which is exactly how a
    guard suite can stay green while the write it guards stops firing, so both
    shapes feed `_status_writes`.
    """
    out: list[dict] = []
    for stmt, params in session.calls:
        if not _is_the_close(stmt):
            continue
        row = dict(params)
        row["_sql"] = " ".join(str(stmt).split())
        out.append(row)
    return out


def _status_writes(session) -> list[dict]:
    """Every market write that actually sets `status`, whichever shape it is."""
    orm = [
        w for w in _market_writes(session) if "status=" in w["_sql"].replace(" ", "")
    ]
    return orm + _close_writes(session)


LEGS = ((SUB_YES_ID, "Yes", f"{CID}_yes"), (SUB_NO_ID, "No", f"{CID}_no"))


# ---------------------------------------------------------------------------
# ANTI-VACUITY. Before asserting what the fix writes, prove the specimen
# reaches the branch the fix lives on — and that the rail really does grade it
# today. A guard whose specimen never enters the gate passes on both sides of
# the change (rig 249, and the cost of learning it on #6919's first attempt).
# ---------------------------------------------------------------------------
class TestTheSpecimenReallyTakesTheSettledBranch:
    def test_the_real_parser_keeps_the_two_fields_the_gate_reads(self):
        market = _parsed()
        assert market.closed is True
        assert market.outcome_prices == [1.0, 0.0]

    def test_the_gate_calls_it_settled(self):
        assert rail.settled_yes_probability(_parsed()) == 1.0

    def test_an_open_book_is_refused_by_that_same_gate(self):
        assert (
            rail.settled_yes_probability(
                _parsed(closed=False, outcomePrices='["0.62", "0.38"]')
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_the_rail_already_grades_this_specimen(self, monkeypatch):
        _, stats = await _run(monkeypatch, _parsed(), market_keyed=LEGS)
        assert stats["legs_settled"] == 2, (
            "the specimen must be one the rail already settles, or this file "
            "proves nothing about the row it leaves behind"
        )


# ---------------------------------------------------------------------------
# THE CLASS GUARD
# ---------------------------------------------------------------------------
class TestASettledBookClosesTheMarketRowItGraded:
    @pytest.mark.asyncio
    async def test_the_market_row_is_marked_resolved(self, monkeypatch):
        session, _ = await _run(monkeypatch, _parsed(), market_keyed=LEGS)
        writes = _status_writes(session)
        assert writes, (
            "the rail graded both legs and left `futures_markets.status` "
            "untouched — this is #6919"
        )
        sql = writes[0]["_sql"].lower()
        assert "'resolved'" in sql
        assert "futures_markets" in sql

    @pytest.mark.asyncio
    async def test_settled_at_moves_with_the_status_and_never_backwards(
        self, monkeypatch
    ):
        # LINKLOSS-02: status and settled_at are one fact. COALESCE so a second
        # pass cannot restamp a settlement we already dated.
        session, _ = await _run(monkeypatch, _parsed(), market_keyed=LEGS)
        sql = _status_writes(session)[0]["_sql"].lower()
        assert "settled_at" in sql
        assert "coalesce" in sql

    @pytest.mark.asyncio
    async def test_it_stays_inside_polymarket(self, monkeypatch):
        session, _ = await _run(monkeypatch, _parsed(), market_keyed=LEGS)
        sql = _status_writes(session)[0]["_sql"].lower()
        assert "source = 'polymarket'" in sql, (
            "the close must never reach a Kalshi or Odds-API row"
        )

    @pytest.mark.asyncio
    async def test_the_no_side_settlement_closes_the_row_too(self, monkeypatch):
        session, stats = await _run(
            monkeypatch, _parsed(outcomePrices='["0", "1"]'), market_keyed=LEGS
        )
        assert stats["legs_settled"] == 2
        assert _status_writes(session), "a losing settlement is still a settlement"


class TestNothingElseIsClosed:
    """The gate is not widened. Both refusals below are the existing ones."""

    @pytest.mark.asyncio
    async def test_an_open_book_closes_nothing(self, monkeypatch):
        session, stats = await _run(
            monkeypatch,
            _parsed(closed=False, acceptingOrders=True, outcomePrices='["0.62", "0.38"]'),
            market_keyed=LEGS,
        )
        assert stats["legs_settled"] == 0
        assert _status_writes(session) == []

    @pytest.mark.asyncio
    async def test_a_closed_book_between_the_bars_closes_nothing(self, monkeypatch):
        # Void / mis-settled / caught mid-settlement. We do not know who won, so
        # we must not say the question is answered.
        session, stats = await _run(
            monkeypatch,
            _parsed(outcomePrices='["0.5", "0.5"]'),
            market_keyed=LEGS,
        )
        assert stats["closed_without_result"] == 1
        assert stats["legs_settled"] == 0
        assert _status_writes(session) == []

    @pytest.mark.asyncio
    async def test_the_volume_write_is_still_issued_and_is_not_the_status_write(
        self, monkeypatch
    ):
        # The rail already UPDATEs `futures_markets` for volume on every market
        # it is served, including ones it cannot price. That write must stay,
        # and it must not be mistaken for the settlement write.
        session, _ = await _run(
            monkeypatch,
            _parsed(closed=False, outcomePrices='["0.62", "0.38"]'),
            market_keyed=LEGS,
        )
        assert _market_writes(session), "the volume write disappeared"
        assert _status_writes(session) == []


# ---------------------------------------------------------------------------
# THE PARENT-LADDER REPAIR. #6919's first cut keyed the close on
# `futures_markets.external_id == <condition>`, which is the SUB-MARKET row and
# nothing else. #3868's comment in this very file names the OTHER row — a
# parent ladder keyed on the Gamma EVENT id, whose legs carry the BARE
# condition — and the first cut graded its legs and could not close it.
#
# Measured on production 2026-09-18, the fixed rail's own 16:08:02Z pass:
# 60755454 / 60755456 / 60755459 (CPBL, `external_id` 1004380 / 1004378 /
# 1004376 — numeric Gamma EVENT ids, never 64-hex conditions) had their `Yes`
# leg graded `api_settlement` to the microsecond by that pass and kept
# `status='open'`, `settled_at NULL`. All three are LINKED — i.e. on a game
# page, a settled question served as one still being asked.
# ---------------------------------------------------------------------------
class TestTheCloseReachesTheParentLadderRow:
    @pytest.mark.asyncio
    async def test_it_is_addressed_through_the_legs_not_the_market_key(
        self, monkeypatch
    ):
        session, _ = await _run(monkeypatch, _parsed(), market_keyed=LEGS)
        sql = _status_writes(session)[0]["_sql"].lower()
        assert "futures_outcomes" in sql, (
            "a close keyed on `futures_markets.external_id` structurally "
            "cannot reach an event-id-keyed ladder row — this is the defect"
        )
        assert "fm.external_id" not in sql

    @pytest.mark.asyncio
    async def test_the_bare_condition_is_among_the_keys_it_looks_for(
        self, monkeypatch
    ):
        # THE ASSERTION THAT WOULD HAVE CAUGHT THE CPBL CLASS. The ladder's leg
        # carries the BARE condition; only the sub-market's legs carry the
        # `_yes` / `_no` suffixes. A close that looks for the suffixed forms
        # alone closes half the rows it graded — and reports success.
        session, _ = await _run(monkeypatch, _parsed(), market_keyed=LEGS)
        keys = _status_writes(session)[0]["leg_keys"]
        assert CID in keys, "the parent ladder's leg is unreachable"
        assert f"{CID}_yes" in keys and f"{CID}_no" in keys

    @pytest.mark.asyncio
    async def test_one_statement_for_the_whole_pass_not_one_per_market(
        self, monkeypatch
    ):
        other = "0x" + "ab" * 32
        session, _ = await _run(
            monkeypatch,
            [_parsed(), _parsed(conditionId=other)],
            market_keyed=LEGS,
        )
        writes = _status_writes(session)
        assert len(writes) == 1, (
            "the close is deferred to one statement after the grading loop, "
            "so that it can see the grades THIS pass just wrote"
        )
        assert CID in writes[0]["leg_keys"] and other in writes[0]["leg_keys"]


# ---------------------------------------------------------------------------
# THE SAFETY CLAUSE. A parent ladder owns ONE LEG PER CHILD and its children
# settle at different times — #3868's own words: a round-by-round ladder
# settles over weeks. "This market owns a leg we just graded" is therefore true
# of a live US Open draw the moment one player's condition settles, so the
# reach above is only safe with the ungraded-leg gate beside it.
#
# Measured on production 2026-09-18 16:35Z: without the gate this statement
# would close 389 open markets, 322 of them tier 1-3 — every live tournament
# ladder on a marquee surface, retired mid-event.
# ---------------------------------------------------------------------------
class TestTheCloseCannotRetireALiveLadder:
    @pytest.mark.asyncio
    async def test_a_market_with_an_ungraded_leg_is_excluded(self, monkeypatch):
        session, _ = await _run(monkeypatch, _parsed(), market_keyed=LEGS)
        sql = " ".join(_status_writes(session)[0]["_sql"].split()).lower()
        assert "not exists" in sql and "resolution_source is null" in sql, (
            "without this gate the first child to settle closes the whole ladder"
        )

    @pytest.mark.asyncio
    async def test_the_gate_is_resolution_source_and_never_is_winner(
        self, monkeypatch
    ):
        # 🛑 MEASURED, AND NEARLY GOT WRONG. This file's own CERT-452 comment
        # says `is_winner` is nullable with `default=False`, so an UNGRADED leg
        # reads FALSE, not NULL — an `is_winner IS NULL` gate reads "nobody
        # looked" as "graded". Production 2026-09-18 16:45Z, open markets whose
        # every leg the gate calls graded: `is_winner IS NULL` → 12,926 (806
        # linked); `resolution_source IS NULL` → 4,921 (64 linked). The wrong
        # gate closes ~8,000 extra markets, 742 of them on game pages.
        session, _ = await _run(monkeypatch, _parsed(), market_keyed=LEGS)
        sql = _status_writes(session)[0]["_sql"].lower()
        assert "is_winner" not in sql

    @pytest.mark.asyncio
    async def test_a_legless_row_is_not_swept_up(self, monkeypatch):
        # `NOT EXISTS (... resolution_source IS NULL)` is VACUOUSLY TRUE for a
        # market with no legs at all, so the positive existence test beside it
        # is load-bearing, not decoration.
        session, _ = await _run(monkeypatch, _parsed(), market_keyed=LEGS)
        sql = " ".join(_status_writes(session)[0]["_sql"].split()).lower()
        assert sql.count("exists") >= 3

    @pytest.mark.asyncio
    async def test_an_already_resolved_row_is_not_restamped(self, monkeypatch):
        session, _ = await _run(monkeypatch, _parsed(), market_keyed=LEGS)
        sql = _status_writes(session)[0]["_sql"].lower()
        assert "status <> 'resolved'" in sql
        assert "coalesce" in sql, "a second pass must not redate a settlement"


# ---------------------------------------------------------------------------
# THE COUNTER. `markets_settled` is what the #6919 after-check reads as proof
# the fix is working, and the first cut incremented it once per settled BOOK
# with the UPDATE's result discarded. On the 16:08:00-16:08:37Z production pass
# it reported 4 while exactly ONE row moved. A counter that cannot be wrong
# about its own write is the cheapest liveness oracle there is; one that counts
# intentions is worse than none, because an after-check believes it.
# ---------------------------------------------------------------------------
class TestTheCounterCountsClosuresNotAttempts:
    @pytest.mark.asyncio
    async def test_a_settled_book_that_moves_no_row_counts_zero(self, monkeypatch):
        session, stats = await _run(
            monkeypatch, _parsed(), market_keyed=LEGS, closed_rows=0
        )
        assert _status_writes(session), "the close must still be attempted"
        assert stats["legs_settled"] == 2, "the book really was settled"
        assert stats["markets_settled"] == 0, (
            "the rail graded legs and closed nothing, and said so"
        )

    @pytest.mark.asyncio
    async def test_it_reports_what_the_update_reports(self, monkeypatch):
        _, stats = await _run(
            monkeypatch, _parsed(), market_keyed=LEGS, closed_rows=2
        )
        assert stats["markets_settled"] == 2, (
            "both rows a condition can own — sub-market and ladder — count once"
        )
