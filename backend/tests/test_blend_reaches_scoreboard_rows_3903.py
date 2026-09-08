"""THE HUB ROW THE US OPEN ACTUALLY RENDERS GETS THE EVENT'S NUMBER TOO.

ux/1127 · PILLAR: TRUTH · SHIP: tapping a match on the US Open hub no longer
changes the percentage or flips the move arrow — on the rows a Slam day is
actually made of.

═══ WHY THERE IS A SECOND #3903 FILE ═══

#3903 shipped, was reviewed twice (CERT-2234 GREEN, CERT-2235 BLOCK, CERT-2241
GREEN on the repair), merged, deployed — and changed nothing a reader could see.
Measured on production at 10:48-10:50Z on 2026-09-08, read six times to be sure
it was stable and not a mid-restart frame::

    price_basis     "venue" on all 8 quarter-finals
    blend_refusal   null on all 8
    openings        5 of 7 still disagreeing with the event page
    arrows          2 of 7 still pointing opposite ways

``build_match_row`` applies the blend inline and reaches every REGISTER-paired
row.  It reached none of these, and the reason is ORDERING, not scope:

    1. ``build_slate`` builds today's quarter-finals through
       ``authority_match_row`` (``pairing_source="scoreboard"``), which returns
       ``event_id: None``.
    2. ``apply_espn_event_links`` runs AFTERWARDS and backfills the ``event_id``
       onto exactly those rows.

At the moment the blend was offered the row had no event to orient onto; by the
time it had one, nothing was left to ask.  Hence ``blend_refusal: null`` beside a
venue price: not a refusal, a question never put.

═══ THE COMMENT THAT HID IT, RECORDED SO THE NEXT READER DOES NOT REPEAT IT ═══

Beside ``authority_match_row``'s static ``price_basis`` stood:

    An authority row is ALWAYS the venue basis, and the reason is structural
    rather than an omission: it exists precisely because the register's pairing
    was withheld, so there is no registered fixture to carry an ``event_id``

True of the ``authority`` pairing.  **False of the ``scoreboard`` one**, because
``apply_espn_event_links`` exists to give it an ``event_id`` and does.  One
function serves both pairings; the justification was written for one of them and
read as covering both.

═══ WHAT THESE GUARDS DO DIFFERENTLY FROM THE FIRST FILE'S ═══

``test_tournament_slate_serves_the_event_blend_3903.py`` builds its blend map with
its own helper and hands it to ``build_slate``.  That is a real test of the
builder and it could never have caught this: the map arrives at the one call site
that already worked.

Every test below drives the REAL ordering — build the slate through the
scoreboard path, link it the way the route links it, then apply the pass — so a
regression in the SEQUENCE fails here, which is the only thing that was ever
wrong.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.tournament_register import SCHEMA_VERSION
from app.utils.tournament_slate import (
    PRICE_BASIS_BLEND,
    PRICE_BASIS_VENUE,
    apply_espn_event_links,
    apply_event_blend_to_linked_rows,
    build_slate,
)

NOW = datetime(2026, 9, 8, 10, 50, tzinfo=timezone.utc)

COMP = "182777"
EVENT_ID = 15306225
HOME, AWAY = "Frances Tiafoe", "Alex Michelsen"
HOME_ID, AWAY_ID = 2708, 5992

#: The venue's own quote, and the event's. Deliberately different on BOTH the
#: level and the direction, so a row that kept its venue numbers cannot pass a
#: blend assertion by coincidence: venue 0.575 moving DOWN from 0.605, event
#: 0.5900 moving UP from 0.5764.
VENUE_NOW, VENUE_OPEN = 0.575, 0.605
EVENT_NOW, EVENT_OPEN = 0.59, 0.5764


def _competitor(name, athlete_id, order):
    """One side of an ESPN competition, in ``_competitor_view``'s shape."""
    return {
        "name": name,
        "espn_athlete_id": athlete_id,
        "flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/usa.png",
        "country": "USA",
        "determined": True,
        "order": order,
    }


def _order_of_play():
    competitors = [_competitor(HOME, HOME_ID, 1), _competitor(AWAY, AWAY_ID, 2)]
    return {
        COMP: {
            "espn_competition_id": COMP,
            "draw": "mens-singles",
            "state": "in_progress",
            "start_at": "2026-09-08T17:00:00+00:00",
            "start_is_tbd": False,
            "status_detail": "1st Set",
            "espn_round": "Quarterfinal",
            "players": [c["name"] for c in competitors],
            "competitors": competitors,
        }
    }


def _link():
    return {
        f"espn:{COMP}|kalshi": {
            "source": "kalshi",
            "kind": "match",
            "market_id": 61000001,
            "outcome_id": 910001,
            "status": "live",
            "sides": {
                f"espn:athlete:{HOME_ID}": {"outcome_id": 910001},
                f"espn:athlete:{AWAY_ID}": {"outcome_id": 910002},
            },
        }
    }


def _prices():
    at = NOW - timedelta(minutes=1)
    return {
        910001: {
            "probability": VENUE_NOW,
            "opening_probability": VENUE_OPEN,
            "observed_at": at,
        },
        910002: {
            "probability": round(1 - VENUE_NOW, 4),
            "opening_probability": round(1 - VENUE_OPEN, 4),
            "observed_at": at,
        },
    }


def _register():
    """A register with NO matchups — the scoreboard is the only source of rows.

    This is the shape that matters: it is why these rows come out of
    ``authority_match_row`` with ``event_id: None`` and pick one up later.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "tournament": "us-open",
        "season": "2026",
        "version": 14,
        "generated_at": NOW.isoformat(),
        "draw_released": True,
        "players": [],
        "matchups": [],
    }


def _blends(**overrides):
    """The map ``_load_blends`` returns for our event."""
    entry = {
        "home_name": HOME,
        "away_name": AWAY,
        "home_probability": EVENT_NOW,
        "away_probability": round(1 - EVENT_NOW, 4),
        "source": "blend",
        "source_count": 3,
        "opening_home_probability": EVENT_OPEN,
        "opening_away_probability": round(1 - EVENT_OPEN, 4),
    }
    entry.update(overrides)
    return {EVENT_ID: entry}


def _slate():
    """Built exactly as the route builds the first screen."""
    return build_slate(
        _register(),
        prices=_prices(),
        now=NOW,
        order_of_play=_order_of_play(),
        order_of_play_complete=True,
        authority_links=_link(),
        # The route passes the blends it has AT BUILD TIME. Ours cannot contain
        # this event: its id is not known until the linker runs, three steps
        # later. Passing `{}` here is not a simplification, it is the situation.
        blends={},
    )


def _the_row(slate):
    """The vacuity gate: every assertion below reads a row off this list."""
    rows = [r for r in slate["matches"] if r.get("pairing_source") == "scoreboard"]
    assert len(rows) == 1, f"no scoreboard row built; matches={slate['matches']}"
    return rows[0]


# ---------------------------------------------------------------------------
# The defect, reproduced
# ---------------------------------------------------------------------------


def test_a_scoreboard_row_has_no_event_at_build_time():
    """The premise. If this ever stops being true the rest is unnecessary."""
    row = _the_row(_slate())

    assert row["event_id"] is None
    assert row["price_basis"] == PRICE_BASIS_VENUE
    assert row["priced"] is True
    # And the silence that made it invisible on production: no refusal, because
    # nothing was asked.
    assert row["blend_refusal"] is None


def test_linking_alone_leaves_the_row_on_the_venue_basis():
    """What shipped on 2026-09-08 — the link lands, the number does not follow.

    This test asserts the BUG, on purpose. It is the positive control for the
    one below: without it a passing suite could not tell "the pass fixed it"
    from "there was nothing to fix".
    """
    slate = _slate()
    apply_espn_event_links(slate, {COMP: EVENT_ID})
    row = _the_row(slate)

    assert row["event_id"] == EVENT_ID
    assert row["price_basis"] == PRICE_BASIS_VENUE
    assert row["sides"][0]["probability"] == pytest.approx(VENUE_NOW)


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------


def test_the_linked_scoreboard_row_prints_the_event_page_number():
    slate = _slate()
    apply_espn_event_links(slate, {COMP: EVENT_ID})
    moved = apply_event_blend_to_linked_rows(slate, _blends())

    assert moved == 1
    row = _the_row(slate)
    assert row["price_basis"] == PRICE_BASIS_BLEND
    assert row["blend_refusal"] is None
    assert row["sides"][0]["probability"] == pytest.approx(EVENT_NOW)
    assert row["sides"][1]["probability"] == pytest.approx(1 - EVENT_NOW)
    # And it is genuinely a different number from the one it replaced.
    assert row["sides"][0]["probability"] != pytest.approx(VENUE_NOW)


def test_the_move_arrow_follows_the_event_and_can_change_direction():
    """The p1 symptom: DOWN on the hub, UP on the page, for one match."""
    slate = _slate()
    apply_espn_event_links(slate, {COMP: EVENT_ID})
    apply_event_blend_to_linked_rows(slate, _blends())
    home = _the_row(slate)["sides"][0]

    assert home["opening_probability"] == pytest.approx(EVENT_OPEN)
    # The venue said DOWN (0.575 from 0.605). The event says UP.
    assert VENUE_NOW - VENUE_OPEN < 0
    assert home["move"] == pytest.approx(EVENT_NOW - EVENT_OPEN)
    assert home["move"] > 0


def test_the_derived_fields_move_with_the_numbers():
    """`favourite` and `has_moved` were computed from the pair being replaced.

    A row naming one player the favourite while printing the larger number
    beside the other is the same two-answers-one-card defect #3903 is about,
    which is why leaving them stale would have been this fix causing the bug it
    was sent to remove.
    """
    slate = _slate()
    apply_espn_event_links(slate, {COMP: EVENT_ID})
    # An event that DISAGREES WITH THE VENUE ABOUT WHO IS WINNING — the only
    # input under which a stale `favourite` is detectable at all.
    apply_event_blend_to_linked_rows(
        slate,
        _blends(
            home_probability=0.42,
            away_probability=0.58,
            opening_home_probability=0.45,
            opening_away_probability=0.55,
        ),
    )
    row = _the_row(slate)

    assert row["sides"][0]["probability"] == pytest.approx(0.42)
    assert row["favourite"] == f"espn:athlete:{AWAY_ID}"
    assert row["has_moved"] is True


# ---------------------------------------------------------------------------
# Controls — what this pass must NOT do
# ---------------------------------------------------------------------------


def test_a_row_with_no_link_is_untouched_and_says_nothing():
    """No link, no event, no claim — and no invented refusal either."""
    slate = _slate()
    moved = apply_event_blend_to_linked_rows(slate, _blends())
    row = _the_row(slate)

    assert moved == 0
    assert row["price_basis"] == PRICE_BASIS_VENUE
    assert row["blend_refusal"] is None
    assert row["sides"][0]["probability"] == pytest.approx(VENUE_NOW)


def test_a_linked_row_whose_names_do_not_orient_says_WHY():
    """The silence this repair exists to remove must not come back by a new road.

    A row that HAS an event and still shows a venue price has to account for
    itself. `price_basis: "venue"` with `blend_refusal: null` is exactly what
    production printed, and it is unreadable.
    """
    slate = _slate()
    apply_espn_event_links(slate, {COMP: EVENT_ID})
    moved = apply_event_blend_to_linked_rows(
        slate, _blends(home_name="Someone Else", away_name="Another Person")
    )
    row = _the_row(slate)

    assert moved == 0
    assert row["price_basis"] == PRICE_BASIS_VENUE
    assert row["blend_refusal"] is not None
    assert row["sides"][0]["probability"] == pytest.approx(VENUE_NOW)


def test_a_row_already_on_the_blend_basis_is_never_displaced():
    """The inline pass is the upper rung; a second answer must not overwrite it."""
    slate = _slate()
    apply_espn_event_links(slate, {COMP: EVENT_ID})
    apply_event_blend_to_linked_rows(slate, _blends())
    first = _the_row(slate)["sides"][0]["probability"]

    # A second pass carrying a DIFFERENT answer for the same event.
    moved = apply_event_blend_to_linked_rows(
        slate, _blends(home_probability=0.11, away_probability=0.89)
    )

    assert moved == 0
    assert _the_row(slate)["sides"][0]["probability"] == pytest.approx(first)


def test_a_blank_row_built_by_the_real_builder_is_left_blank():
    """The bound as the route meets it: no prices, no numbers, no card invented.

    NOTE WHICH RAIL CATCHES THIS ONE. A builder-made unpriced row carries `None`
    on both sides, so `normalize_pair` refuses it as incoherent and the `priced`
    check never runs. That makes this a test of the OUTCOME and not of the bound;
    the bound itself is exercised by the test below, which had to hand-build a
    row because no builder emits the shape it needs.
    """
    slate = build_slate(
        _register(),
        prices={},
        now=NOW,
        order_of_play=_order_of_play(),
        order_of_play_complete=True,
        authority_links=_link(),
        blends={},
    )
    apply_espn_event_links(slate, {COMP: EVENT_ID})
    moved = apply_event_blend_to_linked_rows(slate, _blends())
    row = _the_row(slate)

    assert moved == 0
    assert row["priced"] is False
    assert row["price_basis"] == PRICE_BASIS_VENUE
    assert row["sides"][0]["probability"] is None


def test_a_coherent_but_unpriced_row_is_still_refused():
    """The `priced` bound on its own, with coherence deliberately satisfied.

    Hand-built, because nothing in `tournament_slate` currently emits a row that
    is `priced: False` and carries a coherent pair — which is exactly why this
    matters: the check is redundant TODAY and is the only thing standing between
    a future rung that fills probabilities and a card that silently becomes
    priced. `apply_event_blend_slate` (#3729) already fills numbers and sets
    `priced` itself, one rung further down this same route.

    Without this test the bound is unreachable code that no mutation can kill,
    and the docstring's claim about it would be unbacked.
    """
    slate = {
        "matches": [
            {
                "event_id": EVENT_ID,
                "priced": False,
                "price_basis": PRICE_BASIS_VENUE,
                "blend_refusal": None,
                "sides": [
                    {
                        "entity_key": f"espn:athlete:{HOME_ID}",
                        "display_name": HOME,
                        "probability": VENUE_NOW,
                        "opening_probability": VENUE_OPEN,
                        "move": round(VENUE_NOW - VENUE_OPEN, 6),
                    },
                    {
                        "entity_key": f"espn:athlete:{AWAY_ID}",
                        "display_name": AWAY,
                        "probability": round(1 - VENUE_NOW, 4),
                        "opening_probability": round(1 - VENUE_OPEN, 4),
                        "move": round(VENUE_OPEN - VENUE_NOW, 6),
                    },
                ],
            }
        ]
    }

    moved = apply_event_blend_to_linked_rows(slate, _blends())
    row = slate["matches"][0]

    assert moved == 0
    assert row["price_basis"] == PRICE_BASIS_VENUE
    assert row["sides"][0]["probability"] == pytest.approx(VENUE_NOW)
