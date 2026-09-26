"""CE1/2/3/5: a missing partition never licenses swapping a named quote."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.tasks import prediction_market_matching as poll
from app.tasks.live_blend_refresh import LiveBlendRefresher
from app.utils.live_blend import (
    MarketOutcomes,
    compute_source_home_probability,
    has_proven_home_orientation,
)
from tests.test_named_three_way_quotes_keep_their_team_8814 import Session


def entry(
    names,
    source="polymarket",
    external_id="1016059",
    market_name="Bulgaria vs. Luxembourg",
):
    return MarketOutcomes(
        SimpleNamespace(
            id=60933567, source=source, external_id=external_id, name=market_name
        ),
        [
            SimpleNamespace(
                name=name,
                current_probability=p,
                rank=i,
                current_yes_bid=None,
                current_yes_ask=None,
            )
            for i, (name, p) in enumerate(names, 1)
        ],
    )


def incomplete_away(draw=0.42):
    return entry(
        [
            ("Draw (Bulgaria vs. Luxembourg)", draw),
            ("Bulgaria", None),
            ("Luxembourg", 0.255),
        ]
    )


def ceuta(home=0.275, away=0.33, draw=0.28):
    return compute_source_home_probability(
        [
            entry(
                [("Ceuta", home), ("Real Sociedad B", away), ("Tie", draw)],
                "kalshi",
                "KXLALIGA2GAME-26SEP26CEURSO",
                "Ceuta vs Real Sociedad B",
            )
        ],
        "AD Ceuta FC",
        "Real Sociedad B",
    )


@pytest.mark.parametrize("draw", [0.42, None, 0])
def test_ce1_named_away_with_known_draw_refuses_fabricated_home(draw):
    assert (
        compute_source_home_probability(
            [incomplete_away(draw)], "Bulgaria", "Luxembourg"
        )
        is None
    )


@pytest.mark.asyncio
async def test_ce2_named_kalshi_home_outside_partition_band_keeps_its_quote():
    r = ceuta()
    assert r.home_probability == 0.275 and r.draw_probability is None
    assert has_proven_home_orientation(r)
    s = Session(0.5771)
    assert await poll._orient_blend_reading(s, 15314954, r, "kalshi") == 0.275
    arm = LiveBlendRefresher("kalshi")
    assert await arm._oriented(s, 15314954, r.home_probability, reading=r) == 0.275
    assert 15314954 not in arm._inversion


@pytest.mark.asyncio
async def test_ce3_cached_flip_is_retired_before_next_named_tick():
    s = Session(0.5771)
    arm = LiveBlendRefresher("kalshi")
    assert await arm._oriented(s, 15314954, 0.275) == 0.725
    for r, book in [(ceuta(), 0.5771), (ceuta(0.325, 0.30, 0.26), 0.2769)]:
        s.consensus = book
        assert r.draw_probability is None
        assert (
            await arm._oriented(s, 15314954, r.home_probability, reading=r)
            == r.home_probability
        )
        assert 15314954 not in arm._inversion


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source,ticker",
    [("polymarket", "1016059"), ("kalshi", "KXWCQGAME-26SEP26BULLUX-BUL")],
)
async def test_ce5_same_named_home_has_same_proof_across_sources(source, ticker):
    r = compute_source_home_probability(
        [entry([("Bulgaria", 0.35)], source, ticker)], "Bulgaria", "Luxembourg"
    )
    assert r is not None and has_proven_home_orientation(r)
    assert await poll._orient_blend_reading(Session(0.66), 1, r, source) == 0.35


def test_unknown_format_away_only_remains_unproved_not_called_two_way():
    # Deliberate remaining boundary: no draw member or trustworthy format here.
    r = compute_source_home_probability(
        [entry([("Luxembourg", 0.255)])], "Bulgaria", "Luxembourg"
    )
    assert r is not None and r.home_probability == pytest.approx(0.745)
    assert not has_proven_home_orientation(r)


@pytest.mark.asyncio
async def test_real_guessed_binary_retains_legacy_inversion():
    r = compute_source_home_probability(
        [
            entry(
                [("Yes", 0.275), ("No", 0.725)],
                "kalshi",
                "KXNBAGAME-26OCT21BOSPHI-BOS",
                "Celtics vs 76ers",
            )
        ],
        "Boston Celtics",
        "Philadelphia 76ers",
    )
    assert r is not None and not has_proven_home_orientation(r)
    book = 0.85 if r.home_probability < 0.5 else 0.15
    assert await poll._orient_blend_reading(
        Session(book), 1, r, "kalshi"
    ) == pytest.approx(1 - r.home_probability)


@pytest.mark.asyncio
async def test_ce1_matcher_makes_no_fabricated_write_or_snapshot(monkeypatch):
    from tests.test_phase2_writer_group_reading_cert767 import (
        _FakeSession,
        _EventRow,
        _ref,
    )

    board = incomplete_away()
    old = {"polymarket": {"value": 0.335, "updated_at": "2026-09-26T16:00:00Z"}}
    for row in board.outcomes:
        row.market_id = 60933567
    session = _FakeSession(board.outcomes, _EventRow(15290678, old, opening=0.4))
    # Actual resolver and retirement path, not a mocked None reading.
    monkeypatch.setattr(poll, "_blend_group_for_refs", lambda *a: [board])

    async def snapshot(*a, **kw):
        pytest.fail("a refused home reading cannot create a snapshot")

    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", snapshot
    )
    assert (
        await poll._phase2_persist_group_reading(
            session,
            [
                replace(
                    _ref(60933567, "Bulgaria vs. Luxembourg", event_id=15290678),
                    home_team_name="Bulgaria",
                    away_team_name="Luxembourg",
                )
            ],
            {},
        )
        is None
    )
    # A missing price is transient; do not pretend this patch retires the source.
    assert not session.updates


@pytest.mark.asyncio
async def test_ce1_ws_refuses_without_restamping_or_claiming_a_removal(monkeypatch):
    from contextlib import asynccontextmanager
    from tests.test_live_blend_refresh import _RecordingSession

    board = incomplete_away()
    for row in board.outcomes:
        row.market_id = 60933567
    old = {"polymarket": {"value": 0.335, "updated_at": "2026-09-26T16:00:00Z"}}
    event = SimpleNamespace(
        id=15290678,
        home_team_name="Bulgaria",
        away_team_name="Luxembourg",
        completed_at=None,
        status="live",
        espn_win_prob_home=None,
        opening_home_probability=0.4,
        win_probability_sources=old,
    )
    session = _RecordingSession([(board.market, event)], board.outcomes, returned=old)

    @asynccontextmanager
    async def get_session():
        yield session

    monkeypatch.setattr("app.tasks.base.get_task_session", get_session)

    async def snapshot(*a, **kw):
        pytest.fail("refused home cannot write a snapshot")

    monkeypatch.setattr(
        "app.tasks.snapshots._create_or_update_win_prob_snapshot", snapshot
    )
    frames = []

    async def publish(batch):
        frames.extend(batch)

    arm = LiveBlendRefresher("polymarket")
    monkeypatch.setattr(arm, "_publish", publish)
    stats = await arm.refresh([15290678])
    assert stats["errors"] == 0 and stats["no_reading"] == 1
    assert session.updates == [] and frames == []
    assert event.win_probability_sources == old  # aging/removal is not paid here


@pytest.mark.asyncio
@pytest.mark.parametrize("home,expected", [(None, []), (0.335, [0.335])])
async def test_ce1_live_poll_refuses_missing_home_but_keeps_priced_control(
    monkeypatch, home, expected
):
    from app.utils import aggregation
    from tests.test_live_poll_commit_boundary_5682 import (
        _Market,
        _Outcome,
        _Event,
        _Population,
        _Session,
        _PolyService,
        _run,
        _now,
    )

    market = _Market(60933567, "polymarket", "1016059")
    market.name = "Bulgaria vs. Luxembourg"
    event = _Event(15290678)
    event.home_team_name = "Bulgaria"
    event.away_team_name = "Luxembourg"
    event.opening_home_probability = 0.4
    event.win_probability_sources = {}
    outcomes = []
    for i, (name, prob) in enumerate(
        [
            ("Draw (Bulgaria vs. Luxembourg)", 0.42),
            ("Bulgaria", home),
            ("Luxembourg", 0.255),
        ],
        1,
    ):
        row = _Outcome(i, market.id, str(i), name)
        row.current_probability = prob
        row.last_updated = _now()
        row.rank = i
        outcomes.append(row)
    population = _Population([(market, event)], outcomes)
    session = _Session([population, population])

    async def get(*args):
        return event

    session.get = get
    stamped = []
    real = aggregation.stamp_source_reading

    def record(existing, source, value, **kwargs):
        stamped.append(value)
        return real(existing, source, value, **kwargs)

    monkeypatch.setattr(aggregation, "stamp_source_reading", record)
    stats = await _run(monkeypatch, session, poly=_PolyService({}, []), blend={})
    assert not stats.get("errors")
    assert stamped == expected


@pytest.mark.asyncio
async def test_ce2_ws_writer_keeps_named_home_when_partition_is_out_of_band(
    monkeypatch,
):
    from contextlib import asynccontextmanager
    import time
    from tests.test_live_blend_refresh import _RecordingSession

    source = ceuta()
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
        returned={"kalshi": {"value": 0.275, "updated_at": stamp}},
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
    assert frames[0]["source_value"] == 0.275
    assert snapshots[0]["home_win_probability"] == 0.275
    assert snapshots[0]["away_win_probability"] == 0.725
    assert snapshots[0]["draw_probability"] is None
    assert snapshots[0]["game_state"]["outcome_name"] == "Ceuta"
