"""#4170 — a question the strict pool already serves is not dealt again by the broaden merge.

THE SPECIMEN, production 2026-09-24 ~00:30Z, ``bainluck.com/categories/economics``
at 390px (``GET /api/feed?category=economics``, cards 2 and 3 of the payload):

    card 1  Will OpenAI or Anthropic IPO first?   kalshi 108231      Anthropic 91%
    card 5  Will Anthropic or OpenAI IPO first?   polymarket 115417  Anthropic 95%

One question, two cards, two numbers. ``is_same_question`` pairs the titles and
#6400's ``fold_same_question_cards`` runs on every futures pool — so why both?

``/api/admin/discover-quality/trace`` for each: 108231 is strict-INELIGIBLE
(``stale_no_movement``, 4.64 days, under the relaxed 7-day window), 115417 is
strict-eligible. The category pool is thin (< ``_THIN_FUTURES_POOL_FLOOR``), so
#1090's broaden merge fires, and it added every broadened card whose market ID
the strict pool lacked. Each pool had been folded on its own; the twin straddled
the two, and a different id is all the merge asked.
"""

import inspect

from app.routes import feed as feed_mod
from app.routes.feed import _merge_broadened_futures
from tests.test_feed_same_question_duplicate_cards_6400 import _card

KALSHI_IPO = "Will OpenAI or Anthropic IPO first?"
POLY_IPO = "Will Anthropic or OpenAI IPO first?"


def _poly_ipo(score: float = 95) -> dict:
    return _card(115417, POLY_IPO, source="polymarket", score=score,
                 category="economics", resolution_date="2027-12-31T00:00:00+00:00")


def _kalshi_ipo(score: float = 95) -> dict:
    return _card(108231, KALSHI_IPO, source="kalshi", score=score,
                 category="economics", resolution_date="2039-12-31T00:00:00+00:00")


def _ids(items: list[dict]) -> list[int]:
    return [i["data"]["id"] for i in items]


def test_the_stale_twin_of_a_strict_card_is_not_added():
    # The relaxed pool is a superset of the strict one, so it carries BOTH rows.
    primary = [_poly_ipo()]
    broadened = [_kalshi_ipo(), _poly_ipo()]

    merged, added = _merge_broadened_futures(primary, broadened)

    assert _ids(merged) == [115417]
    assert added == []


def test_the_strict_card_survives_even_when_its_twin_scores_higher():
    """Survivor rule: the card still moving beats the one the strict window
    refused as stale, whatever the relaxed pass scored it."""
    merged, _ = _merge_broadened_futures([_poly_ipo(score=60)], [_kalshi_ipo(score=98)])

    assert _ids(merged) == [115417]


def test_a_broadened_card_asking_a_different_question_is_still_added():
    """Control: the merge exists for recall on a thin page and must keep it."""
    other = _card(60760395, "Argentina Monthly Inflation - September",
                  source="polymarket", score=70, category="economics")

    merged, added = _merge_broadened_futures([_poly_ipo()], [_kalshi_ipo(), other])

    assert _ids(merged) == [115417, 60760395]
    assert _ids(added) == [60760395]


def test_two_listings_from_one_venue_are_not_folded():
    """Control: the fold needs two venues. One venue's two markets are its own
    distinct listings, whatever their titles."""
    same_venue = _card(108232, KALSHI_IPO, source="polymarket", score=90,
                       category="economics")
    primary = [_poly_ipo()]

    merged, _ = _merge_broadened_futures(primary, [same_venue])

    assert _ids(merged) == [115417, 108232]


def test_the_mens_and_womens_draw_stay_two_cards_across_the_pools():
    """#4479's control, straddling the pools the way the specimen did."""
    mens = _card(1, "US Open Men's Singles Winner", source="kalshi", score=80,
                 category="tennis")
    womens = _card(2, "US Open Women's Singles Winner", source="polymarket",
                   score=80, category="tennis")

    merged, added = _merge_broadened_futures([mens], [womens])

    assert _ids(merged) == [1, 2]
    assert _ids(added) == [2]


def test_nothing_new_returns_the_strict_pool_unchanged():
    primary = [_poly_ipo()]

    merged, added = _merge_broadened_futures(primary, list(primary))

    assert merged is primary
    assert added == []


def test_the_route_merges_through_the_helper():
    """Source guard: the id-only merge is gone from ``get_feed``; a revert to it
    re-opens the specimen on every thin page."""
    src = inspect.getsource(feed_mod.get_feed)

    assert "_merge_broadened_futures(" in src
    assert "not in seen_ids" not in src
