"""#6704 — a cumulative ladder stops being deleted from /economics as "decided".

Measured on production 2026-09-21 17:2xZ. `routes/economics.py` computed each
market's leader probability as ``max(current_probability)`` and handed it to
``should_exclude_from_featured``, whose ``probability_extreme`` arm drops
anything over 0.98. For a **cumulative** ladder the maximum is the LOOSEST
bound — "gold above $3,000" on a day gold trades near $4,545 — which is a
near-certainty by construction and says nothing about whether the question is
decided.

Site-wide that arm deleted **323 open markets**, of which **256 (79%) carried a
rung between 2% and 98%**. On the METALS section shipped that morning (#7809) it
deleted **5 of the 11 metals markets we hold**, and the inversion is the tell:
the wider the ladder the further its floor reaches below spot, so the ladders
most worth drawing are the likeliest to go. `KXCOPPERMON` — 50 rungs and
**12,225** in 24h volume, the most-traded metals market on the page — was
excluded; `KXGOLDDIRY`, 13 rungs and 2,642, survived.

═══ WHY THIS SHIP IS TWO CHANGES AND NOT ONE ═══

Admitting the five is not, by itself, anything a reader sees. Every section on
this page publishes a slice (`cards[:4]`, `side_markets[:6]`) and the query
carries no ``ORDER BY``, so widening the pool from 6 to 11 for four card slots
just re-rolls which four arbitrary markets win — and the pool it re-rolls
against contains `KXSILVERW` at **34** in 24h volume. Widening the gate without
an order is how the 34 takes the slot from the 12,225. So the gate fix ships
with a deterministic most-traded-first sort, and the reader-visible claim is the
pair: **the four metals cards are the four most-traded metals markets.**

═══ HOW THESE GUARDS COULD HAVE BEEN VACUOUS ═══

1. **A fixture that never reproduced the defect.** Every assertion below would
   pass on a pool the old code already published. ``TestTheDefectIsInTheSeed``
   runs the OLD rule over the fixtures and requires all five exclusions, and
   the equivalence test pins the binary path against a literal copy of the
   closure this change replaced.
2. **Counting the section instead of reading it.** The metals section did NOT
   get bigger: it published 4 cards + 1 row before and publishes 4 cards + 1
   row after, because the card cap was already binding. A `len(...)` assertion
   would be green on the unfixed page. The claims below are on WHICH markets
   and in WHICH order.
3. **Order by accident.** A fixture listing the biggest market first is green
   under heap order too. ``_METALS`` is deliberately in ASCENDING volume — the
   12,225 ladder is last — and the whole route is re-run over shuffles.
4. **The clock.** ``get_economics`` reads ``datetime.now`` and the staleness
   arm consumes it, so an unpinned test changes meaning as the fixtures' titles
   recede (gotcha #44). ``datetime`` is patched to a fixed instant.
"""

import random
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.economics import get_economics
from app.utils.market_staleness import (
    featured_leader_probability,
    is_probability_extreme,
    outcome_names_are_cumulative_ladder,
    should_exclude_from_featured,
)

# The metals fixtures below are dated September 2026; keep the clock inside the
# month so no title-implied-staleness arm fires instead of the one under test.
FIXED_NOW = datetime(2026, 9, 21, 17, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# The rule this change replaced, copied verbatim so the binary path is pinned
# against the thing it has to stay equal to rather than against a paraphrase.
# ---------------------------------------------------------------------------


def _old_leader_prob(outcomes):
    ordered = sorted(
        list(outcomes),
        key=lambda o: float(o.current_probability or 0),
        reverse=True,
    )
    return (
        float(ordered[0].current_probability)
        if ordered and ordered[0].current_probability
        else None
    )


def _outcome(idx: int, name: str, prob: float | None):
    return SimpleNamespace(id=idx, name=name, current_probability=prob, rank=idx)


def _pairs(outcomes):
    return [(o.name, o.current_probability) for o in outcomes]


# ---------------------------------------------------------------------------
# Production metals pool, 2026-09-21 17:2xZ
# ---------------------------------------------------------------------------
#
# ticker, question, 24h volume, rung count, max rung, rung nearest even money.
# Ticker / volume / rung count / both probabilities are the measured values; the
# intermediate rungs are a monotone fill, since what this suite asks of a rung is
# only which side of the band it sits on.
_METALS = [
    ("KXSILVERW-26SEP2517", "Silver price on September 25, 2026 at 5:00 PM EDT?", 34, 40, 0.995, 0.565),
    ("KXGOLDW-26SEP2517", "Gold price on September 25, 2026 at 5:00 PM EDT?", 92, 40, 0.985, 0.475),
    ("KXGOLDVSSILVER-26DEC31", "Annual Return: Gold vs. Silver", 149, 2, 0.705, 0.705),
    ("KXSILVERMON-26SEP3017", "Silver price on September 30, 2026 at 5:00 PM EDT?", 628, 40, 0.985, 0.495),
    ("KXCOPPERW-26SEP2517", "Copper price on September 25, 2026 at 5:00 PM EDT?", 1316, 40, 0.920, 0.525),
    ("KXSILVERD-26SEP2117", "Silver price on September 21, 2026 at 5:00 PM EDT?", 1913, 40, 0.980, 0.505),
    ("KXGOLDDIRY-26DEC31H1700", "Gold price at year end?", 2642, 13, 0.665, 0.500),
    ("KXCOPPERD-26SEP2117", "Copper price on September 21, 2026 at 5:00 PM EDT?", 3363, 40, 0.785, 0.480),
    ("KXGOLDMON-26SEP3017", "Gold price on September 30, 2026 at 5:00 PM EDT?", 4078, 40, 0.985, 0.525),
    ("KXGOLDD-26SEP2117", "Gold price on September 21, 2026 at 5:00 PM EDT?", 6133, 40, 0.980, 0.495),
    ("KXCOPPERMON-26SEP3017", "Copper price on September 30, 2026 at 5:00 PM EDT?", 12225, 50, 0.985, 0.505),
]

# The five the featured gate deleted, and the most-traded of them.
_DELETED_TODAY = {
    "KXSILVERW-26SEP2517",
    "KXGOLDW-26SEP2517",
    "KXSILVERMON-26SEP3017",
    "KXGOLDMON-26SEP3017",
    "KXCOPPERMON-26SEP3017",
}
_BIGGEST = "KXCOPPERMON-26SEP3017"


def _rungs(count: int, top: float, nearest: float, base: int = 3000) -> list[tuple[str, float]]:
    """A monotone `Above $X` ladder from `top` down, passing through `nearest`.

    ⚠️ ``base`` IS THE MARKET'S FINGERPRINT, and it is the only one available.
    A published card carries ``label`` / ``val`` / ``prob`` / ``brackets`` /
    ``src`` and no id or ticker, and the labels collide — four of these eleven
    questions truncate to "Gold price". A card assertion keyed on the label
    alone therefore cannot tell WHICH gold market is on the page, and passes on
    the unfixed route. Each fixture gets its own price decade so the card's
    ``val`` names its market.
    """
    if count == 2:
        return [("Gold", top), ("Silver", round(1 - top, 3))]
    probs = [top, nearest]
    step = (top - nearest) / max(count - 2, 1)
    probs += [round(top - step * (i + 1), 4) for i in range(count - 2)]
    probs = sorted(probs, reverse=True)[:count]
    # Thresholds ascend as the probability falls — a real cumulative ladder.
    return [
        (f"Above ${base + 10 * i:,}", p) for i, p in enumerate(probs)
    ]


def _market(index: int, ticker: str, name: str, volume: int, rungs):
    return SimpleNamespace(
        id=600_000 + index,
        name=name,
        source="kalshi",
        external_id=ticker.lower(),
        outcomes=[_outcome(i, n, p) for i, (n, p) in enumerate(rungs)],
        status="open",
        llm_sport_category="economics",
        group_id=None,
        volume=volume * 10,
        volume_24h=volume,
    )


_BASE_BY_TICKER = {ticker: 1000 * (i + 2) for i, (ticker, *_) in enumerate(_METALS)}


def _metals_markets():
    return [
        _market(i, ticker, name, volume, _rungs(count, top, nearest, _BASE_BY_TICKER[ticker]))
        for i, (ticker, name, volume, count, top, nearest) in enumerate(_METALS)
    ]


async def _run(markets):
    """Call the builder and return the published metals theme."""
    result_obj = MagicMock()
    result_obj.scalars.return_value.unique.return_value.all.return_value = list(markets)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result_obj)
    with patch("app.routes.economics.datetime") as dt:
        dt.now.return_value = FIXED_NOW
        payload = await get_economics(db)
    return payload["themes"]["metals"]


def _labels(section) -> list[str]:
    return [c["label"] for c in section["cards"]]


def _card_tickers(section) -> list[str]:
    """Which markets the section published, read back off the card's own ``val``.

    The published card has no id and no ticker, and its label truncates four
    different questions to "Gold price" — see ``_rungs``. The modal bracket is
    the only field that separates them, and each fixture owns a price decade.
    """
    decades = {base // 1000: ticker for ticker, base in _BASE_BY_TICKER.items()}
    return [
        decades[int(c["val"].replace("$", "").replace(",", "")) // 1000]
        for c in section["cards"]
    ]


# ---------------------------------------------------------------------------
# Non-vacuity — the fixtures reproduce the production defect
# ---------------------------------------------------------------------------


class TestTheDefectIsInTheSeed:
    """If the old rule already published these, nothing below tests anything."""

    def test_the_old_rule_deletes_exactly_the_five_production_deleted(self):
        deleted = {
            m.external_id.upper()
            for m in _metals_markets()
            if should_exclude_from_featured(
                m.name,
                m.llm_sport_category,
                m.status,
                _old_leader_prob(m.outcomes),
                FIXED_NOW,
            )
            == "probability_extreme"
        }
        assert deleted == _DELETED_TODAY

    def test_every_deleted_ladder_had_a_rung_in_the_live_band(self):
        """The 79% finding, on the specimens: these were never decided."""
        for m in _metals_markets():
            if m.external_id.upper() not in _DELETED_TODAY:
                continue
            live = [
                o for o in m.outcomes
                if o.current_probability is not None
                and 0.02 <= float(o.current_probability) <= 0.98
            ]
            assert live, m.external_id

    def test_the_biggest_metals_market_is_one_of_the_deleted(self):
        assert _BIGGEST in _DELETED_TODAY
        assert max(v for _, _, v, _, _, _ in _METALS) == 12225


# ---------------------------------------------------------------------------
# The helper
# ---------------------------------------------------------------------------


class TestTheLadderIsJudgedOnItsLiveRung:

    def test_a_wide_ladder_is_not_extreme(self):
        rungs = _rungs(50, 0.985, 0.505)
        outcomes = [_outcome(i, n, p) for i, (n, p) in enumerate(rungs)]

        assert is_probability_extreme(_old_leader_prob(outcomes)) is True
        assert is_probability_extreme(featured_leader_probability(_pairs(outcomes))) is False

    def test_the_value_returned_is_the_rung_nearest_even_money(self):
        pairs = [("Above $1", 0.99), ("Above $2", 0.62), ("Above $3", 0.03)]
        assert featured_leader_probability(pairs) == pytest.approx(0.62)

    def test_a_ladder_with_every_rung_decided_high_is_still_deleted(self):
        pairs = [("Above $1", 0.999), ("Above $2", 0.995), ("Above $3", 0.99)]
        assert is_probability_extreme(featured_leader_probability(pairs)) is True

    def test_a_ladder_with_every_rung_dead_low_is_still_deleted(self):
        pairs = [("Above $1", 0.012), ("Above $2", 0.008), ("Above $3", 0.001)]
        assert is_probability_extreme(featured_leader_probability(pairs)) is True

    def test_a_rung_exactly_on_the_bar_is_not_extreme(self):
        assert is_probability_extreme(
            featured_leader_probability([("Above $1", 0.999), ("Above $2", 0.98)])
        ) is False


class TestTheBinaryPathIsUnchanged:
    """The gate must still delete a question that really is over."""

    def test_a_binary_at_99_is_still_deleted(self):
        assert is_probability_extreme(
            featured_leader_probability([("Yes", 0.99), ("No", 0.01)])
        ) is True

    def test_a_multi_outcome_field_is_judged_on_its_leader(self):
        pairs = [("Alice", 0.991), ("Bob", 0.006), ("Carol", 0.003)]
        assert featured_leader_probability(pairs) == pytest.approx(0.991)
        assert is_probability_extreme(featured_leader_probability(pairs)) is True

    def test_one_stray_non_threshold_row_makes_it_not_a_ladder(self):
        """A ladder is ALL thresholds; the gate must not be talked out of its
        job by a pool that merely looks laddered."""
        pairs = [("Above $1", 0.995), ("Above $2", 0.55), ("Yes", 0.99)]
        assert outcome_names_are_cumulative_ladder([n for n, _ in pairs]) is False
        assert featured_leader_probability(pairs) == pytest.approx(0.995)

    def test_a_single_threshold_row_is_not_a_ladder(self):
        assert outcome_names_are_cumulative_ladder(["Above $1"]) is False

    @pytest.mark.parametrize(
        "pairs",
        [
            [],
            [("Yes", None), ("No", None)],
            [("Yes", 0.0), ("No", 0.0)],
            [("Yes", 0.55), ("No", None)],
            [("Alice", 0.4), ("Bob", 0.35), ("Carol", 0.25)],
            [("Yes", 0.999), ("No", 0.001)],
            [("Yes", 0.001), ("No", 0.999)],
        ],
    )
    def test_it_equals_the_closure_it_replaced_on_every_non_ladder(self, pairs):
        outcomes = [_outcome(i, n, p) for i, (n, p) in enumerate(pairs)]
        assert featured_leader_probability(_pairs(outcomes)) == _old_leader_prob(outcomes)

    def test_mixed_case_and_padding_still_read_as_thresholds(self):
        assert outcome_names_are_cumulative_ladder(["  AT LEAST 370", "At Least 380"]) is True


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTheMetalsSectionShowsTheMarketsPeopleTrade:

    async def test_the_four_cards_are_the_four_most_traded(self):
        metals = await _run(_metals_markets())
        assert _card_tickers(metals) == [
            "KXCOPPERMON-26SEP3017",  # 12,225 — deleted from the page before this ship
            "KXGOLDD-26SEP2117",      # 6,133
            "KXGOLDMON-26SEP3017",    # 4,078 — deleted before this ship
            "KXCOPPERD-26SEP2117",    # 3,363
        ]

    async def test_the_most_traded_metals_market_reaches_the_page(self):
        """The reader-visible claim. `KXCOPPERMON` is 50 rungs and the biggest
        book on the section; the gate deleted it for being wide."""
        metals = await _run(_metals_markets())
        biggest = next(m for m in _metals_markets() if m.external_id.upper() == _BIGGEST)

        assert _BIGGEST in _card_tickers(metals)
        assert len(biggest.outcomes) == 50
        card = metals["cards"][_card_tickers(metals).index(_BIGGEST)]
        assert card["src"] == "kalshi"
        assert card["prob"] is not None and card["brackets"]

    async def test_the_34_volume_ladder_does_not_take_a_card_slot(self):
        """Widening the gate without an order is how this one wins a slot: it
        is FIRST in the pool and, once admitted, is drawable like any other."""
        metals = await _run(_metals_markets())
        assert "KXSILVERW-26SEP2517" not in _card_tickers(metals)

    async def test_the_section_did_not_shrink(self):
        """The card cap was already binding, so this ship changes WHICH four
        are drawn, not how many. Stated so a later change cannot read the
        unchanged count as evidence that nothing happened."""
        metals = await _run(_metals_markets())
        assert len(metals["cards"]) == 4
        assert metals["count"] == len(metals["cards"]) + len(metals["markets"])

    async def test_shuffling_the_query_order_cannot_change_the_cards(self):
        """`_METALS` is in ascending volume, so heap order alone would put the
        12,225 ladder last. 12 shuffles of the same pool."""
        expected = _card_tickers(await _run(_metals_markets()))
        rng = random.Random(6704)
        for _ in range(12):
            pool = _metals_markets()
            rng.shuffle(pool)
            assert _card_tickers(await _run(pool)) == expected

    async def test_a_metals_market_that_really_is_over_stays_off_the_page(self):
        """Every rung at 99% IS a decided ladder, and the gate keeps deleting
        it — otherwise this ship is just a hole in the filter."""
        pool = _metals_markets()
        dead = _market(
            99,
            "KXGOLDDEAD-26SEP2117",
            "Gold price on September 21, 2026 at 5:00 PM EDT?",
            999_999,
            [("Above $1,000", 0.999), ("Above $1,100", 0.995), ("Above $1,200", 0.99)],
        )
        metals = await _run([dead] + pool)

        assert _card_tickers(metals) == _card_tickers(await _run(pool))
