"""#4485 — a UFC card names the EVENT, when the venue published a name for it.

═══ THE DEFECT ═══

A card built from the schedule (events) source alone has two fighter names and
nothing else, so `list_card_concepts` falls through to its own main event and
the card is named after one of its fights. Served on production 2026-09-22:

    event:ufc:26oct25   "Alex Volkanovski vs Movsar Evloev"     <- ESPN: UFC 333
    event:ufc:26nov15   "Ciryl Gane vs Josh Hokit"              <- ESPN: UFC 334

8 of 10 UFC cards on the feed were named this way. discover/027 read both our
stores and found no card name in either — correctly — and recorded the venue
read as the next step without taking it. Taken: ESPN's MMA board models a CARD
as one event, `name` is the card name, and all 14 cards in the forward window
carry one.

═══ WHAT IS GUARDED, AND WHY EACH ARM CAN FAIL ═══

The dangerous direction here is the FALSE POSITIVE — calling a Czech regional
card "UFC 333" is worse than the defect. So the refusal arms outnumber the ship
arm, and each is a shape measured on the live rows rather than an invented one:

* `test_the_card_takes_the_venues_name` — the ship. Fails on the old code.
* `test_a_shared_surname_on_ONE_side_is_not_evidence` — the 26sep25 OKTAGON
  card really does carry a "Max Holloway", and ESPN's board really does carry a
  UFC "Max Holloway" bout that week. A join on a name in common renames a
  regional card to a UFC one; the join is BOTH sides of one bout.
* `test_a_card_the_venue_does_not_list_keeps_its_own_name` — the 26dec27 /
  27jan01 / 27jul11 rumour fixtures of #4560. ESPN lists nothing on those
  nights, and this must stay silent rather than reach for the nearest card.
* `test_a_cold_listing_changes_nothing` — the whole fail-open claim. Redis cold,
  ESPN dark, or an unknown stored shape must all produce the pre-#4485 name.
* `test_a_bout_a_year_away_cannot_borrow_this_seasons_name` — "Islam Makhachev
  vs Kamaru Usman" is booked twice, seven months apart. Bout evidence alone
  would let the 2027 rumour take the 2026 card's name.
* `test_two_matching_venue_cards_refuse_to_name` — a bout cannot be on two
  cards, so a double match means one join is wrong with no way to tell which.
* `test_naming_a_card_does_not_move_it` — `is_major` is the marquee key the
  lister sorts on. This ship renames; it does not re-rank, and that is a claim
  a reader could otherwise catch us breaking.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils import combat_card_names
from app.utils.combat_card_names import match_card_name, parse_espn_cards
from app.utils.event_ufc import list_ufc_card_concepts


# ---------------------------------------------------------------------------
# Fixtures — the harness of #4555's suite, which drives the real lister.
# ---------------------------------------------------------------------------
def _bout(event_id, home, away, when):
    return SimpleNamespace(
        id=event_id,
        home_team_name=home,
        away_team_name=away,
        commence_time=when,
        status="scheduled",
        win_probability_sources=None,
        espn_win_prob_home=None,
        opening_home_probability=None,
    )


def _soon():
    """Always future, never a branch on the clock (gotcha #44: offset FIRST)."""
    return (datetime.now(timezone.utc) + timedelta(days=3)).replace(
        hour=2, minute=0, second=0, microsecond=0
    )


class _FakeResult:
    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return self

    def all(self):
        return list(self._items)


class _FakeDB:
    """The lister's two reads, told apart by statement (#1712's fake).

    Answering both from one list is the shared-mock trap: `_attach_headline_bouts`
    swallows every exception on purpose, so handing it Event rows would leave
    this file green while the path it names never ran.
    """

    def __init__(self, events):
        self._events = list(events)

    async def execute(self, statement, *_a, **_k):
        if "futures_outcomes" in str(statement):
            return _FakeResult([])
        return _FakeResult(self._events)


def _the_real_card():
    """The 26oct25 card as production served it: two bouts, no venue rows."""
    when = _soon()
    return [
        _bout(15316001, "Petr Yan", "Merab Dvalishvili", when),
        _bout(
            15316002, "Alex Volkanovski", "Movsar Evloev", when + timedelta(minutes=30)
        ),
    ]


def _venue_card(name, when, bouts):
    return {
        "name": name,
        "date": when.isoformat().replace("+00:00", "Z"),
        "bouts": bouts,
    }


def _ufc333(when):
    """ESPN's own row for that night, trimmed to three of its nine bouts."""
    return _venue_card(
        "UFC 333: Volkanovski vs. Evloev",
        when,
        [
            "Alexander Volkov vs Rizvan Kuniev",
            "Alex Volkanovski vs Movsar Evloev",
            "Petr Yan vs Merab Dvalishvili",
        ],
    )


async def _name_of_the_card(monkeypatch, listing, events=None):
    """The name the lister gives the card, with `listing` published."""
    monkeypatch.setattr(combat_card_names, "load_card_names", lambda *_a, **_k: listing)
    # `rows=[]` is the venue-market accelerator, and passing it is what makes
    # this an EVENTS-ONLY card — the branch the defect lives in.
    concepts = await list_ufc_card_concepts(
        _FakeDB(events or _the_real_card()), statuses=("upcoming", "live"), rows=[]
    )
    assert len(concepts) == 1, f"expected one card, got {[c['name'] for c in concepts]}"
    return concepts[0]


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------
class TestTheCardNamesTheEvent:
    @pytest.mark.asyncio
    async def test_the_card_takes_the_venues_name(self, monkeypatch):
        """The filed defect, with the venue's listing published."""
        card = await _name_of_the_card(monkeypatch, [_ufc333(_soon())])
        assert card["name"] == "UFC 333: Volkanovski vs. Evloev"

    @pytest.mark.asyncio
    async def test_naming_a_card_does_not_move_it(self, monkeypatch):
        """Renaming is not re-ranking — `is_major` is untouched.

        `is_major` is the first key `list_card_concepts` sorts on, so if naming a
        card promoted it the whole cohort would jump the feed. Compared against
        the SAME card with no listing, so this cannot pass by both sides being
        wrong in the same direction.
        """
        with_name = await _name_of_the_card(monkeypatch, [_ufc333(_soon())])
        without = await _name_of_the_card(monkeypatch, [])
        assert with_name["name"] != without["name"], "the arms must differ in NAME"
        assert with_name["is_major"] == without["is_major"]
        assert with_name["fight_count"] == without["fight_count"]
        assert with_name["start_date"] == without["start_date"]
        assert with_name["key"] == without["key"]


# ---------------------------------------------------------------------------
# The refusals — the direction that matters
# ---------------------------------------------------------------------------
class TestTheVenueMustProveItIsTheSameCard:
    @pytest.mark.asyncio
    async def test_a_cold_listing_changes_nothing(self, monkeypatch):
        """Redis cold / ESPN dark / an unknown shape == today's behaviour."""
        for listing in ([], None, "not a list", [{"no": "name"}], [{"name": "X"}]):
            card = await _name_of_the_card(monkeypatch, listing)
            assert card["name"] == "Alex Volkanovski vs Movsar Evloev", listing

    @pytest.mark.asyncio
    async def test_a_shared_surname_on_ONE_side_is_not_evidence(self, monkeypatch):
        """The live OKTAGON shape — a regional card carrying a 'Max Holloway'.

        Both cards name a Max Holloway, and only a both-sides test refuses.
        """
        when = _soon()
        oktagon = [
            _bout(1, "David Kozma", "Christian Eckerlin", when),
            _bout(
                2, "Christian Jungwirth", "Max Holloway", when + timedelta(minutes=20)
            ),
        ]
        listing = [
            _venue_card(
                "UFC Fight Night: Holloway vs. McGregor",
                when,
                ["Max Holloway vs Conor McGregor", "Alexandre Pantoja vs Joshua Van"],
            )
        ]
        card = await _name_of_the_card(monkeypatch, listing, events=oktagon)
        assert card["name"] == "Christian Jungwirth vs Max Holloway"

    @pytest.mark.asyncio
    async def test_a_card_the_venue_does_not_list_keeps_its_own_name(self, monkeypatch):
        """#4560's rumour fixtures — ESPN lists no card on those nights."""
        listing = [
            _venue_card(
                "UFC 335",
                _soon() + timedelta(days=40),
                ["Someone Else vs Another Person"],
            )
        ]
        card = await _name_of_the_card(monkeypatch, listing)
        assert card["name"] == "Alex Volkanovski vs Movsar Evloev"

    def test_a_bout_a_year_away_cannot_borrow_this_seasons_name(self):
        """'Makhachev vs Usman' is booked twice, seven months apart.

        Bout evidence joins them; the date fence is what keeps the 2027 rumour
        from wearing the 2026 card's name.
        """
        when = _soon()
        listing = [
            _venue_card(
                "UFC 340: Makhachev vs. Usman",
                when,
                ["Islam Makhachev vs Kamaru Usman"],
            )
        ]
        ours = ["Islam Makhachev vs Kamaru Usman"]

        inside = match_card_name(ours, listing, span=(when, when))
        assert (
            inside == "UFC 340: Makhachev vs. Usman"
        ), "the fence must admit the real card"

        far = when + timedelta(days=210)
        assert match_card_name(ours, listing, span=(far, far)) is None

    def test_two_matching_venue_cards_refuse_to_name(self):
        """A bout cannot be on two cards — a double match is not a coin flip."""
        when = _soon()
        bout = ["Alex Volkanovski vs Movsar Evloev"]
        one = _venue_card("UFC 333: Volkanovski vs. Evloev", when, bout)
        two = _venue_card("UFC 999: Something Else", when, bout)

        assert match_card_name(bout, [one], span=(when, when)) is not None
        assert match_card_name(bout, [one, two], span=(when, when)) is None


# ---------------------------------------------------------------------------
# The parser
# ---------------------------------------------------------------------------
class TestParsingTheVenueBoard:
    def test_it_reads_the_card_name_and_its_bouts(self):
        """ESPN's real scoreboard shape, trimmed."""
        payload = {
            "events": [
                {
                    "id": "600061267",
                    "name": "UFC 333: Volkanovski vs. Evloev",
                    "date": "2026-10-24T22:00Z",
                    "competitions": [
                        {
                            "competitors": [
                                {"athlete": {"displayName": "Alexander Volkov"}},
                                {"athlete": {"displayName": "Rizvan Kuniev"}},
                            ]
                        }
                    ],
                }
            ]
        }
        cards = parse_espn_cards(payload)
        assert cards == [
            {
                "name": "UFC 333: Volkanovski vs. Evloev",
                "date": "2026-10-24T22:00Z",
                "bouts": ["Alexander Volkov vs Rizvan Kuniev"],
            }
        ]

    def test_a_card_with_no_usable_bout_is_dropped(self):
        """It could only ever match on date, and date is not evidence here.

        ESPN really does publish such a row — 'UFC Fight Night: Qatar' carried
        zero competitions in the 2026-09-22 read.
        """
        payload = {
            "events": [
                {
                    "name": "UFC Fight Night: Qatar",
                    "date": "2026-11-21T18:00Z",
                    "competitions": [],
                },
                {
                    "name": "Half a bout",
                    "date": "2026-11-21T18:00Z",
                    "competitions": [
                        {"competitors": [{"athlete": {"displayName": "Solo"}}]}
                    ],
                },
            ]
        }
        assert parse_espn_cards(payload) == []

    def test_junk_in_never_raises(self):
        """The producer must not die on a board shape nobody predicted."""
        for payload in (None, {}, [], {"events": None}, {"events": [None, 7, {}]}):
            assert parse_espn_cards(payload) == []


# ---------------------------------------------------------------------------
# The producer — a dark read is not an empty board (gotcha #53)
# ---------------------------------------------------------------------------
class TestThePublisher:
    """`get_combat_card_board` answers None when ESPN did not answer at all.

    Publishing an empty listing on that reading would overwrite good card names
    with none, and the consumer cannot tell an empty listing from "the venue
    named no cards". The standing listing is strictly better, so the task must
    publish NOTHING — and the only way to know it does is to make the read dark
    and watch the store.
    """

    @pytest.mark.asyncio
    async def test_a_dark_read_publishes_nothing(self, monkeypatch):
        from app.tasks import espn_combat_cards as mod

        stored: list = []
        monkeypatch.setattr(
            mod, "store_card_names", lambda cards, *a, **k: stored.append(cards) or True
        )

        class _Dark:
            async def get_combat_card_board(self, *_a, **_k):
                return None

        monkeypatch.setattr("app.services.espn_api.get_espn_service", lambda: _Dark())
        out = await mod._refresh_espn_combat_cards()
        assert out["published"] is False
        assert stored == [], "a dark read must not overwrite the standing listing"

    @pytest.mark.asyncio
    async def test_a_real_board_publishes(self, monkeypatch):
        """The positive control — without it the arm above passes on a no-op."""
        from app.tasks import espn_combat_cards as mod

        stored: list = []
        monkeypatch.setattr(
            mod, "store_card_names", lambda cards, *a, **k: stored.append(cards) or True
        )

        class _Live:
            async def get_combat_card_board(self, *_a, **_k):
                return {
                    "events": [
                        {
                            "name": "UFC 333: Volkanovski vs. Evloev",
                            "date": "2026-10-24T22:00Z",
                            "competitions": [
                                {
                                    "competitors": [
                                        {"athlete": {"displayName": "Petr Yan"}},
                                        {
                                            "athlete": {
                                                "displayName": "Merab Dvalishvili"
                                            }
                                        },
                                    ]
                                }
                            ],
                        }
                    ]
                }

        monkeypatch.setattr("app.services.espn_api.get_espn_service", lambda: _Live())
        out = await mod._refresh_espn_combat_cards()
        assert out["published"] is True
        assert stored and stored[0][0]["name"] == "UFC 333: Volkanovski vs. Evloev"
