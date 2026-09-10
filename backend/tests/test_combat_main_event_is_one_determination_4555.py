"""#4555 — a fight card's title and its hero name the SAME fight, every request.

═══ THE DEFECT ═══

Three consumers each decided what a card's main event was, and all three spelled
it `bouts[-1]` over a list sorted on `commence_time` alone:

    list_card_concepts   -> the card's NAME
    _build_events_envelope -> the envelope's `primary` (and so the feed's hero)
    the feed's cached envelope -> the hero again, built at a different moment

`commence_time` is not a total order over a fight card. Measured on production
2026-09-10 by db-query over every combat card in the lister's window, **7 of 18
cards carry two or more bouts at their latest commence**, and on
`event:ufc:26sep10` the tie is total: all ten fights are stamped
`2026-09-10 00:00:00+00`. A sort on a tied key is stable with respect to its
INPUT, and the input was a query with no tiebreak — so `bouts[-1]` was whichever
row Postgres returned last, and it changed between requests.

What a reader saw, on one card, in one evening (`GET /api/feed`):

    21:57Z   name: "Renato Moicano vs Brian Ortega"
    00:15Z   name: "Mauricio Ruffy vs Arman Tsarukyan"     hero: Joshua Van 52% / Pantoja 48%
    00:26Z   name: "Alonzo Menifield vs Iwo Baraniewski"   hero: Baraniewski 70% / Menifield 30%

Same key, same ten fights. Refreshing the page renamed the event.

═══ WHAT IS GUARDED ═══

One determination — `main_bout_of` — used by both consumers. The arms below are
behavioural, not a source scan: this module's own prose contains the string
`bouts[-1]` several times, and a grep-shaped guard over a file that documents the
thing it bans is a guard that cannot tell a fix from a comment.

The permutation arms are the ones that can actually fail. A tied card has no
canonical input order, so the test hands the SAME bouts in every order and
demands one answer; under the old code each order produced its own.
"""

from __future__ import annotations

import itertools
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.event_combat import bout_order_key, main_bout_of
from app.utils.event_ufc import UFC_CONFIG, list_ufc_card_concepts


def _bout(event_id, home, away, when, *, opening_home=None):
    """An Event row for one fight, with the two fields the order depends on.

    `opening_home_probability` feeds `compute_aggregate_probability`'s tier 3, so
    the envelope's competitor list is really priced and really sorted by price —
    which is what lets the fixture below put the main event on the LOW side of
    the card's prices.
    """
    return SimpleNamespace(
        id=event_id,
        home_team_name=home,
        away_team_name=away,
        commence_time=when,
        status="scheduled",
        win_probability_sources=None,
        espn_win_prob_home=None,
        opening_home_probability=opening_home,
    )


def _next_utc_midnight():
    """A card that is always in the future, whatever hour the suite runs at.

    Gotcha #44: offset FIRST, then truncate. No branch on the clock.
    """
    return (datetime.now(timezone.utc) + timedelta(days=3)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def _tied_card():
    """The Sep 10 card's real shape: every bout at ONE placeholder commence.

    Ids ascend in ingest order, and that is the real ordering too — the three
    marquee bouts were created on Aug 6, five weeks before the seven-fight
    undercard batch of Sep 1. The main event is therefore the LOWEST id, and it
    is deliberately NOT the most lopsided fight on the card (Menifield/
    Baraniewski at 0.70 is), so a hero taken from a price-ordered list picks a
    different bout and the agreement arm can fail.
    """
    when = _next_utc_midnight()
    return [
        _bout(15190384, "Alexandre Pantoja", "Joshua Van", when, opening_home=0.478),
        _bout(15190802, "Robelis Despaigne", "Tai Tuivasa", when, opening_home=0.160),
        _bout(15190830, "Mauricio Ruffy", "Arman Tsarukyan", when, opening_home=0.395),
        _bout(
            15300578, "Alonzo Menifield", "Iwo Baraniewski", when, opening_home=0.305
        ),
        _bout(15300584, "Giga Chikadze", "Joanderson Brito", when, opening_home=0.520),
    ]


class _FakeResult:
    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return self

    def all(self):
        return list(self._items)


class _FakeDB:
    """The lister's two reads, told apart by statement (see #1712's fake).

    Answering both from one list is the shared-mock trap: `_attach_headline_bouts`
    swallows every exception on purpose, so handing it Event rows would leave this
    file green while the path it names was never run.
    """

    def __init__(self, events):
        self._events = list(events)

    async def execute(self, statement, *_a, **_k):
        if "futures_outcomes" in str(statement):
            return _FakeResult([])
        return _FakeResult(self._events)


class TestTheOrderIsTotal:
    def test_a_tie_is_broken_by_id_so_two_reads_agree(self):
        when = _next_utc_midnight()
        a = _bout(2, "A", "B", when)
        b = _bout(1, "C", "D", when)
        assert sorted([a, b], key=bout_order_key) == [b, a]
        assert sorted([b, a], key=bout_order_key) == [b, a]

    def test_the_latest_bout_still_wins_when_the_times_differ(self):
        """The tiebreak is a tiebreak — it never outranks the clock.

        The oldest ROW here fights first; the main event is the late one, and a
        rule that just took the lowest id would get this backwards.
        """
        when = _next_utc_midnight()
        early_but_oldest_row = _bout(1, "Prelim A", "Prelim B", when)
        main = _bout(99, "Headliner A", "Headliner B", when + timedelta(hours=3))
        assert main_bout_of([early_but_oldest_row, main]) is main
        assert main_bout_of([main, early_but_oldest_row]) is main

    def test_no_bouts_is_none_not_an_index_error(self):
        assert main_bout_of([]) is None


class TestOneDeterminationUnderEveryInputOrder:
    """The card is totally tied, so its input order is arbitrary. Answer isn't."""

    def test_main_bout_of_is_invariant_under_permutation(self):
        bouts = _tied_card()
        picks = {
            main_bout_of(list(order)).id for order in itertools.permutations(bouts)
        }
        assert picks == {
            15190384
        }, f"the main event moved with the input order: {picks}"

    @pytest.mark.asyncio
    async def test_the_card_keeps_its_name_across_reads(self):
        """Postgres may hand back a tied card in any order; the title may not move.

        Five bouts, 120 orders, one name — the arm that reproduces the three
        different names one production card served in one evening.
        """
        names = set()
        for order in itertools.permutations(_tied_card()):
            concepts = await list_ufc_card_concepts(
                _FakeDB(order), statuses=("upcoming", "live"), rows=[]
            )
            assert len(concepts) == 1, [c["key"] for c in concepts]
            names.add(concepts[0]["name"])
        assert len(names) == 1, f"one card, {len(names)} names: {sorted(names)}"
        assert "Pantoja" in names.pop()


class TestTheTitleAndTheHeroAreTheSameFight:
    """#4555's acceptance: the name and `primary` name ONE bout, both branches."""

    @pytest.mark.asyncio
    async def test_the_envelope_primary_is_the_bout_the_card_is_named_after(self):
        adapter = _ufc_adapter()
        now = datetime.now(timezone.utc)
        for order in itertools.permutations(_tied_card()):
            bouts = sorted(order, key=bout_order_key)
            envelope = adapter._build_events_envelope("26sep10", bouts, now)
            name = envelope["event"]["name"]
            hero = {c["name"] for c in envelope["primary"]["competitors"]}
            assert hero == {"Alexandre Pantoja", "Joshua Van"}, hero
            assert all(side in name for side in ("Pantoja", "Van")), name

    @pytest.mark.asyncio
    async def test_the_lister_and_the_envelope_do_not_disagree(self):
        """The two consumers, on the same card, must land on the same fight.

        This is the shape the reader saw: a title from one branch, a hero from
        the other, and nothing making them agree.
        """
        bouts = _tied_card()
        concepts = await list_ufc_card_concepts(
            _FakeDB(bouts), statuses=("upcoming", "live"), rows=[]
        )
        listed_name = concepts[0]["name"]

        adapter = _ufc_adapter()
        envelope = adapter._build_events_envelope(
            "26sep10", sorted(bouts, key=bout_order_key), datetime.now(timezone.utc)
        )
        assert envelope["event"]["name"] == listed_name
        hero = {c["name"] for c in envelope["primary"]["competitors"]}
        assert all(surname in listed_name for surname in ("Pantoja", "Van"))
        assert hero == {"Alexandre Pantoja", "Joshua Van"}

    @pytest.mark.asyncio
    async def test_the_hero_is_not_simply_the_biggest_price_on_the_card(self):
        """The negative control: a price-ordered hero would pick a different bout.

        The most lopsided fight in the fixture is Tuivasa/Despaigne at 0.84 —
        which is not an invented number: ux/1070's own docstring records
        `event:ufc:26sep10` leading with "Tai Tuivasa 84%" while titled after a
        different bout, measured on production 2026-09-04. If this arm ever
        passes because the fixture went flat, it is not testing anything.
        """
        bouts = _tied_card()
        most_lopsided = max(
            bouts,
            key=lambda b: max(
                b.opening_home_probability, 1 - b.opening_home_probability
            ),
        )
        assert most_lopsided.id == 15190802, "fixture no longer has a lopsided fight"
        assert main_bout_of(bouts).id != most_lopsided.id


def _ufc_adapter():
    from app.utils.event_combat import CombatEventAdapter

    return CombatEventAdapter(UFC_CONFIG)
