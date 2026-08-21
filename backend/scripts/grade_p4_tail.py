#!/usr/bin/env python3
"""Grade LAT-P079's owed **P4 TAIL** clause from the pass-ring payload.

## Why this exists, and why it is written now rather than in the window

The ≥6 h horizon read has been defeated five consecutive times, and the sixth
attempt runs under a bought deploy freeze. A protected window is the worst place
to be deciding what "post-fix" means or discovering that a field is named
something else. Everything decidable before the horizon is decided here; the
morning window only READS. Same contract as `grade_ruling_110.py`, same reason.

## What is owed

LAT-P079 §5: **P4 itself PASSED** on an attributable paired split, each ring
record stamped with its own `head_source`:

    arm         n    wall p50   wall p95   wall max   > 65 s
    POST-FIX    8    43.310     45.421     45.952     0
    PRE-FIX    24    45.117     51.981     54.047     0

🔴 **What that does NOT establish is the TAIL.** The quantity that breached the
TTL is the **66.365 s** max that set `MEASURED_WALL_MAX_S`, measured off a
32-deep ring. Neither arm above reaches it, and the post-fix arm is **n = 8**.
**A max over 8 samples cannot refute a max over 32.**

The fix is the horizon, not a new method. The ring is 32 deep, so after an
overnight freeze it is entirely post-fix and one read gives the first fully
post-fix 32-sample wall distribution that can be compared like-for-like.

## 🔴 TRAP 1 — A SAMPLED MAXIMUM IS A LOWER BOUND (ruling 075)

Four consecutive cycles have proved a prior sampled maximum too low:

    42.6  ->  53.920  ->  61.282  ->  66.365

So a post-fix max that comes in LOWER is **not** evidence the tail improved. It
is equally consistent with a smaller sample of the same distribution. This
script therefore never returns "improved". Its favourable verdict is
`NOT_REFUTED`, and it says in the same breath what would be needed to make it
mean more.

## 🔴 TRAP 2 — DO NOT LOWER THE CONSTANT ON A FAVOURABLE READ

`test_the_wall_max_exceeding_the_ttl_is_DERIVED_and_currently_TRUE` carries its
own failure message: *"if the constant was lowered to make this green, that is
the fourth instance of the stale-constant defect this test was rewritten to
end."* Lowering `MEASURED_WALL_MAX_S` on a favourable read is exactly the move
that made LAT-P075's "SAFE for the first time" retractable. This script
**never** recommends lowering it and says so in the payload it writes.

Upward is different, and upward is a same-window obligation: a post-fix max
ABOVE the pinned constant means the constant is a stale underestimate for the
fifth time, and the script exits **2** so it cannot be scrolled past.

## 🔴 THE ARM SPLIT, AND A HAZARD THIS CYCLE INTRODUCED INTO IT

The arms are keyed on `head_source`, and LAT-P080B changed what that field can
say. #2072 hour-buckets `search:trending:24h`, so for roughly the first hour
after that deploy the zset window is thin or empty and `resolve_head` returns
``db:search_query_logs:30d`` rather than ``blend:query_log+trending:...``.

**A grader that defined post-fix as "starts with `blend:`" would classify those
records as PRE-FIX and silently under-count the post-fix arm — the arm whose
sample size is the entire problem.** So post-fix is defined as *the query log is
contributing*, which is the actual content of #1866's fix, and `db:` counts.
`redis:search:trending:24h` (the old zset-only cascade) and `static_floor` are
pre-fix. Anything unrecognised is `UNKNOWN` and is never quietly folded into
either arm.

A MIXED ring is not a grade. If any pre-fix or unknown record is present the
verdict is `MIXED_RING`, because the whole purpose of the overnight horizon is a
ring that no longer needs a paired split.

## Exit codes — read the VALUE, not just non-zero (gotcha #54)

    0  graded, and nothing is owed (includes an honest NOT_REFUTED)
    1  the tail is CONFIRMED above the TTL — reportable, no constant change owed
       (the pinned constant already covers it)
    2  🔴 the pinned MEASURED_WALL_MAX_S is a STALE UNDERESTIMATE (fifth
       instance) — raise it in THIS window, with the sampling argument stated
    3  the payload could not be read, or the ring is mixed/too shallow to grade
       — a story about the instrument, never a result about the tail

## Usage

    # the morning window, live:
    source ~/.claude/.env
    python3 backend/scripts/grade_p4_tail.py --live \
        --out docs/audits/latency/lat-p080-p4-tail.json ; echo "EXIT CODE: $?"

    # offline, against a payload already captured (no production read):
    python3 backend/scripts/grade_p4_tail.py --from-file /tmp/pass-ring.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

# Constants come FROM the module they govern. Never re-typed here — a second
# copy of `MEASURED_WALL_MAX_S` is a second thing to go stale, which is the
# defect class this whole clause exists to close.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.utils.typeahead_beat_budget import (  # noqa: E402
    MEASURED_WALL_MAX_S,
    RESPONSE_CACHE_TTL_S,
    WALL_MAX_EXCEEDS_RESPONSE_TTL,
    WALL_MAX_MARGIN_S,
    wall_max_exceeds_response_ttl,
)

EXIT_OK = 0
EXIT_TAIL_CONFIRMED = 1
EXIT_CONSTANT_STALE = 2
EXIT_UNREADABLE = 3

#: The ring depth the 66.365 s max was measured over. A post-fix arm materially
#: shallower than this cannot refute it — that is the entire content of the
#: clause, so the bar is a named constant rather than a number in a branch.
BASELINE_TAIL_SAMPLES = 32

#: How much of that depth the post-fix arm must reach before its max is allowed
#: to be compared at all. 24 of 32 is a judgement, stated: it keeps a
#: three-quarter-full ring gradeable after an overnight freeze while refusing
#: the n=8 arm that made LAT-P079's split unable to speak to the tail.
MIN_TAIL_SAMPLES = 24

#: LAT-P079's post-fix arm, pinned so a later read is compared against a fixed
#: prior rather than against whatever the previous run happened to print.
LAT_P079_POST_FIX_ARM = {"n": 8, "p50": 43.310, "p95": 45.421, "max": 45.952, "over_ttl": 0}

#: The four measured maxima, in order. Each was the honest sampled maximum of
#: its day and each was later proved an underestimate. This is the sampling
#: argument, carried as data so the report can print it rather than assert it.
MAX_HISTORY_S = (42.6, 53.920, 61.282, 66.365)

#: `head_source` prefixes that mean the query log is contributing — which IS
#: #1866's fix. `db:` is included deliberately; see the module docstring.
POST_FIX_HEAD_SOURCES = ("blend:", "db:search_query_logs")

#: The pre-fix cascade: the zset alone, or the cold-start floor.
PRE_FIX_HEAD_SOURCES = ("redis:search:trending", "static_floor")


def _fetch_live() -> dict[str, Any]:
    base = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not base or not token:
        raise RuntimeError(
            "BAINLUCK_API and ADMIN_TOKEN must be set — `source ~/.claude/.env`"
        )
    req = urllib.request.Request(
        f"{base}/api/admin/typeahead-warmer/last",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def classify_arm(head_source: Any) -> str:
    """`post_fix` | `pre_fix` | `unknown`, never a silent default.

    An unrecognised source is its own answer. Folding it into either arm would
    put a record the grader does not understand into the sample whose size is
    the whole question.
    """
    if not isinstance(head_source, str) or not head_source:
        return "unknown"
    if head_source.startswith(POST_FIX_HEAD_SOURCES):
        return "post_fix"
    if head_source.startswith(PRE_FIX_HEAD_SOURCES):
        return "pre_fix"
    return "unknown"


def _stats(walls: list[float]) -> dict[str, Any]:
    """min / p50 / p95 / max over the walls, or an explicit empty shape.

    Same keys either way — `None` is "not measured" and is never rendered as
    `0.0`, which on a MAXIMUM would read as the most favourable number there is.
    """
    if not walls:
        return {"n": 0, "min": None, "p50": None, "p95": None, "max": None}
    vals = sorted(walls)
    return {
        "n": len(vals),
        "min": round(vals[0], 3),
        "p50": round(vals[len(vals) // 2], 3),
        "p95": round(vals[min(len(vals) - 1, int(round(0.95 * (len(vals) - 1))))], 3),
        "max": round(vals[-1], 3),
    }


def split_ring(payload: dict[str, Any]) -> dict[str, Any]:
    """Split the pass ring into arms, counting what is dropped and why."""
    passes = ((payload.get("passes") or {}).get("records")) or []
    arms: dict[str, list[float]] = {"post_fix": [], "pre_fix": [], "unknown": []}
    counts = {"post_fix": 0, "pre_fix": 0, "unknown": 0}
    no_wall = 0

    for rec in passes:
        arm = classify_arm(rec.get("head_source"))
        counts[arm] += 1
        wall = rec.get("seconds_wall")
        if isinstance(wall, (int, float)):
            arms[arm].append(float(wall))
        else:
            # Counted, not dropped silently: a record with no wall is a record
            # the tail cannot see, and an unexplained shortfall in n is exactly
            # what a reader would otherwise attribute to the freeze.
            no_wall += 1

    return {
        "records_total": len(passes),
        "arm_counts": counts,
        "records_without_a_wall": no_wall,
        "post_fix": _stats(arms["post_fix"]),
        "pre_fix": _stats(arms["pre_fix"]),
        "unknown": _stats(arms["unknown"]),
        "post_fix_walls_over_response_ttl": sum(
            1 for w in arms["post_fix"] if w > RESPONSE_CACHE_TTL_S
        ),
    }


def grade_tail(payload: dict[str, Any]) -> dict[str, Any]:
    """The P4 tail clause, graded three-valued and never as 'improved'."""
    status = payload.get("status")
    split = split_ring(payload)
    post = split["post_fix"]
    counts = split["arm_counts"]

    base: dict[str, Any] = {
        "clause": "P4-tail",
        "claim": (
            "on a FULLY post-fix ring at least "
            f"{MIN_TAIL_SAMPLES} deep, does the pass wall still exceed the "
            f"{RESPONSE_CACHE_TTL_S}s response-cache TTL?"
        ),
        "payload_status": status,
        "ring_split": split,
        "pinned": {
            "measured_wall_max_s": MEASURED_WALL_MAX_S,
            "wall_max_margin_s": WALL_MAX_MARGIN_S,
            "response_cache_ttl_s": RESPONSE_CACHE_TTL_S,
            "wall_max_exceeds_response_ttl": WALL_MAX_EXCEEDS_RESPONSE_TTL,
            "baseline_tail_samples": BASELINE_TAIL_SAMPLES,
            "lat_p079_post_fix_arm": LAT_P079_POST_FIX_ARM,
            "max_history_s": list(MAX_HISTORY_S),
        },
        "never_recommend": (
            "LOWERING MEASURED_WALL_MAX_S. A sampled maximum is a LOWER BOUND "
            f"(ruling 075) and this program has raised it four times "
            f"({' -> '.join(str(m) for m in MAX_HISTORY_S)}). A lower read is "
            "consistent with a smaller sample of the same distribution."
        ),
    }

    if status != "ok":
        return {
            **base,
            "verdict": "UNREADABLE",
            "reason": (
                f"pass-ring status is {status!r} — we learned nothing. "
                "'unreadable' and 'no_data' are different facts and neither is "
                "a tail measurement (gotcha #53)."
            ),
        }

    if counts["pre_fix"] or counts["unknown"]:
        return {
            **base,
            "verdict": "MIXED_RING",
            "reason": (
                f"{counts['pre_fix']} pre-fix and {counts['unknown']} unknown "
                f"record(s) beside {counts['post_fix']} post-fix. The overnight "
                "horizon exists to produce a ring that needs no paired split; a "
                "mixed ring means the horizon has not been reached, NOT that "
                "the tail is unchanged. Re-read later — do not grade a split."
            ),
        }

    if post["n"] < MIN_TAIL_SAMPLES:
        return {
            **base,
            "verdict": "INSUFFICIENT_SAMPLES",
            "reason": (
                f"post-fix arm is n={post['n']}, under the {MIN_TAIL_SAMPLES} "
                f"needed to speak to a maximum measured over "
                f"{BASELINE_TAIL_SAMPLES}. This is LAT-P079's n=8 problem "
                "unchanged: a max over a short sample cannot refute a max over "
                "a long one, in either direction."
            ),
        }

    post_max = float(post["max"])
    still_exceeds = wall_max_exceeds_response_ttl(post_max, float(RESPONSE_CACHE_TTL_S))

    if post_max > MEASURED_WALL_MAX_S:
        return {
            **base,
            "verdict": "CONSTANT_STALE",
            "still_exceeds_ttl": still_exceeds,
            "reason": (
                f"🔴 post-fix wall max {post_max:.3f}s EXCEEDS the pinned "
                f"MEASURED_WALL_MAX_S {MEASURED_WALL_MAX_S}s over n={post['n']} "
                "— the fifth instance of the stale-constant defect. Raise the "
                "constant THIS window with the sampling argument stated, and "
                "re-derive WALL_MAX_MARGIN_S rather than carrying it forward."
            ),
        }

    if still_exceeds:
        return {
            **base,
            "verdict": "TAIL_CONFIRMED_OVER_TTL",
            "still_exceeds_ttl": True,
            "reason": (
                f"post-fix wall max {post_max:.3f}s over n={post['n']} still "
                f"exceeds the {RESPONSE_CACHE_TTL_S}s TTL, and sits under the "
                f"pinned {MEASURED_WALL_MAX_S}s. "
                "`WALL_MAX_EXCEEDS_RESPONSE_TTL` stays TRUE; the live 10s beat "
                "stays MARGINAL. No constant change owed."
            ),
        }

    return {
        **base,
        "verdict": "NOT_REFUTED",
        "still_exceeds_ttl": False,
        "reason": (
            f"post-fix wall max {post_max:.3f}s over n={post['n']} does not "
            f"reach the {RESPONSE_CACHE_TTL_S}s TTL, and "
            f"{split['post_fix_walls_over_response_ttl']} of {post['n']} walls "
            "are over it. 🔴 THIS IS NOT 'THE TAIL IMPROVED'. A sampled maximum "
            "is a lower bound; four prior maxima were each proved too low. What "
            "would make it mean more: a second independent fully-post-fix ring "
            "at the same depth agreeing, or a wall bound that is derived rather "
            "than sampled. `MEASURED_WALL_MAX_S` is NOT lowered on this read."
        ),
    }


def build_report(payload: dict[str, Any]) -> dict[str, Any]:
    grade = grade_tail(payload)
    return {
        "clause": "LAT-P079 P4 tail",
        "issue": 1866,
        "verdict": grade["verdict"],
        "grade": grade,
    }


def exit_code_for(verdict: str) -> int:
    if verdict == "CONSTANT_STALE":
        return EXIT_CONSTANT_STALE
    if verdict == "TAIL_CONFIRMED_OVER_TTL":
        return EXIT_TAIL_CONFIRMED
    if verdict in ("UNREADABLE", "MIXED_RING", "INSUFFICIENT_SAMPLES"):
        return EXIT_UNREADABLE
    return EXIT_OK


def render(report: dict[str, Any]) -> str:
    g = report["grade"]
    split = g["ring_split"]
    post = split["post_fix"]
    lines = [
        "LAT-P079 P4 TAIL CLAUSE",
        f"  verdict : {g['verdict']}",
        f"  reason  : {g['reason']}",
        f"  arms    : post_fix={split['arm_counts']['post_fix']} "
        f"pre_fix={split['arm_counts']['pre_fix']} "
        f"unknown={split['arm_counts']['unknown']} "
        f"(no wall: {split['records_without_a_wall']})",
        f"  post-fix: n={post['n']} p50={post['p50']} p95={post['p95']} "
        f"max={post['max']} over_ttl={split['post_fix_walls_over_response_ttl']}",
        f"  pinned  : MEASURED_WALL_MAX_S={MEASURED_WALL_MAX_S} "
        f"TTL={RESPONSE_CACHE_TTL_S} "
        f"WALL_MAX_EXCEEDS_RESPONSE_TTL={WALL_MAX_EXCEEDS_RESPONSE_TTL}",
        f"  NEVER   : {g['never_recommend']}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--live", action="store_true", help="read production")
    src.add_argument("--from-file", help="a captured payload; no production read")
    ap.add_argument("--out", help="write the JSON report here")
    args = ap.parse_args(argv)

    try:
        if args.live:
            payload = _fetch_live()
        else:
            with open(args.from_file) as fh:
                payload = json.load(fh)
    except (OSError, ValueError, RuntimeError, urllib.error.URLError) as exc:
        print(f"UNREADABLE: {exc}", file=sys.stderr)
        return EXIT_UNREADABLE

    report = build_report(payload)
    print(render(report))
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as fh:
            json.dump(report, fh, indent=2, sort_keys=True)
        print(f"\nwrote {args.out}")
    return exit_code_for(report["verdict"])


if __name__ == "__main__":
    raise SystemExit(main())
