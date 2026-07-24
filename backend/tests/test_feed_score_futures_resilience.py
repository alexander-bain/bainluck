"""Guard: one malformed futures market must never wipe the whole futures pass.

Queue #250: the futures analogue of the #1091 `_score_events` guard
(test_feed_score_events_resilience.py). `_score_futures` scored every candidate
market in a single loop with NO per-item error guard, so one market that raised
mid-loop (e.g. the naive-vs-aware `resolution_date - now` TypeError in the
sort_time arithmetic, or an unparseable `current_probability`) aborted scoring
for ALL futures and emptied the futures half of the feed.

Two fixes are locked in here:
1. The sort_time arithmetic now reuses the tz-normalized ``res_dt`` (via ``_utc``)
   instead of the raw ``resolution_date`` — so a naive DB datetime can't raise.
2. A per-item try/except around the loop body skips a poison market and keeps
   the healthy siblings (this test's poison uses an unparseable probability so
   the ``sorted(..., float(o.current_probability))`` raises mid-loop).
"""

import inspect
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.routes.feed as feed_mod
from app.routes.feed import _score_futures
from app.utils.personalization import PersonalizationContext


class _Outcome:
    def __init__(self, id, name, current_probability, *, change=0.0, opening=None):
        self.id = id
        self.name = name
        self.current_probability = current_probability
        self.probability_change_24h = change
        self.opening_probability = opening
        self.rank = None
        self.rank_change_24h = None
        self.team_id = None
        self.calibration_probability = None


class _Market:
    """A real object (not MagicMock) so ``__dict__.get(...)`` reads work."""

    # Distinct name + category per id so the diversity caps (exact_family_cap=1)
    # don't legitimately collapse siblings — this test is about the error guard,
    # not dedup.
    _PROFILES = {
        1: ("Who will win the US Presidential election?", "politics"),
        2: ("Will the Fed cut rates in December?", "economics"),
        3: ("Who wins Best Picture at the Oscars?", "entertainment"),
    }

    def __init__(self, id, *, poison=False):
        now = datetime.now(timezone.utc)
        self.id = id
        name, category = self._PROFILES.get(
            id, (f"Test market {id}?", "politics")
        )
        self.name = name
        self.source = "polymarket"
        self.external_id = f"poly-{id}"
        self.sport_id = None
        self.sport = None
        self.category = category
        self.llm_sport_category = category
        self.market_tier = 1
        self.canonical_market_key = None  # short-circuits canonical source counts
        self.group_id = None
        self.group_type = None
        self.image_url = None
        self.hook_description = None
        self.hook_generated_at = None
        self.hook_leader_at_generation = None
        self.market_metadata = {}
        self.curation_score_adj = 0
        self.volume_24h = 250000
        self.updated_at = now
        self.commence_time = now - timedelta(days=1)
        self.resolution_date = now + timedelta(days=30)
        self.status = "open"
        self.created_at = now - timedelta(days=10)
        self.llm_league = None
        self.llm_gender = None
        self.llm_level = None
        # A poison market carries an unparseable probability so the outcome sort
        # (float(o.current_probability)) raises mid-loop, exactly like a real
        # malformed row would.
        top_prob = "not-a-number" if poison else 0.55
        self.outcomes = [
            _Outcome(10 + id, "Candidate A", top_prob, change=0.12, opening=0.43),
            _Outcome(20 + id, "Candidate B", 0.45, change=-0.12, opening=0.57),
        ]


def _mock_db(markets):
    """DB whose pool queries yield market ids and whose entity load yields the
    market objects. Distinguished by whether ``.scalars().unique()`` is used."""
    db = AsyncMock()

    def make_result(*a, **k):
        r = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = [m.id for m in markets]  # pool id queries
        unique = MagicMock()
        unique.all.return_value = markets  # markets_result entity load
        scalars.unique.return_value = unique
        r.scalars.return_value = scalars
        r.all.return_value = []  # canonical counts / snapshots
        return r

    db.execute = AsyncMock(side_effect=make_result)
    return db


async def _run(markets):
    with (
        patch(
            "app.routes.feed._external_curator_recall_market_ids",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.tasks.redis_state.get_async_redis_client",
            side_effect=Exception("no redis in test"),
        ),
    ):
        now = datetime.now(timezone.utc)
        ctx = PersonalizationContext()
        return await _score_futures(_mock_db(markets), now, None, ctx)


@pytest.mark.asyncio
async def test_poison_market_does_not_wipe_futures_pass():
    good = _Market(1)
    poison = _Market(2, poison=True)
    # Poison first: proves the loop keeps going past the failing row.
    items = await _run([poison, good])
    ids = {i["data"]["id"] for i in items if i["type"] == "futures"}
    assert 1 in ids, f"good market dropped by poison neighbor — pass wiped: {ids}"
    assert 2 not in ids, "poison market should have been skipped, not scored"


@pytest.mark.asyncio
async def test_all_good_markets_survive():
    markets = [_Market(i) for i in (1, 2, 3)]
    items = await _run(markets)
    ids = {i["data"]["id"] for i in items if i["type"] == "futures"}
    assert ids == {1, 2, 3}, f"expected all 3 markets, got {ids}"


def test_score_futures_loop_has_per_item_guard():
    """Source guard: the scoring loop must wrap its body in try/except+continue
    so a throwing market can't abort the pass (mirrors _score_events, #1091)."""
    src = inspect.getsource(feed_mod._score_futures)
    loop_body = src.split("for market in markets:", 1)[1]
    # The very first statement inside the loop is the guard.
    assert loop_body.lstrip().startswith("try:"), (
        "the _score_futures per-item loop must open with `try:`"
    )
    assert "except Exception as _score_err:" in loop_body
    # The sort_time arithmetic must use the tz-normalized res_dt, not raw
    # resolution_date, so a naive DB datetime cannot raise.
    assert "(res_dt - now).total_seconds()" in loop_body
