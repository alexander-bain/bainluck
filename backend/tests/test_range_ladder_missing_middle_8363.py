"""#8363 — a range ladder held with its middle missing never reaches Discover.

Production 2026-09-24 06:26Z, card 9 of the 390px Discover page:
`"Resident Evil" 2nd Weekend Box Office` drew `<26m 57%` / `32m+ 43%` and
"More likely than not: <26m". Polymarket (event 1071223) lists FOUR ranges —
<26m, 26-29m, 29-32m, 32m+ — and we held the two with a trade (.66 and .50),
so the reader was told $26-32m is 0% and the one-winner divisor inflated the
pair to fill the missing mass.

The rule: holding BOTH ends of a ladder but fewer legs than the venue lists
means every missing leg is in the middle. The unit arms are the served feed's
own names (GET /api/feed?limit=250, 06:40Z): the specimen fires, the 21 other
served neg-risk markets holding fewer legs than the venue do not.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.routes.feed import _score_futures
from app.utils.feed_market_quality import range_ladder_missing_middle
from app.utils.personalization import PersonalizationContext

from tests.test_feed_score_futures_resilience import _Market, _Outcome, _mock_db


# ── the rule, on production names ────────────────────────────────────────────


def test_the_specimen_fires():
    assert range_ladder_missing_middle(["32m+", "<26m"], 4) is True


def test_every_end_shape_is_read():
    # Off-feed rows of the same census (ADARx IPO 3/8, US Tornadoes 3/5,
    # a lowest-temperature ladder written with words).
    assert range_ladder_missing_middle(["$1.5B-$1.75B", "$3B+", "<$1.5B"], 8)
    assert range_ladder_missing_middle(["50 - 74", "125 or more", "Under 25"], 5)
    assert range_ladder_missing_middle(["47°F or below", "56-57°F", "68°F or higher"], 11)


def test_a_complete_ladder_does_not_fire():
    assert range_ladder_missing_middle(["<26m", "26-29m", "29-32m", "32m+"], 4) is False


def test_a_ladder_missing_only_a_tail_does_not_fire():
    # Served at 06:40Z: MrBeast day-6 views, 5 of 7, bottom end only — the
    # missing legs cannot be located, so no claim.
    names = ["64-65M", "65-66M", "63-64M", "62-63M", "<62M"]
    assert range_ladder_missing_middle(names, 7) is False


def test_a_candidate_race_with_unheld_longshots_does_not_fire():
    # Served at 06:40Z: Worlds 2026 16 of 20, Group D1 3 of 6 — no range ends.
    assert range_ladder_missing_middle(["Gen.G", "T1", "Bilibili Gaming"], 20) is False
    assert range_ladder_missing_middle(["Malta", "Gibraltar", "Andorra"], 6) is False


def test_no_readable_venue_count_makes_no_claim():
    for count in (None, "", "four", {}):
        assert range_ladder_missing_middle(["<26m", "32m+"], count) is False
    # JSONB can carry the count as a string; a real number still reads.
    assert range_ladder_missing_middle(["<26m", "32m+"], "4") is True


def test_blank_names_are_not_legs():
    assert range_ladder_missing_middle(["<26m", None, "", "32m+"], 3) is True
    assert range_ladder_missing_middle(["<26m", None, "32m+"], 2) is False


# ── the route: the card leaves, its control stays ────────────────────────────


def _box_office(id: int, market_count: int) -> _Market:
    m = _Market(id)
    m.name = '"Resident Evil" 2nd Weekend Box Office'
    m.category = m.llm_sport_category = "entertainment"
    m.market_metadata = {"neg_risk": True, "market_count": market_count}
    m.outcomes = [
        _Outcome(10 * id + 1, "<26m", 0.66, change=0.05, opening=0.55),
        _Outcome(10 * id + 2, "32m+", 0.50, change=-0.05, opening=0.45),
    ]
    return m


async def _served_ids(markets) -> set:
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
        items = await _score_futures(
            _mock_db(markets), datetime.now(timezone.utc), None, PersonalizationContext()
        )
    return {i["data"]["id"] for i in items if i["type"] == "futures"}


@pytest.mark.asyncio
async def test_the_gapped_ladder_leaves_discover():
    assert 7 not in await _served_ids([_box_office(7, market_count=4)])


@pytest.mark.asyncio
async def test_the_same_card_held_whole_is_served():
    # CONTROL: identical legs, and the venue lists exactly these two. If this
    # card were refused for any other reason the treatment above would pass
    # without the rule, so it must be served.
    assert 8 in await _served_ids([_box_office(8, market_count=2)])


@pytest.mark.asyncio
async def test_one_gapped_ladder_does_not_take_its_neighbours():
    served = await _served_ids([_box_office(7, market_count=4), _Market(1)])
    assert served == {1}
