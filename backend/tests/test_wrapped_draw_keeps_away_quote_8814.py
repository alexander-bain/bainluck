"""PM60933567: Luxembourg's .255 quote must not absorb the .420 draw."""

from types import SimpleNamespace

import pytest

from app.utils.live_blend import compute_source_home_probability
from app.utils.prediction_market_matching import find_three_way_partition
from tests.test_named_polymarket_quote_keeps_its_team_8814 import group


def specimen(draw_name="Draw (Bulgaria vs. Luxembourg)", draw=0.420):
    # Exact saved market-outcomes.json for15290678/60933567, not inferred prices.
    return group(names=[(draw_name, draw), ("Bulgaria", 0.335), ("Luxembourg", 0.255)])


def reading(entry=None):
    return compute_source_home_probability(
        [entry or specimen()], "Bulgaria", "Luxembourg"
    )


@pytest.mark.parametrize(
    "name", ["Draw (Bulgaria vs. Luxembourg)", "Tie (Bulgaria vs. Luxembourg)"]
)
def test_same_fixture_wrapped_draw_preserves_all_three_real_quotes(name):
    result = reading(specimen(name))
    assert (
        result.home_probability,
        result.away_probability,
        result.draw_probability,
    ) == (0.335, 0.255, 0.420)


@pytest.mark.parametrize(
    "name",
    [
        "Bulgaria vs. Luxembourg",
        "Reg Time: Tie (Bulgaria vs. Luxembourg)",
        "Tie 1st Half (Bulgaria vs. Luxembourg)",
        "Draw (Bulgaria vs. Luxembourg",
        "Draw (Bulgaria vs. Luxembourg) regulation",
        "Bulgaria 1 - 1 Luxembourg",
    ],
)
def test_matchup_or_qualified_or_truncated_wrapper_remains_refused(name):
    result = reading(specimen(name))
    assert result is None or (
        result.away_probability is None and result.draw_probability is None
    )


def test_foreign_fixture_wrapper_cannot_become_a_draw():
    entry = specimen("Draw (Bulgaria vs. France)")
    assert (
        find_three_way_partition(
            entry.outcomes, entry.outcomes[1], "Bulgaria", "Luxembourg"
        )
        is None
    )


@pytest.mark.parametrize("draw", [0, 1, 0.02, 0.8])
def test_endpoints_and_incoherent_sum_still_refuse(draw):
    result = reading(specimen(draw=draw))
    assert result is None or (
        result.away_probability is None and result.draw_probability is None
    )


def test_wrapped_draw_does_not_relax_unique_member_or_anchor_identity():
    entry = specimen()
    for anchor in [
        entry.outcomes[0],
        entry.outcomes[2],
        SimpleNamespace(name="Bulgaria", current_probability=0.335),
    ]:
        assert (
            find_three_way_partition(entry.outcomes, anchor, "Bulgaria", "Luxembourg")
            is None
        )
    for name in ["Bulgaria", "Luxembourg", "Tie"]:
        duplicate = SimpleNamespace(name=name, current_probability=0.1)
        assert (
            find_three_way_partition(
                [*entry.outcomes, duplicate],
                entry.outcomes[1],
                "Bulgaria",
                "Luxembourg",
            )
            is None
        )


@pytest.mark.asyncio
async def test_matcher_persists_opponent_quote_and_draw_not_complement(monkeypatch):
    from app.tasks import prediction_market_matching as poll
    from tests.test_phase2_writer_group_reading_cert767 import (
        _FakeSession,
        _EventRow,
        _ref,
    )

    source = reading()
    session = _FakeSession([], _EventRow(15290678, {}, opening=0.66))
    monkeypatch.setattr(poll, "_compute_source_home_probability", lambda *a: source)
    snapshots = []

    async def snapshot(_session, **kwargs):
        snapshots.append(kwargs)
        return object(), True

    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", snapshot
    )
    await poll._phase2_persist_group_reading(
        session,
        [_ref(60933567, "Bulgaria vs. Luxembourg", event_id=15290678)],
        {"snapshots_written": 0, "snapshots_deduped": 0},
    )
    assert snapshots[0]["home_win_probability"] == 0.335
    assert snapshots[0]["away_win_probability"] == 0.255
    assert snapshots[0]["draw_probability"] == 0.420
    assert session.stamped_sources()["polymarket"]["value"] == 0.335


@pytest.mark.asyncio
async def test_ws_writer_streams_raw_home_with_real_away_and_draw(
    monkeypatch,
):
    from app.tasks.live_blend_refresh import LiveBlendRefresher
    from contextlib import asynccontextmanager
    import time
    from tests.test_live_blend_refresh import _RecordingSession

    source = reading()
    event = SimpleNamespace(
        id=15290678,
        home_team_name="Bulgaria",
        away_team_name="Luxembourg",
        completed_at=None,
        status="live",
        espn_win_prob_home=None,
        opening_home_probability=0.66,
    )
    stamp = "2026-09-26T13:12:15.486123+00:00"
    session = _RecordingSession(
        [(source.market, event)],
        [],
        returned={"polymarket": {"value": 0.335, "updated_at": stamp}},
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

    r = LiveBlendRefresher("polymarket")
    r._inversion[15290678] = (time.monotonic() + 150, True)
    monkeypatch.setattr(r, "_publish", publish)
    stats = await r.refresh([15290678])
    assert stats["errors"] == 0
    assert frames[0]["source_value"] == 0.335
    assert snapshots[0]["home_win_probability"] == 0.335
    assert snapshots[0]["away_win_probability"] == 0.255
    assert snapshots[0]["draw_probability"] == 0.420
    assert snapshots[0]["game_state"]["outcome_name"] == "Bulgaria"
