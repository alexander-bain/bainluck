"""Ship: read live probabilities without transferring irrelevant market metadata."""
import json

import pytest
from sqlalchemy import update

from app.models.models import FuturesMarket
from app.tasks.live_blend_refresh import LiveBlendRefresher, PREPARED_MARKET_FIELDS
from app.utils.content_understanding import CONTENT_UNDERSTANDING_KEY as KEY, semantic_type_for_market
from app.utils.live_blend import compute_source_home_probability
from tests.integration.test_live_blend_grouped_commit_8129_pg import DB_URL, rig, seed

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(not DB_URL, reason="disposable PostgreSQL required")]


class FullMetadata:
    """Execute the parent projection against the same rows and transaction."""
    def __init__(self, session):
        self.session = session

    async def execute(self, statement):
        columns = list(statement.selected_columns)
        columns[PREPARED_MARKET_FIELDS.index("market_metadata")] = FuturesMarket.market_metadata
        return await self.session.execute(statement.with_only_columns(*columns, maintain_column_froms=True))


def reading(group):
    result = compute_source_home_probability(group, "Chicago Cubs", "Miami Marlins")
    if result is None:
        return None
    # Compare every reading field, including full eligibility and source
    # identities. The metadata representation is intentionally projected and
    # checked separately below; it is not itself a probability result.
    return vars(result) | {"market": {
        k: v for k, v in vars(result.market).items() if k != "market_metadata"
    }}


@pytest.mark.parametrize("source", ["polymarket", "kalshi"])
async def test_projected_metadata_preserves_readings_and_refusals_in_real_postgres(rig, source):
    await seed(rig, count=2)
    async with rig.engine.begin() as conn:
        for mid in (1, 2):
            await conn.execute(update(FuturesMarket).where(FuturesMarket.id == mid).values(
                event_id=1, source=source,
                external_id=f"KXMLBGAME-26OCT23MIACHC-CHC{mid}" if source == "kalshi" else f"game-{mid}",
            ))
    r = LiveBlendRefresher(source)
    r.preview_events = frozenset()
    shapes = [None, {}, [], "bad root", {KEY: None}, {KEY: []}]
    for version in (1, 0, 2, "1", True, 1.0):
        for venue in ("moneyline", "tennis_completed_match"):
            shapes.append({KEY: {"v": version, "semantic_type": "moneyline",
                                 "venue_type": venue, "agreement": "contradicted"}})
    shapes.append({KEY: {"v": 1, "semantic_type": "moneyline", "venue_type": "moneyline"},
                   "unrelated_history": "x" * 262144})
    for metadata in shapes:
        async with rig.engine.begin() as conn:
            await conn.execute(update(FuturesMarket).where(FuturesMarket.id == 1).values(market_metadata=metadata))
        async with rig.maker() as session:
            baseline = await r._read_groups(FullMetadata(session), [1])
            projected = await r._read_groups(session, [1])
        before, after = baseline[1][1], projected[1][1]
        assert reading(before) == reading(after)
        assert [(g.market.id, [o.id for o in g.outcomes], semantic_type_for_market(g.market)) for g in before] == [(g.market.id, [o.id for o in g.outcomes], semantic_type_for_market(g.market)) for g in after]
        original = next(g.market for g in before if g.market.id == 1)
        narrowed = next(g.market for g in after if g.market.id == 1)
        assert narrowed.market_metadata == {KEY: metadata.get(KEY) if isinstance(metadata, dict) else None}
        if isinstance(metadata, dict) and "unrelated_history" in metadata:
            assert len(json.dumps(narrowed.market_metadata)) < len(json.dumps(original.market_metadata)) / 1000
    # Settlement must remain a refusal rather than being revived by projection.
    async with rig.engine.begin() as conn:
        await conn.execute(update(FuturesMarket).values(status="closed"))
    async with rig.maker() as session:
        before = (await r._read_groups(FullMetadata(session), [1]))[1][1]
        after = (await r._read_groups(session, [1]))[1][1]
    assert reading(before) == reading(after)
