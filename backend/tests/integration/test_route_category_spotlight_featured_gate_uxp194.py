"""Guard: the cross-source spotlight honors its page's own featured gate.

UX-P194-1. `/economics`, `/politics` and `/entertainment` each run every market
through ``should_exclude_from_featured`` before putting it in a theme section,
and each then handed ``find_cross_source_markets`` the RAW query result. A
market the page had just refused to list could still headline it as the
Kalshi-vs-Polymarket disagreement.

REPRODUCED ON PRODUCTION 2026-08-31, before the fix. Of 19 live spotlight cards
across the three pages, one was built on an ineligible market: `/politics`
showed

    "Will the Supreme Court rule in favor of Trump's tariffs"
    Kalshi 25.5%   Polymarket 0.1%   delta 25.4

whose Polymarket side (market 112981) was a single-outcome market sitting at a
leader probability of **0.0005**. That is `probability_extreme` — an order of
magnitude under ``PROBABILITY_EXTREME_LOW`` — and the page's own theme sections
had already dropped it. The "disagreement" was between a real market and a dead
one. ``TestTheProductionSpecimen`` below replays those exact two rows.

═══ TWO THINGS THIS FILE HAS TO GET RIGHT ═══

**1. Both members of the pair.** A cross-source card is a PAIR, and the live
specimen was unfit on its POLYMARKET half while its Kalshi half was healthy at
0.255. A guard that only ever plants the defect on the Kalshi side passes while
the real production defect walks straight through, so every case below is run
from both ends.

**2. The LOW extreme, not the high one.** All three `_cross_source_row_fn`s
already drop a binary priced over 95, and ``find_cross_source_markets`` already
skips ``is_resolved`` markets. Between them the top end was covered, which is
why the surviving production specimen is a LOW one. The arms that were genuinely
unguarded are `probability_extreme` at the bottom and the `stale_*` title
reasons; those are what these tests plant.

═══ WHAT THIS GUARD DELIBERATELY DOES NOT COVER ═══

The eligible list is captured after ``should_exclude_from_featured`` and BEFORE
each page's topical filter (`_is_non_politics`, entertainment's
`"excluded"` theme). Those answer "is this market on-topic", not "is this market
fit to feature", and widening a predicate blind has bitten this repo before
(UX-P197-1: `market_reads_settled` has one consumer and extending it is not
safe). Measured on the same 19 production cards: **0 of 8** `/politics` and
**0 of 8** `/entertainment` spotlight cards fail their topical filter today, so
this is a stated absence with a number behind it, not an oversight.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest


# ---------------------------------------------------------------------------
# Mocks — mirroring the shared idiom in test_route_category_pages.py
# ---------------------------------------------------------------------------


class _MockScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items

    def first(self):
        return self._items[0] if self._items else None

    def unique(self):
        return self


class _MockResult:
    def __init__(self, items):
        self._scalars = _MockScalars(items)

    def scalars(self):
        return self._scalars

    def all(self):
        return self._scalars.all()

    def first(self):
        return self._scalars.first()


def _outcome(name, probability, *, outcome_id=1, rank=1):
    return SimpleNamespace(
        id=outcome_id,
        name=name,
        current_probability=probability,
        probability_change_24h=0,
        rank=rank,
    )


def _market(
    *,
    market_id,
    name,
    source,
    probability,
    llm_sport_category="politics",
    external_id=None,
):
    """A single-outcome market — the shape both production specimens had."""
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=market_id,
        name=name,
        external_id=external_id or f"mock{market_id}",
        source=source,
        category="news",
        llm_sport_category=llm_sport_category,
        outcomes=[_outcome("Yes", probability, outcome_id=market_id * 10)],
        resolution_date=now + timedelta(days=30),
        updated_at=now,
        volume_24h=1000,
        image_url=None,
        hook_description=None,
        status="open",
    )


# Each page, with the category its markets must carry to survive the route's
# own query-shaped assumptions.
PAGES = [
    pytest.param("/api/economics", "economics", id="economics"),
    pytest.param("/api/politics", "politics", id="politics"),
    pytest.param("/api/entertainment", "entertainment", id="entertainment"),
]

# A leader probability under PROBABILITY_EXTREME_LOW (0.02). Kept ABOVE the
# is_resolved()'s all-outcomes-under-0.01 rule's reach by being a single-outcome
# market, exactly like production market 112981.
DEAD_LOW = 0.005
HEALTHY = 0.35
OTHER_HEALTHY = 0.62


def _pair(question, *, kalshi_prob, poly_prob, category, kalshi_name=None):
    """A Kalshi/Polymarket pair the spotlight should match on."""
    return [
        _market(
            market_id=901,
            name=kalshi_name or question,
            source="kalshi",
            probability=kalshi_prob,
            llm_sport_category=category,
        ),
        _market(
            market_id=902,
            name=question,
            source="polymarket",
            probability=poly_prob,
            llm_sport_category=category,
        ),
    ]


async def _spotlight(client, mock_db, path, markets):
    mock_db.execute.return_value = _MockResult(markets)
    resp = await client.get(path)
    assert resp.status_code == 200
    return resp.json()["cross_source"]


# ============================================================================
# The production specimen, replayed
# ============================================================================


class TestTheProductionSpecimen:
    """The exact two rows that were live on /politics on 2026-08-31."""

    KALSHI_Q = "Will the Supreme Court rule in favor of Trump's tariffs?"
    POLY_Q = "Supreme Court rules in favor of Trump's tariffs?"

    def _markets(self, poly_prob):
        return [
            _market(
                market_id=108496,
                name=self.KALSHI_Q,
                source="kalshi",
                probability=0.255,
            ),
            _market(
                market_id=112981,
                name=self.POLY_Q,
                source="polymarket",
                probability=poly_prob,
            ),
        ]

    async def test_the_dead_polymarket_side_no_longer_headlines_politics(
        self, client, mock_db
    ):
        cards = await _spotlight(
            client, mock_db, "/api/politics", self._markets(0.0005)
        )
        assert cards == [], (
            "the 0.05% Polymarket market is probability_extreme and the page's "
            f"own theme sections drop it; it must not headline. Got: {cards}"
        )

    async def test_control_the_same_pair_headlines_when_both_sides_are_alive(
        self, client, mock_db
    ):
        """Without this the test above would pass on a pair that never matched."""
        cards = await _spotlight(
            client, mock_db, "/api/politics", self._markets(HEALTHY)
        )
        assert len(cards) == 1, f"the pair itself must still match. Got: {cards}"
        assert cards[0]["kalshi_market_id"] == 108496
        assert cards[0]["poly_market_id"] == 112981


# ============================================================================
# Both sides of the pair, on all three pages
# ============================================================================


class TestEitherMemberDisqualifiesTheCard:
    QUESTION = "Will the committee approve the measure?"

    @pytest.mark.parametrize("path,category", PAGES)
    async def test_control_a_healthy_pair_is_featured(
        self, client, mock_db, path, category
    ):
        cards = await _spotlight(
            client,
            mock_db,
            path,
            _pair(
                self.QUESTION,
                kalshi_prob=HEALTHY,
                poly_prob=OTHER_HEALTHY,
                category=category,
            ),
        )
        assert len(cards) == 1, f"{path}: a healthy pair must still be featured"

    @pytest.mark.parametrize("path,category", PAGES)
    async def test_dead_kalshi_side_drops_the_card(
        self, client, mock_db, path, category
    ):
        cards = await _spotlight(
            client,
            mock_db,
            path,
            _pair(
                self.QUESTION,
                kalshi_prob=DEAD_LOW,
                poly_prob=OTHER_HEALTHY,
                category=category,
            ),
        )
        assert cards == [], f"{path}: excluded KALSHI member must drop the card"

    @pytest.mark.parametrize("path,category", PAGES)
    async def test_dead_polymarket_side_drops_the_card(
        self, client, mock_db, path, category
    ):
        """The side the real production defect was on."""
        cards = await _spotlight(
            client,
            mock_db,
            path,
            _pair(
                self.QUESTION,
                kalshi_prob=HEALTHY,
                poly_prob=DEAD_LOW,
                category=category,
            ),
        )
        assert cards == [], f"{path}: excluded POLYMARKET member must drop the card"


# ============================================================================
# The other unguarded arm: a title whose own date has passed
# ============================================================================


class TestEntertainmentTrendingSharesTheSameList:
    """`/entertainment` has a THIRD reader of the eligible set: trending.

    It used to call ``should_exclude_from_featured`` in its own loop and now
    reads the shared list, so the exclusion is one edit away from being lost
    here without the spotlight tests noticing. Measured while building this
    guard: mutating that loop back to the raw `all_markets` left the whole
    entertainment suite GREEN at 81/81 — the behaviour was never pinned by
    anything in the repo. It is pinned now.
    """

    async def test_a_dead_market_does_not_reach_the_trending_hero(
        self, client, mock_db
    ):
        mock_db.execute.return_value = _MockResult([
            _market(
                market_id=701,
                name="Which artist tops the chart in December?",
                source="kalshi",
                probability=DEAD_LOW,
                llm_sport_category="entertainment",
            ),
        ])
        body = (await client.get("/api/entertainment")).json()
        names = [row["q"] for row in body["trending"]]
        assert names == [], (
            f"a probability_extreme market must not trend. Got: {names}"
        )

    async def test_control_a_live_market_does_reach_the_trending_hero(
        self, client, mock_db
    ):
        mock_db.execute.return_value = _MockResult([
            _market(
                market_id=702,
                name="Which artist tops the chart in December?",
                source="kalshi",
                probability=HEALTHY,
                llm_sport_category="entertainment",
            ),
        ])
        body = (await client.get("/api/entertainment")).json()
        names = [row["q"] for row in body["trending"]]
        assert names == ["Which artist tops the chart in December?"], (
            f"only the PRICE differs from the case above. Got: {names}"
        )


class TestStaleTitleIsAlsoExcluded:
    """`stale_*` is the second arm the row-fn's `prob > 95` clause never covered.

    Staleness is derived from the market NAME and the pair is matched on the
    name, so both members carry the same verdict — the one-sided cases above
    are the probability arm's job. The year is explicit in both titles, so
    neither assertion moves with the clock (gotcha #44).
    """

    STALE = "Will the delegation arrive by Jan 5, 2020?"
    FUTURE = "Will the delegation arrive by Jan 5, 2099?"

    @pytest.mark.parametrize("path,category", PAGES)
    async def test_a_title_dated_in_the_past_is_not_featured(
        self, client, mock_db, path, category
    ):
        cards = await _spotlight(
            client,
            mock_db,
            path,
            _pair(
                self.STALE,
                kalshi_prob=HEALTHY,
                poly_prob=OTHER_HEALTHY,
                category=category,
            ),
        )
        assert cards == [], f"{path}: a title-stale pair must not be featured"

    @pytest.mark.parametrize("path,category", PAGES)
    async def test_control_the_same_question_dated_ahead_is_featured(
        self, client, mock_db, path, category
    ):
        cards = await _spotlight(
            client,
            mock_db,
            path,
            _pair(
                self.FUTURE,
                kalshi_prob=HEALTHY,
                poly_prob=OTHER_HEALTHY,
                category=category,
            ),
        )
        assert len(cards) == 1, (
            f"{path}: only the DATE differs from the case above — if this is "
            "empty too, the assertion above is proving nothing"
        )
