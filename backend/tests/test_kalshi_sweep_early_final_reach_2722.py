"""#2722, the reach half — a row whose date already converged is asked again.

PR #3308 built the action half. The sweep writes ``status='resolved'`` when the
venue reports every leg terminal, so settlement no longer needs a date to pass.
But that write only sees rows the SELECT returns, and the SELECT's provisional
predicate (``resolution_date >= expiration_time``) drops a row as soon as its
stored date is a real close instead of the backstop. A market Kalshi finalises
EARLY keeps its future ``close_time``, so its row is converged, future-dated
and ``open``. The date path skips it (the date is in the future) and this sweep
skipped it (it converged). That was the residual the issue's 2026-09-05
handback named.

WHAT THIS FILE HOLDS, all of it executed against a seeded SQLite table:

1. Selection. The base predicate EXCLUDES the specimen; the run's statement
   (:func:`reach_select_sql`) INCLUDES it, ranks it in the played-game band,
   and still returns every row the base predicate returned.
2. The boundary. A past-dated row is the date path's and is not re-admitted.
   So is a ticker whose day has not been played. An undated converged row is
   the named residual, pinned so that reaching it is a deliberate change.
3. The composed run: selection → venue read → ``UPDATE_SQL``, through
   ``run_backfill`` and a session that executes the real statements. The
   early-final row ends ``resolved`` with ``settled_at``. A band row the venue
   still lists as open keeps its status. No outcome's grade moves.

Clocks are literals (gotcha #44).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text

from app.tasks import kalshi_resolution_sweep as sweep
from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS

#: A beat instant. 00:20 ET on 2026-10-13, so the band's newest day is 26OCT12.
NOW = datetime(2026, 10, 13, 4, 20, tzinfo=timezone.utc)
PURGE_FLOOR = NOW - timedelta(days=PROVABLY_PURGED_AGE_DAYS)

#: The specimen. A tournament market whose ticker names its first day (played,
#: inside the band), whose stored date is its scheduled close twelve days out,
#: and whose backstop is later still. That makes it converged and future-dated.
#: The venue finalised it early.
EARLY = dict(
    id=1,
    external_id="KXPGATOUR-26OCT08SHRINERS",
    resolution_date=NOW + timedelta(days=12),
    expiration_time=NOW + timedelta(days=40),
    updated_at=NOW - timedelta(hours=1),
)
#: Same shape, but the venue still trades it. The open control.
OPEN_IN_BAND = dict(
    id=2,
    external_id="KXMLBSERIES-26OCT10NYYBOS",
    resolution_date=NOW + timedelta(days=5),
    expiration_time=NOW + timedelta(days=30),
    updated_at=NOW - timedelta(hours=2),
)
#: Converged, and its date has passed. This row belongs to the date path.
PAST_DATED = dict(
    id=3,
    external_id="KXPGATOUR-26OCT01OPEN",
    resolution_date=NOW - timedelta(days=1),
    expiration_time=NOW + timedelta(days=20),
    updated_at=NOW - timedelta(days=3),
)
#: Converged and future-dated, ticker names TODAY. The day is still being
#: played, so it is not in the band and not re-admitted.
TODAY_TOKEN = dict(
    id=4,
    external_id="KXMLBSERIES-26OCT13LADPHI",
    resolution_date=NOW + timedelta(days=4),
    expiration_time=NOW + timedelta(days=30),
    updated_at=NOW - timedelta(days=4),
)
#: The named residual: converged, future-dated, no played day in the ticker.
UNDATED = dict(
    id=5,
    external_id="KXSENATEME-26",
    resolution_date=NOW + timedelta(days=21),
    expiration_time=NOW + timedelta(days=386),
    updated_at=NOW - timedelta(days=9),
)
#: A base-eligible row (never swept). It must still be selected by the run.
PROVISIONAL = dict(
    id=6,
    external_id="KXMIDTERMMOV-CO01D",
    resolution_date=NOW + timedelta(days=21),
    expiration_time=None,
    updated_at=NOW - timedelta(days=30),
)

ALL_ROWS = (EARLY, OPEN_IN_BAND, PAST_DATED, TODAY_TOKEN, UNDATED, PROVISIONAL)


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def _seed(rows=ALL_ROWS):
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE futures_markets (
                    id INTEGER PRIMARY KEY,
                    external_id TEXT,
                    source TEXT,
                    status TEXT,
                    market_tier INTEGER,
                    commence_time TEXT,
                    resolution_date TEXT,
                    expiration_time TEXT,
                    settled_at TEXT,
                    updated_at TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE futures_outcomes (
                    id INTEGER PRIMARY KEY,
                    market_id INTEGER,
                    resolution_source TEXT,
                    is_winner BOOLEAN
                )
                """
            )
        )
        for r in rows:
            conn.execute(
                text(
                    """
                    INSERT INTO futures_markets
                        (id, external_id, source, status, market_tier,
                         commence_time, resolution_date, expiration_time,
                         settled_at, updated_at)
                    VALUES (:id, :external_id, 'kalshi', 'open', 5, NULL,
                            :resolution_date, :expiration_time, NULL, :updated_at)
                    """
                ),
                {k: _iso(v) for k, v in r.items()},
            )
            conn.execute(
                text(
                    "INSERT INTO futures_outcomes (market_id, resolution_source, is_winner)"
                    " VALUES (:mid, NULL, NULL)"
                ),
                {"mid": r["id"]},
            )
    return engine


def _binds(tokens, **extra):
    return {
        "purge_floor": PURGE_FLOOR.isoformat(),
        "limit": 100,
        "offset": 0,
        **sweep.band_bind_params(tokens),
        **({"reach_after": NOW.isoformat()} if tokens else {}),
        **extra,
    }


def _ids(engine, sql, tokens):
    with engine.begin() as conn:
        return [r[0] for r in conn.execute(text(sql), _binds(tokens)).all()]


TOKENS = sweep.past_event_band_tokens(NOW)


# ---------------------------------------------------------------------------
# 1. Selection
# ---------------------------------------------------------------------------


class TestTheEarlyFinalRowIsSelected:
    def test_the_base_predicate_excludes_it(self):
        """The defect, reproduced. Without the arm the row never reaches the venue."""
        engine = _seed()
        assert EARLY["id"] not in _ids(engine, sweep.banded_select_sql(len(TOKENS)), TOKENS)

    def test_the_runs_statement_includes_it(self):
        engine = _seed()
        assert EARLY["id"] in _ids(engine, sweep.reach_select_sql(len(TOKENS)), TOKENS)

    def test_it_ranks_in_the_band_ahead_of_older_non_band_rows(self):
        """Inside the band, so the next 04:20Z batch reads it first.

        PROVISIONAL and UNDATED carry far older ``updated_at`` stamps. Under the
        inherited ordering alone they would lead.
        """
        engine = _seed()
        ids = _ids(engine, sweep.reach_select_sql(len(TOKENS)), TOKENS)
        assert ids.index(EARLY["id"]) < ids.index(PROVISIONAL["id"])
        assert sweep.row_is_in_band(EARLY["external_id"], TOKENS)

    def test_every_row_the_base_selects_is_still_selected(self):
        """Additive only. A superset, proven on executed SQL, not on text."""
        engine = _seed()
        base = set(_ids(engine, sweep.banded_select_sql(len(TOKENS)), TOKENS))
        reach = set(_ids(engine, sweep.reach_select_sql(len(TOKENS)), TOKENS))
        assert base <= reach
        assert reach - base == {EARLY["id"], OPEN_IN_BAND["id"]}

    def test_the_order_is_the_banded_order_byte_for_byte(self):
        """The arm touches the predicate only. ORDER BY and LIMIT are unchanged."""
        n = len(TOKENS)
        assert (
            sweep.reach_select_sql(n).partition("ORDER BY")[2]
            == sweep.banded_select_sql(n).partition("ORDER BY")[2]
        )

    def test_the_only_predicate_change_is_the_arm(self):
        n = len(TOKENS)
        head = sweep.reach_select_sql(n).partition("ORDER BY")[0]
        arm = f"\n           OR ({sweep.early_final_reach_sql(n)})"
        assert arm in head
        assert head.replace(arm, "") == sweep.banded_select_sql(n).partition("ORDER BY")[0]


# ---------------------------------------------------------------------------
# 2. The boundary
# ---------------------------------------------------------------------------


class TestTheArmsBoundary:
    def test_a_past_dated_row_is_left_to_the_date_path(self):
        engine = _seed()
        assert PAST_DATED["id"] not in _ids(engine, sweep.reach_select_sql(len(TOKENS)), TOKENS)

    def test_a_day_still_being_played_is_not_re_admitted(self):
        engine = _seed()
        assert TODAY_TOKEN["id"] not in _ids(engine, sweep.reach_select_sql(len(TOKENS)), TOKENS)

    def test_the_undated_residual_is_not_reached_by_this_arm(self):
        """Pinned on purpose. #2722 stays open for this cohort.

        Re-admitting every converged future-dated row would push a cycle of the
        500-a-night rotation past its 30-day cursor TTL. Reaching these rows
        needs its own screen with a measured yield. When that ships, this
        assertion should change in the same commit.
        """
        engine = _seed()
        assert UNDATED["id"] not in _ids(engine, sweep.reach_select_sql(len(TOKENS)), TOKENS)

    def test_an_empty_band_changes_nothing(self):
        assert sweep.early_final_reach_sql(0) == ""
        assert sweep.reach_select_sql(0) == sweep.banded_select_sql(0)


class TestTheCountWalksTheSamePopulation:
    def test_eligible_total_includes_the_arm_and_the_arm_is_reported(self):
        """`next_cursor` wraps on eligible_total. A count narrower than the select
        would end the cycle before the arm's rows were walked."""
        engine = _seed()
        with engine.begin() as conn:
            base = conn.execute(
                text(sweep.COUNT_SQL), {"purge_floor": PURGE_FLOOR.isoformat()}
            ).first()
            widened = conn.execute(
                text(sweep.reach_count_sql(len(TOKENS))),
                {"purge_floor": PURGE_FLOOR.isoformat(), "reach_after": NOW.isoformat(),
                 **sweep.band_bind_params(TOKENS)},
            ).first()
        assert len(widened) == len(base) + 1
        assert tuple(widened[:5])[1:] == tuple(base)[1:]
        assert widened[0] == base[0] + 2
        assert widened[5] == 2  # EARLY and OPEN_IN_BAND

    def test_an_empty_band_counts_zero_reach(self):
        engine = _seed()
        with engine.begin() as conn:
            row = conn.execute(
                text(sweep.reach_count_sql(0)), {"purge_floor": PURGE_FLOOR.isoformat()}
            ).first()
        assert row[5] == 0


# ---------------------------------------------------------------------------
# 3. The composed run, on real SQL
# ---------------------------------------------------------------------------


class _SqliteSession:
    """An async-shaped session that executes every statement on SQLite.

    Unlike the recording fakes beside this file, nothing here answers by
    shape: the SELECT, the COUNT and the UPDATE all run. Datetimes are bound
    as ISO strings so they compare the way the seeded strings do, and the two
    date columns of the selected rows come back as datetimes, the shape asyncpg
    hands ``handle()``.
    """

    def __init__(self, engine):
        self._engine = engine
        self._conn = None

    async def __aenter__(self):
        self._conn = self._engine.connect()
        return self

    async def __aexit__(self, *exc):
        self._conn.commit()
        self._conn.close()
        return False

    async def execute(self, stmt, params=None):
        bound = {k: _iso(v) for k, v in (params or {}).items()}
        result = self._conn.execute(stmt, bound)
        if not result.returns_rows:
            return result
        rows = result.all()
        if str(stmt).lstrip().upper().startswith("SELECT ID,"):
            rows = [
                (r[0], r[1], *(datetime.fromisoformat(v) if v else None for v in r[2:4]), r[4])
                for r in rows
            ]

        class _R:
            def all(self_inner):
                return rows

            def first(self_inner):
                return rows[0] if rows else None

        return _R()

    async def commit(self):
        self._conn.commit()


class _Venue:
    """Per-ticker legs. The early final keeps its FUTURE scheduled close."""

    def __init__(self):
        self.asked: list[str] = []

    async def get_event(self, ticker, with_nested_markets=True):
        self.asked.append(ticker)
        row = next(r for r in ALL_ROWS if r["external_id"] == ticker)
        close = _iso(row["resolution_date"])
        expiry = _iso(row["expiration_time"] or row["resolution_date"])
        status, result = (
            ("finalized", "yes") if ticker == EARLY["external_id"] else ("active", "")
        )
        leg = {
            "ticker": f"{ticker}-A",
            "status": status,
            "result": result,
            "close_time": close,
            "expiration_time": expiry,
        }
        return {"markets": [leg, {**leg, "ticker": f"{ticker}-B", "result": "no" if result else ""}]}

    async def close(self):
        return None


def _run(engine):
    venue = _Venue()
    report = asyncio.run(
        sweep.run_backfill(
            session_maker=lambda: _SqliteSession(engine),
            client_factory=lambda: venue,
            limit=100,
            apply=True,
            now=NOW,
        )
    )
    with engine.begin() as conn:
        state = {
            r[0]: (r[1], r[2])
            for r in conn.execute(text("SELECT id, status, settled_at FROM futures_markets")).all()
        }
        grades = conn.execute(text("SELECT market_id, is_winner FROM futures_outcomes")).all()
    return report, venue, state, grades


class TestTheEarlyFinalReachesTheWrite:
    def test_the_specimen_is_asked_at_the_venue_and_written_resolved(self):
        """The issue's acceptance line, run end to end: selection → venue → write."""
        report, venue, state, _ = _run(_seed())
        assert EARLY["external_id"] in venue.asked
        assert state[EARLY["id"]][0] == "resolved"
        assert state[EARLY["id"]][1] == NOW.isoformat()
        assert report["stats"]["venue_settled"] == 1
        assert report["stats"]["early_final_reach_total"] == 2

    def test_the_open_control_keeps_its_status(self):
        _, venue, state, _ = _run(_seed())
        assert OPEN_IN_BAND["external_id"] in venue.asked
        assert state[OPEN_IN_BAND["id"]] == ("open", None)

    def test_rows_outside_the_arm_are_never_asked(self):
        _, venue, state, _ = _run(_seed())
        for row in (PAST_DATED, TODAY_TOKEN, UNDATED):
            assert row["external_id"] not in venue.asked
            assert state[row["id"]] == ("open", None)

    def test_no_grade_is_written(self):
        """#1852's line: the arm widens who is asked, never what is written."""
        _, _, _, grades = _run(_seed())
        assert all(g[1] is None for g in grades)
