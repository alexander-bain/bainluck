"""#2722, the reach half — the venue's settled feed (CERT-4117's repair).

PR #3308 made :data:`UPDATE_SQL` write ``status='resolved'`` on the venue's word,
but only for rows a selection hands it. A market Kalshi finalises EARLY keeps a
future ``close_time``, so its row is converged, future-dated and ``open``, and
nothing in it changes. The first repair re-admitted such rows into the population
sweep; CERT-4117 blocked it because the sweep resumes a rotating global cursor:
at cursor 500:500 it selected 500 of 1,503 rows, never asked the specimen, and
advanced to 1000:1000.

:func:`run_settled_feed` selects on the venue instead. It walks
``GET /markets?status=settled`` forward by ``settlement_ts`` and looks up our
``open`` rows by event ticker. Everything here executes the real statements on
a seeded SQLite table; only the venue, the clock and Redis are doubled.

1. The guard #2722 asks for: the feed's selection has no date predicate and
   never reads the sweep's cursor.
2. CERT-4117's composed control: the population sweep at a nonzero saved cursor
   still does not reach the specimen (that is the sweep's nature, unchanged);
   the next feed run does, band-dated and undated alike. A head-0 positive
   control, an active control and a partially-settled control beside it.
3. The walk: the watermark moves only after a window is finished, a refused
   filter fails loud, a venue error retries, an oversized window halves, and a
   dry run writes nothing.

Clocks are literals (gotcha #44).
"""

from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text

from app.tasks import kalshi_resolution_sweep as sweep

#: A beat instant.
NOW = datetime(2026, 10, 13, 4, 23, tzinfo=timezone.utc)
NOW_TS = int(NOW.timestamp())
CEILING = NOW_TS  # the head walks to the present (CERT-4118)
#: Where a running feed's watermark stood before this beat: the previous run.
LAST_RUN = CEILING - 600

#: CERT-4117's specimen. A tournament market whose ticker names its first day,
#: stored with its scheduled close twelve days out. The venue finalised it early.
EARLY_BAND = dict(
    id=1,
    external_id="KXPGATOUR-26OCT08SHRINERS",
    resolution_date=NOW + timedelta(days=12),
    expiration_time=NOW + timedelta(days=40),
    updated_at=NOW - timedelta(hours=1),
)
#: The cohort the played-day arm could never reach: no day in the ticker at all.
EARLY_UNDATED = dict(
    id=2,
    external_id="KXOSCARSONG-26",
    resolution_date=NOW + timedelta(days=79),
    expiration_time=NOW + timedelta(days=400),
    updated_at=NOW - timedelta(days=9),
)
#: Same shape as the specimen, still trading. The venue never lists it settled.
OPEN_ACTIVE = dict(
    id=3,
    external_id="KXMLBSERIES-26OCT10NYYBOS",
    resolution_date=NOW + timedelta(days=5),
    expiration_time=NOW + timedelta(days=30),
    updated_at=NOW - timedelta(hours=2),
)
#: One leg settled at the venue, one still open. Listed in the feed, refused at
#: the all-legs read.
PARTIAL = dict(
    id=4,
    external_id="KXEMMYCOUNT-26WID",
    resolution_date=NOW + timedelta(days=30),
    expiration_time=NOW + timedelta(days=60),
    updated_at=NOW - timedelta(days=2),
)
#: Settled at the venue AND already resolved here. Not ours to touch again.
ALREADY_RESOLVED = dict(
    id=5,
    external_id="KXFEDDECISION-26SEP",
    resolution_date=NOW - timedelta(days=20),
    expiration_time=NOW - timedelta(days=20),
    updated_at=NOW - timedelta(days=20),
    status="resolved",
)

SPECIMENS = (EARLY_BAND, EARLY_UNDATED, OPEN_ACTIVE, PARTIAL, ALREADY_RESOLVED)

#: CERT-4117's tail: base-eligible rows (never swept) the population sweep
#: rotates through, older stamps than every specimen.
TAIL = tuple(
    dict(
        id=1000 + i,
        external_id=f"KXTAIL-{i:05d}",
        resolution_date=NOW + timedelta(days=200),
        expiration_time=None,
        updated_at=NOW - timedelta(days=60, minutes=i),
    )
    for i in range(1500)
)


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def _seed(rows=SPECIMENS):
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
                    VALUES (:id, :external_id, 'kalshi', :status, 5, NULL,
                            :resolution_date, :expiration_time, NULL, :updated_at)
                    """
                ),
                {"status": "open", **{k: _iso(v) for k, v in r.items()}},
            )
            conn.execute(
                text(
                    "INSERT INTO futures_outcomes (market_id, resolution_source, is_winner)"
                    " VALUES (:mid, NULL, NULL)"
                ),
                {"mid": r["id"]},
            )
    return engine


class _SqliteSession:
    """Executes every statement on SQLite; nothing answers by shape."""

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


def _ts(seconds_ago: int) -> str:
    return datetime.fromtimestamp(CEILING - seconds_ago, timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


class _Venue:
    """Kalshi, doubled at the transport boundary.

    ``settled`` is the venue's settled-market list; ``get_markets`` applies the
    two settlement-time bounds, newest first, in pages, the way the live
    endpoint was read to behave on 2026-10-14. ``legs`` is what
    ``GET /events/{ticker}`` returns per event.
    """

    def __init__(self, *, settled=None, legs=None, page_size=None):
        self.settled = list(settled if settled is not None else _DEFAULT_SETTLED)
        self.legs = dict(legs if legs is not None else _DEFAULT_LEGS)
        self.page_size = page_size
        self.asked: list[str] = []
        self.pages: list[dict] = []
        self.ignore_filter = False
        self.page_error: Exception | None = None
        self.event_error_for: set = set()
        #: ticker -> the payload `get_event` answers with instead (CERT-4118):
        #: None is a 404 or three swallowed failures; `{"markets": []}` is the
        #: empty 200.
        self.event_payload_for: dict = {}

    async def get_markets(self, *, status, limit, cursor=None, min_settled_ts=None,
                          max_settled_ts=None, mve_filter=None, **_):
        self.pages.append(dict(status=status, min=min_settled_ts, max=max_settled_ts,
                               mve=mve_filter, cursor=cursor))
        if self.page_error is not None:
            raise self.page_error
        assert status == "settled"
        rows = self.settled
        if not self.ignore_filter:
            rows = [
                m for m in rows
                if min_settled_ts <= datetime.fromisoformat(
                    m["settlement_ts"].replace("Z", "+00:00")).timestamp() <= max_settled_ts
            ]
        rows = sorted(rows, key=lambda m: m["settlement_ts"], reverse=True)
        size = self.page_size or limit
        start = int(cursor or 0)
        page = rows[start : start + size]
        nxt = str(start + size) if start + size < len(rows) else None
        return page, nxt

    async def get_event(self, ticker, with_nested_markets=True):
        self.asked.append(ticker)
        if ticker in self.event_error_for:
            raise RuntimeError("venue 502")
        if ticker in self.event_payload_for:
            return self.event_payload_for[ticker]
        legs = self.legs.get(ticker)
        if legs is None:
            return {"markets": [
                {"ticker": f"{ticker}-A", "status": "active", "result": "",
                 "close_time": _iso(NOW + timedelta(days=30)),
                 "expiration_time": _iso(NOW + timedelta(days=60))},
            ]}
        return {"markets": legs}

    async def close(self):
        return None


def _legs(ticker, statuses, close):
    return [
        {
            "ticker": f"{ticker}-{i}",
            "status": st,
            "result": ("yes" if i == 0 else "no") if st == "finalized" else "",
            # An early final keeps its FUTURE scheduled close.
            "close_time": _iso(close),
            "expiration_time": _iso(close + timedelta(days=30)),
        }
        for i, st in enumerate(statuses)
    ]


_DEFAULT_SETTLED = [
    # Market tickers match `_legs`'s naming: the feed and the event read name
    # the same markets, as they do at the venue.
    {"ticker": "KXPGATOUR-26OCT08SHRINERS-0", "event_ticker": EARLY_BAND["external_id"],
     "settlement_ts": _ts(200)},
    {"ticker": "KXPGATOUR-26OCT08SHRINERS-1", "event_ticker": EARLY_BAND["external_id"],
     "settlement_ts": _ts(200)},
    {"ticker": "KXOSCARSONG-26-0", "event_ticker": EARLY_UNDATED["external_id"],
     "settlement_ts": _ts(300)},
    {"ticker": "KXEMMYCOUNT-26WID-0", "event_ticker": PARTIAL["external_id"],
     "settlement_ts": _ts(400)},
    {"ticker": "KXFEDDECISION-26SEP-C25", "event_ticker": ALREADY_RESOLVED["external_id"],
     "settlement_ts": _ts(450)},
    # Settled at the venue, not a row of ours. Read, matched to nothing.
    {"ticker": "KXBTCD-26OCT1300-T60000", "event_ticker": "KXBTCD-26OCT1300",
     "settlement_ts": _ts(100)},
]
_DEFAULT_LEGS = {
    EARLY_BAND["external_id"]: _legs(EARLY_BAND["external_id"], ["finalized", "finalized"],
                                     EARLY_BAND["resolution_date"]),
    EARLY_UNDATED["external_id"]: _legs(EARLY_UNDATED["external_id"],
                                        ["finalized", "finalized", "finalized"],
                                        EARLY_UNDATED["resolution_date"]),
    PARTIAL["external_id"]: _legs(PARTIAL["external_id"], ["finalized", "active"],
                                  PARTIAL["resolution_date"]),
}


def _copy_feed(feed):
    return dict(feed, owed=list(feed["owed"]),
                owed_meta={t: dict(m, legs=list(m["legs"]))
                           for t, m in (feed.get("owed_meta") or {}).items()})


def _feed_state(*, head=LAST_RUN, back=None, back_end=None, owed=(), owed_meta=None):
    """A running feed's state. By default the backlog is already walked."""
    back_end = head if back_end is None else back_end
    return {
        "head": head,
        "head_step": sweep.SETTLED_FEED_STEP_S,
        "back": back_end if back is None else back,
        "back_end": back_end,
        "back_step": sweep.SETTLED_FEED_STEP_S,
        "owed": list(owed),
        "owed_meta": dict(owed_meta or {}),
    }


@pytest.fixture
def redis_state(monkeypatch):
    """The two Redis values this file touches, in memory."""
    store: dict = {"feed": _feed_state(), "cursor": (0, 0)}
    writes: list = []

    async def read_feed():
        feed = store["feed"]
        return None if feed is None else _copy_feed(feed)

    async def write_feed(state):
        if store.get("feed_write_fails"):
            return False
        store["feed"] = _copy_feed(state)
        writes.append(store["feed"])
        return True

    async def read_cursor():
        return store["cursor"]

    async def write_cursor(offset, scanned):
        store["cursor"] = (offset, scanned)
        return True

    monkeypatch.setattr(sweep, "_read_feed_state", read_feed)
    monkeypatch.setattr(sweep, "_write_feed_state", write_feed)
    monkeypatch.setattr(sweep, "_read_cursor", read_cursor)
    monkeypatch.setattr(sweep, "_write_cursor", write_cursor)
    return SimpleNamespace(store=store, writes=writes)


def _feed(engine, venue, **kw):
    return asyncio.run(
        sweep.run_settled_feed(
            session_maker=lambda: _SqliteSession(engine),
            client_factory=lambda: venue,
            now=NOW,
            **kw,
        )
    )


def _state(engine):
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT id, status, settled_at FROM futures_markets")).all()
        grades = conn.execute(text("SELECT market_id, is_winner, resolution_source "
                                   "FROM futures_outcomes")).all()
    return {r[0]: (r[1], r[2]) for r in rows}, grades


# ---------------------------------------------------------------------------
# 1. The guard: settlement is not entered through a date, a ticker or a cursor
# ---------------------------------------------------------------------------


class TestTheSelectionReadsNoDateAndNoCursor:
    def test_the_feed_select_has_no_date_predicate(self):
        """#2722's third acceptance line. The columns a date path keys on are
        absent from the WHERE clause, so no stored date can keep a settled row
        out of this arm."""
        where = sweep.SETTLED_FEED_SELECT_SQL.partition("WHERE")[2].partition("ORDER BY")[0]
        for column in ("resolution_date", "expiration_time", "commence_time",
                       "updated_at", "settled_at", "now()", "LIKE"):
            assert column not in where, column
        assert "external_id IN :tickers" in where
        assert "status = 'open'" in where

    def test_the_feed_never_reads_the_sweeps_cursor(self):
        """CERT-4117's causal boundary was the saved global offset. The feed
        must not consult it, so its cadence cannot depend on the sweep's cycle."""
        src = inspect.getsource(sweep.run_settled_feed)
        for name in ("_read_cursor", "SWEEP_CURSOR_KEY", "next_cursor", "offset="):
            assert name not in src, name

    def test_the_feed_asks_the_venue_for_settled_markets_by_settlement_time(self, redis_state):
        venue = _Venue()
        _feed(_seed(), venue)
        assert venue.pages
        for page in venue.pages:
            assert page["status"] == "settled"
            assert page["mve"] == "exclude"
            # The head's first window re-reads the overlap behind the watermark.
            assert page["min"] == LAST_RUN - sweep.SETTLED_FEED_OVERLAP_S
            assert page["max"] == CEILING


# ---------------------------------------------------------------------------
# 2. CERT-4117's composed control, plus its three companions
# ---------------------------------------------------------------------------


class _SweepVenue(_Venue):
    """The population sweep's venue: every tail row is still trading."""


def _sweep_at(engine, venue, cursor, redis_state):
    redis_state.store["cursor"] = cursor
    return asyncio.run(
        sweep.run_sweep(
            session_maker=lambda: _SqliteSession(engine),
            client_factory=lambda: venue,
            limit=500,
        )
    )


class TestANonzeroSweepCursorNoLongerDecidesTheCadence:
    def test_the_sweep_at_500_500_still_does_not_reach_the_specimen(self, redis_state):
        """Reproduces CERT-4117's observation on the restored sweep. Unchanged
        on purpose: the population sweep keeps its v3 cycle and its tail's
        progress. This is the shape the feed exists to make irrelevant."""
        engine = _seed(SPECIMENS + TAIL)
        venue = _SweepVenue()
        report = _sweep_at(engine, venue, (500, 500), redis_state)
        assert report["offset"] == 500
        assert report["stats"]["candidates"] == 500
        assert EARLY_BAND["external_id"] not in venue.asked
        state, _ = _state(engine)
        assert state[EARLY_BAND["id"]] == ("open", None)
        # The cycle advanced past the specimen's slot without visiting it.
        assert redis_state.store["cursor"][1] == 1000

    def test_the_next_feed_run_resolves_it_whatever_the_cursor_says(self, redis_state):
        """The ship, composed: the sweep runs at a nonzero cursor and skips the
        specimen, then the next feed beat asks the venue and writes it closed.
        The sweep's cursor is untouched by the feed."""
        engine = _seed(SPECIMENS + TAIL)
        _sweep_at(engine, _SweepVenue(), (500, 500), redis_state)
        cursor_after_sweep = redis_state.store["cursor"]

        venue = _Venue()
        report = _feed(engine, venue)

        assert EARLY_BAND["external_id"] in venue.asked
        state, _ = _state(engine)
        assert state[EARLY_BAND["id"]] == ("resolved", NOW.isoformat())
        assert redis_state.store["cursor"] == cursor_after_sweep
        assert report["terminal"] == "complete"

    def test_the_undated_early_final_is_resolved_in_the_same_run(self, redis_state):
        """The cohort the played-day arm left unreached. No day in its ticker,
        a future stored date, and closed in one beat all the same."""
        engine = _seed(SPECIMENS + TAIL)
        venue = _Venue()
        _feed(engine, venue)
        state, _ = _state(engine)
        assert EARLY_UNDATED["external_id"] in venue.asked
        assert state[EARLY_UNDATED["id"]] == ("resolved", NOW.isoformat())

    def test_head_zero_control_the_outcome_does_not_depend_on_the_cursor(self, redis_state):
        """The same table with the sweep's cursor at the head. The restored
        sweep does not select converged rows at any offset, so the specimens
        are still open after it, and the feed resolves them exactly as it does
        behind a 500:500 cursor. The cursor is not an input to the ship."""
        engine = _seed(SPECIMENS + TAIL)
        sweep_venue = _SweepVenue()
        _sweep_at(engine, sweep_venue, (0, 0), redis_state)
        assert EARLY_BAND["external_id"] not in sweep_venue.asked
        assert _state(engine)[0][EARLY_BAND["id"]] == ("open", None)

        report = _feed(engine, _Venue())
        state, _ = _state(engine)
        assert state[EARLY_BAND["id"]] == ("resolved", NOW.isoformat())
        assert state[EARLY_UNDATED["id"]] == ("resolved", NOW.isoformat())
        assert report["stats"]["venue_settled"] == 2

    def test_active_control_is_never_asked_and_keeps_its_status(self, redis_state):
        engine = _seed()
        venue = _Venue()
        _feed(engine, venue)
        state, _ = _state(engine)
        assert OPEN_ACTIVE["external_id"] not in venue.asked
        assert state[OPEN_ACTIVE["id"]] == ("open", None)

    def test_partially_settled_control_is_asked_and_refused(self, redis_state):
        """All-terminal proof is unchanged: one finalized leg is not the event."""
        engine = _seed()
        venue = _Venue()
        report = _feed(engine, venue)
        state, _ = _state(engine)
        assert PARTIAL["external_id"] in venue.asked
        assert state[PARTIAL["id"]] == ("open", None)
        assert report["stats"]["venue_partially_settled"] == 1

    def test_an_already_resolved_row_is_not_selected(self, redis_state):
        engine = _seed()
        venue = _Venue()
        _feed(engine, venue)
        assert ALREADY_RESOLVED["external_id"] not in venue.asked

    def test_no_grade_is_written(self, redis_state):
        """#1852's line: the feed changes who is asked, never what is written."""
        engine = _seed()
        _feed(engine, _Venue())
        _, grades = _state(engine)
        assert all(g[1] is None and g[2] is None for g in grades)

    def test_the_counts_name_what_happened(self, redis_state):
        engine = _seed()
        report = _feed(engine, _Venue())
        stats = report["stats"]
        assert stats["venue_markets_seen"] == len(_DEFAULT_SETTLED)
        assert stats["event_tickers_seen"] == 5
        assert stats["rows_matched"] == 3
        assert stats["venue_settled"] == 2
        assert report["head_caught_up"] is True


# ---------------------------------------------------------------------------
# 3. The walk
# ---------------------------------------------------------------------------


class TestTheHeadWalk:
    def test_it_moves_to_the_ceiling_and_a_quiet_next_run_asks_nothing(self, redis_state):
        engine = _seed()
        _feed(engine, _Venue())
        assert redis_state.store["feed"]["head"] == CEILING

        venue = _Venue()
        report = _feed(engine, venue)
        assert venue.asked == []
        assert report["terminal"] == "complete"
        assert report["head_windows"] == 0

    def test_an_event_whose_last_leg_settles_later_is_closed_then(self, redis_state):
        """Leg-by-leg settlement: refused on the first leg, reached again when
        the last leg's settlement time falls in a later window."""
        engine = _seed()
        _feed(engine, _Venue())
        assert _state(engine)[0][PARTIAL["id"]][0] == "open"

        later = NOW + timedelta(minutes=10)
        settled = _DEFAULT_SETTLED + [
            {"ticker": "KXEMMYCOUNT-26WID-1", "event_ticker": PARTIAL["external_id"],
             "settlement_ts": (later - timedelta(minutes=7)).isoformat().replace("+00:00", "Z")},
        ]
        legs = {**_DEFAULT_LEGS, PARTIAL["external_id"]: _legs(
            PARTIAL["external_id"], ["finalized", "finalized"], PARTIAL["resolution_date"])}
        venue = _Venue(settled=settled, legs=legs)
        asyncio.run(sweep.run_settled_feed(
            session_maker=lambda: _SqliteSession(engine),
            client_factory=lambda: venue, now=later))
        assert venue.asked == [PARTIAL["external_id"]]
        assert _state(engine)[0][PARTIAL["id"]] == ("resolved", later.isoformat())


class TestTheHeadIsNeverHeldBehindTheBacklog:
    def test_a_fresh_state_puts_the_head_one_step_back_and_the_backlog_at_the_floor(self):
        state = sweep.fresh_feed_state(NOW)
        floor = int((NOW - timedelta(days=sweep.SETTLED_FEED_BACKLOG_DAYS)).timestamp())
        assert state["head"] == CEILING - sweep.SETTLED_FEED_STEP_S
        assert state["back"] == floor
        assert state["back_end"] == state["head"]
        assert state["owed"] == []

    def test_on_first_deploy_a_fresh_undated_settlement_closes_in_the_first_run(self, redis_state):
        """Root 019's composed test. No stored state, so the backlog is ~74 days
        behind and the run's page budget could not walk it, yet an undated early
        final settled minutes ago is closed by this very run."""
        redis_state.store["feed"] = None
        engine = _seed()
        venue = _Venue()
        report = _feed(engine, venue, max_pages=5)
        assert report["bootstrapped"] is True
        assert report["backlog_behind_seconds"] > 70 * 86400
        assert EARLY_UNDATED["external_id"] in venue.asked
        assert _state(engine)[0][EARLY_UNDATED["id"]] == ("resolved", NOW.isoformat())
        assert report["head_caught_up"] is True
        # The head was read first: its window is the first page asked for.
        assert venue.pages[0]["max"] == CEILING

    def test_while_the_backlog_is_behind_each_later_run_still_reaches_the_head(self, redis_state):
        floor = int((NOW - timedelta(days=sweep.SETTLED_FEED_BACKLOG_DAYS)).timestamp())
        redis_state.store["feed"] = _feed_state(back=floor, back_end=LAST_RUN - 3600)
        engine = _seed()
        venue = _Venue()
        report = _feed(engine, venue, max_pages=3)
        assert _state(engine)[0][EARLY_BAND["id"]][0] == "resolved"
        assert report["head_caught_up"] is True
        assert report["backlog_windows"] >= 1
        assert redis_state.store["feed"]["back"] > floor
        assert report["terminal"] == "complete"

    def test_the_backlog_walk_uses_what_the_head_left_and_is_bounded(self, redis_state):
        floor = int((NOW - timedelta(days=sweep.SETTLED_FEED_BACKLOG_DAYS)).timestamp())
        redis_state.store["feed"] = _feed_state(back=floor, back_end=LAST_RUN)
        venue = _Venue(settled=[])
        report = _feed(_seed(), venue, max_pages=5)
        assert len(venue.pages) == 5
        assert report["head_windows"] == 1
        assert report["backlog_windows"] == 4
        assert redis_state.store["feed"]["back"] == floor + 4 * sweep.SETTLED_FEED_STEP_S

    def test_a_backlog_settlement_is_closed_when_the_walk_reaches_it(self, redis_state):
        old = dict(EARLY_UNDATED, id=9, external_id="KXGRAMMYAOTY-26")
        settled = [{"ticker": "KXGRAMMYAOTY-26-0", "event_ticker": old["external_id"],
                    "settlement_ts": _ts(86400 * 3)}]
        legs = {old["external_id"]: _legs(old["external_id"], ["finalized"], old["resolution_date"])}
        redis_state.store["feed"] = _feed_state(back=CEILING - 86400 * 4, back_end=LAST_RUN)
        engine = _seed(SPECIMENS + (old,))
        _feed(engine, _Venue(settled=settled, legs=legs))
        assert _state(engine)[0][9] == ("resolved", NOW.isoformat())


class TestAWindowThatIsNotFinishedDoesNotMoveIt:
    def test_a_venue_that_ignores_the_filter_fails_loud_and_writes_nothing(self, redis_state):
        """A feed that silently stopped filtering would read as an empty window
        walked correctly. It is refused instead."""
        engine = _seed()
        venue = _Venue(settled=_DEFAULT_SETTLED + [
            {"ticker": "OLD-1", "event_ticker": "OLD", "settlement_ts": "2026-01-01T00:00:00Z"}])
        venue.ignore_filter = True
        report = _feed(engine, venue)
        assert report["terminal"] == "failed"
        assert "not applied" in report["terminal_reason"]
        assert redis_state.store["feed"]["head"] == LAST_RUN
        assert venue.asked == []
        assert all(s == ("open", None) or i == ALREADY_RESOLVED["id"]
                   for i, s in _state(engine)[0].items())

    def test_a_page_error_is_partial_and_retried(self, redis_state):
        venue = _Venue()
        venue.page_error = RuntimeError("429 Too Many Requests")
        report = _feed(_seed(), venue)
        assert report["terminal"] == "partial"
        assert "page error" in report["head_stop"]
        assert redis_state.store["feed"]["head"] == LAST_RUN

    def test_a_window_too_big_for_a_whole_run_halves_and_then_finishes(self, redis_state):
        engine = _seed()
        venue = _Venue(page_size=1)
        report = _feed(engine, venue, max_pages=3)
        assert report["head_windows"] == 0
        assert redis_state.store["feed"]["head"] == LAST_RUN
        assert redis_state.store["feed"]["head_step"] == (CEILING - LAST_RUN) // 2

        for _ in range(10):
            if redis_state.store["feed"]["head"] == CEILING:
                break
            _feed(engine, _Venue(page_size=1), max_pages=3)
        assert redis_state.store["feed"]["head"] == CEILING
        assert _state(engine)[0][EARLY_BAND["id"]][0] == "resolved"

    def test_a_lost_state_write_fails_the_run(self, redis_state):
        redis_state.store["feed_write_fails"] = True
        report = _feed(_seed(), _Venue())
        assert report["terminal"] == "failed"
        assert report["state_persisted"] is False

    def test_a_dry_run_writes_nothing_and_keeps_the_watermark(self, redis_state):
        engine = _seed()
        report = _feed(engine, _Venue(), apply=False)
        assert report["mode"] == "DRY_RUN"
        assert redis_state.writes == []
        assert report["head_after"] == report["head_before"]
        state, _ = _state(engine)
        assert state[EARLY_BAND["id"]] == ("open", None)


class TestAnErroredReadIsOwedNotForgotten:
    def test_the_walk_moves_on_and_the_ticker_is_owed(self, redis_state):
        """One bad ticker neither wedges the walk nor drops the row: the head
        reaches the present and the ticker is carried as a debt, read partial."""
        engine = _seed()
        venue = _Venue()
        venue.event_error_for = {EARLY_UNDATED["external_id"]}
        report = _feed(engine, venue)
        assert redis_state.store["feed"]["head"] == CEILING
        assert redis_state.store["feed"]["owed"] == [EARLY_UNDATED["external_id"]]
        assert report["terminal"] == "partial"
        assert "owed" in report["terminal_reason"]
        # Its siblings in the same window were still written.
        assert _state(engine)[0][EARLY_BAND["id"]][0] == "resolved"
        assert _state(engine)[0][EARLY_UNDATED["id"]] == ("open", None)

    def test_every_fresh_row_erroring_is_an_outage(self, redis_state):
        venue = _Venue()
        venue.event_error_for = {EARLY_BAND["external_id"], EARLY_UNDATED["external_id"],
                                 PARTIAL["external_id"]}
        report = _feed(_seed(), venue)
        assert report["terminal"] == "failed"
        assert len(redis_state.store["feed"]["owed"]) == 3

    def test_repeated_errors_keep_the_debt_then_recovery_closes_the_row(self, redis_state):
        """Root 019: errors for several runs, then the venue answers. The row
        closes from the owed list alone — no window re-read, no sweep, no date."""
        engine = _seed()
        for _ in range(5):
            venue = _Venue()
            venue.event_error_for = {EARLY_UNDATED["external_id"]}
            report = _feed(engine, venue)
            assert redis_state.store["feed"]["owed"] == [EARLY_UNDATED["external_id"]]
            assert report["terminal"] == "partial"
        assert _state(engine)[0][EARLY_UNDATED["id"]] == ("open", None)

        venue = _Venue()
        report = _feed(engine, venue)
        assert venue.asked == [EARLY_UNDATED["external_id"]]
        assert all(p["min"] == CEILING for p in venue.pages)  # head is current; nothing re-read
        assert _state(engine)[0][EARLY_UNDATED["id"]] == ("resolved", NOW.isoformat())
        assert redis_state.store["feed"]["owed"] == []
        assert report["owed_paid"] == 1
        assert report["terminal"] == "complete"

    def test_a_debt_whose_row_closed_elsewhere_is_paid_without_a_read(self, redis_state):
        engine = _seed()
        with engine.begin() as conn:
            conn.execute(text("UPDATE futures_markets SET status = 'resolved' WHERE id = :i"),
                         {"i": EARLY_UNDATED["id"]})
        redis_state.store["feed"] = _feed_state(head=CEILING, owed=[EARLY_UNDATED["external_id"]])
        venue = _Venue()
        report = _feed(engine, venue)
        assert venue.asked == []
        assert redis_state.store["feed"]["owed"] == []
        assert report["terminal"] == "complete"

    def test_a_full_owed_list_holds_the_window_instead_of_dropping_a_debt(self, redis_state, monkeypatch):
        monkeypatch.setattr(sweep, "SETTLED_FEED_OWED_MAX", 1)
        monkeypatch.setattr(sweep, "SETTLED_FEED_OWED_RETRY_PER_RUN", 0)
        redis_state.store["feed"] = _feed_state(owed=["KXSOMETHING-ELSE"])
        venue = _Venue()
        venue.event_error_for = {EARLY_UNDATED["external_id"]}
        report = _feed(_seed(), venue)
        assert redis_state.store["feed"]["head"] == LAST_RUN
        assert redis_state.store["feed"]["owed"] == ["KXSOMETHING-ELSE"]
        assert "owed list full" in report["head_stop"]
        assert report["terminal"] == "partial"

    def test_owed_retries_are_bounded_and_rotate(self, redis_state, monkeypatch):
        monkeypatch.setattr(sweep, "SETTLED_FEED_OWED_RETRY_PER_RUN", 1)
        engine = _seed()
        redis_state.store["feed"] = _feed_state(
            head=CEILING, owed=[EARLY_UNDATED["external_id"], EARLY_BAND["external_id"]])
        venue = _Venue()
        venue.event_error_for = {EARLY_UNDATED["external_id"]}
        _feed(engine, venue)
        assert venue.asked == [EARLY_UNDATED["external_id"]]
        assert redis_state.store["feed"]["owed"] == [
            EARLY_BAND["external_id"], EARLY_UNDATED["external_id"]]


class TestAnUnconfirmedReadIsOwedNotForgotten:
    """CERT-4118 / Root's exact-head review of eb65ad4677: the venue's settled
    feed names an open event, the event read comes back empty or missing, and
    the next run's read is all-terminal. The window is never listed again, so
    the row is reached only if the first read was owed.

    An empty 200 is a response shape (gotcha #53), and ``get_event`` returns
    None for a 404 AND after three swallowed failures — neither is absence."""

    @pytest.mark.parametrize(
        "payload",
        [None, {"markets": []}, {}, {"markets": None}],
        ids=["none-404-or-swallowed", "empty-200", "no-markets-key", "null-markets"],
    )
    def test_an_empty_read_is_owed_and_the_recovered_read_closes_it(self, redis_state, payload):
        engine = _seed()
        venue = _Venue()
        venue.event_payload_for = {EARLY_UNDATED["external_id"]: payload}
        report = _feed(engine, venue)

        feed = redis_state.store["feed"]
        assert feed["head"] == CEILING  # the walk still moved on
        assert feed["owed"] == [EARLY_UNDATED["external_id"]]
        assert feed["owed_meta"][EARLY_UNDATED["external_id"]]["legs"] == ["KXOSCARSONG-26-0"]
        assert report["stats"]["venue_read_unconfirmed"] == 1
        assert report["terminal"] == "partial"
        assert _state(engine)[0][EARLY_UNDATED["id"]] == ("open", None)
        assert _state(engine)[0][EARLY_BAND["id"]][0] == "resolved"

        venue = _Venue()  # the venue answers with every leg finalized
        report = _feed(engine, venue)
        assert venue.asked == [EARLY_UNDATED["external_id"]]
        assert all(p["min"] == CEILING for p in venue.pages)  # no window re-read
        assert _state(engine)[0][EARLY_UNDATED["id"]] == ("resolved", NOW.isoformat())
        assert redis_state.store["feed"]["owed"] == []
        assert redis_state.store["feed"]["owed_meta"] == {}
        assert report["owed_paid"] == 1
        assert report["terminal"] == "complete"

    def test_mutant_control_without_the_owe_the_row_is_never_reached(self, redis_state, monkeypatch):
        """The test above bites: with the unconfirmed list ignored (the
        eb65ad4677 behaviour), the same two runs leave the row open."""
        real = sweep.run_backfill

        async def forgetful(**kw):
            report = await real(**kw)
            return dict(report, unconfirmed_tickers=[])

        monkeypatch.setattr(sweep, "run_backfill", forgetful)
        engine = _seed()
        venue = _Venue()
        venue.event_payload_for = {EARLY_UNDATED["external_id"]: {"markets": []}}
        _feed(engine, venue)
        _feed(engine, _Venue())
        assert redis_state.store["feed"]["owed"] == []
        assert _state(engine)[0][EARLY_UNDATED["id"]] == ("open", None)

    def test_a_read_older_than_the_listing_is_owed(self, redis_state):
        """The feed listed the leg settled; the event read still shows it
        trading. That read is stale, not a refusal."""
        engine = _seed()
        venue = _Venue()
        venue.legs[EARLY_UNDATED["external_id"]] = _legs(
            EARLY_UNDATED["external_id"], ["active", "finalized", "finalized"],
            EARLY_UNDATED["resolution_date"])
        report = _feed(engine, venue)
        assert redis_state.store["feed"]["owed"] == [EARLY_UNDATED["external_id"]]
        assert report["stats"]["venue_read_unconfirmed"] == 1
        assert _state(engine)[0][EARLY_UNDATED["id"]] == ("open", None)

        # Still stale on the retry: kept, because the retry checks the same legs.
        _feed(engine, venue)
        assert redis_state.store["feed"]["owed"] == [EARLY_UNDATED["external_id"]]

        venue = _Venue()
        _feed(engine, venue)
        assert _state(engine)[0][EARLY_UNDATED["id"]] == ("resolved", NOW.isoformat())
        assert redis_state.store["feed"]["owed"] == []

    def test_partial_settlement_control_confirms_the_listing_and_is_not_owed(self, redis_state):
        """The listed leg is terminal and another leg still trades. The read
        confirms what the feed said, so nothing is owed — the last leg's own
        listing reaches the row later (test_an_event_whose_last_leg_settles_later)."""
        engine = _seed()
        report = _feed(engine, _Venue())
        assert report["stats"]["venue_partially_settled"] == 1
        assert report["stats"]["venue_read_unconfirmed"] == 0
        assert redis_state.store["feed"]["owed"] == []
        assert report["terminal"] == "complete"

    def test_a_listing_past_the_retention_floor_is_retired_by_name(self, redis_state):
        """Purged history, said as such: once the listing window is older than
        the venue's retention bound no read can confirm it, so it is not asked
        and is reported by name. A listing one day inside the bound is still asked."""
        engine = _seed(SPECIMENS + (dict(EARLY_UNDATED, id=9, external_id="KXGRAMMYAOTY-26"),))
        purged = NOW_TS - (sweep.PROVABLY_PURGED_AGE_DAYS * 86400) - 1
        inside = NOW_TS - ((sweep.PROVABLY_PURGED_AGE_DAYS - 1) * 86400)
        redis_state.store["feed"] = _feed_state(
            head=CEILING,
            owed=[EARLY_UNDATED["external_id"], "KXGRAMMYAOTY-26"],
            owed_meta={
                EARLY_UNDATED["external_id"]: {"since": purged, "legs": []},
                "KXGRAMMYAOTY-26": {"since": inside, "legs": []},
            },
        )
        venue = _Venue()
        venue.event_payload_for = {"KXGRAMMYAOTY-26": {"markets": []}}
        report = _feed(engine, venue)
        assert venue.asked == ["KXGRAMMYAOTY-26"]
        assert report["owed_retired_purged"] == 1
        assert report["owed_retired_tickers"] == [EARLY_UNDATED["external_id"]]
        assert redis_state.store["feed"]["owed"] == ["KXGRAMMYAOTY-26"]
        assert set(redis_state.store["feed"]["owed_meta"]) == {"KXGRAMMYAOTY-26"}
        assert report["terminal"] == "partial"

    def test_a_retirement_alone_reads_partial_not_complete(self, redis_state):
        purged = NOW_TS - (sweep.PROVABLY_PURGED_AGE_DAYS * 86400) - 1
        redis_state.store["feed"] = _feed_state(
            head=CEILING, owed=[EARLY_UNDATED["external_id"]],
            owed_meta={EARLY_UNDATED["external_id"]: {"since": purged, "legs": []}})
        report = _feed(_seed(), _Venue())
        assert report["terminal"] == "partial"
        assert "retention" in report["terminal_reason"]
        assert redis_state.store["feed"]["owed"] == []

    def test_an_undated_legacy_entry_is_dated_now_not_retired(self, redis_state):
        redis_state.store["feed"] = _feed_state(head=CEILING, owed=[EARLY_UNDATED["external_id"]])
        venue = _Venue()
        venue.event_payload_for = {EARLY_UNDATED["external_id"]: None}
        report = _feed(_seed(), venue)
        assert report["owed_retired_purged"] == 0
        assert redis_state.store["feed"]["owed_meta"][EARLY_UNDATED["external_id"]]["since"] == NOW_TS

    def test_a_dry_run_retires_nothing(self, redis_state):
        purged = NOW_TS - (sweep.PROVABLY_PURGED_AGE_DAYS * 86400) - 1
        redis_state.store["feed"] = _feed_state(
            head=CEILING, owed=[EARLY_UNDATED["external_id"]],
            owed_meta={EARLY_UNDATED["external_id"]: {"since": purged, "legs": []}})
        report = _feed(_seed(), _Venue(), apply=False)
        assert report["owed_retired_purged"] == 0
        assert redis_state.writes == []

    def test_the_population_sweep_reports_an_empty_read_by_name(self):
        """run_backfill's other callers get the same report key; their writes
        are unchanged (an empty read still writes nothing)."""
        engine = _seed()
        venue = _Venue()
        venue.event_payload_for = {EARLY_UNDATED["external_id"]: {"markets": []}}
        rows = [(EARLY_UNDATED["id"], EARLY_UNDATED["external_id"],
                 EARLY_UNDATED["resolution_date"], None, 3)]
        report = asyncio.run(sweep.run_backfill(
            session_maker=lambda: _SqliteSession(engine), client_factory=lambda: venue,
            apply=True, now=NOW, rows=rows))
        assert report["unconfirmed_tickers"] == [EARLY_UNDATED["external_id"]]
        assert report["errored_tickers"] == []
        assert report["stats"]["unresolvable_at_venue"] == 1
        assert report["stats"]["writes_applied"] == 0


def _at(hh_mm: str) -> int:
    """A 2026-10-13 UTC clock time as unix seconds (NOW is 04:23)."""
    hh, mm = hh_mm.split(":")
    return int(NOW.replace(hour=int(hh), minute=int(mm)).timestamp())


def _iso_at(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


class TestTheNextBeatReadsWhatTheVenueAlreadyListed:
    """CERT-4118's required repair 2722-NEXT-BEAT-SETTLED-HEAD. The beat fires
    at :x3. The old walk stopped five minutes short of the present, so a
    question listed settled at 04:19 was not read at 04:23 and closed at 04:33
    — fourteen minutes. The walk now reaches the present and re-reads the last
    five minutes on the next run, so late listings are still caught."""

    SPEC = dict(EARLY_UNDATED, id=21, external_id="KXGOLDENGLOBE-26")

    def _venue(self, *stamps):
        ticker = self.SPEC["external_id"]
        return _Venue(
            settled=[{"ticker": f"{ticker}-0", "event_ticker": ticker,
                      "settlement_ts": _iso_at(ts)} for ts in stamps],
            legs={ticker: _legs(ticker, ["finalized"], self.SPEC["resolution_date"])},
        )

    def _run(self, engine, venue, at: int):
        return asyncio.run(sweep.run_settled_feed(
            session_maker=lambda: _SqliteSession(engine), client_factory=lambda: venue,
            now=datetime.fromtimestamp(at, timezone.utc)))

    def test_listed_at_0419_closes_on_the_0423_beat(self, redis_state):
        redis_state.store["feed"] = _feed_state(head=_at("04:13"))
        engine = _seed(SPECIMENS + (self.SPEC,))
        report = self._run(engine, self._venue(_at("04:19")), _at("04:23"))
        assert _state(engine)[0][21] == ("resolved", NOW.isoformat())
        assert report["head_caught_up"] is True
        assert redis_state.store["feed"]["head"] == _at("04:23")

    def test_listed_one_second_after_a_beat_closes_on_the_next(self, redis_state):
        """The worst case of an already-listed settlement: one period."""
        redis_state.store["feed"] = _feed_state(head=_at("04:23"))
        engine = _seed(SPECIMENS + (self.SPEC,))
        at = _at("04:33")
        self._run(engine, self._venue(_at("04:23") + 1), at)
        assert _state(engine)[0][21] == ("resolved",
                                         datetime.fromtimestamp(at, timezone.utc).isoformat())

    def test_a_listing_late_at_0423_is_caught_by_the_0433_re_read(self, redis_state):
        """The hold's reason, kept: stamped 04:22 but not yet listed when the
        04:23 beat read to the present. The 04:33 beat re-reads from 04:18."""
        redis_state.store["feed"] = _feed_state(head=_at("04:13"))
        engine = _seed(SPECIMENS + (self.SPEC,))
        self._run(engine, self._venue(), _at("04:23"))  # not listed yet
        assert _state(engine)[0][21] == ("open", None)
        assert redis_state.store["feed"]["head"] == _at("04:23")

        at = _at("04:33")
        venue = self._venue(_at("04:22"))
        self._run(engine, venue, at)
        assert venue.pages[0]["min"] == _at("04:18")
        assert _state(engine)[0][21] == ("resolved",
                                         datetime.fromtimestamp(at, timezone.utc).isoformat())

    def test_the_re_read_is_the_head_only_and_once_per_run(self, redis_state):
        floor = _at("04:23") - 86400
        redis_state.store["feed"] = _feed_state(head=_at("03:53"), back=floor,
                                                back_end=floor + 1800)
        venue = self._venue()
        self._run(_seed(), venue, _at("04:23"))
        mins = [p["min"] for p in venue.pages]
        assert mins[0] == _at("03:48")  # the head's first window re-reads
        assert mins[1] == _at("04:08")  # its second starts at the watermark
        assert mins[2:] == [floor, floor + sweep.SETTLED_FEED_STEP_S]  # backlog, none


class TestTheRowCapIsLiteral:
    """CERT-4118's named follow-up 2722-ONE-SECOND-ROW-CAP: a one-second window
    bypassed ``max_rows``. And a window too big for the run must still narrow
    when owed retries have already spent part of the run's rows."""

    @staticmethod
    def _crowd(n, ts):
        rows = tuple(dict(EARLY_UNDATED, id=300 + i, external_id=f"KXCROWD-{i:03d}")
                     for i in range(n))
        settled = [{"ticker": f"{r['external_id']}-0", "event_ticker": r["external_id"],
                    "settlement_ts": _iso_at(ts)} for r in rows]
        legs = {r["external_id"]: _legs(r["external_id"], ["finalized"], r["resolution_date"])
                for r in rows}
        return rows, settled, legs

    def test_one_second_over_the_cap_asks_the_cap_and_owes_the_rest(self, redis_state):
        rows, settled, legs = self._crowd(3, LAST_RUN + 1)
        engine = _seed(rows)
        venue = _Venue(settled=settled, legs=legs)
        report = _feed(engine, venue, max_rows=2)
        assert len(venue.asked) == 2
        assert report["stats"]["candidates"] == 2
        assert redis_state.store["feed"]["owed"] == ["KXCROWD-002"]
        # Past the crowded second, then the run's rows are spent.
        assert redis_state.store["feed"]["head"] == LAST_RUN + 1
        assert report["head_stop"] == "row budget spent"

        venue = _Venue(settled=settled, legs=legs)
        _feed(engine, venue, max_rows=2)  # the debt is paid from the owed list
        assert redis_state.store["feed"]["head"] == CEILING
        assert redis_state.store["feed"]["owed"] == []
        assert all(_state(engine)[0][r["id"]][0] == "resolved" for r in rows)

    def test_owed_retries_do_not_hold_an_oversized_window_forever(self, redis_state):
        rows, settled, legs = self._crowd(3, LAST_RUN + 1)
        stuck = dict(EARLY_UNDATED, id=399, external_id="KXSTUCK-26")
        engine = _seed(rows + (stuck,))
        redis_state.store["feed"] = _feed_state(
            owed=["KXSTUCK-26"], owed_meta={"KXSTUCK-26": {"since": NOW_TS, "legs": []}})
        venue = _Venue(settled=settled, legs=legs)
        venue.event_error_for = {"KXSTUCK-26"}
        report = _feed(engine, venue, max_rows=3)
        assert report["stats"]["candidates"] <= 3
        assert redis_state.store["feed"]["head"] == LAST_RUN + 1  # moved past the crowd
        assert set(redis_state.store["feed"]["owed"]) == {"KXSTUCK-26", "KXCROWD-002"}


class TestTheBeat:
    def test_the_task_is_registered_and_scheduled_on_realtime(self):
        from app.tasks import celery_app

        entry = celery_app.conf.beat_schedule["settle-kalshi-settled-feed"]
        assert entry["task"] == "app.tasks.settle_kalshi_settled_feed"
        assert entry["options"]["queue"] == "realtime"
        assert entry["options"]["expires"] == 600
        assert "app.tasks.settle_kalshi_settled_feed" in celery_app.tasks

    def test_its_terminal_is_enforced(self):
        from app.utils import task_verdict

        assert "kalshi_settled_feed" in task_verdict.ENFORCED_TASKS


class TestTheClientSendsTheBoundsOnlyWhenAsked:
    def _service(self, captured):
        from app.services.kalshi_api import KalshiAPIService

        class _Resp:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"markets": [], "cursor": None}

        class _Client:
            async def get(self, url, params=None):
                captured.append(params)
                return _Resp()

        svc = KalshiAPIService.__new__(KalshiAPIService)
        svc.client = _Client()
        return svc

    def test_default_call_sends_exactly_the_params_it_always_sent(self):
        captured: list = []
        asyncio.run(self._service(captured).get_markets(status="settled", event_ticker="X"))
        assert captured == [{"limit": 1000, "status": "settled", "event_ticker": "X"}]

    def test_the_feed_call_sends_both_bounds_and_the_combo_filter(self):
        captured: list = []
        asyncio.run(self._service(captured).get_markets(
            status="settled", min_settled_ts=10, max_settled_ts=20, mve_filter="exclude"))
        assert captured[0]["min_settled_ts"] == 10
        assert captured[0]["max_settled_ts"] == 20
        assert captured[0]["mve_filter"] == "exclude"
