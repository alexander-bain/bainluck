#!/usr/bin/env python3
"""CAL-P111 — ruling 009's amended lift condition, as a number instead of a paragraph.

Ruling 009 freezes ``backend/app/tasks/precompute_calibration.py``. Its
2026-08-28 amendment (Alex, MC, on #2248) replaced the lift condition's clause 2:

    ~13 CONSECUTIVE clean beats  ->  22 OF THE LAST 24 beats publish cleanly

This script reads that condition off production and prints the score. It exists
because of gotcha #35's lesson — **a predicate cannot consume a threshold
written in prose.** The previous condition lived only in the ruling text, and
the consequence is on the record: it went unsatisfiable for nineteen days and
the deadlock was found by a scorecard built for something else.

WHY THE CONDITION IS A SCORE AND NOT A STREAK
----------------------------------------------
The amendment's own argument, restated here so a reader of the script does not
have to trust the ruling: a consecutive-run counter is a poor test of a RATE,
because clustered misses leave long clean stretches behind them. Measured under
a moving-block bootstrap of the real 166-beat pre-fix record, the BROKEN
producer would satisfy 13-consecutive with probability 0.27-0.59 inside 90 days
and 22-of-24 with probability 0.006-0.105. The streak form was the LOOSER test.

A score also has the property a streak does not: it exists before it is met. The
freeze's distance from lifting is readable every hour, instead of being nothing
until it is suddenly everything.

WHAT COUNTS
-----------
* **Clean** = one observation in ``calibration:beat_gauge_history`` whose
  ``outcome.published`` is ``true`` — equivalently ``terminal == "complete"``
  AND ``outcome.gate == "pass"``. A ``cancelled`` or ``not_evaluated`` beat is a
  MISS, whatever caused it. No beat is excused; that is the point of a budget.
* **The last 24** = the 24 most recent observations by ``generation``.
* **All 24 must post-date the baseline** — the deploy carrying the CAL-P109/P110
  phase-budget repair. Pass it as ``--baseline-at``. Without it this script
  scores the ring as it stands and says so, which is a MEASUREMENT and not a
  verdict on the freeze.

The no-regression half of clause 2 is NOT checked here — it is one command in
the other rail (``calibration_scorecard.py --live`` must report
``self_check.ok`` and ``headline_pass``), and this script prints the reminder
rather than duplicating a fold it would be free to disagree with.

USAGE
-----
    source ~/.claude/.env
    python3 backend/scripts/calibration_freeze_score.py
    python3 backend/scripts/calibration_freeze_score.py --baseline-at 2026-08-29T12:00:00Z
    python3 backend/scripts/calibration_freeze_score.py --json

Needs ``BAINLUCK_API`` and ``ADMIN_TOKEN``. Read-only; never writes.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# THE CONDITION. Both numbers are Alex's, ruled on #2248 2026-08-28, and each
# carries the measurement it came from. Changing either is a ruling, not a tune.
# ---------------------------------------------------------------------------

#: Clean beats required inside the window.
#:
#: 22 is the FIRST value the measured pre-fix producer does not reach. Over the
#: 166 beats in ``calibration:beat_gauge_history`` (2026-08-21T18:37Z ->
#: 2026-08-28T15:34Z, publish rate 0.476) the best 24-beat window was 19/24, and
#: under a moving-block bootstrap of that same sequence the broken producer
#: reaches 20-of-24 with probability ~1.00 and 21-of-24 with 0.48-0.70 inside 90
#: days — so 20 and 21 are thresholds the thing being excluded can clear.
#: 22-of-24 sits at 0.006-0.105.
#:
#: 23 was rejected in the OTHER direction: at a 0.85 publish rate it takes ~3.7
#: days and one dyno-cycle pair of misses costs a whole day, which re-creates a
#: softer version of the deadlock the amendment repairs.
CLEAN_REQUIRED = 22

#: Beats in the window.
#:
#: 24 = one day of the hourly beat (``precompute-calibration-main`` is
#: ``crontab(minute=15)``). Chosen so the condition reads without arithmetic:
#: ONE FULL DAY IN WHICH THE PRODUCER LOST AT MOST TWO BEATS.
WINDOW = 24

#: Per-window probability of satisfying the condition, i.i.d. binomial, at the
#: two rates the amendment is required to state. Printed so a reader meeting a
#: 19/24 knows whether that is bad luck or a broken producer.
P_AT_BROKEN_RATE = 5.6e-6   # publish rate 0.472 — the measured pre-fix rate
P_AT_HEALTHY_RATE = 0.884   # publish rate 0.95  — ~1.0 day expected wait

HISTORY_IDENTITY = "calibration:beat_gauge_history"

#: CAL-P993 (calibration-028) — WHY a miss missed.
#:
#: The score does not change and no beat is excused: ruling 009 budgets misses,
#: not excuses, and a miss caused by a deploy is still an hour in which
#: ``/api/calibration`` did not refresh. What changes is that the reader can see
#: WHICH producer question a 5/24 is evidence about.
#:
#: * ``incomplete`` — the staged build ran out of window with units banked. This
#:   is the number "is it converging?" is asking for.
#: * ``interrupted`` — the runtime took the worker away mid-phase (a deploy
#:   cycling ``worker-heavy``, a dyno restart, an operator pause). Measured
#:   2026-09-03: 21 of 23 such beats in the ring had a Heroku release inside
#:   their own window. That is a finding about the DEPLOY CADENCE.
#: * ``unattributed`` — the beat predates the cause gauge, or missed for a
#:   reason that is not a cancellation at all (``failed``, ``overlap_refused``).
#:   Rendered as its own bucket rather than folded into either real cause: this
#:   whole change exists because one word stood for two states, and inventing a
#:   third collapse to fix the first would be comic.
#:
#: The prefix must equal ``calibration_main_build.CANCEL_CAUSE_PREFIX``. It is
#: retyped here because this script imports nothing from ``app`` on purpose (it
#: runs against production from any checkout); the equality is held by
#: ``backend/tests/test_calibration_cancel_cause_993.py``, which reads both.
CANCEL_CAUSE_PREFIX = "beat:cancel_cause:"
CANCEL_CAUSE_INCOMPLETE = "incomplete"
CANCEL_CAUSE_INTERRUPTED = "interrupted"
CANCEL_CAUSE_UNATTRIBUTED = "unattributed"
CANCEL_CAUSES = (CANCEL_CAUSE_INCOMPLETE, CANCEL_CAUSE_INTERRUPTED)

#: Wide enough that the window is never short because the ring was read thin,
#: and small enough to stay under the endpoint's row cap.
FETCH_LIMIT = 200

SQL = (
    "SELECT o->>'generation' AS generation, "
    "o->>'generated_at' AS generated_at, "
    "o->>'terminal' AS terminal, "
    "o->'outcome'->>'gate' AS gate, "
    "o->'outcome'->>'published' AS published"
    + "".join(
        f", o->'gauges'->>'{CANCEL_CAUSE_PREFIX}{cause}' AS cause_{cause}"
        for cause in CANCEL_CAUSES
    )
    + " FROM durable_state_snapshots d, "
    "jsonb_array_elements(d.payload->'observations') o "
    f"WHERE d.identity = '{HISTORY_IDENTITY}' "
    "ORDER BY 1"
)


class FreezeScoreError(RuntimeError):
    """Could not measure. Distinct from measuring a bad score."""


def _post(api: str, token: str, body: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        f"{api.rstrip('/')}/api/admin/db-query",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise FreezeScoreError(f"HTTP {exc.code}: {exc.read().decode()[:400]}") from None
    except urllib.error.URLError as exc:
        raise FreezeScoreError(f"unreachable: {exc.reason}") from None


def _parse_stamp(text):
    if not text:
        return None
    try:
        stamp = datetime.datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=datetime.timezone.utc)
    return stamp.astimezone(datetime.timezone.utc)


def is_clean(row: dict) -> bool:
    """The amendment's definition, in one place.

    ``published`` is the primary key on the question and the other two are
    checked WITH it rather than instead of it: a row that claims ``published``
    while its gate did not pass is a contradiction in the producer's own
    ledger, and the honest reading of a contradiction is NOT CLEAN.
    """
    return (
        str(row.get("published")).lower() == "true"
        and row.get("terminal") == "complete"
        and row.get("gate") == "pass"
    )


def miss_cause(row: dict) -> str:
    """Which bucket a NON-clean beat belongs to. Pure. See :data:`CANCEL_CAUSES`.

    Only ever called on a miss — a clean beat has no cause and asking for one
    would invite a caller to render "incomplete" beside a publish.

    A beat carrying BOTH gauges is impossible (one exception ends one beat) and
    is reported ``unattributed`` rather than picking a winner: two causes on one
    row means the writer is wrong, and guessing which half to believe is how a
    contradiction becomes a statistic.
    """
    present = [c for c in CANCEL_CAUSES if row.get(f"cause_{c}") is not None]
    return present[0] if len(present) == 1 else CANCEL_CAUSE_UNATTRIBUTED


def score(rows: list[dict], *, baseline=None, window: int = WINDOW,
          required: int = CLEAN_REQUIRED) -> dict:
    """The verdict. Pure, so every branch is reachable from a test."""
    ordered = sorted(rows, key=lambda r: int(r["generation"]))

    eligible = ordered
    excluded_pre_baseline = 0
    if baseline is not None:
        eligible = []
        for row in ordered:
            stamp = _parse_stamp(row.get("generated_at"))
            if stamp is not None and stamp >= baseline:
                eligible.append(row)
            else:
                excluded_pre_baseline += 1

    considered = eligible[-window:]
    clean = sum(1 for r in considered if is_clean(r))

    # A short window is NOT a low score. Reporting 8/24 because only 8 beats
    # have happened since the baseline would read as a broken producer when it
    # actually means "not enough time has passed" — gotcha #53 at the level of
    # a verdict, and the exact confusion the old streak form created.
    if len(considered) < window:
        verdict = "WINDOW_NOT_FULL"
    elif clean >= required:
        verdict = "CONDITION_MET"
    else:
        verdict = "NOT_MET"

    # The best the window could still reach if every remaining beat were clean.
    # Under a rolling window this is always `window` once it is full, so it is
    # only informative while filling — which is when a reader most wants it.
    beats_still_to_come = window - len(considered)
    reachable = clean + beats_still_to_come

    return {
        "condition": f"{required} of the last {window}",
        "ruling": "009, amended 2026-08-28 (Alex, MC, #2248)",
        "clean": clean,
        "window": window,
        "required": required,
        "beats_in_window": len(considered),
        "misses": len(considered) - clean,
        "misses_allowed": window - required,
        # CAL-P993: the misses, attributed. Every key is always present, at zero
        # when empty — an absent key would read as "none of that kind" and
        # "this build predates the split" identically, which is the exact
        # collapse this field exists to end.
        "miss_causes": {
            bucket: sum(
                1
                for r in considered
                if not is_clean(r) and miss_cause(r) == bucket
            )
            for bucket in CANCEL_CAUSES + (CANCEL_CAUSE_UNATTRIBUTED,)
        },
        "verdict": verdict,
        "reachable_if_all_remaining_clean": reachable if beats_still_to_come else None,
        "baseline_at": baseline.isoformat() if baseline else None,
        "excluded_pre_baseline": excluded_pre_baseline,
        "ring_observations": len(ordered),
        "oldest_in_window": considered[0].get("generated_at") if considered else None,
        "newest_in_window": considered[-1].get("generated_at") if considered else None,
        "p_per_window_at_broken_rate": P_AT_BROKEN_RATE,
        "p_per_window_at_healthy_rate": P_AT_HEALTHY_RATE,
        "beats": [
            {
                "generated_at": r.get("generated_at"),
                "terminal": r.get("terminal"),
                "gate": r.get("gate"),
                "clean": is_clean(r),
                "miss_cause": None if is_clean(r) else miss_cause(r),
            }
            for r in considered
        ],
    }


def render(result: dict) -> str:
    strip = "".join("#" if b["clean"] else "." for b in result["beats"])
    # A filling window is scored against the beats that EXIST, not against 24.
    # "4/24" when only six beats have happened since the baseline reads as a
    # catastrophic producer and means "it is early" — the two must never share a
    # denominator.
    full = result["beats_in_window"] == result["window"]
    headline = (
        f"  {result['clean']}/{result['window']} clean"
        if full
        else f"  {result['clean']}/{result['beats_in_window']} clean so far (window {result['window']})"
    )
    lines = [
        "RULING 009 FREEZE SCORE — " + result["condition"],
        headline + f"   ({result['misses']} misses; {result['misses_allowed']} allowed)",
        f"  {strip}   <- oldest ... newest",
        f"  window   {result['oldest_in_window']} -> {result['newest_in_window']}",
        "  misses   "
        + " · ".join(
            f"{count} {bucket}" for bucket, count in result["miss_causes"].items()
        )
        + "   (attributed since CAL-P993; every miss still counts as a miss)",
        f"  ring     {result['ring_observations']} observations"
        + (
            f", {result['excluded_pre_baseline']} excluded as pre-baseline"
            if result["baseline_at"]
            else ""
        ),
        f"  VERDICT  {result['verdict']}",
    ]
    if result["verdict"] == "WINDOW_NOT_FULL":
        lines.append(
            f"           only {result['beats_in_window']} post-baseline beats exist; "
            f"the freeze cannot lift before {result['window']} of them do "
            f"(best still reachable: {result['reachable_if_all_remaining_clean']}/{result['window']})"
        )
    elif result["verdict"] == "NOT_MET":
        lines.append(
            f"           per-window P is {result['p_per_window_at_broken_rate']:.1e} at the broken "
            f"0.472 rate and {result['p_per_window_at_healthy_rate']:.3f} at a healthy 0.95 rate — "
            "a score this far short is not bad luck"
        )
        # CAL-P993. The line above used to end "is a PRODUCER finding". It is
        # not entitled to say which finding it is: an `interrupted` miss is the
        # runtime taking the worker away, and blaming the producer for it is how
        # ruling 009's freeze came to be held shut by other lanes' deploys.
        interrupted = result["miss_causes"].get(CANCEL_CAUSE_INTERRUPTED, 0)
        misses = result["misses"]
        if misses and interrupted * 2 > misses:
            lines.append(
                f"           MOST MISSES ARE `{CANCEL_CAUSE_INTERRUPTED}` "
                f"({interrupted}/{misses}) — the build was KILLED, not slow. That is a "
                "deploy-cadence finding, and no change to the producer moves it."
            )
    else:
        lines += [
            "",
            "  CLAUSE 2 IS SATISFIED. The freeze is NOT yet lifted — clause 2 is one half:",
            "    * clause 1: a fresh publish exists post-baseline (implied by the window above)",
            "    * no-regression: `calibration_scorecard.py --live` must report",
            "      self_check.ok: true AND headline_pass: true on the closing beat",
            "    * ruling 009: whoever observes both WRITES THE NUMBERS INTO THE CALIBRATION",
            "      REPORT and says the freeze is lifted in the same entry. It does not",
            "      expire on its own and no lane lifts it by judgment.",
        ]
    if not result["baseline_at"]:
        lines += [
            "",
            "  ⚠️  NO --baseline-at GIVEN. This is a measurement of the ring as it stands,",
            "      not a verdict on the freeze: the amendment requires all 24 beats to",
            "      post-date the deploy carrying the CAL-P109/P110 phase-budget repair.",
        ]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--baseline-at",
        help="ISO-8601 instant of the baseline deploy. Beats before it are excluded.",
    )
    ap.add_argument("--json", action="store_true", help="emit the result as JSON")
    args = ap.parse_args(argv)

    api = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not api or not token:
        print("BAINLUCK_API and ADMIN_TOKEN required (source ~/.claude/.env)", file=sys.stderr)
        return 2

    baseline = None
    if args.baseline_at:
        baseline = _parse_stamp(args.baseline_at)
        if baseline is None:
            print(f"unparseable --baseline-at: {args.baseline_at}", file=sys.stderr)
            return 2

    try:
        payload = _post(api, token, {"sql": SQL, "limit": FETCH_LIMIT})
    except FreezeScoreError as exc:
        print(f"could not read {HISTORY_IDENTITY}: {exc}", file=sys.stderr)
        return 2

    columns = payload.get("columns") or []
    rows = [dict(zip(columns, r)) for r in (payload.get("rows") or [])]
    if not rows:
        # An empty 200 is a response SHAPE, not an absence (gotcha #53). The
        # sampler writes every hour; an empty ring means the sampler is down,
        # which is a finding and must not read as 0/24.
        print(
            f"{HISTORY_IDENTITY} returned NO observations. That is the sampler failing, "
            "not a score of zero — check `calibration_beat_gauge_sampler`.",
            file=sys.stderr,
        )
        return 2
    if payload.get("truncated"):
        print(
            f"WARNING: the read was truncated at {FETCH_LIMIT} rows; the window is still the "
            "newest beats, but the ring total below is a floor.",
            file=sys.stderr,
        )

    result = score(rows, baseline=baseline)
    print(json.dumps(result, indent=2) if args.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
