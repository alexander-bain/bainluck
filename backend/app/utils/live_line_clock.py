"""The live game clock the current-line rule reads, and the projection that follows it (#12938).

Ruling 233: A (Alex, Nov 17): in a live game a sportsbook line counts only while
it is current. `odds_filtering.live_line_is_current` is the rule; this module
gives it the game's clock on the read side and applies it to the projected
final, so the page's projection and the Sportsbooks number in Now are built from
the same lines.

The clock is the game's last score change, or its start when none is recorded:
`score_snapshots` gets a row when a writer sees the score change.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import func, select

from app.utils.odds_filtering import live_line_is_current

logger = logging.getLogger(__name__)

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


async def live_state_clocks(db: Any, events: Iterable[Any]) -> dict[int, datetime]:
    """``{event_id: clock}`` for the LIVE events among ``events``, in one statement.

    Never raises: on a failed read it returns ``{}``, and a caller with no clock
    for a game leaves that game's projection exactly as it was. The read runs in
    a savepoint so a failure cannot poison the request's transaction.
    """
    live = [
        e for e in events
        if getattr(e, "status", None) == "live" and getattr(e, "commence_time", None) is not None
    ]
    if not live:
        return {}
    from app.models import ScoreSnapshot

    try:
        async with db.begin_nested():
            rows = (
                await db.execute(
                    select(ScoreSnapshot.event_id, func.max(ScoreSnapshot.captured_at))
                    .where(ScoreSnapshot.event_id.in_(sorted({e.id for e in live})))
                    .group_by(ScoreSnapshot.event_id)
                )
            ).all()
    except Exception:  # noqa: BLE001 — gotcha #42: today's projection, not a failed page
        logger.exception("live state clock read failed for %d events", len(live))
        return {}
    last = {event_id: at for event_id, at in rows}
    clocks = {}
    for e in live:
        clock = game_state_clock(last.get(e.id), e.commence_time)
        if clock is not None:
            clocks[e.id] = clock
    return clocks


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

    No clock (not live, or the read failed) returns ``aggregated`` unchanged.
    With no current line the projection is withheld (all four fields None):
    a projection from lines that stopped moving is the 65-68 Alex saw on a
    game that finished 65-61.
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
