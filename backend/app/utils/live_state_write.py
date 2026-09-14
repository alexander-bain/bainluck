"""#6056: make a live-state write atomic with the decision that authorised it.

Three tasks write `events.period`, `game_clock`, `home_score` and `away_score`
on a running game. `utils/game_state.live_write_would_revert` decides whether an
incoming observation is from EARLIER in the game than the row already is, and
refuses it if so — but that decision is only as good as the instant it is taken
at, and none of the three writers wrote at that instant.

Every one of them plain-SELECTs the row, reads the two position columns, decides,
then ORM-assigns the new values — which do not reach Postgres until the session
commits. There is no lock, no version column, and in two of the three no
intermediate commit at all, so the gap between the decision and the write spans
the rest of the pass, network calls included. The three run on two different
queues (the hourly schedule pass on `background`, the 30-second StatPal
livescore writer and the ESPN writer on `realtime` at concurrency 4), so that
gap is genuinely concurrent and not a theoretical one. A writer that read a
current position, decided correctly, and then committed behind a newer writer
put the reader back in front of exactly the defect #6056 exists to fix — a
touchdown leaving the page, a clock running backwards — with the sequential
guard reporting nothing, because from its point of view it did nothing wrong.

So the decision is re-asserted AT WRITE TIME, in the database:

    UPDATE events SET <the fields>
     WHERE id = :id
       AND period IS NOT DISTINCT FROM :position_the_decision_saw
       AND game_clock IS NOT DISTINCT FROM :position_the_decision_saw

Optimistic compare-and-write. No new column, no lock ordering to get wrong, and
no change to the hot path when nothing is contending — this is the same Core
`update(Event)` idiom `statpal_sync` already uses for the injuries JSONB.

── WHY THIS IS ACTUALLY ATOMIC, AND NOT JUST A NARROWER WINDOW ──

Worth stating, because "check then write" usually just moves the race. Under
PostgreSQL's READ COMMITTED, an UPDATE that finds a row locked by another
transaction BLOCKS until that transaction ends and then RE-EVALUATES its WHERE
clause against the new version of the row. So a concurrent writer cannot slip
between this statement's predicate and its write: it either committed before,
in which case the predicate now fails and this write correctly refuses, or it
arrives after, in which case it waits on the row lock this statement holds until
commit. The comparison and the write are one act, which is the whole point.

The counter-example to keep in mind is the one this does NOT claim to solve: two
writers whose observations are at the SAME position both land, last one wins.
That is correct and deliberate — a same-moment correction is news, not a
reversion, and `live_write_would_revert` accepts ties for the same reason.

── THE FAILURE MODE IS A REFUSAL, WHICH IS WHY IT IS COUNTED ──

A lost race means "we were current when we looked and stale by the time we
wrote", and the right response is to drop the write: the row already holds a
LATER observation, and the next beat is 30 seconds away. But a refusal that
nobody counts is indistinguishable from a write that never had anything to say,
and that is how this class of defect stays invisible. Every caller counts its
own refusals under its own key, and the keys are always present so a 0 is a
reading rather than an absence (gotcha #53).
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from sqlalchemy import update

logger = logging.getLogger(__name__)

#: The columns that together say where a live row is in its own game, and which
#: therefore may only be written as one act. Named here rather than spelled out
#: at each call site so a guard test can assert that no caller ORM-assigns one
#: behind the compare-and-write's back (gotcha #5).
LIVE_STATE_COLUMNS = ("period", "game_clock", "home_score", "away_score")


async def write_row_if_unmoved(
    session,
    event,
    values: Mapping[str, Any],
    *,
    observed: Mapping[str, Any],
    what: str,
) -> bool:
    """Write `values` onto `event` only if every column in `observed` still holds it.

    `observed` maps a column name to its value AS THE CALLER READ IT when it took
    its decision — not as it stands now, which is the whole distinction. Returns
    True if the write landed, False if another writer moved the row first and it
    was refused.

    ── WHICH COLUMNS BELONG IN `observed` ──

    The ones the decision CONSUMED, which are not always the ones it writes.
    Position (`period`/`game_clock`) is the right predicate for a writer whose
    decision was "is this observation earlier in the game than the row is" —
    that is what `write_live_state_if_unmoved` below exists for, and it is what
    the four score-and-clock producers use.

    It is the WRONG predicate for a writer that never reads position. The tennis
    authority pass decides by comparing ESPN's set score against the row's own
    `home_score`/`away_score` and touches neither position column; on a tennis
    row those two are routinely NULL, so a position predicate there would
    compile, run, be green, and arbitrate precisely nothing — a compare-and-write
    that cannot refuse is worse than none, because it reads as protection. That
    writer therefore predicates on the two score columns its decision actually
    read, and refuses if either moved.

    An empty `values` returns True: a caller with nothing to write has not lost a
    race, and counting it as one would bury the real signal under every quiet
    beat. An empty `observed` RAISES, because it is not a compare-and-write at
    all — it is an unconditional UPDATE wearing the name of one.

    Callers must keep every predicate column out of their own ORM assignments and
    pass it here instead: a pending ORM assignment to a predicate column would be
    flushed ahead of this statement and make the predicate compare the row
    against itself.
    """
    if not observed:
        raise ValueError(
            f"#6056: {what} asked for a compare-and-write with nothing to "
            "compare — an empty `observed` is an unconditional UPDATE"
        )

    if not values:
        return True

    from app.models.models import Event

    # Explicit rather than left to autoflush, so this statement's position
    # relative to the row's OTHER pending writes (status, commence_time, the
    # provider ids) is stated here instead of inferred (gotcha #5).
    await session.flush()

    result = await session.execute(
        update(Event)
        .where(
            Event.id == event.id,
            # `is_not_distinct_from` rather than `==` STATES the null-safety
            # instead of inheriting it. A live row with no position yet is the
            # common case on these paths, and `==` happens to survive it only
            # because SQLAlchemy rewrites a literal `None` to `IS NULL` at
            # compile time — a property of this value being None, not of the
            # predicate. Equivalent as written; only this spelling stays correct
            # if the comparison is ever built from a bindparam.
            *[
                getattr(Event, column).is_not_distinct_from(was)
                for column, was in observed.items()
            ],
        )
        .values(**values)
    )

    if result.rowcount:
        # The loaded row needs no hand-written mirror: this is an ORM-enabled
        # UPDATE, so SQLAlchemy's default `synchronize_session="auto"` writes
        # the new values onto the matched instance itself. That is load-bearing
        # — callers read `event.home_score` further down the same pass — so it
        # is asserted by test rather than assumed.
        return True

    logger.info(
        "#6056: refused a %s write on event %s — the row moved off %r "
        "between the decision and the write; offered %s",
        what, getattr(event, "id", None), dict(observed), dict(values),
    )
    return False


async def write_live_state_if_unmoved(
    session,
    event,
    values: Mapping[str, Any],
    *,
    observed_period: str | None,
    observed_clock: str | None,
    what: str = "live state",
) -> bool:
    """Write `values` onto `event` only if its POSITION has not moved since.

    The position-predicated spelling of :func:`write_row_if_unmoved`, and the one
    the four score-and-clock producers use: their decision is
    `live_write_would_revert`, which reads exactly these two columns, so exactly
    these two are what the write must re-assert.
    """
    return await write_row_if_unmoved(
        session,
        event,
        values,
        observed={"period": observed_period, "game_clock": observed_clock},
        what=what,
    )
