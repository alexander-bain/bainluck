"""Ceuta's named 32.5% quote must not become 67.5% beside a real draw.

Production 15314954, 2026-09-26 13:12:15Z: WS snapshot raw Ceuta=.325,
stored home=.675/draw=NULL. A stale sportsbook .5771 caused a .275 quote
to be inverted and that Boolean remained cached for 150s after books caught up.
"""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.tasks import prediction_market_matching as poll
from app.tasks.live_blend_refresh import LiveBlendRefresher
from app.utils.live_blend import MarketOutcomes, compute_source_home_probability


def reading(home=0.325, away=0.365, draw=0.305):
    market = SimpleNamespace(
        id=62419263,
        source="kalshi",
        external_id="KXLALIGA2GAME-26SEP26CEURSO",
        name="Ceuta vs Real Sociedad B",
    )
    outcomes = [
        SimpleNamespace(
            name=name,
            current_probability=p,
            rank=rank,
            current_yes_bid=None,
            current_yes_ask=None,
        )
        for rank, (name, p) in enumerate(
            [("Ceuta", home), ("Real Sociedad B", away), ("Tie", draw)], 1
        )
    ]
    result = compute_source_home_probability(
        [MarketOutcomes(market, outcomes)], "AD Ceuta FC", "Real Sociedad B"
    )
    assert result is not None and result.draw_probability == draw
    return result


class Session:
    def __init__(self, consensus=0.5771):
        self.consensus = consensus
        self.queries = 0

    async def get(self, *args):
        return SimpleNamespace(
            opening_home_probability=0.3445, win_probability_sources={}
        )

    async def execute(self, *args):
        self.queries += 1
        return SimpleNamespace(scalar_one_or_none=lambda: self.consensus)


@pytest.mark.asyncio
async def test_named_home_quote_survives_the_stale_book_that_triggered_the_flip():
    source = reading(0.275, 0.410, 0.305)
    s = Session()
    home = await poll._orient_blend_reading(s, 15314954, source, "kalshi")
    assert home == 0.275
    assert poll._second_slot(source, home) == (0.410, 0.305)
    assert s.queries == 0, "named-side proof outranks a guessed price orientation"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "home,away,draw",
    [(0.325, 0.365, 0.305), (0.295, 0.395, 0.305), (0.475, 0.200, 0.325)],
)
async def test_cached_flip_cannot_replace_named_home_or_erase_its_draw(
    home, away, draw
):
    r = LiveBlendRefresher("kalshi", inversion_ttl_s=150)
    s = Session()
    # Reproduce the old decision with the actual helper; don't mock inversion.
    assert await r._oriented(s, 15314954, 0.275) == 0.725
    s.consensus = 0.2769
    source = reading(home, away, draw)
    stored = await r._oriented(s, 15314954, home, reading=source)
    assert stored == home
    assert poll._second_slot(source, stored) == (away, draw)
    assert await poll._orient_blend_reading(s, 15314954, source, "kalshi") == stored


@pytest.mark.asyncio
async def test_proven_partition_discards_old_boolean_before_a_later_two_way_reading():
    r = LiveBlendRefresher("kalshi", inversion_ttl_s=150)
    s = Session()
    assert await r._oriented(s, 15314954, 0.275) == 0.725
    s.consensus = 0.2769
    source = reading()
    assert await r._oriented(s, 15314954, 0.325, reading=source) == 0.325
    # Losing partition evidence must re-check consensus, not resurrect the
    # previously disproven cached flip.
    assert await r._oriented(s, 15314954, 0.325) == 0.325


@pytest.mark.asyncio
@pytest.mark.parametrize("away,draw", [(None, None), (0.410, None), (None, 0.305)])
async def test_unproven_partition_cannot_overturn_named_home_identity(away, draw):
    source = replace(
        reading(0.275, 0.410, 0.305), away_probability=away, draw_probability=draw
    )
    assert (
        await poll._orient_blend_reading(Session(), 15314954, source, "kalshi") == 0.275
    )


@pytest.mark.asyncio
async def test_phase2_writer_persists_the_named_home_and_real_draw(monkeypatch):
    from tests.test_phase2_writer_group_reading_cert767 import (
        _FakeSession,
        _EventRow,
        _ref,
    )

    source = reading(0.275, 0.410, 0.305)
    session = _FakeSession([], _EventRow(15314954, {}, opening=0.5771))
    monkeypatch.setattr(poll, "_compute_source_home_probability", lambda *a: source)
    snapshots = []

    async def snapshot(_session, **kwargs):
        snapshots.append(kwargs)
        return object(), True

    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", snapshot
    )
    stats = {"snapshots_written": 0, "snapshots_deduped": 0}
    await poll._phase2_persist_group_reading(
        session,
        [
            _ref(
                62419263,
                "Ceuta vs Real Sociedad B",
                source="kalshi",
                external_id="KXLALIGA2GAME-26SEP26CEURSO",
                event_id=15314954,
            )
        ],
        stats,
    )
    assert snapshots[0]["home_win_probability"] == 0.275
    assert snapshots[0]["away_win_probability"] == 0.410
    assert snapshots[0]["draw_probability"] == 0.305
    assert session.stamped_sources()["kalshi"]["value"] == 0.275


@pytest.mark.asyncio
async def test_ws_writer_streams_real_home_and_keeps_snapshot_partition(monkeypatch):
    from contextlib import asynccontextmanager
    import time
    from tests.test_live_blend_refresh import _RecordingSession

    source = reading()
    event = SimpleNamespace(
        id=15314954,
        home_team_name="AD Ceuta FC",
        away_team_name="Real Sociedad B",
        completed_at=None,
        status="live",
        espn_win_prob_home=None,
        opening_home_probability=0.3445,
    )
    stamp = "2026-09-26T13:12:15.486123+00:00"
    session = _RecordingSession(
        [(source.market, event)],
        [],
        returned={"kalshi": {"value": 0.325, "updated_at": stamp}},
    )

    @asynccontextmanager
    async def get_session():
        yield session

    monkeypatch.setattr("app.tasks.base.get_task_session", get_session)
    monkeypatch.setattr(
        "app.utils.live_blend.compute_source_home_probability", lambda *a: source
    )
    snapshots = []

    async def snapshot(_session, **kwargs):
        snapshots.append(kwargs)
        return object(), True

    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", snapshot
    )
    frames = []

    async def publish(batch):
        frames.extend(batch)

    r = LiveBlendRefresher("kalshi")
    r._inversion[15314954] = (time.monotonic() + 150, True)
    monkeypatch.setattr(r, "_publish", publish)
    stats = await r.refresh([15314954])
    assert stats["errors"] == 0
    assert frames[0]["source_value"] == 0.325
    assert snapshots[0]["home_win_probability"] == 0.325
    assert snapshots[0]["away_win_probability"] == 0.365
    assert snapshots[0]["draw_probability"] == 0.305
    assert snapshots[0]["game_state"]["outcome_name"] == "Ceuta"
