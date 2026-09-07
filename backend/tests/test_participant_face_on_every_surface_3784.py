"""#3784 — the shared event card gets the same face the feed card already draws.

#2919 gave `/api/feed` a pinned, verified headshot-or-flag per participant and
shipped it to exactly ONE renderer.  `_format_event` — the base for
`/api/events`, `/api/events/search` and the detail route, and therefore for the
shared `components/EventCard` behind `/sports/[key]`, `/search`, `/my-stuff`,
`/preferences` and the league rails — never got it.

Measured on production `ce783c6e`, 2026-09-07, during the US Open: the same
event (15304939, Medvedev v Tiafoe) carried a Wikipedia headshot and an ESPN
flag on `/api/feed` and had **no image key of any kind** on `/api/events`, and
`/sports/tennis_atp_us_open` at 390px drew a grey initials square on every card
— `FC`, `AB`, `KK`, `LT`, `AG`, `BV`.

What is pinned here is the property, not the prose:

  * an individual-sport fixture serves all four keys, so the shared card can
    draw the face;
  * a TEAM fixture serves none of them — a club must never wear a headshot, and
    four nulls per row on a 500-row MLB list is bytes that can never carry an
    answer (the same call `linescore` above it already makes);
  * `_format_event` and the feed's `participant_images_for_event` AGREE for one
    event, which is the regression that let the two cards drift apart in the
    first place;
  * a player the register has never heard of still renders initials — the
    honest fallback, and the one already on screen.

Every guard carries BOTH arms.  "The key is absent" alone passes for a
formatter that has been reduced to serving nothing.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models import Event, Sport
from app.routes.events import _format_event
from app.utils import participant_images as pi
from app.utils.participant_images import participant_images_for_event

#: The four keys, together, always.  Named once so a guard cannot drift from
#: the helper by asserting three of them.
FACE_KEYS = (
    "home_image_url",
    "away_image_url",
    "home_flag_url",
    "away_flag_url",
)

ATP = "tennis_atp_us_open"

#: Two of the players Alex's tour page drew as `KK` and `LT`.  Register
#: spellings — this guard is about the wire, not about name canonicalisation,
#: which `test_participant_images_1052.py` already owns.
KHACHANOV = "Karen Khachanov"
TIEN = "Learner Tien"

#: The control arm, and it is a real one: of the eight players on the 2026-09-07
#: screenshot this is the only one the register cannot answer for, so it is the
#: fixture that proves initials survive rather than a name invented to fail.
UNREGISTERED = "Arthur Gea"


@pytest.fixture(autouse=True)
def _clean_cache():
    pi.reset_index_cache()
    yield
    pi.reset_index_cache()


def _event(sport_key=ATP, home=KHACHANOV, away=TIEN, **kwargs):
    sport = Sport(id=1, key=sport_key, name=sport_key)
    return Event(
        id=15304939,
        sport_id=1,
        sport=sport,
        home_team_name=home,
        away_team_name=away,
        commence_time=datetime(2026, 9, 7, 20, 0, tzinfo=timezone.utc),
        status="scheduled",
        home_score=None,
        away_score=None,
        **kwargs,
    )


# ── the ship ───────────────────────────────────────────────────────────────


def test_a_tennis_card_payload_carries_the_players_face():
    """The defect, stated positively.  Before #3784 this dict had no key
    containing the word `image` at all."""
    data = _format_event(_event())

    assert data["home_image_url"], "Khachanov has a pinned face in the register"
    assert data["away_image_url"], "Tien has a pinned face in the register"
    assert data["home_image_url"].startswith("http")


def test_all_four_keys_are_served_together_for_an_individual_sport():
    """Within the population where the question is meaningful, absence must not
    be reachable: a client cannot tell "no photo of this player" from "this
    payload predates the field" unless the keys are unconditional here."""
    data = _format_event(_event())

    for key in FACE_KEYS:
        assert key in data, f"{key} missing — a client cannot read an absent key"


def test_a_flag_alone_still_beats_two_letters():
    """42 of 378 registered players have a flag and no face (measured
    2026-09-03).  A card that only draws the face throws those away."""
    data = _format_event(_event())

    assert data["home_flag_url"], "Khachanov has a flag"
    assert data["away_flag_url"], "Tien has a flag"


# ── the absence arms, which outnumber the ship on purpose ──────────────────


def test_a_team_sport_carries_no_face_key_at_all():
    """A club must never wear somebody's headshot, and an MLB list must not pay
    four nulls a row for a question that has no answer in it."""
    data = _format_event(
        _event(
            sport_key="baseball_mlb",
            home="Los Angeles Dodgers",
            away="Washington Nationals",
        )
    )

    for key in FACE_KEYS:
        assert key not in data, f"{key} served on a team fixture"


def test_an_unregistered_player_keeps_initials():
    """The control arm.  The key is PRESENT (so the client knows we looked) and
    the value is None (so the card falls through to initials)."""
    data = _format_event(_event(home=UNREGISTERED, away=TIEN))

    assert "home_image_url" in data
    assert data["home_image_url"] is None
    assert data["home_flag_url"] is None
    # ...and the sibling on the same card is unaffected, which is what makes
    # this a per-participant fallback rather than a per-card one.
    assert data["away_image_url"]


def test_an_event_with_no_sport_does_not_raise():
    """`event.sport` is nullable on this model and the formatter is on the hot
    path of every list endpoint.  A face is a nicety; a 500 is not."""
    event = _event()
    event.sport = None

    data = _format_event(event)

    for key in FACE_KEYS:
        assert key not in data


# ── the agreement guard the acceptance asks for ────────────────────────────


def test_the_shared_card_and_the_feed_card_agree_about_the_same_match():
    """THE REGRESSION THAT MATTERS.

    The bug was never a bad value — it was two endpoints answering the same
    question differently, one with a headshot and one with nothing.  Comparing
    the two producers for one event is the only assertion that fails if a
    future edit teaches one of them a rule the other does not learn.

    `participant_images_for_event` is the feed's own producer, called here
    exactly as `routes/feed.py` calls it.
    """
    served = _format_event(_event())
    feed = participant_images_for_event(
        home_team=KHACHANOV, away_team=TIEN, sport_key=ATP
    )

    for key in FACE_KEYS:
        assert served[key] == feed[key], (
            f"{key}: the shared card serves {served[key]!r} and the feed card "
            f"serves {feed[key]!r} for one match"
        )
