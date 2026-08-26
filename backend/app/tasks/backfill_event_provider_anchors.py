"""#1946 Item 8: write the correspondences the anchor channel was built to hold.

Queue 415. Three things landed before this one and none of them put a row in
the table:

* **Queue 393 / PR #2119** created ``event_provider_anchors``, empty, by design.
* **Queue 412R / PR #2220** shipped ``provider_anchor_keys`` — a correct answer
  to *"what would an anchor row for this id be?"* — and nothing called it.
* **Queue 413 / PR #2225** shipped ``anchor_channel`` — the reader and the
  forward writer — wired into the registry so that **new** correspondences are
  recorded as they are established.

The forward writer only fires when a correspondence is established, which is
the right rule for a live pipeline and the wrong one for a table that starts
empty: it means the channel learns about the games we see from today onward and
knows nothing about the 74,181 rows already sitting there. #2213's 41 duplicate
MLB groups are in that backlog, not in the future, so nothing the forward path
does will ever collapse them.

This module is the backfill. It reads ids that are already on the row, turns
them into namespace-qualified anchor keys with the same function the live path
uses, and writes them through the same ``record_anchor``. It derives no
identity of its own and it merges nothing.

WHAT IT DOES NOT DO, STATED FIRST BECAUSE IT IS THE EASY THING TO MISREAD
--------------------------------------------------------------------------

**It does not merge duplicates.** When two events claim one provider id, the
unique index refuses the second write and ``record_anchor`` reports
``COLLISION`` with the incumbent as canonical. That is *proof* that two rows are
one game — the first proof ruling 048's drain clause has ever had — and it is
still not authority to delete a row. The merge rail
(``event_merge_invariant.assert_mergeable``) owns that decision and applies the
#1947 corroboration arms to it. This task counts collisions, tags the losing
row so the pair is queryable, and stops.

**It does not widen absorption authority by a millimetre.** Every key comes from
``provider_anchor_keys``; a key that module classifies ``market`` or
``container`` is written as ``market`` or ``container`` and is never consulted
by cascade Step 2. Tennis stays ``market``. A Kalshi anchor is written only as
``sport_key:game_id``, never bare (Alex, 2026-08-21).

**It does not write link-derived anchors.** See the gate, below.

THE GATE, AND WHY IT SPLITS THE WORK IN TWO
-------------------------------------------

Item 8 has carried a launch gate since queue 387: the **sink census**. The
finding behind it is that anchors derived from ``futures_markets.event_id``
would encode every existing mislink as identity evidence — 570 sink events
measured Feb-Aug 2026, the worst holding 50 distinct game-ids, one of them an
event whose two team names are both literally "Over 2.5 maps".

``app/utils/anchor_backfill_gate.py`` turns that prose into a predicate, and the
predicate distinguishes two classes:

``CLASS_COLUMN_DERIVED``
    ``events.external_id`` (Odds API), ``events.espn_id``,
    ``events.statpal_fixture_id``. A scalar column cannot hold two values, so
    one row yields at most one anchor per provider. There is no grouping to
    invert and no sink to census. **This class runs.**
``CLASS_LINK_DERIVED``
    Kalshi and Polymarket, reachable only through ``futures_markets.event_id``.
    This is the population the census was measured on. **This class is refused**
    until ``M-SINK-CENSUS-1`` returns, and the refusal is a code path with a
    test, not a comment.

Splitting it is not a loosening. It is the gate applied to the population the
gate was measured on, and it is what lets the safe half ship while the measured
half waits for its measurement.

ORDERING — AND WHY IT IS *NOT* OLDEST-FIRST HERE
-------------------------------------------------

Gotcha #41 says a bulk backfill needs both bounds and warns that newest-first
starves the old tail. Its second clause is the one that decides this case:
*oldest-first over an EXPIRING population without a floor processes the dead
first.* The question it tells you to ask is **what the ordering starts on**.

This population does not expire. An ``espn_id`` sitting on a 2026-February row
is exactly as writable next month as it is today, so a deferred tail is deferred
and not lost — the failure mode #41 exists to prevent cannot occur here. The
ship, meanwhile, is dated: #2213's 41 duplicate groups are the 2026-08-25 MLB
slate and the ones that follow it. Oldest-first would spend every early run on
February esports before reaching the games Alex is looking at.

So: **newest-first within an explicit floor**, and the deferral is made loud
rather than silent. Every run reports ``remaining_in_window`` and
``below_floor``, because a bounded sweep that does not say what it skipped reads
as "covered everything" when it did not.

VERDICT
-------

The summary carries a ``terminal`` field so ``task_verdict`` can classify it
(gotcha #53: "it returned" is not "it worked"). A run that wrote nothing because
the gate refused everything reports ``no_work`` and is *not* green — which is
the correct reading, and the reading a bare row count would have hidden.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.anchor_channel import (
    COLLISION,
    CONFIRMED,
    NO_KEY,
    WROTE,
    duplicate_tag,
    record_anchor,
)
from app.utils.anchor_backfill_gate import (
    CLASS_COLUMN_DERIVED,
    CLASS_LINK_DERIVED,
    gate_for,
)
from app.utils.provider_anchor_keys import (
    espn_anchor_key,
    odds_api_anchor_key,
    statpal_anchor_key,
)

logger = logging.getLogger(__name__)

#: How many rows one invocation will look at. Bounded so the task cannot become
#: the thing it is backfilling for.
DEFAULT_LIMIT = 2000

#: The floor, in days before now, on ``commence_time``. Rows older than this are
#: not processed by a default run and are counted as ``below_floor`` so the
#: remainder is visible. 400 days covers a full season cycle plus the Kalshi
#: corpus, which starts 2026-02.
DEFAULT_FLOOR_DAYS = 400

#: The three scalar provider-id columns on ``events``, and the key function each
#: one goes through. There is deliberately no fourth entry: Kalshi and
#: Polymarket have no column, which is the entire finding of #1946.
_COLUMN_SOURCES: tuple[tuple[str, str, Any], ...] = (
    ("external_id", "odds_api", odds_api_anchor_key),
    ("espn_id", "espn", espn_anchor_key),
    ("statpal_fixture_id", "statpal", statpal_anchor_key),
)

#: Newest-first within the floor. See the module docstring for why the ordering
#: is the opposite of the usual bulk-backfill default, and why #41 permits it.
_CANDIDATE_SQL = text("""
    SELECT id, external_id, espn_id, statpal_fixture_id, commence_time
    FROM events
    WHERE commence_time >= NOW() - make_interval(days => :floor_days)
      AND (
            external_id IS NOT NULL
         OR espn_id IS NOT NULL
         OR statpal_fixture_id IS NOT NULL
      )
    ORDER BY commence_time DESC, id DESC
    LIMIT :limit OFFSET :offset
    """)

#: Counted, never processed, so the skip is reported rather than implied.
_BELOW_FLOOR_SQL = text("""
    SELECT COUNT(*)
    FROM events
    WHERE commence_time < NOW() - make_interval(days => :floor_days)
      AND (
            external_id IS NOT NULL
         OR espn_id IS NOT NULL
         OR statpal_fixture_id IS NOT NULL
      )
    """)

_IN_WINDOW_SQL = text("""
    SELECT COUNT(*)
    FROM events
    WHERE commence_time >= NOW() - make_interval(days => :floor_days)
      AND (
            external_id IS NOT NULL
         OR espn_id IS NOT NULL
         OR statpal_fixture_id IS NOT NULL
      )
    """)

#: The losing row of a collision is tagged so the pair is queryable without
#: re-deriving it. Uses the same `provenance:` vocabulary the registry writes
#: under ruling 048, and is idempotent — a re-run appends nothing new.
_TAG_SQL = text("""
    UPDATE events
       SET event_tags = CASE
             WHEN event_tags IS NULL THEN :tag
             WHEN event_tags LIKE '%' || :tag || '%' THEN event_tags
             ELSE event_tags || ',' || :tag
           END
     WHERE id = :event_id
    """)


def _row_value(row: Any, index: int, name: str) -> Any:
    """Read a driver row positionally, falling back to attribute access.

    Both shapes turn up: asyncpg rows index cleanly, and the test doubles in
    this repo hand back ``SimpleNamespace``. Neither is worth a mapping layer.
    """
    try:
        return row[index]
    except (TypeError, KeyError, IndexError):
        return getattr(row, name, None)


async def backfill_column_anchors(
    session: AsyncSession,
    *,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    floor_days: int = DEFAULT_FLOOR_DAYS,
    apply: bool = False,
) -> dict[str, Any]:
    """Write anchors for every id already sitting in a column on ``events``.

    ``apply=False`` is the default and it means *derive everything, write
    nothing* — the counts come back identical in shape so a dry run and a real
    run are comparable line for line. A backfill whose dry run exercises a
    different code path than its real run has not been dry-run.
    """
    gate = gate_for(CLASS_COLUMN_DERIVED)
    if not gate.may_write:
        # Unreachable today by construction, and tested anyway: a gate that has
        # never refused is a gate nobody has read.
        return {
            "terminal": "skipped",
            "reason": gate.reason,
            "gate_state": gate.state,
            "anchor_class": CLASS_COLUMN_DERIVED,
        }

    params = {"floor_days": floor_days, "limit": limit, "offset": offset}
    rows = (await session.execute(_CANDIDATE_SQL, params)).fetchall()

    counts = {WROTE: 0, CONFIRMED: 0, COLLISION: 0, NO_KEY: 0}
    per_source: dict[str, dict[str, int]] = {}
    collisions: list[dict[str, Any]] = []
    row_errors = 0

    for row in rows:
        event_id = _row_value(row, 0, "id")
        if event_id is None:
            row_errors += 1
            continue

        for column_index, (column, source, key_fn) in enumerate(
            _COLUMN_SOURCES, start=1
        ):
            raw = _row_value(row, column_index, column)
            if raw is None or str(raw).strip() == "":
                continue

            bucket = per_source.setdefault(
                source, {WROTE: 0, CONFIRMED: 0, COLLISION: 0, NO_KEY: 0}
            )

            try:
                key = key_fn(str(raw))
            except Exception:  # noqa: BLE001
                # One bad id must never wipe the pass (gotcha #42). An
                # unparseable StatPal namespace is exactly the input
                # `compare_statpal_ids` refuses to guess about.
                logger.exception(
                    "anchor backfill: %s=%r on event %s could not be keyed",
                    column,
                    raw,
                    event_id,
                )
                row_errors += 1
                continue

            if key is None:
                counts[NO_KEY] += 1
                bucket[NO_KEY] += 1
                continue

            if not apply:
                # Dry run: report what WOULD be written, and do not pretend to
                # know whether it would conflict. Guessing the outcome here is
                # how a dry run starts disagreeing with its real run.
                counts[WROTE] += 1
                bucket[WROTE] += 1
                continue

            try:
                result = await record_anchor(
                    session,
                    event_id=int(event_id),
                    key=key,
                    claim_context={
                        "via": "backfill_event_provider_anchors",
                        "column": column,
                        "issue": 1946,
                        "item": 8,
                    },
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "anchor backfill: writing %s:%s for event %s failed",
                    key.source,
                    key.source_id,
                    event_id,
                )
                row_errors += 1
                continue

            counts[result.outcome] = counts.get(result.outcome, 0) + 1
            bucket[result.outcome] = bucket.get(result.outcome, 0) + 1

            if result.outcome == COLLISION:
                canonical = result.canonical_event_id
                collisions.append(
                    {
                        "source": key.source,
                        "source_id": key.source_id,
                        "id_kind": key.id_kind,
                        "canonical_event_id": canonical,
                        "duplicate_event_id": int(event_id),
                    }
                )
                if canonical is not None:
                    try:
                        await session.execute(
                            _TAG_SQL,
                            {
                                "tag": duplicate_tag(int(canonical)),
                                "event_id": int(event_id),
                            },
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "anchor backfill: tagging event %s as duplicate-of %s "
                            "failed — the anchor row still stands",
                            event_id,
                            canonical,
                        )
                        row_errors += 1

    in_window = (
        await session.execute(_IN_WINDOW_SQL, {"floor_days": floor_days})
    ).scalar()
    below_floor = (
        await session.execute(_BELOW_FLOOR_SQL, {"floor_days": floor_days})
    ).scalar()

    examined = len(rows)
    remaining = max(int(in_window or 0) - (offset + examined), 0)

    # A run that examined rows and derived nothing is not a success, and a run
    # that derived nothing because there was nothing left is not a failure. Say
    # which one happened rather than emitting a count and letting the reader
    # decide.
    derived = counts[WROTE] + counts[CONFIRMED] + counts[COLLISION]
    if examined == 0:
        terminal = "no_work"
    elif derived == 0:
        terminal = "partial"
    elif remaining > 0:
        terminal = "partial"
    else:
        terminal = "complete"

    return {
        "terminal": terminal,
        "anchor_class": CLASS_COLUMN_DERIVED,
        "gate_state": gate.state,
        "applied": bool(apply),
        "examined": examined,
        "completed": derived,
        "total": derived + counts[NO_KEY],
        "outcomes": counts,
        "per_source": per_source,
        "collisions": collisions[:50],
        "collision_count": len(collisions),
        "row_errors": row_errors,
        "floor_days": floor_days,
        "in_window": int(in_window or 0),
        "remaining_in_window": remaining,
        "below_floor": int(below_floor or 0),
    }


async def backfill_link_anchors(
    session: AsyncSession,
    *,
    limit: int = DEFAULT_LIMIT,
    apply: bool = False,
) -> dict[str, Any]:
    """Kalshi and Polymarket anchors, derived through ``futures_markets``.

    This is the half the sink census gates, and today the gate refuses it. The
    function exists — rather than the work simply being absent — so the refusal
    is a thing that runs, returns a reason, and can be asserted on. An
    unimplemented gate and a closed gate look identical from the outside, and
    only one of them opens when the measurement arrives.
    """
    gate = gate_for(CLASS_LINK_DERIVED)
    if not gate.may_write:
        logger.info("anchor backfill: link-derived class refused — %s", gate.reason)
        return {
            "terminal": "skipped",
            "anchor_class": CLASS_LINK_DERIVED,
            "gate_state": gate.state,
            "reason": gate.reason,
            "examined": 0,
            "completed": 0,
        }

    # Reached only once M-SINK-CENSUS-1 has returned and its dispositions have
    # been adopted in `anchor_backfill_gate.SINK_CENSUS`. The derivation itself
    # is deliberately not written ahead of the census, because the census
    # decides which classes are written as `game`, which as `market`, and which
    # not at all — writing it first would mean writing it to be rewritten.
    return {
        "terminal": "skipped",
        "anchor_class": CLASS_LINK_DERIVED,
        "gate_state": gate.state,
        "reason": (
            "gate is OPEN but the link-derived derivation is not implemented "
            "yet — it is written against the census's per-class dispositions, "
            f"which arrive with {gate.reason}"
        ),
        "excluded_classes": sorted(gate.excluded_classes),
        "examined": 0,
        "completed": 0,
    }


async def run_backfill_event_provider_anchors(
    session: AsyncSession,
    *,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    floor_days: int = DEFAULT_FLOOR_DAYS,
    apply: bool = False,
) -> dict[str, Any]:
    """Run both classes and report them separately.

    Separately, and not summed: a total that adds a class that ran to a class
    that was refused is a number with no meaning, and it is the number that
    would let a refused gate read as a completed backfill.
    """
    column = await backfill_column_anchors(
        session, limit=limit, offset=offset, floor_days=floor_days, apply=apply
    )
    link = await backfill_link_anchors(session, limit=limit, apply=apply)

    # The run's verdict is the column class's verdict: it is the only class that
    # can do work today, and inheriting `skipped` from the gated class would
    # report a working backfill as no-work.
    return {
        "terminal": column.get("terminal", "unknown"),
        "completed": column.get("completed", 0),
        "total": column.get("total", 0),
        "column_derived": column,
        "link_derived": link,
    }


def summarize_for_operator(result: dict[str, Any]) -> str:
    """One-line human summary, for a log line or an admin response."""
    column = result.get("column_derived") or {}
    link = result.get("link_derived") or {}
    outcomes = column.get("outcomes") or {}
    mode = "APPLY" if column.get("applied") else "DRY-RUN"
    return (
        f"anchor backfill [{mode}] {result.get('terminal')}: "
        f"examined {column.get('examined', 0)}, "
        f"wrote {outcomes.get(WROTE, 0)}, "
        f"confirmed {outcomes.get(CONFIRMED, 0)}, "
        f"collisions {column.get('collision_count', 0)}, "
        f"no-key {outcomes.get(NO_KEY, 0)}, "
        f"remaining-in-window {column.get('remaining_in_window', 0)}, "
        f"below-floor {column.get('below_floor', 0)} "
        f"| link-derived {link.get('gate_state')}"
    )
