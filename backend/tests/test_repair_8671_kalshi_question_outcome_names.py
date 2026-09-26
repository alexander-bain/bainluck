"""#8671 — the repair renames a leg only when the venue still vouches for it."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from app.services.kalshi_api import KalshiEvent, KalshiMarket  # noqa: E402
from repair_8671_kalshi_question_outcome_names import (  # noqa: E402
    Refused,
    StoredLeg,
    plan_event,
    refuse_unless_production,
)

EVENT = "KXALBUMRELEASEDATEFRANK"
TITLE = "When will Frank Ocean release a new album?"


def _market(leg: str, year: str, *, yes_sub_title=None) -> KalshiMarket:
    return KalshiMarket(
        ticker=f"{EVENT}-JAN01-{leg}",
        event_ticker=EVENT,
        title=f"Will Frank Ocean release a new album in {year}?",
        yes_sub_title=year if yes_sub_title is None else yes_sub_title,
        status="active",
    )


def _event(*markets) -> KalshiEvent:
    return KalshiEvent(event_ticker=EVENT, title=TITLE, markets=list(markets))


def _leg(oid: int, leg: str, name: str) -> StoredLeg:
    return StoredLeg(oid, 112760, EVENT, f"{EVENT}-JAN01-{leg}", name)


def test_a_leg_frozen_on_its_markets_question_takes_the_ladders_name():
    """Production specimen, venue-read 2026-09-26: stored as the question, ladder says the year."""
    venue = _event(_market("27", "2026"), _market("28", "2027"))
    legs = [
        _leg(1, "27", "Will Frank Ocean release a new album in 2026?"),
        _leg(2, "28", "Will Frank Ocean release a new album in 2027?"),
    ]
    renames, skips = plan_event(legs, venue)
    assert renames == [
        (1, "Will Frank Ocean release a new album in 2026?", "2026"),
        (2, "Will Frank Ocean release a new album in 2027?", "2027"),
    ]
    assert skips == []


def test_a_real_name_ending_in_a_question_mark_is_never_touched():
    """'Is It Cool?' is the venue's yes_sub_title, not the market title: leave it."""
    venue = _event(
        _market("27", "2026", yes_sub_title="Is It Cool?"),
        _market("28", "2027"),
    )
    renames, skips = plan_event([_leg(1, "27", "Is It Cool?")], venue)
    assert renames == []
    assert skips == [(1, "stored name is not the market's question")]


@pytest.mark.parametrize(
    "venue, reason",
    [
        (None, "venue unreadable"),
        (_event(), "venue purged its markets"),
        (_event(_market("28", "2027")), "leg not listed by the venue"),
    ],
)
def test_without_the_venue_nothing_is_inferred(venue, reason):
    """KXFEDCHAIRCOUNT-27's markets are purged: no ticker-leg guess is written."""
    leg = _leg(1, "27", "Will Frank Ocean release a new album in 2026?")
    assert plan_event([leg], venue) == ([], [(1, reason)])


def test_a_ladder_that_hands_the_title_back_writes_nothing():
    """Two legs whose only distinct candidate is the title: nothing better exists."""
    a = _market("27", "2026", yes_sub_title="")
    b = _market("28", "2027", yes_sub_title="")
    renames, skips = plan_event(
        [_leg(1, "27", "Will Frank Ocean release a new album in 2026?")], _event(a, b)
    )
    assert (renames, skips) == ([], [(1, "ladder gives the same name")])


def test_a_real_name_ending_in_a_question_mark_replaces_the_question():
    """Stored as the title, venue names it 'Is It Cool?': the song title is the answer."""
    venue = _event(
        _market("27", "2026", yes_sub_title="Is It Cool?"),
        _market("28", "2027"),
    )
    renames, _ = plan_event(
        [_leg(1, "27", "Will Frank Ocean release a new album in 2026?")], venue
    )
    assert renames == [(1, "Will Frank Ocean release a new album in 2026?", "Is It Cool?")]


def test_refuses_off_production():
    with pytest.raises(Refused):
        refuse_unless_production({"HEROKU_APP_NAME": "bainluck-staging"})
    refuse_unless_production({"HEROKU_APP_NAME": "bainluck-heavy"})
