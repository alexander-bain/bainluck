"""The live game clock the current-line rule reads, and the projection that follows it (#12938).

Ruling 233: A (Alex, Nov 17): in a live game a sportsbook line counts only while
it is current. `odds_filtering.live_line_is_current` is the rule. The odds job
(`odds_polling._ingest_event_odds`) already reads each live game's clock — its
last score change, or its start before any score — to build the Sportsbooks
number in Now. It stores that clock in the game's sources bag under
:data:`LIVE_STATE_CLOCK_KEY`, beside ``betting_book_count``, and the page and the
cards read it from there (Fable, Nov 18, option A): the card pair's read stays
one statement (#2920), and the projected final is built from the same lines as
Sportsbooks in Now.

A missing or unparseable clock means "not decided by the live rule": the
projection is built exactly as before.
"""

from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from app.utils.odds_filtering import live_line_is_current

#: Top-level bookkeeping key in ``Event.win_probability_sources``: an ISO time.
#: Not a source: it has no ``value`` and is not in ``SOURCE_WEIGHTS``, so the
#: blend, the source marks and Discover pass over it by shape, as they do
#: ``betting_book_count`` (guarded in the #12938 tests).
LIVE_STATE_CLOCK_KEY = "live_state_changed_at"

#: The fields a projected final is made of. Probability and book count are not
#: here: the page's chance is the blend, and the count describes the book table.
PROJECTION_FIELDS = ("home_spread", "over_under", "projected_home_score", "projected_away_score")


def _aware(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def game_state_clock(last_score_change: Any, commence_time: Any) -> Optional[datetime]:
    """The later of the last score change and the start; a pre-start row loses."""
    stamps = [t for t in (_aware(last_score_change), _aware(commence_time)) if t is not None]
    return max(stamps) if stamps else None


def stored_state_clock(sources: Any) -> Optional[datetime]:
    """The live clock the odds job stored in a sources bag, or None."""
    if not isinstance(sources, dict):
        return None
    raw = sources.get(LIVE_STATE_CLOCK_KEY)
    if not isinstance(raw, str):
        return None
    try:
        return _aware(datetime.fromisoformat(raw.replace("Z", "+00:00")))
    except ValueError:
        return None


def event_state_clock(event: Any, sources: Any = None) -> Optional[datetime]:
    """A LIVE event's stored clock; None for any other status.

    ``sources`` lets a caller that holds an already-loaded bag pass it, so no
    attribute access can trigger a lazy load (gotcha #42).
    """
    if getattr(event, "status", None) != "live":
        return None
    if sources is None:
        sources = getattr(event, "win_probability_sources", None)
    return stored_state_clock(sources)


def current_lines(snapshots: Iterable[Any], *, now: datetime, state_changed_at: datetime) -> list:
    """The snapshots whose line is current under ruling 233: A."""
    return [
        s for s in snapshots
        if live_line_is_current(
            getattr(s, "captured_at", None), now=now, state_changed_at=state_changed_at
        )
    ]


def apply_live_line_projection(
    aggregated: dict, snapshots: Iterable[Any], *, now: datetime,
    state_changed_at: Optional[datetime],
) -> dict:
    """``aggregated`` with its projected final rebuilt from current lines only.

    No clock returns ``aggregated`` unchanged. With no current line the
    projection is withheld (all four fields None): a projection from lines that
    stopped moving is the 65-68 Alex saw on a game that finished 65-61.
    """
    if state_changed_at is None:
        return aggregated
    from app.utils.odds_math import aggregate_bookmaker_odds

    # No book-count floor here: in a blowout books pull the moneyline and keep
    # quoting the spread and total, and two current lines are an honest
    # projection (#8922). The floor is Sportsbooks-in-Now's (ruling 051).
    rebuilt = aggregate_bookmaker_odds(
        current_lines(snapshots, now=now, state_changed_at=state_changed_at)
    )
    out = dict(aggregated)
    for key in PROJECTION_FIELDS:
        out[key] = rebuilt.get(key)
    return out
