"""Odds snapshot filtering utilities.

Pure functions for filtering odds snapshots before aggregation.
Extracted from routes/events.py for testability (no FastAPI dependency).
"""

from datetime import datetime, timedelta, timezone


def _effective_time(snapshot) -> datetime:
    """Return the most recent confirmation time for a snapshot.

    With write-time dedup, `captured_at` is when the odds value first appeared,
    while `valid_until` gets bumped on each subsequent poll that confirms the
    same value.  Using valid_until (when available) correctly identifies
    bookmakers that are still actively being polled even if their odds haven't
    changed.
    """
    if snapshot.valid_until is not None:
        return snapshot.valid_until
    return snapshot.captured_at


def _carries_a_quote(snapshot) -> bool:
    """Does this snapshot price ANYTHING — a moneyline, a spread or a total?

    #8922: the "does the narrower set still hold something" probes below used
    to ask about the moneyline alone. In a blowout every live sportsbook pulls
    its moneyline and keeps quoting the spread and total, so the probe read the
    live set as empty and fell back to ALL snapshots — re-admitting the books
    that froze at kickoff. Measured on production 2026-09-26 20:30Z,
    /events/15315949 (Notre Dame 35–3 Purdue, end of Q3): seven live books at
    ND −40.5…−43.5 / total 52.5, all `home_moneyline: null`, plus four pre-game
    books frozen at ND −27 / 57. `current_odds` served their mean, 36.5 / 54.2,
    and the margin map printed `PROJECTION ND by 36.1+` under a headline of
    `Projected final: 6 – 47`.

    A live book with no moneyline is still live evidence for the fields it
    does quote. A snapshot quoting nothing at all is evidence of nothing, and
    the fall-back-to-all behaviour for that case is unchanged.
    """
    return any(
        getattr(snapshot, field, None) is not None
        for field in ("home_win_probability", "home_spread", "over_under")
    )


#: #12938 / ruling 233: A. In a live game a sportsbook line counts toward Now
#: only while it is current. A line is current while its price changed in the
#: last three minutes, OR changed after the game's last score change (the start,
#: before any score). The second arm exists because a quiet line is not always a
#: frozen one: hockey lines rest between goals. Replayed over 52 finished games
#: (#12938): the plain three-minute rule took Sportsbooks out of 808 of 7,486
#: live minutes (459 of 2,124 in the NHL) and left 17 with no other current
#: source; this rule, 246 (84 NHL) and none.
LIVE_LINE_CURRENT_SECONDS = 180


def live_line_is_current(
    changed_at: datetime | None,
    *,
    now: datetime,
    state_changed_at: datetime | None,
    window_seconds: int = LIVE_LINE_CURRENT_SECONDS,
) -> bool:
    """Whether one book's live line still counts toward the Sportsbooks number.

    ``changed_at`` is when we first saw the line's current price: the snapshot's
    ``captured_at``. NOT ``valid_until`` — that moves every time the Odds API
    re-serves the same price, and re-serving a price a book stopped updating is
    exactly the failure (#12938: eight books served unchanged from 9:05 to
    9:19 PM through a lead change, 81% beside Polymarket's 99.5%).

    ``state_changed_at`` is the game's last score change, or its start when no
    score change is recorded. A line priced after it has seen the current score.
    """
    if changed_at is None:
        return False
    if changed_at.tzinfo is None:
        changed_at = changed_at.replace(tzinfo=timezone.utc)
    if (now - changed_at).total_seconds() <= window_seconds:
        return True
    if state_changed_at is None:
        return False
    if state_changed_at.tzinfo is None:
        state_changed_at = state_changed_at.replace(tzinfo=timezone.utc)
    return changed_at >= state_changed_at


def filter_stale_bookmaker_snapshots(
    snapshots: list, event_status: str, commence_time: datetime = None
) -> list:
    """Filter out stale bookmaker snapshots for games that have started.

    Two layers of filtering for non-scheduled events:

    1. **Pregame filter**: Exclude bookmakers whose odds haven't been confirmed
       since before the game started.  Uses ``_effective_time`` (prefers
       ``valid_until`` over ``captured_at``) so that write-time-deduped
       snapshots with unchanged-but-confirmed odds are correctly kept.

    2. **Recency filter** (live events only): Exclude bookmakers whose last
       confirmation is >10 minutes older than the freshest bookmaker.  This
       catches bookmakers that posted a single live update then stopped.

    For scheduled events or when commence_time is unavailable, returns
    snapshots unchanged.
    """
    if event_status == "scheduled" or not snapshots or commence_time is None:
        return snapshots

    # Sanity check: commence_time should be in the past for started events.
    # If it's in the future, it's likely a bad value from the Odds API.
    now = datetime.now(timezone.utc)
    if commence_time > now:
        return snapshots

    # Layer 1: exclude bookmakers not confirmed since game start
    live_snapshots = [
        s for s in snapshots if _effective_time(s) >= commence_time
    ]

    # Only use filtered list if at least one live book still quotes something
    # (#8922: a spread or total counts — not only a moneyline)
    if not any(_carries_a_quote(s) for s in live_snapshots):
        return snapshots

    # Layer 2 (live only): exclude bookmakers that stopped updating
    # A bookmaker that posted one live update then went silent would pass
    # Layer 1 but contaminate the aggregate with stale odds.
    if event_status == "live" and len(live_snapshots) > 1:
        latest_time = max(_effective_time(s) for s in live_snapshots)
        recency_cutoff = latest_time - timedelta(minutes=10)
        recent_snapshots = [
            s for s in live_snapshots
            if _effective_time(s) >= recency_cutoff
        ]
        # Only apply recency filter if it leaves at least one quoting snapshot
        if any(_carries_a_quote(s) for s in recent_snapshots):
            live_snapshots = recent_snapshots

    return live_snapshots
