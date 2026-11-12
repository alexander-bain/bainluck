"""#12042: the two six-hourly backfills that never finished work in bounded batches.

Since the Nov 11 switch (144-A), every R15 kill of the background worker landed
while ``backfill_kalshi_settled`` or ``backfill_polymarket_matchups`` was in
flight, and neither logged a success in three days.

* ``backfill_polymarket_matchups`` loaded every Polymarket row (1.72M) into one
  list through OFFSET pages. It now walks groups in ``group_id`` order, at most
  ``groups_per_batch`` groups per batch, one UPDATE and one commit per batch,
  stops on a time budget and resumes from a saved cursor.
* ``backfill_kalshi_settled`` held 200 settled events, each with every nested
  market, per page. The page is now ``_SETTLED_PAGE_EVENTS``; the page cap and
  the empty-page exit scale so a run reads each series as deep as before.

These drive the real functions against faked DB, Redis and venue.
"""

from contextlib import asynccontextmanager

import pytest

import app.tasks.entity_seed as entity_seed
import app.tasks.kalshi as kalshi


# ---------------------------------------------------------------- Polymarket


def _row(mid, group_id, name, matchup_title=None, linked=True):
    return {
        "id": mid,
        "group_id": group_id,
        "name": name,
        "matchup_title": matchup_title,
        "event_id": 1 if linked else None,
    }


def _game_group(n, first_id, linked=True):
    """A game group: a moneyline row that names the matchup, a spread row and a
    prop row that don't."""
    gid = f"polymarket:{n:05d}"
    return [
        _row(first_id, gid, f"Team{n}A vs. Team{n}B", linked=linked),
        _row(first_id + 1, gid, f"Spread: Team{n}A (-2.5)", linked=linked),
        _row(first_id + 2, gid, "Will the game go to overtime?", linked=linked),
    ]


class _Res:
    def __init__(self, rows=(), rowcount=0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def all(self):
        return list(self._rows)


class _FakeMarkets:
    """futures_markets for the matchup walk. It answers the three statements the
    walk issues (next group ids, members of those groups, the batched UPDATE)
    and records every batch's size so the bound can be read back."""

    def __init__(self, rows, on_members_read=None):
        self.rows = rows
        self.group_batches: list[list[str]] = []
        self.member_loads: list[int] = []
        self.commits = 0
        self.on_members_read = on_members_read

    def _visible(self, stmt_sql):
        linked = "event_id IS NOT NULL" in stmt_sql
        return [r for r in self.rows if not linked or r["event_id"] is not None]

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if sql.lstrip().startswith("UPDATE futures_markets"):
            # Apply the guard the SQL actually carries, so a changed guard is
            # caught here even though no real database runs under test.
            if "COALESCE(fm.market_metadata->>'matchup_title', '') = ''" in sql:
                writable = lambda title: title in (None, "")  # noqa: E731
            elif "->>'matchup_title') IS NULL" in sql:
                writable = lambda title: title is None  # noqa: E731
            else:
                writable = lambda title: True  # noqa: E731
            n = 0
            for mid, title in zip(params["ids"], params["titles"]):
                r = next(r for r in self.rows if r["id"] == mid)
                if writable(r["matchup_title"]):
                    r["matchup_title"] = title
                    n += 1
            return _Res(rowcount=n)
        compiled = stmt.compile()
        p = compiled.params
        if "DISTINCT" in sql:
            after = next(v for k, v in p.items() if k.startswith("group_id"))
            limit = next(v for k, v in p.items() if k.startswith("param") or k == "limit_1")
            gids = sorted({r["group_id"] for r in self._visible(sql) if r["group_id"] > after})
            out = gids[:limit]
            self.group_batches.append(out)
            return _Res([(g,) for g in out])
        wanted = set(next(v for k, v in p.items() if k.startswith("group_id")))
        members = [r for r in self._visible(sql) if r["group_id"] in wanted]
        # A database returns rows in any order unless asked; model the worst
        # case (highest id first) unless the read orders by id.
        ordered = "ORDER BY futures_markets.id" in sql
        members.sort(key=lambda r: r["id"], reverse=not ordered)
        self.member_loads.append(len(members))
        out = _Res([(r["id"], r["name"], r["group_id"], r["matchup_title"]) for r in members])
        if self.on_members_read:
            self.on_members_read(self.rows)
        return out

    async def commit(self):
        self.commits += 1


class _FakeRedis:
    def __init__(self, store=None):
        self.store = dict(store or {})

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)


def _install(monkeypatch, markets, rc, clock=None):
    @asynccontextmanager
    async def _session(*args, **kwargs):
        yield markets

    async def _no_marker(session, ref, payload):
        return None

    monkeypatch.setattr(entity_seed, "get_task_session", _session)
    monkeypatch.setattr(entity_seed, "_write_seed_marker", _no_marker)
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: rc)
    if clock is not None:
        monkeypatch.setattr(entity_seed, "_monotonic", clock)


def test_plan_titles_only_rows_that_cannot_name_their_own_matchup():
    rows = _game_group(1, 10) + [
        _row(20, "polymarket:00002", "Who will win the 2028 election?"),
        _row(21, "polymarket:00002", "Will turnout exceed 60%?"),
    ]
    rows[2]["matchup_title"] = "Already Set vs. Earlier"
    games, updates = entity_seed.plan_matchup_updates(rows)
    assert games == 1
    # the spread row gets the title; the moneyline parses on its own; the prop
    # row already has one; the non-game group is left alone
    assert updates == [(11, "Team1A vs. Team1B")]


@pytest.mark.asyncio
async def test_walk_reaches_every_group_in_bounded_batches(monkeypatch):
    rows = []
    for n in range(7):
        rows += _game_group(n, 100 + 10 * n)
    markets = _FakeMarkets(rows)
    rc = _FakeRedis()
    _install(monkeypatch, markets, rc)

    result = await entity_seed.backfill_polymarket_matchups_impl(
        all_groups=True, groups_per_batch=3
    )

    assert [len(b) for b in markets.group_batches] == [3, 3, 1]
    assert max(markets.member_loads) == 9  # 3 groups x 3 rows, never the table
    assert markets.commits >= 3
    assert result["complete"] is True
    assert result["groups_scanned"] == 7
    # every spread and prop row now carries its group's matchup
    for r in rows:
        assert r["matchup_title"] is not None or " vs. " in r["name"]
    assert result["applied"] == 14
    # a finished pass resets the cursor, so the next run starts from the top
    assert rc.store == {}


@pytest.mark.asyncio
async def test_budget_stop_saves_the_cursor_and_the_next_run_resumes(monkeypatch):
    rows = []
    for n in range(6):
        rows += _game_group(n, 100 + 10 * n)
    markets = _FakeMarkets(rows)
    rc = _FakeRedis()
    ticks = iter([0.0, 0.0, 5.0, 999.0, 999.0, 999.0])
    _install(monkeypatch, markets, rc, clock=lambda: next(ticks))

    first = await entity_seed.backfill_polymarket_matchups_impl(
        all_groups=True, groups_per_batch=2, max_seconds=10
    )
    assert first["complete"] is False
    assert first["batches"] == 2
    key = "bainluck:poly_matchups:group_cursor:all"
    assert rc.store[key] == "polymarket:00003"

    # the next run starts after the saved group, not from the top
    monkeypatch.setattr(entity_seed, "_monotonic", lambda: 0.0)
    markets.group_batches.clear()
    second = await entity_seed.backfill_polymarket_matchups_impl(
        all_groups=True, groups_per_batch=2, max_seconds=10
    )
    assert markets.group_batches[0] == ["polymarket:00004", "polymarket:00005"]
    assert second["started_after"] == "polymarket:00003"
    assert second["complete"] is True
    assert key not in rc.store
    assert all(r["matchup_title"] is not None or " vs. " in r["name"] for r in rows)


@pytest.mark.asyncio
async def test_linked_only_walk_leaves_unlinked_rows_alone(monkeypatch):
    rows = _game_group(1, 10) + _game_group(2, 20, linked=False)
    markets = _FakeMarkets(rows)
    rc = _FakeRedis()
    _install(monkeypatch, markets, rc)

    result = await entity_seed.backfill_polymarket_matchups_impl(all_groups=False)

    assert result["linked_only"] is True
    assert result["applied"] == 2
    assert all(r["matchup_title"] is None for r in rows if r["event_id"] is None)


@pytest.mark.asyncio
async def test_rerun_over_titled_rows_writes_nothing(monkeypatch):
    rows = _game_group(1, 10)
    markets = _FakeMarkets(rows)
    _install(monkeypatch, markets, _FakeRedis())
    await entity_seed.backfill_polymarket_matchups_impl(all_groups=True)
    again = await entity_seed.backfill_polymarket_matchups_impl(all_groups=True)
    assert again["needed"] == 0 and again["applied"] == 0


@pytest.mark.asyncio
async def test_redis_down_still_finishes_one_bounded_pass(monkeypatch):
    rows = []
    for n in range(4):
        rows += _game_group(n, 100 + 10 * n)
    markets = _FakeMarkets(rows)

    def _broken(*a, **k):
        raise ConnectionError("redis down")

    _install(monkeypatch, markets, None)
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", _broken)
    result = await entity_seed.backfill_polymarket_matchups_impl(
        all_groups=True, groups_per_batch=3
    )
    assert result["complete"] is True and result["applied"] == 8


@pytest.mark.asyncio
async def test_an_equal_length_tie_keeps_the_lower_ids_title(monkeypatch):
    """Builder B's case on #12629: two sibling names of the same length both
    parse; the old reader went in id order, so the lower id's matchup won."""
    gid = "polymarket:tie"
    rows = [
        _row(30, gid, "Alpha vs. Bravo"),
        _row(31, gid, "Delta vs. Echoo"),
        _row(32, gid, "Will there be a red card?"),
    ]
    assert len(rows[0]["name"]) == len(rows[1]["name"])
    markets = _FakeMarkets(rows)
    _install(monkeypatch, markets, _FakeRedis())
    await entity_seed.backfill_polymarket_matchups_impl(all_groups=True)
    assert rows[2]["matchup_title"] == "Alpha vs. Bravo"


@pytest.mark.asyncio
async def test_empty_titles_are_filled_and_a_concurrent_title_is_kept(monkeypatch):
    gid = "polymarket:mixed"
    rows = [
        _row(40, gid, "Team9A vs. Team9B"),
        _row(41, gid, "Spread: Team9A (-1.5)"),  # NULL title
        _row(42, gid, "Total corners over 9.5?", matchup_title=""),  # empty title
        _row(43, gid, "Will Team9A keep a clean sheet?"),  # filled after the read
    ]

    def _ingest_writes_one(all_rows):
        next(r for r in all_rows if r["id"] == 43)["matchup_title"] = "Written By Ingest"

    markets = _FakeMarkets(rows, on_members_read=_ingest_writes_one)
    _install(monkeypatch, markets, _FakeRedis())
    result = await entity_seed.backfill_polymarket_matchups_impl(all_groups=True)

    assert rows[1]["matchup_title"] == "Team9A vs. Team9B"
    assert rows[2]["matchup_title"] == "Team9A vs. Team9B"  # "" counts as missing
    assert rows[3]["matchup_title"] == "Written By Ingest"  # never overwritten
    assert result["needed"] == 3 and result["applied"] == 2


# --------------------------------------------------------------------- Kalshi


def test_settled_page_is_small_and_series_depth_is_unchanged():
    assert kalshi._SETTLED_PAGE_EVENTS <= 50
    # one run may still read 200 pages x 200 events of a series, and still gives
    # up on a series after 5 x 200 events that changed nothing
    assert kalshi._SETTLED_PAGES_PER_SERIES * kalshi._SETTLED_PAGE_EVENTS == 200 * 200
    assert kalshi._SETTLED_EMPTY_PAGE_EXIT * kalshi._SETTLED_PAGE_EVENTS == 5 * 200


class _KRes:
    def __init__(self, rows=()):
        self._rows = list(rows)
        self.rowcount = 0

    def all(self):
        return list(self._rows)

    def fetchall(self):
        return list(self._rows)


class _KSession:
    async def execute(self, stmt, params=None):
        if "series_prefix" in str(stmt):
            return _KRes([("KXNBAPTS", True, True)])
        return _KRes()

    async def commit(self):
        pass

    async def rollback(self):
        pass


class _PagedVenue:
    """Serves endless pages of settled events whose markets change nothing in the
    DB, so the scan runs until the empty-page exit."""

    def __init__(self):
        self.limits: list[int] = []

    async def get_events(self, **kwargs):
        self.limits.append(kwargs["limit"])
        page = len(self.limits)
        events = [
            {"markets": [{"ticker": f"KXNBAPTS-{page}-{i}-{j}"} for j in range(3)]}
            for i in range(kwargs["limit"])
        ]
        return events, f"cursor-{page}"

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_settled_scan_asks_for_small_pages_and_exits_at_the_same_depth(monkeypatch):
    venue = _PagedVenue()
    rc = _FakeRedis()

    @asynccontextmanager
    async def _session(*args, **kwargs):
        yield _KSession()

    async def _noop_index():
        return None

    async def _no_sleep(*a, **k):
        return None

    monkeypatch.setattr(kalshi, "get_task_session", _session)
    monkeypatch.setattr(kalshi, "_ensure_futures_outcomes_external_id_index", _noop_index)
    monkeypatch.setattr("app.services.kalshi_api.KalshiAPIService", lambda *a, **k: venue)
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: rc)
    monkeypatch.setattr("asyncio.sleep", _no_sleep)

    stats = await kalshi._backfill_from_settled_events(limit=10, only_series=["KXNBAPTS"])

    assert stats["errors"] == [], stats["errors"]
    assert set(venue.limits) == {kalshi._SETTLED_PAGE_EVENTS}
    # gave up after the scaled number of no-op pages, i.e. 1,000 events as before
    assert len(venue.limits) == kalshi._SETTLED_EMPTY_PAGE_EXIT
    assert stats["events_scanned"] == 5 * 200
    # and saved where it stopped so the next run resumes the series
    assert rc.store["bainluck:settled_cursor:KXNBAPTS"] == f"cursor-{len(venue.limits)}"
