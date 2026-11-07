"""Midterms 2026-11-03 — a RETRACTED Kalshi leg on an open market streams again.

Measured on production 2026-11-03: the Midterms 2026 collection served Kalshi
numbers 90–100 min old, and 12 of 20 single-source numbers sat outside Kalshi's
current bid–ask. 40 of the collection's 50 Kalshi legs (13 open markets, e.g.
futures_markets 108620 "Which party will win the U.S. Senate?", open, unexpired,
``settled_at`` NULL) carried ``resolution_source='ungradeable_result',
is_winner=false`` — a RETRACTION, not a grade (CAL-P056). The open-contract
socket admitted only ``is_winner IS NULL``, the 30 s venue poll covers
Polymarket only, so those legs moved on the 2 h REST poll alone.

Three properties, each against SQL a fake cannot fake (SQLite over the real
model tables):

1. the admission statement now takes a retracted leg and still refuses every
   graded / closed shape it refused before;
2. the real consumer subscribes that leg, and the price UPDATE it emits writes
   the retracted row (leaving the retraction in place, as the REST poll does)
   while still refusing a venue-authoritative one;
3. a venue grade frame on that leg reaches the per-leg grader, and the grader
   overwrites the retraction with the venue's answer.

Tickers and outcome ids are synthetic; market 108620 is the production id.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, event, insert, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

import tests.test_ws_open_contract_prices_9484 as rig
from app.models.models import FuturesMarket, FuturesOutcome
from app.tasks import ws_open_contracts as oc
from app.tasks import venue_poll_30s
from tests._sqlite_returned_clock import install_returned_clock


@compiles(JSONB, "sqlite")
def _jsonb_as_json(_type, _compiler, **_kw):  # pragma: no cover - DDL shim
    return "JSON"


#: The statement's ``NOW()``, pinned. SQLite stores a naive DATETIME in this
#: exact text form, so ``expiration_time > NOW()`` compares like Postgres would.
NOW = datetime(2026, 11, 3, 12, 0, 0)
NOW_TEXT = NOW.strftime("%Y-%m-%d %H:%M:%S.%f")

SENATE = 108620
DEM, REP = 1086201, 1086202
DEM_T, REP_T = "KXSENATECONTROL-26-D", "KXSENATECONTROL-26-R"


def _engine():
    engine = create_engine("sqlite://")
    install_returned_clock(engine)

    @event.listens_for(engine, "connect")
    def _now(connection, _record):
        connection.create_function("NOW", 0, lambda: NOW_TEXT)

    FuturesMarket.__table__.create(engine)
    FuturesOutcome.__table__.create(engine)
    return engine


def _market(conn, market_id, *, source="kalshi", status="open",
            settled_at=None, expiration_time=NOW + timedelta(days=30)):
    conn.execute(insert(FuturesMarket.__table__).values(
        id=market_id, source=source, external_id=f"KXM-{market_id}",
        name=f"market {market_id}", status=status, settled_at=settled_at,
        expiration_time=expiration_time,
    ))


def _leg(conn, outcome_id, market_id, ticker, *, is_winner=False,
         source="ungradeable_result", price=0.30):
    conn.execute(insert(FuturesOutcome.__table__).values(
        id=outcome_id, market_id=market_id, external_id=ticker,
        name=ticker or f"leg {outcome_id}", current_probability=price,
        is_winner=is_winner, resolution_source=source,
    ))


def _admitted(conn) -> set[int]:
    return {row[2] for row in conn.execute(oc.kalshi_open_contract_stmt()).all()}


# ------------------------------------------------------------ the admission ----


class TestTheAdmissionTakesARetractionAndNothingElseNew:
    def test_a_retracted_leg_on_an_open_market_is_admitted(self):
        engine = _engine()
        with engine.begin() as conn:
            _market(conn, SENATE)
            _leg(conn, DEM, SENATE, DEM_T, price=0.53)
            _leg(conn, REP, SENATE, REP_T, price=0.47)
            assert _admitted(conn) == {DEM, REP}, (
                "108620's retracted legs must stream: ungradeable_result is "
                "a retraction, the venue has not called them"
            )

    def test_an_ungraded_leg_is_still_admitted(self):
        engine = _engine()
        with engine.begin() as conn:
            _market(conn, SENATE)
            _leg(conn, DEM, SENATE, DEM_T, is_winner=None, source=None)
            assert _admitted(conn) == {DEM}

    @pytest.mark.parametrize("is_winner,source", [
        (False, "api_settlement"),       # the venue graded it a loss
        (True, "api_settlement"),        # the venue crowned it
        (True, None),                    # crowned by anything
        (True, "ungradeable_result"),    # a crown never rides in on the source
        (False, "pass2_guess"),          # only the retraction is widened
        (False, None),                   # the column default stays out, as before
    ])
    def test_a_graded_or_crowned_leg_is_still_refused(self, is_winner, source):
        engine = _engine()
        with engine.begin() as conn:
            _market(conn, SENATE)
            _leg(conn, DEM, SENATE, DEM_T)  # the admitted control
            _leg(conn, REP, SENATE, REP_T, is_winner=is_winner, source=source)
            assert _admitted(conn) == {DEM}

    @pytest.mark.parametrize("market", [
        {"status": "resolved"},
        {"settled_at": NOW - timedelta(hours=1)},
        {"expiration_time": NOW - timedelta(seconds=1)},
        {"source": "polymarket"},
    ])
    def test_a_retracted_leg_on_a_closed_market_is_still_refused(self, market):
        engine = _engine()
        with engine.begin() as conn:
            _market(conn, SENATE)
            _leg(conn, DEM, SENATE, DEM_T)  # the admitted control
            _market(conn, 2, **market)
            _leg(conn, 21, 2, "KXCLOSED-26-X")
            assert _admitted(conn) == {DEM}

    def test_a_retracted_leg_without_a_ticker_is_never_subscribed(self):
        # `external_id` is NOT NULL in the model, so the no-ticker shape that
        # can exist is '' — the statement's `IS NOT NULL` passes it and the
        # ticker map drops it. Both halves are the admission.
        engine = _engine()
        with engine.begin() as conn:
            _market(conn, SENATE)
            _leg(conn, DEM, SENATE, DEM_T)
            _leg(conn, REP, SENATE, "")
            rows = conn.execute(oc.kalshi_open_contract_stmt()).all()
        assert oc.open_contract_ticker_map(rows, {}) == {DEM_T: (SENATE, DEM)}
        assert "futures_outcomes.external_id IS NOT NULL" in rig._sql(
            oc.kalshi_open_contract_stmt()
        )

    @pytest.mark.parametrize("is_winner,source,streams", [
        (None, None, True),
        (False, "ungradeable_result", True),
        (False, "api_settlement", False),
        (True, "ungradeable_result", False),
        (False, None, False),
    ])
    def test_the_route_mirror_says_what_the_statement_says(
        self, is_winner, source, streams,
    ):
        assert oc.leg_streams(is_winner, source) is streams
        engine = _engine()
        with engine.begin() as conn:
            _market(conn, SENATE)
            _leg(conn, DEM, SENATE, DEM_T, is_winner=is_winner, source=source)
            assert (DEM in _admitted(conn)) is streams


class TestTheThirtySecondPollStillRendersTheSocketsPredicate:
    def test_the_rendered_exclusion_carries_the_retraction_arm(self):
        sql = venue_poll_30s.kalshi_population_sql(open_arm=True)
        rendered = venue_poll_30s._render(oc.kalshi_open_contract_stmt().whereclause)
        assert f"AND NOT COALESCE({rendered}, FALSE)" in sql
        assert "fo.is_winner IS NULL" in rendered
        assert "fo.resolution_source = 'ungradeable_result'" in rendered
        assert "futures_outcomes" not in rendered, "rendered against the poll's aliases"

    def test_the_poll_without_the_open_arm_excludes_nothing_of_it(self):
        assert "ungradeable_result" not in venue_poll_30s.kalshi_population_sql(
            open_arm=False
        )


# ------------------------------------------------------ the consumer, wired ----


def _senate_board():
    """The production shape: one open market, both legs retracted."""
    engine = _engine()
    with engine.begin() as conn:
        _market(conn, SENATE)
        _leg(conn, DEM, SENATE, DEM_T, price=0.53)
        _leg(conn, REP, SENATE, REP_T, price=0.47)
    return engine


def _open_rows_from(engine):
    """The open-contract read, answered by running the real statement."""
    def _read():
        with engine.connect() as conn:
            return [tuple(r) for r in conn.execute(oc.kalshi_open_contract_stmt()).all()]
    return _read


def _capture_price_statements(monkeypatch):
    """Keep each price UPDATE the consumer emits, beside the rig's own pairs."""
    captured = []
    real = rig.price_writes

    def _recording(stmt, params=None):
        pairs = real(stmt, params)
        if pairs:
            captured.append((stmt, params))
        return pairs

    monkeypatch.setattr(rig, "price_writes", _recording)
    return captured


def _row(engine, outcome_id):
    with engine.connect() as conn:
        return conn.execute(
            select(
                FuturesOutcome.current_probability,
                FuturesOutcome.is_winner,
                FuturesOutcome.resolution_source,
            ).where(FuturesOutcome.id == outcome_id)
        ).one()


class TestARetractedLegTicksIntoAStoredPrice:
    async def test_the_consumer_subscribes_it_and_writes_its_tick(self, monkeypatch):
        engine = _senate_board()
        captured = _capture_price_statements(monkeypatch)
        stats, record, state = await rig._run(
            monkeypatch,
            frames_for={REP_T: [rig._tick(REP_T)]},
            open_rows=_open_rows_from(engine),
        )

        subscribed = {
            t for subs in rig._connections(record) for p in subs
            for t in p.get("market_tickers") or []
        }
        assert {DEM_T, REP_T} <= subscribed, "the retracted legs never reached the wire"
        assert stats["open_contract_tickers"] == 2
        assert (REP, pytest.approx(0.41)) in state["price_writes"]
        assert stats["open_contract_prices_written"] >= 1

        # The UPDATE the consumer actually emitted, on the real row.
        (stmt, params), = [c for c in captured if params_id(c) == REP]
        with engine.begin() as conn:
            written = conn.execute(stmt, params).all()
        assert len(written) == 1
        price, is_winner, source = _row(engine, REP)
        assert float(price) == pytest.approx(0.41)
        # The retraction stays: the REST poll's `graded_columns` is `{}` on an
        # unanswered market, so it re-prices without touching the grade pair.
        assert (is_winner, source) == (False, "ungradeable_result")

    @pytest.mark.parametrize("is_winner", [False, True])
    async def test_the_same_update_still_refuses_an_authoritative_leg(
        self, monkeypatch, is_winner,
    ):
        engine = _senate_board()
        captured = _capture_price_statements(monkeypatch)
        await rig._run(
            monkeypatch,
            frames_for={REP_T: [rig._tick(REP_T)]},
            open_rows=_open_rows_from(engine),
        )
        (stmt, params), = [c for c in captured if params_id(c) == REP]
        settled = 1.0 if is_winner else 0.0
        with engine.begin() as conn:
            # Graded by the venue between the admission read and the tick.
            conn.execute(
                update(FuturesOutcome.__table__)
                .where(FuturesOutcome.__table__.c.id == REP)
                .values(is_winner=is_winner, resolution_source="api_settlement",
                        current_probability=settled)
            )
            written = conn.execute(stmt, params).all()
        assert written == []
        assert float(_row(engine, REP)[0]) == pytest.approx(settled)


def params_id(capture):
    stmt, params = capture
    return (params or {}).get("kalshi_outcome_id")


# ------------------------------------------------------------- the grade ----


class _AsyncOver:
    """The grader's one session call, over a sync SQLite connection."""

    def __init__(self, conn):
        self._conn = conn

    async def execute(self, stmt, params=None):
        return self._conn.execute(stmt, params or {})


class TestAVenueGradeOnARetractedLegLands:
    async def test_the_frame_reaches_the_per_leg_grader(self, monkeypatch):
        engine = _senate_board()
        calls = []

        async def _grade(_session, *, market_id, outcome_id, state, result):
            calls.append((market_id, outcome_id, state, result))
            return None, None

        monkeypatch.setattr(oc, "grade_open_contract_leg", _grade)
        await rig._run(
            monkeypatch,
            frames_for={REP_T: [rig._settle(REP_T, result="yes")]},
            open_rows=_open_rows_from(engine),
        )
        assert calls == [(SENATE, REP, "determined", "yes")]

    async def test_the_grader_overwrites_the_retraction(self):
        engine = _senate_board()
        with engine.begin() as conn:
            graded, resolved = await oc.grade_open_contract_leg(
                _AsyncOver(conn), market_id=SENATE, outcome_id=REP,
                state="determined", result="yes",
            )
        assert graded is not None and graded[0] == REP
        assert resolved is None, "DEM is still only retracted: the board stays open"
        price, is_winner, source = _row(engine, REP)
        assert (is_winner, source, float(price)) == (True, "api_settlement", 1.0)

        with engine.begin() as conn:
            graded, resolved = await oc.grade_open_contract_leg(
                _AsyncOver(conn), market_id=SENATE, outcome_id=DEM,
                state="determined", result="no",
            )
        assert graded is not None and resolved is not None
        price, is_winner, source = _row(engine, DEM)
        assert (is_winner, source, float(price)) == (False, "api_settlement", 0.0)

    async def test_a_venue_grade_is_never_flipped_by_a_stray_frame(self):
        engine = _senate_board()
        with engine.begin() as conn:
            conn.execute(
                update(FuturesOutcome.__table__)
                .where(FuturesOutcome.__table__.c.id == REP)
                .values(is_winner=True, resolution_source="api_settlement",
                        current_probability=1.0)
            )
            graded, _resolved = await oc.grade_open_contract_leg(
                _AsyncOver(conn), market_id=SENATE, outcome_id=REP,
                state="determined", result="no",
            )
        assert graded is None
        assert _row(engine, REP)[1:] == (True, "api_settlement")
