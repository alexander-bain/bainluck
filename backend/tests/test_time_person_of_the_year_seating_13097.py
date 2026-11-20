"""#13097 — TIME Person of the Year seating guards (new reader first 20).

Two seating passes previously pushed TIME Person of the Year 2026 (27467306,
score 85-88) from seat 9 down to seats 38-45 for a new (cold-start) reader:

1. `diversify_discover_first_page(cold_start=True)` kept `COLD_START_WINDOW_SERVED`
   (`len(category_counts) < 8`), holding entertainment at cap=2 across all 20
   seats instead of releasing after 8 cards, while two weekly Netflix movie
   charts (US + global) consumed both slots.
2. `enforce_first_page_quality_floor(why_now_window=10)` evicted clean,
   fun-admitted standing-race cards from slots 0..9 directly into `new_tail[pick]`
   (seats 38-45 behind lower-scored cards and spliced roundups) even though they
   are legal and clean at slots 10..19.
"""

from __future__ import annotations

from app.utils.feed_market_quality import (
    COLD_START_WINDOW_FIRST_CARDS,
    FIRST_PAGE_WHY_NOW_WINDOW,
    diversify_discover_first_page,
    enforce_first_page_quality_floor,
)


def _futures(
    mid: int,
    name: str,
    *,
    score: int,
    category: str = "entertainment",
    headline: str = "James Talarico leads at 25%",
    reason: str | None = None,
    context: str | None = None,
    fun_tags: list[str] | None = None,
) -> dict:
    item: dict = {
        "type": "futures",
        "score": score,
        "headline": headline,
        "reason": reason or f"{name}: {headline}",
        "context_summary": context or headline,
        "data": {
            "id": mid,
            "name": name,
            "llm_sport_category": category,
            "hook_description": None,
            "status": "open",
        },
    }
    if fun_tags:
        item["_fun_tags"] = list(fun_tags)
    return item


def _why_now_card(mid: int, name: str, *, score: int, category: str) -> dict:
    return _futures(
        mid,
        name,
        score=score,
        category=category,
        headline="Down 8 points since Feb 18",
        reason=f"{name}: down 8 points since Feb 18",
        context="Down 8 points since Feb 18",
    )


def test_cold_start_first_cards_and_weekly_netflix_cap_seat_time_in_first_20():
    """6:58 PM scenario: two weekly Netflix movie cards (88, 88) + Katy Perry (87)
    sit ahead of TIME Person of the Year (85) for a cold-start new reader.
    With COLD_START_WINDOW_FIRST_CARDS + weekly Netflix cap=1 + entertainment cap=4,
    TIME reaches page 1 cleanly."""
    time_card = _futures(
        27467306,
        "TIME Person of the Year 2026",
        score=85,
        category="entertainment",
        fun_tags=["year-end", "pope-leo-xiv"],
    )
    netflix_us = _futures(
        71058525,
        "What will be the top US Netflix movie this week? (May 24)",
        score=88,
        category="entertainment",
        headline="Resolving soon: Guarding Stars leads at 59%",
    )
    netflix_global = _futures(
        71058521,
        "What will be the top global Netflix movie this week? (May 24)",
        score=88,
        category="entertainment",
        headline="Resolving soon: Guarding Stars leads at 85%",
    )
    katy_perry = _why_now_card(
        113658,
        "Katy Perry and Justin Trudeau engaged by end of 2025?",
        score=87,
        category="entertainment",
    )

    pool = [
        _why_now_card(1, "Middle East", score=95, category="politics"),
        _why_now_card(2, "Russia-Ukraine", score=94, category="geopolitics"),
        _why_now_card(3, "Fed & Rates", score=92, category="economics"),
        _why_now_card(4, "GPT Astra", score=91, category="tech"),
        _why_now_card(5, "Super Bowl", score=90, category="football"),
        netflix_us,
        netflix_global,
        katy_perry,
        time_card,
        _why_now_card(6, "Winter snow", score=70, category="weather"),
        _why_now_card(7, "Tech story 2", score=69, category="tech"),
        _why_now_card(8, "Econ story 2", score=68, category="economics"),
        _why_now_card(9, "Hockey story 2", score=67, category="hockey"),
        _why_now_card(10, "Politics story 2", score=66, category="politics"),
        _why_now_card(11, "Econ story 3", score=65, category="economics"),
        _why_now_card(12, "Tech story 3", score=64, category="tech"),
        _why_now_card(13, "Sports story 3", score=63, category="basketball"),
        _why_now_card(14, "Geopolitics story 2", score=62, category="geopolitics"),
        _why_now_card(15, "Econ story 4", score=61, category="economics"),
        _why_now_card(16, "Weather story 2", score=60, category="weather"),
        _why_now_card(17, "Politics story 3", score=59, category="politics"),
        _why_now_card(18, "Culture story 1", score=58, category="culture"),
        _why_now_card(19, "Culture story 2", score=57, category="culture"),
        _why_now_card(20, "Politics story 4", score=56, category="politics"),
    ]

    diversified = diversify_discover_first_page(
        pool,
        first_page_size=20,
        cold_start=True,
        cold_start_window=COLD_START_WINDOW_FIRST_CARDS,
    )
    top20_ids = [c["data"]["id"] for c in diversified[:20]]
    assert 27467306 in top20_ids
    # At most one weekly Netflix movie card on page 1
    assert sum(1 for cid in (71058525, 71058521) if cid in top20_ids) == 1


def test_floor_steps_clean_fun_card_to_slots_10_to_19_instead_of_tail_seat_38():
    """10:03 PM scenario: TIME Person of the Year (88, fun-tagged, clean page-wide,
    standing-leader headline) sits in slots 0..9. enforce_first_page_quality_floor
    keeps slots 0..9 free of no-why-now cards, and steps TIME cleanly to slot 10
    (seat 11) rather than swapping it into new_tail[18] (seat 38)."""
    time_card = _futures(
        27467306,
        "TIME Person of the Year 2026",
        score=88,
        category="entertainment",
        headline="James Talarico leads at 25%",
        fun_tags=["year-end", "pope-leo-xiv"],
    )
    # 19 other page-1 cards (slots 0..7 have why-now, slot 8 is TIME, slots 9..19 are mixed)
    page = [_why_now_card(100 + i, f"Lead {i}", score=95 - i, category="tech") for i in range(8)]
    page.append(time_card)  # slot 8 (seat 9)
    page.append(_why_now_card(109, "Slot 10 why-now", score=86, category="economics"))
    # Slots 10..19: standing non-why-now cards (legal at slots 10..19, cannot lift into slot 8)
    for i in range(10, 20):
        page.append(_futures(200 + i, f"Second half {i}", score=80 - i, category="politics"))

    # Tail: 17 non-why-now cards, then at tail[17] (seat 38) a weak score-59 why-now card
    tail = [_futures(300 + i, f"Tail quiet {i}", score=70 - i, category="politics") for i in range(17)]
    weak_decade = _why_now_card(108254, "Time's Person of the Decade", score=59, category="entertainment")
    tail.append(weak_decade)

    items = page + tail
    out, meta = enforce_first_page_quality_floor(
        items,
        first_page_size=20,
        why_now_window=FIRST_PAGE_WHY_NOW_WINDOW,
    )

    assert len(out) == len(items)
    assert sorted(map(id, out)) == sorted(map(id, items))
    assert meta["no_why_now_in_window"] == 1
    assert meta["demoted"] == 1
    assert meta["unreplaced"] == 0
    # Slots 0..9 remain 100% why-now clean
    assert time_card not in out[:10]
    # TIME lands right at slot 10 (seat 11), NOT down at seat 38
    assert out.index(time_card) == 10
    assert out[8] is weak_decade or weak_decade in out[:10]
