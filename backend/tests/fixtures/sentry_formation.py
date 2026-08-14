"""The deployed formation, PARSED from backend/Procfile — never hand-copied (#1501).

Codex C-CERT-SENTRY (c) rejected the previous volume claim partly because its
budget arithmetic "prices four realtime children" while the Procfile also
declares background and heavy pools, web, a scheduler and a websocket process.
A constant transcribed into a comment cannot notice a new dyno type; this module
reads the file, so adding one to the Procfile changes the derived number and
trips :mod:`tests.test_sentry_filter`.

Why the process count is what matters: ``app/utils/sentry_filter.py`` keeps its
throttle state **in process memory** (deliberately — gotcha #39: the biggest
error class is Redis being unreachable, and a filter that needs Redis to decide
whether to report a Redis failure fails exactly when it matters). So every
process that calls ``sentry_sdk.init`` holds its own independent allowance, and
the fleet ceiling for one signature is

    cap x (SDK processes) x (process incarnations per process per day)

Celery's prefork pool forks children from the parent AFTER ``sentry_sdk.init``
has run at import time, so each child inherits a *copy* of an empty throttle
table — a fresh allowance per child, and another one every time
``--max-memory-per-child`` recycles it.
"""

from __future__ import annotations

import re
from pathlib import Path

#: Free Developer plan (``am3_f``): 5,000 error events per billing month,
#: on-demand disabled, period the 21st -> the 20th.
QUOTA_EVENTS_PER_MONTH = 5_000
#: Mean days per month, so the daily budget does not swing with month length.
DAYS_PER_MONTH = 30.4
DAILY_BUDGET = QUOTA_EVENTS_PER_MONTH / DAYS_PER_MONTH  # ~164.5/day

PROCFILE = Path(__file__).resolve().parents[2] / "Procfile"


def parse_procfile(path: Path = PROCFILE) -> dict[str, dict]:
    """``{proc_type: {"command", "concurrency", "max_memory_kb", "kind"}}``."""
    out: dict[str, dict] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        name, command = line.split(":", 1)
        name, command = name.strip(), command.strip()
        conc = re.search(r"--concurrency[= ](\d+)", command)
        mem = re.search(r"--max-memory-per-child[= ](\d+)", command)
        if "celery" in command and " worker" in f" {command}":
            kind = "celery_worker"
        elif "celery" in command and "beat" in command:
            kind = "celery_beat"
        elif name == "release":
            kind = "release"
        else:
            kind = "single"
        out[name] = {
            "command": command,
            "concurrency": int(conc.group(1)) if conc else None,
            "max_memory_kb": int(mem.group(1)) if mem else None,
            "kind": kind,
        }
    return out


def sdk_processes(spec: dict) -> int:
    """OS processes that hold their own ``before_send`` state, for one dyno.

    A celery prefork worker is the parent plus ``--concurrency`` children; the
    parent counts because billiard's worker-death records are emitted there.
    """
    if spec["kind"] == "celery_worker":
        return 1 + (spec["concurrency"] or 1)
    return 1


FORMATION = parse_procfile()

#: Steady-state process types (``release`` is transient, one per deploy).
STEADY_TYPES = tuple(sorted(n for n in FORMATION if n != "release"))

#: Every steady-state process type initialises the SDK: ``web`` imports
#: ``app.main``; the celery types boot ``app.tasks.celery_app``; ``worker-ws``
#: runs ``run_kalshi_ws.py``, whose ``from app.tasks.kalshi_ws import ...``
#: executes ``app/tasks/__init__.py`` and therefore its ``sentry_sdk.init``.
STEADY_SDK_PROCESSES = sum(sdk_processes(FORMATION[n]) for n in STEADY_TYPES)

#: One dyno of each type is running in production (``heroku ps -a bainluck``,
#: verified 2026-08-13). Scaling any type up multiplies the ceiling below.
DYNOS_PER_TYPE = 1


# ---------------------------------------------------------------------------
# server_name as an allowance-reset multiplier — CORROBORATED, and bounded
# (codex C-CERT-SENTRY-R2 finding 3, second half)
#
# The claim under challenge: each distinct ``server_name`` is a fresh process
# incarnation with an empty throttle table, so ~72 of them a day is ~72 resets
# of every allowance. Codex objected that 563 distinct values prove CARDINALITY
# and not that the changes are restarts — and the anonymisation removes the
# value needed to check. Fair, and it is now checked from outside the fixture.
#
# Deploy evidence, measured 2026-08-14:
#
#   heroku releases -a bainluck -n 200   ->  200 releases spanning
#                                            2026-07-28 -> 2026-08-14 (16.84d)
#                                            = 11.9 releases/day
#   Sentry count_unique(release), in-window:  2026-07-22 -> 20
#                                             2026-07-25 ->  5
#
# Every release restarts every dyno, so at 6 steady types a 12-release day
# mints ~72 hostnames — which is the observed mean (71.9/day) almost exactly.
# The interpretation is therefore corroborated IN MAGNITUDE by an independent
# source, which is what it lacked.
#
# What is NOT established, and is recorded rather than smoothed: on 2026-07-25
# Sentry saw only 5 releases against 73 distinct census dynos, so deploys alone
# do not explain that day. The residual is presumably Heroku's own daily dyno
# cycling plus R14/R15 memory restarts, neither of which was measured here.
#
# The bound that makes the residual safe: this uncertainty can only mean MORE
# incarnations than modelled, and the replay does not extrapolate — it partitions
# by the incarnations actually observed in the census. An increase beyond that is
# exactly the shock MIN_SAFE_MARGIN exists to absorb.
CENSUS_DYNO_INCARNATIONS = 564
CENSUS_SINGLE_DAY_INCARNATIONS = 553
CENSUS_MEAN_INCARNATIONS_PER_DAY = 71.875
MEASURED_RELEASES_PER_DAY = 11.9


# ---------------------------------------------------------------------------
# The BUDGET MODEL — #1501 item 1, from codex C-CERT-SENTRY-R2 finding 1.
#
# The replay alone is not a budget. It is a REPLAY: one frozen eight-day census
# pushed back through the shipped policy, so it can only ever price signatures
# that were present in that window. Two ordinary shipped states are absent from
# it by construction, and each one on its own turned the certified 5% margin
# negative. They are modelled here as explicit reserves, so the budget prices
# the POLICY rather than the sample.
# ---------------------------------------------------------------------------

#: Largest prefork pool in the formation. A task-side signature can land on any
#: child, and each child holds its own throttle table.
MAX_WORKER_CONCURRENCY = max(
    (spec["concurrency"] or 1)
    for spec in FORMATION.values()
    if spec["kind"] == "celery_worker"
)

#: Children in the pool that runs the watchdog beat (``worker-background``),
#: plus its parent — the parent does not run task bodies, so only the children
#: can emit a watchdog alert.
WATCHDOG_POOL_CHILDREN = FORMATION["worker-background"]["concurrency"] or 1

#: The watchdog's emission cooldown is 6h and FLEET-shared (Redis SET NX).
WATCHDOG_COOLDOWN_WINDOWS_PER_DAY = 24 // 6

#: Distinct ``[alert_class, provider]`` pairs alarming per day, measured from
#: the census (40 pair-days over 8 days).
WATCHDOG_PAIRS_PER_DAY = 5


def novel_signature_reserve(backstop_per_window: int, signatures: int = 1) -> int:
    """Events/day held back for signature(s) the census has never seen.

    The census cannot contain tomorrow's bug. One ordinary novel
    high-frequency worker signature — a new task erroring on every run — is
    capped per process, and a task-side error reaches every child in the pool,
    so it costs ``cap x children`` per day, every day, until someone fixes it.
    Pricing zero for that is pricing the sample instead of the policy.
    """
    return backstop_per_window * MAX_WORKER_CONCURRENCY * signatures


def watchdog_ceiling_per_day(backstop_per_window: int) -> int:
    """Watchdog events/day under the WORSE of its two shipped states.

    ``_alert_on_cooldown`` fails **open** when Redis is unreachable — a
    deliberate choice (a telemetry-infra failure must never swallow an alarm),
    and the tested one. So the cooldown cannot be assumed to be holding, and
    the honest ceiling is the max of:

    * cooldown HOLDING — ``windows/day`` emissions per pair; and
    * cooldown FAILED OPEN — every reading emits, bounded only by the
      per-process backstop across the pool that runs the beat.

    Each is then bounded by the other mechanism, because both are always
    armed: a working cooldown is still subject to the backstop, and a failed
    cooldown is still subject to nothing else. This is why lowering the
    backstop makes the fail-open path free rather than merely cheaper.
    """
    cooldown_bound = WATCHDOG_COOLDOWN_WINDOWS_PER_DAY
    backstop_bound = backstop_per_window * WATCHDOG_POOL_CHILDREN
    return WATCHDOG_PAIRS_PER_DAY * min(cooldown_bound, backstop_bound)


#: The floor the margin must clear, as a fraction of the daily budget.
#:
#: A FLOOR, deliberately, and not the range it replaces. The predecessor
#: asserted ``0.0 < headroom < 0.10`` under a docstring promising that a change
#: making the margin thinner would fail — but shrinking the margin from 5% to
#: 0.1% satisfies that assertion perfectly. It was a test whose name was the
#: opposite of its assertion, and it passed all the way to production.
#:
#: **Why 12%, derived rather than chosen.** A floor is only meaningful if it
#: exceeds the error of the instrument it is applied to, and that error is now
#: measured rather than guessed: rebuilding the fixture with the signature
#: fields it had been missing (schema 2) moved the replay from 133.6 to
#: 141.1/day — a **5.6% correction, in the optimistic direction**, from ONE
#: missing field family. The floor is set at roughly twice the largest
#: correction the fixture has ever needed, so a comparable undiscovered
#: distortion cannot by itself put the policy over quota.
#:
#: Recorded plainly because the sequence matters: this constant was provisionally
#: 15% earlier in the same change, written BEFORE the schema-2 rebuild existed.
#: What moved it is the rebuild — a better instrument with a measurable error
#: term — and not the number the rebuild produced. Tuning a floor until the
#: current result clears it is the exact failure this constant replaced, so if a
#: future change cannot meet 12%, cut volume or lower a cap. Do not edit this
#: line.
MIN_SAFE_MARGIN = 0.12

#: The floor expressed the way an operator can actually reason about it: how
#: many *additional* novel high-frequency worker signatures the remaining slack
#: absorbs before the quota is at risk. A percentage is abstract; "we can take
#: five more bugs like the ones we already have" is not.
NOVEL_SIGNATURE_CAPACITY_FLOOR = 5
