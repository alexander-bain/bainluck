#!/usr/bin/env python3
"""Rotate the rolling `.claude/handoff/` reports: entries older than N days move out.

Windows read the tails of these files at startup. `CODEX-REPORT.md` reached **3.0 MB**,
which is why windows began compacting mid-queue. Rotation keeps the live file at the
last 7 days, moves older entries to `archive/rolling/<STEM>-pre-<CUT>.md`, and leaves a
one-line index at the top saying what left and where it went.

Committed rather than run ad hoc, because the first version of this lived in `/tmp` and
a check that exists only in a report gets re-derived from scratch or, more likely, not
run at all.

THREE THINGS THIS GETS RIGHT THAT THE OBVIOUS VERSION DOES NOT

1.  **Age is the entry's own date, never its position in the file.** Three of the five
    files are not chronologically ordered. `PROGRAM-CALIBRATION-REPORT.md` runs CAL-P084
    -> P076 *descending* and then P081 -> P090 *ascending*; `INTEGRATOR-REPORT.md`
    prepends at the top and appends at the bottom; `PROGRAM-CALIBRATION-QUEUE.md` is
    newest-first throughout. "Cut the first N lines" archives the NEW half of two of them.
    An undated `##` subsection inherits the date of the window that opened above it, so it
    travels with its parent instead of being stranded in the live file after the parent
    leaves. An entry that can be dated by nothing at all is KEPT.

2.  **Every one of these files is owned by a live lane.** Read, compute, then RE-READ
    before writing and require the new bytes to be a pure suffix of what was read,
    carrying that delta into the tail. Without it an entry appended mid-rotation is
    silently dropped. A lane that instead rewrites the whole file from a stale copy merely
    reverts the rotation, which is the benign direction: nothing is lost, re-run.

3.  **It verifies conservation and says the number.** Every entry heading present before
    must be present in the live file or the archive after. `--apply` prints the count.

A file that rotates to nothing is not a failure: the calibration lane runs ~5 windows a
day, so all of `PROGRAM-CALIBRATION-REPORT.md` legitimately falls inside 7 days.

USAGE

    python3 scripts/rotate_rolling_handoff_reports.py              # dry run
    python3 scripts/rotate_rolling_handoff_reports.py --apply
    python3 scripts/rotate_rolling_handoff_reports.py --days 14 --apply

Exit codes (gotcha #54): `0` ok, `1` a rotation lost content or aborted on a non-append
concurrent write -- a real result, `2` the rotation could not be performed at all.
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")

# filename -> regex matching the line that OPENS an entry.
#
# Explicit per file rather than "any heading": these files interleave real window
# entries with sub-headings, and splitting on every `##` turns one window's report into
# a dozen fragments that then rotate independently of each other.
SPECS: dict[str, str] = {
    "CODEX-REPORT.md": r"^## CODEX run ",
    "PROGRAM-UX-REPORT.md": r"^#{1,2} .*UX-P\d",
    "PROGRAM-CALIBRATION-REPORT.md": r"^# .*CAL-P\d",
    "PROGRAM-CALIBRATION-QUEUE.md": r"^#{1,2} .*CAL-P\d",
    "INTEGRATOR-REPORT.md": r"^#{1,2} .*INT-\d",
}


def parse(text: str, boundary: str):
    """-> (preamble_lines, [entry]) where entry = {head, body, date}."""
    bre = re.compile(boundary)
    lines = text.split("\n")
    starts = [i for i, line in enumerate(lines) if bre.match(line)]
    if not starts:
        return lines, []

    preamble = lines[: starts[0]]
    entries = []
    inherited: datetime.date | None = None

    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        body = lines[start:end]
        match = DATE_RE.search("\n".join(body))
        own: datetime.date | None = None
        if match:
            try:
                own = datetime.date.fromisoformat(match.group(1))
            except ValueError:
                own = None
        if own is None:
            date = inherited  # a subsection belongs to the window above it
        else:
            date = inherited = own
        entries.append({"head": lines[start], "body": body, "date": date})

    return preamble, entries


def rotate(handoff: Path, name: str, cut: datetime.date, today: datetime.date, apply: bool) -> int:
    """-> 0 ok / 1 content lost or aborted."""
    live = handoff / name
    if not live.is_file():
        print(f"=== {name}\n    absent — skipped\n")
        return 0

    before = live.read_text(encoding="utf-8", errors="replace")
    preamble, entries = parse(before, SPECS[name])
    old = [e for e in entries if e["date"] and e["date"] < cut]
    keep = [e for e in entries if not (e["date"] and e["date"] < cut)]

    kept_bytes = sum(len("\n".join(e["body"])) + 1 for e in keep)
    print(f"=== {name}")
    print(f"    {len(before) / 1024:>7.0f}K  {len(entries)} entries   "
          f"ARCHIVE {len(old)}  KEEP {len(keep)}")

    if not old:
        print(f"    NO ROTATION — nothing here predates {cut}. Left untouched.\n")
        return 0

    dates = sorted(e["date"] for e in old)
    stem = name[:-3]
    arch_name = f"{stem}-pre-{cut}.md"
    arch_path = handoff / "archive" / "rolling" / arch_name
    print(f"    archived {dates[0]} .. {dates[-1]}   live -> {kept_bytes / 1024:.0f}K")

    header = [
        f"# {stem} — archived bodies, everything dated before {cut}",
        "",
        f"Rotated out of `.claude/handoff/{name}` on {today}. Windows read the tails of these "
        "files at startup, and a multi-megabyte rolling file forces mid-queue context compaction.",
        "",
        f"{len(old)} entries, {dates[0]} .. {dates[-1]}. Ordering is exactly as it stood in the "
        "live file — these files are not uniformly chronological, so this is the original order, "
        "not a sort. Nothing was edited; this is a move.",
        "",
        "**Line-number citations.** Other handoff docs cite the live file by line. Any such "
        "citation written before this rotation now points into THIS file, and the offsets no "
        "longer match either, because the live file's remaining entries shifted up. Resolve by "
        "the section heading, not the number. Cite the run/cycle id in future — it survives "
        "rotation; a line number does not.",
        "",
        "---",
        "",
    ]
    arch_lines = header + [line for e in old for line in e["body"]]

    index = (
        f"> **ROTATED {today}** — {len(old)} entries dated {dates[0]}..{dates[-1]} "
        f"({len(before) / 1024:.0f}K → {kept_bytes / 1024:.0f}K) moved to "
        f"`archive/rolling/{arch_name}`. This file is the last "
        f"{(today - cut).days} days."
    )
    new_text = "\n".join([index, ""] + preamble + [l for e in keep for l in e["body"]])

    if not apply:
        print("    (dry run)\n")
        return 0

    arch_path.parent.mkdir(parents=True, exist_ok=True)
    arch_path.write_text("\n".join(arch_lines), encoding="utf-8")

    # A live lane may have appended between the read above and this moment.
    after = live.read_text(encoding="utf-8", errors="replace")
    delta = ""
    if after != before:
        if not after.startswith(before):
            print("    🔴 ABORT — the file changed in a way that is not a pure append. "
                  "Nothing written. Re-run when the lane is idle.")
            arch_path.unlink()
            return 1
        delta = after[len(before):]
        print(f"    ⚠️  a live lane appended {len(delta)} B mid-rotation — carried into the tail")

    tmp = live.with_suffix(".md.rotating")
    tmp.write_text(new_text + delta, encoding="utf-8")
    os.replace(tmp, live)

    now_live = live.read_text(encoding="utf-8", errors="replace")
    now_arch = arch_path.read_text(encoding="utf-8", errors="replace")
    missing = [e["head"] for e in entries if e["head"] not in now_live and e["head"] not in now_arch]
    print(f"    live {len(now_live) / 1024:.0f}K + archive {len(now_arch) / 1024:.0f}K   "
          f"headings verified {len(entries) - len(missing)}/{len(entries)}")
    if missing:
        print(f"    🔴 {len(missing)} HEADINGS LOST: {missing[:5]}")
        return 1
    print("    ✅ conserved\n")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--handoff", default=str(REPO / ".claude" / "handoff"))
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--today", default=None, help="ISO date; defaults to the system date")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    handoff = Path(args.handoff)
    if not handoff.is_dir():
        print(f"🔴 CANNOT ROTATE — no handoff directory at {handoff}", file=sys.stderr)
        return 2

    today = datetime.date.fromisoformat(args.today) if args.today else datetime.date.today()
    cut = today - datetime.timedelta(days=args.days)

    print(f"handoff={handoff}  today={today}  cut={cut} ({args.days}d)  "
          f"{'APPLY' if args.apply else 'DRY RUN'}\n")

    bad = sum(rotate(handoff, name, cut, today, args.apply) for name in SPECS)
    if bad:
        print(f"🔴 {bad} file(s) failed to rotate cleanly")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
