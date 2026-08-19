"""Pool boring-rate censuses across DAYS — the question cycle 99 could not answer.

WHY THIS IS A SEPARATE INSTRUMENT AND NOT A BIGGER `--reads`.

`census_boring_rate.py` answers "what is the rate right now", over one window,
and it is careful about it: it dedupes builds by CONTENT, names every excluded
read, and refuses a rate over an empty population. What it cannot do is answer
Fable's actual question — *does 5% hold across DAYS* — because three builds in
one evening are three samples of one evening, and cycle 99 said so in its own
words: three builds ruled out an unlucky build, nothing more.

Stretching `--spacing` does not fix that. A 24-hour run is one process holding
one HTTP client against a production endpoint for a day, which is a load
commitment (ruling 096: a window that polls production OWNS the load it
creates) and dies with the window. The right shape is many short censuses,
banked as artifacts, pooled afterwards. This file is the pooling.

THREE WAYS POOLING LIES, AND WHAT IS DONE ABOUT EACH.

1. **Double-counting one build.** Two censuses run back to back read the same
   build; yesterday's pass 2 and today's pass 1 can too, if the feed is stale.
   Fingerprints are therefore deduped GLOBALLY across every input file, not
   per file. A build seen twice is one sample, and the pooled denominator says
   so.

2. **Grouping by the wrong midnight.** Every timestamp in a census artifact is
   UTC. Cycle 99's two passes are stamped `2026-08-19T04:38Z` and
   `2026-08-19T05:56Z` — the SAME UTC date as a census run at midday Pacific
   on 2026-08-19, and a different Pacific date (they are the evening of the
   18th). Grouped by UTC, "two days" silently becomes one, the tool reports a
   pooled rate over what it calls a single day, and the multi-day question
   answers itself wrongly. Grouping is therefore in **America/Los_Angeles**,
   and the report names the zone it grouped by rather than leaving the reader
   to assume.

3. **A pooled rate that is really one day.** A "multi-day" verdict computed
   from inputs that all land on one Pacific date is not a weaker answer, it is
   the wrong answer to a different question. This tool REFUSES it: exit **2**,
   the could-not-check code (gotcha #54's amendment), never exit 0 with a
   number attached.

Read-only. Consumes artifacts. Makes no network calls.

Usage:
    python3 backend/scripts/boring_rate_across_days.py a.json b.json c.json
    python3 backend/scripts/boring_rate_across_days.py --out /tmp/pooled.json *.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

# The zone the product's own reports are written in, and the zone a "day" means
# to the person asking whether the rate held across days.
REPORT_TZ = ZoneInfo("America/Los_Angeles")
TZ_NAME = "America/Los_Angeles"


class PoolRefusal(Exception):
    """A pooled number that would be a lie. Raised, never returned as a rate."""


def _pt_date(iso_utc: str) -> str:
    """UTC stamp -> Pacific calendar date. See reason 2 in the module docstring."""
    return (
        datetime.fromisoformat(iso_utc).astimezone(REPORT_TZ).date().isoformat()
    )


def load_census(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if "samples" not in payload:
        raise PoolRefusal(
            f"{path}: not a census artifact (no `samples` key). "
            "This tool pools census_boring_rate.py output, nothing else."
        )
    return payload


def countable_samples(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """The same exclusions the census itself applies, re-applied here.

    Deliberately NOT read off the artifact's `summary`: the summary already
    deduped WITHIN its own file, and pooling needs the raw samples so it can
    dedupe ACROSS files. Re-deriving from `samples` also means an artifact
    written by an older version of the census — before some exclusion existed
    — is filtered by today's rules rather than yesterday's.
    """
    out = []
    for s in payload.get("samples", []):
        if not s.get("ok"):
            continue
        if s.get("degraded_reason"):
            continue
        if s.get("short_window"):
            continue
        if not s.get("window_fingerprint"):
            continue
        out.append(s)
    return out


def pool(paths: list[Path]) -> dict[str, Any]:
    per_day: dict[str, dict[str, Any]] = {}
    seen_builds: dict[str, str] = {}  # fingerprint -> the day that first claimed it
    cross_day_repeats: list[dict[str, str]] = []
    same_day_repeats = 0
    sources: list[dict[str, Any]] = []

    for path in sorted(paths):
        payload = load_census(path)
        samples = countable_samples(payload)
        raw = payload.get("samples", [])
        sources.append(
            {
                "file": str(path),
                "samples_total": len(raw),
                "samples_countable": len(samples),
                "first_at": raw[0]["at"] if raw else None,
                "last_at": raw[-1]["at"] if raw else None,
            }
        )
        for s in samples:
            day = _pt_date(s["at"])
            bucket = per_day.setdefault(
                day,
                {
                    "builds": 0,
                    "cards_graded": 0,
                    "boring_cards": 0,
                    "boring_names": {},
                    "boring_reasons": {},
                    "served_slots": 0,
                    "served_boring": 0,
                    "served_available": 0,
                    "windows": [],
                },
            )
            fp = s["window_fingerprint"]
            if fp in seen_builds:
                if seen_builds[fp] == day:
                    same_day_repeats += 1
                else:
                    # A build straddling midnight, or a feed so stale the same
                    # cards served on two days. Counting it twice would invent
                    # a sample; naming it is how the reader knows it happened.
                    cross_day_repeats.append(
                        {"fingerprint": fp, "first_day": seen_builds[fp], "also_on": day}
                    )
                continue
            seen_builds[fp] = day
            bucket["builds"] += 1
            bucket["cards_graded"] += s["window_size"]
            bucket["boring_cards"] += s["boring_count"]
            bucket["windows"].append(s["at"])
            if s.get("served_window_size") is not None:
                bucket["served_available"] += 1
                bucket["served_slots"] += s["served_window_size"]
                bucket["served_boring"] += s.get("served_boring_count", 0)
            for b in s.get("boring", []):
                name = b.get("name") or "?"
                bucket["boring_names"][name] = bucket["boring_names"].get(name, 0) + 1
                # Names rotate; classes do not. See `boring_reasons_every_day`.
                for reason in b.get("reasons") or ["?"]:
                    bucket["boring_reasons"][reason] = (
                        bucket["boring_reasons"].get(reason, 0) + 1
                    )

    if not per_day:
        raise PoolRefusal(
            "zero countable builds across every input — nothing to pool. "
            "A rate over no population is the failure this whole family of "
            "tools exists to refuse (gotcha #53)."
        )
    if len(per_day) < 2:
        only = next(iter(per_day))
        raise PoolRefusal(
            f"every countable build lands on ONE Pacific day ({only}). "
            "A multi-day rate cannot be computed from a single day, and "
            "reporting the pooled number anyway would answer a question "
            "nobody asked. Bank another census on a different day, then "
            "re-run. (If the inputs LOOK like different days, check the "
            "timestamps: census artifacts are stamped UTC, and an evening "
            "Pacific run carries the NEXT UTC date.)"
        )

    for day, bucket in per_day.items():
        bucket["rate"] = (
            None
            if bucket["cards_graded"] == 0
            else round(bucket["boring_cards"] / bucket["cards_graded"], 4)
        )
        bucket["boring_names"] = dict(
            sorted(bucket["boring_names"].items(), key=lambda kv: -kv[1])
        )
        bucket["boring_reasons"] = dict(
            sorted(bucket["boring_reasons"].items(), key=lambda kv: -kv[1])
        )

    graded = sum(b["cards_graded"] for b in per_day.values())
    boring = sum(b["boring_cards"] for b in per_day.values())
    rates = [b["rate"] for b in per_day.values() if b["rate"] is not None]
    all_names: set[str] = set()
    for b in per_day.values():
        all_names |= set(b["boring_names"])
    persistent = sorted(
        n for n in all_names
        if all(n in b["boring_names"] for b in per_day.values())
    )
    # A DATED card ("… close above $540 on August 19?") is a new name every
    # morning, so a per-NAME persistence check reports the whole dated-ladder
    # class as rotation and understates a defect that is in fact standing.
    # The reason set is what does not rotate.
    all_reasons: set[str] = set()
    for b in per_day.values():
        all_reasons |= set(b["boring_reasons"])
    persistent_reasons = sorted(
        r for r in all_reasons
        if all(r in b["boring_reasons"] for b in per_day.values())
    )

    # The served window is only in artifacts written after the census learned to
    # measure it. A pool over SOME of the builds is not a smaller sample of the
    # same thing — it is a different population wearing the same label — so it
    # is reported as unavailable rather than partially computed.
    builds_total = sum(b["builds"] for b in per_day.values())
    served_builds = sum(b["served_available"] for b in per_day.values())
    if served_builds == builds_total and builds_total:
        served_slots = sum(b["served_slots"] for b in per_day.values())
        served_boring = sum(b["served_boring"] for b in per_day.values())
        served_block = {
            "available": True,
            "window": "served_top20",
            "slots_graded": served_slots,
            "boring_cards": served_boring,
            "rate": None if served_slots == 0 else round(served_boring / served_slots, 4),
        }
    else:
        served_block = {
            "available": False,
            "reason": (
                f"{served_builds} of {builds_total} countable builds carry a "
                "served-window measurement; the rest predate it. A partial pool "
                "would be a different population under the same label."
            ),
        }

    return {
        "grouped_by_timezone": TZ_NAME,
        "days": len(per_day),
        # Every number under `pooled` is the LEGACY futures-only window, named
        # so a reader never has to guess which of the two it is holding.
        "window": "futures_only_top20",
        "served_window": served_block,
        "per_day": dict(sorted(per_day.items())),
        "pooled": {
            "builds": sum(b["builds"] for b in per_day.values()),
            "cards_graded": graded,
            "boring_cards": boring,
            "rate": None if graded == 0 else round(boring / graded, 4),
        },
        "spread_across_days": {
            "min_rate": min(rates) if rates else None,
            "max_rate": max(rates) if rates else None,
        },
        # A card boring on EVERY day is a standing defect; a card boring on one
        # day is a rotation. The distinction is the point of reading days.
        "boring_on_every_day": persistent,
        "boring_reasons_every_day": persistent_reasons,
        "deduped": {
            "same_day_repeat_builds": same_day_repeats,
            "cross_day_repeat_builds": cross_day_repeats,
        },
        "sources": sources,
    }


def render(result: dict[str, Any]) -> str:
    lines = ["=" * 72, "BORING-RATE@20 — POOLED ACROSS DAYS", "=" * 72]
    lines.append(f"grouped by calendar day in {result['grouped_by_timezone']}")
    lines.append(
        f"window: {result['window']}  "
        f"([SUPPLY — the pool the floor screens]; ruling 100)"
    )
    sw = result["served_window"]
    if sw.get("available"):
        pct = "n/a" if sw["rate"] is None else f"{100 * sw['rate']:.2f}%"
        lines.append(
            f"SERVED window [the target — what the visitor scrolls]: "
            f"{sw['boring_cards']}/{sw['slots_graded']} = {pct}"
        )
    else:
        lines.append(f"SERVED window [the target]: NOT POOLED — {sw['reason']}")
    lines.append("")
    for day, b in result["per_day"].items():
        pct = "n/a" if b["rate"] is None else f"{100 * b['rate']:.2f}%"
        lines.append(
            f"  {day}   {b['boring_cards']:>3}/{b['cards_graded']:<4} = {pct:<7}"
            f"  over {b['builds']} distinct build(s)"
        )
        for name, n in b["boring_names"].items():
            lines.append(f"             - {name}  (x{n})")
    p = result["pooled"]
    pct = "n/a" if p["rate"] is None else f"{100 * p['rate']:.2f}%"
    lines.append("")
    lines.append(
        f"  POOLED  {p['boring_cards']}/{p['cards_graded']} = {pct}"
        f"  over {p['builds']} distinct builds, {result['days']} days"
    )
    spread = result["spread_across_days"]
    if spread["min_rate"] is not None:
        lines.append(
            f"  per-day spread: {100 * spread['min_rate']:.2f}% – "
            f"{100 * spread['max_rate']:.2f}%"
        )
    if result["boring_on_every_day"]:
        lines.append("")
        lines.append("  boring on EVERY day (a standing defect, not rotation):")
        for name in result["boring_on_every_day"]:
            lines.append(f"    - {name}")
    if result["boring_reasons_every_day"]:
        lines.append("")
        lines.append(
            "  reasons present on EVERY day (the class persists even where the "
            "card name rotates):"
        )
        for reason in result["boring_reasons_every_day"]:
            lines.append(f"    - {reason}")
    dd = result["deduped"]
    lines.append("")
    lines.append(
        f"  deduped: {dd['same_day_repeat_builds']} same-day repeat build(s), "
        f"{len(dd['cross_day_repeat_builds'])} cross-day"
    )
    for r in dd["cross_day_repeat_builds"]:
        lines.append(
            f"    build {r['fingerprint']} served on {r['first_day']} AND {r['also_on']}"
        )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("census", nargs="+", help="census_boring_rate.py JSON artifacts")
    ap.add_argument("--out", help="write the pooled result as JSON")
    args = ap.parse_args()

    paths = [Path(p) for p in args.census]
    missing = [p for p in paths if not p.exists()]
    if missing:
        print(f"REFUSED: missing input(s): {', '.join(str(m) for m in missing)}")
        return 2

    try:
        result = pool(paths)
    except PoolRefusal as exc:
        # Exit 2, not 1: nothing failed a check, the check could not be run.
        print(f"REFUSED — no pooled rate produced.\n  {exc}")
        return 2

    print(render(result))
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2))
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
