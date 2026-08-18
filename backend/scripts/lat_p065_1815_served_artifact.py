#!/usr/bin/env python3
"""#1815 — produce the `?stage=served` blend-ratification artifact for Alex.

LAT-P065 was ordered to produce this and could not: `?stage=served` shipped on
`program/latency-59`, which is unmerged. This script exists so the artifact is
ONE COMMAND the moment `-59` deploys, rather than a window of re-derivation.

⚠️ THE TRAP THIS SCRIPT EXISTS TO CLOSE
---------------------------------------
On any build predating `-59`, FastAPI **ignores** the unknown `stage` query
param and the endpoint answers **HTTP 200 with a complete, plausible body** —
`cache_hits.cached` populated, `comparison` populated, everything acceptance 1
tells you to check. It is the `ranked` stage wearing a `served` request's
clothes, and it is the exact distinction #1923 exists to draw.

So the FIRST assertion is ``"stage" in payload``, before `cache_hits`, before
anything. Absent => the build is too old => there is no artifact => stop.
(Gotcha #53: a 200 that answers a question nobody asked is not an answer.)

READ ORDER, which is #1815's acceptance and is enforced here in code:
  1. ``stage`` present            -> we are talking to the right build at all
  2. ``cache_hits.cached`` > 0    -> an empty cache and a neutral weight render
                                     identically; without this the artifact is
                                     meaningless (acceptance 1)
  3. ``absorbed``                 -> #1923's registered ruling-050 expectation.
                                     If ``absorbed`` is 0 on EVERY weight and
                                     EVERY card, the display chain passes
                                     ranking deltas through untouched, `ranked`
                                     was always sufficient, and `stage=served`
                                     SHOULD BE DELETED. Grade that BEFORE using
                                     the artifact — it is the cheap refutation.
  4. only then, the two columns for Alex

BOUNDS ARE NOT WIDENED. `served` is capped at 2 weights and ``limit <= 20``
(``admin_feed_config.py:182``, 400 outside it) because it runs a full Discover
build per weight. The directive asked for weights 0/0.1/0.2/0.3 at limit 25,
which would 400. This runs THREE PAIRED CALLS at limit 20 with ``0`` as the
shared control in each pair — same four weights, inside the instrument's own
bound. ``build_ms`` is reported per weight so the instrument prices itself; if
it is slow, that number is the finding, not a reason to raise the cap.

DOES NOT SET THE WEIGHT. It stays 0 until Alex rules a number (acceptance 4).
This script is read-only against production and writes only its own artifact.

Usage:
    source ~/.claude/.env
    python3 backend/scripts/lat_p065_1815_served_artifact.py \
        --out docs/audits/latency/lat-p0XX-1815-served-artifact.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

PAIRS = ["0,0.1", "0,0.2", "0,0.3"]
LIMIT = 20


def _iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _get(base: str, token: str, weights: str, timeout: float) -> tuple[bool, Any, str]:
    """Return (ok, payload, note). ok=False NEVER yields a usable payload.

    A throttled or errored request must not be mistaken for a result: the public
    API is rate limited and a throttled JSON parses as something, so every
    non-200 and every parse failure is reported as a failure with its reason
    rather than folded into an empty-ish payload.
    """
    qs = urllib.parse.urlencode(
        {"weights": weights, "limit": LIMIT, "stage": "served"}
    )
    url = f"{base}/api/admin/interestingness-side-by-side?{qs}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            if resp.status != 200:
                return False, None, f"HTTP {resp.status}"
            return True, json.loads(body), ""
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8")[:400]
        except Exception:
            pass
        return False, None, f"HTTP {exc.code}: {detail}"
    except Exception as exc:  # noqa: BLE001 - the note carries the reason
        return False, None, f"{type(exc).__name__}: {exc}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument(
        "--base",
        default=os.getenv("BAINLUCK_API", "https://api.bainluck.com"),
    )
    args = ap.parse_args()

    token = os.getenv("ADMIN_TOKEN")
    if not token:
        print("ADMIN_TOKEN unset — `source ~/.claude/.env` first", file=sys.stderr)
        return 2

    results: dict[str, Any] = {}
    for weights in PAIRS:
        started = time.time()
        ok, payload, note = _get(args.base, token, weights, args.timeout)
        wall_s = round(time.time() - started, 1)

        if not ok:
            print(f"[{weights}] REQUEST FAILED after {wall_s}s — {note}")
            if "400" in note:
                print(
                    "  A 400 here means the bound was exceeded. Do NOT widen it; "
                    "this script is already at 2 weights / limit 20."
                )
            results[weights] = {"ok": False, "note": note, "wall_s": wall_s}
            continue

        # ---- GATE 1: right build at all? (the silent-degrade trap) ----------
        if "stage" not in payload:
            print(
                f"[{weights}] 🔴 NO ARTIFACT — response has no `stage` field.\n"
                "  This build predates program/latency-59: the `stage` param was\n"
                "  IGNORED and this 200 is the `ranked` stage, not `served`.\n"
                f"  keys seen: {sorted(payload.keys())}\n"
                "  STOP. Do not treat this as the #1815 artifact."
            )
            return 1

        # ---- GATE 2: cache populated? (acceptance 1) ------------------------
        cached = ((payload.get("cache_hits") or {}).get("cached")) or 0
        if not cached:
            print(
                f"[{weights}] 🔴 NO ARTIFACT — cache_hits.cached = {cached!r}.\n"
                "  An empty interestingness cache and a genuinely neutral weight\n"
                "  render IDENTICALLY. Without a populated cache this comparison\n"
                "  cannot distinguish them (#1815 acceptance 1). STOP."
            )
            return 1

        results[weights] = {
            "ok": True,
            "wall_s": wall_s,
            "stage": payload.get("stage"),
            "cache_hits": payload.get("cache_hits"),
            "interleave_effect": payload.get("interleave_effect"),
            "registered_expectation_absorbed_gt_0": payload.get(
                "registered_expectation_absorbed_gt_0"
            ),
            "comparison": payload.get("comparison"),
            "slates": payload.get("slates"),
        }
        print(f"[{weights}] ok in {wall_s}s — cached={cached}")

    good = {w: r for w, r in results.items() if r.get("ok")}
    if not good:
        print("\n🔴 no successful call — nothing to grade.")
        return 1

    # ---- GATE 3: #1923's registered refutation branch, graded FIRST ---------
    absorbed_total = 0
    amplified_total = 0
    for r in good.values():
        for eff in (r.get("interleave_effect") or {}).values():
            if isinstance(eff, dict):
                absorbed_total += eff.get("absorbed") or 0
                amplified_total += eff.get("amplified") or 0

    if absorbed_total == 0 and amplified_total == 0:
        verdict = (
            "REFUTED — absorbed AND amplified are 0 on every weight. The display "
            "chain passed every ranking delta through untouched, `ranked` was "
            "always sufficient, and `stage=served` SHOULD BE DELETED (#1923's own "
            "registered refutation branch). Report this BEFORE using the artifact."
        )
    elif absorbed_total == 0:
        verdict = (
            f"PARTIAL — absorbed=0 but amplified={amplified_total}. Every delta "
            "that survived was magnified and none were swallowed; `served` is not "
            "redundant, but the registered expectation (absorbed > 0) did NOT hold."
        )
    else:
        verdict = (
            f"CONFIRMED — absorbed={absorbed_total}, amplified={amplified_total}. "
            "`ranked` deltas do NOT reach the page unchanged, which is exactly why "
            "a `ranked`-based weight ruling would have been made against a list no "
            "user is served."
        )

    artifact = {
        "record": "lat-p065-1815-served-artifact",
        "generated_at": _iso(),
        "base": args.base,
        "limit": LIMIT,
        "pairs": PAIRS,
        "note": (
            "Three paired calls, not one four-weight call: `served` is bounded to "
            "2 weights and limit<=20 by design. 0 is the shared control in each "
            "pair. The bound was NOT widened."
        ),
        "registered_expectation_grade": verdict,
        "absorbed_total": absorbed_total,
        "amplified_total": amplified_total,
        "weight_not_set": "The live blend weight is untouched and stays 0 until Alex rules (#1815 acceptance 4).",
        "results": results,
    }
    with open(args.out, "w") as fh:
        json.dump(artifact, fh, indent=2)

    print("\n" + "=" * 72)
    print("#1923 REGISTERED EXPECTATION:", verdict)
    print("=" * 72)
    print(f"artifact -> {args.out}")
    print("Next: build #1815's two columns from `slates`, route ONE MC to Alex")
    print("THROUGH FABLE (acceptance 3). Do NOT set the weight (acceptance 4).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
