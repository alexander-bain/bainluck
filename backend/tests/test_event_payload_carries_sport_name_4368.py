"""#4368 — an event card cannot name its league, because the payload never told it.

`_format_event` served `sport` (the KEY) and nothing else, so every client that
drew a league on an event card had to parse the key.  Measured against
`/api/sports` on 2026-09-09, that parse reproduces 30 of the 161 branded rows,
gets 131 wrong, and prints a different WORD for 83 of them —
`soccer_netherlands_eredivisie` renders "NETHERLANDS EREDIVISIE" beside a filter
chip on the same screen reading "Dutch Eredivisie".

The fix is one line of payload: serve the name the row already stores, so a
client can PREFER it.  It is deliberately not the whole answer — 15 of the 176
rows store their own key in `name` ("mma_other"), so a client still needs its
map as a fallback, which is what `getSportLabel` does on the other side.

The arms below are the three shapes a `sports` row comes in, plus the two that
would make this a regression rather than a ship: a name that costs a query, and
a key that quietly stops being served.
"""

from datetime import datetime, timezone

from sqlalchemy import inspect

from app.models import Event, Sport
from app.routes.events import _format_event


def _event(sport: Sport | None) -> Event:
    return Event(
        id=15301243,
        sport_id=getattr(sport, "id", None),
        sport=sport,
        home_team_name="Ajax",
        away_team_name="Feyenoord",
        commence_time=datetime(2026, 9, 12, 11, 0, tzinfo=timezone.utc),
        status="scheduled",
        home_score=None,
        away_score=None,
    )


def test_a_branded_row_serves_the_brand():
    """The specimen from the issue.  The key parses to "NETHERLANDS EREDIVISIE";
    the row has said "Dutch Eredivisie" all along and nobody could read it."""
    sport = Sport(id=1, key="soccer_netherlands_eredivisie", name="Dutch Eredivisie")

    data = _format_event(_event(sport))

    assert data["sport"] == "soccer_netherlands_eredivisie"
    assert data["sport_name"] == "Dutch Eredivisie"


def test_the_key_is_still_served_beside_the_name():
    """SURVIVAL.  `sport` is the field every existing client filters, links and
    groups on; the name is additive.  A change that replaced one with the other
    would pass a "the label is right" test and break routing everywhere."""
    sport = Sport(id=1, key="americanfootball_nfl", name="NFL")

    data = _format_event(_event(sport))

    assert data["sport"] == "americanfootball_nfl"
    assert data["sport_name"] == "NFL"


def test_a_raw_row_serves_its_raw_name_rather_than_hiding_it():
    """One of the 15.  The server has no word for these, and the payload says so
    honestly instead of inventing one — the client's map owns that fallback.

    Asserting the raw value rather than `None` is the point: a formatter that
    "helpfully" nulled it would make the two cases indistinguishable on the wire,
    and `getSportLabel` decides between them by comparing the name to the key.
    """
    sport = Sport(id=1, key="mma_other", name="mma_other")

    data = _format_event(_event(sport))

    assert data["sport"] == "mma_other"
    assert data["sport_name"] == "mma_other"


def test_an_event_with_no_sport_serves_null_for_both():
    """The existing `if event.sport else None` arm, extended.  A row with no
    sport must not raise on the new line."""
    data = _format_event(_event(None))

    assert data["sport"] is None
    assert data["sport_name"] is None


def test_a_transient_sport_needs_no_session_to_serve_its_name():
    """The cost arm.

    Every `Sport` in this module is transient — constructed in memory, attached
    to no session.  Reading `.name` off one therefore cannot lazily load, cannot
    emit SQL and cannot touch a connection: if the name were fetched rather than
    read, these tests would raise instead of pass.

    That is the whole N+1 argument, and it is structural rather than asserted:
    `_format_event` is SYNC and takes no session, so on the async engine this
    codebase uses it has nothing to query WITH.  `.key` on the line above
    already resolved `event.sport`, so `.name` is a second read of an instance
    the caller loaded, not a second lookup.

    This test exists to say that out loud next to the arms that rely on it — a
    later refactor that gives this formatter a session should have to delete
    this docstring first.
    """
    sport = Sport(id=1, key="soccer_germany_liga3", name="3. Liga - Germany")
    # Stated, not assumed: no session, so no lazy load is even possible.
    assert inspect(sport).transient

    data = _format_event(_event(sport))

    assert data["sport"] == "soccer_germany_liga3"
    assert data["sport_name"] == "3. Liga - Germany"
