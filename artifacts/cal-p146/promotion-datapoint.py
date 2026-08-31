#!/usr/bin/env python3
"""CAL-P146 — read the freeze window's MEASUREMENT beats, and fail if one cannot be read.

WHY THIS EXISTS
---------------
CAL-P140 built the window to answer ruling 009 (does the producer publish?) and
recorded, correctly, that *"not one beat in this window is a datapoint about the
calibration"* — every clean beat re-served the census promoted at
``2026-08-29T20:18:32Z``.

That stopped being true at beat 14 (``2026-08-30T12:24:39Z``), when the producer
promoted a NEW census unattended, under freeze. CAL-P143's handoff render counted
it -- ``MEASUREMENT  a new census was promoted, the number could move: 1`` -- and
no session has read it since. It was tallied, never opened.

When you go to open it you find the actual problem: **a promotion is only readable
if a scorecard render was banked on both sides of it.** The nearest banked render
before beat 14 is beat 8, six beats and eight hours earlier; the nearest after is
beat 16. Anything that moved across that bracket is confounded by everything else
that moved in eight hours, and the payload demonstrably drifts within a single
census (``cells_total`` 290 -> 291 between beats 6 and 8, same census).

So the window's one datapoint about the calibration is now *partly unreadable*,
for exactly the reason the directive gives about MISS beats: seen late, it is
unattributable forever. The same is true of the MEASUREMENT beat, and nobody had
written that down.

WHAT IT DOES
------------
1. Finds every MEASUREMENT beat in the window log (a ``staged_at`` transition).
2. Inventories every banked scorecard render on disk and maps it to its beat.
3. Brackets each MEASUREMENT beat with its nearest pre/post render and reports the
   bracket gap in beats.
4. Splits the reading into what SURVIVES the confound (fields identical in every
   render, so no gap can hide a move) and what does NOT (fields that moved across
   a bracket wider than ``MAX_CLEAN_BRACKET_BEATS``).
5. **Exits 4 if a MEASUREMENT beat is not cleanly bracketed** -- a datapoint that
   was counted but cannot be read is the failure this instrument exists to catch,
   and CAL-P145's lesson is that such a failure must be a non-zero exit rather
   than a paragraph.

This reads banked artifacts only. It runs no query, re-measures nothing, and
touches no frozen file.
"""

from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))  # the worktree root
WINDOW_LOG = os.path.join(ROOT, "artifacts", "cal-p140", "window-log.jsonl")
RENDER_GLOBS = ("artifacts/*/scorecard*.txt", "artifacts/*/scorecard*.json")

#: A render this many beats away from the promotion (or nearer) can bracket it.
#: 1 means "the beat either side"; anything wider admits confounds.
MAX_CLEAN_BRACKET_BEATS = 1

#: Fields whose value comes from the CAL-P128 measured-sigma LEDGER rather than
#: from the census. `calibration_scorecard._attach_measured_sigma` overlays these
#: from a file that sessions write to out of band, so a change in them across a
#: bracket is NOT evidence about the promotion. Excluded from attribution.
LEDGER_DERIVED_PREFIX = "measured_sigma."

EXIT_UNREADABLE_DATAPOINT = 4

#: Promotions whose loss is CLOSED and unrepairable, each with the reason it can
#: never be recovered. Nothing goes in here because it is inconvenient -- the
#: only admissible reason is that the render which would bracket it can no
#: longer be created by anyone.
#:
#: A NEW entry here needs that argument written out. If a promotion is merely
#: unbracketed *so far*, it is not permanent: leave it red.
PERMANENTLY_UNREADABLE = {
    14: (
        "CAL-P146 §3 — the bracket is beat 8 -> beat 16 and the confound is "
        "within-census drift between beats 8 and 13. Closing it needs a render "
        "of the payload served at beat 13 and at beat 15; both censuses have "
        "since been evicted from the 1 h serve cache and the producer cannot be "
        "asked to re-serve them (?bust=1 is gone from the public route and the "
        "admin variant QUEUES the heavy task, which would corrupt this window). "
        "No action available to any future session recovers it."
    ),
}


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def load_json_prefix(path: str) -> dict:
    """Renders are a JSON object followed by a human board; take the object."""
    with open(path) as fh:
        return json.JSONDecoder().raw_decode(fh.read())[0]


def flat(d: dict, prefix: str = "") -> dict:
    out: dict = {}
    for k, v in d.items():
        key = prefix + k
        if isinstance(v, dict):
            out.update(flat(v, key + "."))
        else:
            out[key] = v if not isinstance(v, list) else tuple(v)
    return out


def load_beats() -> list[dict]:
    with open(WINDOW_LOG) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def measurement_beats(beats: list[dict]) -> list[dict]:
    """A MEASUREMENT beat is one whose staged_at differs from its predecessor."""
    out = []
    prev = None
    for b in beats:
        staged = b.get("staged_at")
        if prev is not None and staged != prev:
            out.append(b)
        prev = staged
    return out


def inventory_renders(beats: list[dict]) -> list[dict]:
    """Every banked render, mapped to the beat it was rendered from."""
    found = []
    for pattern in RENDER_GLOBS:
        for path in glob.glob(os.path.join(ROOT, pattern)):
            try:
                obj = load_json_prefix(path)
            except Exception:
                continue  # not a scorecard render
            ga = obj.get("generated_at")
            if not ga:
                continue
            nearest = min(
                beats, key=lambda b: abs((_ts(b["generated_at"]) - _ts(ga)).total_seconds())
            )
            delta = abs((_ts(nearest["generated_at"]) - _ts(ga)).total_seconds())
            found.append(
                {
                    "path": os.path.relpath(path, ROOT),
                    "generated_at": ga,
                    "beat": nearest["n"] if delta <= 5 else None,
                    "staged_at": nearest["staged_at"] if delta <= 5 else None,
                    "obj": obj,
                }
            )
    return sorted(found, key=lambda r: r["generated_at"])


def main() -> int:
    beats = load_beats()
    renders = inventory_renders(beats)
    in_window = [r for r in renders if r["beat"] is not None]

    print("=" * 88)
    print("CAL-P146 — the freeze window's MEASUREMENT beats, and whether they can be read")
    print("=" * 88)
    print(f"beats logged: {len(beats)}   banked renders on disk: {len(renders)}   "
          f"mapped to a window beat: {len(in_window)}")

    print("\nRenders mapped into the window:")
    for r in in_window:
        print(f"   beat {r['beat']:>3}  {r['generated_at'][:23]}  census {r['staged_at'][:19]}  {r['path']}")

    mbeats = measurement_beats(beats)
    print(f"\nMEASUREMENT beats (a staged_at transition — a NEW census was promoted): {len(mbeats)}")

    unreadable = []
    for mb in mbeats:
        n = mb["n"]
        pre = [r for r in in_window if r["beat"] < n]
        post = [r for r in in_window if r["beat"] >= n]
        pre_r = pre[-1] if pre else None
        post_r = post[0] if post else None
        print(f"\n  --- beat {n}  {mb['generated_at'][:23]}")
        print(f"      promoted census : {mb['staged_at']}")
        print(f"      attribution     : {mb.get('attribution','')[:100]}")
        if not pre_r or not post_r:
            print("      🔴 NOT BRACKETED — no banked render on one side. Unreadable.")
            unreadable.append((n, "no bracket"))
            continue
        gap_pre, gap_post = n - pre_r["beat"], post_r["beat"] - n
        print(f"      bracketed by    : beat {pre_r['beat']} ({pre_r['path']})"
              f"  ->  beat {post_r['beat']} ({post_r['path']})")
        print(f"      bracket gap     : {gap_pre} beat(s) before, {gap_post} beat(s) after")

        a, b = flat(pre_r["obj"]), flat(post_r["obj"])
        keys = sorted(set(a) | set(b))
        moved = [k for k in keys if a.get(k) != b.get(k) and k != "generated_at"]
        census_moved = [k for k in moved if not k.startswith(LEDGER_DERIVED_PREFIX)]
        ledger_moved = [k for k in moved if k.startswith(LEDGER_DERIVED_PREFIX)]

        clean = gap_pre <= MAX_CLEAN_BRACKET_BEATS and gap_post <= MAX_CLEAN_BRACKET_BEATS
        if clean:
            print("      ✅ bracket is adjacent — what moved IS the promotion:")
            for k in census_moved:
                print(f"           {k:44} {a.get(k)} -> {b.get(k)}")
        else:
            print(f"      🔴 bracket is {gap_pre}+{gap_post} beats wide — what moved across it is")
            print("         CONFOUNDED with ordinary within-census drift and cannot be")
            print("         attributed to the promotion. Reported, not claimed:")
            for k in census_moved:
                print(f"           (unattributable) {k:34} {a.get(k)} -> {b.get(k)}")
            unreadable.append((n, f"bracket {gap_pre}+{gap_post} beats wide"))
        if ledger_moved:
            print("      (excluded — CAL-P128 ledger overlay, not census output:)")
            for k in ledger_moved:
                print(f"           {k:44} {a.get(k)} -> {b.get(k)}")

    # What survives regardless of bracket width: fields identical in EVERY render.
    print("\n" + "-" * 88)
    print("WHAT SURVIVES THE CONFOUND — identical in every in-window render, so no")
    print("gap can be hiding a move. This is the part of the datapoint that IS read:")
    if in_window:
        flats = [flat(r["obj"]) for r in in_window]
        common = set(flats[0])
        for f in flats[1:]:
            common &= set(f)
        stable = sorted(k for k in common
                        if k != "generated_at" and len({f[k] for f in flats}) == 1)
        for k in ("headline_mce_closing_line", "headline_ci", "headline_pass",
                  "headline_target_pp", "population_version"):
            if k in stable:
                print(f"   HELD  {k:38} = {flats[0][k]}")
        others = [k for k in stable if not k.startswith("headline") and k != "population_version"]
        print(f"   (+ {len(others)} further fields identical across all "
              f"{len(in_window)} renders)")

    print("\n" + "=" * 88)

    # CAL-P147 amendment. As written, `unreadable` accumulated EVERY measurement
    # beat including beat 14, whose loss is permanent and unrepairable -- so this
    # guard could never return to 0 again. A guard that is red forever is a guard
    # that gets ignored, and the thing it would then fail to announce is the NEXT
    # promotion being missed the same way. Beat 14 is therefore acknowledged as a
    # closed permanent loss (loudly, never silently), and the exit code is
    # reserved for a promotion that can still be saved.
    permanent = [(n, why) for n, why in unreadable if n in PERMANENTLY_UNREADABLE]
    live = [(n, why) for n, why in unreadable if n not in PERMANENTLY_UNREADABLE]

    for n, why in permanent:
        print(f"⚫ MEASUREMENT beat {n} was COUNTED and can never be READ — {why}.")
        print(f"   PERMANENT, acknowledged: {PERMANENTLY_UNREADABLE[n]}")
        print("   Not counted toward the exit code — nothing anyone does now recovers it.")
    if permanent and live:
        print()

    if live:
        for n, why in live:
            print(f"🔴 MEASUREMENT beat {n} was COUNTED but cannot be READ — {why}.")
        print()
        print("A promotion is readable only if a render is banked on the beat either side")
        print("of it. Bank one on the next MEASUREMENT beat; the rebuild stands at")
        print(f"{beats[-1].get('rebuild_units_banked')}/{beats[-1].get('units_banked')}, so the next promotion is still ahead.")
        print(f"EXIT {EXIT_UNREADABLE_DATAPOINT}")
        return EXIT_UNREADABLE_DATAPOINT

    print("No RECOVERABLE measurement beat is unread.")
    if permanent:
        print(f"({len(permanent)} permanent loss(es) above stand on the record, unrepairable.)")
    print("EXIT 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
