#!/usr/bin/env python3
"""Board-drift sentinel — the LOCAL rail (#1878).

Why local and not a Celery beat, decided at the start rather than at gate time
(the spec's explicit warning): ``.claude/handoff/`` is **gitignored, absent
from the Heroku dyno, and absent from an Actions checkout**. Conditions (a),
(b), (d) and (e) read those files, so they can only ever be computed on the
machine where the lanes run. Shipping this as a beat would produce a task that
reports ``checked: 0`` forever — a green empty pass, which is the precise
failure mode #1147 and gotcha #53 are about, rebuilt on purpose.

So: this script reads, ``app/utils/board_drift`` decides, and nothing here
holds judgment. That split is what lets the six conditions be unit-tested in
CI against the 2026-08-11 state they were written for, on a runner that has no
handoff directory at all.

**It never mutates.** No renaming files, no moving cards, no editing CHAIN.md.
A sentinel that writes is a second writer in a single-writer-lock directory.

Usage
-----
    python3 scripts/board_drift_sentinel.py            # report only
    python3 scripts/board_drift_sentinel.py --file-issues
    python3 scripts/board_drift_sentinel.py --json

Intended invocation is ``night.sh`` or a launchd timer at 07:30 UTC — after
Grid (07:25) and Flow (07:10), so the morning verdicts read as one batch.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.board_drift import (  # noqa: E402
    condition_a_orphan_staged_queues,
    condition_b_dead_promotes_after,
    condition_c_stale_ready_items,
    condition_d_chain_row_file_mismatch,
    condition_e_prose_only_disposition,
    condition_f_over_age_held_rows,
    summarise,
)

HANDOFF = Path(__file__).resolve().parents[2] / ".claude" / "handoff"

_CONDITION_TITLES = {
    "a": "staged queues absent from CHAIN.md",
    "b": "queue gates pointing at a dead queue",
    "c": "stale Ready-column items",
    "d": "chain rows whose file no longer holds that queue",
    "e": "dispositions recorded in prose but not in the filename",
    "f": "HELD rows past their escalation age",
}

#: `| **341** | Items ... | gate | held since | **6** 🔴 |`
_HELD_ROW_RE = re.compile(
    r"^\|\s*\*\*(?P<queue>[^*|]+)\*\*\s*\|\s*(?P<item>[^|]{0,80})\|.*?\|"
    r"[^|]*\|\s*\*{0,2}(?P<age>\d+)\*{0,2}\s*[^|]*\|\s*$",
    re.MULTILINE)


def _read(path: Path) -> str:
    try:
        return path.read_text()
    except OSError:
        return ""


def parse_held_rows(chain_text: str) -> list[tuple[str, int]]:
    """``(label, age_in_windows)`` from the HELD table.

    Rows whose age cell is not a bare integer (``—`` for a discharged row) are
    skipped rather than coerced to 0 — a discharged row is not a zero-age row,
    and reading it as one would quietly shrink the denominator.
    """
    section = chain_text.split("## ⏸️ HELD ITEMS", 1)
    if len(section) < 2:
        return []
    body = section[1].split("\n## ", 1)[0]
    rows = []
    for m in _HELD_ROW_RE.finditer(body):
        label = f"{m.group('queue').strip()} {m.group('item').strip()}".strip()
        rows.append((label[:90], int(m.group("age"))))
    return rows


def parse_chain_rows(chain_text: str) -> list[tuple[str, str]]:
    """``(queue_id, filename)`` for chain rows that name a staged file."""
    rows = []
    for m in re.finditer(r"`(QUEUE-STAGED-[A-Za-z0-9._-]+\.md)`", chain_text):
        filename = m.group(1)
        line_start = chain_text.rfind("\n", 0, m.start()) + 1
        line = chain_text[line_start:m.start()]
        qid = re.search(r"\*{0,2}(\d{2,4}[A-Z]?)\*{0,2}", line)
        if qid:
            rows.append((qid.group(1), filename))
    return rows


def collect() -> dict:
    if not HANDOFF.is_dir():
        return summarise([])  # every condition `unknown`, never a pass

    filenames = [p.name for p in HANDOFF.iterdir() if p.is_file()]
    chain = _read(HANDOFF / "CHAIN.md")
    queue_files = {
        n: _read(HANDOFF / n) for n in filenames
        if n.startswith(("QUEUE-STAGED-", "QUEUE.md", "QUEUE-NEXT"))
    }

    # A queue id is DEAD if its file is resolved-by-filename or absent.
    live_ids = set()
    for name, text in queue_files.items():
        m = re.search(r"^queue_id:\s*(\S+)", text or "", re.MULTILINE)
        if m and not any(s in name for s in (".consumed", ".superseded", ".promoted")):
            live_ids.add(m.group(1).strip())
    referenced = {
        m.group(1) for t in queue_files.values()
        for m in re.finditer(r"^promotes-after:\s*(\S+)", t or "", re.MULTILINE)
    }
    dead_ids = {r.strip("`\"'") for r in referenced} - live_ids

    results = [
        condition_a_orphan_staged_queues(filenames, chain),
        condition_b_dead_promotes_after(queue_files, dead_ids),
        condition_c_stale_ready_items(_ready_items()),
        condition_d_chain_row_file_mismatch(parse_chain_rows(chain), queue_files),
        condition_e_prose_only_disposition(chain, filenames),
        condition_f_over_age_held_rows(parse_held_rows(chain)),
    ]
    out = summarise(results)
    out["generated_at"] = datetime.now(timezone.utc).isoformat()
    out["handoff_dir"] = str(HANDOFF)
    return out


def _ready_items() -> list[tuple[str, int]]:
    """Ready-column items as ``(label, age_days)``, or [] if gh is unavailable.

    Returning [] makes condition (c) ``unknown`` rather than ``pass`` — the
    board could not be read, which is not the same as the board being clean.
    """
    try:
        raw = subprocess.run(
            ["gh", "project", "item-list", "1", "--owner", "alexander-bain",
             "--format", "json", "--limit", "200"],
            capture_output=True, text=True, timeout=60)
        if raw.returncode != 0:
            return []
        items = json.loads(raw.stdout).get("items", [])
    except (OSError, ValueError, subprocess.SubprocessError):
        return []

    now, out = datetime.now(timezone.utc), []
    for it in items:
        if (it.get("status") or "").strip().lower() != "ready":
            continue
        stamp = it.get("updatedAt") or it.get("createdAt")
        if not stamp:
            continue
        try:
            when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        label = f"#{it.get('content', {}).get('number', '?')} {it.get('title', '')}"
        out.append((label[:80], (now - when).days))
    return out


def file_issues(report: dict) -> list[str]:
    """One deduped issue per CONDITION per day — never one per finding.

    An open issue gets a comment, not a duplicate. The title names the count
    and the condition, because a title reading "findings" is a title nobody
    opens.
    """
    posted = []
    by_condition: dict[str, list[dict]] = {}
    for f in report["findings"]:
        by_condition.setdefault(f["condition"], []).append(f)

    for letter, findings in sorted(by_condition.items()):
        marker = f"board-drift:{letter}"
        title = (f"[Board drift] {len(findings)} "
                 f"{_CONDITION_TITLES.get(letter, letter)}")
        body = "\n".join(
            [f"`{marker}` — {report['generated_at']}", "",
             f"**{len(findings)} finding(s).** Worst severity: "
             f"{min(f['severity'] for f in findings)}.", ""]
            + [f"- **{f['severity']}** `{f['subject']}` — {f['detail']}"
               for f in findings]
            + ["", "_Filed by the board-drift sentinel (#1878). It never "
                   "mutates: no files renamed, no cards moved._"])

        found = subprocess.run(
            ["gh", "issue", "list", "--state", "open", "--search", marker,
             "--json", "number", "--limit", "1"],
            capture_output=True, text=True)
        existing = json.loads(found.stdout or "[]") if found.returncode == 0 else []
        if existing:
            n = str(existing[0]["number"])
            subprocess.run(["gh", "issue", "comment", n, "--body", body],
                           capture_output=True, text=True)
            posted.append(f"commented #{n} ({marker})")
        else:
            made = subprocess.run(
                ["gh", "issue", "create", "--title", title, "--body", body,
                 "--label", "area:infra", "--label", "type:bug"],
                capture_output=True, text=True)
            posted.append((made.stdout or made.stderr).strip().splitlines()[-1:][0]
                          if (made.stdout or made.stderr) else f"created ({marker})")
    return posted


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--file-issues", action="store_true")
    args = ap.parse_args()

    report = collect()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"board-drift sentinel — verdict: {report['verdict'].upper()} "
              f"({report['finding_count']} findings, "
              f"worst {report['worst_severity'] or 'none'})")
        for letter, c in report["conditions"].items():
            print(f"  ({letter}) {c['verdict']:8} checked={c['checked']:<4} "
                  f"findings={c['findings']:<3} {_CONDITION_TITLES.get(letter,'')}")
        for f in report["findings"]:
            print(f"    {f['severity']} [{f['condition']}] {f['subject']}")

    if args.file_issues and report["findings"]:
        for line in file_issues(report):
            print(f"  filed: {line}")

    # Exit 0 always: this is a REPORTER. A non-zero exit would make night.sh
    # treat real drift as a broken sentinel, and the fix for a red sentinel
    # would become "stop running it".
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
