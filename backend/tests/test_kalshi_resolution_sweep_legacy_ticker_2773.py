"""#2773 — the resolution-window sweep reaches legacy-ticker Kalshi rows.

WHAT A READER SAW. bainluck.com/futures/109082 at 390px, 2026-09-26: "Maine
Senate winner? — Resolves Nov 3, 2027". It is the November 2026 midterm, tier 1,
five weeks out. Kalshi's ``SENATEME-26`` sends ``close_time == expiration_time ==
2027-11-03`` (a one-year backstop) and ``expected_expiration_time = 2027-01-04``.
The #2644 derivation already turns exactly that shape into the venue's estimate,
but the sweep selected ``external_id LIKE 'KX%'`` and never asked about a
``SENATE*`` / ``HOUSE*`` / ``GOVPARTY*`` ticker.

MEASURED BEFORE WIDENING (venue-read of all 209 open legacy rows through this
module's own derivation, 2026-09-26): 124 move earlier, all still in the future
(earliest 2027-01-04), 85 unchanged, 0 later, 0 past-dated, 0 settled.

WHAT THIS FILE HOLDS.

1. Selection, as real SQL against a seeded table: the legacy row is a candidate
   and is counted; a row with no ticker is not. The pre-#2773 statement is kept
   verbatim as the defect arm, so the fixture is proved able to tell them apart.
2. The composed write for the specimen's real venue payload: the date moves to
   the estimate, the backstop is preserved in ``expiration_time``, and the row
   stays open.

CLOCK DISCIPLINE (gotcha #44): every instant here is a literal.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text

from app.tasks import kalshi_resolution_sweep as sweep
from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS

NOW = datetime(2026, 9, 26, 17, 0, tzinfo=timezone.utc)
PURGE_FLOOR = NOW - timedelta(days=PROVABLY_PURGED_AGE_DAYS)

#: The specimen's venue dates, read from Kalshi 2026-09-26.
BACKSTOP = datetime(2027, 11, 3, 15, 0, tzinfo=timezone.utc)
EXPECTED = datetime(2027, 1, 4, 15, 0, tzinfo=timezone.utc)

CREATE_TABLE = """
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

#: Seeded empty: no row here is in #7000's fully-retracted cohort.
CREATE_OUTCOMES = """
    CREATE TABLE futures_outcomes (
        id INTEGER PRIMARY KEY,
        market_id INTEGER,
        resolution_source TEXT
    )
"""

INSERT = """
    INSERT INTO futures_markets
        (id, external_id, source, status, market_tier, commence_time,
         resolution_date, expiration_time, updated_at)
    VALUES (:id, :external_id, 'kalshi', 'open', :tier, :commence,
            :resolution_date, NULL, :updated_at)
"""

#: The statement as it stood before #2773, verbatim apart from its ORDER BY.
DEFECT_SELECT_SQL = """
    SELECT id, external_id, resolution_date, commence_time, market_tier
    FROM futures_markets
    WHERE source = 'kalshi'
      AND status = 'open'
      AND external_id LIKE 'KX%'
      AND (expiration_time IS NULL
           OR resolution_date IS NULL
           OR resolution_date >= expiration_time)
      AND (commence_time IS NULL OR commence_time >= :purge_floor)
    ORDER BY id
    LIMIT :limit OFFSET :offset
"""

ROWS = [
    # The specimen: legacy ticker, stored on the backstop.
    {"id": 109082, "external_id": "SENATEME-26", "tier": 1},
    # Control: a current-convention ticker, selected before and after.
    {"id": 52755659, "external_id": "KXNHL-27", "tier": 1},
    # No ticker: nothing to ask the venue, so never a candidate.
    {"id": 7, "external_id": None, "tier": 1},
]


def _seed():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE))
        conn.execute(text(CREATE_OUTCOMES))
        for r in ROWS:
            conn.execute(
                text(INSERT),
                {
                    **r,
                    "commence": BACKSTOP.isoformat(),
                    "resolution_date": BACKSTOP.isoformat(),
                    "updated_at": (NOW - timedelta(hours=3)).isoformat(),
                },
            )
    return engine


def _params(**extra):
    return {"purge_floor": PURGE_FLOOR.isoformat(), "limit": 100, "offset": 0, **extra}


class TestSelection:
    def test_the_legacy_ticker_is_a_candidate(self):
        tokens = sweep.past_event_band_tokens(NOW)
        with _seed().begin() as conn:
            got = conn.execute(
                text(sweep.banded_select_sql(len(tokens))),
                _params(**sweep.band_bind_params(tokens)),
            ).all()
        assert sorted(r[1] for r in got) == ["KXNHL-27", "SENATEME-26"]

    def test_the_count_sees_the_same_population(self):
        with _seed().begin() as conn:
            totals = conn.execute(
                text(sweep.COUNT_SQL), {"purge_floor": PURGE_FLOOR.isoformat()}
            ).first()
        # eligible_total and never_swept: the two ticker-bearing rows, not the null.
        assert (totals[0], totals[2]) == (2, 2)

    def test_the_old_prefix_could_not_reach_it(self):
        """The defect arm: the same fixture under the pre-#2773 statement."""
        with _seed().begin() as conn:
            got = conn.execute(text(DEFECT_SELECT_SQL), _params()).all()
        assert [r[1] for r in got] == ["KXNHL-27"]

    def test_the_game_selects_keep_their_prefix(self):
        """Only the population sweep widened; the played-game arms did not."""
        assert "external_id LIKE 'KX%'" in sweep.RESOLVED_VOID_SELECT_SQL
        assert "external_id LIKE 'KX%'" in sweep.RECENT_FINAL_SELECT_SQL
        assert "LIKE 'KX%'" not in sweep.SELECT_SQL
        assert "LIKE 'KX%'" not in sweep.COUNT_SQL


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _RecordingSession:
    def __init__(self, recorder):
        self._recorder = recorder

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, params=None):
        self._recorder.append((str(stmt), params))
        return _Result([])

    async def commit(self):
        return None


class _Venue:
    """``SENATEME-26`` exactly as Kalshi served it on 2026-09-26."""

    async def get_event(self, ticker, with_nested_markets=True):
        assert ticker == "SENATEME-26"
        leg = {
            "status": "active",
            "result": "",
            "close_time": "2027-11-03T15:00:00Z",
            "expiration_time": "2027-11-03T15:00:00Z",
            "expected_expiration_time": "2027-01-04T15:00:00Z",
        }
        return {
            "markets": [
                {**leg, "ticker": "SENATEME-26-D"},
                {**leg, "ticker": "SENATEME-26-R"},
            ]
        }

    async def close(self):
        return None


class TestTheSpecimenWrite:
    def _run(self):
        recorder: list = []
        report = asyncio.run(
            sweep.run_backfill(
                session_maker=lambda: _RecordingSession(recorder),
                client_factory=_Venue,
                apply=True,
                now=NOW,
                rows=[(109082, "SENATEME-26", BACKSTOP, BACKSTOP, 1)],
            )
        )
        writes = [p for sql, p in recorder if sql == sweep.UPDATE_SQL]
        return report, writes

    def test_the_date_moves_to_the_venue_estimate(self):
        report, writes = self._run()
        assert len(writes) == 1
        w = writes[0]
        assert w["id"] == 109082
        assert w["resolution_date"] == EXPECTED
        assert w["expiration_time"] == BACKSTOP
        assert report["stats"]["moved_earlier"] == 1
        # Still in the future, so nothing downstream may resolve it on a date.
        assert report["stats"]["newly_past"] == 0

    def test_the_row_stays_open(self):
        report, writes = self._run()
        assert writes[0]["venue_settled"] is False
        assert report["stats"]["venue_settled"] == 0
