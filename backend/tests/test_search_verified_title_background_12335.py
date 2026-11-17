"""#12335 step 4: a composition the Search bound leaves running finishes, and the next build prints it.

THE DEFECT, measured on production after #12346 (Nov 8, 3:25 and 5:53 AM
PT): 0 of 20 searches for the NFL title teams ("chiefs", "49ers", "bears",
"jaguars", "eagles", first read and repeat) carried the page's blend. Every
build tripped the 1 s bound, the bound CANCELLED the composition, so nothing
ever reached `_VERIFIED_TITLE_CACHE` (#12347) — only a page view filled it, and
in a quiet hour none came. The page was then cached for 180 s, three times the
verdict's 60 s life, so even a filled verdict was gone by the next build.

THE SHIP. The search stops WAITING at the bound but the composition keeps
running, one per market, on its own session; its verdict serves the next build,
and the page that missed it is cached for the short shed life instead of 180 s.
"""

import asyncio
import time

import pytest

import app.routes.futures as futures_mod
from app.models.models import FuturesMarket
from app.routes import events
from app.routes.events import _search_verified_titles
from app.utils.futures_verified_title import Composition
from app.utils.search_cache import (
    SEARCH_THIN_RESPONSE_TTL_SECONDS,
    shed_answer_ttl_seconds,
)


def _market(market_id=129037):
    return FuturesMarket(
        id=market_id,
        source="polymarket",
        external_id="pm-sb-2027",
        name="NFL: 2027 Champion",
        status="open",
        mutually_exclusive=True,
        market_tier=1,
        market_type="field",
        category="sports",
        llm_sport_category="football",
        market_metadata={"polymarket_event_slug": "pro-football-2027-champion"},
    )


def _verdict(tag):
    return Composition(question_identity={"tag": tag}, overlay={}, contributing_sources=["kalshi"])


def _engine_session(pool_size=2):
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    # Never connects: the row read and the composer are faked.
    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none", pool_size=pool_size)
    return engine, AsyncSession(bind=engine)


@pytest.fixture
def rig(monkeypatch):
    """Real `_resolve_verified_title` and its cache; a composer taking `rig.delay` s."""

    class Rig:
        delay = 0.3
        composed: list = []
        rows: list = []

    r = Rig()
    r.composed, r.rows = [], []

    async def _compose(db, market):
        r.composed.append(market.id)
        await asyncio.sleep(r.delay)
        return _verdict(len(r.composed))

    async def _row(side, market_id):
        r.rows.append((side, market_id))
        return _market(market_id)

    monkeypatch.setenv("VERIFIED_TITLE_CACHE_SECONDS", "60")
    monkeypatch.setattr(futures_mod, "_compose_verified_title", _compose)
    monkeypatch.setattr(events, "_verified_title_row", _row)
    monkeypatch.setattr(events, "_SEARCH_VERIFIED_TITLE_BUDGET_S", 0.05)
    futures_mod._VERIFIED_TITLE_CACHE.clear()
    yield r
    futures_mod._VERIFIED_TITLE_CACHE.clear()


async def _settle():
    for task in list(events._VERIFIED_TITLE_BACKGROUND.values()):
        await task


@pytest.mark.asyncio
async def test_a_composition_past_the_bound_finishes_and_the_next_build_prints_it(rig):
    engine, db = _engine_session()
    missed = []
    t0 = time.monotonic()
    first = await _search_verified_titles(db, [_market()], None, missed=missed)
    assert time.monotonic() - t0 < 0.25, "the search waited past its bound"
    assert first == {} and missed == [129037]
    await _settle()
    second_missed = []
    second = await _search_verified_titles(db, [_market()], None, missed=second_missed)
    assert isinstance(second.get(129037), Composition), "the finished verdict never reached the next build"
    assert second_missed == []
    assert rig.composed == [129037], "the next build composed again instead of reading the verdict"
    await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_searches_share_one_composition_per_market(rig):
    engine, db = _engine_session()
    await asyncio.gather(
        _search_verified_titles(db, [_market()], None),
        _search_verified_titles(db, [_market()], None),
        _search_verified_titles(db, [_market()], None),
    )
    await _settle()
    assert rig.composed == [129037]
    await engine.dispose()


@pytest.mark.asyncio
async def test_the_background_reads_its_own_row_on_its_own_session(rig):
    """Never the request's row or session: the task outlives the request (gotcha #6)."""
    engine, db = _engine_session()
    await _search_verified_titles(db, [_market()], None)
    await _settle()
    assert len(rig.rows) == 1
    side, market_id = rig.rows[0]
    assert market_id == 129037 and side is not db
    await engine.dispose()


@pytest.mark.asyncio
async def test_a_held_verdict_starts_nothing(rig, monkeypatch):
    engine, db = _engine_session()
    futures_mod._VERIFIED_TITLE_CACHE[129037] = (time.monotonic() + 60, _verdict("held"))

    def _no(*a, **k):  # pragma: no cover - must not be called
        raise AssertionError("a held verdict started a composition")

    monkeypatch.setattr(events, "_verified_title_in_background", _no)
    missed = []
    out = await _search_verified_titles(db, [_market()], None, missed=missed)
    assert out[129037].question_identity == {"tag": "held"}
    assert missed == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_the_deadline_floor_starts_nothing_and_reports_the_miss(rig):
    engine, db = _engine_session()
    deadline = time.monotonic() + events._SEARCH_VERIFIED_TITLE_MIN_REMAINING_S - 0.01
    missed = []
    assert await _search_verified_titles(db, [_market()], deadline, missed=missed) == {}
    assert missed == [129037]
    assert events._VERIFIED_TITLE_BACKGROUND == {} and rig.composed == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_a_full_pool_starts_nothing_and_reports_the_miss(rig, monkeypatch):
    engine, db = _engine_session(pool_size=1)
    monkeypatch.setattr(type(engine.pool), "checkedout", lambda self: 1)
    missed = []
    assert await _search_verified_titles(db, [_market()], None, missed=missed) == {}
    assert missed == [129037]
    assert events._VERIFIED_TITLE_BACKGROUND == {}
    await engine.dispose()


@pytest.mark.asyncio
async def test_the_background_has_a_ceiling_and_keeps_nothing_past_it(rig, monkeypatch):
    rig.delay = 5
    monkeypatch.setattr(events, "_VERIFIED_TITLE_BACKGROUND_CEILING_S", 0.1)
    engine, db = _engine_session()
    await _search_verified_titles(db, [_market()], None)
    task = events._VERIFIED_TITLE_BACKGROUND[129037]
    assert await asyncio.wait_for(task, timeout=2) is None
    assert 129037 not in futures_mod._VERIFIED_TITLE_CACHE
    await asyncio.sleep(0)
    assert 129037 not in events._VERIFIED_TITLE_BACKGROUND, "a finished task stayed registered"
    await engine.dispose()


@pytest.mark.asyncio
async def test_a_title_market_that_is_not_a_member_is_not_a_miss(rig):
    market = _market()
    market.market_metadata = {"polymarket_event_slug": "some-other-event"}
    engine, db = _engine_session()
    missed = []
    assert await _search_verified_titles(db, [market], None, missed=missed) == {}
    assert missed == [] and rig.composed == []
    await engine.dispose()


def test_a_page_that_missed_only_its_composition_is_cached_briefly():
    payload = {"futures": [{"id": 129037}]}
    assert shed_answer_ttl_seconds(["verified_title"], payload, debug_timing=False) == SEARCH_THIN_RESPONSE_TTL_SECONDS
    assert (
        shed_answer_ttl_seconds(["headline_contenders", "verified_title"], payload, debug_timing=False)
        == SEARCH_THIN_RESPONSE_TTL_SECONDS
    )
    assert shed_answer_ttl_seconds(["verified_title", "futures"], payload, debug_timing=False) is None
    assert shed_answer_ttl_seconds(["verified_title"], payload, debug_timing=True) is None


def test_the_route_declares_the_miss_before_the_cache_decision():
    import inspect

    src = inspect.getsource(events.search_events)
    call = src.index("missed=_verified_missed")
    declare = src.index('degraded.append("verified_title")')
    write = src.index("shed_answer_ttl_seconds(degraded, _payload")
    assert call < declare < write


@pytest.mark.asyncio
async def test_the_warmer_waits_for_the_composition_a_reader_does_not(rig):
    """#12335 step 5: no reader waits on the head warmer, and its event loop ends
    with its pass, so it waits for the verdict rather than leave it to be cancelled."""
    engine, db = _engine_session()
    token = events._force_search_cache_rebuild.set(True)
    try:
        missed = []
        out = await _search_verified_titles(db, [_market()], None, missed=missed)
    finally:
        events._force_search_cache_rebuild.reset(token)
    assert isinstance(out.get(129037), Composition) and missed == []
    futures_mod._VERIFIED_TITLE_CACHE.clear()
    reader_missed = []
    assert await _search_verified_titles(db, [_market(129038)], None, missed=reader_missed) == {}
    assert reader_missed == [129038], "CONTROL: a reader's build must still stop at its bound"
    await engine.dispose()


@pytest.mark.asyncio
async def test_the_warmer_still_respects_the_deadline_floor(rig):
    engine, db = _engine_session()
    deadline = time.monotonic() + events._SEARCH_VERIFIED_TITLE_MIN_REMAINING_S + 0.1
    token = events._force_search_cache_rebuild.set(True)
    try:
        t0 = time.monotonic()
        missed = []
        await _search_verified_titles(db, [_market()], deadline, missed=missed)
        took = time.monotonic() - t0
    finally:
        events._force_search_cache_rebuild.reset(token)
    assert took < 0.25 and missed == [129037]
    await engine.dispose()


@pytest.mark.asyncio
async def test_title_composes_during_independent_work_before_the_final_wait(rig, monkeypatch):
    """#11933: an event handshake proves overlap without a timing threshold."""
    began, release = asyncio.Event(), asyncio.Event()

    async def compose(db, market):
        rig.composed.append(market.id)
        began.set()
        await release.wait()
        return _verdict("overlapped")

    monkeypatch.setattr(futures_mod, "_compose_verified_title", compose)
    engine, db = _engine_session()
    started = events._prime_search_verified_title(db, [_market()], None)
    await asyncio.wait_for(began.wait(), timeout=2)
    # The route can complete its independent container/headline work here.
    release.set()
    await asyncio.wait_for(started[129037], timeout=2)
    out = await _search_verified_titles(db, [_market()], None, started=started)
    assert out[129037].question_identity == {"tag": "overlapped"}
    assert rig.composed == [129037]
    assert rig.rows[0][0] is not db
    await engine.dispose()


@pytest.mark.asyncio
async def test_priming_starts_only_one_title_and_reuses_an_existing_flight(rig):
    engine, db = _engine_session()
    first = events._prime_search_verified_title(db, [_market(), _market(129038)], None)
    second = events._prime_search_verified_title(db, [_market()], None)
    assert list(first) == [129037] and first[129037] is second[129037]
    await _settle()
    assert rig.composed == [129037]
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("guard", ["deadline", "full_pool", "no_pool_counters", "held", "not_title"])
async def test_priming_preserves_the_existing_no_new_read_guards(rig, monkeypatch, guard):
    engine, db = _engine_session()
    original_checkedout = type(engine.pool).checkedout
    market = _market()
    deadline = None
    if guard == "deadline":
        deadline = time.monotonic() + events._SEARCH_VERIFIED_TITLE_MIN_REMAINING_S - 0.1
    elif guard == "full_pool":
        monkeypatch.setattr(type(engine.pool), "checkedout", lambda self: 2)
    elif guard == "no_pool_counters":
        def no_count(self):
            raise RuntimeError("no counter")
        monkeypatch.setattr(type(engine.pool), "checkedout", no_count)
    elif guard == "held":
        futures_mod._VERIFIED_TITLE_CACHE[market.id] = (time.monotonic() + 60, _verdict("held"))
    else:
        market.market_metadata = {"polymarket_event_slug": "another-event"}
    assert events._prime_search_verified_title(db, [market], deadline) == {}
    assert rig.composed == [] and events._VERIFIED_TITLE_BACKGROUND == {}
    monkeypatch.setattr(type(engine.pool), "checkedout", original_checkedout)
    await engine.dispose()


@pytest.mark.asyncio
async def test_primed_read_is_not_retried_when_it_finishes_without_a_cached_verdict(rig, monkeypatch):
    engine, db = _engine_session()
    calls = []

    async def no_verdict(db, market):
        calls.append(market.id)
        return None

    monkeypatch.setattr(futures_mod, "_resolve_verified_title", no_verdict)
    started = events._prime_search_verified_title(db, [_market()], None)
    await started[129037]
    await asyncio.sleep(0)  # let the single-flight registry remove the completed task
    assert events._VERIFIED_TITLE_BACKGROUND == {}
    assert await _search_verified_titles(db, [_market()], None, started=started) == {}
    assert calls == [129037]
    await engine.dispose()


@pytest.mark.asyncio
async def test_primed_read_can_finish_when_its_own_connection_fills_the_pool(rig, monkeypatch):
    engine, db = _engine_session(pool_size=1)
    rig.delay = 0
    started = events._prime_search_verified_title(db, [_market()], None)
    monkeypatch.setattr(type(engine.pool), "checkedout", lambda self: 1)
    missed = []
    out = await _search_verified_titles(db, [_market()], None, started=started, missed=missed)
    assert isinstance(out[129037], Composition) and missed == []
    assert rig.composed == [129037]
    await engine.dispose()


def test_route_starts_title_before_container_reads_and_consumes_the_same_handle():
    import inspect

    src = inspect.getsource(events.search_events)
    start = src.index("_title_started = _prime_search_verified_title(")
    independent = src.index("await _search_container_parent_ids(")
    consume = src.index("started=_title_started")
    assert start < independent < consume
