"""CAL-P084 (#2007, #1544) — the beat gauge sampler, as an instrument that EXISTS ON PURPOSE.

Why this file exists: a descent that survived on luck
------------------------------------------------------
On 2026-08-21 at 12:30:24 UTC the agreement bound finally came down —
``100.0000pp -> 0.5000pp`` at generation ``1787315424367`` — the single event
#2007 had been waiting weeks for. **It was captured by a background process a
PREVIOUS window had left running.** CAL-P082 started
``scripts/sample_calibration_beats.py`` in a terminal; CAL-P083 inherited it
still alive and could therefore quote the descent. Had that process died with
its window, the evidence would not exist, because of one fact about the store:

    ``durable_state_snapshots`` keeps **ONE ROW PER IDENTITY**.

``calibration:main:phase_ledger`` is overwritten every beat. The beat that
promotes the bank is visible for about an hour and is then gone forever. So the
program's central number is observable only by something that is *looking at the
time*, and until now the only thing looking was a human's leftover shell.

CAL-P083 named that and did not fix it. Fable's CAL-P084 item 3 is the fix:
*"finish it into a permanent instrument this cycle so the NEXT promotion's
evidence doesn't depend on a prior window's leftover process. Descent-survived-
on-luck is a named failure; the fix is a sampler that exists on purpose."*

What "fixed gauge" means, and why the gauge list is DERIVED and not typed
-------------------------------------------------------------------------
This module captures a **fixed set of gauges every beat**, so that a later
reader can replay ``build_disclosure`` + ``tolerance_pp`` — the production pair,
imported, never re-derived — over a beat that no longer exists in the ledger.

The gauge list is the part that has already gone wrong twice, both times the
same way, both times found only by accident:

* **CAL-P083 #1** — ``staged:served_drift_uncheckable`` was missing. It is the
  term that can only push the bound **UP**, so a replay off the captured row
  reported ``units_drift_unknown: None`` where production published ``0``.
  Harmless while it is zero; CAL-P069's exact failure the moment it is not.
* **CAL-P083 #2** — ``staged:units_done`` was missing. It is a literal operand
  of the carry-withhold's predicate, so the captured row could show the guard's
  verdict but not its input: the guard could be *agreed with*, never *derived*.

Both were hand-maintained tuple entries that someone forgot. A third was sitting
there unnoticed when this file was written — see ``CONVERGENCE_REASON_PREFIX``
below — which is the proof that a hand-maintained list is the defect, not the
two omissions from it. So:

**:data:`REQUIRED_DISCLOSURE_GAUGES` is read out of
``app.utils.calibration_staged_disclosure`` at import time** by collecting its
``GAUGE_*`` module constants. Adding a gauge there adds it here, with no second
edit and no chance to forget. ``test_calibration_beat_gauge_sampler_p084.py``
pins that in both directions so the derivation cannot be quietly replaced by a
literal later.

Honest terminals, because a sampler's failure mode is silence
--------------------------------------------------------------
The dangerous outcome is not an error. It is a sampler that runs every hour,
returns cleanly, and captures nothing — the ``kalshi_trades`` shape (gotcha #53:
500 fetched, 500 empty, recorded SUCCESS every 6 h for ten weeks). Three
terminals, and the middle one is the one that exists for that:

``complete``
    the current ledger generation is in the history when the run ends —
    appended now, or already there from the previous sample. Both are the job
    done; ``appended`` says which, so "the sampler ran" and "a beat was
    captured" never collapse into one fact.
``partial``
    the ledger was read fine and is **STALE** — no beat has landed in longer
    than :data:`LEDGER_STALE_AFTER_S`. The sampler worked and the producer did
    not. It must not read GREEN, because a green sampler over a stopped producer
    is precisely the blindness this instrument was built to end.
``failed``
    the ledger could not be read, the gauges could not be extracted, or the
    history could not be written. A failed durable write is a FAILED run here
    (unlike the twin, where the measurement is the product and the record is
    secondary): for a sampler the record IS the product.

It is enrolled in ``ENFORCED_TASKS`` in the same change that gives it these
terminals — enrolment without a terminal is a documented no-op.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

#: A fixed instant, used only as the ``now`` handed to ``build_disclosure`` when
#: neither the beat's own stamp nor the served epoch is readable. In that state
#: the disclosure is always ``unmeasured`` and never reads ``now`` — this exists
#: so that if a future branch DOES read it, the value is a constant rather than
#: the wall clock. A deterministic wrong number is findable; a clock-dependent
#: one is what gotcha #44 is a list of.
_EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)

#: The durable artifact this sampler owns. Deliberately NOT the ledger's own
#: identity: this row must survive the ledger being overwritten, which is the
#: entire point.
HISTORY_IDENTITY = "calibration:beat_gauge_history"
HISTORY_SCHEMA = "calibration-beat-gauge-history/v1"

#: How many beat observations the ring keeps. 168 = 7 days at the hourly beat.
#:
#: Sized, not guessed. One observation is ~30 keys of scalars, ~1.3 KB of JSON,
#: so the row lands near 220 KB — the same order as the Gate 0 twin's 195 KB
#: artifact, which the store and the admin rail both already carry comfortably.
#: Seven days is chosen against the thing being measured: the bound's sawtooth
#: has a period of roughly 16 beats, so a week holds ~10 full teeth and cannot
#: be fooled by one atypical cycle.
HISTORY_LIMIT = 168

#: The beat's scheduled period (``precompute-calibration-main`` is
#: ``crontab(minute=15)``).
BEAT_PERIOD_S = 3600

#: A ledger row older than this means beats have STOPPED, not that this sample
#: had nothing to do. Two full periods plus the measured finish-time spread
#: (~18-22 min): one skipped beat is a real event but within normal turbulence,
#: two in a row is a producer that is down.
LEDGER_STALE_AFTER_S = 2 * BEAT_PERIOD_S + 1500

#: ``build_disclosure`` reads any key with this prefix — it is a PREFIX SCAN, not
#: a named key, and no fixed tuple can ever contain it.
#:
#: 🔴 THIS IS THE THIRD BLIND SPOT, AND IT WAS STILL OPEN WHEN THIS FILE WAS
#: WRITTEN. When the convergence reader cannot read the cursor it records
#: ``staged:convergence_reason:<status>``, and ``build_disclosure`` returns
#: ``unmeasured(<that key>)`` — the real reason the bank is unreadable. A
#: capture that dropped these keys would replay as the generic
#: ``units_banked_absent`` instead, so the one row that could explain a
#: disclosure outage would explain it wrongly, with the instrument's authority.
#: Exactly CAL-P028's collapse ("nothing banked" vs "the reader broke") arriving
#: through the sampler.
CONVERGENCE_REASON_PREFIX = "staged:convergence_reason:"

#: The SECOND prefix, added by CAL-P993 (calibration-028): why a ``cancelled``
#: beat was cancelled. Imported from the module that writes it rather than
#: retyped — the CAL-P083 blind spots were both transcription omissions, and a
#: string copied into a capture list is a string free to drift from the one the
#: producer emits.
#:
#: Captured for a reason the disclosure gauges are not: it is the only field in
#: which "a deploy killed the beat" and "the build has not converged" can be
#: told apart, and the ruling 009 freeze score — the number that decides whether
#: ``precompute_calibration.py`` may be touched at all — is computed off this
#: ring. A miss is still a miss; an UNATTRIBUTABLE miss is what this ends.
_CANCEL_CAUSE_PREFIX_FALLBACK = "beat:cancel_cause:"


def _cancel_cause_prefix() -> str:
    """The producer's own constant, read off the module that emits it."""
    try:
        from app.tasks.calibration_main_build import CANCEL_CAUSE_PREFIX
    except Exception:  # noqa: BLE001 — a sampler must never fail on an import
        return _CANCEL_CAUSE_PREFIX_FALLBACK
    return CANCEL_CAUSE_PREFIX


CANCEL_CAUSE_PREFIX = _cancel_cause_prefix()

#: Every prefix ``select_gauges`` scans for. One tuple so a third prefix is one
#: line here and nowhere else.
CAPTURED_PREFIXES = (CONVERGENCE_REASON_PREFIX, CANCEL_CAUSE_PREFIX)


def _required_disclosure_gauges() -> tuple[str, ...]:
    """Every gauge ``build_disclosure`` consumes, read off that module.

    Collected from its ``GAUGE_*`` constants rather than transcribed. The two
    CAL-P083 blind spots were both transcription omissions; a derivation cannot
    omit. Sorted so the tuple is stable across interpreter runs and therefore
    quotable in a report.
    """
    from app.utils import calibration_staged_disclosure as disclosure_mod

    names = {
        value
        for attr, value in vars(disclosure_mod).items()
        if attr.startswith("GAUGE_") and isinstance(value, str)
    }
    return tuple(sorted(names))


#: The gauges the DERIVED BOUND depends on. Missing any one of these makes a
#: captured row unreplayable, which is the failure this instrument exists to
#: prevent, so their absence is recorded on the observation by name.
REQUIRED_DISCLOSURE_GAUGES = _required_disclosure_gauges()

#: Gauges the bound does NOT depend on, kept because a human grading a descent
#: needs them beside it: the rebuild's rate and remaining distance, the unit
#: cost distribution that predicts the next promotion, and the carry guard's
#: predicate operands. This tuple is the sampler's own editorial choice and is
#: allowed to be hand-maintained — forgetting one costs a column in a report,
#: not the replayability of the row.
OPERATIONAL_GAUGES = (
    "staged:units_planned",
    "staged:units_done",
    "staged:units_completed_this_beat",
    "staged:beats_to_publish",
    "staged:unit_ms_mean",
    "staged:unit_ms_worst",
    "staged:window_left_ms",
    "staged:cursor_resume",
    "staged:units_cancelled",
)


# ---------------------------------------------------------------------------
# pure
# ---------------------------------------------------------------------------

def select_gauges(stages: Any) -> tuple[dict, list[str]]:
    """``(captured, missing_required)`` — the fixed gauge set out of one ledger.

    ``missing_required`` is RETURNED rather than logged, because a gauge that
    stopped being written is a finding about the producer and belongs on the
    banked row where a later reader will meet it. A sampler that silently
    captured 8 of 9 gauges and said nothing would hand its successor a row that
    replays to the wrong bound with no hint why.
    """
    if not isinstance(stages, dict):
        return {}, list(REQUIRED_DISCLOSURE_GAUGES)

    captured: dict = {}
    for name in REQUIRED_DISCLOSURE_GAUGES + OPERATIONAL_GAUGES:
        if name in stages:
            captured[name] = stages[name]

    # The prefix half. Never a fixed name, so never in the tuples above.
    for key, value in stages.items():
        if isinstance(key, str) and key.startswith(CAPTURED_PREFIXES):
            captured[key] = value

    missing = [n for n in REQUIRED_DISCLOSURE_GAUGES if n not in captured]
    return captured, missing


def _parse_stamp(value):
    """A UTC ``datetime`` from whatever the row carried, or ``None``."""
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        stamp = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            stamp = datetime.datetime.fromisoformat(text)
        except ValueError:
            return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=datetime.timezone.utc)
    return stamp.astimezone(datetime.timezone.utc)


def build_observation(
    *,
    generation: Any,
    generated_at: Any,
    complete: Any,
    payload: Any,
) -> dict:
    """One beat, reduced to a replayable observation. Pure.

    The derived bound is computed **through the production pair**
    (``build_disclosure`` then ``tolerance_pp``) and stored beside the raw
    gauges, not instead of them. Both, on purpose:

    * the raw gauges make the row **replayable** against a future version of the
      disclosure logic, which is what makes this an instrument rather than a log
      of one release's opinion;
    * the derived bound makes the row **readable** without importing anything,
      which is what makes a descent quotable from a curl.

    ``now`` is pinned to the beat's OWN ``generated_at``, never the wall clock
    (gotcha #44 — this program's most-repeated self-inflicted wound). A stored
    observation whose ``staged_age_s`` depended on when the sampler happened to
    run would be a different number every time it was re-derived.
    """
    from app.utils.calibration_published_twin import tolerance_pp
    from app.utils.calibration_staged_disclosure import build_disclosure

    payload = payload if isinstance(payload, dict) else {}
    stages = payload.get("stages")
    captured, missing = select_gauges(stages)
    stamp = _parse_stamp(generated_at)

    # 🔴 THE WALL CLOCK GETS IN HERE IF YOU LET IT, AND THIS SUITE CAUGHT IT.
    #
    # ``build_disclosure`` does ``reference = now or datetime.now(timezone.utc)``.
    # For a SERVING bank it derives its own ``staged_dt`` from
    # ``staged:served_at`` and ignores ``staged_generated_at`` entirely — so a
    # beat whose ledger stamp is unparseable still produces a MEASURED
    # disclosure, and passing ``now=None`` there dates it against whenever the
    # sampler happened to run. The row would then be a different row every time
    # it was re-derived, which is gotcha #44 arriving through the one input that
    # looked safe because it is usually not None.
    #
    # So the reference falls back to the SERVED instant, never to the clock, and
    # when the beat's own stamp is unreadable the age is nulled outright. The
    # BOUND survives that — ``tolerance_pp`` reads units, not ages — so the
    # observation stays quotable for the thing it exists to record while
    # refusing to state an age it cannot know.
    reference = stamp
    if reference is None:
        served_epoch = captured.get("staged:served_at")
        if isinstance(served_epoch, int) and not isinstance(served_epoch, bool):
            reference = datetime.datetime.fromtimestamp(
                served_epoch, tz=datetime.timezone.utc
            )

    disclosure = build_disclosure(
        ledger_stages=captured,
        staged_generated_at=stamp,
        now=reference if reference is not None else _EPOCH,
    )
    if stamp is None and isinstance(disclosure, dict) and disclosure.get("measured"):
        disclosure = dict(disclosure)
        disclosure["staged_age_s"] = None
    bound = tolerance_pp(disclosure)

    return {
        "generation": int(generation) if generation is not None else None,
        "generated_at": stamp.isoformat() if stamp is not None else None,
        # Named, so a reader meeting a row with no ``staged_age_s`` knows it was
        # WITHHELD rather than absent from the producer.
        "beat_stamp_unparseable": stamp is None,
        "envelope_complete": bool(complete),
        # -- the beat's own verdict fields, straight off the ledger -----------
        "terminal": payload.get("terminal"),
        "carried": payload.get("carried"),
        "outcome": payload.get("outcome"),
        "elapsed_ms": payload.get("elapsed_ms"),
        "input_fingerprint": payload.get("input_fingerprint"),
        # The carry-withhold announces itself here and NOWHERE else — not in
        # ``phases[].checkpoint_write``, which collapses to two values and can
        # never carry a refusal reason (CAL-P083 made that mistake first).
        "banked": payload.get("banked"),
        # -- the fixed gauge set, verbatim ------------------------------------
        "gauges": captured,
        "gauges_missing_required": missing,
        # -- derived, through production ---------------------------------------
        "disclosure": disclosure,
        "tolerance_pp": bound,
        "measured": disclosure.get("measured") is True,
    }


def merge_history(existing: Any, observation: dict, *, limit: int = HISTORY_LIMIT) -> dict:
    """``(history)`` with ``observation`` folded in. Pure, keyed on generation.

    Returns ``{"observations": [...], "appended": bool, "replaced": bool}``.

    Keyed on ``generation``, not on position, for the reason
    ``sample_calibration_beats`` learned the hard way: a generation seen twice is
    ONE beat read twice, and counting it as two produced CAL-P081's ``[13, 13]``.

    A re-read of a generation already held **replaces** it only when the stored
    copy is unmeasured and the new one is measured — a beat whose ledger row was
    incomplete at :45 and complete at :05 should improve, never regress. The
    reverse is refused: history does not get worse because a later read was
    poorer.
    """
    rows: list[dict] = []
    if isinstance(existing, dict):
        raw = existing.get("observations")
        if isinstance(raw, list):
            rows = [r for r in raw if isinstance(r, dict)]

    gen = observation.get("generation")
    appended = False
    replaced = False

    if gen is None:
        # No key means no dedup and no ordering — it would corrupt the ring
        # rather than extend it. Refused loudly by the caller's terminal.
        return {"observations": rows, "appended": False, "replaced": False}

    index = {r.get("generation"): i for i, r in enumerate(rows) if r.get("generation") is not None}
    if gen in index:
        prior = rows[index[gen]]
        if observation.get("measured") and not prior.get("measured"):
            rows[index[gen]] = observation
            replaced = True
    else:
        rows.append(observation)
        appended = True

    rows.sort(key=lambda r: (r.get("generation") is None, r.get("generation")))
    if len(rows) > limit:
        rows = rows[-limit:]

    return {"observations": rows, "appended": appended, "replaced": replaced}


def summarise(history: dict) -> dict:
    """The few numbers a reader wants before scrolling 168 rows. Pure.

    ``bound_min_pp`` is over the retained window and is reported WITH the
    generation it came from, because CAL-P083's whole finding was that quoting
    the trough alone is the #2007 defect wearing celebration clothes: the bound
    reached 0.5 pp for exactly one beat in sixteen, and a minimum with no
    denominator says the opposite of what happened.
    """
    rows = [r for r in (history.get("observations") or []) if isinstance(r, dict)]
    bounds = [
        (r.get("tolerance_pp"), r.get("generation"))
        for r in rows
        if isinstance(r.get("tolerance_pp"), (int, float))
    ]
    floor_rows = [g for b, g in bounds if b is not None and b <= 1.0]
    return {
        "observations": len(rows),
        "oldest_generation": rows[0].get("generation") if rows else None,
        "newest_generation": rows[-1].get("generation") if rows else None,
        "newest_generated_at": rows[-1].get("generated_at") if rows else None,
        "bound_readable": len(bounds),
        "bound_min_pp": min((b for b, _ in bounds), default=None),
        "bound_min_generation": min(bounds, default=(None, None))[1] if bounds else None,
        "bound_max_pp": max((b for b, _ in bounds), default=None),
        "bound_latest_pp": rows[-1].get("tolerance_pp") if rows else None,
        # How many of the retained beats were at the tight floor. This is the
        # denominator the trough needs beside it.
        "beats_at_floor": len(floor_rows),
        "beats_at_floor_generations": floor_rows[-5:],
    }


def decide_terminal(
    *,
    read_status: str,
    observation: Optional[dict],
    write_status: Optional[str],
    ledger_age_s: Optional[float],
) -> tuple[str, Optional[str]]:
    """``(terminal, reason)``. Pure, so every branch is reachable from a test.

    Ordered by which fact dominates. A stale ledger under a failed write is a
    failed run — the write failure is about US and is fixable here; the staleness
    is about the producer and is somebody else's P1.
    """
    if observation is None:
        return "failed", f"ledger_unreadable: {read_status}"
    if observation.get("generation") is None:
        return "failed", "ledger_row_has_no_generation"
    if write_status not in ("stored", "unchanged"):
        return "failed", f"history_write_failed: {write_status}"
    if observation.get("gauges_missing_required"):
        return (
            "failed",
            "required gauges absent from the ledger: "
            + ",".join(observation["gauges_missing_required"]),
        )
    if ledger_age_s is not None and ledger_age_s > LEDGER_STALE_AFTER_S:
        return (
            "partial",
            f"ledger_stale: newest beat is {int(ledger_age_s)}s old, "
            f"bound is {LEDGER_STALE_AFTER_S}s",
        )
    return "complete", None


# ---------------------------------------------------------------------------
# io
# ---------------------------------------------------------------------------

async def _read_ledger() -> tuple[Optional[dict], str]:
    """The current phase-ledger row, or ``(None, status)``. Never raises.

    An **incomplete** envelope is mined here rather than refused, and that is a
    deliberate reversal of the servability rule. ``read_snapshot`` types an
    incomplete row ``malformed``; a beat that died mid-flight banks exactly that,
    and it is the beat most worth capturing. Refusing it is how CAL-P083's twin
    endpoint answered ``artifact_unreadable`` over a 195 KB diagnosis. A
    checksum-torn or wrong-version row is a different thing — those bytes cannot
    describe themselves — and is still refused.
    """
    from app.services.durable_snapshots import read_snapshot_standalone
    from app.tasks.calibration_main_build import LEDGER_IDENTITY
    from app.utils.calibration_phase_ledger import PHASE_LEDGER_SCHEMA

    forever = 3650 * 86400
    try:
        read = await read_snapshot_standalone(
            LEDGER_IDENTITY, expected_version=PHASE_LEDGER_SCHEMA, max_age_s=forever
        )
    except Exception as exc:  # noqa: BLE001 — recorded, never swallowed
        return None, f"read_raised: {type(exc).__name__}"

    envelope = read.envelope
    if envelope is None:
        return None, read.status
    if read.status not in ("ok", "malformed"):
        # wrong_version / checksum failures: the bytes do not describe
        # themselves, so nothing here can be trusted into the history.
        return None, read.status
    return (
        {
            "generation": envelope.generation,
            "generated_at": envelope.generated_at,
            "complete": envelope.complete,
            "payload": envelope.payload,
            "status": read.status,
        },
        read.status,
    )


async def _read_history() -> tuple[dict, str]:
    """The existing ring, or an empty one. Never raises.

    A read failure returns ``({}, status)`` and the caller does NOT then write:
    appending to an empty ring after failing to read the full one would silently
    delete the history this module exists to keep. Losing one beat is a gap;
    losing the ring is the original defect.
    """
    from app.services.durable_snapshots import read_snapshot_standalone

    forever = 3650 * 86400
    try:
        read = await read_snapshot_standalone(
            HISTORY_IDENTITY, expected_version=HISTORY_SCHEMA, max_age_s=forever
        )
    except Exception as exc:  # noqa: BLE001
        return {}, f"read_raised: {type(exc).__name__}"
    if read.status == "missing":
        return {}, "missing"
    if read.envelope is None or read.status not in ("ok", "malformed"):
        return {}, read.status
    payload = read.envelope.payload
    return (payload if isinstance(payload, dict) else {}), read.status


async def run_beat_gauge_sample() -> dict:
    """Capture the current beat's fixed gauge set into the durable ring.

    Never raises. Returns the artifact ``_tracked_run`` classifies.
    """
    started = datetime.datetime.now(datetime.timezone.utc)

    ledger, read_status = await _read_ledger()
    artifact: dict[str, Any] = {
        "queue": "CAL-P084",
        "issue": 2007,
        "instrument": "beat gauge sampler — the fixed gauge, banked every beat",
        "identity": HISTORY_IDENTITY,
        "ledger_read_status": read_status,
        "required_gauges": list(REQUIRED_DISCLOSURE_GAUGES),
        "history_limit": HISTORY_LIMIT,
    }

    if ledger is None:
        artifact["terminal"], artifact["reason"] = decide_terminal(
            read_status=read_status, observation=None, write_status=None, ledger_age_s=None
        )
        artifact["appended"] = False
        return artifact

    observation = build_observation(
        generation=ledger["generation"],
        generated_at=ledger["generated_at"],
        complete=ledger["complete"],
        payload=ledger["payload"],
    )
    artifact["generation"] = observation["generation"]
    artifact["generated_at"] = observation["generated_at"]
    artifact["tolerance_pp"] = observation["tolerance_pp"]
    artifact["beat_terminal"] = observation["terminal"]
    artifact["gauges_missing_required"] = observation["gauges_missing_required"]

    stamp = _parse_stamp(ledger["generated_at"])
    ledger_age_s = (started - stamp).total_seconds() if stamp is not None else None
    artifact["ledger_age_s"] = None if ledger_age_s is None else round(ledger_age_s)

    existing, history_status = await _read_history()
    artifact["history_read_status"] = history_status
    if history_status not in ("ok", "malformed", "missing"):
        # Do not write over a ring we could not read. See ``_read_history``.
        artifact["terminal"] = "failed"
        artifact["reason"] = f"history_unreadable: {history_status}"
        artifact["appended"] = False
        return artifact

    merged = merge_history(existing, observation)
    artifact["appended"] = merged["appended"]
    artifact["replaced"] = merged["replaced"]

    history_payload = {
        "schema": HISTORY_SCHEMA,
        "limit": HISTORY_LIMIT,
        "required_gauges": list(REQUIRED_DISCLOSURE_GAUGES),
        "operational_gauges": list(OPERATIONAL_GAUGES),
        "observations": merged["observations"],
    }
    history_payload["summary"] = summarise(history_payload)
    artifact["summary"] = history_payload["summary"]

    write_status: Optional[str] = None
    if merged["appended"] or merged["replaced"] or not existing:
        try:
            from app.services.durable_snapshots import publish_snapshot_standalone
            from app.utils.durable_state import DurableEnvelope

            envelope = DurableEnvelope.build(
                identity=HISTORY_IDENTITY,
                schema_version=HISTORY_SCHEMA,
                payload=history_payload,
                complete=True,
                source="calibration_beat_gauge_sampler",
            )
            stage = await publish_snapshot_standalone(envelope)
            write_status = stage.get("status")
            artifact["history_generation"] = envelope.generation
        except Exception as exc:  # noqa: BLE001
            logger.warning("beat gauge sampler: durable write failed", exc_info=True)
            write_status = f"error: {type(exc).__name__}"
    else:
        # Nothing new to record. NOT a write failure and NOT no-work: the beat
        # is already in the ring, which is the job.
        write_status = "unchanged"
    artifact["history_write"] = write_status

    artifact["terminal"], artifact["reason"] = decide_terminal(
        read_status=read_status,
        observation=observation,
        write_status=write_status,
        ledger_age_s=ledger_age_s,
    )
    artifact["duration_s"] = round(
        (datetime.datetime.now(datetime.timezone.utc) - started).total_seconds(), 2
    )
    return artifact
