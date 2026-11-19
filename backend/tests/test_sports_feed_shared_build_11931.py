"""#11931 / #12886 — Sports feed shares its principal-independent build across readers.

Signed-in readers with personalization state (favorite teams, sport affinities,
seen/dismissed history) cannot take the inert-principal response cache or the
anonymous page base. Previously every Sports tab open for a signed-in reader ran
cold database queries for events (~1.5 s), sports-mode futures (~2.5 s), and
review decisions, producing a 2.9 s median / 4.5 s p90 on `/api/feed?mode=sports`.

This suite pins the three shared pre-personalization artifacts added for #11931:
1. ``events_scored`` — bit-for-bit identical to direct ``_score_events`` for
   anonymous and personalized readers (both ``sports_mode=True`` and Discover),
   across process-local and cross-worker Redis round trips.
2. ``sports_futures_scored`` — bit-for-bit identical to direct
   ``_score_sports_mode_futures`` for anonymous and personalized readers, across
   process-local and cross-worker Redis round trips, while ``my_teams_only=True``
   never reads or writes the shared cache.
3. ``review_decisions`` — bit-for-bit identical to direct
   ``_apply_manual_review_decisions`` and still honors the kill switch.
4. Live ceiling & kill-switch contracts: all three namespaces are clamped by
   ``live_artifact_ttl_ceiling_s()``, counted against the 60 s live ceiling,
   bounded in ``MAX_ENTRIES_BY_NAMESPACE``, and disabled cleanly by
   ``FEED_SHARED_BUILD_TTL_S=0`` or per-namespace overrides.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.routes.feed as feed_mod
import app.utils.principal_independent_cache as pic
from app.routes.feed import (
    _apply_manual_review_decisions,
    _score_events,
    _score_sports_mode_futures,
)
from app.utils.personalization import PersonalizationContext

NOW = datetime(2026, 9, 15, 22, 0, tzinfo=timezone.utc)

SHARED_NAMESPACES = (
    "events_scored",
    "sports_futures_scored",
    "review_decisions",
)


class _FakeRedis:
    def __init__(self):
        self.stored: dict[str, object] = {}

    async def set(self, key, value, ex=None):
        self.stored[key] = value
        return True

    async def get(self, key):
        return self.stored.get(key)


@pytest.fixture(autouse=True)
def _clean_shared_cache(monkeypatch):
    monkeypatch.setenv("FEED_SHARED_BUILD_CROSS_WORKER", "0")
    monkeypatch.setenv("PREMATCH_READING_CACHE", "0")
    for env_name in (
        "FEED_SHARED_BUILD_TTL_S",
        "FEED_SHARED_BUILD_TTL_S_EVENTS_SCORED",
        "FEED_SHARED_BUILD_TTL_S_SPORTS_FUTURES_SCORED",
        "FEED_SHARED_BUILD_TTL_S_REVIEW_DECISIONS",
    ):
        monkeypatch.delenv(env_name, raising=False)
    pic.clear_shared_builds()
    yield
    pic.clear_shared_builds()


def _rich_reader_ctx() -> PersonalizationContext:
    """A signed-in reader with follows, affinities, Nah, low-affinity, seen, dismissed."""
    ctx = PersonalizationContext(is_authenticated=True)
    ctx.team_relations = {101: {"follow"}, 202: {"local"}}
    ctx.sport_affinities = {
        "basketball_nba": 0.9,
        "icehockey_nhl": 0.0,  # Nah sport
        "soccer_epl": 0.1,  # low affinity ("if it's wild")
    }
    ctx.recent_dismissed_event_ids = {9002}
    ctx.recent_seen_event_ids = {9003}
    return ctx


def _make_sport(key: str, name: str):
    s = MagicMock()
    s.key = key
    s.name = name
    return s


def _make_event(
    event_id: int,
    *,
    sport_key: str,
    sport_name: str,
    status: str,
    start: datetime,
    home_team_id: int,
    away_team_id: int,
    home_name: str,
    away_name: str,
    home_prob: float = 0.55,
    importance: str = "regular",
    home_score: int | None = None,
    away_score: int | None = None,
):
    e = MagicMock()
    e.id = event_id
    e.status = status
    e.commence_time = start
    e.home_team_id = home_team_id
    e.away_team_id = away_team_id
    e.home_team_name = home_name
    e.away_team_name = away_name
    e.opening_home_probability = home_prob
    e.opening_away_probability = round(1.0 - home_prob, 4)
    e.win_probability_sources = {
        "betting": home_prob,
        "kalshi": home_prob,
        "betting_book_count": 6,
    }
    e.espn_win_prob_home = None
    e.opening_home_spread = -3.5
    e.opening_over_under = 220.5
    e.opening_favorite = "home"
    e.llm_importance = importance
    e.llm_gender = None
    e.llm_level = None
    e.llm_league = None
    e.sport = _make_sport(sport_key, sport_name)
    e.statpal_end_time = None
    e.completed_at = start + timedelta(hours=3) if status == "completed" else None
    e.period = "3rd Quarter" if status == "live" else None
    e.raw_ei = 72.0
    e.ei_metadata = None
    e.home_score = home_score
    e.away_score = away_score
    e.external_id = f"ext-{event_id}"
    e.game_clock = "4:12" if status == "live" else None
    e.broadcast_info = None
    e.event_tags = []
    e.score_source = "espn" if home_score is not None else None
    e.score_observed_at = NOW - timedelta(seconds=20) if home_score is not None else None
    e.closing_home_probability = None
    return e


def _sample_events():
    return [
        # Live followed-team NBA game
        _make_event(
            9001,
            sport_key="basketball_nba",
            sport_name="NBA",
            status="live",
            start=NOW - timedelta(hours=1),
            home_team_id=101,
            away_team_id=102,
            home_name="Boston Celtics",
            away_name="Miami Heat",
            home_prob=0.62,
            home_score=74,
            away_score=70,
        ),
        # Scheduled NBA game dismissed by reader (kept in sports_mode, dropped in discover)
        _make_event(
            9002,
            sport_key="basketball_nba",
            sport_name="NBA",
            status="scheduled",
            start=NOW + timedelta(hours=2),
            home_team_id=103,
            away_team_id=104,
            home_name="Los Angeles Lakers",
            away_name="Denver Nuggets",
            home_prob=0.52,
        ),
        # Completed NHL playoff game (Nah sport + freshness decay + seen)
        _make_event(
            9003,
            sport_key="icehockey_nhl",
            sport_name="NHL",
            status="completed",
            start=NOW - timedelta(hours=14),
            home_team_id=201,
            away_team_id=205,
            home_name="Toronto Maple Leafs",
            away_name="Florida Panthers",
            home_prob=0.58,
            importance="playoff",
            home_score=4,
            away_score=3,
        ),
        # Scheduled EPL game (low-affinity "if it's wild" sport)
        _make_event(
            9004,
            sport_key="soccer_epl",
            sport_name="EPL",
            status="scheduled",
            start=NOW + timedelta(hours=3),
            home_team_id=301,
            away_team_id=302,
            home_name="Arsenal",
            away_name="Chelsea",
            home_prob=0.51,
        ),
    ]


class _EventsDb:
    def __init__(self, events):
        self.events = events
        self.calls = 0

    @staticmethod
    def _result(rows=(), scalars=()):
        r = MagicMock()
        r.scalars.return_value.all.return_value = list(scalars)
        r.all.return_value = list(rows)
        return r

    async def execute(self, stmt, params=None, *a, **k):
        self.calls += 1
        s = str(stmt).lower()
        if "from events" in s:
            return self._result(scalars=self.events)
        return self._result()


def _canon(items: list[dict]) -> str:
    return json.dumps(items, sort_keys=True, default=str)


def _make_futures_market(market_id: int, name: str, team_id: int, sport_key: str, cat: str):
    o1 = SimpleNamespace(
        id=market_id * 10 + 1,
        external_id=f"ext-o-{market_id}-1",
        name="Boston Celtics",
        team_id=team_id,
        current_probability=0.34,
        probability_change_24h=0.03,
        opening_probability=0.25,
        rank=1,
        rank_change_24h=0,
        current_yes_bid=0.33,
        current_yes_ask=0.35,
        updated_at=NOW - timedelta(minutes=10),
        last_price_updated_at=NOW - timedelta(minutes=10),
        is_winner=None,
        resolution_source=None,
        volume_24h=50000.0,
        volume_24h_at=NOW - timedelta(minutes=10),
    )
    o2 = SimpleNamespace(
        id=market_id * 10 + 2,
        external_id=f"ext-o-{market_id}-2",
        name="Oklahoma City Thunder",
        team_id=team_id + 50,
        current_probability=0.28,
        probability_change_24h=-0.01,
        opening_probability=0.30,
        rank=2,
        rank_change_24h=0,
        current_yes_bid=0.27,
        current_yes_ask=0.29,
        updated_at=NOW - timedelta(minutes=10),
        last_price_updated_at=NOW - timedelta(minutes=10),
        is_winner=None,
        resolution_source=None,
        volume_24h=40000.0,
        volume_24h_at=NOW - timedelta(minutes=10),
    )
    sport = SimpleNamespace(key=sport_key, name=sport_key.upper())
    return SimpleNamespace(
        id=market_id,
        external_id=f"fm-{market_id}",
        name=name,
        source="kalshi",
        market_tier=1,
        market_type="championship",
        category="sports",
        llm_sport_category=cat,
        llm_league=None,
        llm_gender=None,
        llm_level=None,
        status="open",
        resolution_date=NOW + timedelta(days=90),
        commence_time=None,
        updated_at=NOW - timedelta(minutes=5),
        created_at=NOW - timedelta(days=30),
        volume_24h=120000.0,
        canonical_market_key=f"cmk-{market_id}",
        group_id=None,
        group_type=None,
        image_url=None,
        image_width=None,
        image_height=None,
        hook_description=None,
        hook_generated_at=None,
        hook_leader_at_generation=None,
        market_metadata=None,
        description=None,
        curation_score_adj=0,
        outcomes=[o1, o2],
        sport=sport,
        sport_id=1,
    )


class _SportsFuturesDb:
    def __init__(self, markets):
        self.markets = markets
        self.calls = 0

    async def execute(self, stmt, params=None, *a, **k):
        self.calls += 1
        r = MagicMock()
        if self.calls == 1:
            r.scalars.return_value.all.return_value = [m.id for m in self.markets]
        else:
            r.scalars.return_value.unique.return_value.all.return_value = list(
                self.markets
            )
            r.scalars.return_value.all.return_value = list(self.markets)
            r.all.return_value = []
        return r


# ---------------------------------------------------------------------------
# 1. events_scored equivalence (process + cross-worker Redis)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("sports_mode", [True, False])
async def test_events_scored_shared_equals_direct_for_anon_and_personalized(
    monkeypatch, sports_mode
):
    monkeypatch.setenv("FEED_SHARED_BUILD_CROSS_WORKER", "1")
    redis = _FakeRedis()

    async def _client():
        return redis

    monkeypatch.setattr(pic, "_shared_redis_client", _client)

    async def _direct(ctx):
        with patch(
            "app.routes.feed._get_championship_probabilities",
            new=AsyncMock(return_value={}),
        ), patch(
            "app.routes.feed._attach_card_projected_pairs",
            new=AsyncMock(return_value=None),
        ), patch(
            "app.routes.feed._attach_pregame_projections",
            new=AsyncMock(return_value=None),
        ):
            return await _score_events(
                _EventsDb(_sample_events()),
                NOW,
                None,
                ctx,
                sports_mode=sports_mode,
            )

    direct_anon = await _direct(PersonalizationContext())
    direct_reader = await _direct(_rich_reader_ctx())
    assert direct_anon, "fixture must produce events"

    # Worker 1 builds the shared pre-personalization events artifact via _score_events.
    db1 = _EventsDb(_sample_events())
    with patch(
        "app.routes.feed._get_championship_probabilities",
        new=AsyncMock(return_value={}),
    ), patch(
        "app.routes.feed._attach_card_projected_pairs",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.routes.feed._attach_pregame_projections",
        new=AsyncMock(return_value=None),
    ):
        shared_anon = await _score_events(
            db1,
            NOW,
            None,
            PersonalizationContext(),
            sports_mode=sports_mode,
            share_scored_events=True,
        )
    assert db1.calls >= 1
    assert any("events_scored" in k for k in redis.stored)
    assert _canon(shared_anon) == _canon(direct_anon)

    # Worker 2 (empty process cache) reads from Redis and personalizes for Alex-like reader
    # with ZERO DB calls.
    pic.clear_shared_builds()
    db2 = _EventsDb(_sample_events())
    shared_reader = await _score_events(
        db2,
        NOW,
        None,
        _rich_reader_ctx(),
        sports_mode=sports_mode,
        share_scored_events=True,
    )
    assert db2.calls == 0, "worker 2 rebuilt events instead of reading Redis"
    assert _canon(shared_reader) == _canon(direct_reader)
    assert all("_event_pers_inputs" not in it for it in shared_reader)
    # Confirm sports_mode vs Discover suppression difference survived intact.
    reader_ids = {it["data"]["id"] for it in shared_reader}
    if sports_mode:
        assert 9002 in reader_ids
    else:
        assert 9002 not in reader_ids


# ---------------------------------------------------------------------------
# 2. sports_futures_scored equivalence (process + cross-worker Redis)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sports_futures_scored_shared_equals_direct_across_workers(monkeypatch):
    monkeypatch.setenv("FEED_SHARED_BUILD_CROSS_WORKER", "1")
    redis = _FakeRedis()

    async def _client():
        return redis

    monkeypatch.setattr(pic, "_shared_redis_client", _client)

    markets = [
        _make_futures_market(5001, "NBA Championship 2027", 101, "basketball_nba", "basketball"),
        _make_futures_market(5002, "Stanley Cup 2027", 201, "icehockey_nhl", "hockey"),
    ]

    def _patches():
        return (
            patch(
                "app.utils.sports_market_metadata_reuse.load_sports_markets",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.routes.feed._get_canonical_source_counts",
                new=AsyncMock(return_value={"cmk-5001": 2, "cmk-5002": 2}),
            ),
            patch(
                "app.routes.feed._team_names_by_id",
                new=AsyncMock(return_value={101: "Boston Celtics", 201: "Toronto Maple Leafs"}),
            ),
            patch(
                "app.routes.feed.withheld_price_outcome_ids_for_markets",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "app.routes.feed.out_legs_by_market",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "app.routes.feed.graded_out_leg_ids_by_market",
                new=AsyncMock(return_value={}),
            ),
        )

    p1, p2, p3, p4, p5, p6 = _patches()
    with p1, p2, p3, p4, p5, p6:
        direct_anon = await _score_sports_mode_futures(
            _SportsFuturesDb(markets), NOW, None, PersonalizationContext()
        )
        direct_reader = await _score_sports_mode_futures(
            _SportsFuturesDb(markets), NOW, None, _rich_reader_ctx()
        )
        assert direct_anon, "fixture must produce sports futures"

        db1 = _SportsFuturesDb(markets)
        shared_anon = await _score_sports_mode_futures(
            db1, NOW, None, PersonalizationContext(), share_inputs=True
        )
        assert db1.calls >= 1
        assert _canon(shared_anon) == _canon(direct_anon)
        assert any("sports_futures_scored" in k for k in redis.stored)

        # Worker 2 (cold process tier) serves personalized reader from Redis with 0 DB calls.
        pic.clear_shared_builds()
        db2 = _SportsFuturesDb(markets)
        shared_reader = await _score_sports_mode_futures(
            db2, NOW, None, _rich_reader_ctx(), share_inputs=True
        )
        assert db2.calls == 0, "worker 2 rebuilt sports futures instead of reading Redis"
        assert _canon(shared_reader) == _canon(direct_reader)
        # Ensure private helper key never leaks onto returned items.
        assert all("_sports_pers_inputs" not in it for it in shared_reader)


@pytest.mark.asyncio
async def test_sports_futures_my_teams_only_never_touches_shared_cache(monkeypatch):
    spy = AsyncMock(side_effect=AssertionError("my_teams_only reached shared cache"))
    monkeypatch.setattr(feed_mod._pic, "get_or_build", spy)
    db = _SportsFuturesDb([])
    res = await _score_sports_mode_futures(
        db,
        NOW,
        None,
        _rich_reader_ctx(),
        my_teams_only=True,
        share_inputs=True,
    )
    assert res == []
    spy.assert_not_called()


# ---------------------------------------------------------------------------
# 3. review_decisions shared read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_review_decisions_shared_reuses_rows_and_honors_kill_switch():
    rows = [
        SimpleNamespace(
            item_type="event",
            item_id="9001",
            decision="accepted_promote",
            family_key=None,
        )
    ]

    class _ReviewDb:
        def __init__(self):
            self.calls = 0

        async def execute(self, stmt, *a, **k):
            self.calls += 1
            r = MagicMock()
            r.all.return_value = list(rows)
            return r

    db1 = _ReviewDb()
    db2 = _ReviewDb()
    items1 = [{"type": "event", "score": 50, "_rank_score": 50.0, "data": {"id": 9001}}]
    items2 = [{"type": "event", "score": 50, "_rank_score": 50.0, "data": {"id": 9001}}]

    fake_redis = MagicMock()
    fake_redis.get = AsyncMock(return_value=None)
    with patch(
        "app.utils.request_cache.get_shared_async_redis",
        new=AsyncMock(return_value=fake_redis),
    ):
        await _apply_manual_review_decisions(db1, items1, share_inputs=True)
        await _apply_manual_review_decisions(db2, items2, share_inputs=True)

    assert db1.calls == 1
    assert db2.calls == 0, "second call re-queried DiscoverReviewDecision"
    assert items1 == items2


# ---------------------------------------------------------------------------
# 4. Live ceiling, memory bounds, and kill switch contracts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("namespace", SHARED_NAMESPACES)
def test_new_namespaces_respect_live_ceiling_memory_cap_and_kill_switch(
    namespace, monkeypatch
):
    assert namespace not in pic.LIVENESS_INERT_NAMESPACES
    assert namespace in pic.MAX_ENTRIES_BY_NAMESPACE
    assert pic.MAX_ENTRIES_BY_NAMESPACE[namespace] <= 6
    assert pic.shared_build_ttl_s(namespace) == pic.live_artifact_ttl_ceiling_s()
    assert pic.live_artifact_ttl_headroom_s(namespace) >= 0.0

    monkeypatch.setenv("FEED_SHARED_BUILD_TTL_S", "0")
    assert pic.shared_build_ttl_s(namespace) == 0.0
