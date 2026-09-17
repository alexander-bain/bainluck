"""#4485/#4821 — Discover stops serving a UFC "card" its own rows prove is fiction.

═══ THE DEFECT ═══

`list_card_concepts` groups fight rows by date token and emits one card per
token, asking nothing about whether the rows underneath describe an event. Three
of the nine UFC concept cards production served on 2026-09-17 were bags of
rumoured bouts dropped on a placeholder instant:

    2027-01-01 03:00Z   7 bouts, ALL on that one instant
                        Sean Strickland in two of them, Khamzat Chimaev in two
    2027-04-25 02:00Z   2 bouts, one instant
                        Islam Makhachev vs Morales AND vs Prates
    2027-08-01 02:00Z   2 bouts, one instant
                        Magomed Ankalaev vs Ulberg AND vs Prochazka

Nobody fights twice on one card, and a card's fights do not all start at the
same second. A reader scrolling Discover got these beside the real 12-fight card
happening that week, each with a name, a confident percentage, and (on web) a
correctly-localised date computed off the placeholder.

═══ WHY THE PREDICATE IS A CONJUNCTION ═══

Censused over every upcoming MMA **and boxing** card on production 2026-09-17
(30 cards, 139 bout rows) before building. Each clause alone suppresses real
cards:

    stacked-alone      -> kills tonight's real boxing card (4 bouts @ 22:00, d+0)
    double-alone       -> kills a real 12-bout boxing card at d+2 (one dirty row)
    BOTH TOGETHER      -> 3 cards of 30, all MMA, all >=106 days out

The arms below are that census. The two "alone" arms are the ones that can
actually fail: they are the shapes a tightened predicate would quietly start
eating, and neither is reachable from the defect arms.

`>=106 days` is an OUTCOME, never an input — contamination does not track
distance (a 17-day card is contaminated; a 101-day card is roster-clean), so no
day count appears in the predicate and none should be added to it.
"""

from __future__ import annotations

import itertools
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.event_combat import card_rows_are_not_a_schedule, list_card_concepts
from app.utils.event_ufc import UFC_CONFIG

_IDS = itertools.count(1)


def _bout(home, away, when):
    """An Event row for one fight. `id` matters — `bout_order_key` orders on it."""
    return SimpleNamespace(
        id=next(_IDS),
        home_team_name=home,
        away_team_name=away,
        commence_time=when,
    )


def _far(days: int, hour: int = 3) -> datetime:
    """A fixed instant `days` out. Offset FIRST, then truncate (gotcha #44) — an
    anchor that branches on the clock is not an anchor."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )


# ═══════════════════════════════════════════════════════════════════════════
# The defect: the three live specimens, by their real rosters.
# ═══════════════════════════════════════════════════════════════════════════


class TestTheCardsThatAreNotSchedules:
    def test_makhachev_cannot_fight_two_people_at_one_instant(self):
        when = _far(220, hour=2)
        assert card_rows_are_not_a_schedule(
            [
                _bout("Islam Makhachev", "Michael Morales", when),
                _bout("Islam Makhachev", "Carlos Prates", when),
            ]
        )

    def test_the_seven_bout_new_year_bag(self):
        when = _far(106)
        assert card_rows_are_not_a_schedule(
            [
                _bout("Sean Strickland", "Khamzat Chimaev", when),
                _bout("Sean Strickland", "Nassourdine Imavov", when),
                _bout("Khamzat Chimaev", "Paulo Costa", when),
                _bout("Tom Aspinall", "Ciryl Gane", when),
                _bout("Max Holloway", "Conor McGregor", when),
                _bout("Max Holloway", "Paddy Pimblett", when),
                _bout("Alexandre Pantoja", "Joshua Van", when),
            ]
        )

    def test_ankalaev_booked_twice(self):
        when = _far(318, hour=2)
        assert card_rows_are_not_a_schedule(
            [
                _bout("Magomed Ankalaev", "Carlos Ulberg", when),
                _bout("Magomed Ankalaev", "Jiri Prochazka", when),
            ]
        )

    def test_a_duplicate_row_is_caught_through_diacritics_and_case(self):
        """The two rows are one provider echoing itself, so they spell the name
        the same — but folding is what makes that an equality rather than a
        coincidence of bytes."""
        when = _far(200, hour=2)
        assert card_rows_are_not_a_schedule(
            [
                _bout("Filip Hrgović", "Agit Kabayel", when),
                _bout("FILIP  HRGOVIC", "Moses Itauma", when),
            ]
        )


# ═══════════════════════════════════════════════════════════════════════════
# The other direction (gotcha #43): what the predicate must NOT eat.
# Each of these is a real production card measured on 2026-09-17.
# ═══════════════════════════════════════════════════════════════════════════


class TestTheRealCardsItMustNotEat:
    def test_stacked_alone_is_not_enough__tonights_real_boxing_card(self):
        """4 bouts all stamped 22:00, d+0, no fighter repeated. A promotion that
        stamps its whole card at the broadcast time is not lying about anything,
        and `stacked-alone` would have deleted it."""
        when = _far(0, hour=22)
        assert not card_rows_are_not_a_schedule(
            [
                _bout("Moses Itauma", "Dillian Whyte", when),
                _bout("Fabio Wardley", "Justis Huni", when),
                _bout("Anthony Yarde", "Lyndon Arthur", when),
                _bout("Ben Whittaker", "Liam Cameron", when),
            ]
        )

    def test_double_booked_alone_is_not_enough__a_real_card_with_one_dirty_row(self):
        """12 bouts over 7 distinct times, two days out, with exactly one
        fighter carrying a duplicate row. One dirty row does not make a card
        fictional, and `double-alone` would have deleted it."""
        base = _far(2, hour=18)
        bouts = [
            _bout(f"Home {i}", f"Away {i}", base + timedelta(minutes=25 * i))
            for i in range(7)
        ]
        bouts += [
            _bout("Joe Howarth", "Kane Gardner", base),
            _bout("Joe Howarth", "Ryan Walsh", base + timedelta(minutes=50)),
        ]
        assert not card_rows_are_not_a_schedule(bouts)

    def test_two_fighters_sharing_a_surname_are_two_people(self):
        """The surname trap. `player_key` folds both of these to "silva", so a
        surname-keyed predicate reports this ONE bout as a double booking and
        deletes a real card."""
        when = _far(30, hour=2)
        assert not card_rows_are_not_a_schedule(
            [
                _bout("Anderson Silva", "Thiago Silva", when),
                _bout("Natalia Silva", "Wang Cong", when),
            ]
        )

    def test_a_lone_bout_cannot_contradict_itself(self):
        assert not card_rows_are_not_a_schedule(
            [_bout("Paddy Pimblett", "Conor McGregor", _far(297, hour=0))]
        )

    def test_a_clean_far_future_card_keeps_its_slot(self):
        """Distance is not the predicate. A genuinely scheduled card 220 days
        out is as admissible as tonight's."""
        base = _far(220, hour=2)
        assert not card_rows_are_not_a_schedule(
            [
                _bout("Alex Pereira", "Jiri Prochazka", base),
                _bout("Sean O'Malley", "Merab Dvalishvili", base + timedelta(hours=1)),
            ]
        )

    def test_empty_and_timeless_rosters_are_not_judged(self):
        assert not card_rows_are_not_a_schedule([])
        assert not card_rows_are_not_a_schedule(
            [_bout("A B", "C D", None), _bout("E F", "G H", None)]
        )


# ═══════════════════════════════════════════════════════════════════════════
# The wiring: the predicate has to reach the SERVED card list, not just pass
# its own unit test.
# ═══════════════════════════════════════════════════════════════════════════


class _FakeResult:
    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._items)


class _FakeDB:
    """Dispatch on the statement — `list_card_concepts` reads Event rows and then
    FuturesOutcome rows, and answering both from one list lets the outcome
    reader raise inside its own catch-all and silently skip (the shared-mock
    trap this suite's sibling documents)."""

    def __init__(self, events=()):
        self._events = list(events)

    async def execute(self, statement, *_a, **_k):
        if "futures_outcomes" in str(statement):
            return _FakeResult([])
        return _FakeResult(self._events)


@pytest.mark.asyncio
class TestTheListerDropsIt:
    async def test_the_fabricated_card_is_not_emitted_and_the_real_one_is(self):
        """Two cards, one call. The population must HOLD while the fiction goes
        — "the bad card is gone" passes on an empty list, so it is not asserted
        on its own."""
        bad_when = _far(220, hour=2)
        good_base = _far(9, hour=18)
        events = [
            # Fabricated: one instant, Makhachev twice.
            _bout("Islam Makhachev", "Michael Morales", bad_when),
            _bout("Islam Makhachev", "Carlos Prates", bad_when),
            # Real: distinct times, no repeats.
            _bout("Darren Till", "Yoel Romero", good_base),
            _bout("Natalia Silva", "Wang Cong", good_base + timedelta(hours=1)),
        ]

        concepts = await list_card_concepts(UFC_CONFIG, _FakeDB(events), rows=[])

        names = {c["name"] for c in concepts}
        assert any(
            "Till" in n or "Silva" in n for n in names
        ), f"the real card must survive; got {names}"
        assert not any(
            "Makhachev" in n for n in names
        ), f"the fabricated card must not be served; got {names}"
