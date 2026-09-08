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


# ---------------------------------------------------------------------------
# THE REPAIR — CERT-2235, `HUB-BLEND-LOADER-USES-EVENT-NAME-COLUMNS-3903`
#
# Everything above this line drives `build_slate` with a blend dict that THIS
# FILE built, via `_blend_entry`. That is a fine test of the builder and it is
# not a test of the ship, because the route does not use `_blend_entry` — it
# uses `_load_blends`, and `_load_blends` was broken.
#
# It selected `Event.home_team` / `Event.away_team`, which are `relationship()`s
# and not columns. SQLAlchemy does not refuse that. It compiles to
#
#     SELECT events.id, teams.id = events.home_team_id AS anon_1 ...
#     FROM events, teams
#
# — a boolean comparison over a CARTESIAN product, landing in `anon_1`. So
# `row.home_team` is not the player's name, `orient_event_blend` cannot match
# either name onto a side, and every linked hub row is refused. The ship failed
# on the first screen while this file was green, because the guard injected a
# prebuilt blend BELOW the failing seam.
#
# The lesson is the same one #3892 hit tonight in the frontend and the same one
# #3920 records: a guard that rebuilds what the code does can only prove the
# rebuild self-consistent. These two tests call the real loader.

import asyncio

from app.routes.tournaments import _load_blends


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _CapturingSession:
    """Answers `execute` with prepared rows and keeps the statement it was given.

    The statement is kept because half of this defect is invisible in the rows:
    a tree that fixed the MAPPING (`row.home_team_name`) and left the SELECT on
    the relationship would satisfy any row-shaped stub while still emitting the
    cartesian join to Postgres. So the SQL is asserted too.
    """

    def __init__(self, rows):
        self._rows = rows
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _FakeResult(self._rows)


def _selected_row(event, keys):
    """A row exposing EXACTLY the result keys a SELECT of `keys` would produce.

    Not a `SimpleNamespace(**everything)`: that is what made the original guard
    hole possible. A row carrying every attribute the code MIGHT read answers
    `row.home_team` happily and hides the very mistake this test exists for. A
    real `Row` answers for the columns that were selected and raises for the
    rest, so this one does too.
    """
    return SimpleNamespace(**{k: getattr(event, k) for k in keys})


# The columns the loader must select for the names. Written out here so the
# assertion below names them, rather than reading them back off the code under
# test and agreeing with itself.
NAME_COLUMNS = ("home_team_name", "away_team_name")

ROW_KEYS = (
    "id",
    *NAME_COLUMNS,
    "status",
    "home_score",
    "away_score",
    "completed_at",
    "win_probability_sources",
    "espn_win_prob_home",
    "opening_home_probability",
    "opening_away_probability",
)


def _event_row(**overrides):
    """The `_event` fixture, renamed onto the real name columns."""
    base = _event(**overrides)
    base.home_team_name = base.home_team
    base.away_team_name = base.away_team
    return _selected_row(base, ROW_KEYS)


def test_the_loader_selects_the_name_columns_and_not_the_relationships():
    """The SQL half: no cartesian join, and the two name columns are present."""
    session = _CapturingSession([_event_row()])
    asyncio.run(_load_blends(session, [EVENT_ID]))

    assert session.statements, "the loader issued no query; the test proves nothing"
    sql = str(session.statements[0])

    for column in NAME_COLUMNS:
        assert f"events.{column}" in sql, f"{column} is not selected: {sql}"

    # The relationship's signature, asserted by what it COMPILES TO rather than
    # by the attribute name — `home_team_id` is a legitimate column and may be
    # selected one day, but this comparison never is.
    assert "= events.home_team_id" not in sql
    assert "= events.away_team_id" not in sql
    # And the cartesian product those comparisons drag in.
    assert "FROM events, teams" not in sql


def test_the_loader_maps_the_real_names_through_to_a_priced_hub_row():
    """The ship, end to end: real loader -> real builder -> the page's number.

    This is the test CERT-2235 required. It fails with `AttributeError` on a
    tree that reads `row.home_team`, because a row that never selected it does
    not have it — which is exactly what production does.
    """
    event = _event_row()
    session = _CapturingSession([event])

    blends = asyncio.run(_load_blends(session, [EVENT_ID]))

    # The mapping itself: real strings, not booleans and not None.
    entry = blends[EVENT_ID]
    assert entry["home_name"] == "Clara Burel"
    assert entry["away_name"] == "Yexin Ma"
    assert isinstance(entry["home_name"], str)

    # And through the builder, which is where the names have to land for the
    # orientation to resolve at all.
    row = _the_row(_linked_register(), _venue_prices(), blends)

    assert row["blend_refusal"] is None, (
        "the loader's names did not orient onto the row's sides"
    )
    assert row["price_basis"] == PRICE_BASIS_BLEND

    page = resolve_hero(event)
    assert page is not None
    assert row["sides"][0]["probability"] == pytest.approx(page.home_probability)
    assert row["sides"][1]["probability"] == pytest.approx(page.away_probability)

    # The control that makes the assertion above mean something: the venue's own
    # number is genuinely different, so a row that kept it would fail here.
    assert row["sides"][0]["probability"] != pytest.approx(
        VENUE_NOW / (VENUE_NOW + 0.415)
    )
