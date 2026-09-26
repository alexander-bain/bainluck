"""Both named contributors must support a two-way devig before it is protected.

CE4 is a code counterexample, not a measured production frequency. A 30% home
YES and 72% away YES resolve to 29% home; a stale book must not rewrite it as 71%.
"""

from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace
import time

import pytest

from app.tasks import prediction_market_matching as poll
from app.tasks.live_blend_refresh import LiveBlendRefresher
from app.utils.live_blend import (
    MarketOutcomes,
    compute_source_home_probability,
    has_proven_home_orientation,
)
from tests.test_named_three_way_quotes_keep_their_team_8814 import Session


HOME, AWAY = "Boston Celtics", "Philadelphia 76ers"


def pair():
    entries = []
    for mid, suffix, name, price in [
        (1, "BOS", "Celtics", 0.30),
        (2, "PHI", "76ers", 0.72),
    ]:
        market = SimpleNamespace(
            id=mid,
            source="kalshi",
            external_id=f"KXNBAGAME-26OCT21BOSPHI-{suffix}",
            name="Celtics vs 76ers",
        )
        outcome = SimpleNamespace(
            id=mid,
            market_id=mid,
            external_id=str(mid),
            name=name,
            rank=1,
            current_probability=price,
            current_yes_bid=None,
            current_yes_ask=None,
        )
        entries.append(MarketOutcomes(market, [outcome]))
    return entries


def resolve(entries):
    return compute_source_home_probability(entries, HOME, AWAY)


@pytest.mark.parametrize("away_first", [False, True])
async def test_both_contributors_prove_devig_even_when_away_speaks_first(away_first):
    entries = pair()
    if away_first:
        entries[0].market.id, entries[1].market.id = 2, 1
    reading = resolve(entries)
    assert reading.devigged and reading.home_probability == pytest.approx(0.29)
    assert len(reading.contributing_outcomes) == 2
    assert not reading.named_home_quote
    assert has_proven_home_orientation(reading)
    session = Session(0.70)
    assert await poll._orient_blend_reading(
        session, 1, reading, "kalshi"
    ) == pytest.approx(0.29)
    assert session.queries == 0


async def test_named_pair_clears_previous_ws_flip():
    reading = resolve(pair())
    arm, session = LiveBlendRefresher("kalshi"), Session(0.70)
    assert await arm._oriented(session, 1, 0.29) == pytest.approx(0.71)
    assert await arm._oriented(session, 1, 0.29, reading=reading) == pytest.approx(0.29)
    assert 1 not in arm._inversion


@pytest.mark.parametrize(
    "mutation",
    [
        "guessed",
        "duplicate",
        "both_home",
        "other_fixture",
        "other_series",
        "same_ticker",
        "missing_fixture",
        "missing_side",
        "mixed_source",
        "unknown_format",
        "draw_on_home",
    ],
)
async def test_any_unproven_contributor_preserves_existing_fallback(mutation):
    entries = pair()
    home, away = entries
    if mutation == "guessed":
        away.outcomes[0].name = "Yes"
        away.outcomes[0].current_probability = 0.20
    elif mutation == "duplicate":
        away.outcomes.append(
            SimpleNamespace(name="Philadelphia 76ers", rank=2, current_probability=0.73)
        )
    elif mutation == "both_home":
        away.outcomes[0].name = "Celtics"
        away.outcomes[0].current_probability = 0.20
    elif mutation == "other_fixture":
        away.market.external_id = "KXNBAGAME-26OCT22BOSPHI-PHI"
    elif mutation == "other_series":
        away.market.external_id = "KXNFLGAME-26OCT21BOSPHI-PHI"
    elif mutation == "same_ticker":
        away.market.external_id = home.market.external_id
    elif mutation == "missing_fixture":
        home.market.external_id, away.market.external_id = (
            "KXNBAGAME--BOS",
            "KXNBAGAME--PHI",
        )
    elif mutation == "missing_side":
        away.market.external_id = "KXNBAGAME-26OCT21BOSPHI-"
    elif mutation == "mixed_source":
        away.market.source = "polymarket"
    elif mutation == "unknown_format":
        home.market.source = away.market.source = "polymarket"
        home.market.external_id, away.market.external_id = "11", "12"
    elif mutation == "draw_on_home":
        home.outcomes.append(
            SimpleNamespace(
                name="Draw (Celtics vs 76ers)", rank=2, current_probability=None
            )
        )
    reading = resolve(entries)
    assert reading is not None and reading.devigged
    assert not has_proven_home_orientation(reading)
    book = 0.85 if reading.home_probability < 0.5 else 0.15
    assert await poll._orient_blend_reading(
        Session(book), 1, reading, "kalshi"
    ) == pytest.approx(1 - reading.home_probability)


def test_explicit_draw_on_away_cannot_join_the_devig():
    entries = pair()
    entries[1].outcomes.append(
        SimpleNamespace(name="Tie", rank=2, current_probability=None)
    )
    reading = resolve(entries)
    assert not reading.devigged
    assert reading.home_probability == 0.30
    assert reading.named_home_quote  # Single raw home proof stays independent.
    assert not getattr(reading, "named_two_way_devig", False)


@pytest.mark.parametrize("mutation", ["unpriced", "derivative"])
def test_partial_or_inadmissible_pair_cannot_claim_full_contributor_proof(mutation):
    entries = pair()
    if mutation == "unpriced":
        entries[1].outcomes[0].current_probability = None
    else:
        entries[1].market.external_id = "KXNBASPREAD-26OCT21BOSPHI-PHI"
    reading = resolve(entries)
    assert not reading.devigged and reading.home_probability == 0.30
    assert not getattr(reading, "named_two_way_devig", False)


async def test_actual_matcher_persists_the_named_pair(monkeypatch):
    from tests.test_phase2_writer_group_reading_cert767 import (
        _FakeSession,
        _EventRow,
        _ref,
    )

    entries = pair()
    session = _FakeSession(
        [o for e in entries for o in e.outcomes], _EventRow(1, {}, opening=0.70)
    )
    monkeypatch.setattr(poll, "_blend_group_for_refs", lambda *a: entries)
    refs = [
        replace(
            _ref(
                e.market.id,
                e.market.name,
                source="kalshi",
                external_id=e.market.external_id,
                event_id=1,
            ),
            home_team_name=HOME,
            away_team_name=AWAY,
        )
        for e in entries
    ]
    snapshots = []

    async def snapshot(_session, **kwargs):
        snapshots.append(kwargs)
        return object(), True

    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", snapshot
    )
    await poll._phase2_persist_group_reading(
        session, refs, {"snapshots_written": 0, "snapshots_deduped": 0}
    )
    assert session.stamped_sources()["kalshi"]["value"] == pytest.approx(0.29)
    assert snapshots[0]["home_win_probability"] == pytest.approx(0.29)
    assert snapshots[0]["away_win_probability"] == pytest.approx(0.71)


async def test_actual_ws_resolver_clears_flip_before_snapshot_and_stream(monkeypatch):
    from tests.test_live_blend_refresh import _RecordingSession

    entries = pair()
    event = SimpleNamespace(
        id=1,
        home_team_name=HOME,
        away_team_name=AWAY,
        completed_at=None,
        status="live",
        espn_win_prob_home=None,
        opening_home_probability=0.70,
    )
    session = _RecordingSession(
        [(e.market, event) for e in entries],
        [o for e in entries for o in e.outcomes],
        returned={"kalshi": {"value": 0.29, "updated_at": "2026-09-26T21:00:00Z"}},
    )

    @asynccontextmanager
    async def get_session():
        yield session

    monkeypatch.setattr("app.tasks.base.get_task_session", get_session)
    snapshots, frames = [], []

    async def snapshot(_session, **kwargs):
        snapshots.append(kwargs)
        return object(), True

    async def publish(batch):
        frames.extend(batch)

    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", snapshot
    )
    arm = LiveBlendRefresher("kalshi")
    arm._inversion[1] = (time.monotonic() + 150, True)
    monkeypatch.setattr(arm, "_publish", publish)
    stats = await arm.refresh([1])
    assert stats["errors"] == 0
    assert snapshots[0]["home_win_probability"] == pytest.approx(0.29)
    assert frames[0]["source_value"] == pytest.approx(0.29)
    assert 1 not in arm._inversion


async def test_actual_live_poll_keeps_named_pair_against_stale_opening(monkeypatch):
    from app.utils import aggregation
    from tests.test_live_poll_commit_boundary_5682 import (
        _Event,
        _Population,
        _Session,
        _KalshiService,
        _run,
        _now,
    )

    entries = pair()
    event = _Event(1)
    event.home_team_name, event.away_team_name = HOME, AWAY
    event.opening_home_probability, event.win_probability_sources = 0.70, {}
    for e in entries:
        e.market.market_metadata = None
        e.market.market_type = "game_winner"
        for o in e.outcomes:
            o.last_updated = _now()
    population = _Population(
        [(e.market, event) for e in entries], [o for e in entries for o in e.outcomes]
    )
    session = _Session([population, population])

    async def get(*a):
        return event

    session.get = get
    stamped = []
    real = aggregation.stamp_source_reading

    def record(existing, source, value, **kwargs):
        stamped.append(value)
        return real(existing, source, value, **kwargs)

    monkeypatch.setattr(aggregation, "stamp_source_reading", record)
    stats = await _run(monkeypatch, session, kalshi=_KalshiService({}, []), blend={})
    assert not stats.get("errors")
    assert stamped == pytest.approx([0.29])
