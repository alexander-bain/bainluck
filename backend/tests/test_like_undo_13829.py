"""Tests for #13829: neutral ``like_undo`` interaction accounting on Discover."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request

from app.routes.admin_engagement import discover_engagement_summary
from app.routes.feed import (
    _DISCOVER_ACTIONS,
    _DISCOVER_NEGATIVE_ACTIONS,
    DiscoverInteractionBatch,
    DiscoverInteractionIn,
    _build_discover_category_affinities,
    _build_discover_category_negative_counts,
    _build_discover_feature_affinities,
    _load_personalization_context,
    _net_active_like_interactions,
    _should_skip_futures_for_recent_dismissal,
    record_discover_interactions,
)

_READER = SimpleNamespace(id=13829)


def _dummy_request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/feed/interactions",
        "headers": headers or [],
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


def _ev(
    action: str,
    item_id: str = "101",
    *,
    item_type: str = "futures",
    category: str = "politics",
    item_name: str | None = "Who wins Senate control?",
    created_at: datetime | None = None,
    row_id: int = 1,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=row_id,
        item_type=item_type,
        item_id=item_id,
        category=category,
        item_name=item_name,
        action=action,
        created_at=created_at or datetime.now(timezone.utc),
    )


def _event_store_session(events: list[SimpleNamespace]):
    """Stateful session answering the personalization queries over ``events``."""
    executed_sql: list[str] = []

    def _result(rows):
        res = MagicMock()
        res.all.return_value = rows
        res.fetchall.return_value = rows
        res.scalars.return_value.all.return_value = rows
        res.scalar_one_or_none.return_value = None
        return res

    async def mock_execute(stmt, *args, **kwargs):
        sql = str(stmt).lower()
        executed_sql.append(sql)
        if "discover_interactions" not in sql:
            return _result([])

        # Chronological like / like_undo replay query
        if "order by" in sql and "group by" not in sql:
            ordered = sorted(
                (e for e in events if e.action in ("like", "like_undo")),
                key=lambda e: (e.created_at, e.id),
            )
            return _result(
                [
                    (e.item_type, e.item_id, e.category, e.item_name, e.action)
                    for e in ordered
                ]
            )

        # Recent-items suppression query (`impression`, `dismiss`, `unlike`)
        if "max(" in sql:
            grouped: dict[tuple[str, str, str], list[SimpleNamespace]] = defaultdict(list)
            for e in events:
                if e.action in ("impression", "dismiss", "unlike") and e.item_type in (
                    "event",
                    "futures",
                    "grid",
                    "tournament",
                    "concept",
                    "bundle",
                ):
                    grouped[(e.item_type, str(e.item_id), e.action)].append(e)
            rows = []
            for (itype, iid, act), items in grouped.items():
                latest = max(items, key=lambda x: x.created_at)
                rows.append(
                    (
                        itype,
                        iid,
                        act,
                        latest.created_at,
                        max((x.item_name for x in items if x.item_name), default=None),
                        max((x.category for x in items if x.category), default=None),
                    )
                )
            rows.sort(key=lambda r: r[3], reverse=True)
            return _result(rows)

        # Feature rollup query
        if "item_name" in sql:
            allowed = {
                "detail_click",
                "open",
                "share",
                "like",
                "unlike",
                "dismiss",
                "group_expand",
                "context_expand",
            }
            counts: dict[tuple[str, str, str, str], int] = defaultdict(int)
            for e in events:
                if e.item_name is not None and e.category is not None and e.action in allowed:
                    counts[(e.item_type, e.item_name, e.category, e.action)] += 1
            return _result([(k[0], k[1], k[2], k[3], n) for k, n in counts.items()])

        # Category rollup query
        cat_counts: dict[tuple[str, str], int] = defaultdict(int)
        for e in events:
            if e.category is not None:
                cat_counts[(e.category, e.action)] += 1
        return _result([(k[0], k[1], n) for k, n in cat_counts.items()])

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=mock_execute)
    session.rollback = AsyncMock()
    session.executed_sql = executed_sql
    return session


def test_like_undo_in_allowed_actions_only():
    assert "like_undo" in _DISCOVER_ACTIONS
    assert "like_undo" not in _DISCOVER_NEGATIVE_ACTIONS
    assert "unlike" in _DISCOVER_NEGATIVE_ACTIONS
    assert "dismiss" in _DISCOVER_NEGATIVE_ACTIONS


@pytest.mark.asyncio
async def test_record_discover_interactions_preserves_like_undo_verbatim(monkeypatch):
    monkeypatch.setattr("app.routes.feed.ranking_snapshots_enabled", lambda: False)
    captured = []

    class _RecordingSession:
        def add_all(self, rows):
            captured.extend(rows)

        async def commit(self):
            return None

    batch = DiscoverInteractionBatch(
        interactions=[
            DiscoverInteractionIn(
                action="like_undo",
                item_type="futures",
                item_id="555",
                category="economics",
                item_name="Fed cut in June?",
                surface="ios",
            ),
            DiscoverInteractionIn(
                action="unlike",
                item_type="futures",
                item_id="556",
                category="economics",
                item_name="CPI above 3%?",
                surface="web",
            ),
        ]
    )
    resp = await record_discover_interactions(
        request=_dummy_request([(b"x-session-id", b"sess-13829")]),
        body=batch,
        user=_READER,
        db=_RecordingSession(),
    )
    assert resp == {"status": "ok", "recorded": 2}
    assert [row.action for row in captured] == ["like_undo", "unlike"]
    assert captured[0].item_id == "555"


def test_net_active_like_interactions_sequences():
    # like -> like_undo nets 0
    cat_0, feat_0 = _net_active_like_interactions(
        [
            ("futures", "101", "politics", "Senate control", "like"),
            ("futures", "101", "politics", "Senate control", "like_undo"),
        ]
    )
    assert cat_0 == {}
    assert feat_0 == {}

    # like -> like_undo -> like nets 1
    cat_1, feat_1 = _net_active_like_interactions(
        [
            ("futures", "101", "politics", "Senate control", "like"),
            ("futures", "101", "politics", "Senate control", "like_undo"),
            ("futures", "101", "politics", "Senate control", "like"),
        ]
    )
    assert cat_1 == {"politics": 1}
    assert feat_1 == {("futures", "Senate control", "politics"): 1}

    # Unmatched like_undo alone never produces negatives; subsequent like nets 1
    cat_alone, feat_alone = _net_active_like_interactions(
        [("futures", "102", "culture", "Oscars Best Picture", "like_undo")]
    )
    assert cat_alone == {}
    assert feat_alone == {}

    cat_after, feat_after = _net_active_like_interactions(
        [
            ("futures", "102", "culture", "Oscars Best Picture", "like_undo"),
            ("futures", "102", "culture", "Oscars Best Picture", "like"),
        ]
    )
    assert cat_after == {"culture": 1}
    assert feat_after == {("futures", "Oscars Best Picture", "culture"): 1}

    # Cross-card independence: undoing card 101 leaves card 202 active
    cat_cross, feat_cross = _net_active_like_interactions(
        [
            ("futures", "101", "politics", "Senate control", "like"),
            ("futures", "202", "politics", "House control", "like"),
            ("futures", "101", "politics", "Senate control", "like_undo"),
        ]
    )
    assert cat_cross == {"politics": 1}
    assert feat_cross == {("futures", "House control", "politics"): 1}


@pytest.mark.asyncio
async def test_like_then_undo_nets_zero_without_hiding_or_penalizing():
    t0 = datetime.now(timezone.utc) - timedelta(hours=2)
    base_events = [
        _ev(
            "impression",
            item_id=str(i),
            category="politics",
            item_name=f"Policy question {i}",
            created_at=t0 - timedelta(minutes=1),
            row_id=i,
        )
        for i in range(1, 26)
    ]
    # Include baseline clicks so politics meets the 2-interaction rollup floor identically
    base_events.extend(
        [
            _ev("detail_click", item_id="901", category="politics", item_name="Primary 1", created_at=t0, row_id=101),
            _ev("detail_click", item_id="902", category="politics", item_name="Primary 2", created_at=t0, row_id=102),
        ]
    )
    with_like_and_undo = list(base_events) + [
        _ev(
            "like",
            item_id="5001",
            category="politics",
            item_name="Midterm Senate Control",
            created_at=t0 + timedelta(seconds=10),
            row_id=201,
        ),
        _ev(
            "like_undo",
            item_id="5001",
            category="politics",
            item_name="Midterm Senate Control",
            created_at=t0 + timedelta(seconds=20),
            row_id=202,
        ),
    ]

    baseline_sess = _event_store_session(base_events)
    baseline_ctx = await _load_personalization_context(baseline_sess, _READER, session_id="s-1")

    undo_sess = _event_store_session(with_like_and_undo)
    undo_ctx = await _load_personalization_context(undo_sess, _READER, session_id="s-1")

    assert undo_ctx.discover_category_affinities == baseline_ctx.discover_category_affinities
    assert undo_ctx.discover_category_negative_counts == {}
    assert undo_ctx.discover_feature_affinities == baseline_ctx.discover_feature_affinities
    assert 5001 not in undo_ctx.recent_dismissed_futures_ids
    assert undo_ctx.recent_dismissed_story_keys == set()
    assert undo_ctx.recent_dismissed_group_ids == set()
    assert undo_ctx.recent_dismissed_feature_token_sets == []

    # Card remains eligible even when grouped
    candidate_market = SimpleNamespace(group_id="grp-senate")
    assert (
        _should_skip_futures_for_recent_dismissal(
            market=candidate_market,
            quality=None,
            ctx=undo_ctx,
            my_teams_only=False,
        )
        is False
    )


@pytest.mark.asyncio
async def test_like_undo_like_nets_one_active_like():
    t0 = datetime.now(timezone.utc) - timedelta(hours=1)
    single_like_events = [
        _ev("impression", item_id=str(i), category="economy", item_name=f"Econ {i}", created_at=t0, row_id=i)
        for i in range(1, 25)
    ] + [
        _ev("detail_click", item_id="901", category="economy", item_name="GDP growth", created_at=t0, row_id=50),
        _ev("like", item_id="7001", category="economy", item_name="Fed rate cut", created_at=t0 + timedelta(seconds=10), row_id=51),
    ]

    like_undo_like_events = single_like_events + [
        _ev("like_undo", item_id="7001", category="economy", item_name="Fed rate cut", created_at=t0 + timedelta(seconds=20), row_id=52),
        _ev("like", item_id="7001", category="economy", item_name="Fed rate cut", created_at=t0 + timedelta(seconds=30), row_id=53),
    ]

    expected_ctx = await _load_personalization_context(_event_store_session(single_like_events), _READER)
    actual_ctx = await _load_personalization_context(_event_store_session(like_undo_like_events), _READER)

    assert actual_ctx.discover_category_affinities == expected_ctx.discover_category_affinities
    assert actual_ctx.discover_feature_affinities == expected_ctx.discover_feature_affinities
    assert actual_ctx.discover_category_negative_counts == {}
    assert 7001 not in actual_ctx.recent_dismissed_futures_ids


@pytest.mark.asyncio
async def test_cold_start_does_not_count_like_undo_as_interaction():
    # 10 interactions (< 20 cold start threshold) + 15 like_undos must stay < 20 and net 0
    rows = [("politics", "detail_click", 1), ("politics", "dismiss", 1), ("politics", "impression", 8)]
    rows_with_undo = rows + [("politics", "like_undo", 15)]
    assert _build_discover_category_affinities(rows_with_undo) == _build_discover_category_affinities(rows)
    assert _build_discover_category_negative_counts(rows_with_undo) == _build_discover_category_negative_counts(rows)
    assert _build_discover_feature_affinities(
        [("futures", "Election", "politics", "like_undo", 5)]
    ) == {}


@pytest.mark.asyncio
async def test_unlike_still_hides_and_penalizes_while_no_extra_query_without_like_undo():
    t0 = datetime.now(timezone.utc) - timedelta(hours=1)
    events_no_undo = [
        _ev("impression", item_id="1", category="politics", item_name="Card A", created_at=t0, row_id=1),
        _ev("unlike", item_id="8888", category="politics", item_name="Card B", created_at=t0 + timedelta(seconds=5), row_id=2),
        _ev("unlike", item_id="8889", category="politics", item_name="Card C", created_at=t0 + timedelta(seconds=6), row_id=3),
    ]
    sess = _event_store_session(events_no_undo)
    ctx = await _load_personalization_context(sess, _READER, session_id="s-unlike")

    assert 8888 in ctx.recent_dismissed_futures_ids
    assert ctx.discover_category_negative_counts.get("politics") == 2
    assert ctx.discover_category_affinities.get("politics", 0.0) < 0
    # Zero extra chronological queries when no like_undo rows are present
    di_queries = [q for q in sess.executed_sql if "discover_interactions" in q]
    assert len(di_queries) == 3


@pytest.mark.asyncio
async def test_admin_engagement_summary_ignores_like_undo(monkeypatch):
    monkeypatch.setattr("app.routes.admin_engagement._check_admin_secret", lambda *a, **k: None)

    async def _no_runtime_config():
        return {
            "interaction_suppression_enabled": True,
            "seen_suppression_hours": 48.0,
            "dismiss_suppression_days": 14.0,
            "stale_no_movement_days": 7.0,
            "no_resolution_stale_days": 14.0,
        }

    monkeypatch.setattr(
        "app.routes.admin_engagement._load_discover_runtime_config",
        _no_runtime_config,
    )

    summary_rows = [
        ("ios", "politics", "futures", "impression", 10),
        ("ios", "politics", "futures", "like", 2),
        ("ios", "politics", "futures", "like_undo", 5),
        ("ios", "politics", "futures", "dismiss", 1),
    ]
    score_rows = [
        (80, "impression", 10),
        (80, "open", 1),
        (80, "like_undo", 5),
    ]
    queries = []

    def _result(rows):
        r = MagicMock()
        r.all.return_value = rows
        r.scalars.return_value.all.return_value = []
        return r

    async def _mock_execute(stmt, *args, **kwargs):
        sql = str(stmt).lower()
        params = str(stmt.compile().params).lower() if hasattr(stmt, "compile") else ""
        queries.append((sql, params))
        if "discover_interactions.surface, discover_interactions.category" in sql and "group by discover_interactions.surface" in sql:
            return _result(summary_rows)
        if "group by discover_interactions.score, discover_interactions.action" in sql:
            return _result(score_rows)
        return _result([])

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_mock_execute)

    payload = await discover_engagement_summary(
        request=_dummy_request(),
        secret="ignored",
        days=7,
        db=db,
    )
    assert len(payload["groups"]) == 1
    row = payload["groups"][0]
    assert row["impressions"] == 10
    assert row["likes"] == 2
    assert row["dismisses"] == 1
    # like (2) + dismiss (1) = 3; like_undo (5) adds 0 to actions
    assert row["actions"] == 3

    assert len(payload["score_buckets"]) == 1
    bucket = payload["score_buckets"][0]
    assert bucket["impressions"] == 10
    assert bucket["opens"] == 1
    # only open (1); like_undo (5) adds 0 to score bucket actions
    assert bucket["actions"] == 1
    assert any("limit" in sql and "like_undo" in params for sql, params in queries)
