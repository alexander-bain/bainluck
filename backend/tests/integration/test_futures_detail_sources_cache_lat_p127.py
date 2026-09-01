"""LAT-P127 — the futures detail page stops sorting 189,312 rows to print 256.

SHIP: tapping a championship market from Discover ("NFL Super Bowl Winner",
"MLB World Series Winner") stops taking three to six seconds before anything
renders.

THE DEFECT, MEASURED IN PRODUCTION 2026-08-29 (three reads in a row, so a CACHE
defect by LAT-P124's rule, against a 0.26 s `/health` control on the same path):

    /api/futures/86832   3.73 / 3.76 / 5.97 s   db=3376-5621 ms   q=5
    /api/futures/1       2.72 / 2.39 / 3.21 s   db=2369-2861 ms   q=5
    /api/futures/55674287  0.27 / 0.45 / 0.28 s   db=3-44 ms      q=3

and the reason the third one is fast is the whole finding:

    market 86832   32 outcomes   189,312 snapshot rows   8 books
    market 1       30 outcomes   131,807 snapshot rows   5 books
    market 55674287 1 outcome          5 snapshot rows   1 book

`get_futures_market` ran a `row_number() OVER (PARTITION BY outcome_id,
bookmaker ORDER BY captured_at DESC)` across every one of those rows to keep the
~256 that are current — and ran a `SELECT DISTINCT bookmaker` over the identical
row set first, to decide whether to do it. Two full scans, no cache, every load.

THE TWO HALVES OF THE FIX, AND WHY EACH TEST BELOW EXISTS:

  1. The DISTINCT is deleted. `bookmaker` is NOT NULL in production, so the set
     it returned is exactly the set of sources the breakdown produces. One scan
     now answers both. `TestDerivationReplacesTheDistinct` is what holds that
     equivalence: if the derivation ever disagrees with `ORDER BY bookmaker`,
     these fail.
  2. What survives is cached — and ONLY the provenance half.
     `TestOnlyTheProvenanceHalfIsCached` is the guard that matters most: the
     hero and the outcome ladder are formatted from rows read fresh on every
     request, so this cache CANNOT serve a stale price on the number the page
     leads with. It was never in the cache.

🔴 THE KEY IS SPELLED OUT AS A LITERAL IN THIS FILE, ON PURPOSE. LAT-P125's
battery had two mutants survive because every test read the key through the
constant, so respelling the constant moved the test with the code. Here M-KEY
respells it route-side only and dies.
"""

import datetime as _dt
import json

from app.routes import futures as futures_route


# The key, written out. Not imported. See the module docstring.
EXPECTED_KEY_MARKET_86832 = "bainluck:futures:detail-sources:86832"


class FakeRedis:
    """Enough Redis to prove the cache round-trip, and no more.

    Counts reads and writes so a test can assert the SECOND request touched the
    database zero times — "it was fast" is not the claim, "it did not query" is.
    """

    def __init__(self, *, fail_get=False, fail_set=False):
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.gets = 0
        self.sets = 0
        self.fail_get = fail_get
        self.fail_set = fail_set

    def get(self, key):
        self.gets += 1
        if self.fail_get:
            raise ConnectionError("redis down")
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.sets += 1
        if self.fail_set:
            raise ConnectionError("redis down")
        self.store[key] = value
        self.ttls[key] = ex


class RecordingDB:
    """An AsyncSession stand-in that hands back canned rows and counts calls."""

    def __init__(self, breakdown_rows):
        self._rows = breakdown_rows
        self.executes = 0
        self.params = []

    async def execute(self, _stmt, params=None):
        # LAT-P148 made the breakdown statement a parameterised `text()`, so the
        # double takes the bind dict the way `AsyncSession.execute` does. It is
        # RECORDED rather than ignored: `TestTheStatementIsTheLooseScan` reads
        # `params` to prove the outcome ids are bound, not interpolated.
        self.executes += 1
        self.params.append(params)

        class _Result:
            def __init__(self, rows):
                self._rows = rows

            def all(self):
                return self._rows

        return _Result(self._rows)


#: Fixture clocks as OFFSETS from a single anchor, never literals (gotcha #44).
#:
#: `_get_source_breakdown` compares `captured_at` against
#: ``now - SOURCE_STALENESS_DAYS``, a REAL clock. A literal date would be fresh
#: today and stale in a fortnight and the `stale` assertions below would flip on
#: their own. The anchor is taken ONCE at import so that a fixture built in a
#: test and a fixture built in the code under test are the same instant to the
#: microsecond — recomputing `now()` per call would make the isoformat
#: comparisons race. Offset first; nothing here branches on the wall clock.
_ANCHOR = _dt.datetime.now(_dt.timezone.utc)

TS = {
    "fresh": _ANCHOR - _dt.timedelta(hours=1),
    "older": _ANCHOR - _dt.timedelta(hours=2),
    "stale": _ANCHOR - _dt.timedelta(days=30),
}


def _timestamps():
    return TS


def _rows():
    """Latest-per-(outcome, bookmaker) rows, as the window query returns them.

    🔴 THE SHAPE HERE IS LOAD-BEARING AND THE FIRST VERSION OF IT WAS NOT.
    Every row originally carried one identical fresh timestamp, and two mutants
    survived because of it: with nothing stale, `stale is False` is true whether
    the flag is computed or hard-coded, and with one row per bookmaker the
    "newer row wins" branch in `_get_source_breakdown` never executes. This
    fixture makes both observable:

      kalshi       two rows, the SECOND newer  -> exercises the overwrite branch
      draftkings   two rows, the second older  -> exercises the keep-first branch
      polymarket   one row, 30 days old        -> the only row where stale=True
    """
    ts = _timestamps()
    return [
        (501, "kalshi", 0.62, ts["older"]),
        (501, "draftkings", 0.60, ts["fresh"]),
        (502, "kalshi", 0.31, ts["fresh"]),
        (502, "draftkings", 0.33, ts["older"]),
        (502, "polymarket", 0.32, ts["stale"]),
    ]


def _patch_redis(monkeypatch, fake):
    monkeypatch.setattr(
        "app.tasks.redis_state.get_redis_client", lambda: fake, raising=True
    )


class TestDerivationReplacesTheDistinct:
    """Half 1: one scan answers what two used to."""

    async def test_bookmakers_match_what_order_by_bookmaker_returned(
        self, monkeypatch
    ):
        # The query that was deleted was `SELECT DISTINCT bookmaker ... ORDER BY
        # bookmaker`. Its answer for these rows, spelled out rather than
        # recomputed, is the assertion.
        distinct_ordered = ["draftkings", "kalshi", "polymarket"]

        fake = FakeRedis()
        _patch_redis(monkeypatch, fake)
        db = RecordingDB(_rows())

        bookmakers, breakdown = await futures_route._load_market_sources(
            db, 86832, [501, 502]
        )

        assert bookmakers == distinct_ordered
        assert [s["source"] for s in breakdown] == distinct_ordered

    async def test_one_database_query_not_two(self, monkeypatch):
        fake = FakeRedis()
        _patch_redis(monkeypatch, fake)
        db = RecordingDB(_rows())

        await futures_route._load_market_sources(db, 86832, [501, 502])

        # The whole point of half 1. Two would mean the DISTINCT came back.
        assert db.executes == 1

    async def test_single_bookmaker_market_still_computes_the_breakdown(
        self, monkeypatch
    ):
        """The breakdown now runs where it previously did not — and that is free.

        It replaces the DISTINCT scan one-for-one. What must NOT change is the
        response, and `TestResponseShapeIsUnchanged` holds that end.
        """
        fake = FakeRedis()
        _patch_redis(monkeypatch, fake)
        db = RecordingDB([(501, "kalshi", 0.62, TS["fresh"])])

        bookmakers, breakdown = await futures_route._load_market_sources(
            db, 4242, [501]
        )

        assert bookmakers == ["kalshi"]
        assert len(breakdown) == 1
        assert db.executes == 1


class TestOnlyTheProvenanceHalfIsCached:
    """Half 2: the cache holds what is slow and stable, never the live number."""

    async def test_miss_writes_the_key_with_the_ttl(self, monkeypatch):
        fake = FakeRedis()
        _patch_redis(monkeypatch, fake)
        db = RecordingDB(_rows())

        await futures_route._load_market_sources(db, 86832, [501, 502])

        assert fake.sets == 1
        assert EXPECTED_KEY_MARKET_86832 in fake.store
        assert fake.ttls[EXPECTED_KEY_MARKET_86832] == 300

    async def test_hit_issues_zero_database_queries(self, monkeypatch):
        """This is the ship, stated as an assertion about work not done."""
        fake = FakeRedis()
        _patch_redis(monkeypatch, fake)

        first = RecordingDB(_rows())
        await futures_route._load_market_sources(first, 86832, [501, 502])
        assert first.executes == 1

        second = RecordingDB(_rows())
        await futures_route._load_market_sources(second, 86832, [501, 502])
        assert second.executes == 0

    async def test_hit_equals_miss_as_an_object_not_merely_as_json(
        self, monkeypatch
    ):
        """#1587's class: the cache must store what it serves.

        `outcomes` is keyed by outcome_id, an INT, and `json.dumps` stringifies
        every dict key. FastAPI stringifies int keys too, so the HTTP bytes
        would have matched either way and no route-level test could have seen
        this. Compare the objects.
        """
        fake = FakeRedis()
        _patch_redis(monkeypatch, fake)

        miss_books, miss_rows = await futures_route._load_market_sources(
            RecordingDB(_rows()), 86832, [501, 502]
        )
        hit_books, hit_rows = await futures_route._load_market_sources(
            RecordingDB(_rows()), 86832, [501, 502]
        )

        assert hit_books == miss_books
        assert hit_rows == miss_rows

        # And say the int-ness out loud, so a future `str(k)` cannot pass by
        # making both sides equally wrong.
        for row in hit_rows:
            assert all(isinstance(k, int) for k in row["outcomes"])

    async def test_a_cached_row_still_reports_its_own_staleness(self, monkeypatch):
        """Why caching a deliberate source-comparison surface is honest here.

        A cached row can be up to the TTL old, but it cannot MISREPORT its age:
        freshness is a field computed from the snapshot's own timestamp, not a
        property of the cache. Polymarket's only snapshot is 30 days old, past
        `SOURCE_STALENESS_DAYS`, and it must come back out of Redis still saying
        so. Kill this and the cache starts being able to lie.
        """
        fake = FakeRedis()
        _patch_redis(monkeypatch, fake)

        _, miss_rows = await futures_route._load_market_sources(
            RecordingDB(_rows()), 86832, [501, 502]
        )
        _, hit_rows = await futures_route._load_market_sources(
            RecordingDB(_rows()), 86832, [501, 502]
        )

        by_source = {r["source"]: r for r in hit_rows}
        assert by_source["polymarket"]["stale"] is True
        assert by_source["kalshi"]["stale"] is False
        assert by_source["draftkings"]["stale"] is False
        # The flag survived the round-trip unchanged, not merely "was present".
        assert [r["stale"] for r in hit_rows] == [r["stale"] for r in miss_rows]

    async def test_each_row_carries_the_newest_captured_at_it_saw(
        self, monkeypatch
    ):
        """The overwrite branch, pinned through the cache.

        kalshi's two rows arrive oldest-first, so the second must replace the
        first's timestamp; draftkings' arrive newest-first, so the first must
        be kept. Both then have to survive JSON.
        """
        fake = FakeRedis()
        _patch_redis(monkeypatch, fake)
        ts = _timestamps()

        await futures_route._load_market_sources(
            RecordingDB(_rows()), 86832, [501, 502]
        )
        _, hit_rows = await futures_route._load_market_sources(
            RecordingDB(_rows()), 86832, [501, 502]
        )

        by_source = {r["source"]: r for r in hit_rows}
        assert by_source["kalshi"]["captured_at"] == ts["fresh"].isoformat()
        assert by_source["draftkings"]["captured_at"] == ts["fresh"].isoformat()
        assert by_source["polymarket"]["captured_at"] == ts["stale"].isoformat()

    async def test_keys_do_not_collide_between_markets(self, monkeypatch):
        fake = FakeRedis()
        _patch_redis(monkeypatch, fake)

        await futures_route._load_market_sources(RecordingDB(_rows()), 86832, [501])
        await futures_route._load_market_sources(RecordingDB(_rows()), 1, [501])

        assert "bainluck:futures:detail-sources:86832" in fake.store
        assert "bainluck:futures:detail-sources:1" in fake.store

    async def test_ttl_is_far_shorter_than_the_cadence_that_writes_the_data(self):
        """A staleness budget, NOT #901's outlive-the-warmer rule.

        Nothing warms this key, so a TTL longer than the write cadence would buy
        nothing but staleness. `poll-futures-every-4h` and
        `refresh-stale-futures-prices-hourly` are what move these rows.
        """
        assert futures_route.MARKET_SOURCES_TTL_S == 300
        assert futures_route.MARKET_SOURCES_TTL_S < 3600


class TestRedisIsBestEffortInBothDirections:
    async def test_unreachable_redis_still_answers(self, monkeypatch):
        def _boom():
            raise ConnectionError("no redis")

        monkeypatch.setattr(
            "app.tasks.redis_state.get_redis_client", _boom, raising=True
        )
        db = RecordingDB(_rows())

        bookmakers, breakdown = await futures_route._load_market_sources(
            db, 86832, [501, 502]
        )

        assert bookmakers == ["draftkings", "kalshi", "polymarket"]
        assert len(breakdown) == 3
        assert db.executes == 1

    async def test_failing_get_degrades_to_computing(self, monkeypatch):
        fake = FakeRedis(fail_get=True)
        _patch_redis(monkeypatch, fake)
        db = RecordingDB(_rows())

        bookmakers, _ = await futures_route._load_market_sources(
            db, 86832, [501, 502]
        )

        assert bookmakers == ["draftkings", "kalshi", "polymarket"]
        assert db.executes == 1

    async def test_failing_set_does_not_break_the_response(self, monkeypatch):
        fake = FakeRedis(fail_set=True)
        _patch_redis(monkeypatch, fake)
        db = RecordingDB(_rows())

        bookmakers, _ = await futures_route._load_market_sources(
            db, 86832, [501, 502]
        )

        assert bookmakers == ["draftkings", "kalshi", "polymarket"]

    async def test_corrupt_cache_entry_degrades_to_computing(self, monkeypatch):
        fake = FakeRedis()
        fake.store[EXPECTED_KEY_MARKET_86832] = "{not json"
        _patch_redis(monkeypatch, fake)
        db = RecordingDB(_rows())

        bookmakers, _ = await futures_route._load_market_sources(
            db, 86832, [501, 502]
        )

        assert bookmakers == ["draftkings", "kalshi", "polymarket"]
        assert db.executes == 1


class TestCachedPayloadShape:
    async def test_stored_json_carries_both_halves(self, monkeypatch):
        fake = FakeRedis()
        _patch_redis(monkeypatch, fake)

        await futures_route._load_market_sources(
            RecordingDB(_rows()), 86832, [501, 502]
        )

        payload = json.loads(fake.store[EXPECTED_KEY_MARKET_86832])
        assert set(payload) == {"bookmakers", "source_breakdown"}
        assert payload["bookmakers"] == ["draftkings", "kalshi", "polymarket"]

    def test_restore_is_a_no_op_on_already_int_keys(self):
        rows = [{"source": "kalshi", "outcomes": {501: 62.0}}]
        assert futures_route._restore_source_breakdown(rows) == rows

    def test_restore_tolerates_a_row_with_no_outcomes(self):
        rows = [{"source": "kalshi"}]
        assert futures_route._restore_source_breakdown(rows) == [
            {"source": "kalshi", "outcomes": {}}
        ]

    def test_restore_does_not_mutate_its_input(self):
        rows = [{"source": "kalshi", "outcomes": {"501": 62.0}}]
        futures_route._restore_source_breakdown(rows)
        assert rows == [{"source": "kalshi", "outcomes": {"501": 62.0}}]


class TestResponseShapeIsUnchanged:
    """End to end through the route, both halves crossed.

    The unit tests above prove the loader. These prove the HANDLER still emits
    the same document — including the `> 1 book` gate that decides whether
    `source_breakdown` appears at all, which moved when the DISTINCT went away.
    """

    async def test_multi_book_market_attaches_source_breakdown(
        self, client, mock_db, monkeypatch
    ):
        from unittest.mock import MagicMock

        _patch_redis(monkeypatch, FakeRedis())
        ts = TS["fresh"]

        market = _fake_market([_fake_outcome(501, "Chiefs", 0.22)])
        rows = MagicMock()
        rows.all.return_value = [(501, "kalshi", 0.22, ts), (501, "fanduel", 0.24, ts)]
        one = MagicMock()
        one.scalar_one_or_none.return_value = market
        mock_db.execute.side_effect = [one, rows]

        resp = await client.get("/api/futures/86832")

        assert resp.status_code == 200
        body = resp.json()
        assert body["bookmakers"] == ["fanduel", "kalshi"]
        assert len(body["source_breakdown"]) == 2

    async def test_single_book_market_omits_source_breakdown(
        self, client, mock_db, monkeypatch
    ):
        """The gate that moved. It used to read `if source_breakdown:` after a
        `len(bookmakers) > 1` guard on COMPUTING it; now the breakdown is always
        computed, so the guard has to live at the attach site instead."""
        from unittest.mock import MagicMock

        _patch_redis(monkeypatch, FakeRedis())
        ts = TS["fresh"]

        market = _fake_market([_fake_outcome(501, "Chiefs", 0.22)])
        rows = MagicMock()
        rows.all.return_value = [(501, "kalshi", 0.22, ts)]
        one = MagicMock()
        one.scalar_one_or_none.return_value = market
        mock_db.execute.side_effect = [one, rows]

        resp = await client.get("/api/futures/4242")

        assert resp.status_code == 200
        body = resp.json()
        assert body["bookmakers"] == ["kalshi"]
        assert "source_breakdown" not in body

    async def test_market_with_no_outcomes_never_reaches_redis(
        self, client, mock_db, monkeypatch
    ):
        from unittest.mock import MagicMock

        fake = FakeRedis()
        _patch_redis(monkeypatch, fake)

        market = _fake_market([])
        one = MagicMock()
        one.scalar_one_or_none.return_value = market
        mock_db.execute.side_effect = [one]

        resp = await client.get("/api/futures/4242")

        assert resp.status_code == 200
        assert resp.json()["bookmakers"] == []
        assert fake.gets == 0
        assert fake.sets == 0

    async def test_second_request_serves_the_page_without_a_snapshot_query(
        self, client, mock_db, monkeypatch
    ):
        """The ship, crossed end to end: warm through the route, read back
        through the route, and assert the second load did no snapshot work."""
        from unittest.mock import MagicMock

        fake = FakeRedis()
        _patch_redis(monkeypatch, fake)
        ts = TS["fresh"]

        def _market_result():
            one = MagicMock()
            one.scalar_one_or_none.return_value = _fake_market(
                [_fake_outcome(501, "Chiefs", 0.22)]
            )
            return one

        rows = MagicMock()
        rows.all.return_value = [(501, "kalshi", 0.22, ts), (501, "fanduel", 0.24, ts)]

        mock_db.execute.side_effect = [_market_result(), rows, _market_result()]

        first = await client.get("/api/futures/86832")
        second = await client.get("/api/futures/86832")

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json() == second.json()
        # Three executes total across TWO page loads: market+snapshots, then
        # market only. A fourth would mean the cache did not hold.
        assert mock_db.execute.call_count == 3


def _fake_outcome(outcome_id, name, probability):
    from types import SimpleNamespace

    return SimpleNamespace(
        id=outcome_id,
        name=name,
        current_probability=probability,
        # Q480: the display path reads `external_id` to drop a `_yes`/`_no`
        # leg duplicating a bare rung. None = not a leg (pass-through).
        external_id=None,
        current_american_odds=350,
        rank=1,
        probability_change_24h=None,
        rank_change_24h=None,
        opening_probability=None,
        opening_american_odds=None,
        is_winner=None,
        last_updated=None,
    )


def _fake_market(outcomes):
    from types import SimpleNamespace

    return SimpleNamespace(
        id=86832,
        name="NFL Super Bowl Winner",
        description=None,
        sport=SimpleNamespace(key="americanfootball_nfl", name="NFL"),
        category="championship",
        llm_sport_category="americanfootball",
        status="open",
        source="odds_api",
        external_id="nfl_sb_2027",
        # The shape field (#194) the detail payload serves. A stand-in for the
        # model that omits a column the route reads is an incomplete double, not
        # a route bug — Q478.
        market_type="field",
        mutually_exclusive=True,
        commence_time=None,
        resolution_date=None,
        outcomes=outcomes,
        category_tags=None,
        created_at=None,
        updated_at=None,
        group_id=None,
        canonical_market_key=None,
        hook_description=None,
        image_url=None,
        market_metadata=None,
    )
