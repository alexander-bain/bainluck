"""UX-1035 / #2709 — the "Live Now" rail is a promise about every live match.

``/sports`` builds its "Live Now · N" heading by sectioning whatever the FIRST
PAGE returned. The page is 20 items, ranked by score, so the heading really says
"live items in the top 20" and prints it as if it said "live". On the banked
production payload beside this file — nine US Open matches in play — the number
was **6** while **14** games were in progress.

The fix is a projection, not a bigger page: ``GET /api/feed?live_only=true``
returns the live slice of the SAME ranked build, so the rail can be sourced from
all of it while first paint stays bounded at 20 (L2-240 / LAT-P171).

The counts asserted here are also asserted, against the same file, by
``frontend/__tests__/lib/liveRailParity2709.test.ts`` running the real
TypeScript sectioner. Neither test reimplements the other's predicate — they
meet on a number and a banked payload, so a drift in either language fails one
of them.
"""

import json
from pathlib import Path

import pytest

from app.utils.feed_cache import render_feed_page_from_base
from app.utils.feed_live_section import feed_item_is_live, filter_live_items

FIXTURE = Path(__file__).parent / "fixtures" / "sports_feed_live_rail_2709.json"

# 🔴 THESE THREE NUMBERS ARE THE BUG, WRITTEN DOWN.
#     83 ranked items, 14 of them live, 6 of those inside the 20-item page the
#     rail was built from. The gap 14 - 6 = 8 is what a reader could not see.
BANKED_TOTAL = 83
BANKED_LIVE = 14
BANKED_LIVE_IN_FIRST_PAGE = 6
PAGE_LIMIT = 20


@pytest.fixture(scope="module")
def banked() -> dict:
    return json.loads(FIXTURE.read_text())["payload"]


# ---------------------------------------------------------------------------
# A. The population — that the fixture still shows the defect it was banked for
# ---------------------------------------------------------------------------


def test_the_banked_payload_is_the_one_the_defect_was_measured_on(banked):
    """A fixture that quietly changed shape would make every assertion below
    true of something else. Pin what it IS before asserting what it means."""
    assert len(banked["items"]) == BANKED_TOTAL
    assert banked["total"] == BANKED_TOTAL


def test_the_first_page_cannot_see_most_of_the_live_games(banked):
    """🔴 THE DEFECT. This is the arithmetic the rail was doing, and it is here
    so the fix cannot be read as a refactor of something that already worked."""
    items = banked["items"]
    live_everywhere = filter_live_items(items)
    live_on_page_one = filter_live_items(items[:PAGE_LIMIT])

    assert len(live_everywhere) == BANKED_LIVE
    assert len(live_on_page_one) == BANKED_LIVE_IN_FIRST_PAGE
    assert len(live_everywhere) > len(live_on_page_one), (
        "the fixture no longer reproduces #2709 — re-bank it against a payload "
        "with live games below the first page, or this suite proves nothing"
    )


def test_the_hidden_live_games_were_the_tennis(banked):
    """The user-visible half of the same fact: the rail showed no US Open match
    while six courts were mid-match. Named players, so a future reader can see
    which cards the number was about."""
    hidden = filter_live_items(banked["items"][PAGE_LIMIT:])
    names = {
        f"{i['data'].get('home_team')} vs {i['data'].get('away_team')}"
        for i in hidden
        if i.get("type") == "event"
    }
    assert "Denis Shapovalov vs Luca Van Assche" in names
    assert "Matteo Berrettini vs Mariano Navone" in names
    assert "Lloyd Harris vs Stefanos Tsitsipas" in names
    assert len(names) >= 8


# ---------------------------------------------------------------------------
# B. The predicate
# ---------------------------------------------------------------------------


def test_a_futures_card_is_never_live_however_its_price_moves():
    """Refused BY TYPE, before ``status`` is even read. A futures market has no
    phase of its own; inferring one from its price is the doctrine violation
    #2711 is about, and this is the place it must not enter the rail."""
    assert not feed_item_is_live({"type": "futures", "data": {"status": "live"}})
    assert not feed_item_is_live({"type": "bundle", "data": {"status": "live"}})


def test_a_tournament_carries_its_phase_under_a_different_key():
    """``tournament`` items use ``schedule_status``; everything else uses
    ``status``. Reading only one of the two is how a whole card type goes
    missing from a rail that claims to hold all of them."""
    assert feed_item_is_live(
        {"type": "tournament", "data": {"schedule_status": "in-progress"}}
    )
    assert not feed_item_is_live(
        {"type": "tournament", "data": {"schedule_status": "scheduled"}}
    )


def test_a_concept_card_is_live_by_its_own_status():
    assert feed_item_is_live({"type": "concept", "data": {"status": "live"}})
    assert not feed_item_is_live({"type": "concept", "data": {"status": "upcoming"}})


@pytest.mark.parametrize(
    "item",
    [
        None,
        "live",
        {},
        {"type": "event"},
        {"type": "event", "data": None},
        {"type": "event", "data": {}},
        {"type": "event", "data": {"status": None}},
    ],
)
def test_an_unreadable_phase_is_not_a_live_one(item):
    """Over-claiming is the bug being fixed, so the unknown case falls the
    conservative way. A card whose shape this cannot read stays out of a rail
    that promises to be complete."""
    assert feed_item_is_live(item) is False


def test_the_projection_keeps_the_builds_own_order(banked):
    """A filter that re-sorted would be a second opinion about score that
    nothing asked for — and the rail would disagree with the list under it."""
    items = banked["items"]
    live = filter_live_items(items)
    positions = [items.index(i) for i in live]
    assert positions == sorted(positions)


def test_filter_live_items_refuses_a_non_list():
    assert filter_live_items(None) == []
    assert filter_live_items({"items": []}) == []


# ---------------------------------------------------------------------------
# C. The serve — the projection off the stored page base
# ---------------------------------------------------------------------------


def _base(banked: dict) -> dict:
    return {"items": banked["items"], "total": len(banked["items"])}


def test_live_only_off_the_base_returns_every_live_game(banked):
    """🟢 THE FIX, at the tier that actually serves it. One stored base, two
    projections: the scroll takes a window, the rail takes the live sub-list."""
    page = render_feed_page_from_base(
        _base(banked), limit=50, offset=0, live_only=True
    )
    assert len(page["items"]) == BANKED_LIVE
    assert page["total"] == BANKED_LIVE
    assert all(feed_item_is_live(i) for i in page["items"])


def test_the_default_projection_is_byte_for_byte_what_it_always_was(banked):
    """The control. ``live_only`` defaults False and every existing caller must
    get the identical page — this fix is not licensed to move the scroll."""
    base = _base(banked)
    before = render_feed_page_from_base(base, limit=20, offset=0)
    after = render_feed_page_from_base(base, limit=20, offset=0, live_only=False)
    assert before == after
    assert before["total"] == BANKED_TOTAL
    assert len(before["items"]) == 20


def test_has_more_describes_the_list_the_caller_is_actually_paging(banked):
    """``total`` and ``has_more`` are about the LIVE list once it is the list
    being served. Reporting the ranked total here would tell a live-rail client
    there were 63 more live games to fetch."""
    page = render_feed_page_from_base(
        _base(banked), limit=10, offset=0, live_only=True
    )
    assert page["total"] == BANKED_LIVE
    assert page["has_more"] is True

    tail = render_feed_page_from_base(
        _base(banked), limit=10, offset=10, live_only=True
    )
    assert tail["has_more"] is False
    assert len(tail["items"]) == BANKED_LIVE - 10


def test_the_integrity_check_runs_on_the_base_not_the_projection(banked):
    """``len(items) != total`` means a truncated or half-written blob and must
    fail closed. Checking it AFTER the filter would make every live_only read
    of a healthy base look corrupt, silently disabling the page base."""
    truncated = {"items": banked["items"][:10], "total": BANKED_TOTAL}
    assert (
        render_feed_page_from_base(truncated, limit=50, offset=0, live_only=True)
        is None
    )
    healthy = _base(banked)
    assert (
        render_feed_page_from_base(healthy, limit=50, offset=0, live_only=True)
        is not None
    )


# ---------------------------------------------------------------------------
# D. The key — one base, two responses
# ---------------------------------------------------------------------------


def test_the_live_rail_and_the_scroll_read_the_same_stored_base():
    """The whole reason ``live_only`` is excluded from the base key. If these
    differed, the rail would trigger a second full build of a list the scroll
    had already built."""
    from app.utils.feed_cache import feed_page_base_cache_key

    assert "live_only" not in feed_page_base_cache_key.__code__.co_varnames
    assert feed_page_base_cache_key(limit=20, mode="sports") == (
        feed_page_base_cache_key(limit=20, mode="sports")
    )


def test_the_live_rail_gets_its_own_response_key():
    """...and the whole reason it IS in the response key. Same base, different
    body: sharing a response entry would serve the rail to the scroll."""
    from app.utils.feed_cache import feed_response_cache_key

    scroll = feed_response_cache_key(limit=20, offset=0, mode="sports")
    rail = feed_response_cache_key(
        limit=20, offset=0, mode="sports", live_only=True
    )
    assert scroll != rail


def test_shipping_this_does_not_cold_start_the_warm_feed():
    """🔴 The non-live key must hash the BYTE-IDENTICAL string it hashed before
    this parameter existed, or the deploy invalidates every warm feed key on the
    site at once. Pinned as a literal digest, because "the default is False" is
    a statement about the signature and this is a statement about the bytes."""
    import hashlib

    from app.utils.feed_cache import (
        FEED_RESPONSE_CACHE_PREFIX,
        feed_response_cache_key,
    )

    legacy_parts = (
        "feed:anon:all:20:0:True:True::0.15:False:sports"
    )
    legacy = (
        f"{FEED_RESPONSE_CACHE_PREFIX}:"
        f"{hashlib.md5(legacy_parts.encode()).hexdigest()}"
    )
    assert (
        feed_response_cache_key(
            limit=20, offset=0, event_pct=0.15, mode="sports"
        )
        == legacy
    )
    assert (
        feed_response_cache_key(
            limit=20, offset=0, event_pct=0.15, mode="sports", live_only=False
        )
        == legacy
    )


def test_a_category_live_rail_collides_with_neither_single_prefix():
    """Two composable prefixes need a fixed order, or `cat=..|live=1|..` and
    `live=1|cat=..|..` become two names for one page."""
    from app.utils.feed_cache import feed_response_cache_key

    keys = {
        feed_response_cache_key(limit=20, offset=0),
        feed_response_cache_key(limit=20, offset=0, category="tennis"),
        feed_response_cache_key(limit=20, offset=0, live_only=True),
        feed_response_cache_key(
            limit=20, offset=0, category="tennis", live_only=True
        ),
    }
    assert len(keys) == 4
