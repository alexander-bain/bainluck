"""#3729 — the US Open quarterfinals stop rendering blank while we hold a price.

Measured on production ``GET /api/tournaments/us-open`` at 2026-09-07T00:35:47Z:
**13 slate rows, 11 priced, and the two blanks were the two quarterfinals** —
the most advanced matches in the tournament.

| row | slate said | its own match page said |
|---|---|---|
| Sabalenka v Noskova (`event_id 15306160`) | `priced: false`, `unpriced` | 69% - 31%, 7 books |
| Tiafoe v Michelsen (`event_id 15306225`) | `priced: false`, `unpriced` | 58%, 4 books |

Not cache lag: the payload's ``generated_at`` was 00:35:47Z and the two events'
``betting`` readings were stamped 00:33:38Z and 00:34:57Z — the payload was
built AFTER the numbers existed and still reported them unpriced.

The values in this file are those two production rows, read out of ``events``
with the admin query in the same minute.

WHAT THIS PINS, beyond the two rows: a quarterfinal's prediction market cannot
be pinned until its round-of-16 feeders resolve, so the pinned market always
arrives last while the books quote the pairing the moment it is known. A rule
that only counts a pinned market therefore blanks the deepest round of every
tournament, every time — which is why the fill is a rung and the refusals are
named rather than silent.
"""

from datetime import datetime, timedelta, timezone

from app.utils.aggregation import compute_aggregate_probability
from app.utils.tournament_slate import (
    UNPRICED_NO_EVENT_LINK,
    UNPRICED_NO_EVENT_READING,
    UNPRICED_NO_EVENT_ROW,
    UNPRICED_ORIENTATION_AMBIGUOUS,
    apply_event_blend_slate,
    event_blend_view,
)


NOW = datetime(2026, 9, 7, 0, 35, 47, tzinfo=timezone.utc)
BETTING_AT = datetime(2026, 9, 7, 0, 33, 38, tzinfo=timezone.utc)

SABALENKA = "espn:athlete:1000001"
NOSKOVA = "espn:athlete:1000002"

class _Event:
    """The `events` columns the hero reads — and nothing else.

    A plain object rather than a mock: `compute_aggregate_probability` is
    documented to work on anything carrying these attributes, and every test
    below goes through the REAL function, so a change to the blend that would
    move the event page's hero moves this card's number in the same commit.
    """

    def __init__(self, **over):
        self.id = 15306160
        self.status = "scheduled"
        self.home_team_name = "Aryna Sabalenka"
        self.away_team_name = "Linda Noskova"
        self.opening_home_probability = 0.6992
        self.opening_away_probability = 0.3008
        self.espn_win_prob_home = None
        self.win_probability_sources = {
            "betting": {"value": 0.6992, "updated_at": BETTING_AT.isoformat()},
            "betting_book_count": 7,
        }
        for key, value in over.items():
            setattr(self, key, value)


def _view(**over):
    """What the route hands the rung, built by the code the route calls."""
    return {15306160: event_blend_view(_Event(**over))}


def _side(entity_key, display_name):
    """A blank side, exactly as `authority_match_row` publishes one."""
    return {
        "entity_key": entity_key,
        "display_name": display_name,
        "seed": None,
        "country": "BLR",
        "image": {"url": None, "flag_url": None},
        "role": "contender",
        "probability": None,
        "opening_probability": None,
        "move": None,
        "raw_probability": None,
        "raw_opening_probability": None,
        "observed_at": None,
        "age_hours": None,
        "price_state": "unpriced",
        "liquidity": "unknown",
        "liquidity_reasons": [],
    }


def _slate(**over):
    """The served shape of the blank quarterfinal row."""
    row = {
        "priced": False,
        "matchup_key": "espn:182533",
        "event_id": 15306160,
        "draw": "womens-singles",
        "round": "QF",
        "scheduled_date": "2026-09-08T04:00:00+00:00",
        "live_state": "upcoming",
        "sides": [_side(SABALENKA, "Aryna Sabalenka"), _side(NOSKOVA, "Linda Noskova")],
        "coherent": False,
        "raw_sum": None,
        "opening_raw_sum": None,
        "probability_is_live": False,
        "price_state": "unpriced",
        "observed_at": None,
        "age_hours": None,
        "freshest_observed_at": None,
        "freshest_age_hours": None,
        "stale_sides": [],
        "mixed_freshness": False,
        "favourite": None,
        "has_moved": False,
        "source_count": 0,
        "liquidity": "unknown",
        "liquidity_reasons": [],
        "pairing_source": "scoreboard",
    }
    row.update(over.pop("row", {}))
    slate = {
        "matches": [row],
        "count": 1,
        "scoreboard_pairings": 1,
        "scoreboard_priced": 0,
        "scoreboard_linked": 1,
        "books_priced": 0,
        "price_state": "unpriced",
        "newest_observed_at": None,
        "age_hours": None,
    }
    slate.update(over)
    return slate


def _apply(slate, rows_by_event=None, now=NOW):
    if rows_by_event is None:
        rows_by_event = _view()
    filled = apply_event_blend_slate(slate, rows_by_event=rows_by_event, now=now)
    return filled, slate["matches"][0]


def test_the_quarterfinal_alex_would_have_read_now_shows_sixty_nine_percent():
    """The headline acceptance, on the numbers production actually held."""
    filled, row = _apply(_slate())

    assert filled == 1
    assert row["priced"] is True
    by_key = {s["entity_key"]: s for s in row["sides"]}
    assert round(by_key[SABALENKA]["probability"] * 100) == 70
    assert round(by_key[NOSKOVA]["probability"] * 100) == 30
    assert row["favourite"] == SABALENKA
    assert row["coherent"] is True


def test_the_number_says_where_it_came_from():
    """One page, one vocabulary: the finished list already marks a books number."""
    _, row = _apply(_slate())

    assert row["price_source"] == "books"


def test_a_fresh_books_reading_is_live_and_carries_its_own_clock():
    """The reading's own stamp, not the request clock — 2m9s old here."""
    _, row = _apply(_slate())

    assert row["price_state"] == "live"
    assert row["probability_is_live"] is True
    assert row["observed_at"] == BETTING_AT.isoformat()
    assert row["age_hours"] == 0.04
    assert row["stale_sides"] == []
    assert row["mixed_freshness"] is False


def test_a_stale_books_reading_is_dark_and_says_so_on_both_sides():
    """A pair quoted from one place cannot be fresh on one side and stale on the other."""
    old = BETTING_AT - timedelta(days=2)
    _, row = _apply(
        _slate(),
        rows_by_event=_view(
            win_probability_sources={
                "betting": {"value": 0.6992, "updated_at": old.isoformat()}
            }
        ),
    )

    assert row["priced"] is True
    assert row["price_state"] == "dark"
    assert row["probability_is_live"] is False
    assert sorted(row["stale_sides"]) == sorted([SABALENKA, NOSKOVA])


def test_the_script_rides_with_the_divergence():
    """`move` is computed from the row's own two numbers, as on a market row."""
    _, row = _apply(
        _slate(),
        rows_by_event=_view(
            win_probability_sources={
                "betting": {"value": 0.74, "updated_at": BETTING_AT.isoformat()}
            }
        ),
    )

    by_key = {s["entity_key"]: s for s in row["sides"]}
    assert by_key[SABALENKA]["opening_probability"] == 0.6992
    assert round(by_key[SABALENKA]["move"], 4) == round(0.74 - 0.6992, 4)
    assert round(by_key[NOSKOVA]["move"], 4) == round(0.26 - 0.3008, 4)
    assert row["has_moved"] is True


def test_a_pinned_prediction_market_is_never_displaced():
    """The ladder is ordered: a books number must not overwrite a Kalshi one."""
    filled, row = _apply(
        _slate(row={"priced": True, "price_state": "live", "coherent": True})
    )

    assert filled == 0
    assert "price_source" not in row
    assert row["sides"][0]["probability"] is None  # untouched, whatever it held


def test_an_absent_betting_key_refuses_rather_than_printing_the_opening():
    """Ruling 051 / #1829: the key is DROPPED when the books pull the line.

    Falling back to `opening_*` here would print a number from an hour the
    market has since abandoned — the frozen reading that rendered 87-13 for a
    team trailing 5-0 in the 9th, wearing a fresh row's clothes.
    """
    filled, row = _apply(
        _slate(), rows_by_event=_view(win_probability_sources={"betting_book_count": 0})
    )

    assert filled == 0
    assert row["priced"] is False
    assert row["unpriced_reason"] == UNPRICED_NO_EVENT_READING
    assert row["sides"][0]["probability"] is None


def test_a_settled_endpoint_is_not_a_forecast():
    """0 and 1 are a settled price that leaked backwards, not a 100% claim."""
    filled, row = _apply(
        _slate(),
        rows_by_event=_view(
            win_probability_sources={
                "betting": {"value": 1.0, "updated_at": BETTING_AT.isoformat()}
            }
        ),
    )

    assert filled == 0
    assert row["unpriced_reason"] == UNPRICED_NO_EVENT_READING


def test_the_orientation_must_be_a_bijection():
    """69% on the wrong player is wrong in the most confident possible way."""
    # Both event names answer to one side.
    filled, row = _apply(_slate(), rows_by_event=_view(away_team_name="Aryna Sabalenka"))

    assert filled == 0
    assert row["unpriced_reason"] == UNPRICED_ORIENTATION_AMBIGUOUS
    assert all(s["probability"] is None for s in row["sides"])


def test_an_unrelated_event_row_does_not_price_this_match():
    """Neither name lands, so nothing is filled — a doubles row's usual outcome."""
    filled, row = _apply(
        _slate(),
        rows_by_event=_view(
            home_team_name="Carlos Alcaraz", away_team_name="Jannik Sinner"
        ),
    )

    assert filled == 0
    assert row["unpriced_reason"] == UNPRICED_ORIENTATION_AMBIGUOUS


def test_every_refusal_names_itself():
    """gotcha #53: "no market pinned", "no link" and "no row" were one silence."""
    _, unlinked = _apply(_slate(row={"event_id": None}), rows_by_event={})
    assert unlinked["unpriced_reason"] == UNPRICED_NO_EVENT_LINK

    _, unresolved = _apply(_slate(), rows_by_event={})
    assert unresolved["unpriced_reason"] == UNPRICED_NO_EVENT_ROW


def test_a_filled_row_carries_no_stale_refusal():
    """The reason is about the row as served, so it must not survive the fill."""
    slate = _slate(row={"unpriced_reason": UNPRICED_NO_EVENT_ROW})
    _, row = _apply(slate)

    assert "unpriced_reason" not in row


def test_the_counters_cannot_claim_a_gap_the_card_does_not_have():
    """`scoreboard_pairings - scoreboard_priced` is ux/1033's live alarm.

    Filling rows and leaving the counts alone would publish that alarm at its
    maximum while every row on the card carried a number.
    """
    slate = _slate()
    apply_event_blend_slate(slate, rows_by_event=_view(), now=NOW)

    assert slate["scoreboard_priced"] == 1
    assert slate["scoreboard_pairings"] == 1
    assert slate["books_priced"] == 1


def test_books_priced_is_zero_and_never_absent_when_nothing_filled():
    """An absent count and a genuine zero are the same bytes to a reader."""
    slate = _slate()
    apply_event_blend_slate(slate, rows_by_event={}, now=NOW)

    assert slate["books_priced"] == 0


def test_the_slate_freshness_re_answers_after_the_fill():
    """The card's own clock must describe the rows it is actually serving."""
    slate = _slate()
    apply_event_blend_slate(slate, rows_by_event=_view(), now=NOW)

    assert slate["newest_observed_at"] == BETTING_AT.isoformat()
    assert slate["price_state"] == "live"
    assert slate["age_hours"] == 0.04


def test_the_card_prints_the_same_number_as_the_event_page_hero():
    """THE ANTI-DRIFT PIN, and the reason the rung reads a blend at all.

    #3729 is two surfaces disagreeing about one match. Filling the card from
    one hand-picked source would have fixed the blank and re-opened the
    disagreement a couple of points wide on any event carrying more than one
    reading — so the card is required to publish the hero's own answer, not a
    number that merely resembles it.
    """
    event = _Event(
        win_probability_sources={
            "betting": {"value": 0.6992, "updated_at": BETTING_AT.isoformat()},
            "kalshi": {"value": 0.64, "updated_at": BETTING_AT.isoformat()},
            "espn": {"value": 0.71, "updated_at": BETTING_AT.isoformat()},
        }
    )
    hero = compute_aggregate_probability(event, event.status)
    _, row = _apply(_slate(), rows_by_event={15306160: event_blend_view(event)})

    by_key = {s["entity_key"]: s for s in row["sides"]}
    assert by_key[SABALENKA]["probability"] == hero
    assert by_key[NOSKOVA]["probability"] == round(1 - hero, 6)


def test_a_blend_a_prediction_market_fed_wears_no_books_marker():
    """`books` is a claim about where the number came from, not a badge."""
    _, row = _apply(
        _slate(),
        rows_by_event=_view(
            win_probability_sources={
                "betting": {"value": 0.6992, "updated_at": BETTING_AT.isoformat()},
                "kalshi": {"value": 0.64, "updated_at": BETTING_AT.isoformat()},
            }
        ),
    )

    assert row["priced"] is True
    assert "price_source" not in row


def test_the_hero_may_fall_back_to_the_opening_and_this_row_may_not():
    """The one place the two surfaces are allowed to differ, and why.

    `compute_aggregate_probability`'s tier 3 IS `opening_home_probability`, so
    the hero still renders a number for an event with no live reading. A slate
    row printing it would be publishing an opening inside freshness fields that
    say how recent it is — the frozen number in a new place (ruling 051).
    """
    event = _Event(win_probability_sources={})
    assert compute_aggregate_probability(event, event.status) is not None

    filled, row = _apply(_slate(), rows_by_event={15306160: event_blend_view(event)})

    assert filled == 0
    assert row["unpriced_reason"] == UNPRICED_NO_EVENT_READING


def test_an_unstamped_reading_renders_dark_rather_than_claiming_freshness():
    """The legacy bare-float shape carries no write time — so we claim none."""
    _, row = _apply(_slate(), rows_by_event=_view(win_probability_sources={"betting": 0.6992}))

    assert row["priced"] is True
    assert row["price_state"] == "dark"
    assert row["observed_at"] is None
    assert row["age_hours"] is None
