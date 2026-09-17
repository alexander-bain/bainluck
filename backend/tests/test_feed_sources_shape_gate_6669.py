"""#6669 — the feed's `win_probability_sources` is gated by SHAPE, like the event page's.

`/api/events/{id}` has dropped non-numeric entries from this column since #4120.
`/api/feed` never got that gate: `format_event_data` assigned the raw JSONB bag
onto the wire, and the column is a grab-bag — besides readings it carries
`statpal_injuries` (an ARRAY of injury dicts) and `statpal_injuries_updated`
(an ISO STRING).

Why that is fatal rather than untidy. On the phone `FeedEventData` declares
`winProbabilitySources: [String: WinProbSource]?`, and `WinProbSource.init`
falls through to `decoder.container(keyedBy:)` — which throws on a bare array
AND on a bare string. `FeedResponse.init` decodes items with `try?` and skips a
thrower (`SkipOne`), so the card does not render wrong, it is simply **not
there**. Measured on production 2026-09-17 02:15Z against the shipped models
compiled verbatim: `served=50 decoded=49 lost=1`, the lost card being event
15310992 Botafogo–Grêmio, a completed game carrying a real `betting` price.

⭐ The gate is the SHAPE, not the key, and the difference is the whole ship.
#4120's post-deploy note reasoned that only the array was fatal because
"`WinProbValue` accepts Double or String" — that is the INNER `value` field, not
the OUTER entry. Decoding three variants of the same production payload settles
it:

    minus `statpal_injuries` only        → lost=1
    minus `statpal_injuries_updated` only → lost=1
    minus both                            → lost=0

so a key-based fix would have merged green and recovered nothing. These tests
are written against shapes for that reason: a future writer that stuffs a fourth
bookkeeping key in here is caught without anyone naming it.
"""

from datetime import datetime, timezone

import pytest

from app.utils.feed_scoring import format_event_data

# The bag exactly as production served it for event 15310992 (one injury row kept
# of the several it carried). Anchoring on the real thing rather than a sketch is
# deliberate: the defect was a shape nobody had written down.
PRODUCTION_BAG = {
    "betting": {"value": 0.9483, "updated_at": "2026-09-17T00:33:33.213532+00:00"},
    "statpal_injuries": [
        {
            "team": "Botafogo RJ",
            "type": "Injury",
            "detail": None,
            "player": "J. Barrera",
            "status": "Out",
        }
    ],
    "betting_book_count": 5,
    "statpal_injuries_updated": "2026-09-17T00:21:09.652063+00:00",
}


def _card(sources):
    """A feed card with only the fields this file is about."""
    return format_event_data(
        event_id=15310992,
        external_id="ext-15310992",
        sport_key="soccer_brazil_campeonato",
        sport_name="Brazil Campeonato",
        home_team="Botafogo",
        away_team="Grêmio",
        commence_time=datetime(2026, 9, 16, 22, 0, tzinfo=timezone.utc),
        status="completed",
        home_score=1,
        away_score=0,
        current_home_prob=0.9483,
        current_away_prob=0.0517,
        opening_home_prob=None,
        opening_away_prob=None,
        opening_favorite=None,
        win_probability_sources=sources,
        prob_source="betting",
        game_clock=None,
        period=None,
        broadcast_info=None,
        highlight_label=None,
        raw_ei=None,
        inline_tags=[],
        ended_at=None,
    )


def _served(sources):
    return _card(sources).get("win_probability_sources")


def test_the_production_bag_that_lost_the_card_serves_only_its_two_numbers():
    """The end-to-end shape of the ship, on the row that actually failed."""
    served = _served(PRODUCTION_BAG)

    assert set(served) == {"betting", "betting_book_count"}


@pytest.mark.parametrize(
    "key, value",
    [
        ("statpal_injuries", [{"team": "Botafogo RJ", "player": "J. Barrera"}]),
        ("statpal_injuries_updated", "2026-09-17T00:21:09.652063+00:00"),
        ("statpal_fixture_id", "1234567"),
        ("deep_straggler_asked_at", "2026-09-16T11:02:00+00:00"),
    ],
)
def test_a_value_the_phone_cannot_decode_never_reaches_the_wire(key, value):
    """Every non-numeric entry the column actually holds, one at a time.

    Parametrised rather than asserted as a set because each one on its own is
    sufficient to lose the whole card — that is what the three-variant decode
    measured, and a combined assertion would not have caught it.

    The four are the complete production census (2026-09-17):

        statpal_injuries         array   292 events
        statpal_injuries_updated string  292
        statpal_fixture_id       string   56
        deep_straggler_asked_at  string    3

    ⭐ The fourth is the argument for a shape gate in one line: `deep_straggler_asked_at`
    postdates #4120 and is named in none of its analysis. A fix written against
    that issue's list of keys would already be one key behind.
    """
    served = _served({"betting": 0.61, key: value})

    assert key not in served
    assert served == {"betting": 0.61}


def test_an_empty_list_and_an_empty_string_are_dropped_too():
    """Falsy is not numeric. A shape gate that leans on truthiness lets these by."""
    served = _served({"betting": 0.61, "statpal_injuries": [], "stamp": ""})

    assert served == {"betting": 0.61}


def test_a_bool_is_not_a_probability():
    """`isinstance(True, int)` is True in Python, so this is the gate's blind spot."""
    served = _served({"betting": 0.61, "some_flag": True})

    assert served == {"betting": 0.61}


def test_both_stored_shapes_of_a_real_reading_survive():
    """The column holds a bare float AND a `{"value": …}` wrapper, both live.

    The wrapper must come through UNCHANGED — its `updated_at` sibling is what
    the source rows date themselves from. A gate that rebuilt the entry as a
    bare number would pass the drop assertions and quietly strip the timestamp.
    """
    wrapper = {"value": 0.42, "updated_at": "2026-09-17T00:33:33.213532+00:00"}
    served = _served({"kalshi": 0.77, "betting": wrapper})

    assert served == {"kalshi": 0.77, "betting": wrapper}


def test_the_count_of_sportsbooks_is_numeric_and_stays():
    """Not a source, but iOS `WinProbSourceCatalog` labels the row "Sportsbooks (N)"
    from it, and #4120 kept it deliberately on the event page for that reason.
    Dropping it here would silently take the count away from the app."""
    served = _served({"betting": 0.61, "betting_book_count": 14})

    assert served["betting_book_count"] == 14


def test_a_private_key_is_not_served():
    """`_`-prefixed entries are internal bookkeeping; `events.py` skips them."""
    served = _served({"betting": 0.61, "_internal": 0.5})

    assert served == {"betting": 0.61}


def test_a_bag_with_nothing_servable_omits_the_key_entirely():
    """Not an empty dict.

    The serializer's contract is `if win_probability_sources:` — a key present
    and empty is a different statement from absent, and web readers branch on
    `if (!sources)`. Emptied-by-the-gate must land on the same side as
    never-had-any.
    """
    card = _card({"statpal_injuries": [{"player": "J. Barrera"}]})

    assert "win_probability_sources" not in card


def test_no_sources_at_all_is_unchanged():
    """The control: the gate must not invent the key on a card that had none."""
    assert "win_probability_sources" not in _card(None)
    assert "win_probability_sources" not in _card({})
