"""THE HUB AND THE MATCH PAGE STOP ARGUING ABOUT WHO IS WINNING.

ux/1126 · PILLAR: TRUTH · SHIP: tapping a match on the US Open hub no longer
changes the percentage or flips the move arrow.

═══ WHAT WAS MEASURED (production, 2026-09-08 ~07:15-07:25Z, during the Slam) ═══

``/tournaments/us-open``, Quarter-finals::

    Frances Tiafoe   −2  59%      (Frances Tiafoe opened at 61%)
    Alex Michelsen   +2  41%

``/events/15306225``, the page that row links to::

    60% – 40%      ↑ +2% Tiafoe since open      (Opened 58% – 42%)

One question, one tap apart: 59 vs 60 now, 61 vs 58 at the open, **and Tiafoe
down two points on the hub while up two on his own page.**  The arrows are the
part that makes it a p1 — a level that rounds a point apart reads as a wobble,
two arrows pointing opposite ways reads as one of the two surfaces being wrong.

Read serially off the two APIs at the same moment (a parallel sweep tripped
HTTP 429 and reported a clean-looking ``0 / 0``), 8 event-linked quarter-finals::

    every one of the 7 comparable rows differed at the raw level
    2 of them differed in the rendered integer (Tiafoe 58.9 vs 59.5,
      Zheng 28.5 vs 28.7); Pegula read 77.7 vs 78.5
    1 (Andreeva, 15307447) carried no event opening at all

They were not two roundings of one number.  They were two numbers: the hub
priced from Kalshi alone (0.595/0.415) renormalized by its own vig to 0.589,
while the page served the weighted median over kalshi 0.595, betting 0.5764 and
polymarket 0.605, which lands on 0.595.  ``source_count: 1`` was sitting on the
hub payload the whole time, next to an ``event_id`` whose page blended three.

═══ WHAT THESE GUARDS PIN ═══

The load-bearing one is ``test_the_hub_row_prints_the_number_the_event_page_prints``,
because it drives the REAL ``build_slate`` with the REAL production numbers and
compares against ``resolve_hero`` — the same function ``routes/events.py`` now
serves the page from — rather than against a constant somebody typed.  A guard
that asserted ``== 0.595`` would stay green if both surfaces drifted together.

Two are CONTROLS, asserting what this change must NOT do:

* ``test_a_match_with_no_linked_event_is_untouched`` — the acceptance criterion's
  second half, and the obvious over-reach (blending everything).
* ``test_an_event_with_no_opening_keeps_the_venue_basis`` — a live case, not a
  hypothetical: Andreeva/Vondrousova on the day this shipped.  Taking "now" from
  the blend and "the open" from the venue is the mixed basis that inverted the
  arrow in the first place, so half a blend is refused rather than applied.

═══ THE VACUITY TRAP THIS FILE IS BUILT AGAINST ═══

Every assertion below runs after ``assert slate["count"] == 1``, and the blend
tests assert the row's ``price_basis`` POSITIVELY before reading a number off
it.  A slate test whose register does not produce a row passes every
``!=``-shaped assertion in this file while proving nothing — ux/1125 shipped a
rendered-regression draft with exactly that hole (an invented fixture the
grouping code returned ``""`` for), and the fixtures here are imported from
``test_tournament_slate`` rather than re-invented for the same reason.

═══ RED-FIRST ═══

Against the pre-fix tree ``orient_event_blend``, ``PRICE_BASIS_BLEND`` and the
``blends=`` keyword do not exist, so the import fails and the whole file is red.
With the overlay present but neutered (``orient_event_blend`` returning a
refusal unconditionally), the three blend tests go red and the two controls stay
green — which is the split that says the guards are measuring the change and not
the weather.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.utils.hero_probability import blend_provenance, resolve_hero
from app.utils.tournament_slate import (
    PRICE_BASIS_BLEND,
    PRICE_BASIS_VENUE,
    build_slate,
    orient_event_blend,
)

from tests.test_tournament_slate import NOW, _matchup, _prices, _register

#: The production fixture, verbatim. `events` row 15306225 is the Tiafoe /
#: Michelsen quarter-final; the four probabilities are the ones the two APIs
#: served at 07:2xZ on 2026-09-08.
EVENT_ID = 15306225
KALSHI, BETTING, POLYMARKET = 0.595, 0.5764, 0.605
VENUE_NOW, VENUE_OPEN = 0.595, 0.605  # what the hub priced from: Kalshi alone
EVENT_OPEN_HOME = 0.5764


def _event(**overrides):
    """An object shaped like the `events` row the route selects.

    A `SimpleNamespace` rather than a model because `resolve_hero` reads every
    input through `getattr(..., default)` precisely so an ORM object, a SQLAlchemy
    `Row` and a stub are the same thing to it — that is the property that lets
    the hub and the page share one cascade at all.
    """
    row = {
        "id": EVENT_ID,
        "home_team": "Clara Burel",
        "away_team": "Yexin Ma",
        "status": "scheduled",
        "home_score": None,
        "away_score": None,
        "completed_at": None,
        "espn_win_prob_home": None,
        "opening_home_probability": EVENT_OPEN_HOME,
        "opening_away_probability": round(1.0 - EVENT_OPEN_HOME, 4),
        "win_probability_sources": {
            "kalshi": {"value": KALSHI, "type": "market"},
            "betting": {"value": BETTING, "type": "market"},
            "polymarket": {"value": POLYMARKET, "type": "market"},
        },
    }
    row.update(overrides)
    return SimpleNamespace(**row)


def _blend_entry(event=None):
    """The plain dict the route hands the builder, built by the route's own rule."""
    event = event if event is not None else _event()
    hero = resolve_hero(event)
    assert hero is not None, "fixture must resolve a hero or the test proves nothing"
    count, _freshest = blend_provenance(event)
    return {
        event.id: {
            "home_name": event.home_team,
            "away_name": event.away_team,
            "home_probability": hero.home_probability,
            "away_probability": hero.away_probability,
            "source": hero.source,
            "source_count": count,
            "opening_home_probability": event.opening_home_probability,
            "opening_away_probability": event.opening_away_probability,
        }
    }


def _linked_register():
    """The canonical register, with its one matchup pinned to our event."""
    return _register(matchups=[_matchup(event_id=EVENT_ID)])


def _venue_prices():
    """The hub's own quote: Kalshi alone, 0.595 / 0.415, opening 0.605 / 0.395.

    Deliberately DIFFERENT from the blend on both the level and the direction —
    0.589 after the vig, moving DOWN 1.6 — so a row that merely kept its venue
    numbers cannot accidentally satisfy a blend assertion.
    """
    return _prices(a_now=0.595, b_now=0.415, a_open=0.605, b_open=0.395)


def _the_row(register, prices, blends):
    slate = build_slate(register, prices=prices, now=NOW, blends=blends)
    # THE VACUITY GATE. Everything below reads a row off this list.
    assert slate["count"] == 1, f"no row built; dropped={slate.get('dropped')}"
    return slate["matches"][0]


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------


def test_the_hub_row_prints_the_number_the_event_page_prints():
    """The acceptance criterion's first half, against the page's OWN function."""
    event = _event()
    row = _the_row(_linked_register(), _venue_prices(), _blend_entry(event))

    assert row["price_basis"] == PRICE_BASIS_BLEND
    assert row["blend_refusal"] is None

    page = resolve_hero(event)
    assert row["sides"][0]["probability"] == pytest.approx(page.home_probability)
    assert row["sides"][1]["probability"] == pytest.approx(page.away_probability)

    # And the venue number it replaced is genuinely a different number, or this
    # test would pass on a tree that changed nothing at all.
    assert row["sides"][0]["probability"] != pytest.approx(
        VENUE_NOW / (VENUE_NOW + 0.415)
    )


def test_the_move_arrow_agrees_in_sign_with_the_event_page():
    """The symptom that made #3903 a p1: −2 on the hub, +2 on the page."""
    row = _the_row(_linked_register(), _venue_prices(), _blend_entry())

    assert row["price_basis"] == PRICE_BASIS_BLEND
    home = row["sides"][0]
    assert home["opening_probability"] == pytest.approx(EVENT_OPEN_HOME)
    # The page's arrow: 0.595 against an open of 0.5764, so UP.
    assert home["move"] > 0, "the hub must not point down while the page points up"
    # The venue basis pointed the other way. Stated as its own assertion so the
    # test names the inversion rather than implying it.
    assert VENUE_NOW / (VENUE_NOW + 0.415) - VENUE_OPEN / (VENUE_OPEN + 0.395) < 0


def test_the_row_says_how_many_sources_fed_its_number():
    """`source_count: 1` beside an `event_id` was the payload-level tell."""
    row = _the_row(_linked_register(), _venue_prices(), _blend_entry())
    assert row["price_basis"] == PRICE_BASIS_BLEND
    assert row["source_count"] == 3


# ---------------------------------------------------------------------------
# The controls — what this must NOT change
# ---------------------------------------------------------------------------


def test_a_match_with_no_linked_event_is_untouched():
    """The acceptance criterion's second half, and the obvious over-reach."""
    row = _the_row(_register(), _venue_prices(), _blend_entry())

    assert row["event_id"] is None
    assert row["price_basis"] == PRICE_BASIS_VENUE
    assert row["source_count"] == 1
    # The venue's own de-vigged pair, unchanged: 0.595 / 1.01.
    assert row["sides"][0]["probability"] == pytest.approx(0.589109, abs=1e-5)
    assert row["sides"][0]["move"] < 0


def test_an_event_with_no_opening_keeps_the_venue_basis():
    """Half a blend is refused: a mixed basis is what inverted the arrow.

    Live case on the day this shipped — Andreeva/Vondrousova (15307447) served a
    hero and no `opening_odds`.
    """
    event = _event(opening_home_probability=None, opening_away_probability=None)
    row = _the_row(_linked_register(), _venue_prices(), _blend_entry(event))

    assert row["price_basis"] == PRICE_BASIS_VENUE
    assert row["blend_refusal"] == "BLEND_HAS_NO_OPEN"
    # It kept a COMPLETE venue pair rather than losing its arrow.
    assert row["sides"][0]["probability"] == pytest.approx(0.589109, abs=1e-5)
    assert row["sides"][0]["move"] is not None


# ---------------------------------------------------------------------------
# Orientation — the step that can put a number under the wrong player's name
# ---------------------------------------------------------------------------


def test_a_swapped_event_is_turned_to_face_the_rows_own_side_order():
    """`home_team` is not required to be the register's first side."""
    event = _event(home_team="Yexin Ma", away_team="Clara Burel")
    hero = resolve_hero(event)
    current, opening, refusal = orient_event_blend(
        {
            "home_name": event.home_team,
            "away_name": event.away_team,
            "home_probability": hero.home_probability,
            "away_probability": hero.away_probability,
            "opening_home_probability": event.opening_home_probability,
            "opening_away_probability": event.opening_away_probability,
        },
        ["Clara Burel", "Yexin Ma"],
    )
    assert refusal is None
    # Burel is the event's AWAY side, so she takes the away number.
    assert current[0] == pytest.approx(hero.away_probability)
    assert current[1] == pytest.approx(hero.home_probability)
    assert opening[0] == pytest.approx(round(1.0 - EVENT_OPEN_HOME, 4))


@pytest.mark.parametrize(
    "blend, side_names, expected",
    [
        (None, ["Clara Burel", "Yexin Ma"], "NO_BLEND"),
        ({"home_name": "", "away_name": "Yexin Ma"}, ["Clara Burel", "Yexin Ma"],
         "EVENT_SIDES_UNNAMED"),
        ({"home_name": "Clara Burel", "away_name": "Yexin Ma"}, ["Clara Burel", ""],
         "ROW_SIDES_UNNAMED"),
        ({"home_name": "Carlos Alcaraz", "away_name": "Jannik Sinner"},
         ["Clara Burel", "Yexin Ma"], "BLEND_ORIENTATION_UNCLEAR"),
    ],
)
def test_orientation_refuses_by_name_rather_than_guessing(blend, side_names, expected):
    """A number under the wrong player's name is the worst defect here.

    The blank-name cases are the ones worth the parametrize: `names_agree` is a
    MATCHER and documents that an empty name agrees with ANYTHING, which is right
    for deciding whether to withhold a fixture and catastrophic for deciding whose
    number this is. A blank `home_team` fits both slots.
    """
    assert orient_event_blend(blend, side_names)[2] == expected


def test_an_unpriced_row_is_not_given_a_number_it_never_had():
    """The bound on the overlay: this ship changes numbers, not which cards exist.

    A registered fixture nobody quotes yet (UX-P142) — no live source block at
    all, which is the whole main draw four days out. The linked event has a
    perfectly good blend; the row still renders with no number on it, because
    turning an unpriced card into a priced one changes which cards EXIST and is a
    different ship with a different blast radius.
    """
    register = _register(matchups=[_matchup(event_id=EVENT_ID, sources=[])])
    row = _the_row(register, {}, _blend_entry())

    assert row["priced"] is False
    assert row["price_basis"] == PRICE_BASIS_VENUE
    assert row["sides"][0]["probability"] is None
    assert row["price_state"] == "unpriced"
