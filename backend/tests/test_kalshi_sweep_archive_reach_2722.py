"""#2722 — a Kalshi question whose legs have moved to the venue's archive stops looking open.

WHAT WAS WRONG, MEASURED. Measurement's 2026-10-15 exact-nine read (18 public
GETs, all HTTP 200, saved verbatim under
``tests/fixtures/kalshi_2722_archived_nine/``): for nine events we still hold as
``status='open'``, the live ``/markets?event_ticker=`` listing is empty and the
``/historical/markets?event_ticker=`` listing holds every leg, 80/80
``finalized``. The DB read straight after confirmed all nine still ``open``.

WHY NO RUN COULD FIX THEM, read off the current source:

1. THE READ. The sweep reads a candidate with ``get_event(...,
   with_nested_markets=True)``, and GetEvent omits archived legs (Kalshi's
   openapi: "Historical markets settled before the historical cutoff will not be
   included"). The event comes back with no markets, the row is
   ``unresolvable_at_venue``, nothing is written.
2. THE WINDOW. The population sweep's batch is ``[offset, offset+500)`` of an
   ordering led by two sticky ranks (played-game band, fully-retracted cohort).
   Every row in the window is written and rotates only within its own rank, so
   the offset holds and rows in neither rank — all nine — are never selected
   (2026-10-15 04:21Z run: offset 5, ``stranded 0``, ``unresolvable 0``). Two
   of the nine are also behind the 86-day retention floor.

WHAT THIS FILE HOLDS. The saved bytes driven through the REAL
``KalshiAPIService`` (over an httpx mock transport) and the real selection and
write, on a SQLite table seeded with the nine rows' production values (read
2026-10-15T21:1xZ): the beat's own ``run_sweep`` settles all nine through the
archive walk. Then the window lock reproduced, the walk's keyset cursor, and
the controls the directive names: partial, empty, malformed, wrong event,
cursor, 429, budget — each leaves the row open. Statuses only: no grade.

CLOCK DISCIPLINE (gotcha #44): ``NOW`` is a literal and is passed to every run.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, text

from app.services.kalshi_api import KalshiAPIService
from app.tasks import kalshi_resolution_sweep as sweep

FIXTURES = Path(__file__).parent / "fixtures" / "kalshi_2722_archived_nine"

#: Measurement's collection instant, to the hour. A literal, never `utcnow()`.
NOW = datetime(2026, 10, 15, 21, 0, tzinfo=timezone.utc)

#: The nine rows as production held them (futures_markets read 2026-10-15
#: ~21:1xZ): id, external_id, commence_time, market_tier, updated_at,
#: resolution_date. `expiration_time` is NULL on all nine.
NINE = [
    (109776, "KXTXPRIMARY-04R26", "2027-11-03T15:00:00+00:00", 2,
     "2026-06-23T18:40:05+00:00", "2027-11-03T15:00:00+00:00"),
    (110337, "KXWALESPARLIAMENT-26MAY07", "2027-05-07T14:00:00+00:00", 2,
     "2026-05-11T18:41:56+00:00", "2027-05-07T14:00:00+00:00"),
    (110749, "KXPGAAWARDS-26-LIM", "2027-02-28T15:00:00+00:00", 3,
     "2026-09-25T03:06:56+00:00", "2027-02-28T15:00:00+00:00"),
    (925648, "KXPAXTONPRIMARYCOUNTIES-26", "2027-03-03T15:00:00+00:00", 2,
     "2026-07-21T05:54:31+00:00", "2027-03-03T15:00:00+00:00"),
    (925724, "KXTALARICOPRIMARYCOUNTIES-26", "2027-03-03T15:00:00+00:00", 2,
     "2026-06-27T00:40:00+00:00", "2027-03-03T15:00:00+00:00"),
    (1631094, "KXINPRIMARY-01D26", "2027-11-03T15:00:00+00:00", 2,
     "2026-07-19T09:06:08+00:00", "2027-11-03T15:00:00+00:00"),
    (3452978, "KXNEXTTEAMNFL-26THENDRICKSON", "2026-12-01T04:59:00+00:00", 5,
     "2026-06-30T17:07:16+00:00", "2026-12-08T15:00:00+00:00"),
    (11757847, "KXPRIMARYTURNOUT-SENATETXR26", "2026-06-12T20:46:58+00:00", 2,
     "2026-08-12T16:49:04+00:00", "2027-05-26T14:00:00+00:00"),
    (54069617, "KXDNCAUTOPSY-26", "2026-05-21T14:40:24+00:00", 2,
     "2026-07-18T14:49:03+00:00", "2026-11-10T15:00:00+00:00"),
]
IDS = [r[0] for r in NINE]
TICKER = {r[0]: r[1] for r in NINE}
#: Behind the 86-day floor at NOW (2026-07-21T21:00Z).
PAST_FLOOR = {11757847, 54069617}


# ---------------------------------------------------------------------------
# The saved bytes
# ---------------------------------------------------------------------------


def _manifest() -> dict:
    return json.loads((FIXTURES / "manifest.json").read_text())


def _saved() -> dict:
    """event ticker -> {"live": bytes, "archive": bytes}, hash-checked."""
    out: dict = {}
    for entry in _manifest()["responses"]:
        raw = (FIXTURES / entry["file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"], entry["file"]
        url = httpx.URL(entry["url"])
        ticker = url.params["event_ticker"]
        kind = "archive" if "/historical/" in url.path else "live"
        out.setdefault(ticker, {})[kind] = raw
    return out


class TestTheSavedBytes:
    def test_eighteen_responses_hash_to_measurements_record(self):
        saved = _saved()
        assert sorted(saved) == sorted(TICKER.values())
        assert all(set(v) == {"live", "archive"} for v in saved.values())

    def test_every_live_listing_is_empty_and_every_archive_is_exhausted(self):
        legs = 0
        for ticker, pair in _saved().items():
            live = json.loads(pair["live"])
            archive = json.loads(pair["archive"])
            assert live == {"cursor": "", "markets": []}, ticker
            assert archive["cursor"] == "", ticker
            assert archive["markets"], ticker
            assert {m["event_ticker"] for m in archive["markets"]} == {ticker}
            assert {m["status"] for m in archive["markets"]} == {"finalized"}
            legs += len(archive["markets"])
        assert legs == 80


# ---------------------------------------------------------------------------
# The rig: the real service over a mock transport, a real seeded table
# ---------------------------------------------------------------------------


class Venue:
    """Serves GetEvent and /historical/markets per event; counts every request.

    GetEvent answers the event with the LIVE listing's markets — the saved live
    listing is the evidence that no leg is still in the live set, and GetEvent's
    documented behaviour is to omit archived legs. ``archive`` maps a ticker to
    a list of page handlers (bytes, or an ``httpx.Response``), served in order.
    """

    def __init__(self, live: dict, archive: dict, events: dict | None = None):
        self.live = live
        self.archive = {k: list(v) for k, v in archive.items()}
        self.events = events or {}
        self.event_reads: list[str] = []
        self.archive_reads: list[tuple[str, str | None]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/historical/markets" in path:
            ticker = request.url.params.get("event_ticker")
            self.archive_reads.append((ticker, request.url.params.get("cursor")))
            pages = self.archive.get(ticker)
            if not pages:
                return httpx.Response(200, json={"cursor": "", "markets": []})
            page = pages.pop(0)
            if isinstance(page, httpx.Response):
                return page
            return httpx.Response(200, content=page)
        if "/events/" in path:
            ticker = path.rsplit("/", 1)[-1]
            self.event_reads.append(ticker)
            if ticker in self.events:
                return self.events[ticker]
            markets = json.loads(self.live[ticker])["markets"]
            return httpx.Response(
                200, json={"event": {"event_ticker": ticker, "markets": markets}}
            )
        return httpx.Response(404)

    def service(self) -> KalshiAPIService:
        svc = KalshiAPIService(api_key="")
        svc.client = httpx.AsyncClient(transport=httpx.MockTransport(self.handler))
        return svc


def _venue(**overrides) -> Venue:
    saved = _saved()
    live = {t: v["live"] for t, v in saved.items()}
    archive = {t: [v["archive"]] for t, v in saved.items()}
    archive.update(overrides.pop("archive", {}))
    return Venue(live, archive, **overrides)


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def _seed(rows=NINE):
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(
            """CREATE TABLE futures_markets (
                id INTEGER PRIMARY KEY, external_id TEXT, source TEXT, status TEXT,
                market_tier INTEGER, commence_time TEXT, resolution_date TEXT,
                expiration_time TEXT, settled_at TEXT, updated_at TEXT)"""
        ))
        conn.execute(text(
            """CREATE TABLE futures_outcomes (
                id INTEGER PRIMARY KEY, market_id INTEGER,
                resolution_source TEXT, is_winner BOOLEAN)"""
        ))
        for mid, ticker, commence, tier, updated, rd in rows:
            conn.execute(
                text(
                    """INSERT INTO futures_markets (id, external_id, source, status,
                        market_tier, commence_time, resolution_date, expiration_time,
                        settled_at, updated_at)
                       VALUES (:id, :t, 'kalshi', 'open', :tier, :c, :rd, NULL,
                               NULL, :u)"""
                ),
                {"id": mid, "t": ticker, "tier": tier, "c": commence, "rd": rd,
                 "u": updated},
            )
            conn.execute(
                text(
                    "INSERT INTO futures_outcomes (market_id, resolution_source, "
                    "is_winner) VALUES (:id, NULL, NULL)"
                ),
                {"id": mid},
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
                (r[0], r[1],
                 *(datetime.fromisoformat(v) if v else None for v in r[2:4]), r[4])
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


def _state(engine) -> dict:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, status, settled_at FROM futures_markets ORDER BY id")
        ).all()
    return {r[0]: (r[1], r[2]) for r in rows}


def _grades(engine) -> list:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT market_id, resolution_source, is_winner FROM futures_outcomes "
                 "ORDER BY market_id")
        ).all()


async def _backfill(engine, venue, **kw):
    kw.setdefault("archive_requests", sweep.ARCHIVE_REQUESTS_PER_RUN)
    return await sweep.run_backfill(
        session_maker=lambda: _SqliteSession(engine),
        client_factory=venue.service,
        limit=500,
        apply=True,
        now=NOW,
        **kw,
    )


async def _walk(engine, venue, **kw):
    """One pinned archive-walk batch from the head (no Redis cursor)."""
    kw.setdefault("after_id", 0)
    return await sweep.run_archive_settlements(
        session_maker=lambda: _SqliteSession(engine),
        client_factory=venue.service,
        now=NOW,
        **kw,
    )


@pytest.fixture
def beat(monkeypatch):
    """`run_sweep` with both cursors in memory and every run pinned to NOW."""
    store = {"walk": 0, "walk_writes": []}

    async def _persist(offset, scanned):
        return True

    async def _read_walk():
        return store["walk"]

    async def _write_walk(after_id):
        store["walk_writes"].append(after_id)
        store["walk"] = after_id
        return True

    monkeypatch.setattr(sweep, "_write_cursor", _persist)
    # raising=False so the pre-#2722 head runs this rig and fails on the ROWS,
    # not on a missing name — the red-first run is the real defect.
    monkeypatch.setattr(sweep, "_read_walk_cursor", _read_walk, raising=False)
    monkeypatch.setattr(sweep, "_write_walk_cursor", _write_walk, raising=False)
    real = sweep.run_backfill

    async def _pinned(**kw):
        return await real(**{**kw, "now": NOW})

    monkeypatch.setattr(sweep, "run_backfill", _pinned)
    return store


async def _run_sweep(engine, venue, **kw):
    return await sweep.run_sweep(
        offset=0,
        session_maker=lambda: _SqliteSession(engine),
        client_factory=venue.service,
        **kw,
    )


# ---------------------------------------------------------------------------
# 1. The ship, red-first: the daily beat's own entry point settles all nine
# ---------------------------------------------------------------------------


class TestTheActivatedSweepSettlesTheNine:
    async def test_run_sweep_settles_all_nine(self, beat):
        """RED on the pre-#2722 head: every row stays `open`. The sweep's own
        entry point with the walk switched on, not a helper — "reached, not
        simply supported by an unused helper". The beat does not switch it on
        yet: see :class:`TestTheBeatDoesNotActivateTheWalk`."""
        engine = _seed()
        venue = _venue()
        report = await _run_sweep(engine, venue, archive_walk=True)

        state = _state(engine)
        assert {mid: s for mid, (s, _) in state.items()} == {
            mid: "resolved" for mid in IDS
        }, report.get("archive_walk", {}).get("stats")
        assert all(settled for _, settled in state.values())
        walk = report["archive_walk"]
        assert walk["terminal"] == "complete"
        assert walk["stats"]["venue_settled_from_archive"] == 9
        assert walk["stats"]["archive_read"] == 9
        assert walk["stats"]["archive_requests"] == 9
        assert {s["id"] for s in walk["archive_settled_samples"]} == set(IDS)
        # A short batch is the end of the population: the next walk restarts.
        assert beat["walk_writes"] == [0]

    async def test_the_population_batch_alone_leaves_all_nine_open(self, beat):
        """The defect, on the same rig: the population batch reads 7 (2 are
        behind the floor), gets no legs for any, and writes nothing."""
        engine = _seed()
        venue = _venue()
        report = await _run_sweep(engine, venue, archive_walk=False)

        assert {s for s, _ in _state(engine).values()} == {"open"}
        assert venue.archive_reads == []
        assert report["stats"]["candidates"] == 7
        assert report["stats"]["unresolvable_at_venue"] == 7
        assert "archive_walk" not in report

    async def test_no_grade_is_written(self, beat):
        engine = _seed()
        before = _grades(engine)
        await _run_sweep(engine, _venue(), archive_walk=True)
        assert _grades(engine) == before
        assert all(r[1] is None and r[2] is None for r in before)

    async def test_run_backfills_default_reads_no_archive(self):
        """Only the walk opts in: the population batch, the CLI, the settled
        feed and the event-driven arms keep their old reads."""
        engine = _seed()
        venue = _venue()
        await sweep.run_backfill(
            session_maker=lambda: _SqliteSession(engine),
            client_factory=venue.service,
            limit=500,
            apply=True,
            now=NOW,
        )
        assert venue.archive_reads == []
        assert {s for s, _ in _state(engine).values()} == {"open"}

    async def test_a_failed_walk_does_not_read_green_or_lose_the_batch(
        self, beat, monkeypatch
    ):
        async def _boom(**kw):
            raise RuntimeError("walk exploded")

        monkeypatch.setattr(sweep, "run_archive_settlements", _boom)
        engine = _seed()
        # One active live leg per event, so the population batch writes all 7
        # it selects and would read `complete` on its own.
        events = {}
        for t in TICKER.values():
            leg = copy.deepcopy(_archive_body(t)["markets"][0])
            leg.update(status="active", close_time="2027-12-01T00:00:00Z",
                       expiration_time="2027-12-01T00:00:00Z")
            events[t] = httpx.Response(
                200, json={"event": {"event_ticker": t, "markets": [leg]}}
            )
        report = await _run_sweep(engine, _venue(events=events), archive_walk=True)
        assert report["stats"]["writes_applied"] == 7
        assert report["archive_walk"]["terminal"] == "failed"
        assert "walk exploded" in report["archive_walk"]["terminal_reason"]
        assert report["terminal"] == "partial"
        assert "archive walk failed" in report["terminal_reason"]

    async def test_a_dry_run_sweep_never_walks(self, beat):
        engine = _seed()
        venue = _venue()
        report = await _run_sweep(engine, venue, apply=False, archive_walk=True)
        assert "archive_walk" not in report
        assert venue.archive_reads == []


    async def test_a_walk_left_owed_makes_the_night_partial(self, beat, monkeypatch):
        """Debt is not a finished night: a walk that ran out of page budget
        turns a complete population batch `partial`, and says why."""
        engine = _seed()
        # One active live leg per event, so the population batch writes all 7
        # it selects and reads `complete` on its own.
        events = {}
        for t in TICKER.values():
            leg = copy.deepcopy(_archive_body(t)["markets"][0])
            leg.update(status="active", close_time="2027-12-01T00:00:00Z",
                       expiration_time="2027-12-01T00:00:00Z")
            events[t] = httpx.Response(
                200, json={"event": {"event_ticker": t, "markets": [leg]}}
            )
        real_walk = sweep.run_archive_settlements

        async def _two_pages(**kw):
            # The walk reads a legless venue with a two-page budget, so seven
            # of the nine are left owed.
            return await real_walk(**{**kw, "client_factory": _venue().service,
                                      "archive_requests": 2, "concurrency": 1})

        monkeypatch.setattr(sweep, "run_archive_settlements", _two_pages)
        report = await _run_sweep(engine, _venue(events=events), archive_walk=True)

        assert report["stats"]["writes_applied"] == 7
        walk = report["archive_walk"]
        assert walk["terminal"] == "partial"
        assert len(walk["archive_owed_tickers"]) == 7
        assert "7 rows owed" in walk["terminal_reason"]
        assert "page budget spent" in walk["terminal_reason"]
        assert report["terminal"] == "partial"
        assert "archive walk partial" in report["terminal_reason"]


# ---------------------------------------------------------------------------
# 1b. The activation boundary: deploying this code writes nothing historical
# ---------------------------------------------------------------------------


class TestTheBeatDoesNotActivateTheWalk:
    """#2722's directive reserves the historical apply; Root's 2026-10-15 hold
    found the first presentation activated it on deploy. The walk is OFF unless
    a caller passes ``archive_walk=True``, and the beat does not."""

    async def test_the_sweep_called_as_the_beat_calls_it_reads_no_archive(self, beat):
        engine = _seed()
        venue = _venue()
        # Exactly the beat's arguments (limit, concurrency) plus the rig.
        report = await sweep.run_sweep(
            limit=sweep.SWEEP_BATCH_LIMIT,
            concurrency=sweep.SWEEP_CONCURRENCY,
            offset=0,
            session_maker=lambda: _SqliteSession(engine),
            client_factory=venue.service,
        )
        assert venue.archive_reads == []
        assert beat["walk_writes"] == []
        assert "archive_walk" not in report
        assert {s for s, _ in _state(engine).values()} == {"open"}

    def test_the_beat_task_does_not_pass_archive_walk(self):
        """Pinned on the task's own call: the one place that could switch the
        walk on in production passes only `limit` and `concurrency`."""
        import ast
        import inspect

        from app import tasks

        tree = ast.parse(inspect.getsource(tasks))
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and getattr(node.func, "id", None) == "run_sweep"
        ]
        assert len(calls) == 1, "the beat's run_sweep call moved; re-pin it"
        assert sorted(k.arg for k in calls[0].keywords) == ["concurrency", "limit"]
        assert not calls[0].args

    def test_nothing_in_the_app_calls_the_walk(self):
        """`run_archive_settlements` is reachable only through run_sweep's
        opt-in; no other app module names it."""
        import pathlib

        app_dir = pathlib.Path(sweep.__file__).resolve().parents[1]
        callers = [
            str(f.relative_to(app_dir)) for f in app_dir.rglob("*.py")
            if "run_archive_settlements" in f.read_text()
        ]
        assert callers == ["tasks/kalshi_resolution_sweep.py"]


# ---------------------------------------------------------------------------
# 2. Reach: the walk selects what the population window cannot
# ---------------------------------------------------------------------------


def _window(engine, limit=500, offset=5):
    purge_floor = NOW - timedelta(days=sweep.PROVABLY_PURGED_AGE_DAYS)
    tokens = sweep.past_event_band_tokens(NOW)
    with engine.connect() as conn:
        return conn.execute(
            text(sweep.banded_select_sql(len(tokens))),
            {"purge_floor": purge_floor.isoformat(), "limit": limit,
             "offset": offset, **sweep.band_bind_params(tokens)},
        ).all()


def _retracted_cohort(engine, n, first_id=20_000_000):
    """`n` open rows in #7000's promoted cohort — every leg retracted."""
    with engine.begin() as conn:
        for i in range(n):
            mid = first_id + i
            conn.execute(
                text(
                    """INSERT INTO futures_markets (id, external_id, source, status,
                        market_tier, commence_time, resolution_date, expiration_time,
                        settled_at, updated_at)
                       VALUES (:id, :t, 'kalshi', 'open', 1, :c, :rd, NULL, NULL, :u)"""
                ),
                {"id": mid, "t": f"KXRETRACTED-{i}", "c": "2027-01-01T00:00:00+00:00",
                 "rd": "2027-01-01T00:00:00+00:00", "u": NOW.isoformat()},
            )
            conn.execute(
                text("INSERT INTO futures_outcomes (market_id, resolution_source, "
                     "is_winner) VALUES (:id, :src, NULL)"),
                {"id": mid, "src": sweep.RETRACTION_SOURCE},
            )


class TestTheWalkReachesWhatTheWindowCannot:
    def test_the_window_is_locked_on_the_promoted_cohort(self):
        """The production shape: >505 promoted rows hold every slot of the
        window, however fresh their stamps and however stale the nine's."""
        engine = _seed()
        _retracted_cohort(engine, 600)
        ids = {r[0] for r in _window(engine)}
        assert len(ids) == 500
        assert not ids & set(IDS)

    def test_the_window_never_selects_the_past_floor_pair(self):
        ids = {r[0] for r in _window(_seed(), offset=0)}
        assert ids == set(IDS) - PAST_FLOOR

    def test_the_walk_selects_every_open_row_by_id(self):
        engine = _seed()
        _retracted_cohort(engine, 600)
        with engine.connect() as conn:
            rows = conn.execute(
                text(sweep.ARCHIVE_WALK_SELECT_SQL), {"after_id": 0, "limit": 2000}
            ).all()
        ids = [r[0] for r in rows]
        assert ids == sorted(ids)
        assert set(IDS) <= set(ids)
        assert len(rows[0]) == 5

    def test_the_walk_skips_rows_that_are_not_open(self):
        engine = _seed()
        with engine.begin() as conn:
            conn.execute(text("UPDATE futures_markets SET status = 'resolved' "
                              "WHERE id = 54069617"))
        with engine.connect() as conn:
            ids = {r[0] for r in conn.execute(
                text(sweep.ARCHIVE_WALK_SELECT_SQL), {"after_id": 0, "limit": 50}
            ).all()}
        assert ids == set(IDS) - {54069617}


class TestTheWalkCursor:
    ROWS = [(1, "A"), (2, "B"), (3, "C")]

    def test_a_short_batch_wraps_to_the_head(self):
        assert sweep.next_archive_walk_cursor(self.ROWS, set(), limit=10) == 0

    def test_a_full_batch_moves_past_its_last_row(self):
        assert sweep.next_archive_walk_cursor(self.ROWS, set(), limit=3) == 3

    def test_a_full_batch_stops_before_its_first_owed_row(self):
        assert sweep.next_archive_walk_cursor(self.ROWS, {"B", "C"}, limit=3) == 1

    def test_a_short_batch_stops_before_its_first_owed_row(self):
        """CERT-4137: owed debt outranks the wrap. The end of the population is
        not the end of the run's debt."""
        assert sweep.next_archive_walk_cursor(self.ROWS, {"C"}, limit=10) == 2

    async def test_a_head_that_spends_the_budget_cannot_starve_the_tail(self, beat):
        """CERT-4137's control, at production defaults (1,000 rows, 1,200
        archive pages, concurrency 6) through the real service and the real
        select+write: 240 earlier open events whose archive listings run past
        the per-event page bound spend 5 pages each — the whole budget — before
        the nine are admitted.

        RED on 91f29374fe: the batch is short, so the cursor wrapped to 0 with
        all nine owed, and every later night spent the same 1,200 pages on the
        same head; the nine stayed open forever while the walk read `complete`.
        Here the first night stops before the first owed specimen and says
        `partial`; the second starts there and settles all nine."""
        head = [(i, f"KXHEAD-{i}", None, 3, None, None) for i in range(1, 241)]
        engine = _seed(head + NINE)

        def venue_for_night():
            venue = _venue()
            for _, ticker, *_ in head:
                venue.live[ticker] = b'{"markets":[],"cursor":""}'
                venue.archive[ticker] = [
                    json.dumps({"cursor": f"page{n + 1}", "markets": [{
                        "ticker": f"{ticker}-LEG{n}", "event_ticker": ticker,
                        "status": "finalized", "result": "yes"}]}).encode()
                    for n in range(sweep.ARCHIVE_EVENT_MAX_PAGES + 1)
                ]
            return venue

        nights = []
        for _ in range(2):
            venue = venue_for_night()
            report = await sweep.run_archive_settlements(
                session_maker=lambda: _SqliteSession(engine),
                client_factory=venue.service,
                now=NOW,
            )
            nights.append((report, venue, _state(engine)))

        (first, _v1, after_first), (second, v2, after_second) = nights
        assert first["after_id"] == 0
        assert first["stats"]["archive_requests"] == sweep.ARCHIVE_REQUESTS_PER_RUN
        assert first["stats"]["archive_truncated"] == 240
        assert sorted(first["archive_owed_tickers"]) == sorted(TICKER.values())
        assert first["next_after_id"] == min(IDS) - 1
        assert first["terminal"] == "partial"
        assert first["cycle_wrapped"] is False
        assert {after_first[i][0] for i in IDS} == {"open"}

        assert second["after_id"] == min(IDS) - 1
        assert {t for t, _ in v2.archive_reads} == set(TICKER.values())
        assert second["stats"]["archive_requests"] == 9
        assert second["archive_owed_tickers"] == []
        assert second["terminal"] == "complete"
        assert second["next_after_id"] == 0 and second["cycle_wrapped"] is True
        assert beat["walk_writes"] == [min(IDS) - 1, 0]
        assert {after_second[i][0] for i in IDS} == {"resolved"}
        # The head stays open: a listing past the page bound is unread, not
        # settled.
        assert {after_second[i][0] for i in range(1, 241)} == {"open"}

    async def test_the_walk_resumes_from_its_persisted_position(self, beat):
        engine = _seed()
        venue = _venue()
        beat["walk"] = 925724  # resume just past the fifth specimen
        report = await sweep.run_archive_settlements(
            session_maker=lambda: _SqliteSession(engine),
            client_factory=venue.service,
            now=NOW,
        )
        assert report["after_id"] == 925724
        assert {t for t, _ in venue.archive_reads} == {
            TICKER[i] for i in IDS if i > 925724
        }
        assert report["next_after_id"] == 0 and beat["walk_writes"] == [0]

    async def test_a_429_holds_the_cursor_at_the_first_unread_row(self, beat):
        engine = _seed()
        venue = _venue(archive={
            t: [httpx.Response(429, headers={"Retry-After": "5"})]
            for t in TICKER.values()
        })
        report = await sweep.run_archive_settlements(
            session_maker=lambda: _SqliteSession(engine),
            client_factory=venue.service,
            limit=9,
            concurrency=1,
            now=NOW,
        )
        assert report["next_after_id"] == min(IDS) - 1
        assert beat["walk_writes"] == [min(IDS) - 1]
        assert report["terminal"] == "partial"
        assert "archive 429" in report["terminal_reason"]

    async def test_every_row_refused_by_the_venue_is_still_a_failed_walk(self, beat):
        """The 429 carve-out is only for rows our circuit held back: nine real
        archive errors are an outage, not debt."""
        engine = _seed()
        venue = _venue(archive={t: [httpx.Response(500)] for t in TICKER.values()})
        report = await sweep.run_archive_settlements(
            session_maker=lambda: _SqliteSession(engine),
            client_factory=venue.service,
            now=NOW,
        )
        assert report["stats"]["archive_error"] == 9
        assert report["archive_owed_tickers"] == []
        assert report["terminal"] == "failed"

    async def test_an_unpersisted_cursor_is_a_failed_walk(self, beat, monkeypatch):
        async def _fail(after_id):
            return False

        monkeypatch.setattr(sweep, "_write_walk_cursor", _fail)
        report = await sweep.run_archive_settlements(
            session_maker=lambda: _SqliteSession(_seed()),
            client_factory=_venue().service,
            now=NOW,
        )
        assert report["terminal"] == "failed"
        assert report["cursor_persisted"] is False


# ---------------------------------------------------------------------------
# 3. Controls: every short read leaves the row open and owed
# ---------------------------------------------------------------------------


def _archive_body(ticker) -> dict:
    return json.loads(_saved()[ticker]["archive"])


def _one(ticker):
    return [r for r in NINE if r[1] == ticker]


class TestEveryShortReadLeavesTheRowOpen:
    async def test_a_pending_leg_in_the_archive_keeps_the_row_open(self):
        t = "KXTXPRIMARY-04R26"
        body = _archive_body(t)
        body["markets"][0]["status"] = "active"
        engine = _seed(_one(t))
        report = await _walk(
            engine, _venue(archive={t: [json.dumps(body).encode()]})
        )
        assert _state(engine)[109776][0] == "open"
        assert report["stats"]["archive_read"] == 1
        assert report["stats"]["venue_partially_settled"] == 1
        assert report["stats"]["venue_settled"] == 0

    async def test_a_live_pending_leg_is_never_overruled_by_the_archive(self):
        t = "KXTXPRIMARY-04R26"
        live_leg = copy.deepcopy(_archive_body(t)["markets"][0])
        live_leg["status"] = "active"
        engine = _seed(_one(t))
        venue = _venue(events={t: httpx.Response(
            200, json={"event": {"event_ticker": t, "markets": [live_leg]}}
        )})
        report = await _walk(engine, venue)
        assert venue.archive_reads == []
        assert _state(engine)[109776][0] == "open"
        assert report["stats"]["archive_walk_live_rows"] == 1

    async def test_a_live_settled_event_is_left_to_the_live_arms(self):
        """The walk writes only what the ARCHIVE proved; a finalized event still
        in the live set belongs to the settled feed and the population sweep."""
        t = "KXINPRIMARY-01D26"
        legs = _archive_body(t)["markets"]
        engine = _seed(_one(t))
        venue = _venue(events={t: httpx.Response(
            200, json={"event": {"event_ticker": t, "markets": legs}}
        )})
        report = await _walk(engine, venue)
        assert venue.archive_reads == []
        assert _state(engine)[1631094][0] == "open"
        assert report["stats"]["archive_walk_live_rows"] == 1

    async def test_an_exhausted_empty_archive_is_not_a_settlement(self):
        t = "KXDNCAUTOPSY-26"
        engine = _seed(_one(t))
        report = await _walk(
            engine, _venue(archive={t: [b'{"cursor":"","markets":[]}']})
        )
        assert _state(engine)[54069617][0] == "open"
        assert report["stats"]["archive_empty"] == 1
        assert report["unconfirmed_tickers"] == [t]

    async def test_a_malformed_page_is_error_debt(self):
        t = "KXDNCAUTOPSY-26"
        engine = _seed(_one(t))
        report = await _walk(
            engine, _venue(archive={t: [b'{"cursor":"","markets":null}']})
        )
        assert _state(engine)[54069617][0] == "open"
        assert report["stats"]["archive_malformed"] == 1
        assert report["errored_tickers"] == [t]

    async def test_a_leg_from_another_event_refuses_the_whole_listing(self):
        t = "KXPGAAWARDS-26-LIM"
        body = _archive_body(t)
        body["markets"][2]["event_ticker"] = "KXPGAAWARDS-26-POY"
        engine = _seed(_one(t))
        report = await _walk(
            engine, _venue(archive={t: [json.dumps(body).encode()]})
        )
        assert _state(engine)[110749][0] == "open"
        assert report["stats"]["archive_wrong_event"] == 1

    async def test_a_repeated_ticker_refuses_the_listing(self):
        t = "KXPGAAWARDS-26-LIM"
        body = _archive_body(t)
        body["markets"].append(copy.deepcopy(body["markets"][0]))
        engine = _seed(_one(t))
        report = await _walk(
            engine, _venue(archive={t: [json.dumps(body).encode()]})
        )
        assert _state(engine)[110749][0] == "open"
        assert report["stats"]["archive_malformed"] == 1

    async def test_a_two_page_listing_is_followed_to_the_end(self):
        t = "KXNEXTTEAMNFL-26THENDRICKSON"
        legs = _archive_body(t)["markets"]
        p1 = json.dumps({"cursor": "c2", "markets": legs[:20]}).encode()
        p2 = json.dumps({"cursor": "", "markets": legs[20:]}).encode()
        engine = _seed(_one(t))
        venue = _venue(archive={t: [p1, p2]})
        report = await _walk(engine, venue)
        assert _state(engine)[3452978][0] == "resolved"
        assert venue.archive_reads == [(t, None), (t, "c2")]
        assert report["stats"]["archive_requests"] == 2

    async def test_a_page_that_has_not_yet_named_the_pending_leg_is_not_the_end(self):
        """Settling off page one would miss a pending leg on page two."""
        t = "KXNEXTTEAMNFL-26THENDRICKSON"
        legs = _archive_body(t)["markets"]
        legs[-1] = {**legs[-1], "status": "active"}
        p1 = json.dumps({"cursor": "c2", "markets": legs[:20]}).encode()
        p2 = json.dumps({"cursor": "", "markets": legs[20:]}).encode()
        engine = _seed(_one(t))
        await _walk(engine, _venue(archive={t: [p1, p2]}))
        assert _state(engine)[3452978][0] == "open"

    async def test_a_repeated_cursor_is_refused(self):
        t = "KXNEXTTEAMNFL-26THENDRICKSON"
        legs = _archive_body(t)["markets"]
        p1 = json.dumps({"cursor": "c2", "markets": legs[:20]}).encode()
        p2 = json.dumps({"cursor": "c2", "markets": legs[20:]}).encode()
        engine = _seed(_one(t))
        report = await _walk(engine, _venue(archive={t: [p1, p2]}))
        assert _state(engine)[3452978][0] == "open"
        assert report["stats"]["archive_malformed"] == 1

    async def test_a_listing_still_going_at_the_page_bound_is_unread(self):
        t = "KXNEXTTEAMNFL-26THENDRICKSON"
        legs = _archive_body(t)["markets"]
        pages = [
            json.dumps({"cursor": f"c{i + 1}", "markets": [legs[i]]}).encode()
            for i in range(sweep.ARCHIVE_EVENT_MAX_PAGES + 1)
        ]
        engine = _seed(_one(t))
        report = await _walk(engine, _venue(archive={t: pages}))
        assert _state(engine)[3452978][0] == "open"
        assert report["stats"]["archive_truncated"] == 1
        assert report["stats"]["archive_requests"] == sweep.ARCHIVE_EVENT_MAX_PAGES

    async def test_a_429_stops_every_later_archive_read_in_the_run(self):
        # SERIAL case (concurrency 1): nothing else is in flight, so exactly
        # ONE request is the proof the circuit held, whichever row the
        # selection reaches first. Production runs at 6 — see the next test.
        engine = _seed()
        venue = _venue(archive={
            t: [httpx.Response(429, headers={"Retry-After": "5"})]
            for t in TICKER.values()
        })
        report = await _walk(engine, venue, concurrency=1)

        stats = report["stats"]
        assert len(venue.archive_reads) == 1, venue.archive_reads
        assert stats["archive_requests"] == 1
        assert stats["archive_rate_limited"] == 9
        assert stats["archive_rate_limit_stop"] == f"429 on {venue.archive_reads[0][0]}"
        assert {s for s, _ in _state(engine).values()} == {"open"}
        assert sorted(report["errored_tickers"]) == sorted(TICKER.values())

    async def test_a_429_at_production_concurrency_stops_admission_not_flight(self):
        """CERT-4137's in-flight contract, at ``SWEEP_CONCURRENCY``. Every
        listing answers 429 after a delay, so the reads admitted before the
        first answer are all in flight together. The circuit stops ADMISSION:
        at most `concurrency` requests start, every one of them before the first
        429 came back, none after; all nine stay open and owed."""
        import asyncio

        engine = _seed()
        venue = _venue()
        log: list[str] = []
        original = venue.handler

        async def delayed(request: httpx.Request) -> httpx.Response:
            if "/historical/markets" in request.url.path:
                log.append("start")
                venue.archive_reads.append(
                    (request.url.params.get("event_ticker"), None)
                )
                await asyncio.sleep(0.01)
                log.append("429")
                return httpx.Response(429, headers={"Retry-After": "5"})
            return original(request)

        def service():
            svc = KalshiAPIService(api_key="")
            svc.client = httpx.AsyncClient(transport=httpx.MockTransport(delayed))
            return svc

        report = await sweep.run_archive_settlements(
            session_maker=lambda: _SqliteSession(engine),
            client_factory=service,
            now=NOW,
            after_id=0,
        )
        stats = report["stats"]
        assert sweep.SWEEP_CONCURRENCY == 6
        started = log.count("start")
        assert 1 <= started <= sweep.SWEEP_CONCURRENCY, log
        assert "start" not in log[log.index("429"):], log
        assert stats["archive_requests"] == started
        assert stats["archive_rate_limited"] == 9
        assert sorted(report["archive_owed_tickers"]) == sorted(TICKER.values())
        assert {s for s, _ in _state(engine).values()} == {"open"}
        assert report["next_after_id"] == min(IDS) - 1
        assert report["terminal"] == "partial"

    async def test_the_run_budget_bounds_archive_requests(self):
        engine = _seed()
        venue = _venue()
        report = await _walk(engine, venue, archive_requests=3, concurrency=1)
        stats = report["stats"]
        assert len(venue.archive_reads) == 3
        assert stats["archive_requests"] == 3
        assert stats["archive_read"] == 3 and stats["archive_budget"] == 6
        assert sum(s == "resolved" for s, _ in _state(engine).values()) == 3
        assert len(report["archive_owed_tickers"]) == 6
        assert report["terminal"] == "partial"

    async def test_a_404_event_earns_no_archive_read(self):
        t = "KXDNCAUTOPSY-26"
        engine = _seed(_one(t))
        venue = _venue(events={t: httpx.Response(404)})
        await _walk(engine, venue)
        assert venue.archive_reads == []
        assert _state(engine)[54069617][0] == "open"

    async def test_an_event_naming_another_ticker_earns_no_archive_read(self):
        t = "KXDNCAUTOPSY-26"
        engine = _seed(_one(t))
        venue = _venue(events={t: httpx.Response(
            200, json={"event": {"event_ticker": "KXDNCAUTOPSY-27", "markets": []}}
        )})
        await _walk(engine, venue)
        assert venue.archive_reads == []
        assert _state(engine)[54069617][0] == "open"


def test_only_the_walk_opts_in():
    import inspect

    # The walk is opt-in at run_sweep too: OFF unless a caller asks.
    assert inspect.signature(sweep.run_sweep).parameters["archive_walk"].default is False
    params = inspect.signature(sweep.run_backfill).parameters
    assert params["archive_requests"].default == 0
    assert params["archive_only"].default is False
