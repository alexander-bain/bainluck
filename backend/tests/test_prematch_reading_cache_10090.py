"""#10090 — a kicked-off game's pre-match reading is read once, not on every page.

`PREMATCH_PRIOR_SQL` was 8.9% of every block the database read on a saturated
Saturday (16:41–17:24Z, 2026-10-31) while Alex's signed-in feed timed out at
25 s. `fetch_prematch_prior_rows` holds each kicked-off game's rows for a
bounded TTL. These tests pin what that cache may and may not do:

* a hit returns the rows the database returned, and costs no read;
* a cutoff that has not passed is never held;
* the TTL expires, so a late backfill row stamped before kickoff still lands;
* ``PREMATCH_READING_CACHE=0`` reads every time, exactly as before;
* the misses are re-bound with each id beside ITS OWN cutoff (the positional
  rule), and only the misses are read.

The fake database answers the statement the way Postgres does — the last row at
or before each cutoff, per source — so "identical rows" is compared against the
statement's own semantics, not against a canned list.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.utils.prematch_reading as pr
from app.utils.prematch_reading import (
    PREMATCH_PRIOR_SQL,
    PREMATCH_READING_CACHE_TTL_S,
    fetch_prematch_prior_rows,
    read_prematch_priors,
)

# gotcha #44 — a fixed anchor; every time below is an offset from it.
_NOW = datetime(2026, 10, 31, 17, 0, tzinfo=timezone.utc)
_SOURCES = ["kalshi", "polymarket"]


def _snap(event_id, source, home, captured_at, away=None, draw=None):
    return SimpleNamespace(
        event_id=event_id,
        source=source,
        home=home,
        away=away,
        draw=draw,
        captured_at=captured_at,
    )


class _FakeDb:
    """Executes `PREMATCH_PRIOR_SQL` over an in-memory `win_prob_snapshots`."""

    def __init__(self, snapshots):
        self.snapshots = list(snapshots)
        self.calls: list[dict] = []

    async def execute(self, stmt, params):
        assert str(stmt) == PREMATCH_PRIOR_SQL
        self.calls.append(
            {k: (list(v) if isinstance(v, list) else v) for k, v in params.items()}
        )
        rows = []
        for event_id, cutoff in zip(params["ids"], params["cutoffs"]):
            best = {}
            for s in self.snapshots:
                if (
                    s.event_id == event_id
                    and s.source in params["sources"]
                    and s.home is not None
                    and s.captured_at <= cutoff
                ):
                    if s.source not in best or s.captured_at > best[s.source].captured_at:
                        best[s.source] = s
            for source in sorted(best):
                s = best[source]
                rows.append(
                    SimpleNamespace(
                        event_id=s.event_id,
                        source=s.source,
                        home_win_probability=Decimal(str(s.home)),
                        away_win_probability=(
                            Decimal(str(s.away)) if s.away is not None else None
                        ),
                        draw_probability=(
                            Decimal(str(s.draw)) if s.draw is not None else None
                        ),
                    )
                )
        return SimpleNamespace(all=lambda: rows)


def _key(row):
    return (
        row.event_id,
        row.source,
        row.home_win_probability,
        row.away_win_probability,
        row.draw_probability,
    )


def _sorted(rows):
    return sorted(_key(r) for r in rows)


@pytest.fixture
def clock(monkeypatch):
    state = {"now": _NOW, "mono": 1000.0}
    monkeypatch.setattr(pr, "_utcnow", lambda: state["now"])
    monkeypatch.setattr(pr, "_monotonic", lambda: state["mono"])
    monkeypatch.delenv("PREMATCH_READING_CACHE", raising=False)
    return state


def _binds(pairs, sources=_SOURCES):
    return {
        "ids": [event_id for event_id, _ in pairs],
        "cutoffs": [cutoff for _, cutoff in pairs],
        "sources": list(sources),
    }


KICK_1 = _NOW - timedelta(hours=3)
KICK_2 = _NOW - timedelta(hours=2)
KICK_3 = _NOW - timedelta(hours=1)


def _slate():
    return [
        # event 1: two pre-kickoff readings per venue, then the settled ~100%.
        _snap(1, "kalshi", 0.40, KICK_1 - timedelta(hours=2), away=0.60),
        _snap(1, "kalshi", 0.42, KICK_1 - timedelta(minutes=5), away=0.58),
        _snap(1, "kalshi", 0.99, KICK_1 + timedelta(hours=2), away=0.01),
        _snap(1, "polymarket", 0.45, KICK_1 - timedelta(minutes=1), away=0.55),
        # event 2: a three-way game; the draw rides the same row.
        _snap(2, "kalshi", 0.30, KICK_2 - timedelta(minutes=3), away=0.44, draw=0.26),
        _snap(2, "kalshi", 0.00, KICK_2 + timedelta(minutes=95), away=1.0, draw=0.0),
        # event 3: only in-play rows — the read must return nothing for it.
        _snap(3, "kalshi", 0.80, KICK_3 + timedelta(minutes=10), away=0.20),
    ]


@pytest.mark.asyncio
async def test_a_hit_returns_the_rows_the_database_returned_and_reads_nothing(clock):
    db = _FakeDb(_slate())
    binds = _binds([(1, KICK_1), (2, KICK_2), (3, KICK_3)])

    first = await fetch_prematch_prior_rows(db, binds)
    second = await fetch_prematch_prior_rows(db, binds)

    assert len(db.calls) == 1
    assert _sorted(second) == _sorted(first)
    # …and the first answer is the statement's own, settled rows excluded.
    assert _sorted(first) == [
        (1, "kalshi", Decimal("0.42"), Decimal("0.58"), None),
        (1, "polymarket", Decimal("0.45"), Decimal("0.55"), None),
        (2, "kalshi", Decimal("0.3"), Decimal("0.44"), Decimal("0.26")),
    ]


@pytest.mark.asyncio
async def test_a_game_with_no_prematch_rows_is_held_too(clock):
    """Empty is an answer for a passed kickoff; re-reading it is the cost."""
    db = _FakeDb(_slate())
    binds = _binds([(3, KICK_3)])
    assert await fetch_prematch_prior_rows(db, binds) == []
    assert await fetch_prematch_prior_rows(db, binds) == []
    assert len(db.calls) == 1


@pytest.mark.asyncio
async def test_a_cutoff_that_has_not_passed_is_never_held(clock):
    future = _NOW + timedelta(minutes=30)
    db = _FakeDb([_snap(9, "kalshi", 0.5, _NOW - timedelta(minutes=1), away=0.5)])
    binds = _binds([(9, future)])

    await fetch_prematch_prior_rows(db, binds)
    db.snapshots.append(_snap(9, "kalshi", 0.6, _NOW, away=0.4))
    rows = await fetch_prematch_prior_rows(db, binds)

    assert len(db.calls) == 2
    assert [r.home_win_probability for r in rows] == [Decimal("0.6")]
    assert pr._prematch_cache == {}


@pytest.mark.asyncio
async def test_a_cutoff_exactly_now_is_not_held(clock):
    db = _FakeDb([])
    binds = _binds([(9, _NOW)])
    await fetch_prematch_prior_rows(db, binds)
    await fetch_prematch_prior_rows(db, binds)
    assert len(db.calls) == 2


@pytest.mark.asyncio
async def test_the_ttl_expires_so_a_late_backfill_row_lands(clock):
    db = _FakeDb(_slate())
    binds = _binds([(3, KICK_3)])
    assert await fetch_prematch_prior_rows(db, binds) == []

    # A late write stamped before kickoff (a backfill) arrives after the read.
    db.snapshots.append(_snap(3, "kalshi", 0.55, KICK_3 - timedelta(minutes=2), away=0.45))

    clock["mono"] += PREMATCH_READING_CACHE_TTL_S - 1
    assert await fetch_prematch_prior_rows(db, binds) == []
    assert len(db.calls) == 1

    clock["mono"] += 1
    rows = await fetch_prematch_prior_rows(db, binds)
    assert len(db.calls) == 2
    assert _sorted(rows) == [(3, "kalshi", Decimal("0.55"), Decimal("0.45"), None)]


@pytest.mark.parametrize("value", ["0", "false", "off", "no", " OFF "])
@pytest.mark.asyncio
async def test_the_switch_off_reads_every_time_with_the_callers_binds(
    clock, monkeypatch, value
):
    monkeypatch.setenv("PREMATCH_READING_CACHE", value)
    db = _FakeDb(_slate())
    binds = _binds([(1, KICK_1), (2, KICK_2)])

    first = await fetch_prematch_prior_rows(db, binds)
    await fetch_prematch_prior_rows(db, binds)

    assert db.calls == [binds, binds]
    assert pr._prematch_cache == {}
    # Off returns the cursor's own rows, not a copy of them.
    assert all(isinstance(r, SimpleNamespace) for r in first)


@pytest.mark.asyncio
async def test_only_the_misses_are_read_each_beside_its_own_cutoff(clock):
    db = _FakeDb(_slate())
    await fetch_prematch_prior_rows(db, _binds([(2, KICK_2)]))

    rows = await fetch_prematch_prior_rows(
        db, _binds([(1, KICK_1), (2, KICK_2), (3, KICK_3)])
    )

    assert db.calls[1]["ids"] == [1, 3]
    assert db.calls[1]["cutoffs"] == [KICK_1, KICK_3]
    assert db.calls[1]["sources"] == _SOURCES
    oracle = await _FakeDb(_slate()).execute(
        pr_text(), _binds([(1, KICK_1), (2, KICK_2), (3, KICK_3)])
    )
    assert _sorted(rows) == _sorted(oracle.all())


@pytest.mark.asyncio
async def test_rows_come_back_in_the_callers_event_order(clock):
    db = _FakeDb(_slate())
    await fetch_prematch_prior_rows(db, _binds([(2, KICK_2)]))
    rows = await fetch_prematch_prior_rows(db, _binds([(2, KICK_2), (1, KICK_1)]))
    assert [r.event_id for r in rows] == [2, 1, 1]


@pytest.mark.asyncio
async def test_a_rescheduled_kickoff_is_a_different_key(clock):
    db = _FakeDb(_slate())
    await fetch_prematch_prior_rows(db, _binds([(1, KICK_1)]))
    moved = KICK_1 - timedelta(hours=1)
    rows = await fetch_prematch_prior_rows(db, _binds([(1, moved)]))
    assert len(db.calls) == 2
    assert _sorted(rows) == [(1, "kalshi", Decimal("0.4"), Decimal("0.6"), None)]


@pytest.mark.asyncio
async def test_the_source_set_is_part_of_the_key_but_not_its_order(clock):
    db = _FakeDb(_slate())
    await fetch_prematch_prior_rows(db, _binds([(1, KICK_1)], ["kalshi"]))
    both = await fetch_prematch_prior_rows(db, _binds([(1, KICK_1)]))
    assert len(db.calls) == 2
    assert {r.source for r in both} == {"kalshi", "polymarket"}

    await fetch_prematch_prior_rows(db, _binds([(1, KICK_1)], ["polymarket", "kalshi"]))
    assert len(db.calls) == 2


@pytest.mark.asyncio
async def test_a_naive_cutoff_shares_the_aware_cutoffs_key(clock):
    db = _FakeDb(_slate())
    await fetch_prematch_prior_rows(db, _binds([(1, KICK_1)]))
    await fetch_prematch_prior_rows(db, _binds([(1, KICK_1.replace(tzinfo=None))]))
    assert len(db.calls) == 1


@pytest.mark.asyncio
async def test_a_repeated_event_id_bypasses_the_cache(clock):
    """Rows carry no cutoff, so a repeated id cannot be attributed — read as before."""
    db = _FakeDb(_slate())
    binds = _binds([(1, KICK_1), (1, KICK_1 - timedelta(hours=1))])
    await fetch_prematch_prior_rows(db, binds)
    await fetch_prematch_prior_rows(db, binds)
    assert db.calls == [binds, binds]
    assert pr._prematch_cache == {}


@pytest.mark.asyncio
async def test_misaligned_arrays_bypass_the_cache(clock):
    db = _FakeDb(_slate())
    binds = {"ids": [1, 2], "cutoffs": [KICK_1], "sources": _SOURCES}
    await fetch_prematch_prior_rows(db, binds)
    assert db.calls == [binds]
    assert pr._prematch_cache == {}


@pytest.mark.asyncio
async def test_the_cache_is_bounded(clock, monkeypatch):
    monkeypatch.setattr(pr, "PREMATCH_READING_CACHE_MAX_KEYS", 2)
    db = _FakeDb([])
    for event_id in (1, 2, 3):
        await fetch_prematch_prior_rows(db, _binds([(event_id, KICK_1)]))
    assert [k[0] for k in pr._prematch_cache] == [2, 3]


@pytest.mark.asyncio
async def test_held_rows_are_plain_data_not_cursor_rows(clock):
    """gotcha #6 — a module-global cache holds plain data, never live rows."""
    db = _FakeDb(_slate())
    await fetch_prematch_prior_rows(db, _binds([(1, KICK_1)]))
    (_, held), = pr._prematch_cache.values()
    assert held and all(type(r) is pr.PrematchPriorRow for r in held)


@pytest.mark.asyncio
async def test_the_feed_reader_reads_once_per_ttl(clock):
    db = _FakeDb(_slate())
    binds = _binds([(1, KICK_1), (2, KICK_2)])
    first = await read_prematch_priors(db, binds)
    second = await read_prematch_priors(db, binds)
    assert len(db.calls) == 1
    assert first == second
    assert first[2]["kalshi"] == (0.3, 0.44, 0.26)


@pytest.mark.asyncio
async def test_the_hub_and_team_batch_reads_once_per_ttl(clock):
    from app.utils.settled_prematch_batch import settled_prematch_odds_by_event

    class _Nested:
        async def commit(self):
            pass

        async def rollback(self):
            pass

    db = _FakeDb(_slate())

    async def begin_nested():
        return _Nested()

    db.begin_nested = begin_nested
    events = [
        SimpleNamespace(
            id=1,
            status="completed",
            commence_time=KICK_1,
            opening_home_probability=None,
            opening_away_probability=None,
            sport_key="americanfootball_nfl",
        )
    ]
    first = await settled_prematch_odds_by_event(db, events)
    second = await settled_prematch_odds_by_event(db, events)
    assert len(db.calls) == 1
    assert first == second and first[1]["source"] == "kalshi"


def test_no_surface_executes_the_statement_around_the_cache():
    """Every reader goes through `fetch_prematch_prior_rows`; a new inline
    execute would silently skip the cache (and its off switch)."""
    app_dir = Path(__file__).resolve().parents[1] / "app"
    offenders = [
        str(path.relative_to(app_dir))
        for path in app_dir.rglob("*.py")
        if "text(PREMATCH_PRIOR_SQL)" in path.read_text()
        and path.name != "prematch_reading.py"
    ]
    assert offenders == []


def pr_text():
    from sqlalchemy import text

    return text(PREMATCH_PRIOR_SQL)
