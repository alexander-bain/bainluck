"""#9877 — the broaden merge gives a story only the room the strict pool left.

THE SPECIMEN, production 2026-10-01 03:20Z, ``GET /api/feed?limit=40`` (cache
``disabled``, main release v5363 carrying #9877's story key ``d8032fa0ee``):

    slot 8  Brazil Presidential election winner?             kalshi 109952
    slot 9  Brazil Presidential Election First Round Winner  polymarket 59934255

Both carry ``story:brazil_presidential_election``, whose cap is 1, so the key was
right and the cap was right, and the page still had two. Why both?

``/api/admin/discover-quality/trace`` for each: 109952 is strict-INELIGIBLE
(``stale_no_movement``, 2.61 days), 59934255 is strict-eligible. So the Kalshi
card can only have come from #1090's relaxed pool through
``_merge_broadened_futures``. Each pool runs ``diversify_quality_families`` on
its own: the strict pool, which never saw 109952, kept 59934255; the relaxed
pool kept 109952. The merge added every broadened card whose id the strict pool
lacked, and folded only same-question twins (#4170). A winner market and a
first-round market are two questions, so nothing stopped the second card.
"""

from app.routes.feed import _merge_broadened_futures
from app.utils.feed_market_quality import (
    classify_market_quality,
    diversify_quality_families,
)

# (market id, source, name, persisted story_key) — production rows, 2026-09-30.
FIRST_ROUND = (
    59934255,
    "polymarket",
    "Brazil Presidential Election First Round Winner",
    None,
)
WINNER_KALSHI = (
    109952,
    "kalshi",
    "Brazil Presidential election winner?",
    "story:brazil_presidential_election_winner",
)
FRANCE = (
    113364,
    "polymarket",
    "Next French Presidential Election",
    "story:next-french-presidential-election",
)


def _item(row, score: float) -> dict:
    market_id, source, name, persisted = row
    quality = classify_market_quality(name, "politics", persisted_story_key=persisted)
    return {
        "type": "futures",
        "score": score,
        "_quality_class": quality.quality_class,
        "_quality_family_key": quality.family_key,
        "_quality_story_key": quality.story_key,
        "data": {"id": market_id, "name": name, "source": source},
    }


def _ids(items: list[dict]) -> list[int]:
    return [i["data"]["id"] for i in items]


def _pools() -> tuple[list[dict], list[dict]]:
    """The two pools exactly as each pass capped them on production."""
    first_round = _item(FIRST_ROUND, 95)
    winner = _item(WINNER_KALSHI, 98)
    strict = diversify_quality_families([first_round])
    # The relaxed pool is a superset of the strict one; its cap kept the Kalshi
    # card, the higher of the two there.
    relaxed = diversify_quality_families([winner, first_round])
    assert _ids(relaxed) == [109952], "fixture no longer reproduces the relaxed pool"
    return strict, relaxed


def test_the_specimen_rows_share_one_capped_story():
    first_round = _item(FIRST_ROUND, 95)
    winner = _item(WINNER_KALSHI, 98)
    assert first_round["_quality_story_key"] == "story:brazil_presidential_election"
    assert winner["_quality_story_key"] == "story:brazil_presidential_election"
    # Two questions, so #4170's same-question fold rightly does not apply.
    assert first_round["_quality_family_key"] != winner["_quality_family_key"]


def test_one_brazil_race_is_one_card_after_the_merge():
    strict, relaxed = _pools()

    merged, added = _merge_broadened_futures(strict, relaxed)

    assert _ids(merged) == [59934255]
    assert added == []


def test_the_strict_card_keeps_the_slot_even_when_the_relaxed_one_scores_higher():
    """#4170's survivor rule carries over: the card the strict window still
    admits beats the one it refused as stale."""
    strict, relaxed = _pools()
    assert relaxed[0]["score"] > strict[0]["score"]

    merged, _ = _merge_broadened_futures(strict, relaxed)

    assert _ids(merged) == [59934255]


def test_a_different_race_from_the_relaxed_pool_is_still_added():
    """Control: the merge exists for recall on a thin page and must keep it."""
    strict, _ = _pools()
    france = _item(FRANCE, 80)

    merged, added = _merge_broadened_futures(strict, [_item(WINNER_KALSHI, 98), france])

    assert _ids(merged) == [59934255, 113364]
    assert _ids(added) == [113364]


def test_a_story_with_room_left_still_takes_relaxed_cards_up_to_its_cap():
    """Control: the seed spends the strict pool's share, not the whole cap.
    `story:russia_ukraine` is capped at 2; one strict card leaves one seat."""

    def ru(market_id: int, name: str, score: float) -> dict:
        return {
            "type": "futures",
            "score": score,
            "_quality_family_key": name.lower(),
            "_quality_story_key": "story:russia_ukraine",
            "data": {"id": market_id, "name": name, "source": "kalshi"},
        }

    strict = [ru(1, "Russia x Ukraine ceasefire in 2026?", 90)]
    relaxed = [
        ru(2, "Will Putin meet Zelenskyy?", 85),
        ru(3, "Will Russia capture Kostyantynivka?", 80),
    ]

    merged, added = _merge_broadened_futures(strict, relaxed)

    assert _ids(merged) == [1, 2]
    assert _ids(added) == [2]


def test_the_same_wording_across_the_pools_is_one_card():
    """The exact-family cap is seeded too: one wording, one card."""
    strict = [
        {
            "type": "futures",
            "score": 90,
            "_quality_family_key": "fed decision in october",
            "data": {"id": 11, "name": "Fed decision in October", "source": "kalshi"},
        }
    ]
    relaxed = [
        {
            "type": "futures",
            "score": 95,
            "_quality_family_key": "fed decision in october",
            "data": {"id": 12, "name": "Fed decision in October", "source": "kalshi"},
        }
    ]

    merged, _ = _merge_broadened_futures(strict, relaxed)

    assert _ids(merged) == [11]


def test_already_kept_is_counted_but_never_returned():
    first_round = _item(FIRST_ROUND, 95)
    france = _item(FRANCE, 80)

    out = diversify_quality_families(
        [_item(WINNER_KALSHI, 98), france], already_kept=[first_round]
    )

    assert _ids(out) == [113364]


def test_without_a_seed_diversify_is_unchanged():
    out = diversify_quality_families([_item(WINNER_KALSHI, 98), _item(FIRST_ROUND, 95)])

    assert _ids(out) == [109952]
