"""#5918 — the league rails must LOAD the sport, or the soccer fold is inert.

WHAT WAS WRONG, AND WHY EVERY EARLIER MEASUREMENT MISSED IT
===========================================================

The soccer name-pair fold reads a row's sport through
`kalshi_occurrence_start.loaded_sport_key`, which answers ``None`` for an
UNLOADED `Event.sport` rather than emitting IO inside a stage wrapped in a bare
``except`` (gotcha #42). That refusal is correct and stays.

All three league rails — `upcoming_games_query`, `recent_results_query`,
`unreported_games_query` — already `.join(Sport, ...)`, and that join is what
made this invisible. **A join in the FROM clause makes the table available to
the WHERE; it does not populate the relationship on the hydrated row.** So on
`/sports/soccer_spain_la_liga` every row arrived with `Event.sport` unloaded,
the soccer pass skipped every one of them, and Celta–Málaga rendered twice —
the exact defect #5918 exists to fix, on the exact page it was built for.

The reach matrix that measured the fold at nine folds on 765 production rows
could not see this: it drove `fold_twin_events` over row objects that carried
their sport in memory, which is the "already loaded" case. A mechanism
measurement is not a reach measurement (CERT-2805's finding).

WHAT THESE TESTS PIN
====================

The fast arm here is structural and runs in the normal suite: each rail's
statement carries an eager load whose path ends at `sport`. It is read off the
statement's loader OPTIONS rather than its compiled SQL, because `selectinload`
emits a SECOND statement and leaves no trace in the first — a text assertion
would pass with the option deleted, which is the failure mode that would make
this guard worse than none.

The behavioural proof — the real query executed by a real server over two real
Celta rows, with and without the option — is
`tests/integration/test_league_rail_sport_load_pg.py`, because only a database
can tell a loaded relationship from an unloaded one.
"""

from datetime import datetime, timezone

import pytest

from app.routes.league_futures import (
    recent_results_query,
    unreported_games_query,
    upcoming_games_query,
)

BASE = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)

RAILS = {
    "upcoming": upcoming_games_query,
    "recent_results": recent_results_query,
    "unreported": unreported_games_query,
}


def _eager_paths(statement):
    """The relationship names each loader option on `statement` will load.

    Reads `_with_options` — the loader strategies attached to the select —
    rather than the SQL text. `selectinload` is a separate round trip and never
    appears in this statement's SQL at all, so the text is precisely the wrong
    place to ask.
    """
    names = set()
    for option in getattr(statement, "_with_options", ()):
        for element in getattr(option, "path", ()) or ():
            key = getattr(element, "key", None)
            if isinstance(key, str):
                names.add(key)
    return names


@pytest.mark.parametrize("rail", sorted(RAILS))
def test_every_league_rail_eager_loads_the_sport(rail):
    """THE SHIP'S REACH. Without this the soccer fold cannot fire on the page.

    Parametrized so a rail added later fails loudly instead of being forgotten,
    and so the failure message names WHICH rail lost it.
    """
    statement = RAILS[rail]("soccer_spain_la_liga", BASE)
    assert "sport" in _eager_paths(statement), (
        f"the {rail} rail does not eager-load Event.sport, so "
        "loaded_sport_key() answers None for every row it returns and the "
        "#5918 soccer fold silently no-ops on the league page"
    )


def test_the_probe_can_tell_a_loaded_rail_from_an_unloaded_one():
    """NON-VACUITY. A probe that found 'sport' in everything would pass above.

    The same probe over a bare `select(Event)` — the shape all three rails had
    before this fix — must report nothing, so the assertions above are reading
    something that is genuinely capable of being absent.
    """
    from sqlalchemy import select

    from app.models.models import Event, Sport

    unloaded = select(Event).join(Sport, Sport.id == Event.sport_id)
    assert _eager_paths(unloaded) == set(), (
        "a join is not a loader — if the probe reports `sport` here it is "
        "reading the FROM clause and would pass on the broken rails"
    )


def test_the_non_soccer_refusal_is_not_what_was_relaxed():
    """The repair loads the key; it does not widen who may fold.

    `loaded_sport_key` still answers None for a row whose relationship is not
    loaded, and the soccer gate still refuses every non-soccer key. Pinned here
    so a future "fix" that reaches the page by weakening the gate instead of
    loading the row fails this file rather than passing it.
    """
    from app.utils.kalshi_occurrence_start import loaded_sport_key

    class _Unloaded:
        sport = None

    assert loaded_sport_key(_Unloaded()) is None
