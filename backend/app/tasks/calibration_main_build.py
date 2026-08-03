"""Runtime half of the Queue 300M main-build phase ledger + resume (#1479/#1513).

``app.utils.calibration_phase_ledger`` holds the RULES (pure, corpus-graded).
This module is the only thing that touches a substrate, and it picks the same
one Queue 298/300 established: PostgreSQL's ``durable_state_snapshots``.

Not Redis, deliberately. The instance is 50MB ``allkeys-lru`` running near
maxmemory; a phase ledger or a checkpoint there is not "persisted with a TTL",
it is a key waiting to be evicted — and an evicted checkpoint silently restarts
the build from zero while every metric still says the task succeeded. That is
the precise failure Queue 298 removed from the sentinels.

Three things live here:

* :class:`PhaseRunner` — the object the build carries through its phases. It
  times them, applies the per-phase statement timeout, hands back a prior
  beat's committed output when one exists, and captures this run's output for
  the next beat. With no runner (the route's cold-cache path) the build behaves
  exactly as it did before: no timing, no resume, no extra I/O.
* Lossless row (de)serialization. A carried phase output must reconstruct to
  something the downstream Python treats identically — including ``Decimal``,
  which ``canonical_json``'s ``default=str`` would otherwise flatten to a
  string and quietly change the arithmetic.
* Bounded persistence. A phase output that will not fit the checkpoint is NOT
  stored, and the phase is simply recomputed next beat. Silently truncating it
  would be far worse: a resumed run would publish a payload missing rows it
  believes it has.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import socket
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Optional

from sqlalchemy import text

from app.utils.calibration_phase_ledger import (
    CANCELLED,
    DONE_STATUSES,
    FAILED,
    FRESH,
    HARD_LIMIT_MS,
    INVALIDATE,
    MAIN_BUILD_TASK,
    MAIN_CHECKPOINT_SCHEMA,
    PHASE_LEDGER_SCHEMA,
    PHASE_OUTPUT_KEYS,
    RESUMABLE_PHASES,
    RESUMED,
    TERMINAL_COMPLETE,
    TERMINAL_PARTIAL,
    TIMEOUT,
    MainBuildCheckpoint,
    PhaseLedger,
    PhasePlan,
    decode_main_checkpoint,
    derive_plan,
    merge_history,
    new_main_checkpoint,
)

logger = logging.getLogger(__name__)

LEDGER_IDENTITY = "calibration:main:phase_ledger"
CHECKPOINT_IDENTITY = "calibration:main:checkpoint"
#: Queue 300D Item 0. Kept apart from ``CHECKPOINT_IDENTITY`` on purpose: the
#: phase checkpoint carries WHOLE finished phases, this one carries progress
#: INSIDE the futures phase. Sharing a row would mean a partial futures phase
#: could not be recorded without also rewriting (and risking) the committed
#: sports/diagnostics output sitting next to it.
STAGED_FUTURES_IDENTITY = "calibration:main:staged_futures"

#: Queue 300D Item 0 — the staged futures switch.
#:
#: True: the scheduled build reads the futures population one chunk of whole
#: virtual questions at a time, committing each chunk before advancing its
#: cursor, so an interrupted beat banks what it proved.
#:
#: False: one statement, as before.
#:
#: SWITCHED ON (Queue 300E, 2026-08-03) — the watched flip Queue 300D left
#: deliberately undone. 300D shipped the machinery off because the staged
#: statement had never executed against PostgreSQL and that queue's gates forbade
#: triggering a build to find out. What changed is not the code — it is that OFF
#: stopped being free.
#:
#: The evidence for the flip, measured before it: the last monolith beat
#: (generation 1785773700264, release v3683, ledger 2026-08-03T16:37:32Z) ended
#: terminal ``failed`` with the futures phase ``timeout`` at 1,352,046 ms, the
#: tenth consecutive floor within 8s of ~22.5 minutes, ``banked: {}`` and
#: ``completed_required: []``. The public curve was serving a 37.8-hour-old
#: last-good (``cache.status=stale``, ``reason=main_key_absent``). OFF is a
#: proven no-op, and a proven no-op is exactly what the build could no longer
#: afford: it banks nothing, hourly, forever.
#:
#: ROLLBACK is this constant back to ``False`` and one deploy. That path stays
#: exact: the monolith text is byte-identical to the pre-300D statement (pinned
#: by ``test_calibration_staged_futures_sql_300d.TestMonolithIsUnmoved``), so
#: rolling back costs the build nothing beyond returning it to the failure it
#: started from.
#:
#: WATCHING IT: the ledger shows ``read:futures_generation`` and
#: ``read:futures_unit`` stage timings and a ``staged:cursor_*`` action, and a
#: partial beat reports terminal ``cancelled`` with units banked (by design —
#: see :class:`StagedFuturesIncomplete`), not ``failed``. A partial first beat is
#: a PASS, not a regression: it means the build banked work for the first time.
#:
#: The one residual this flip does NOT fix, written down so it is not
#: rediscovered as a surprise: stage 1 (the generation read) is itself a single
#: unchunked statement — the pre-``virtual_market`` prefix of the same pipeline,
#: and it carries 3 of the statement's 7 correlated scans of the 179M-row
#: ``futures_odds_snapshots``. If that prefix alone exceeds the window, the beat
#: times out having banked nothing, which is no worse than today but is also no
#: better. Only the post-``virtual_market`` half is resumable here.
#:
#: This ONLY ever applies to a run that owns a :class:`PhaseRunner` — i.e. the
#: scheduled build. The route's in-request cold-cache serve keeps the single
#: statement unconditionally: it has no checkpoint to resume from, no second
#: beat to finish the job, and a request session whose transaction must not be
#: committed underneath the caller. That is a class attribute on
#: :class:`NullPhaseRunner`, not a read of this constant, so it holds whatever
#: an operator sets here.
STAGED_FUTURES_ENABLED = True

#: Markets per chunk. A budget, not a row count: the unit is a whole virtual
#: question, so a chunk overshoots rather than split one (see
#: ``plan_units``). Sized so a chunk is small enough that losing one to a
#: timeout costs little, and large enough that per-chunk planning overhead
#: stays a rounding error against the population read it replaces.
STAGED_FUTURES_CHUNK_MARKETS = 2_500

#: A ledger or checkpoint older than this is a fossil, not state in progress.
STATE_MAX_AGE_S = 14 * 86400

#: How long this run's claim on the checkpoint is good for. Comfortably past
#: the Celery hard limit so a run that is SIGKILLed still holds the lease until
#: after it could possibly still be alive, and no longer.
LEASE_S = (HARD_LIMIT_MS / 1000.0) + 300.0

#: Ceiling on ONE phase's serialized output inside the checkpoint.
PHASE_OUTPUT_MAX_BYTES = 4_000_000
#: Ceiling on the whole checkpoint payload. Largest-first drop when exceeded.
CHECKPOINT_MAX_BYTES = 8_000_000

#: Postgres cancels a statement with this message; it is the phase's own inner
#: backstop firing, not a bug, and it must be recorded as ``timeout`` rather
#: than lumped in with a genuine failure.
_STATEMENT_TIMEOUT_MARKERS = (
    "canceling statement due to statement timeout",
    "querycanceled",
)


class StagedFuturesIncomplete(RuntimeError):
    """The staged futures generation made progress but is not finished.

    Deliberately its own type rather than a bare ``RuntimeError``: this is the
    ONE way the build stops that is neither a bug nor a resource problem. Units
    committed, the cursor advanced, the next beat will resume — the only correct
    response is to publish nothing and say so. :meth:`PhaseRunner.classify_failure`
    maps it to ``cancelled`` (ran out of window without finishing) rather than
    ``failed``, so a working build does not page anybody RED for doing exactly
    what it was designed to do.
    """


def run_owner() -> str:
    """Who is building right now. Stable within a run, distinct across workers."""
    return f"{socket.gethostname()}:{os.getpid()}"


async def tag_scheduled_session(db, *, task: str) -> dict:
    """Session identity for a scheduled calibration task with no PhaseRunner.

    The main build gets its tag through :meth:`PhaseRunner.tag_session`, which
    can name the exact run generation it is checkpointing under. The horizon,
    fair-fight and coverage sweeps have no ledger, so they derive a generation
    from their own start instant — enough to tell two beats apart and to place a
    backend against the deploy it started under, which is the whole ask.

    Their queries are individually bounded and none of them is the ~22-minute
    population CTE, so they are not the likely orphan. Tagging them anyway is
    what makes the ABSENCE of a tag meaningful: once every scheduled calibration
    session is named, an untagged calibration-shaped backend is by itself
    evidence that it predates this change.
    """
    from app.tasks.base import tag_task_session
    from app.utils.durable_state import generation_for

    return await tag_task_session(
        db,
        task=task,
        run_generation=generation_for(datetime.now(timezone.utc)),
        owner=run_owner(),
    )


# =============================================================================
# Lossless (de)serialization of read output
# =============================================================================


def _encode(value: Any) -> Any:
    """JSON-safe, round-trippable. Types that would lose precision are tagged.

    ``Decimal`` is the one that matters: Postgres returns ``AVG(prob)`` as a
    Decimal, and both a float cast and ``canonical_json``'s ``default=str``
    would change what the downstream bucket arithmetic sees. Tagging keeps a
    carried phase byte-equivalent to a freshly-read one.
    """
    if isinstance(value, Decimal):
        return {"__t__": "dec", "v": str(value)}
    if isinstance(value, datetime):
        return {"__t__": "dt", "v": value.isoformat()}
    if isinstance(value, date):
        return {"__t__": "d", "v": value.isoformat()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_encode(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _encode(v) for k, v in value.items()}
    return {"__t__": "repr", "v": str(value)}


def _decode(value: Any) -> Any:
    if isinstance(value, dict):
        # Only a dict that is EXACTLY a tag envelope is un-tagged; a payload
        # dict that merely happens to contain a "__t__" key stays a dict.
        if set(value) == {"__t__", "v"}:
            tag = value["__t__"]
            if tag == "dec":
                return Decimal(value["v"])
            if tag == "dt":
                return datetime.fromisoformat(value["v"])
            if tag == "d":
                return date.fromisoformat(value["v"])
            if tag == "repr":
                return value["v"]
        return {k: _decode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decode(v) for v in value]
    return value


def encode_rows(rows: Any) -> list[dict[str, Any]]:
    """SQLAlchemy ``Row``s (or namespaces) to a list of plain encoded dicts."""
    out: list[dict[str, Any]] = []
    for row in rows or []:
        mapping = getattr(row, "_mapping", None)
        if mapping is not None:
            source = dict(mapping)
        elif isinstance(row, dict):
            source = dict(row)
        else:
            source = dict(vars(row))
        out.append({str(k): _encode(v) for k, v in source.items()})
    return out


def decode_rows(raw: Any) -> list[SimpleNamespace]:
    """Back to attribute-access rows the downstream post-processing accepts."""
    return [SimpleNamespace(**{k: _decode(v) for k, v in item.items()}) for item in (raw or [])]


def _encode_value(kind: str, value: Any) -> Any:
    if kind == "rows":
        return encode_rows(value)
    if kind == "row":
        encoded = encode_rows([value])
        return encoded[0] if encoded else None
    return _encode(value)


def _decode_value(kind: str, value: Any) -> Any:
    if kind == "rows":
        return decode_rows(value)
    if kind == "row":
        decoded = decode_rows([value] if isinstance(value, dict) else [])
        return decoded[0] if decoded else None
    return _decode(value)


# =============================================================================
# The runner
# =============================================================================


class PhaseRunner:
    """Times, bounds, resumes and records one main-build run's phases.

    Every method is safe to call on a run with no prior state; the "no
    checkpoint yet" path is the normal first run, not an error branch.
    """

    def __init__(
        self,
        *,
        plan: PhasePlan,
        checkpoint: MainBuildCheckpoint,
        checkpoint_action: str,
        population_version: str,
        owner: str,
        generation: int,
        fingerprint: str,
    ) -> None:
        self.ledger = PhaseLedger(
            plan=plan,
            population_version=population_version,
            owner=owner,
            generation=generation,
            input_fingerprint=fingerprint,
        )
        self.checkpoint = checkpoint
        self.checkpoint_action = checkpoint_action
        self.owner = owner
        self.generation = generation
        self.fingerprint = fingerprint
        self.population_version = population_version
        self._started = time.monotonic()
        #: phase -> {key: (kind, live value)} captured THIS run.
        self._captured: dict[str, dict[str, tuple[str, Any]]] = {}
        #: phase -> decoded carried output, materialized lazily once.
        self._carried: dict[str, dict[str, Any]] = {}
        self.carried_phases: list[str] = []
        self.checkpoint_writes: dict[str, str] = {}
        #: Queue 300B Item 1. The SERVER's view of this run — the tag it wrote
        #: into ``application_name`` and the backend PID that wrote it. Recorded
        #: in the ledger so a ``pg_stat_activity`` row seen weeks later can be
        #: joined back to a named run instead of inferred from age.
        self.session_identity: dict[str, Any] = {
            "application_name": None,
            "backend_pid": None,
            "applied": False,
        }
        #: Filled in progressively by the build so the orchestrator's ``finally``
        #: can tell a gate refusal from a durable failure from a clean publish
        #: WITHOUT re-deriving it from an exception message.
        self.outcome: dict[str, Any] = {
            "gate": "not_evaluated",
            "durable": "not_attempted",
            "volatile": "not_attempted",
            "published": False,
            "artifact_generation": None,
        }

    # -- staging --------------------------------------------------------------

    @property
    def staged_futures(self) -> bool:
        """Whether this run may read the futures population in chunks.

        A property rather than a constructor argument so there is exactly one
        answer to "is this the scheduled build?" — owning a real runner IS the
        condition, and :data:`STAGED_FUTURES_ENABLED` is the operator's switch
        on top of it.
        """
        return STAGED_FUTURES_ENABLED

    # -- clock ----------------------------------------------------------------

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self._started) * 1000)

    def deadline_exceeded(self) -> bool:
        return self.ledger.remaining_ms(elapsed_ms=self.elapsed_ms()) <= 0

    # -- phase lifecycle ------------------------------------------------------

    def begin(self, phase: str) -> None:
        self.ledger.begin(phase, now_ms=self.elapsed_ms())

    def complete(self, phase: str, *, committed: bool = True) -> int:
        return self.ledger.complete(phase, now_ms=self.elapsed_ms(), committed=committed)

    def carry(self, phase: str) -> None:
        self.ledger.carry(phase, source_generation=self.checkpoint.generation)
        self.carried_phases.append(phase)

    def is_carried(self, phase: str) -> bool:
        """True when a prior beat already banked this phase's whole output."""
        return self.ledger.records[phase].status == RESUMED

    @contextlib.contextmanager
    def stage(self, name: str):
        """Time one named sub-phase stretch, whatever happens inside it.

        Recorded on the way out even when the body raises, because the stage
        that blew up is the one worth knowing the cost of. Stages carry no
        budget and no resume semantics — they exist purely so no part of the
        build is unaccounted for.
        """
        started = time.monotonic()
        try:
            yield
        finally:
            self.ledger.record_stage(name, int((time.monotonic() - started) * 1000))

    def classify_failure(self, exc: BaseException) -> str:
        """timeout | cancelled | failed — the three ways a phase can end badly."""
        import asyncio

        if isinstance(exc, (asyncio.CancelledError, StagedFuturesIncomplete)):
            return CANCELLED
        text_form = f"{exc.__class__.__name__} {exc}".lower()
        if any(marker in text_form for marker in _STATEMENT_TIMEOUT_MARKERS):
            return TIMEOUT
        return FAILED

    def abort(self, exc: BaseException) -> str:
        """Close whatever phase was in flight, classified. Returns the status."""
        status = self.classify_failure(exc)
        self.ledger.close_open_phase(
            now_ms=self.elapsed_ms(), status=status, detail=str(exc)[:200]
        )
        return status

    # -- resume / capture -----------------------------------------------------

    def reuse(self, phase: str, key: str) -> Any:
        """A prior beat's committed value for ``phase.key``, or ``None``.

        ``None`` always means "not carried, do the read". No phase output here
        is legitimately ``None`` — every one is a row list, a count, or a dict.
        """
        if phase not in self.checkpoint.completed_phases:
            return None
        if phase not in self._carried:
            stored = self.checkpoint.output(phase) or {}
            values = stored.get("values")
            if not isinstance(values, dict):
                return None
            self._carried[phase] = {
                name: _decode_value(entry.get("kind", "value"), entry.get("value"))
                for name, entry in values.items()
                if isinstance(entry, dict)
            }
        return self._carried[phase].get(key)

    def record(self, phase: str, key: str, value: Any, *, kind: str = "value") -> None:
        """Capture a freshly-read value so the next beat can carry it."""
        self._captured.setdefault(phase, {})[key] = (kind, value)

    async def tag_session(self, db) -> dict:
        """Announce this run's identity on the live backend (Queue 300B Item 1).

        Both this and :meth:`apply_statement_timeout` are ``SET LOCAL``-scoped,
        which is what makes them safe — and also what makes them perishable.
        :meth:`commit` ends the transaction between phases, so both have to be
        re-armed on the far side of every commit or the next phase runs bare.
        """
        from app.tasks.base import tag_task_session

        identity = await tag_task_session(
            db,
            task=MAIN_BUILD_TASK,
            run_generation=self.generation,
            owner=self.owner,
        )
        # The PID is captured once and kept: it is the run's server-side identity
        # for the whole run, and a later re-tag on the same session returns the
        # same backend. Keeping the first non-null value means a transient
        # failure to re-tag cannot erase what we already proved.
        if identity.get("backend_pid") is not None or not self.session_identity.get(
            "applied"
        ):
            self.session_identity = identity
        return identity

    async def apply_statement_timeout(self, db, phase: str) -> int:
        """Set this phase's inner DB backstop on the live session.

        Applied per phase rather than once per session so a phase that resumed
        (and therefore did no reading) does not silently hand its unused time to
        the next one, and so the bound always reflects the time actually left
        before the absolute deadline.

        The session tag rides along here rather than in its own call because the
        two have identical lifetimes — transaction-local, wiped by the inter-phase
        commit — and separating them is how one of them ends up silently missing
        from the phase that eventually wedges.
        """
        timeout_ms = self.ledger.statement_timeout_for(phase, elapsed_ms=self.elapsed_ms())
        await db.execute(text(f"SET LOCAL statement_timeout = {int(timeout_ms)}"))
        await self.tag_session(db)
        return timeout_ms

    async def commit(self, db) -> None:
        """End the phase's read transaction so its output counts as committed.

        Two things follow from this that the single-transaction build could not
        have. First, ``checkpoint_advanced`` becomes truthful: the cursor moves
        only after the work behind it is committed. Second — and this one is
        free — the build stops holding ONE MVCC snapshot open across all eleven
        reads for the better part of half an hour, which is exactly the xmin
        pin that let dead tuples accumulate faster than autovacuum could
        reclaim them (#1479's bloat spiral).
        """
        await db.commit()

    # -- persistence ----------------------------------------------------------

    def _serialize_phase(self, phase: str) -> tuple[Optional[dict[str, Any]], int]:
        captured = self._captured.get(phase)
        if not captured:
            return None, 0
        expected = PHASE_OUTPUT_KEYS.get(phase, frozenset())
        if set(captured) != set(expected):
            # Half a phase is not a phase. Storing it would let a later beat
            # mark the phase done and publish a payload missing the rest.
            logger.warning(
                "calibration phase ledger: %s captured %s but owes %s — not "
                "checkpointed", phase, sorted(captured), sorted(expected),
            )
            return None, 0
        values = {
            key: {"kind": kind, "value": _encode_value(kind, value)}
            for key, (kind, value) in captured.items()
        }
        body = {"stored": True, "values": values}
        size = len(json.dumps(body, separators=(",", ":"), default=str))
        return body, size

    def build_checkpoint(self) -> tuple[MainBuildCheckpoint, dict[str, str]]:
        """Fold this run's committed phase outputs into a checkpoint.

        Carried phases stay carried (their stored form is reused verbatim —
        re-encoding a decoded row list would be pure cost for no change).
        Oversize output is dropped rather than truncated, and the drop is
        recorded so the ledger can say which phases the next beat must redo.
        """
        checkpoint = new_main_checkpoint(
            version=self.population_version,
            fingerprint=self.fingerprint,
            owner=self.owner,
            generation=self.generation,
        )
        lease = time.time() + LEASE_S
        outcomes: dict[str, str] = {}
        sized: list[tuple[str, dict[str, Any], int]] = []

        for phase in RESUMABLE_PHASES:
            record = self.ledger.records.get(phase)
            if record is None or record.status not in DONE_STATUSES:
                continue
            if phase in self.carried_phases and phase not in self._captured:
                stored = self.checkpoint.output(phase)
                if stored:
                    size = len(json.dumps(stored, separators=(",", ":"), default=str))
                    sized.append((phase, stored, size))
                continue
            body, size = self._serialize_phase(phase)
            if body is None:
                continue
            if size > PHASE_OUTPUT_MAX_BYTES:
                outcomes[phase] = "oversize"
                self.ledger.note_output(phase, size_bytes=size, stored=False)
                logger.warning(
                    "calibration phase ledger: %s output is %d bytes (> %d) — not "
                    "checkpointed; the next beat will recompute it rather than "
                    "resume a truncated read",
                    phase, size, PHASE_OUTPUT_MAX_BYTES,
                )
                continue
            sized.append((phase, body, size))

        # Largest-first drop until the whole checkpoint fits.
        total = sum(size for _, _, size in sized)
        while total > CHECKPOINT_MAX_BYTES and sized:
            sized.sort(key=lambda item: item[2])
            phase, _, size = sized.pop()
            total -= size
            outcomes[phase] = "checkpoint_full"
            self.ledger.note_output(phase, size_bytes=size, stored=False)
            logger.warning(
                "calibration phase ledger: dropping %s (%d bytes) to keep the "
                "checkpoint under %d bytes", phase, size, CHECKPOINT_MAX_BYTES,
            )

        for phase, body, size in sized:
            checkpoint = checkpoint.with_phase(
                phase, body, owner=self.owner, lease_expires_at=lease
            )
            outcomes[phase] = "stored"
            self.ledger.note_output(phase, size_bytes=size, stored=True)
        return checkpoint, outcomes


class NullPhaseRunner:
    """The no-runner path, spelled out so the build body has no ``if runner``.

    This is what the route's in-request cold-cache fallback gets: no timing, no
    checkpoint, no per-phase statement timeout, and — critically — no
    ``commit()``. A request session must not have its transaction ended
    underneath the caller, and a one-off serve has nothing to resume anyway.
    The build's behaviour on this path is exactly what it was before Queue 300M.
    """

    checkpoint_action = FRESH
    carried_phases: tuple[str, ...] = ()
    #: Never. A one-off serve has nothing to resume into and must not have its
    #: request transaction committed out from under the caller.
    staged_futures = False

    def __init__(self) -> None:
        self.outcome: dict[str, Any] = {
            "gate": "not_evaluated",
            "durable": "not_attempted",
            "volatile": "not_attempted",
            "published": False,
            "artifact_generation": None,
        }
        self.session_identity: dict[str, Any] = {
            "application_name": None,
            "backend_pid": None,
            "applied": False,
        }

    def begin(self, phase: str) -> None:  # noqa: D102 - no-op by design
        return None

    def complete(self, phase: str, *, committed: bool = True) -> int:  # noqa: D102
        return 0

    def is_carried(self, phase: str) -> bool:  # noqa: D102
        return False

    def reuse(self, phase: str, key: str) -> Any:  # noqa: D102
        return None

    def record(self, phase: str, key: str, value: Any, *, kind: str = "value") -> None:  # noqa: D102
        return None

    async def tag_session(self, db) -> dict:  # noqa: D102
        return dict(self.session_identity)

    async def apply_statement_timeout(self, db, phase: str) -> int:  # noqa: D102
        return 0

    async def commit(self, db) -> None:  # noqa: D102
        return None

    @contextlib.contextmanager
    def stage(self, name: str):  # noqa: D102
        yield


NULL_RUNNER = NullPhaseRunner()


# =============================================================================
# Durable load / save
# =============================================================================


async def load_phase_history() -> tuple[dict[str, list[int]], dict[str, list[int]]]:
    """Prior runs' per-phase durations and floors, or ``({}, {})``.

    ``{}`` is the honest answer to every read problem: with no history the plan
    is provisional and nothing pretends to a measured budget it does not have.
    The two are read together off the one durable row — floors are what the
    beats that never completed a phase have to say, and they are worth exactly
    one extra key rather than a second read.
    """
    from app.services.durable_snapshots import read_snapshot_standalone

    read = await read_snapshot_standalone(
        LEDGER_IDENTITY, expected_version=PHASE_LEDGER_SCHEMA, max_age_s=STATE_MAX_AGE_S
    )
    if not read.ok or read.envelope is None or not isinstance(read.envelope.payload, dict):
        return {}, {}
    history = read.envelope.payload.get("history")
    floors = read.envelope.payload.get("floors")
    return (
        merge_history(history, {}) if isinstance(history, dict) else {},
        merge_history(floors, {}) if isinstance(floors, dict) else {},
    )


async def load_main_checkpoint(
    *,
    population_version: str,
    fingerprint: str,
    owner: str,
    generation: int,
    max_age_s: float = STATE_MAX_AGE_S,
) -> tuple[MainBuildCheckpoint, str]:
    """Read + classify the durable checkpoint (fresh / resume / invalidate / refuse)."""
    from app.services.durable_snapshots import read_snapshot_standalone

    read = await read_snapshot_standalone(
        CHECKPOINT_IDENTITY,
        expected_version=MAIN_CHECKPOINT_SCHEMA,
        max_age_s=max_age_s,
    )
    if not read.ok or read.envelope is None:
        if read.status != "missing":
            logger.info(
                "calibration main checkpoint not resumable (%s) — starting fresh",
                read.status,
            )
        blank = new_main_checkpoint(
            version=population_version, fingerprint=fingerprint, owner=owner, generation=generation
        )
        return blank, (FRESH if read.status == "missing" else INVALIDATE)

    return decode_main_checkpoint(
        read.envelope.payload,
        expected_version=population_version,
        expected_fingerprint=fingerprint,
        owner=owner,
        generation=generation,
        now=time.time(),
    )


async def save_main_checkpoint(checkpoint: MainBuildCheckpoint, *, terminal: str) -> bool:
    """Persist the checkpoint. Returns whether the durable generation committed.

    The caller must treat a phase as durably recorded only when this returns
    ``True`` — that boolean is what feeds ``checkpoint_advanced`` in the
    contract row, and therefore what stops a resumed run skipping work it never
    actually banked.
    """
    from app.services.durable_snapshots import publish_snapshot_standalone
    from app.utils.durable_state import DurableEnvelope

    payload = checkpoint.as_payload()
    payload["terminal"] = terminal
    result = await publish_snapshot_standalone(
        DurableEnvelope.build(
            identity=CHECKPOINT_IDENTITY,
            schema_version=MAIN_CHECKPOINT_SCHEMA,
            payload=payload,
            # The RECORD is whole; the build's own state is `terminal` above.
            complete=True,
            source=MAIN_BUILD_TASK,
        )
    )
    ok = result.get("status") in ("ok", "superseded")
    if not ok:
        logger.warning("calibration main checkpoint persist failed: %s", result)
    return ok


async def clear_main_checkpoint(*, population_version: str, fingerprint: str, owner: str) -> bool:
    """Reset after a complete publish.

    A write of an emptied checkpoint rather than a DELETE: the durable store's
    atomicity story is a generation-guarded upsert with no delete path, so the
    next build reads an explicit "nothing carried" under the current version
    instead of an absence it would have to interpret.
    """
    from app.utils.durable_state import generation_for

    blank = new_main_checkpoint(
        version=population_version,
        fingerprint=fingerprint,
        owner=owner,
        generation=generation_for(datetime.now(timezone.utc)),
    )
    return await save_main_checkpoint(blank, terminal="complete")


# =============================================================================
# Staged futures cursor (Queue 300D Item 0)
# =============================================================================


def staged_lease() -> float:
    """When this run's claim on the staged cursor expires.

    Same geometry as :data:`LEASE_S` and for the same reason: comfortably past
    the Celery hard limit, so a SIGKILLed run still holds its claim until after
    it could possibly still be alive, and not one second longer.
    """
    return time.time() + LEASE_S


async def load_staged_cursor(
    *,
    population_version: str,
    input_fingerprint: str,
    generation_fingerprint: str,
    owner: str,
    generation: int,
    max_age_s: float = STATE_MAX_AGE_S,
):
    """Read + classify the staged futures cursor (fresh/resume/invalidate/refuse)."""
    from app.services.durable_snapshots import read_snapshot_standalone
    from app.utils.calibration_staged_futures import (
        STAGED_FUTURES_SCHEMA,
        decode_staged_cursor,
        new_staged_cursor,
    )

    blank = new_staged_cursor(
        population_version=population_version,
        input_fingerprint=input_fingerprint,
        generation_fingerprint=generation_fingerprint,
        owner=owner,
        generation=generation,
    )
    try:
        read = await read_snapshot_standalone(
            STAGED_FUTURES_IDENTITY,
            expected_version=STAGED_FUTURES_SCHEMA,
            max_age_s=max_age_s,
        )
    except Exception as exc:  # noqa: BLE001 — an unreadable cursor is a fresh one
        logger.warning("calibration staged cursor read failed: %s", exc)
        return blank, INVALIDATE
    if not read.ok or read.envelope is None:
        return blank, (FRESH if read.status == "missing" else INVALIDATE)

    return decode_staged_cursor(
        read.envelope.payload,
        expected_population_version=population_version,
        expected_input_fingerprint=input_fingerprint,
        expected_generation_fingerprint=generation_fingerprint,
        owner=owner,
        generation=generation,
        now=time.time(),
    )


async def save_staged_cursor(cursor, *, terminal: str) -> bool:
    """Persist the staged cursor. ``True`` only when the write is durable.

    The caller must treat a unit as banked ONLY on ``True``. Everything the
    resume story rests on — that a unit recorded as done really did commit — is
    this boolean being honest.
    """
    from app.services.durable_snapshots import publish_snapshot_standalone
    from app.utils.calibration_staged_futures import STAGED_FUTURES_SCHEMA
    from app.utils.durable_state import DurableEnvelope

    payload = cursor.as_payload()
    payload["terminal"] = terminal
    try:
        result = await publish_snapshot_standalone(
            DurableEnvelope.build(
                identity=STAGED_FUTURES_IDENTITY,
                schema_version=STAGED_FUTURES_SCHEMA,
                payload=payload,
                complete=True,
                source=MAIN_BUILD_TASK,
            )
        )
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed
        logger.warning("calibration staged cursor persist failed: %s", exc)
        return False
    ok = result.get("status") in ("ok", "superseded")
    if not ok:
        logger.warning("calibration staged cursor persist rejected: %s", result)
    return ok


async def save_phase_ledger(runner: PhaseRunner, extra: Optional[dict[str, Any]] = None) -> str:
    """Persist the phase ledger + rolling history. Returns ``ok`` or ``error``.

    This is the measurement rail Item 0 exists to build, so it is written on
    EVERY terminal — a run that timed out at phase 2 is exactly the run whose
    timings the next plan most needs. A failure here is reported, never
    swallowed: :func:`health_for` turns it into UNKNOWN, never GREEN.
    """
    from app.services.durable_snapshots import publish_snapshot_standalone
    from app.utils.durable_state import DurableEnvelope

    payload = runner.ledger.as_payload()
    if extra:
        payload.update(extra)
    try:
        prior_history, prior_floors = await load_phase_history()
    except Exception as exc:  # noqa: BLE001 — a lost history is not a lost ledger
        logger.warning("calibration phase ledger: history read failed: %s", exc)
        prior_history, prior_floors = {}, {}
    payload["history"] = merge_history(prior_history, runner.ledger.observations())
    payload["floors"] = merge_history(prior_floors, runner.ledger.floors())

    result = await publish_snapshot_standalone(
        DurableEnvelope.build(
            identity=LEDGER_IDENTITY,
            schema_version=PHASE_LEDGER_SCHEMA,
            payload=payload,
            complete=True,
            source=MAIN_BUILD_TASK,
        )
    )
    status = "ok" if result.get("status") in ("ok", "superseded") else "error"
    if status != "ok":
        logger.error(
            "calibration phase ledger: durable write FAILED (%s) — this run's "
            "progress is UNKNOWN, not green", result.get("error") or result.get("status"),
        )
    runner.ledger.ledger_write = status
    return status


async def build_runner(
    *, population_version: str, fingerprint: str, carry_max_age_s: float = STATE_MAX_AGE_S
) -> tuple[PhaseRunner, str]:
    """Assemble the runner for one build: history -> plan -> checkpoint -> runner."""
    from app.utils.durable_state import generation_for

    owner = run_owner()
    generation = generation_for(datetime.now(timezone.utc))
    try:
        history, floors = await load_phase_history()
    except Exception as exc:  # noqa: BLE001 — no history just means provisional
        logger.warning("calibration phase ledger: history read failed: %s", exc)
        history, floors = {}, {}
    plan = derive_plan(history, floors=floors)
    if plan.infeasible_phases:
        # Loud, because no amount of checkpointing or resuming fixes it: the
        # phase as cut is bigger than the whole beat.
        logger.error(
            "calibration phase plan is INFEASIBLE — required phase(s) %s have a "
            "measured floor at or beyond the %dms window; the build cannot "
            "complete as currently cut",
            ", ".join(plan.infeasible_phases),
            plan.available_ms,
        )

    try:
        checkpoint, action = await load_main_checkpoint(
            population_version=population_version,
            fingerprint=fingerprint,
            owner=owner,
            generation=generation,
            max_age_s=carry_max_age_s,
        )
    except Exception as exc:  # noqa: BLE001 — an unreadable checkpoint is a fresh one
        logger.warning("calibration main checkpoint read failed: %s", exc)
        checkpoint, action = (
            new_main_checkpoint(
                version=population_version,
                fingerprint=fingerprint,
                owner=owner,
                generation=generation,
            ),
            INVALIDATE,
        )

    runner = PhaseRunner(
        plan=plan,
        checkpoint=checkpoint,
        checkpoint_action=action,
        population_version=population_version,
        owner=owner,
        generation=generation,
        fingerprint=fingerprint,
    )
    for phase in checkpoint.completed_phases:
        runner.carry(phase)
    return runner, action


def checkpoint_terminal(runner: PhaseRunner) -> str:
    return TERMINAL_COMPLETE if runner.ledger.all_required_done else TERMINAL_PARTIAL
