"""Saturday's 60-seat sheet (#12723, Fable's comment): two rows of one thing in
one card.

* Seat 24, "Three tournaments": The ANNIKA twice — "The ANNIKA driven by
  Gainbridge at Pelican" and "The ANNIKA", Nov 12–15, the same leader.
* Seat 26, "Who goes public, and at what price?": two Polymarket listings of one
  market, "Anthropic IPO Closing Market Cap" at 46% and "… (Middle Brackets)" at
  51%.

Each fold has its controls: the cases that look alike and must NOT fold.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.utils import discover_bundles as db
from app.utils import week_events as we

NOW = datetime(2026, 11, 13, 18, 0, tzinfo=timezone.utc)
OBS = "2026-11-13T17:00:00+00:00"


def _tournament(key, name, leader, p, start="2026-11-12", end="2026-11-15"):
    return {
        "key": key,
        "slug": key.replace("_", "-"),
        "name": name,
        "tour": "lpga",
        "tour_label": "LPGA",
        "start_date": start,
        "end_date": end,
        "schedule_status": "in_progress",
        "champion": None,
        "market_ids": [abs(hash(key)) % 10_000_000],
        "market_sources": ["polymarket"],
        "source_count": 1,
        "updated_at": OBS,
        "golfers": [
            {"name": leader, "probability": p, "rank": 1, "movement_24h": 0.01, "movement_is_dated": True},
            {"name": "Second Player", "probability": 0.15, "rank": 2, "movement_24h": 0.01, "movement_is_dated": True},
        ],
        "_all_golfers": [
            {"name": leader, "probability": p},
            {"name": "Second Player", "probability": 0.15},
            {"name": "Field Remainder", "probability": 1 - p - 0.15},
        ],
    }


class TestTheAnnikaOnce:
    def test_seat_24_keeps_one_annika(self):
        tournaments = [
            _tournament("the_annika_driven_by_gainbridge_at_pelican", "The ANNIKA driven by Gainbridge at Pelican", "Hye-Jin Choi", 0.30),
            _tournament("the_annika", "The ANNIKA", "Hye-Jin Choi", 0.25),
            _tournament("austin_championship", "Austin Championship", "Trace Crowe", 0.20),
        ]
        card = we.select_week_events(tournaments, now=NOW)
        from app.utils.roundup_containers import RoundupRefusal

        assert not isinstance(card, RoundupRefusal), card
        names = [m.get("name") or m.get("title") or (m.get("destination") or {}).get("name") for m in card.members]
        assert len(card.members) == 2, names
        assert sum("ANNIKA" in repr(m) for m in card.members) == 1
        assert any("Austin Championship" in repr(m) for m in card.members)

    def test_a_generic_name_never_folds_into_a_longer_one(self):
        a = _tournament("open", "Open", "A Player", 0.3)
        b = _tournament("australian_open", "Australian Open", "B Player", 0.3)
        sel_a, _ = we._evaluate_single_tournament(a, week_start=NOW.date(), week_end=NOW.date())
        sel_b, _ = we._evaluate_single_tournament(b, week_start=NOW.date(), week_end=NOW.date())
        assert sel_a and sel_b and not we._is_twin(sel_a, sel_b)

    def test_same_name_words_on_different_weeks_are_different_events(self):
        a = _tournament("the_annika", "The ANNIKA", "A", 0.3)
        b = _tournament("the_annika_2", "The ANNIKA", "A", 0.3, start="2026-11-19", end="2026-11-22")
        sel_a, _ = we._evaluate_single_tournament(a, week_start=NOW.date(), week_end=NOW.date())
        sel_b, _ = we._evaluate_single_tournament(b, week_start=datetime(2026, 11, 20).date(), week_end=datetime(2026, 11, 20).date())
        assert sel_a and sel_b and not we._is_twin(sel_a, sel_b)


def _member(mid, name, source="polymarket"):
    return {"type": "futures", "data": {"id": mid, "name": name, "source": source}}


class TestOneListingOneRow:
    def test_seat_26_folds_the_middle_brackets_listing(self):
        kept, folded = db._dedupe_same_question_members([
            _member(1, "Anthropic IPO Closing Market Cap"),
            _member(2, "Anthropic IPO Closing Market Cap (Middle Brackets)"),
            _member(3, "Kimi (Moonshot AI) IPO?"),
        ])
        assert [m["data"]["id"] for m in kept] == [1, 3]
        assert [m["data"]["id"] for m in folded] == [2]

    def test_mens_and_womens_never_fold(self):
        kept, folded = db._dedupe_same_question_members([
            _member(1, "2026 Men's US Open Winner (Tennis)"),
            _member(2, "2026 Women's US Open Winner (Tennis)"),
        ])
        assert len(kept) == 2 and not folded

    def test_a_different_question_with_a_qualifier_stays(self):
        kept, folded = db._dedupe_same_question_members([
            _member(1, "Will Anthropic's valuation hit (LOW) $1.4T by November 30?"),
            _member(2, "Will Anthropic's valuation hit (HIGH) $1.5T by December 31?"),
        ])
        assert len(kept) == 2 and not folded


def test_brackets_inside_a_title_name_different_things_and_never_fold():
    """Monday Nov 16, seat 16: the relegation card's "(LP)" and "(RC)" are two
    clubs (Estudiantes de La Plata, Estudiantes de Río Cuarto)."""
    from app.utils.discover_bundles import _same_listing_with_a_qualifier as same

    def m(name):
        return {"name": name, "source": "kalshi"}

    t = "Will Estudiantes ({}) be relegated from the 2026 Liga Profesional (Argentina)?"
    assert not same(m(t.format("LP")), m(t.format("RC")))
    g = "Will Gimnasia y Esgrima ({}) be relegated from the 2026 Liga Profesional (Argentina)?"
    assert not same(m(g.format("M")), m(g.format("LP")))
    # The case the rule exists for still folds, in either order.
    a, b = m("Anthropic IPO Closing Market Cap"), m("Anthropic IPO Closing Market Cap (Middle Brackets)")
    assert same(a, b) and same(b, a)
    # Same title twice, or another venue, is not this rule's business.
    assert not same(a, m("Anthropic IPO Closing Market Cap"))
    assert not same(a, {"name": b["name"], "source": "polymarket"})
