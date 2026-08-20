"""Reduce the typeahead warmer's pass ring to the distribution three things need.

LAT-P074 (#1866, #1609, #1996). The pure half of `GET /api/admin/typeahead-warmer/last`:
Redis I/O lives in the route, the arithmetic lives here, and the tests exercise
this module with no Redis at all. The same decision/IO split LAT-P073 made for
the publish-side pre-cert artifact, for the same reason — a reduction that can
only be tested through a live Redis is a reduction that does not get tested.

(That artifact is deliberately NOT named here: a tripwire test greps every file
under `app/` for its module name to prove it is still unwired, and a docstring
mention reads to that grep exactly like an import. Which is the guard behaving
correctly — a citation is cheap and a false negative on "is the gate shipped"
is not.)

## Why this endpoint exists, stated precisely, because the previous cycle had it wrong

LAT-P073 concluded the warmer's pass result was unreadable in production
("it goes to the task return value and a log, and nothing can read either").
**It was readable.** `_tracked_run` -> `record_task_success` writes the whole
summary to `task_metrics:warm_typeahead.last_result_summary`, and
`GET /api/admin/celery/task-metrics/warm_typeahead` has been returning it all
along. That correction matters more than the endpoint does, because it is the
second time this program has planned around an instrument it already had.

What is actually missing is a **distribution**, and it is missing structurally
rather than accidentally:

* that slot holds ONE outcome and is overwritten by every run, including no-ops;
* measured 2026-08-20T00:15Z on a saturated 50-sample duration ring, **33 of 50
  executions were no-ops (all <= 71 ms) and 17 were real passes (all >= 32.9 s)**
  — so a single read lands on a no-op two times in three;
* and no number of reads of one overwritten slot reconstructs a distribution.

Three separate pieces of work are blocked on the distribution and not on the
last value: `MEASURED_WALL_MAX_S` (#1866 §5) needs a pass-only wall MAXIMUM; the
publish gate's registered halt needs `expired` PER PASS; and #1996 needs the
no-op share counted rather than inferred.

## The three states, and why they are three

Gotcha #53 and ruling 075's second clause: "could not check" must never render
as "nothing to report".

| status | means | how a reader should act |
|---|---|---|
| `unreadable` | Redis raised. **We learned nothing.** | fix the read, conclude nothing |
| `no_data` | Redis answered, and the warmer has written nothing | the warmer has not run since the ring's TTL |
| `ok` | real records | read the numbers |

A fourth distinction lives *inside* `ok`: `passes.n == 0` with `skips.total > 0`
is a warmer that is FIRING and skipping every time — the single most important
state this surface can report, and the one a boolean "healthy" would erase.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Optional

#: Statuses, named so a caller cannot typo one into a silent mismatch.
STATUS_OK = "ok"
STATUS_NO_DATA = "no_data"
STATUS_UNREADABLE = "unreadable"


def _percentile(values: list[float], q: float) -> Optional[float]:
    """Nearest-rank percentile over an already-sorted-or-not list.

    Nearest-rank rather than interpolated on purpose: every value in this
    distribution is a real measured pass, and an interpolated p95 reports a wall
    that no pass ever had. When the question is "did a pass cross the TTL", an
    invented value between two real ones is the wrong kind of answer.
    """
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    idx = int(round(q * (len(ordered) - 1)))
    return ordered[max(0, min(idx, len(ordered) - 1))]


def _distribution(values: list[float]) -> dict:
    """min / p50 / p95 / max plus n, or an explicit empty shape.

    Returns the same KEYS whether or not there is data, so a consumer never has
    to branch on `n` to know whether a field exists — the contract
    `typeahead_warmer._no_work` carries for the same reason. `None` is "not
    measured"; it is never rendered as `0.0`.
    """
    return {
        "n": len(values),
        "min": min(values) if values else None,
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "max": max(values) if values else None,
    }


def decode_records(raw: Iterable[Any]) -> list[dict]:
    """Ring entries -> dicts, dropping anything unparseable rather than guessing.

    Accepts `bytes` and `str` because a redis client may be configured either
    way, and a reader that silently returned `[]` for the wrong one would report
    "the warmer has not run" about a warmer that had — the exact false absence
    this module is built to refuse.
    """
    out: list[dict] = []
    for item in raw or ():
        if isinstance(item, (bytes, bytearray)):
            try:
                item = item.decode()
            except UnicodeDecodeError:
                continue
        if isinstance(item, dict):
            out.append(item)
            continue
        try:
            parsed = json.loads(item)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict):
            out.append(parsed)
    return out


def decode_state(raw: Any) -> dict:
    """The state hash -> `{skips: {...}, last_outcome: {...}|None, ...}`.

    Skip counters are stored as `skips:<reason>` fields so that a reason nobody
    anticipated still lands somewhere countable instead of being dropped by a
    fixed schema.
    """
    if not raw:
        return {"skips": {}, "skips_total": 0, "last_outcome": None, "last_outcome_at": None}

    def _s(v):
        if isinstance(v, (bytes, bytearray)):
            try:
                return v.decode()
            except UnicodeDecodeError:
                return ""
        return v if isinstance(v, str) else str(v)

    flat = {_s(k): _s(v) for k, v in dict(raw).items()}

    skips: dict[str, int] = {}
    for key, value in flat.items():
        if not key.startswith("skips:"):
            continue
        try:
            skips[key.split(":", 1)[1]] = int(value)
        except (TypeError, ValueError):
            continue

    last_outcome = None
    if flat.get("last_outcome"):
        try:
            candidate = json.loads(flat["last_outcome"])
            if isinstance(candidate, dict):
                last_outcome = candidate
        except (TypeError, ValueError):
            last_outcome = None

    last_at = None
    if flat.get("last_outcome_at"):
        try:
            last_at = float(flat["last_outcome_at"])
        except (TypeError, ValueError):
            last_at = None

    return {
        "skips": skips,
        "skips_total": sum(skips.values()),
        "last_outcome": last_outcome,
        "last_outcome_at": last_at,
    }


def summarise(
    records: list[dict],
    state: dict,
    *,
    now: float,
    ring_max: int,
    ttl_s: int,
) -> dict:
    """The payload. Pure — the caller owns every byte of Redis I/O.

    `ttl_s` is `/typeahead`'s response-cache TTL, carried into the payload so a
    reader can grade the walls against the cliff **without** having to know the
    constant. An instrument that reports a measurement whose threshold lives in
    another file makes every reader re-derive the comparison, and half of them
    will re-derive it from memory.
    """
    passes = [r for r in records if r.get("terminal") != "skipped"]

    walls = [float(r["seconds_wall"]) for r in passes
             if isinstance(r.get("seconds_wall"), (int, float))]
    periods = [float(r["period_s"]) for r in passes
               if isinstance(r.get("period_s"), (int, float))]
    expired = [int(r["expired"]) for r in passes
               if isinstance(r.get("expired"), (int, float))]

    ats = [float(r["at"]) for r in records if isinstance(r.get("at"), (int, float))]
    span_s = (max(ats) - min(ats)) if len(ats) >= 2 else None

    over_ttl = [w for w in walls if w > ttl_s]
    passes_with_loss = [e for e in expired if e > 0]

    status = STATUS_OK
    if not records and not state.get("skips_total") and state.get("last_outcome") is None:
        status = STATUS_NO_DATA

    return {
        "status": status,
        "ring_max": ring_max,
        "ring_ttl_s": ttl_s,
        "response_cache_ttl_s": ttl_s,
        "read_at_epoch": round(now, 3),
        # The pass distribution. This is the thing that does not exist anywhere
        # else — `task_metrics.last_result_summary` holds one overwritten slot.
        "passes": {
            "n": len(passes),
            "span_s": None if span_s is None else round(span_s, 1),
            "newest_age_s": round(now - max(ats), 1) if ats else None,
            "oldest_age_s": round(now - min(ats), 1) if ats else None,
            "seconds_wall": _distribution(walls),
            "period_s": _distribution(periods),
            # `expired` is the halt signal the publish gate has to register
            # against: entries whose key was GONE when the pass reached them,
            # i.e. cache-entry loss that a user typing that prefix paid for.
            "expired": {
                "passes_with_loss": len(passes_with_loss),
                "worst": max(expired) if expired else None,
                "total": sum(expired) if expired else 0,
                "measured_over_passes": len(expired),
            },
            # Walls above the cliff are called out rather than left for the
            # reader to compute, because this is the number #1866 turns on.
            "walls_over_response_ttl": len(over_ttl),
            "records": passes,
        },
        # Counted, not ringed. A warmer firing and skipping every time reads as
        # `passes.n == 0, skips.total > 0` — which is a diagnosis, where a bare
        # empty ring is only an absence.
        "skips": {
            "total": state.get("skips_total", 0),
            "by_reason": state.get("skips", {}),
        },
        # The most recent outcome of ANY kind, so "the last thing that happened
        # was a no-op" is answerable without waiting for the ring to fill.
        "last_outcome": state.get("last_outcome"),
        "last_outcome_age_s": (
            None if not state.get("last_outcome_at")
            else round(now - float(state["last_outcome_at"]), 1)
        ),
    }


def unreadable(reason: str, *, now: float, ring_max: int, ttl_s: int) -> dict:
    """The `unreadable` shape. A read that could not happen is not a read.

    Carries the same top-level keys as `summarise` so a consumer parsing the
    payload does not fault on the error path — but `status` is unambiguous and
    every measured field is `None`, never `0`. Ruling 075's second clause, at
    the point of writing rather than the point of reading.
    """
    return {
        "status": STATUS_UNREADABLE,
        "reason": reason,
        "ring_max": ring_max,
        "ring_ttl_s": ttl_s,
        "response_cache_ttl_s": ttl_s,
        "read_at_epoch": round(now, 3),
        "passes": {
            "n": None,
            "span_s": None,
            "newest_age_s": None,
            "oldest_age_s": None,
            "seconds_wall": _distribution([]),
            "period_s": _distribution([]),
            "expired": {
                "passes_with_loss": None,
                "worst": None,
                "total": None,
                "measured_over_passes": None,
            },
            "walls_over_response_ttl": None,
            "records": [],
        },
        "skips": {"total": None, "by_reason": {}},
        "last_outcome": None,
        "last_outcome_age_s": None,
    }
