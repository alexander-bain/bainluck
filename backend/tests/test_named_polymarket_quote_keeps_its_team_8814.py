"""Bulgaria's named .35 YES must not be published as .65 after a goal.

Live625, event15290678 at16:39:43Z. The actual PM moneyline60933567 has
Draw(Bulgaria vs Luxembourg), Bulgaria, Luxembourg. Its wrapped draw defeats
the old complete-partition proof; that must not unname the selected home quote.
"""

from types import SimpleNamespace

import pytest

from app.tasks import prediction_market_matching as poll
from app.tasks.live_blend_refresh import LiveBlendRefresher
from app.utils.live_blend import MarketOutcomes, compute_source_home_probability
from tests.test_named_three_way_quotes_keep_their_team_8814 import Session


def group(probability=0.35, names=None, market_id=60933567, source="polymarket"):
    market = SimpleNamespace(
        id=market_id,
        source=source,
        external_id="1016059",
        name="Bulgaria vs. Luxembourg",
    )
    named = names or [
        ("Draw (Bulgaria vs. Luxembourg)", 0.35),
        ("Bulgaria", probability),
        ("Luxembourg", 0.30),
    ]
    return MarketOutcomes(
        market,
        [
            SimpleNamespace(
                name=name,
                current_probability=p,
                rank=i,
                current_yes_bid=None,
                current_yes_ask=None,
            )
            for i, (name, p) in enumerate(named, 1)
        ],
    )


def reading(probability=0.35, names=None):
    r = compute_source_home_probability(
        [group(probability, names)], "Bulgaria", "Luxembourg"
    )
    assert r is not None
    return r


@pytest.mark.asyncio
@pytest.mark.parametrize("probability", [0.35, 0.355, 0.36])
async def test_incomplete_named_pm_quote_survives_stale_book_and_cached_flip(probability):
    source = reading(probability, names=[("Bulgaria", probability)])
    assert source.draw_probability is None, "fixture must test named home without partition proof"
    assert source.outcome.name == "Bulgaria"
    s = Session(0.66)
    arm = LiveBlendRefresher("polymarket")
    # Actual old binary helper creates the wrong cached decision.
    assert await arm._oriented(s, 15290678, 0.35) == 0.65
    stored = await arm._oriented(s, 15290678, source.home_probability, reading=source)
    assert stored == probability
    assert (
        await poll._orient_blend_reading(s, 15290678, source, "polymarket")
        == probability
    )
    assert 15290678 not in arm._inversion


def test_single_named_home_keeps_proof_without_inventing_partition():
    source = reading(names=[("Bulgaria", 0.35)])
    assert getattr(source, "named_home_quote", False)
    assert source.home_probability == source.yes_probability == 0.35
    assert source.away_probability is None and source.draw_probability is None


@pytest.mark.parametrize(
    "names",
    [
        [("Yes", 0.35), ("No", 0.65)],
        [("Bulgaria vs. Luxembourg", 0.35)],
        [("Luxembourg", 0.35)],
        [("Bulgaria", 0.35), ("Bulgaria FC", 0.40)],
    ],
)
def test_generic_full_matchup_away_only_and_duplicate_home_do_not_gain_proof(names):
    source = reading(names=names)
    assert not getattr(source, "named_home_quote", False)


def test_same_city_outcome_that_reaches_both_teams_is_not_identity_proof():
    entry = group(names=[("Manchester", 0.35), ("No", 0.65)])
    entry.market.name = "Manchester City vs Manchester United"
    source = compute_source_home_probability(
        [entry], "Manchester City", "Manchester United"
    )
    assert source is None or not getattr(source, "named_home_quote", False)


def test_decompose_then_devig_cannot_borrow_one_constituents_named_proof():
    source = compute_source_home_probability(
        [
            group(names=[("Bulgaria", 0.35)], market_id=60933567),
            group(names=[("Luxembourg", 0.40)], market_id=60933568),
        ],
        "Bulgaria",
        "Luxembourg",
    )
    assert source is not None and source.devigged
    assert not getattr(source, "named_home_quote", False)


@pytest.mark.asyncio
async def test_generic_binary_still_uses_existing_inversion_safeguard():
    source = reading(names=[("Yes", 0.35), ("No", 0.65)])
    # Choose an opposite consensus without depending on the matchup's YES-side
    # parser convention. The existing heuristic should still perform its job.
    book = 0.85 if source.home_probability < 0.5 else 0.15
    got = await poll._orient_blend_reading(
        Session(book), 15290678, source, "polymarket"
    )
    assert got == pytest.approx(1 - source.home_probability)


@pytest.mark.asyncio
async def test_phase2_writer_keeps_selected_pm_quote(monkeypatch):
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
    assert snapshots[0]["home_win_probability"] == 0.35
    assert snapshots[0]["game_state"]["outcome_name"] == "Bulgaria"
    assert session.stamped_sources()["polymarket"]["value"] == 0.35


@pytest.mark.asyncio
async def test_ws_writer_streams_selected_pm_home_without_inventing_partition(
    monkeypatch,
):
    from contextlib import asynccontextmanager
    import time
    from tests.test_live_blend_refresh import _RecordingSession

    source = reading(names=[("Bulgaria", 0.35)])
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
        returned={"polymarket": {"value": 0.35, "updated_at": stamp}},
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
    assert frames[0]["source_value"] == 0.35
    assert snapshots[0]["home_win_probability"] == 0.35
    assert snapshots[0]["away_win_probability"] == 0.65
    assert snapshots[0]["draw_probability"] is None
    assert snapshots[0]["game_state"]["outcome_name"] == "Bulgaria"
