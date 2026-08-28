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

#: Wide enough that the window is never short because the ring was read thin,
#: and small enough to stay under the endpoint's row cap.
FETCH_LIMIT = 200

SQL = (
    "SELECT o->>'generation' AS generation, "
    "o->>'generated_at' AS generated_at, "
    "o->>'terminal' AS terminal, "
    "o->'outcome'->>'gate' AS gate, "
    "o->'outcome'->>'published' AS published "
    "FROM durable_state_snapshots d, "
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
            "a score this far short is a producer finding, not bad luck"
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
