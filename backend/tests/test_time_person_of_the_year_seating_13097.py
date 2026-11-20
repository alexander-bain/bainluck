"""#13097: TIME Person of the Year 2026 seating regression guards.

Verifies the real production Discover seating path
(``diversify_discover_first_page`` with default cold-start window +
``enforce_first_page_quality_floor``):

1. When a clean, non-boring, non-silent ``#13097`` fun-admitted card
   (``item["_fun_tags"]``) sits inside slots 1–10 solely lacking a ``why_now``
   phrase, ``enforce_first_page_quality_floor`` keeps slots 1–10 100% pure on
   ``why_now`` and steps the fun card into seat 11 (slots 11–20) instead of
   banishing it deep into ``new_tail[pick]`` (seats 26–45).
2. The card pushed off the last non-anchor slot of page 1 lands right at
   seat 21 (the front of the tail, preserving rank order across multiple
   steps), never deep into ``new_tail[pick]``.
3. Opening ten (seats 1–10) stays identical to master; boring or wholly silent
   fun-tagged cards still demote normally and never take the seat-11 step.
4. Calls through ``routes/feed.py``'s real seating imports with default
   arguments (never overriding ``cold_start_window`` by hand).
"""

from __future__ import annotations

from app.routes import feed as feed_route
from app.utils import feed_market_quality as fmq


def _card(
    mid: int,
    name: str,
    *,
    score: float,
    category: str = "tech",
    headline: str = "New favorite: Yes (62%)",
    reason: str = "New favorite: Yes (62%)",
    movement: float | None = 0.06,
    fun_tags: list[str] | None = None,
    anchor: bool = False,
) -> dict:
    item: dict = {
        "type": "futures",
        "score": score,
        "headline": headline,
        "context_summary": headline,
        "reason": reason,
        "data": {
            "id": mid,
            "name": name,
            "title": name,
            "llm_sport_category": category,
            "top_outcomes": [
                {"name": "Yes", "probability": 0.45, "movement": movement}
            ],
        },
    }
    if fun_tags:
        item["_fun_tags"] = list(fun_tags)
    if anchor:
        item["_is_anchor"] = True
    return item


def _find_seat(items: list[dict], mid: int) -> int:
    for idx, it in enumerate(items, 1):
        if (it.get("data") or {}).get("id") == mid:
            return idx
    raise AssertionError(f"Market {mid} missing from {len(items)} items")


def test_clean_fun_card_steps_to_seat_11_and_pushed_off_card_lands_at_seat_21():
    """Real production seating call (default cold-start window): TIME Person of
    the Year steps from opening ten to seat 11, slots 1–10 stay 100% why_now
    clean, and the card pushed off seat 20 lands right at seat 21 (not deep in
    the tail at pick=35)."""
    time_card = _card(
        27467306,
        "TIME Person of the Year 2026",
        score=88.0,
        category="entertainment",
        headline="James Talarico leads at 25%",
        reason="James Talarico leads at 25%",
        movement=None,
        fun_tags=["culture"],
    )

    cats = ["tech", "economics", "geopolitics", "weather", "politics", "hockey", "mma", "other"]
    pool: list[dict] = [time_card]
    # 8 why-now cards across all 8 non-entertainment categories so slots 1–10
    # hold TIME + why-now cards and slots 11–20 hold standing-leader cards
    # (exact live-feed shape where TIME steps to seat 11 and seat 20 is pushed
    # off to seat 21, never deep into the tail at seat 41).
    for i in range(8):
        pool.append(
            _card(
                1000 + i,
                f"Opening market {i}",
                score=90.0 - i * 0.5,
                category=cats[i % len(cats)],
                headline=f"New favorite: Option {i} (62%)",
                reason=f"New favorite: Option {i} (62%)",
                movement=0.05,
            )
        )
    for i in range(10):
        pool.append(
            _card(
                1500 + i,
                f"Page one standing market {i}",
                score=82.0 - i * 0.5,
                category=cats[i % len(cats)],
                headline=f"Contender {i} leads at 42%",
                reason=f"Contender {i} leads at 42%",
                movement=None,
            )
        )
    # 20 non-why_now tail cards BEFORE the first clean why_now replacement so
    # `pick` is deep in the tail (index 20 -> seat 41).
    for i in range(20):
        pool.append(
            _card(
                2000 + i,
                f"Standing tail market {i}",
                score=65.0 - i * 0.2,
                category=cats[i % len(cats)],
                headline=f"Option A leads at 55% ({i})",
                reason=f"Option A leads at 55% ({i})",
                movement=None,
            )
        )
    # Clean why_now replacements sitting deep in the tail (tail indices 20-21 -> seats 41-42).
    for r_idx in range(3):
        pool.append(
            _card(
                3001 + r_idx,
                f"Deep clean why-now replacement {r_idx}",
                score=58.0 - r_idx * 0.5,
                category=cats[r_idx % len(cats)],
                headline="New favorite: Yes (68%)",
                reason="New favorite: Yes (68%)",
                movement=0.09,
            )
        )

    # Call through the exact functions imported by routes/feed.py with defaults.
    diversified = feed_route.diversify_discover_first_page(pool, cold_start=True)
    pre_seat = _find_seat(diversified, 27467306)
    assert pre_seat <= 10, f"Expected TIME in opening ten before floor, got seat {pre_seat}"

    seat_20_before_id = diversified[19]["data"]["id"]

    seated, meta = feed_route.enforce_first_page_quality_floor(diversified)

    # 1. Total cardinality and exact element set preserved.
    assert len(seated) == len(diversified)
    assert {it["data"]["id"] for it in seated} == {it["data"]["id"] for it in diversified}
    assert meta["demoted"] >= 1

    # 2. Opening ten stays 100% why_now pure.
    for slot_idx in range(10):
        assert not fmq.lacks_a_why_now(seated[slot_idx]), f"Slot {slot_idx+1} lacks why_now"

    # 3. TIME steps cleanly to seat 11 (inside first 20), NOT deep in the tail.
    assert _find_seat(seated, 27467306) == 11

    # 4. The card displaced from seat 20 lands RIGHT AT SEAT 21 (index 20),
    # never dropped deep into the tail at seat 41.
    assert seated[20]["data"]["id"] == seat_20_before_id
    assert _find_seat(seated, seat_20_before_id) == 21


def test_boring_or_silent_fun_tagged_card_still_demotes_normally():
    """Only clean, non-boring, non-silent fun cards take the seat-11 step."""
    silent_fun = _card(
        4001,
        "Silent fun card",
        score=88.0,
        category="entertainment",
        headline="",
        reason="",
        movement=None,
        fun_tags=["culture"],
    )
    cats = ["tech", "economics", "geopolitics", "weather", "politics", "hockey", "mma", "other"]
    items = [silent_fun] + [
        _card(
            4100 + i,
            f"Clean card {i}",
            score=85.0 - i * 0.3,
            category=cats[i % len(cats)],
            headline=f"New favorite: Option {i} (64%)",
            reason=f"New favorite: Option {i} (64%)",
            movement=0.06,
        )
        for i in range(25)
    ]

    seated, _ = fmq.enforce_first_page_quality_floor(items)
    assert _find_seat(seated, 4001) > 20
