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

── AMENDED BY #6251: ON A SCORE WRITER, THE SCORES ARE PART OF THE PREDICATE ──

That paragraph is still true of the POSITION. It stopped being the whole story
once `live_write_would_revert` gained its tie-break, because on a position tie
the decision now reads the row's two score columns as well — and a decision is
only atomic with its write if the write re-asserts everything the decision read.
A tie-break taken on a score another writer has already moved is the same class
of mistake this module exists to close, one column over.

So the three writers that WRITE a score pass what they read of it, and it joins
the predicate. Two things follow, and the second is a cost worth stating:

  * The tie decision is now genuinely atomic, on the same READ COMMITTED
    argument as the position.
  * The predicate is fractionally stricter than the decision strictly needs. At
    a NON-tie the score was never consulted, so a concurrent score commit does
    not invalidate that decision, yet it will now refuse the write. The refusal
    is a counted no-op and the beat is 30 seconds, so the price is one skipped
    update in a window that has to be measured in milliseconds to hit at all —
    against a tie-break that would otherwise arbitrate on a stale number.

A writer that does not write a score (`mlb_sync`'s win-probability pass) passes
none, predicates on position alone, and is untouched by any of this.

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


#: "This caller did not read that column", which is a different claim from "it
#: read it and it was NULL" — and on a live row a NULL score is the common case,
#: so the two must not collapse. A plain `None` default would have made every
#: score-less caller silently predicate on `home_score IS NULL`.
_UNREAD = object()


async def write_live_state_if_unmoved(
    session,
    event,
    values: Mapping[str, Any],
    *,
    observed_period: str | None,
    observed_clock: str | None,
    observed_home_score: Any = _UNREAD,
    observed_away_score: Any = _UNREAD,
    what: str = "live state",
) -> bool:
    """Write `values` onto `event` only if the state it decided on has not moved.

    The spelling of :func:`write_row_if_unmoved` the four score-and-clock
    producers use. Their decision is `live_write_would_revert`, so the columns
    that decision reads are exactly the columns this write re-asserts: always
    the two position columns, and — for the three producers that write a score,
    whose tie-break reads them (#6251) — the two score columns as well.

    A producer that writes no score passes neither and predicates on position
    alone. Passing one of the two alone is a programming error rather than a
    half-measure: `_score_would_regress` needs all four sides to say anything,
    so a decision that read one score read both.
    """
    observed: dict[str, Any] = {
        "period": observed_period,
        "game_clock": observed_clock,
    }
    supplied = (observed_home_score is not _UNREAD, observed_away_score is not _UNREAD)
    if any(supplied) and not all(supplied):
        raise ValueError(
            f"#6251: {what} offered one observed score and not the other — the "
            "tie-break reads both or neither, so a one-sided predicate would "
            "guard a decision that was never taken"
        )
    if all(supplied):
        observed["home_score"] = observed_home_score
        observed["away_score"] = observed_away_score

    return await write_row_if_unmoved(
        session,
        event,
        values,
        observed=observed,
        what=what,
    )
