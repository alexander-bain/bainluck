"""A folded stream sends the same authoritative quote as detail, once per update."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from app.utils import folded_live_quote as module
from app.utils.hero_probability import resolve_hero
from app.utils.proven_duplicates import FoldedBlendView, merge_probability_sources


def install_read(monkeypatch, *, status="live", sport="basketball_nba", canonical=None, twin=None):
    clock = datetime.now(timezone.utc).isoformat()
    canonical = {"espn": {"value": 0.2, "updated_at": clock}} if canonical is None else canonical
    twin = {"kalshi": {"value": 0.8, "updated_at": clock}} if twin is None else twin
    event = SimpleNamespace(
        id=1, status=status, home_team_name="Home", away_team_name="Away",
        home_score=3, away_score=2, completed_at=datetime.now(timezone.utc),
        win_probability_sources={"espn": 0.99}, espn_win_prob_home=None,
        opening_home_probability=0.3, opening_away_probability=0.7,
        commence_time=datetime.now(timezone.utc),
        sport=SimpleNamespace(key=sport), sport_id=1,
    )
    absorbed = SimpleNamespace(id=2, win_probability_sources=twin)
    reads = []

    class DB:
        async def execute(self, statement):
            reads.append(statement)
            if len(reads) == 1:
                return SimpleNamespace(scalar_one_or_none=lambda: event)
            return SimpleNamespace(all=lambda: [
                (1, "Home", "Away", canonical, 11, False),
                (2, "Home", "Away", twin, 22, False),
            ])

    @asynccontextmanager
    async def factory():
        yield DB()

    async def fold(db, target):
        assert target is event
        return [absorbed]

    monkeypatch.setattr(module, "async_session_maker", factory)
    monkeypatch.setattr(module, "serve_fold_absorbed_rows", fold)
    return event, canonical, twin, clock, reads


async def test_projection_uses_one_snapshot_full_vector_shared_hero_and_clock(monkeypatch):
    event, canonical, twin, clock, reads = install_read(monkeypatch)
    quote = await module.load_folded_quote(1, 2, 22)
    expected = resolve_hero(FoldedBlendView(event, merge_probability_sources(canonical, [(2, twin)])))
    assert quote["hero_probability"] == expected.home_probability
    assert quote["hero_probability_away"] == expected.away_probability
    assert quote["hero_probability_source"] == "blend"
    assert quote["hero_probability_observed_at"] == clock
    assert quote["blend_fold_revision"] == {"1": 11, "2": 22}
    assert set(quote["win_probability_sources"]) == {"espn", "kalshi"}
    assert quote["win_probability_sources"]["espn"]["value"] == 0.2
    assert len(reads) == 2  # compact event inputs + existing one-snapshot fold


async def test_removal_keeps_full_revision_without_borrowing_trigger_clock(monkeypatch):
    older = "2026-10-08T10:00:00+00:00"
    install_read(monkeypatch, canonical={"espn": {"value": 0.2, "updated_at": older}},
                 twin={"kalshi": None})
    quote = await module.load_folded_quote(1, 2, 22)
    assert quote["blend_fold_revision"] == {"1": 11, "2": 22}
    assert set(quote["win_probability_sources"]) == {"espn"}
    assert quote["hero_probability_observed_at"] == older


@pytest.mark.parametrize("status,sport,source,away", [
    ("live", "soccer_epl", "blend", None),
    ("completed", "soccer_epl", "settled", 0.0),
])
async def test_draw_and_settlement_semantics_use_existing_resolvers(monkeypatch, status, sport, source, away):
    install_read(monkeypatch, status=status, sport=sport)
    quote = await module.load_folded_quote(1, 2, 22)
    assert quote["hero_probability_source"] == source
    assert quote["hero_probability_away"] == away
    if source == "settled":
        assert quote["hero_probability"] == 1.0
        assert quote["hero_settled_result"] == "home"
        assert quote["hero_probability_observed_at"] is None


async def test_refused_sources_and_pm_price_evidence_match_detail(monkeypatch):
    from app.utils.probability_source_format import format_probability_sources
    from app.utils.probability_eligibility import ELIGIBILITY_KEY, EligibilityRecord, INELIGIBLE

    event, canonical, twin, _, _ = install_read(monkeypatch, twin={"polymarket": 0.5})
    calls = []

    async def evidence(db, entry):
        calls.append(entry)
        return "unproven"

    monkeypatch.setattr(module, "load_price_evidence", evidence)
    quote = await module.load_folded_quote(1, 2, 22)
    expected = format_probability_sources(merge_probability_sources(canonical, [(2, twin)]))
    expected["polymarket"]["price_evidence"] = "unproven"
    assert quote["win_probability_sources"] == expected
    assert calls == [0.5]
    refused = {"value": 0.99, ELIGIBILITY_KEY: EligibilityRecord(status=INELIGIBLE).to_entry()}
    assert format_probability_sources({"kalshi": refused}) == {}
    assert format_probability_sources({"statpal_plays": [], "_internal": 1,
                                       "betting_book_count": 4}) == {
        "betting_book_count": {"value": 4, "display_name": "betting_book_count",
                               "type": "model", "color": "#6b7280",
                               "evidence_status": "not_applicable"},
    }


@pytest.mark.parametrize("origin,revision", [(2, 23), (3, 1)])
async def test_missing_or_behind_origin_cannot_claim_fold_authority(monkeypatch, origin, revision):
    install_read(monkeypatch)
    assert await module.load_folded_quote(1, origin, revision) is None


def trigger(origin=2, revision=22):
    return {"event_id": origin, "rev": {str(origin): revision}, "status": "live",
            "updated_at": datetime.now(timezone.utc).isoformat(), "p": 0.8}


async def until(predicate):
    async with asyncio.timeout(1):
        while not predicate():
            await asyncio.sleep(0)


async def test_recipients_share_one_read_and_canceling_one_keeps_other(monkeypatch):
    calls, release = [], asyncio.Event()

    async def load(*args):
        calls.append(args)
        await release.wait()
        return {"event_id": args[0]}

    monkeypatch.setattr(module, "load_folded_quote", load)
    projector, frame = module.FoldedQuoteProjector(), trigger()
    first = asyncio.create_task(projector.project(1, frame))
    second = asyncio.create_task(projector.project(1, frame))
    try:
        await until(lambda: len(calls) == 1)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert not second.done()
        release.set()
        assert await second == {"event_id": 1}
        assert await projector.project(1, frame) == {"event_id": 1}
        assert calls == [(1, 2, 22)] and not projector._pending
    finally:
        release.set()
        await asyncio.gather(first, second, return_exceptions=True)


async def test_last_cancel_joins_shared_db_cleanup_even_when_cancelled_twice(monkeypatch):
    cleaning, release, cleaned = asyncio.Event(), asyncio.Event(), asyncio.Event()
    owners = []

    async def load(*args):
        owners.append(asyncio.current_task())
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release.wait()
            cleaned.set()

    monkeypatch.setattr(module, "load_folded_quote", load)
    projector, frame = module.FoldedQuoteProjector(), trigger()
    task = asyncio.create_task(projector.project(1, frame))
    try:
        await until(lambda: bool(owners))
        task.cancel()
        await asyncio.wait_for(cleaning.wait(), 1)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done() and not cleaned.is_set()
        assert await projector.project(1, frame) is None
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cleaned.is_set() and owners[0].done() and not projector._pending
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_projection_timeout_and_capacity_remain_bounded(monkeypatch):
    active = maximum = 0

    async def load(*args):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        try:
            await asyncio.Event().wait()
        finally:
            active -= 1

    monkeypatch.setattr(module, "load_folded_quote", load)
    monkeypatch.setattr(module, "PROJECTION_TIMEOUT_S", 0.05)
    projector = module.FoldedQuoteProjector()
    tasks = [asyncio.create_task(projector.project(i, trigger())) for i in range(8)]
    try:
        await until(lambda: len(projector._pending) == 8 and active == 2)
        assert await projector.project(9, trigger()) is None
        assert await asyncio.gather(*tasks) == [None] * 8
        assert maximum == 2 and active == 0 and not projector._pending
    finally:
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.parametrize("available", [True, False])
async def test_folded_stream_yields_raw_immediately_then_explicit_authority(monkeypatch, available):
    from app.routes import event_stream as route
    from app.utils import live_fanout
    from tests.test_folded_event_stream_invalidation_837 import Hub, Request

    hub, release, calls = Hub(), asyncio.Event(), []
    quote = ({"event_id": 1, "hero_probability": 0.4,
              "blend_fold_revision": {"1": 11, "2": 22}} if available else None)

    async def project(event_id, frame):
        calls.append((event_id, frame))
        await release.wait()
        return quote

    hub.project_folded_quote = project
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    monkeypatch.setattr(route, "latest_frames", lambda ids: asyncio.sleep(0, result=[]))
    stream = route._stream(1, Request(), [1, 2])
    task = None
    try:
        await anext(stream)
        await anext(stream)
        frame = trigger()
        hub.subscriptions["live:event:2"].offer(json.dumps(frame))
        raw = json.loads((await asyncio.wait_for(anext(stream), 1)).split("data: ")[1])
        assert raw["invalidation"] and raw["p"] is None and not calls
        assert raw["folded_quote_pending"] is True
        task = asyncio.create_task(anext(stream))
        await until(lambda: bool(calls))
        assert not task.done()
        release.set()
        chunk = await task
        assert chunk.startswith("event: folded_probability\n")
        enriched = json.loads(chunk.split("data: ")[1])
        assert enriched == {**raw, "folded_quote_pending": False, "folded_quote": quote}
        assert calls == [(1, frame)]
    finally:
        release.set()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        await stream.aclose()


async def test_singleton_stream_never_requests_projection(monkeypatch):
    from app.routes import event_stream as route
    from app.utils import live_fanout
    from tests.test_folded_event_stream_invalidation_837 import Hub, Request

    hub = Hub()

    async def forbidden(*args):
        raise AssertionError("single-row fast path must remain database-free")

    hub.project_folded_quote = forbidden
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    monkeypatch.setattr(route, "latest_frames", lambda ids: asyncio.sleep(0, result=[]))
    stream = route._stream(1, Request(), [1])
    try:
        await anext(stream)
        await anext(stream)
        frame = trigger(1)
        hub.subscriptions["live:event:1"].offer(json.dumps(frame))
        raw = json.loads((await anext(stream)).split("data: ")[1])
        assert raw == frame
    finally:
        await stream.aclose()
