"""CAL-P080 (#2007, #1912, #1544) — Gate 0's twin, run WHERE ITS BUDGET FITS.

Why this file exists, and it is a reachability problem, not a logic one
-----------------------------------------------------------------------
CAL-P078 built the DB-direct twin of the published curve
(:mod:`app.utils.calibration_published_twin`) and CAL-P079 built the script that
drives it (``scripts/measure_published_twin.py``). Both are correct and neither
had anywhere to run:

* **From an agent sandbox** the fold cannot run at all — TCP egress to 5432 is
  blocked, so ``get_task_session()`` never connects.
* **Through the admin ``db-query`` rail** it cannot run either. CAL-P079
  measured the reason and it is not a tuning knob: the rail's row path
  **hardcodes a 10 s ``statement_timeout``** against an instrument whose own
  default budget is **240 s**. Twenty-four times short. Raising the rail's cap
  is not the fix — a general read endpoint holding a connection for four
  minutes is a different and worse problem — so the falsification's conclusion
  was that the reader belongs INSIDE the dyno, next to the database, on a
  worker whose budget is its own.

That conclusion is what this module implements. Nothing here re-litigates it.

So the fold's remaining home was a laptop with production credentials, which
is to say: nowhere durable. Gate 0's verdict was reachable only by a human
running a script by hand, and a gate that only a human can fire is a gate that
does not fire.

What runs, and what it deliberately does NOT do
------------------------------------------------
One SELECT and one artifact write. It reads:

* the **database**, via the frozen population predicate used VERBATIM (see the
  twin module's header for why a hand-mirror would be worse than useless), and
* the **published payload**, from the same Redis key the request path serves
  from, so the comparison's subject is the artifact readers actually get rather
  than a fresh recompute that no reader has ever seen.

It writes exactly one durable snapshot and no market data (gotcha #21). It is
**not on the beat schedule**, for the reason ``cohort_cell_census`` is not: it
reads the same heavy population the deadline-critical hourly q268 producer
reads from :15 to ~:35, and CAL-P074 measured self-inflicted contention costing
a cell its whole first pass. The quiet window is a choice an operator makes.

Honest failure, because this gate has exactly one way to lie
-------------------------------------------------------------
The dangerous outcome is not ``disagrees`` — that is the gate working. It is a
run that reads NOTHING and reports agreement over zero rows, which is gotcha
#53 aimed at the instrument. Three guards, all of them load-bearing:

1. A fold error or an unreadable payload forces ``unmeasurable`` and names the
   cause. It never degrades to ``agrees``.
2. Zero folded rows forces ``unmeasurable`` even when the SELECT "succeeded":
   the published curve has hundreds of thousands of outcomes behind it, so an
   empty fold is a broken read, not an empty database.
3. The task's ``terminal`` is ``complete`` only for a real verdict. An
   unmeasurable run terminates ``failed``, so it cannot read GREEN in
   ``task-metrics``. The task is enrolled in ``ENFORCED_TASKS`` in the same
   change that gives it this terminal — enrolment without a terminal is a
   no-op, which is the trap that file documents at length.

CAL-P084 (#2076) — the twin could not produce a verdict, for TWO reasons
------------------------------------------------------------------------
CAL-P083 filed #2076 against the fold's budget. That was a real blocker and it
was not the only one; the second was hidden behind it, because a run that never
gets past the fold never reaches the comparison.

**Blocker 1 — the fold does not fit its budget, and 900 s does not fix it.**
Measured twice, at both ends: ``fold_duration_s 241.18`` against 240 s
(CAL-P083) and ``901.96`` against 900 s (CAL-P084, generation 1787331305993,
2026-08-21 16:55:05Z), both ``db_rows 0``, both ``QueryCanceledError`` on the
``market_info`` CTE chain. :data:`MAX_TIMEOUT_MS` is raised to the largest value
the task's limits can honour; whether that is enough is the next measurement,
and it is written down as such rather than assumed.

**Blocker 2 — the twin was reading the ``staged`` block off a payload that has
never carried one.** This is the one that mattered, because no fold budget would
have fixed it. ``_read_published_payload`` reads the Redis key
``bainluck:calibration:main``, which is correct — that IS the published artifact
— but ``routes/calibration.py:1000`` composes the ``staged`` block **at request
time** onto a *copy* (``out = dict(payload)``). The producer never writes it to
Redis. So ``payload.get("staged")`` was always ``None``, ``tolerance_pp(None)``
is ``None`` by design ("the payload does not disclose its own drift, so there is
no bound"), and :func:`reconcile` returns ``unmeasurable``.

**Gate 0's twin would therefore have returned ``unmeasurable`` over a fold that
finished perfectly.** Measured on the same artifact that recorded the 900 s
timeout: ``payload_error`` null (the read SUCCEEDED), ``published_generated_at``
``2026-08-21T16:35:07.919Z`` (a real, fresh generation), and ``staged`` JSON
``null`` — while ``GET /api/calibration`` over that same producer output served
a measured block earning a 100.0 pp bound. The instrument was honest about
everything except the one thing it could not see.

The fix is to read the disclosure the way the ROUTE reads it — from the same two
durable rows, through the same ``build_disclosure`` — so the bound the twin
grades against is the bound a reader is actually served, rather than a field
that only exists downstream of the twin's own read.

The subject can rotate underneath a 22-minute fold
---------------------------------------------------
At 240 s this was theoretical. At 1350 s it is not: the beat publishes hourly
and the fold can now span a publish. The bound is a **sawtooth with a one-beat
trough** (CAL-P083: 100.0 -> 0.5 at the promotion beat, 85.94 the next, 100.0
the one after), so a tight-bounded verdict is obtainable in roughly one hour in
sixteen — and a fold that starts inside the trough and ends outside it would
otherwise grade today's database against a bound the payload no longer earns.

So the disclosure is read **before and after** the fold. If it rotated, the
**wider** of the two bounds is used and the rotation is named on the artifact.
Wider, not tighter, and not a refusal: borrowing a trough bound for a generation
that is no longer served is the flattering direction and is the exact shape of
the defect this gate exists to catch, while refusing outright would throw away
the verdict in precisely the hour Gate 0 is supposed to be runnable.

CAL-P086B — THE PREMISE IS NO LONGER UNTESTED. Source-chunking is REFUTED.
---------------------------------------------------------------------------
The paragraph that used to sit here declined #2076's option 2/3 (one chunk per
``source``) on a premise it stated and never measured, and named the obstacle:
``POST /admin/db-query`` refuses this SQL as ``Multi-statement`` because the
frozen builder's COMMENTS carry 15 semicolons. That was a tooling obstacle, not
a law. ``app/utils/sql_comment_strip.py`` removes it; ``scripts/
explain_twin_fold_pushdown.py`` asks the planner. Measured 2026-08-21, plan-only
(``explain: true``, never ``analyze``), artifact
``artifacts/cal-p086b/ARTIFACT-CAL-P086B-2076-PUSHDOWN-EXPLAIN.json``:

**1. The premise was RIGHT, and exactly right.** A ``WHERE d.source = ...`` on
the final SELECT changes the plan by **nothing**: total cost 9,368,253.4 ->
9,368,698.01 (a ratio of **1.0000**, and it went UP), the same 110 nodes, and
``ranked_outcomes``' self-cost identical to the decimal at 6,781,188.7. The
predicate does not reach the CTEs at all. Seven such chunks cost **7.00x**.

**2. But the fix it rules out is not the only chunking shape.** ``market_info``
is the single base CTE everything descends from, so a predicate injected into
ITS ``WHERE`` needs no pushdown — the population is smaller from the first scan.
That works: kalshi **0.3296x**, polymarket **0.7616x**, datagolf 0.0025x, and
the seven-chunk SUM is **1.0939x** — a 9.4% total overhead, not 7x.

**3. And it still does not fix #2076, for two reasons that are arithmetic.**
The budget is per-statement, so what matters is the BIGGEST chunk, not the sum:
polymarket at **0.7616x** of a fold that has never finished in 1,350 s is a 24%
shave on the binding case, against a cost model CAL-P085 measured understating
THIS fold by **>= 2.35x**. And the partition is far smaller than it looked:
``SELECT source, count(*) FROM futures_markets WHERE status='resolved'`` returns
**three** values (polymarket 569,781 / kalshi 225,274 / datagolf 295). The
seven-way decomposition quoted in the old paragraph counted PUBLISHED PAYLOAD
BUCKETS, not population rows. It is a 2-way split wearing a 7-way name.

**4. Before it is a cost question it is a CORRECTNESS question, and that half
is not settled either.** The population's aggregates are source-scoped and safe
(``group_sizes``/``event_sizes`` group by ``(x, source)``; ``virtual_market``
joins carry ``AND gs.source = mi.source``; ``vm_stats`` groups by ``vm.source``)
— but ``vm_id`` is ``'g:'||group_id | 'e:'||event_id | 'm:'||market_id`` and
carries **no source**, while ``mode_prices`` groups by bare ``vm_id`` and
``deduped`` joins on bare ``vm_id``. Measured: **1,271 event_ids reach
``event_size >= 3`` under more than one source** (0 group_ids do). On those, an
unchunked fold can suppress one source's legs with a mode price computed from
the other's, and a chunked fold cannot. Whether any of the 1,271 actually
cross-suppresses today is **NOT measured**. So a source-chunked fold is not
proven row-identical to the whole fold.

**The decision, per the directive: the plan decides, not the planner's cost.**
The plan says tail-chunking is refuted structurally and root-chunking works
structurally; the arithmetic says root-chunking does not clear the budget. So
#2076's option 2/3 is closed alongside option 1, and the remaining avenue is
the in-dyno shape CAL-P079 identified — a reader whose budget is its own, on a
host with no Celery ``soft_time_limit`` over it. See
:func:`app.tasks.calibration_published_twin_worker` module notes and
``scripts/measure_published_twin.py``, whose ``--timeout-ms`` has no ceiling.

AND THE THING THE MEASUREMENT FOUND THAT #2076 WAS NOT LOOKING FOR
-------------------------------------------------------------------
The fold's population is the FUTURES population only. The published curve has
seven sources; four of them (``odds_api``, ``odds_api_bookmaker``,
``odds_api_totals``, ``odds_api_spreads``) are built by separate SQL in
``precompute_calibration.py`` (:3677, :3729, :3778, bookmaker at :3838) over a
different population. So **203 of 285 published cells (71.2%)**, 874 of 1,934
buckets and 135,102 of 867,101 outcomes can NEVER have a twin row.

``reconcile`` counted them into ``published_only`` and reported them, which was
honest — but the VERDICT never read that list, so Gate 0 could return ``agrees``
having compared 28.8% of the curve's cells. That is blocker 2's shape a third
time: an instrument honest about everything except the one thing it cannot see,
and it would have been the FIRST thing a finished fold got wrong. Fixed in
:func:`app.utils.calibration_published_twin.reconcile` by splitting
``published_only`` into out-of-scope (a declared, counted limit) and in-scope
(a population disagreement, which now forces ``disagrees``).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

#: The durable artifact this worker owns.
TWIN_IDENTITY = "calibration:published_twin"
TWIN_SCHEMA = "calibration-published-twin/v1"

#: The Redis key the request path's tier 2 serves from. Read here so the twin's
#: subject is the PUBLISHED artifact, not a recompute.
PUBLISHED_MAIN_KEY = "bainluck:calibration:main"

#: The instrument's own budget, from ``scripts/measure_published_twin.py``.
#:
#: ⚠️ **240 s IS MEASURED INSUFFICIENT** (#2076, CAL-P083: ``fold_duration_s
#: 241.18`` against a 240 000 ms budget, ``db_rows 0``, ``QueryCanceledError``).
#: It is kept as the DEFAULT only because it is the documented instrument budget
#: and changing a default silently is how a number stops being a decision; every
#: real gate run passes ``timeout_ms`` explicitly. See :data:`MAX_TIMEOUT_MS`.
DEFAULT_TIMEOUT_MS = 240_000

#: Hard ceiling on an operator-supplied budget.
#:
#: **RAISED 900 000 -> 1 350 000 by CAL-P084, on a measurement rather than a
#: hunch.** 2026-08-21 16:40:03Z a run was fired at the then-ceiling of 900 s and
#: was cancelled at ``fold_duration_s 901.96`` with ``db_rows 0`` — the same
#: ``QueryCanceledError`` on the same ``market_info`` CTE chain as at 240 s. So
#: the fold does not fit in 900 s either, and #2076's option 1 ("raise the
#: budget") is **refuted at 900 s and untested above it**. This ceiling is the
#: largest the task's limits can honour, not a belief that the fold fits inside
#: it: the task is ``soft_time_limit=1800``, and 1350 s leaves 450 s for the
#: disclosure reads, the payload read and the durable write. A statement allowed
#: to outlive the soft limit would be killed mid-flight with no artifact written,
#: which is the one outcome worse than a timeout — the whole reason there is a
#: ceiling at all.
#:
#: If 1350 s is also consumed, budget is exhausted as an avenue and the fold MUST
#: be narrowed (#2076 options 2/3). See this module's header for why the obvious
#: narrowing is not yet safe to ship.
MAX_TIMEOUT_MS = 1_350_000
MIN_TIMEOUT_MS = 1_000


def clamp_timeout_ms(value: Any) -> int:
    """Coerce an operator-supplied budget into the range the worker can honour.

    Clamped rather than rejected: an out-of-range number is an operator asking
    for a longer look, and refusing the whole run over it would trade a
    measurable gate for a 422.
    """
    try:
        ms = int(value)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_MS
    return max(MIN_TIMEOUT_MS, min(MAX_TIMEOUT_MS, ms))


async def _read_published_payload() -> tuple[dict, Optional[str]]:
    """The payload the request path serves. Returns ``(payload, error)``.

    Never raises. A miss and a Redis failure are DIFFERENT facts and are named
    differently — an absent key means the producer has not published, which is
    a real finding about the producer; a failed client is a fact about us.
    """
    try:
        from app.utils import request_cache as _rc

        rc = await _rc.get_shared_async_redis()
        res = await _rc.bounded_redis_call(lambda: rc.get(PUBLISHED_MAIN_KEY))
    except Exception as exc:  # noqa: BLE001 — recorded, never swallowed
        return {}, f"published_read_raised: {type(exc).__name__}: {exc}"

    if not getattr(res, "is_ok", False):
        return {}, "published_read_failed: redis call did not complete"
    if res.value is None:
        return {}, f"published_absent: {PUBLISHED_MAIN_KEY} is not set"
    try:
        payload = json.loads(res.value)
    except Exception as exc:  # noqa: BLE001
        return {}, f"published_undecodable: {type(exc).__name__}: {exc}"
    if not isinstance(payload, dict):
        return {}, f"published_wrong_shape: {type(payload).__name__}"
    return payload, None


async def read_served_disclosure() -> tuple[Optional[dict], Optional[int], Optional[str]]:
    """The ``staged`` block a READER is served. ``(disclosure, ledger_gen, error)``.

    Mirrors ``routes/calibration.py::_read_staged_disclosure`` deliberately —
    same two durable identities, same ``build_disclosure``, same
    ``max_age_s`` of forever — because the twin's whole job is to grade the
    artifact readers actually get. Composing the bound any other way would be
    grading a number nobody is served.

    The ledger generation is returned alongside so the caller can tell whether
    the subject rotated during a fold that now runs for up to 22 minutes.

    ``max_age_s`` is deliberately enormous, for the route's own reason: an
    ANCIENT bank is exactly the fact being disclosed, and refusing to read it
    past an age bound would hide the only case that matters.
    """
    from app.services.durable_snapshots import read_snapshot_standalone
    from app.tasks.calibration_main_build import (
        LEDGER_IDENTITY,
        STAGED_FUTURES_IDENTITY,
    )
    from app.utils.calibration_phase_ledger import PHASE_LEDGER_SCHEMA
    from app.utils.calibration_staged_disclosure import build_disclosure
    from app.utils.calibration_staged_futures import STAGED_FUTURES_SCHEMA

    forever = 3650 * 86400
    try:
        bank = await read_snapshot_standalone(
            STAGED_FUTURES_IDENTITY,
            expected_version=STAGED_FUTURES_SCHEMA,
            max_age_s=forever,
        )
        ledger = await read_snapshot_standalone(
            LEDGER_IDENTITY, expected_version=PHASE_LEDGER_SCHEMA, max_age_s=forever
        )
    except Exception as exc:  # noqa: BLE001 — recorded, never swallowed
        return None, None, f"disclosure_read_raised: {type(exc).__name__}: {exc}"

    # ``ok``, not ``envelope is not None``. A wrong_version read still carries an
    # envelope, and taking its ``generated_at`` would date this bank from some
    # other artifact's row — the route makes the same distinction for the same
    # reason.
    if not bank.ok or bank.envelope is None:
        return None, None, f"staged_cursor_unreadable: {bank.status}"
    if not ledger.ok or ledger.envelope is None or not isinstance(
        ledger.envelope.payload, dict
    ):
        return None, None, f"phase_ledger_unreadable: {ledger.status}"

    disclosure = build_disclosure(
        ledger_stages=ledger.envelope.payload.get("stages"),
        staged_generated_at=bank.envelope.generated_at,
    )
    return disclosure, ledger.envelope.generation, None


def wider_disclosure(before: Any, after: Any) -> tuple[Any, Optional[str]]:
    """Of two disclosures, the one earning the LOOSER bound. ``(chosen, note)``.

    Called only when the subject rotated during the fold. Wider on purpose: a
    tight bound belonging to a generation that is no longer served is the
    flattering direction, and this gate exists to refuse exactly that kind of
    borrowed number. An unmeasurable disclosure is the widest of all — there is
    no bound at all — so it wins outright.
    """
    from app.utils.calibration_published_twin import tolerance_pp

    b_bound = tolerance_pp(before)
    a_bound = tolerance_pp(after)
    if b_bound is None or a_bound is None:
        return (before if b_bound is None else after), "rotated: one side unmeasurable"
    if b_bound >= a_bound:
        return before, f"rotated: kept the wider pre-fold bound {b_bound} >= {a_bound}"
    return after, f"rotated: kept the wider post-fold bound {a_bound} > {b_bound}"


async def _fold(*, timeout_ms: int) -> tuple[list, float, Optional[str]]:
    """Run the canonical population fold. Returns ``(rows, duration_s, error)``.

    The error is RETURNED, not thrown, so the artifact records that the read was
    attempted and failed — a different fact from a read that was never made
    (ruling 075 clause 2). Deliberately identical in shape to the script's
    ``_fold`` so the two drivers cannot drift in how they treat a failure.
    """
    from sqlalchemy import text

    from app.tasks.base import get_task_session
    from app.utils.calibration_published_twin import published_population_fold_sql

    sql = published_population_fold_sql()
    started = time.monotonic()
    try:
        async with get_task_session() as session:
            await session.execute(
                text(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
            )
            result = await session.execute(text(sql))
            rows = result.all()
        return rows, time.monotonic() - started, None
    except Exception as exc:  # noqa: BLE001 — recorded, never swallowed
        return [], time.monotonic() - started, f"{type(exc).__name__}: {exc}"


def build_artifact(
    *,
    rows: list,
    fold_duration_s: float,
    fold_error: Optional[str],
    payload: dict,
    payload_error: Optional[str],
    timeout_ms: int,
    staged: Any = None,
    staged_error: Optional[str] = None,
    rotation_note: Optional[str] = None,
    ledger_generation_before: Optional[int] = None,
    ledger_generation_after: Optional[int] = None,
) -> dict:
    """Pure. Assemble the artifact and decide its verdict and terminal.

    Separated from the I/O above so every branch — including the ones that only
    happen when production is broken — is reachable from a unit test without a
    database or a Redis.
    """
    from app.utils.calibration_published_twin import (
        fold_rows_to_cells,
        reconcile,
        tolerance_pp,
    )

    cells = fold_rows_to_cells(rows)
    db_rows = sum(b["n"] for buckets in cells.values() for b in buckets.values())

    # CAL-P084 (#2076) blocker 2. The bound comes from the disclosure the ROUTE
    # composes, not from the Redis payload — the producer has never written a
    # `staged` block there, so the old `payload.get("staged")` was always None
    # and every verdict was unmeasurable no matter how the fold went. Both are
    # recorded: `staged` is what the bound was taken from, `payload_staged` is
    # what the published artifact itself carried, so the day the producer starts
    # writing one the disagreement is visible instead of silently preferred.
    payload_staged = payload.get("staged")
    verdict = reconcile(
        db_cells=cells,
        published_buckets=payload.get("buckets") or [],
        staged=staged,
    )

    artifact: dict = {
        "queue": "CAL-P084",
        "issue": 2007,
        "gate": "Gate 0 — bounded agreement, published curve vs DB-direct (in-dyno)",
        "runner": "in_dyno_worker",
        "timeout_ms": timeout_ms,
        "fold_duration_s": round(fold_duration_s, 2),
        "fold_error": fold_error,
        "payload_error": payload_error,
        "payload_source": PUBLISHED_MAIN_KEY,
        "published_generated_at": payload.get("generated_at"),
        "published_availability": payload.get("availability"),
        "staged": staged,
        "staged_error": staged_error,
        "staged_source": "durable ledger + staged_futures, via build_disclosure",
        "payload_staged": payload_staged,
        "payload_carries_staged": payload_staged is not None,
        "subject_rotated_during_fold": rotation_note is not None,
        "rotation_note": rotation_note,
        "ledger_generation_before": ledger_generation_before,
        "ledger_generation_after": ledger_generation_after,
        "tolerance_pp": tolerance_pp(staged),
        "db_cells": len(cells),
        "db_rows": db_rows,
        **verdict,
    }

    # Guard 1 + 2 — a read that failed, or read nothing, must never present as a
    # clean agreement. The zero-row clause is not paranoia: the published curve
    # is folded from hundreds of thousands of outcomes, so zero means the SELECT
    # did not see the population, and `reconcile` over an empty left-hand side
    # has nothing to disagree with.
    #
    # CAL-P084 adds `staged_error` to the same clause. An unreadable disclosure
    # is a THIRD way to have no bound, and it is a fact about us rather than
    # about the payload's honesty, so it must be named separately from
    # `reconcile`'s own "the payload did not disclose its drift".
    if fold_error or payload_error or staged_error:
        artifact["verdict"] = "unmeasurable"
        artifact.setdefault(
            "unmeasurable_reason", fold_error or payload_error or staged_error
        )
    elif db_rows <= 0:
        artifact["verdict"] = "unmeasurable"
        artifact["unmeasurable_reason"] = (
            "fold returned zero rows — the published curve has a population, so "
            "an empty fold is a failed read, not an empty database"
        )

    # Guard 3 — the terminal, which is what keeps this out of a false GREEN.
    # `disagrees` is COMPLETE on purpose: the gate ran and found something, which
    # is the instrument succeeding. Only "could not measure" is a failed run.
    artifact["terminal"] = (
        "complete" if artifact["verdict"] in ("agrees", "disagrees") else "failed"
    )
    artifact["measured"] = artifact["verdict"] in ("agrees", "disagrees")
    return artifact


async def run_published_twin(*, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> dict:
    """Run Gate 0's twin in-dyno and bank the artifact. Never raises."""
    budget = clamp_timeout_ms(timeout_ms)

    # BEFORE the fold, so the trough's own bound is captured at the instant the
    # fold's population is read rather than up to 22 minutes later.
    staged_before, gen_before, staged_error = await read_served_disclosure()

    rows, fold_duration_s, fold_error = await _fold(timeout_ms=budget)
    payload, payload_error = await _read_published_payload()

    # AFTER, to find out whether the subject rotated underneath the fold.
    staged_after, gen_after, staged_error_after = await read_served_disclosure()

    staged = staged_before
    rotation_note: Optional[str] = None
    if staged_error and not staged_error_after:
        # The pre-fold read failed and the post-fold one worked. Use what we
        # have and clear the error: a bound that could be read is better than a
        # refusal, and the artifact still names which side it came from.
        staged, staged_error = staged_after, None
        rotation_note = "pre-fold disclosure unreadable; used the post-fold read"
    elif not staged_error and staged_error_after:
        rotation_note = "post-fold disclosure unreadable; kept the pre-fold read"
    elif gen_before is not None and gen_after is not None and gen_before != gen_after:
        staged, rotation_note = wider_disclosure(staged_before, staged_after)

    artifact = build_artifact(
        rows=rows,
        fold_duration_s=fold_duration_s,
        fold_error=fold_error,
        payload=payload,
        payload_error=payload_error,
        timeout_ms=budget,
        staged=staged,
        staged_error=staged_error,
        rotation_note=rotation_note,
        ledger_generation_before=gen_before,
        ledger_generation_after=gen_after,
    )

    # Bank it. A failed durable write is reported on the artifact rather than
    # thrown: the measurement happened, and losing the record of it is a
    # separate (and lesser) failure than not measuring.
    try:
        from app.services.durable_snapshots import publish_snapshot_standalone
        from app.utils.durable_state import DurableEnvelope

        envelope = DurableEnvelope.build(
            identity=TWIN_IDENTITY,
            schema_version=TWIN_SCHEMA,
            payload=artifact,
            complete=bool(artifact.get("measured")),
            source="calibration_published_twin",
        )
        stage = await publish_snapshot_standalone(envelope)
        artifact["durable"] = stage.get("status")
        artifact["durable_generation"] = envelope.generation
    except Exception as exc:  # noqa: BLE001
        logger.warning("calibration twin: durable write failed", exc_info=True)
        artifact["durable"] = "error"
        artifact["durable_error"] = f"{type(exc).__name__}: {exc}"

    return artifact
