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

═══ WHAT CERT-540 OVERTURNED, AND WHY THE LINE MOVED ═══

The first version of this ship captured the eligible list after
``should_exclude_from_featured`` and BEFORE each page's remaining gates
(`_is_non_politics`, `market_reads_settled` and the resolution-date cutoff on
`/politics`; the `"excluded"` theme on `/entertainment`), on the reasoning that
those answer "is this market on-topic / decided" rather than "is it fit to
feature", and that **0 of 8** `/politics` and **0 of 8** `/entertainment` live
cards failed them.

**That census was evidence of present absence, and CERT-540 was right that it is
not a class guard.** The cert built two pairs that walked straight through the
partial gate: a settled-open winner pair, and an NBA pair carrying
`llm_sport_category='politics'`. Both were absent from every theme section on
the page and both still came back as its sole spotlight card.

The rule is now the simple one, and it is the same on all three routes:
**the spotlight is fed what the page ACCEPTED.** A market that could not earn a
theme section cannot headline the page above them.

Re-measured on production 2026-08-31 before the repair, to size what tightening
costs a reader: across the same 19 live cards, the newly-honored gates remove
**zero** — 8 of 8 `/politics`, 8 of 8 `/entertainment`, 3 of 3 `/economics`
survive them (checked against the real `market_reads_settled`,
`_is_non_politics` and `_classify_theme`; all 16 politics-side markets carry
`n_win = 0`, no venue-settled stamp, and a future `resolution_date`). The class
closes at no cost to today's page.

⚠️ ONE THING IS STILL DELIBERATELY NOT DONE. `/entertainment` keeps TWO lists:
trending still reads the wider `should_exclude_from_featured` survivors, and
only the spotlight reads the themed set. Narrowing trending would be a silent
ranking change nobody asked for. ``TestEntertainmentTrendingSharesTheSameList``
below pins the half that IS shared; ``test_trending_still_sees_an_off_theme
_market`` pins the half that is not.
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


def _outcome(
    name,
    probability,
    *,
    outcome_id=1,
    rank=1,
    is_winner=None,
    resolution_source=None,
):
    return SimpleNamespace(
        id=outcome_id,
        name=name,
        current_probability=probability,
        probability_change_24h=0,
        rank=rank,
        is_winner=is_winner,
        resolution_source=resolution_source,
    )


def _market(
    *,
    market_id,
    name,
    source,
    probability,
    llm_sport_category="politics",
    external_id=None,
    settled=False,
    resolution_date=None,
):
    """A single-outcome market — the shape both production specimens had.

    ``settled=True`` reproduces the CERT-540 specimen: ``status`` stays
    ``'open'`` (gotcha #33 — Kalshi leaves it there) while the single leg
    carries a graded winner and a settlement source, which is what
    ``market_reads_settled`` reads and what nothing else on the page can see.
    """
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=market_id,
        name=name,
        external_id=external_id or f"mock{market_id}",
        source=source,
        category="news",
        llm_sport_category=llm_sport_category,
        outcomes=[
            _outcome(
                "Yes",
                probability,
                outcome_id=market_id * 10,
                is_winner=True if settled else None,
                resolution_source="api_settlement" if settled else None,
            )
        ],
        market_metadata=(
            {"shape": {"expected_winners": 1}} if settled else None
        ),
        resolution_date=(
            resolution_date
            if resolution_date is not None
            else now + timedelta(days=30)
        ),
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


def _pair(
    question,
    *,
    kalshi_prob,
    poly_prob,
    category,
    kalshi_name=None,
    kalshi_settled=False,
    poly_settled=False,
    kalshi_resolution_date=None,
    poly_resolution_date=None,
):
    """A Kalshi/Polymarket pair the spotlight should match on."""
    return [
        _market(
            market_id=901,
            name=kalshi_name or question,
            source="kalshi",
            probability=kalshi_prob,
            llm_sport_category=category,
            settled=kalshi_settled,
            resolution_date=kalshi_resolution_date,
        ),
        _market(
            market_id=902,
            name=question,
            source="polymarket",
            probability=poly_prob,
            llm_sport_category=category,
            settled=poly_settled,
            resolution_date=poly_resolution_date,
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


# ============================================================================
# CERT-540: the gates BELOW the old append point
# ============================================================================


class TestASettledPairDoesNotHeadlinePolitics:
    """CERT-540 finding 1 — "settled means settled", including in the spotlight.

    `/politics` drops a decided contest from its theme sections through
    ``market_reads_settled`` (CERT-452). The first version of this ship
    snapshotted the eligible list ABOVE that gate, so a settled election could
    be absent from every section and still headline the page as a live
    Kalshi-vs-Polymarket disagreement.

    Nothing else on the page can see this: ``status`` stays ``'open'`` on a
    settled Kalshi market (gotcha #33), ``resolution_date`` is in the future,
    the prices are healthy, and ``find_cross_source_markets.is_resolved`` looks
    only at price extremes. The pair below is priced 35 / 62 and would sail
    through every one of them.

    ONE SIDE AT A TIME, because settlement is a per-market fact and the live
    UX-P194 specimen was unfit on its Polymarket half alone.
    """

    QUESTION = "Will the incumbent win the runoff?"

    async def test_a_settled_kalshi_side_drops_the_card(self, client, mock_db):
        cards = await _spotlight(
            client,
            mock_db,
            "/api/politics",
            _pair(
                self.QUESTION,
                kalshi_prob=HEALTHY,
                poly_prob=OTHER_HEALTHY,
                category="politics",
                kalshi_settled=True,
            ),
        )
        assert cards == [], (
            "a graded winner on the KALSHI side is settled; the page's own "
            f"sections drop it and so must the spotlight. Got: {cards}"
        )

    async def test_a_settled_polymarket_side_drops_the_card(
        self, client, mock_db
    ):
        cards = await _spotlight(
            client,
            mock_db,
            "/api/politics",
            _pair(
                self.QUESTION,
                kalshi_prob=HEALTHY,
                poly_prob=OTHER_HEALTHY,
                category="politics",
                poly_settled=True,
            ),
        )
        assert cards == [], (
            "a graded winner on the POLYMARKET side is settled; the page's own "
            f"sections drop it and so must the spotlight. Got: {cards}"
        )

    async def test_control_the_same_pair_headlines_while_ungraded(
        self, client, mock_db
    ):
        """Only ``is_winner``/``resolution_source`` differ from the two above."""
        cards = await _spotlight(
            client,
            mock_db,
            "/api/politics",
            _pair(
                self.QUESTION,
                kalshi_prob=HEALTHY,
                poly_prob=OTHER_HEALTHY,
                category="politics",
            ),
        )
        assert len(cards) == 1, (
            "the pair must match while ungraded, or the two assertions above "
            f"are proving nothing. Got: {cards}"
        )


class TestAnOffTopicPairDoesNotHeadline:
    """CERT-540 finding 2 — the page's topical filter reaches the spotlight too.

    ``_is_non_politics`` on `/politics` and the ``"excluded"`` theme on
    `/entertainment` are each that page's defence against an upstream
    misclassification. The cert's specimen is an NBA market carrying
    ``llm_sport_category='politics'``: absent from every theme, and yet the
    page's sole spotlight card.

    SYMMETRIC BY CONSTRUCTION, and that is not the same omission the
    probability arm would be making. Both verdicts are derived from the market
    NAME, and the pair is matched on the name, so both members always carry the
    same verdict — the same reasoning as ``TestStaleTitleIsAlsoExcluded``. The
    per-side cases live in the classes above, where the fact IS per-market.
    """

    async def test_a_mislabelled_sports_pair_does_not_headline_politics(
        self, client, mock_db
    ):
        cards = await _spotlight(
            client,
            mock_db,
            "/api/politics",
            _pair(
                "Will the NBA finals winner be Boston?",
                kalshi_prob=HEALTHY,
                poly_prob=OTHER_HEALTHY,
                category="politics",
            ),
        )
        assert cards == [], (
            "`_is_non_politics` rejects this from every theme section; it must "
            f"not headline the page above them. Got: {cards}"
        )

    async def test_control_an_on_topic_pair_headlines_politics(
        self, client, mock_db
    ):
        """Only the SUBJECT differs — same category, same prices."""
        cards = await _spotlight(
            client,
            mock_db,
            "/api/politics",
            _pair(
                "Will the senate committee winner be Boston?",
                kalshi_prob=HEALTHY,
                poly_prob=OTHER_HEALTHY,
                category="politics",
            ),
        )
        assert len(cards) == 1, (
            f"an on-topic pair must still be featured. Got: {cards}"
        )

    async def test_an_excluded_theme_pair_does_not_headline_entertainment(
        self, client, mock_db
    ):
        cards = await _spotlight(
            client,
            mock_db,
            "/api/entertainment",
            _pair(
                "Will the studio complete the acquisition this year?",
                kalshi_prob=HEALTHY,
                poly_prob=OTHER_HEALTHY,
                category="entertainment",
            ),
        )
        assert cards == [], (
            "`_classify_theme` returns 'excluded' for this, so no section "
            f"carries it; the spotlight must not either. Got: {cards}"
        )

    async def test_control_an_on_theme_pair_headlines_entertainment(
        self, client, mock_db
    ):
        cards = await _spotlight(
            client,
            mock_db,
            "/api/entertainment",
            _pair(
                "Will the studio complete the sequel this year?",
                kalshi_prob=HEALTHY,
                poly_prob=OTHER_HEALTHY,
                category="entertainment",
            ),
        )
        assert len(cards) == 1, (
            f"an on-theme pair must still be featured. Got: {cards}"
        )


class TestAPastResolutionDateDoesNotHeadlinePolitics:
    """The third gate below the old append point, and the cert did not name it.

    `/politics` drops a market whose ``resolution_date`` is more than seven days
    old. CERT-540 named the settled and topical gates; this one is the same
    class sitting in the same loop, and closing two of three would have left
    the next cert a third instance to find.

    Unlike the two topical cases this fact is PER-MARKET — it is a column, not
    the shared question text — so both sides are exercised separately. The
    dates are absolute, never clock-branched (gotcha #44).
    """

    QUESTION = "Will the treaty be ratified?"
    LONG_PAST = datetime(2020, 1, 5, tzinfo=timezone.utc)

    async def test_a_stale_dated_kalshi_side_drops_the_card(
        self, client, mock_db
    ):
        cards = await _spotlight(
            client,
            mock_db,
            "/api/politics",
            _pair(
                self.QUESTION,
                kalshi_prob=HEALTHY,
                poly_prob=OTHER_HEALTHY,
                category="politics",
                kalshi_resolution_date=self.LONG_PAST,
            ),
        )
        assert cards == [], (
            f"a KALSHI side resolving in 2020 is not a live question. Got: {cards}"
        )

    async def test_a_stale_dated_polymarket_side_drops_the_card(
        self, client, mock_db
    ):
        cards = await _spotlight(
            client,
            mock_db,
            "/api/politics",
            _pair(
                self.QUESTION,
                kalshi_prob=HEALTHY,
                poly_prob=OTHER_HEALTHY,
                category="politics",
                poly_resolution_date=self.LONG_PAST,
            ),
        )
        assert cards == [], (
            f"a POLYMARKET side resolving in 2020 is not live either. Got: {cards}"
        )

    async def test_control_the_same_pair_dated_ahead_headlines(
        self, client, mock_db
    ):
        cards = await _spotlight(
            client,
            mock_db,
            "/api/politics",
            _pair(
                self.QUESTION,
                kalshi_prob=HEALTHY,
                poly_prob=OTHER_HEALTHY,
                category="politics",
                kalshi_resolution_date=datetime(2099, 1, 5, tzinfo=timezone.utc),
                poly_resolution_date=datetime(2099, 1, 5, tzinfo=timezone.utc),
            ),
        )
        assert len(cards) == 1, (
            f"only the DATE differs from the two cases above. Got: {cards}"
        )


# ============================================================================
# The structural pin: whatever the gates are, the spotlight is a subset
# ============================================================================


def _rendered_market_ids(payload: dict) -> set:
    """Every ``market_id`` the page renders in a SECTION, spotlight excluded.

    Walks the whole response rather than naming sections, so a market that
    moves between sections — or a section added later — needs no edit here.
    ``cross_source`` is popped first because its entries are keyed
    ``kalshi_market_id`` / ``poly_market_id``; the comparison would otherwise
    be a tautology.
    """
    body = {k: v for k, v in payload.items() if k != "cross_source"}
    found: set = set()

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("market_id"), int):
                found.add(node["market_id"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(body)
    return found


class TestTheSpotlightIsASubsetOfWhatThePageRenders:
    """The pin the route comments point at, and the only GENERIC one here.

    Every other test in this file names a gate. This one names none: it plants
    one healthy pair and one pair rejected by each gate, and asserts that no
    spotlight card is built on a market that reached no section.

    🔴 THIS IS WHAT NOTICES A GATE ADDED IN THE WRONG PLACE. The coupling
    between the theme loop's rejections and the spotlight's input list is
    POSITIONAL — ``spotlight_eligible.append(m)`` sits at the bottom of the
    loop — and a future gate written below that append re-opens exactly the
    hole CERT-540 blocked, in a shape no gate-specific test can see.
    """

    async def test_politics_spotlight_only_features_rendered_markets(
        self, client, mock_db
    ):
        healthy = _pair(
            "Will the coalition hold through the winter?",
            kalshi_prob=HEALTHY,
            poly_prob=OTHER_HEALTHY,
            category="politics",
        )
        rejected = [
            _market(
                market_id=911,
                name="Will the NBA finals winner be Boston?",
                source="kalshi",
                probability=HEALTHY,
            ),
            _market(
                market_id=912,
                name="Will the NBA finals winner be Boston?",
                source="polymarket",
                probability=OTHER_HEALTHY,
            ),
            _market(
                market_id=913,
                name="Will the referendum pass?",
                source="kalshi",
                probability=HEALTHY,
                settled=True,
            ),
            _market(
                market_id=914,
                name="Will the referendum pass?",
                source="polymarket",
                probability=OTHER_HEALTHY,
            ),
            _market(
                market_id=915,
                name="Will the envoy be confirmed?",
                source="kalshi",
                probability=HEALTHY,
                resolution_date=datetime(2020, 1, 5, tzinfo=timezone.utc),
            ),
            _market(
                market_id=916,
                name="Will the envoy be confirmed?",
                source="polymarket",
                probability=OTHER_HEALTHY,
            ),
            _market(
                market_id=917,
                name="Will the tribunal rule by spring?",
                source="kalshi",
                probability=DEAD_LOW,
            ),
            _market(
                market_id=918,
                name="Will the tribunal rule by spring?",
                source="polymarket",
                probability=OTHER_HEALTHY,
            ),
        ]

        mock_db.execute.return_value = _MockResult(healthy + rejected)
        body = (await client.get("/api/politics")).json()

        rendered = _rendered_market_ids(body)
        featured = {
            side
            for card in body["cross_source"]
            for side in (card["kalshi_market_id"], card["poly_market_id"])
        }

        assert featured, (
            "NON-VACUITY: the healthy pair must produce a card, or this test "
            "passes on an empty spotlight and asserts nothing"
        )
        assert featured <= rendered, (
            "the spotlight is built on markets no section renders — a gate has "
            "been added below `spotlight_eligible.append(m)`. Unrendered and "
            f"featured: {sorted(featured - rendered)}"
        )
        assert featured == {901, 902}, (
            "only the healthy pair may headline; every other pair here is "
            f"rejected by one of the page's gates. Got: {sorted(featured)}"
        )


class TestTrendingIsDeliberatelyNotNarrowed:
    """`/entertainment` keeps TWO lists, and this pins the difference.

    The spotlight reads the themed set; TRENDING still reads the wider
    ``should_exclude_from_featured`` survivors. Collapsing them would be a
    silent ranking change nobody asked for. Without this test, "narrow trending
    to the themed set too" is a one-line edit the rest of the suite is blind to.
    """

    OFF_THEME = "Will the studio complete the acquisition this year?"

    async def test_trending_still_sees_an_off_theme_market(
        self, client, mock_db
    ):
        mock_db.execute.return_value = _MockResult([
            _market(
                market_id=721,
                name=self.OFF_THEME,
                source="kalshi",
                probability=HEALTHY,
                llm_sport_category="entertainment",
            ),
        ])
        body = (await client.get("/api/entertainment")).json()
        assert [row["q"] for row in body["trending"]] == [self.OFF_THEME], (
            "trending reads the FITNESS survivors, not the themed set; an "
            "'excluded'-theme market with a healthy price still trends. If "
            "this is empty, trending was narrowed along with the spotlight."
        )

    async def test_control_the_same_market_does_not_reach_the_spotlight(
        self, client, mock_db
    ):
        """The other half of the same fact, so the pair reads as one decision."""
        cards = await _spotlight(
            client,
            mock_db,
            "/api/entertainment",
            _pair(
                self.OFF_THEME,
                kalshi_prob=HEALTHY,
                poly_prob=OTHER_HEALTHY,
                category="entertainment",
            ),
        )
        assert cards == [], (
            f"the spotlight reads the THEMED set, so this is dropped. Got: {cards}"
        )
