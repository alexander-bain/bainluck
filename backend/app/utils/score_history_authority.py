"""#6155 — withhold a stored score reading from a COMPLETED game's chart only
when the event's own positioned authority trace proves it was already
superseded when it was captured.

`score_snapshots` carries `captured_at`, `home_score`, `away_score` and nothing
else: no source, no game position. From those three fields alone a lagging
feed's reading and a genuine correction (a touchdown reversed on review) are
the same row. So this module never decides from the score rows alone. It asks
an INDEPENDENT trace already served by the same route — `espn_history`, each
point carrying a score AND a game position — and withholds a reading only when
every one of these holds:

  1. the event is completed (the authority trace is closed, so "never again"
     below is a fact and not a forecast);
  2. the two series end on the same score in the same orientation (a crossed
     or diverging authority is no authority);
  3. authority observations bracket the reading within `MAX_BRACKET_GAP_S` on
     BOTH sides (an outage is "no evidence", never "no change");
  4. the reading disagrees with both bracketing observations;
  5. the authority itself held EXACTLY this score earlier, moved off it before
     the reading was captured, and never holds it again through the final —
     a delayed authoritative correction, or a correction later reversed, makes
     the authority return to the value and the reading is kept;
  6. the authority's own game position did not run backwards across that span;
  7. positioned scoring plays exist, the bracket is positioned ON THE SAME
     SCALE the plays use (a countdown period 1..4 — see `_countdown_position`),
     and NO scoring play sits inside it — a re-score inside the bracket is
     exactly what a real correction-then-score looks like, so it keeps the
     reading.

Anything else is kept: a value the authority never held (an intermediate state
such as TD-before-PAT, or a feed AHEAD of the authority), every reading outside
a tight bracket, every reading on an event with no authority, and every reading
whose bracket sits in overtime or in an innings-labelled game — the scoring
plays cannot be placed there, so nothing could ever exonerate it.

NOT a monotonic clamp and NOT an A->B->A smoother: a decrease is never the
test, and a persisting decrease is always kept because the authority follows it.

RESIDUAL, stated rather than hidden: the authority is SAMPLED. A real excursion
to a previously-held score that begins and ends inside one bracket, with no
scoring play in it (a ruling overturned and re-instated inside ~60s), is
indistinguishable from a lagging feed by any field this system stores. Withheld
readings are therefore returned to the caller, never discarded, and the stored
rows are never touched.
"""

from __future__ import annotations

from bisect import bisect_right
from datetime import datetime
from typing import Any, Iterable

from app.utils.game_state import (
    _clock_remaining_seconds,
    _COUNTDOWN_PERIOD_RE,
    live_progress_position,
)

#: Both sides of the bracket must be this close to the reading. ESPN snapshots
#: land every ~60s on a live game; two missed cycles is an outage.
MAX_BRACKET_GAP_S = 120.0

#: ESPN box-score plays number periods 1..4 for the countdown sports this
#: module can position. Overtime numbering differs by sport, so it is refused.
_MAX_POSITIONED_PLAY_PERIOD = 4


def _ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _score(point: dict) -> tuple[int, int] | None:
    home, away = point.get("home_score"), point.get("away_score")
    if isinstance(home, bool) or isinstance(away, bool):
        return None
    if not isinstance(home, int) or not isinstance(away, int):
        return None
    return (home, away)


def _play_position(play: dict) -> tuple[float, float] | None:
    try:
        period = int(str(play.get("period")).strip())
    except (TypeError, ValueError):
        return None
    if not 1 <= period <= _MAX_POSITIONED_PLAY_PERIOD:
        return None
    remaining = _clock_remaining_seconds(play.get("clock"))
    if remaining is None:
        return None
    return (float(period), -remaining)


def _countdown_position(period: Any, game_clock: Any) -> tuple[float, float] | None:
    """The authority row's position, but ONLY on the one scale `_play_position`
    above also speaks: a countdown period numbered 1..4.

    `live_progress_position` deliberately ranks other shapes on other scales —
    an inning as `inning * states + state`, an overtime as
    `_REGULATION_PERIODS + n` — while a scoring play is refused a position
    outside 1..4 entirely. Mixing the two would put the bracket somewhere the
    plays can never reach, and then `play_inside` is False by CONSTRUCTION.
    That check is the only one here that KEEPS a reading, so its silence must
    never be read as agreement: measured, a 'Top 4th' authority row ranks 8.0
    against an inning-4 play's 4.0, and an 'Overtime' row ranks 5.0 while an
    overtime play has no position at all. Both are refused here instead, which
    costs the rule overtime and baseball and buys back the only exoneration
    those brackets had.
    """
    if period is None:
        return None
    if not _COUNTDOWN_PERIOD_RE.search(str(period)):
        return None
    position = live_progress_position(period, game_clock)
    if position is None or position[0] > _MAX_POSITIONED_PLAY_PERIOD:
        return None
    return position


def split_superseded_score_history(
    score_history: list[dict],
    authority_history: Iterable[dict],
    scoring_plays: Iterable[dict] | None,
    *,
    event_completed: bool,
    final_score: tuple[int | None, int | None] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Return ``(served, withheld)``; ``served + withheld`` is the input, reordered
    only by the split. Every refusal returns the input unchanged."""
    unchanged = (list(score_history), [])
    if not event_completed or len(score_history) < 2:
        return unchanged

    authority = []
    for point in authority_history or ():
        ts, score = _ts(point.get("timestamp")), _score(point)
        if ts is None or score is None:
            continue
        authority.append(
            (ts, score, _countdown_position(point.get("period"), point.get("game_clock")))
        )
    authority.sort(key=lambda row: row[0])
    if len(authority) < 2:
        return unchanged

    # (2) same ending, same orientation.
    last_served = _score(score_history[-1])
    if last_served is None or last_served != authority[-1][1]:
        return unchanged
    if final_score is not None and None not in final_score:
        if tuple(final_score) != last_served:
            return unchanged
    held_states = {row[1] for row in authority}
    direct = sum(1 for p in score_history if _score(p) in held_states)
    crossed = sum(
        1 for p in score_history
        if _score(p) is not None and _score(p)[::-1] in held_states
    )
    if crossed > direct:
        return unchanged

    plays = list(scoring_plays or ())
    play_positions = [pos for pos in map(_play_position, plays) if pos]
    # (7) no play evidence, or a list that stops short of the final (a "last
    # 10" feed): "no play inside the bracket" would be an artefact. Refuse.
    if not play_positions or not any(_score(p) == last_served for p in plays):
        return unchanged

    auth_times = [row[0] for row in authority]
    served, withheld = [], []
    for point in score_history:
        ts, score = _ts(point.get("timestamp")), _score(point)
        if ts is None or score is None:
            served.append(point)
            continue
        nxt = bisect_right(auth_times, ts)
        prv = nxt - 1
        keep = True
        if prv >= 0 and nxt < len(authority):
            before, after = authority[prv], authority[nxt]
            tight = (
                (ts - before[0]).total_seconds() <= MAX_BRACKET_GAP_S
                and (after[0] - ts).total_seconds() <= MAX_BRACKET_GAP_S
            )
            held_before = [j for j in range(prv) if authority[j][1] == score]
            returns = any(authority[j][1] == score for j in range(prv, len(authority)))
            if tight and score not in (before[1], after[1]) and held_before and not returns:
                last_hold = authority[held_before[-1]]
                span = [last_hold[2], before[2], after[2]]
                positioned = before[2] is not None and after[2] is not None
                ordered = all(
                    a <= b for a, b in zip(
                        [p for p in span if p is not None],
                        [p for p in span if p is not None][1:],
                    )
                )
                play_inside = positioned and any(
                    before[2] < pos <= after[2] for pos in play_positions
                )
                if positioned and ordered and not play_inside:
                    keep = False
        (served if keep else withheld).append(point)
    return served, withheld
