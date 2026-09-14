"""When each futures outcome's price was last actually OBSERVED.

One question — *what is the newest ``captured_at`` for each of these outcomes?*
— asked the only way that stays cheap as the snapshot table grows.

## why this is not a ``max() ... GROUP BY``

The obvious spelling is the one this module replaces:

```sql
SELECT outcome_id, max(captured_at)
FROM futures_odds_snapshots
WHERE outcome_id IN (:ids) AND probability IS NOT NULL
GROUP BY outcome_id
```

It is correct and it does not scale, because **an aggregate cannot skip**: to
return one row per group PostgreSQL must visit every row of every group. On the
US Open register's 514 pinned outcomes, measured on production 2026-08-30 with
``EXPLAIN (ANALYZE, BUFFERS)``:

    Aggregate (Sorted)                                514 rows out
      Index Only Scan ...outcome_bookmaker_captured   342,059 rows in
      Shared Hit 173,444 + Read 2,310 = 175,754 blocks

**342,059 index tuples read to return 514 numbers**, and ~1.4 GB of buffer
traffic. Warm that is ~1.1 s; it is the buffer volume, not the CPU, that makes
the same statement cost 3.6 s one minute and 11.9 s the next on a request path.

The set of outcomes is always BOUNDED here (a register pins them), and
``idx_fos_outcome_captured (outcome_id, captured_at)`` exists, so the same
answer is one top-1 index probe per outcome. Measured on the same 514 ids, same
database, same minute:

    | executed row query | 1,766 ms  ->    118 ms |
    | buffer blocks      | 175,754   ->    3,407  |
    | rows returned      | 514       ->    514, 0 diffs |

🔴 **This is only the right shape for a BOUNDED id list.** N correlated probes
beat one aggregate at 514 outcomes; they do not at 500,000. A caller that wants
this over an unbounded population wants the aggregate back, or an index.

## the two predicates, and why neither is decoration

**``probability IS NOT NULL`` is carried even though it is dead today.**
``futures_odds_snapshots.probability`` is ``NOT NULL`` in the live schema, so
PostgreSQL removes the clause during planning — it appears in the plan of
neither the old form nor this one. It is kept because it states the caller's
actual question (*observed with a price*), it costs exactly nothing while the
column stays non-nullable, and it is the difference between right and wrong on
the day it does not.

🔴 **``captured_at IS NOT NULL`` IS LOAD-BEARING, AND THE DIALECT IS WHY.**
``ORDER BY x DESC`` is ``NULLS FIRST`` in PostgreSQL. Without this predicate an
outcome holding a single ``captured_at IS NULL`` row would report ``None`` while
``max()`` — which skips NULLs — reports its real newest observation. The two
forms would disagree on exactly the rows a freshness display exists to describe.

The column is nullable *in the database* (``information_schema`` says
``is_nullable = YES``, checked on production 2026-08-30) even though the model
declares ``captured_at: Mapped[datetime]``. **The model and the deployed schema
disagree**, and the database is the one that executes the query — which is also
why a real-PostgreSQL gate built from ``Base.metadata`` cannot police this: it
would emit a ``NOT NULL`` column and be unable to hold the row that breaks it.
The predicate, and the tests that pin it, are the guard.

🔴 **AND DO NOT "FIX" IT WITH ``NULLS LAST``.** The defensive-looking spelling
``ORDER BY captured_at DESC NULLS LAST`` is answer-identical and **19x slower**,
measured on the same population, same minute:

    DESC (NULLS FIRST) + IS NOT NULL     124 ms    3,503 buffer blocks
    DESC NULLS LAST    + IS NOT NULL   2,408 ms  177,719 buffer blocks

``NULLS LAST`` does not match the index's own ordering, so each probe stops
being a one-row backward scan and becomes a Sort over the whole group — which
is the aggregate's cost back again, wearing a safer-looking clause.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FuturesOddsSnapshot, FuturesOutcome


def _as_aware(stamp: str) -> Optional[datetime]:
    """Parse an ISO stamp to an aware datetime, or ``None`` if unparseable.

    A naive stamp is read as UTC rather than rejected: every producer in this
    payload writes ``captured_at`` (``timestamptz``), but comparing a naive to
    an aware datetime raises ``TypeError``, and a freshness display must not be
    able to 500 a page over a timezone.
    """
    try:
        parsed = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def blended_observed_at(stamps: Iterable[Optional[str]]) -> Optional[str]:
    """The honest ``observed_at`` for ONE number blended from several prices.

    🔴 **A blend is only as fresh as its STALEST contributor, so the oldest
    stamp wins.** The served number is not any contributor's price — it is a
    function of all of them — so it cannot be newer than the oldest input that
    shaped it. Serving the newest is the defect this exists to prevent: a 30 h
    Kalshi price averaged with an 8-minute Polymarket one produces a number that
    is half a day stale and would render as eight minutes old, which reads
    FRESHER THAN THE TRUTH. The failure is silent and it is the direction a
    reader cannot detect.

    🔴 **One unknown contributor makes the blend's age unknown — ``None``, not
    the min of the rest.** An absent stamp does not mean "recent"; it means the
    outcome has no priced snapshot at all. Taking the minimum of the known ones
    would publish a bound the data does not support, because the unknown one may
    be older than all of them. Absent stays absent (gotcha #53) and the reader is
    shown no age rather than a wrong one.

    Returns the winning stamp **verbatim** as it was passed in, so the payload
    never gains a re-formatted spelling of a stamp another field already carries.
    """
    values = list(stamps)
    if not values:
        return None

    oldest: Optional[tuple[datetime, str]] = None
    for stamp in values:
        if stamp is None:
            return None
        parsed = _as_aware(stamp)
        if parsed is None:
            # Unparseable is unknown, and unknown poisons the blend exactly the
            # way a missing one does — never silently dropped from the vote.
            return None
        if oldest is None or parsed < oldest[0]:
            oldest = (parsed, stamp)

    return oldest[1] if oldest is not None else None


def clamp_capture_stamp(parsed: Optional[datetime], now: datetime) -> datetime:
    """The write-side companion to this module: a capture never post-dates ``now``.

    A reconstruction path that stamps a snapshot from a VENUE-SUPPLIED time —
    ``close_time``, ``expiration_time``, ``open_time`` — is stating when we
    observed a price. Those fields are SCHEDULE, not observation: Kalshi's
    ``expiration_time`` is the *latest possible* expiry (see
    ``app/utils/kalshi_resolution_window.py``), so a settled market can carry one
    days after it settled, and an open one carries a close in the future.

    🔴 **A future ``captured_at`` is the one staleness error a reader cannot
    detect.** Everything downstream reads this column as "when we saw it", and
    :func:`latest_observed_at_subquery` is ``ORDER BY captured_at DESC LIMIT 1``
    with no upper bound — so a post-dated row WINS its outcome's max and the
    served ``observed_at`` becomes a negative age, which renders as maximally
    fresh. Overstating staleness is conservative and self-correcting; claiming
    freshness we do not have is the #5459 / ruling 142 class, and it is silent.

    🔴 **The clamp is used rather than a reject because its false positives are
    free.** A capture cannot occur in the future, so pulling a post-dated stamp
    down to ``now`` can never turn a true statement false — the worst case is
    that a genuine close-time reconstruction is recorded a few seconds late.
    Dropping the row instead would lose a real price to defend a timestamp.

    Naive input is read as UTC rather than compared, because ``dt_parse`` returns
    a naive datetime for a stamp with no offset and comparing it to an aware
    ``now`` raises ``TypeError`` — an ingest path must not abort over a missing
    ``Z``. ``None`` means the venue gave us no time at all, and the honest stamp
    for "we read it just now" is ``now``.
    """
    if parsed is None:
        return now
    aware = parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return aware if aware <= now else now


def latest_observed_at_subquery():
    """Correlated scalar subquery: newest ``captured_at`` for ``FuturesOutcome.id``.

    Exposed separately from :func:`load_latest_observed_at` so the statement can
    be compiled and inspected without a session, and so a caller already
    selecting from ``futures_outcomes`` can add this as one more column rather
    than issuing a second round trip.

    ``.correlate(FuturesOutcome)`` is explicit rather than left to SQLAlchemy's
    auto-correlation: this subquery is only ever correct when the outer query
    supplies ``FuturesOutcome``, and an auto-correlation that quietly does not
    happen is a cross join against the whole snapshot table.
    """
    return (
        select(FuturesOddsSnapshot.captured_at)
        .where(
            FuturesOddsSnapshot.outcome_id == FuturesOutcome.id,
            # Dead today (schema NOT NULL), kept because it is the question.
            FuturesOddsSnapshot.probability.isnot(None),
            # NOT dead. `DESC` is NULLS FIRST in PostgreSQL — see the module
            # docstring. Removing this makes a NULL row win its own group.
            FuturesOddsSnapshot.captured_at.isnot(None),
        )
        .order_by(FuturesOddsSnapshot.captured_at.desc())
        .limit(1)
        .correlate(FuturesOutcome)
        .scalar_subquery()
    )


def _aware(stamp: object) -> Optional[datetime]:
    """Any stamp this module might be handed, as an aware datetime, or ``None``.

    Both columns compared here are ``timezone=True`` in the model and asyncpg
    returns them aware, so the naive branch is belt-and-braces against a caller
    — a test double, a SQLite gate — that hands over a naive one: ``max()`` over
    a mixed naive/aware pair raises ``TypeError``, and this runs on the request
    path.

    🔴 **AND THE TYPE IS NOT ASSUMED EITHER.** The first cut of this took
    ``Optional[datetime]`` and read ``.tzinfo`` off it, which is true of every
    production row and not of every caller: `test_latest_observation_lat_p147`
    hands `observed_at` in as an ISO STRING, so a freshness floor would have
    raised `AttributeError` on the request path — the 500-over-a-timestamp this
    module's own docstring refuses two functions up. A string is parsed (that is
    what :func:`_as_aware` is for) and anything else is UNKNOWN, which the
    caller must treat as "no comparison available" rather than as a date.
    """
    if isinstance(stamp, datetime):
        return stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=timezone.utc)
    if isinstance(stamp, str):
        return _as_aware(stamp)
    return None


def price_movement_floor(
    price_changed_at: Optional[datetime],
    resolution_source: Optional[str],
    current_probability: object,
) -> Optional[datetime]:
    """The observation a MOVED PRICE proves happened, or ``None`` (#6051).

    🔴 **A PRICE CANNOT CHANGE WITHOUT BEING OBSERVED.** That is the whole
    argument, and it is what lets this be a floor rather than a guess.
    ``price_changed_at`` is written by one shared expression
    (``utils/price_change_stamp.price_changed_at_value``) which returns
    ``now()`` only when the write would change the STORED six-decimal price and
    the row's existing stamp otherwise. So the column is a *lower bound* on the
    last time somebody read this market and got a different number.

    ## the defect this exists for, measured on production 2026-09-14 03:37Z

    ``/api/events/15311956/game-markets`` (Chunichi Dragons @ Hanshin Tigers,
    upcoming) served **every** Kalshi leg with ``observed_at`` of
    ``2026-09-13T22:28:27Z`` — 5.15 h before the read — while those same rows'
    ``price_changed_at`` read ``03:35:49Z``, ``03:34:12Z``, ``03:26:16Z``. The
    moneyline's price had moved **100 seconds** before the request that called
    it five hours old. The snapshot series had simply stopped: some writers move
    a price without recording an observation, so ``max(captured_at)`` answers
    *when we last WROTE A SNAPSHOT*, which is not the question the field asks.

    Not one row. On events within ±1 day, legs whose price provably moved after
    their newest snapshot: **polymarket 1,123 of 6,366** (mean gap 13.8 h) and
    **kalshi 3,067 of 14,035** (mean 2.05 h) — ``sql_fingerprint
    5f30865196b29997``.

    🔴 **AND THE CONSEQUENCE IS NOT A MISPRINTED NUMBER.**
    ``components/event/PriceAgeMark`` returns ``null`` unless the stamp is
    already stale, so a too-old ``observed_at`` does not merely misstate an age
    — it MANUFACTURES a "this price has gone quiet" warning over a card whose
    prices are moving every minute, which is the one thing that mark exists to
    say.

    ## the three refusals, each of which has a row that needs it

    * **``resolution_source`` must be absent.** ``tasks/backfill_winners.py``
      stamps ``price_changed_at`` in the same statement that CROWNS a leg
      ``1.0``/``0.0`` and sets ``resolution_source='api_settlement'``. The
      number did change then, but our grader's certainty is not a reading of a
      venue, and this field's callers ask the second question. Excluding graded
      rows removes exactly that write and nothing else.
    * **There must be a price for an age to be about.** ``tasks/datagolf.py``
      clears a withdrawn leg (``current_probability = None``) and stamps the
      change. Honouring that would date the disappearance of a price as an
      observation of one — and it is the row ``routes/tournaments.py`` already
      refuses under "no price, no observation".
    * **``price_changed_at`` itself may be absent**, on a row no write has ever
      moved.

    Returns a floor to be compared, never a stamp to be served on its own — see
    :func:`load_latest_observed_at` for why it can only ever move the answer
    NEWER, and only for ids that already have a real snapshot behind them.
    """
    if price_changed_at is None:
        return None
    if resolution_source is not None:
        return None
    if current_probability is None:
        return None
    return _aware(price_changed_at)


async def load_latest_observed_at(
    session: AsyncSession, outcome_ids: Iterable[int]
) -> dict[int, datetime]:
    """``{outcome_id: when this price was last observed}`` for the ids given.

    An outcome with no priced observation is **absent from the mapping**, not
    present with ``None``. That is the aggregate form's shape and callers depend
    on it: ``.get(id)`` yields ``None`` either way, but a caller that iterates or
    counts the mapping would silently start seeing rows that have never been
    observed. ``routes/tournaments.py`` states that dependence out loud — "no
    price, no observation … ``load_latest_observed_at`` only returns ids that
    have a PRICED snapshot, so its presence is itself the evidence".

    🔴 **WHICH IS WHY #6051's FLOOR NEVER ADDS A KEY.** A moved price
    (:func:`price_movement_floor`) can only make an EXISTING answer newer; an id
    with no snapshot stays out of the mapping even when its price demonstrably
    moved, because that caller reads membership as evidence and this module does
    not get to redefine the word underneath it. The population that forgoes:
    118 of 20,401 legs on ±1-day events have never been snapshotted at all, and
    showing them no age is the conservative answer they already get.

    The three extra columns ride the SELECT that was already visiting these
    rows, so the floor costs no second round trip.
    """
    ids = list(outcome_ids)
    if not ids:
        return {}

    rows = (
        await session.execute(
            select(
                FuturesOutcome.id,
                latest_observed_at_subquery().label("observed_at"),
                FuturesOutcome.price_changed_at,
                FuturesOutcome.resolution_source,
                FuturesOutcome.current_probability,
            ).where(FuturesOutcome.id.in_(ids))
        )
    ).all()

    observed: dict[int, datetime] = {}
    for row in rows:
        if row.observed_at is None:
            continue
        floor = price_movement_floor(
            row.price_changed_at, row.resolution_source, row.current_probability
        )
        snapshot_at = _aware(row.observed_at)
        # The snapshot is returned VERBATIM unless the floor actually wins, so
        # every row this rule does not touch serves the same bytes it served
        # before — the normalisation above exists for the comparison, not for
        # the payload.
        if floor is not None and snapshot_at is not None and floor > snapshot_at:
            observed[row.id] = floor
        else:
            observed[row.id] = row.observed_at

    return observed
