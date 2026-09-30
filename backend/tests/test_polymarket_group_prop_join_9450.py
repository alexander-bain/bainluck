"""#9450 — a Polymarket match market joins the row its own O/U line created.

## What a reader saw, on production (2026-09-28 ~19:40Z)

`/api/events/15320522` (Harris v Galarneau, Jingshan, Sep 30) served
`home_probability: null` with no sources, though Polymarket prices the match.
Its group `polymarket:1092876` holds four children: the O/U line sits on the
row, and the match market "Jingshan: Lloyd Harris vs Alexis Galarneau" has
`event_id` NULL. Its receipt: `pass2_general · rejected · not_game_level`, 33
attempts. 28 upcoming tennis matches were in this state, and every one of them
served no Polymarket source.

## Why

The match market, set winners, spreads and handicaps are classified
`game_prop`, so Pass 2 refuses them before any search. Only the MATCHED branch
of `_try_link_market` sweeps a group onto its event. The auto-create branch
moves only the child that arrived, so an O/U line that created the row left the
match market behind.

## What this file gates

* a not-game-level child whose group already holds a row is LINKED there,
  committed before its receipt claims it, and queued for history backfill;
* no row means the refusal is exactly what it was;
* a market that is not a Polymarket game child never reaches the database on
  this path (`session=None` is the assertion);
* the real classifier refuses the real production names, so the join sits on
  the path those markets actually take.

The resolver's SQL half runs on real PostgreSQL in
`tests/integration/test_polymarket_group_sibling_8430_pg.py`, and the whole
attempt in `tests/integration/test_polymarket_group_prop_join_9450_pg.py`.
"""

from datetime import datetime, timezone

import pytest

from app.tasks import prediction_market_matching as pmm
from app.utils import match_receipts as _receipts
from app.utils.prediction_market_matching import is_game_level_market

GROUP = "polymarket:1092876"
ROW = 15320522
NOW = datetime(2026, 9, 28, 19, 40, tzinfo=timezone.utc)
MATCH_MARKET = "Jingshan: Lloyd Harris vs Alexis Galarneau"


class _Market:
    def __init__(
        self, *, id=62900001, name=MATCH_MARKET, source="polymarket",
        group_type="polymarket_sub_market", group_id=GROUP,
    ):
        self.id = id
        self.name = name
        self.source = source
        self.category = "game_prop"
        self.group_id = group_id
        self.group_type = group_type
        self.external_id = f"0x9450{id}"
        self.event_id = None
        self.sport_id = None
        self.llm_sport_category = "tennis"
        self.market_metadata = {}


class _Session:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


def _stats():
    return {
        "markets_scanned": 0,
        "newly_linked": 0,
        "funnel": {
            "not_game_level": 0,
            "sample_not_game_level": [],
            "linked": 0,
        },
    }


async def _attempt(session, market):
    stats, queue, receipts = _stats(), [], []
    await pmm._attempt_market(
        session, market, stats, NOW, queue, lambda: 600.0,
        receipts, _receipts.PHASE_PASS2_GENERAL,
    )
    return stats, queue, receipts[0]


class TestTheRealNamesTakeTheNotGameLevelPath:
    @pytest.mark.parametrize(
        "name",
        [
            MATCH_MARKET,
            "Set 1 Winner: Lloyd Harris vs Alexis Galarneau",
            "Set Handicap: Cezar Cretu (-1.5) vs Henrique Rocha (+1.5)",
            "Game Spread: Remy Bertola (-3.5) vs Alexandre Reco (+3.5)",
        ],
    )
    def test_the_production_children_are_refused_as_not_game_level(self, name):
        assert not is_game_level_market(name, "game_prop", external_id="0x9450")

    def test_the_o_u_line_that_created_the_row_is_game_level(self):
        """The asymmetry: the O/U line creates the row, the match market can't."""
        assert is_game_level_market(
            "Harris vs. Galarneau: Match O/U 22.5", "game_prop",
            external_id="0x9450",
        )


class TestAChildWhoseGroupHoldsARowJoinsIt:
    @pytest.mark.asyncio
    async def test_the_match_market_is_linked_to_its_groups_row(self, monkeypatch):
        seen = []

        async def _resolver(session, market):
            seen.append(market.group_id)
            return ROW

        monkeypatch.setattr(pmm, "_polymarket_group_sibling_event_id", _resolver)
        session, market = _Session(), _Market()

        stats, queue, receipt = await _attempt(session, market)

        assert seen == [GROUP]
        assert market.event_id == ROW, "the match market stayed unlinked"
        assert session.commits == 1, "the link was not made durable"
        assert receipt.outcome == _receipts.OUTCOME_LINKED
        assert receipt.linked_event_id == ROW
        assert receipt.detail.get("how") == "group_sibling_link"
        assert queue == [(62900001, ROW)], "no history backfill for the chart"
        assert stats["newly_linked"] == 1
        assert stats["funnel"]["linked"] == 1
        assert stats["funnel"]["group_prop_joins"] == 1
        assert stats["funnel"]["not_game_level"] == 0, (
            "a joined child was still counted as refused"
        )

    @pytest.mark.asyncio
    async def test_the_commit_lands_before_the_receipt_claims_the_link(
        self, monkeypatch
    ):
        """CERT-771: a receipt saying `linked` over a rolled-back link lies."""
        async def _resolver(session, market):
            return ROW

        class _FailingCommit(_Session):
            async def commit(self):
                raise RuntimeError("commit failed")

        abandoned = []

        async def _abandon(session, *, market_id, phase, stats, receipt, exc):
            abandoned.append(market_id)

        monkeypatch.setattr(pmm, "_polymarket_group_sibling_event_id", _resolver)
        monkeypatch.setattr(pmm, "_abandon_attempt", _abandon)

        stats, queue, receipt = await _attempt(_FailingCommit(), _Market())

        assert abandoned == [62900001]
        assert receipt.outcome != _receipts.OUTCOME_LINKED
        assert queue == []


class TestNoRowMeansTheRefusalIsUnchanged:
    @pytest.mark.asyncio
    async def test_a_group_with_no_row_is_refused_as_before(self, monkeypatch):
        async def _resolver(session, market):
            return None

        monkeypatch.setattr(pmm, "_polymarket_group_sibling_event_id", _resolver)
        session, market = _Session(), _Market()

        stats, queue, receipt = await _attempt(session, market)

        assert market.event_id is None
        assert session.commits == 0
        assert receipt.reject_reason == _receipts.REJECT_NOT_GAME_LEVEL
        assert queue == []
        assert stats["funnel"]["not_game_level"] == 1
        assert "group_prop_joins" not in stats["funnel"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"source": "kalshi"},
            {"group_type": "polymarket_event"},
            {"group_id": None},
        ],
    )
    async def test_a_market_that_is_no_game_child_never_queries(self, kwargs):
        """The REAL resolver, `session=None`: any query would raise."""
        market = _Market(**kwargs)
        stats, queue, receipt = await _attempt(None, market)

        assert market.event_id is None
        assert receipt.outcome != _receipts.OUTCOME_LINKED
        assert stats["funnel"]["not_game_level"] == 1
