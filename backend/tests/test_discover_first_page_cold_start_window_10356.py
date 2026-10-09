"""#10356 / #5105 — the cold-start first-page window, served vs the offline arm.

The r4 production capture (e93246d2…, 2026-10-04) opened an anonymous Discover
page with cards scored 25–51 (Buffalo snow, NASCAR, ATP Beijing, two esports
winners, two low-quality foreign rows) while cards scored 93–98 waited below
it. The cause is the cold-start cap's bound: it holds until all eight category
groups have been seen, and the single forward walk never returns to a card the
temporary cap refused. The offline arm (``COLD_START_WINDOW_FIRST_CARDS``)
bounds it to the first 8 cards, as #850's docstring says, and walks again from
the top when the window closes.

The default must stay the served behaviour — production passes nothing — so the
served pin below is a pin of today's ordering, not an endorsement of it.

Archetypes are held unique per card so the archetype caps and the required-
archetype fills cannot move anything: what is under test is the category
window alone.
"""

from __future__ import annotations

import pytest

from app.utils import feed_market_quality as fmq
from app.utils.feed_market_quality import (
    COLD_START_WINDOW_FIRST_CARDS,
    COLD_START_WINDOW_SERVED,
    _discover_category_group,
    diversify_discover_first_page,
)


@pytest.fixture(autouse=True)
def _unique_archetypes(monkeypatch):
    monkeypatch.setattr(
        fmq, "_discover_archetype_group", lambda item: f"a{item['data']['id']}"
    )


def _card(card_id: str, category: str, score: float) -> dict:
    return {
        "type": "futures",
        "score": score,
        "data": {"id": card_id, "name": card_id, "llm_sport_category": category},
    }


# Rank order, as the chain hands it over. Seven groups are strong; the eighth
# ("other": esports, motorsports) only appears among the weak tail, which is
# what keeps the served cap tight past the strong cards.
STRONG = [
    _card("P1", "politics", 98),
    _card("P2", "politics", 97),
    _card("S1", "baseball", 96),
    _card("S2", "football", 95),
    _card("P3", "politics", 95),
    _card("P4", "politics", 94),
    _card("S3", "hockey", 93),
    _card("E1", "economics", 92),
    _card("E2", "economics", 91),
    _card("T1", "tech", 90),
    _card("N1", "entertainment", 89),
    _card("G1", "geopolitics", 88),
    _card("W1", "weather", 85),
]
WEAK = [
    _card("O1", "esports", 40),
    _card("O2", "motorsports", 38),
    _card("W2", "weather", 36),
    _card("L1", "politics", 34),
    _card("L2", "politics", 33),
    _card("L3", "politics", 32),
    _card("L4", "economics", 31),
    _card("L5", "economics", 30),
    _card("L6", "tech", 29),
    _card("L7", "entertainment", 28),
    _card("O3", "esports", 27),
]
POOL = STRONG + WEAK


def _ids(items):
    return [item["data"]["id"] for item in items]


def _run(window, *, cold_start=True, pool=POOL):
    return diversify_discover_first_page(
        [dict(item) for item in pool],
        first_page_size=20,
        cold_start=cold_start,
        cold_start_window=window,
    )


def test_the_default_is_the_served_window():
    default = diversify_discover_first_page(
        [dict(item) for item in POOL], first_page_size=20, cold_start=True
    )
    assert _ids(default) == _ids(_run(COLD_START_WINDOW_SERVED))


def test_served_window_seats_the_weak_tail_over_stronger_refused_cards():
    """The r4 shape, pinned as served. P3/P4/S3 (93–95) are refused by the
    temporary cap of 2; the walk never returns to them, and ten cards scored
    27–40 fill the page instead."""
    page = _ids(_run(COLD_START_WINDOW_SERVED)[:20])
    assert {"P3", "P4", "S3"}.isdisjoint(page)
    assert set(_ids(WEAK)) - {"O3"} <= set(page)


def test_first_cards_window_lets_the_stronger_refused_cards_win():
    page = _ids(_run(COLD_START_WINDOW_FIRST_CARDS)[:20])
    assert {"P3", "P4", "S3"} <= set(page)
    # Every strong card reaches the page; the weak tail only fills what is left.
    assert set(_ids(STRONG)) <= set(page)
    weak_seated = [card_id for card_id in page if card_id in set(_ids(WEAK))]
    assert len(weak_seated) == 20 - len(STRONG)


def test_first_cards_window_still_shapes_the_first_eight_cards():
    """The cold-start promise (#850) is kept: no group past 2 in the first 8."""
    first8 = _run(COLD_START_WINDOW_FIRST_CARDS)[:8]
    groups = [_discover_category_group(item) for item in first8]
    assert max(groups.count(group) for group in set(groups)) <= 2
    assert len(set(groups)) >= 5


def test_first_cards_window_keeps_the_ordinary_caps_after_the_window():
    page = _run(COLD_START_WINDOW_FIRST_CARDS)[:20]
    groups = [_discover_category_group(item) for item in page]
    for group, cap in fmq._DISCOVER_FIRST_PAGE_CATEGORY_CAPS.items():
        assert groups.count(group) <= cap, group


@pytest.mark.parametrize("window", sorted(fmq.COLD_START_WINDOWS))
def test_every_window_returns_the_same_cards_once(window):
    """A reorder, never a deletion or a duplicate — the whole deck survives."""
    out = _run(window)
    assert sorted(_ids(out)) == sorted(_ids(POOL))


def test_the_window_only_matters_on_a_cold_start():
    assert _ids(_run(COLD_START_WINDOW_FIRST_CARDS, cold_start=False)) == _ids(
        _run(COLD_START_WINDOW_SERVED, cold_start=False)
    )


def test_a_pool_that_never_closes_the_window_is_unchanged():
    """Fewer than eight cards selectable: no rewalk, both windows agree."""
    small = POOL[:6]
    assert _ids(_run(COLD_START_WINDOW_FIRST_CARDS, pool=small)) == _ids(
        _run(COLD_START_WINDOW_SERVED, pool=small)
    )


def test_an_unknown_window_is_refused():
    with pytest.raises(ValueError):
        _run("first_eight")
