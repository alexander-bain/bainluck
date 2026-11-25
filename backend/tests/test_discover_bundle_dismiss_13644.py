"""#13644 — Grouped-card `'not for me'` dismissal persists & feeds the Fun Scout (385: A)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.feed import _filter_dismissed_bundle_items
from app.utils.discover_fun_scout import (
    ScoutMarketRow,
    ScoutTaggedMarket,
    ScoutUncoveredFamily,
    load_reader_dismissed_sets,
    run_scout_set_writing_pass,
)
from app.utils.discover_fun_tags import FunMarketEntry
from app.utils.personalization import PersonalizationContext
from app.utils.roundup_containers import _roundup_card_candidate_keys

FROZEN_NOW = datetime(2025, 6, 15, 12, 0, tzinfo=timezone.utc)


def _bundle_card(
    bundle_id: str = "roundup:machinery-next-james-bond",
    slug: str = "machinery-next-james-bond",
    story_key: str = "bond-story",
) -> dict:
    return {
        "type": "bundle",
        "score": 88,
        "data": {
            "id": bundle_id,
            "story_key": story_key,
            "collection_ref": {"slug": slug, "name": "Next James Bond"},
            "roundup": {"machinery_card": {"slug": slug}},
            "items": [],
        },
    }


def test_roundup_candidate_keys_include_slug_and_bundle_id():
    keys = _roundup_card_candidate_keys(_bundle_card())
    assert "machinery-next-james-bond" in keys
    assert "roundup:machinery-next-james-bond" in keys
    assert "bundle-roundup:machinery-next-james-bond" in keys
    assert "bond-story" in keys


def test_filter_dismissed_bundle_items_drops_dismissed_set_and_keeps_others():
    bond = _bundle_card()
    chess = _bundle_card(
        bundle_id="roundup:machinery-chess-milestones-and-curiosities",
        slug="machinery-chess-milestones-and-curiosities",
        story_key="chess-story",
    )
    ctx = PersonalizationContext(recent_dismissed_keys={"machinery-next-james-bond"})
    kept = _filter_dismissed_bundle_items([bond, chess], ctx)
    assert kept == [chess]
    # my_teams_only never filters via recent_dismissed_keys
    assert _filter_dismissed_bundle_items([bond, chess], ctx, my_teams_only=True) == [bond, chess]


@pytest.mark.asyncio
async def test_load_user_context_captures_numeric_and_slug_bundle_dismissals():
    from app.routes.feed import _load_personalization_context

    rows = [
        ("bundle", "machinery-next-james-bond", "dismiss", FROZEN_NOW - timedelta(minutes=5), "Next Bond", "culture"),
        ("bundle", "424242", "dismiss", FROZEN_NOW - timedelta(minutes=5), "Numeric Bundle", "culture"),
    ]

    async def mock_execute(stmt, *args, **kwargs):
        res = MagicMock()
        rendered = str(stmt).lower()
        if "discover_interactions" in rendered and "max(" in rendered:
            res.all.return_value = rows
        else:
            res.all.return_value = []
        res.fetchall.return_value = res.all.return_value
        res.scalars.return_value.all.return_value = []
        res.scalars.return_value.first.return_value = None
        res.scalar_one_or_none.return_value = None
        return res

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=mock_execute)
    ctx = await _load_personalization_context(
        session, None, session_id="bundle-dismiss-13644", config=None
    )
    assert "machinery-next-james-bond" in ctx.recent_dismissed_keys
    assert "424242" in ctx.recent_dismissed_keys


@pytest.mark.asyncio
async def test_load_reader_dismissed_sets_reads_user_bundle_dismissals_for_scout():
    seen_sql: list[str] = []

    async def mock_execute(stmt, *args, **kwargs):
        try:
            seen_sql.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))
        except Exception:
            seen_sql.append(str(stmt))
        res = MagicMock()
        res.all.return_value = [
            ("machinery-next-james-bond", 4),
            ("bond-story", 2),
        ]
        return res

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=mock_execute)
    counts = await load_reader_dismissed_sets(db, lookback_days=30, now=FROZEN_NOW)
    assert counts == {"machinery-next-james-bond": 4, "bond-story": 2}
    assert seen_sql
    sql = seen_sql[0].lower()
    assert "discover_interactions" in sql
    assert "bundle" in sql
    assert "user" in sql


def test_run_scout_set_writing_pass_includes_reader_dismissed_sets_in_prompt():
    captured_prompts: list[str] = []

    class _FakeResp:
        content = '{"sets": []}'
        stop_reason = "end_turn"

    class _FakeMessages:
        def create(self, **kwargs):
            for msg in kwargs.get("messages") or []:
                if msg.get("role") == "user":
                    captured_prompts.append(str(msg.get("content") or ""))
            return _FakeResp()

    class _FakeAnthropic:
        messages = _FakeMessages()

    row = ScoutMarketRow(
        market_id=101,
        source="kalshi",
        title="Will GTA VI launch in 2025?",
        status="open",
        category="entertainment",
        resolution_date=FROZEN_NOW + timedelta(days=90),
        volume=50000.0,
        volume_24h=1000.0,
    )
    tagged = [ScoutTaggedMarket(market_id=101, fun_group="long-awaited", reason="delayed release")]
    examples = [
        FunMarketEntry(
            market_id=1,
            title="Half-Life 3 announced?",
            fun_bucket="long-awaited",
            sub_tags=("long-awaited",),
            discover_category="entertainment",
        )
    ]
    proposals, _model, _cost = run_scout_set_writing_pass(
        tagged,
        {101: row},
        [ScoutUncoveredFamily(family_key="fam-1", sample_title="Test Family", open_count=4)],
        anthropic_client=_FakeAnthropic(),
        approved_examples=examples,
        reader_dismissed_sets={"machinery-next-james-bond": 5},
        now=FROZEN_NOW,
    )
    assert proposals == []
    assert captured_prompts
    assert "Reader dismissed sets ('not for me'): {\"machinery-next-james-bond\": 5}" in captured_prompts[0]
