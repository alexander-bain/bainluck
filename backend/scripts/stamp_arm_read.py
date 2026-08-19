#!/usr/bin/env python3
"""Take one graded read of the stamp arm, and append it to a longitudinal series.

LAT-P073 (#1995, #1609). Fable's LAT-P073 item 1: *"START THE 24h STAMP-ARM READ
NOW (it is live). The no-start class grades on it, not celery-debug."*

A 24-hour read does not fit inside one program window, so the read has to survive
the window that starts it. That is this script's whole reason to exist: it turns
"go look at the endpoint" into an artifact the next window can re-run verbatim and
diff, rather than a screenshot in a report that nobody can reproduce.

It exists as a script rather than a `curl` in a report for three reasons, each of
which cost a previous cycle:

1. **The class is a census, not a number.** `arm_counts.rate_arm_blind_total` counts
   only entries that reached `graded`. An entry that falls out of `graded` into
   `unmapped` silently *decreases* it — so the headline number can improve because
   the instrument went blinder. This script reports the full census
   (`above_ceiling = graded_blind + unmapped_above_ceiling`) so that cannot happen
   unnoticed. Measured 2026-08-19T23:30Z: 39 = 24 + 15.
2. **Reading `celery-debug` for this is what took production down** (#1994). The
   endpoint used here is pure Redis — `build_schedule_adherence` takes no celery
   broadcast — so it is safe to sample. The script hard-refuses to call
   `celery-debug` at all, so a future reader cannot reach for it out of habit.
3. **A flip is the finding, not the level.** Every stamp-armed entry read
   `on_schedule` at t0. What 24 hours buys is the chance to catch one that stops
   doing so, and that needs the same read taken repeatedly against a recorded t0.

Usage (needs `BAINLUCK_API` and `ADMIN_TOKEN`; `source ~/.claude/.env`):

    python3 backend/scripts/stamp_arm_read.py                   # print a summary
    python3 backend/scripts/stamp_arm_read.py --json            # full record
    python3 backend/scripts/stamp_arm_read.py --append s.jsonl  # add to a series
    python3 backend/scripts/stamp_arm_read.py --grade s.jsonl   # grade the series

The `--grade` pass is the one that answers item 1: it reports, over every sample in
the series, which stamp-armed tasks were EVER graded anything other than
`on_schedule`, and whether the above-ceiling census moved.

No DB, no repo imports, standard library only — so it runs from any checkout, and
from none.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

#: The rate arm needs `window_s / interval_s >= MIN_EXPECTED_FIRES`, and `window_s`
#: is bounded above by `WINDOW_COUNTER_TTL`. So the ceiling is arithmetic:
#: 86400 / 2.0 = 43200s = 12h. Mirrored here rather than imported because this
#: script must run without the backend on the path; `--json` emits it so a drift
#: against `app/utils/schedule_adherence.rate_arm_is_structurally_blind` is visible
#: in the record itself rather than silently changing what the census counts.
RATE_ARM_CEILING_S = 43200.0

_ENDPOINT = "/api/admin/celery/schedule-adherence"

#: Reading this to grade beats is the thing item 1 exists to stop (#1994): two
#: read-only samplers on it black-holed the entire production API for ~10 minutes.
#: Named so the refusal is a fact about a specific endpoint, not a vague caution.
_FORBIDDEN = "celery-debug"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(api: str, token: str, timeout: float = 60.0) -> dict:
    """One read of the adherence surface. Raises rather than returning a shape.

    A failed read must not be recorded as a read that found nothing (gotcha #53):
    the whole point of the series is that a missing sample and a sample showing
    zero blind entries are opposite findings.
    """
    if _FORBIDDEN in _ENDPOINT:  # pragma: no cover - structural assertion
        raise AssertionError("this script must never poll celery-debug (#1994)")
    url = api.rstrip("/") + _ENDPOINT
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        if resp.status != 200:
            raise RuntimeError(f"{url} -> HTTP {resp.status}")
        return json.loads(resp.read().decode())


def summarise(payload: dict, *, read_at: str | None = None) -> dict:
    """Reduce one payload to the census item 1 is graded on.

    Deliberately keeps the per-task stamp detail for stamp-armed entries only.
    The full payload is ~66 KB and a 24h series of them is not a thing anyone
    will read; the stamp rows are ~30 lines and are the actual subject.
    """
    graded = payload.get("all") or {}
    unmapped = payload.get("unmapped") or []

    stamp_rows = {}
    for name, row in graded.items():
        if row.get("arm") != "stamp":
            continue
        stamp_rows[name] = {
            "interval_s": row.get("interval_s"),
            "verdict": row.get("verdict"),
            "stamp_kind": row.get("stamp_kind"),
            "stamp_age_s": row.get("stamp_age_s"),
            "age_over_interval": row.get("stamp_age_over_interval"),
        }

    graded_blind = sorted(n for n, r in graded.items() if r.get("rate_arm_blind"))
    unmapped_above = sorted(
        u["task"] for u in unmapped if (u.get("interval_s") or 0) > RATE_ARM_CEILING_S
    )

    # Non-`on_schedule` verdicts on EVERY arm, not just the stamp arm: the series
    # is cheap and a rate-arm regression during the 24h window is worth catching
    # in the same artifact rather than needing a second one.
    exceptions = {
        n: {
            "verdict": r.get("verdict"),
            "arm": r.get("arm"),
            "interval_s": r.get("interval_s"),
            "reason": r.get("reason"),
        }
        for n, r in graded.items()
        if r.get("verdict") != "on_schedule"
    }

    return {
        "read_at": read_at or _now_iso(),
        "rate_arm_ceiling_s": RATE_ARM_CEILING_S,
        "scheduled_tasks": payload.get("scheduled_tasks"),
        "graded": payload.get("graded"),
        "verdict_counts": payload.get("verdict_counts"),
        "arm_counts": payload.get("arm_counts"),
        # The census the headline number cannot express on its own.
        "above_ceiling_total": len(graded_blind) + len(unmapped_above),
        "above_ceiling_graded": len(graded_blind),
        "above_ceiling_unmapped": len(unmapped_above),
        "unmapped_total": len(unmapped),
        "unmapped_above_ceiling_tasks": unmapped_above,
        "stamp_rows": stamp_rows,
        "exceptions": exceptions,
    }


def grade_series(path: str) -> dict:
    """Grade a whole series. This is item 1's actual answer.

    Reports per stamp-armed task whether it was EVER anything but `on_schedule`,
    and whether the above-ceiling census moved across the series. A single read
    can say "everything is fine right now"; only the series can say "and it stayed
    that way", which is the claim the 24h read was asked for.
    """
    samples = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    if not samples:
        raise SystemExit(f"{path}: no samples — a series with no reads grades nothing")

    tasks: dict[str, set] = {}
    for s in samples:
        for name, row in (s.get("stamp_rows") or {}).items():
            tasks.setdefault(name, set()).add(row.get("verdict"))

    never_clean = {n: sorted(v) for n, v in tasks.items() if v != {"on_schedule"}}
    census = sorted({s.get("above_ceiling_total") for s in samples})
    covered = sorted({len(s.get("stamp_rows") or {}) for s in samples})

    span_s = None
    try:
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        t0 = datetime.strptime(samples[0]["read_at"], fmt)
        t1 = datetime.strptime(samples[-1]["read_at"], fmt)
        span_s = (t1 - t0).total_seconds()
    except (KeyError, ValueError):  # pragma: no cover - malformed series
        pass

    return {
        "series": path,
        "samples": len(samples),
        "first_read_at": samples[0].get("read_at"),
        "last_read_at": samples[-1].get("read_at"),
        "span_s": span_s,
        "span_h": None if span_s is None else round(span_s / 3600.0, 2),
        "stamp_tasks_seen": len(tasks),
        "stamp_tasks_covered_per_sample": covered,
        "stamp_tasks_ever_not_on_schedule": never_clean,
        "above_ceiling_total_values": census,
        # A census that moved is a finding either way: up means a new slow beat
        # was added and is invisible to the rate arm; down means an entry stopped
        # being graded at all, which reads as an improvement and is not one.
        "above_ceiling_stable": len(census) == 1,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="print the full record")
    ap.add_argument("--append", metavar="PATH", help="append the record to a JSONL series")
    ap.add_argument("--grade", metavar="PATH", help="grade an existing series and exit")
    ap.add_argument("--timeout", type=float, default=60.0)
    args = ap.parse_args()

    if args.grade:
        print(json.dumps(grade_series(args.grade), indent=1))
        return 0

    api = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not api or not token:
        print(
            "BAINLUCK_API and ADMIN_TOKEN must be set (`source ~/.claude/.env`).",
            file=sys.stderr,
        )
        return 2

    try:
        payload = fetch(api, token, timeout=args.timeout)
    except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError) as exc:
        # Exit 3, not 1: a read that could not happen is not a read that found a
        # problem. Gotcha #54's amendment in the exit-code direction — `1` is a
        # result, anything else is a story about the harness.
        print(f"READ FAILED (not a verdict): {exc}", file=sys.stderr)
        return 3

    record = summarise(payload)

    if args.append:
        with open(args.append, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")

    if args.json:
        print(json.dumps(record, indent=1))
        return 0

    ac = record["arm_counts"]
    print(f"read_at                 {record['read_at']}")
    print(f"scheduled / graded      {record['scheduled_tasks']} / {record['graded']}")
    print(f"verdict_counts          {record['verdict_counts']}")
    print(f"stamp arm               {ac.get('stamp')}")
    print(f"rate arm                {ac.get('rate')}")
    print(
        "above 12h ceiling       "
        f"{record['above_ceiling_total']} "
        f"({record['above_ceiling_graded']} graded by the stamp arm, "
        f"{record['above_ceiling_unmapped']} unmapped and still ungraded)"
    )
    if record["exceptions"]:
        print("exceptions:")
        for name, exc in sorted(record["exceptions"].items()):
            print(f"  {exc['verdict']:<13} {name}  ({exc['arm']} arm)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
