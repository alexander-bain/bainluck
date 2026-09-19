#!/usr/bin/env python3
"""granted-token-sweep.py — notice 31(b): every GREEN token, against master ancestry.

WHAT THIS IS FOR. Notice 31(b) makes the desk sweep `TOKEN GRANTED` ledger rows
against `origin/master` at the TOP and again at the BOTTOM of every pass, and tray
any GREEN sha with no offer. The reason is in the notice: *the tray records what a
lane remembered to say, the ledger what graded.* A granted token nobody offered is
the failure this catches, and it has fired on two consecutive passes (int450/int451,
both inside the sixty-second shadow of a handover).

WHY A TOOL AND NOT A GREP. Every desk has improvised this sweep, and the improvised
form has two defects that were measured on 2026-09-19 (int452):

  1. OVER-INCLUSIVE EXTRACTION. "every 40-hex on a TOKEN GRANTED line" also reads
     the shas a granted row QUOTES — the superseded one, the base one. It reported
     `f5c84b85b` as an unmerged granted token; that sha is CERT-3046, a BLOCK, named
     only because CERT-3048's GREEN row says "SUPERSEDES CERT-3046 SHA". The granted
     sha is the one that follows `exact SHA`, and nothing else on the row is one.

  2. AN UNDERIVED WINDOW. The improvised sweep truncates — `tail -60` — because it
     cannot classify, and a desk reading 60 rows reports "0 unmerged of 60" without
     ever asking what 60 covers. Widening the same sweep to 150 surfaced two more
     tokens. (Both turned out DEAD by declared supersede, so no ship was missed;
     the point is that the window was never derived, so its silence meant nothing.)
     The fix is not a bigger number. It is to read EVERY row and classify, so the
     only bound left is one that means something — see "WHY LIVE IS SCOPED BY AGE".

CLASSES (a granted token is exactly one of these)

  MERGED    the sha is an ancestor of origin/master. It shipped.
  AGED      granted longer ago than --days and still not on master. NOT this tool's
            subject and NOT printed as a tray item — see "WHY LIVE IS SCOPED BY AGE".
  DEAD      a LATER verdict row declares a supersede of this cert (notice 18).
            The token is revoked; the sha is not merged and must not be. Notice 28's
            corollary: if it also conflicts with its base it cannot be re-CI'd at
            this sha at all — rebase, restage, re-grade.
  UNKNOWN   the commit object is not in this checkout. Per gotcha #53 this is a
            RESPONSE SHAPE, not an absence: almost always a merged branch whose ref
            was pruned, but this tool will not call it merged on a guess. Resolve
            with `git fetch --all` or the compare API before believing a count.
  LIVE      granted within --days, not superseded, not on master. THE TRAY LIST.

WHY LIVE IS SCOPED BY AGE, AND WHY THAT IS NOT THE WINDOW THIS TOOL EXISTS TO KILL.
The window being replaced was `tail -60` — a count of ROWS, which maps to no duty and
silently changes meaning every time the bus grades faster or slower. The age bound is
a different thing: it is the definition of the CLASS. Notice 31(b) catches *a token
granted while nobody was looking* — int450 and int451 both found one inside the
sixty-second shadow of a handover. A token granted ten days ago and still unmerged is
not a desk oversight, it is stranded work, and stranded work already has an instrument
with a different remedy (rescue or close, never merge): `tools/stranded-sweep.py`,
D52. So AGED items are counted and pointed there, and they do not fail this run.

Measured on 2026-09-19 (int452), this is also what keeps the tool readable: ancestry
alone called 88 granted tokens unmerged, 87 of them older than three days. Ancestry
cannot see a patch that landed by rebase under a different sha — spot-checking five of
those 87 with `git cherry`, two had already shipped that way. That check is deliberately
NOT run here: it costs ~84s against this shallow clone, which is too slow for something
meant to run at the top and bottom of every pass, and `stranded-sweep.py` already does
it for the population that needs it. What matters for THIS tool is that printing 87
aged rows as a tray list would have buried the two that mattered — CERT-3118 and
CERT-3119, granted 09:10Z and 09:15Z, unoffered, and merged by this pass. A sweep that
cries wolf stops being read, which costs exactly the ship notice 31(b) exists to save.

THE CONTROLS ARE THE POINT, AND THEY RUN IN BOTH DIRECTIONS.
int450's recorded trap was a sweep that read "all clean" while silently skipping
every row it was supposed to read. A control that only proves the sweep can say
"bad" cannot prove it can say "good", so this tool plants three:

    a known-MERGED sha   must classify MERGED   (proves it can say "shipped")
    a known-DEAD sha     must classify DEAD     (proves the supersede path fires)
    a nonexistent sha    must classify UNKNOWN  (proves it reads objects at all)

If any control misbehaves the tool EXITS 2 and prints no verdict. A sweep that
cannot prove it read anything does not get to report a clean result.

  ./tools/granted-token-sweep.py              # the sweep
  ./tools/granted-token-sweep.py --dry-run    # controls + parse only, no verdict
  ./tools/granted-token-sweep.py --self-test  # pin the extraction against real rows
  ./tools/granted-token-sweep.py --json       # machine-readable

EXIT CODES — `1` is a result, everything else is a story about the harness (#124):
  0  swept, no LIVE unmerged tokens
  1  swept, one or more LIVE unmerged tokens to tray  (a RESULT, act on it)
  2  the sweep could not be trusted — a control failed, or the ledger is unreadable
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# The ledger is UNTRACKED, so it exists in the shared checkout and in no worktree.
# Run from a worktree, `REPO/.claude/...` simply is not there. Both candidates are
# tried and the one actually read is PRINTED: there are two plausible locations for
# handoff files in this repo's history and a tool that silently picks one can read a
# fork of the record and report on it with total confidence.
LEDGER_CANDIDATES = [
    REPO / ".claude" / "handoff" / "CODEX-CERT-LOG.md",
    Path.home() / "bainluck" / ".claude" / "handoff" / "CODEX-CERT-LOG.md",
]
MASTER = "origin/master"


def find_ledger(override=None):
    if override:
        p = Path(override).expanduser()
        return p if p.exists() else None
    for c in LEDGER_CANDIDATES:
        if c.exists():
            return c
    return None

# A verdict row. Bus-status and reconciliation rows are prose and are NOT verdicts
# (notice 18, amended 9/11) — they are excluded by requiring the `CERT-<n>` id form.
ROW = re.compile(r"^\|\s*(CERT-\d+)\s*--", re.I)
GRANTED = re.compile(r"TOKEN GRANTED", re.I)
SHA40 = re.compile(r"\b([0-9a-f]{40})\b", re.I)
# The report reference that opens the evidence cell. The SUBJECT sha is the first
# 40-hex AFTER it; everything later on the row is context.
REPORT_REF = re.compile(r"CODEX-REPORT[^`]*:\s*CERT-\d+", re.I)
# "supersedes CERT-N" / "SUPERSEDES CERT-N SHA" anywhere in a verdict row.
SUPERSEDES = re.compile(r"supersedes\s+(CERT-\d+)", re.I)
# The grading stamp, second cell: `2026-09-19 09:10Z`.
WHEN = re.compile(r"\|\s*(\d{4}-\d{2}-\d{2})[ T](\d{2}):(\d{2})Z?\s*\|")


def row_when(line):
    m = WHEN.search(line)
    if not m:
        return None
    try:
        return datetime.strptime(
            f"{m.group(1)} {m.group(2)}:{m.group(3)}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def cells(line):
    """The ledger is a markdown TABLE, so read it as one.

    `| id -- subject | date | lane | verdict | evidence… |` — split gives a leading
    empty field, so verdict is index 4 and evidence is everything from 5 on. This is
    not pedantry: matching `TOKEN GRANTED` against the WHOLE LINE counts 41 rows that
    only mention the phrase in prose — merge notes saying "matches a TOKEN GRANTED
    row", gate descriptions quoting notice 13 — as grants (measured 2026-09-19,
    CERT-796's `-- MERGED` note is the type specimen). Those rows have no subject sha
    of their own, so they surface later as phantom NO_SHA or phantom AGED entries.
    """
    c = line.split("|")
    return (c[4] if len(c) > 4 else ""), ("|".join(c[5:]) if len(c) > 5 else "")


def subject_sha(line):
    """The sha the token was granted ON.

    MEASURED, not assumed (int452, 2026-09-19 over all 1,125 granted verdict rows).
    Two extractions were tried and both are wrong:

      "every 40-hex on the row"  reads the shas a row QUOTES. CERT-3048's GREEN row
          names `f5c84b85b` because it SUPERSEDES it — that sha is a BLOCK, and the
          improvised sweep reported it as an unmerged granted token.

      "the hex after `exact SHA`"  misses 175 of 1,125 rows (16%) outright, because
          graders write the same fact four ways: `exact SHA`, `SHA`, `exact backend
          SHA`, `current exact PR head`. A sweep silently blind to a sixth of the
          ledger is the int450 trap with a tidier output. (An earlier draft of this
          note said 28%. That figure counted the 41 prose rows `cells()` now excludes
          and was wrong in the direction that flattered the argument; 16% is the
          number after both defects are fixed.)

    What holds across every sampled form is POSITION: the subject sha is the first
    40-hex after the `CODEX-REPORT…: CERT-NNNN` reference, and the context shas —
    the replaced pre-rebase sha, a landed sibling, a merge commit — always follow it.
    Rows with no hex at all are real (CERT-3106 reconciles a duplicate and grants no
    new sha); they return None and are classed NO_SHA, never dropped in silence.
    """
    _, evidence = cells(line)
    ref = REPORT_REF.search(evidence)
    m = SHA40.search(evidence, ref.end() if ref else 0)
    if not m:                      # a ref with nothing after it: fall back to the
        m = SHA40.search(evidence)  # first hex in the evidence cell, never the row
    return m.group(1).lower() if m else None

CONTROLS = [
    # (sha, expected class, why this sha)
    (
        "a44d99613aab7455440ad8c453eff1ffef401402",
        "MERGED",
        "CERT-3116, merged as 564dcc0b0 and released v4766",
    ),
    (
        "1555657af82212980debb4a35a136bdc9e97ef3c",
        "DEAD",
        "CERT-2979, revoked by CERT-2980's declared supersede",
    ),
    (
        "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        "UNKNOWN",
        "not a commit; proves the tool reads objects rather than assuming",
    ),
]


def git(*args):
    p = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True, timeout=300
    )
    return p.returncode, p.stdout, p.stderr


def parse_ledger(text):
    """Return (granted, superseded_certs).

    `granted` is ordered [(cert_id, sha, line_no)]; a cert appears once, on its own
    verdict row. `superseded_certs` is every cert id a verdict row declares dead.
    """
    granted, superseded = [], set()
    for n, line in enumerate(text.splitlines(), 1):
        m = ROW.match(line)
        if not m:
            continue  # not a verdict row — prose, bus status, header, separator
        cert = m.group(1).upper()
        # A row declares supersedes regardless of its own verdict, but never of
        # ITSELF: a repair row cites its own id after the word (notice 18's
        # mechanized form exists because the plain grep false-STOPs on exactly that).
        for dead in SUPERSEDES.findall(line):
            if dead.upper() != cert:
                superseded.add(dead.upper())
        verdict, _ = cells(line)
        if GRANTED.search(verdict):
            granted.append((cert, subject_sha(line), n, row_when(line)))
    return granted, superseded


def classify(granted, superseded, ancestors, present, cutoff=None):
    out = []
    for cert, sha, line_no, when in granted:
        if sha is None:
            cls = "NO_SHA"
        elif sha in ancestors:
            cls = "MERGED"
        elif cert in superseded:
            cls = "DEAD"
        elif sha not in present:
            cls = "UNKNOWN"
        elif cutoff and when and when < cutoff:
            cls = "AGED"
        else:
            # No date on the row cannot mean "old enough to ignore" — an unparseable
            # stamp stays LIVE and gets looked at. Fail toward being read.
            cls = "LIVE"
        out.append({"cert": cert, "sha": sha, "line": line_no,
                    "when": when.isoformat() if when else None, "class": cls})
    return out


# Real rows, copied verbatim from the ledger, one per phrasing the graders use plus
# the two shapes that broke the improvised sweep. A change to `subject_sha` that
# regresses any of these is caught here rather than by a ship going missing.
SELF_TEST = [
    ("exact SHA",
     "| CERT-3117 -- 4079-A7 | 2026-09-19 08:24Z | discover/211 (#4079) | **GREEN -- "
     "TOKEN GRANTED** | `CODEX-REPORT-2.md: CERT-3117`; exact SHA "
     "`83e5629a8f635bc4756b193bd630a871b03d0ab3`. DISCOVER ship holds.",
     "83e5629a8f635bc4756b193bd630a871b03d0ab3"),
    ("bare SHA",
     "| CERT-2543 -- 4688-PART-A2 | 2026-09-10 21:25Z | calibration/1093 | **GREEN -- "
     "TOKEN GRANTED** | `CODEX-REPORT-2.md: CERT-2543`; SHA "
     "`520854a67c522160e727e9e6bf5854660a848cf0`. The TRUTH ship holds.",
     "520854a67c522160e727e9e6bf5854660a848cf0"),
    ("current exact PR head, pre-rebase sha ALSO on the row",
     "| CERT-2938 -- 5896 | 2026-09-16 03:20Z | lane1b/281 | **GREEN -- TOKEN GRANTED** "
     "| `CODEX-REPORT-2.md: CERT-2938`; current exact PR head "
     "`3c8ee09811fd585e33fd318622bb52325051e538` (queue's staged pre-rebase SHA "
     "`ea6e06ae67f5eba542fe7261abd4bab72070a6e9` was replaced during grading)",
     "3c8ee09811fd585e33fd318622bb52325051e538"),
    ("exact backend SHA, landed frontend sibling ALSO on the row",
     "| CERT-2622 -- 5088 | 2026-09-11 14:30Z | live/152 | **GREEN -- TOKEN GRANTED** | "
     "`CODEX-REPORT-2.md: CERT-2622`; exact backend SHA "
     "`5d18064c91caac7cae36caaaf9efe54fba3f885e`, composed after landed frontend repair "
     "`9ff6abc27d3ab864b12d61348275573574701e6d`",
     "5d18064c91caac7cae36caaaf9efe54fba3f885e"),
    ("a GREEN row that QUOTES the BLOCK sha it supersedes",
     "| CERT-3048 -- 2693-POP3 | 2026-09-18 03:20Z | lane1/410 | **GREEN -- TOKEN "
     "GRANTED; SUPERSEDES CERT-3046 SHA** | `CODEX-REPORT-2.md: CERT-3048`; exact SHA "
     "`87d7fa201fa15a4d3581b4a5c33cd2500023d023`. The four CERT-3046 records "
     "`f5c84b85b9adf7e0d636595c7f6a10ed03c1ecb9` are absent.",
     "87d7fa201fa15a4d3581b4a5c33cd2500023d023"),
    # SYNTHETIC, and deliberately so. Mutating the ref anchor and the cell scoping
    # away leaves BOTH with zero specimens in today's ledger (measured: 0 rows carry a
    # 40-hex both before AND after the report ref; 0 rows differ between a whole-row
    # and an evidence-cell scan). They are defence in depth against a shape the ledger
    # does not currently contain — a sha in the lane cell, a second sha quoted ahead of
    # the reference. An unreachable guard is still worth pinning; what is not worth
    # doing is pretending a live row proves it. These two fixtures are the proof.
    ("SYNTHETIC: a sha in the LANE cell must not win over the subject sha",
     "| CERT-9001 -- SYNTHETIC | 2026-09-19 10:00Z | bus aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa "
     "| **GREEN -- TOKEN GRANTED** | `CODEX-REPORT-2.md: CERT-9001`; exact SHA "
     "`bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb`.",
     "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"),
    ("SYNTHETIC: a sha quoted BEFORE the report ref must not win",
     "| CERT-9002 -- SYNTHETIC | 2026-09-19 10:00Z | bus | **GREEN -- TOKEN GRANTED** | "
     "prior context `cccccccccccccccccccccccccccccccccccccccc` then "
     "`CODEX-REPORT-2.md: CERT-9002`; exact SHA "
     "`dddddddddddddddddddddddddddddddddddddddd`.",
     "dddddddddddddddddddddddddddddddddddddddd"),
    ("SYNTHETIC: no report ref at all — the lane cell's sha still must not win",
     "| CERT-9003 -- SYNTHETIC | 2026-09-19 10:00Z | bus eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee "
     "| **GREEN -- TOKEN GRANTED** | no report reference on this row; exact SHA "
     "`ffffffffffffffffffffffffffffffffffffffff`.",
     "ffffffffffffffffffffffffffffffffffffffff"),
    ("a reconciliation row that grants no new sha",
     "| CERT-3106 -- 6471-REKEY | 2026-09-19 02:32Z | codex cert bus | **GREEN -- "
     "DUPLICATE RECONCILED; CERT-3105 TOKEN STANDS** | `CODEX-REPORT-2.md: CERT-3106`. "
     "Standing notice 17 rekeys the later review.",
     None),
]


# Rows that must NOT be read as grants, and the id-parse traps. Both were found by
# mutating this tool and checking the mutant against the real ledger: each survived
# the first fixture set while being wrong on 41 and 6 real rows respectively.
NOT_A_GRANT = (
    "| CERT-796 -- MERGED | 2026-09-03 06:20Z | integrator/080 | **MERGED TO MASTER "
    "`26a14a34`** | Merge gate passed: `a3815e4712a2b91a4aa1d1dd4e2b0a3b5c6d7e8f` "
    "matches a TOKEN GRANTED row and no later row supersedes CERT-796."
)
OWN_ID_SUPERSEDES = (
    "| CERT-2939 -- BLEND-RACE-V2 | 2026-09-16 03:44Z | live/317 (repairs CERT-2937) | "
    "**GREEN -- TOKEN GRANTED** | `CODEX-REPORT-2.md: CERT-2939`; a repair row that "
    "supersedes CERT-2939 in its own prose must not mark itself dead; it supersedes "
    "CERT-2937. exact SHA `d56242a6631d1e17b4452800ceef531b54a3cab5`."
)


def self_test():
    bad = 0
    for name, line, want in SELF_TEST:
        got = subject_sha(line)
        ok = got == want
        bad += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            print(f"        want {want}\n        got  {got}")
    g, _ = parse_ledger(NOT_A_GRANT)
    if g:
        print(f"  FAIL  a merge note quoting 'TOKEN GRANTED' in prose was read as a grant")
        bad += 1
    else:
        print("  PASS  'TOKEN GRANTED' in PROSE is not a grant — only the verdict cell is")
    g2, sup2 = parse_ledger(OWN_ID_SUPERSEDES)
    if "CERT-2939" in sup2 or sup2 != {"CERT-2937"}:
        print(f"  FAIL  a repair row marked ITSELF superseded: {sup2}")
        bad += 1
    else:
        print("  PASS  a repair row citing its own id after 'supersedes' is not dead")
    # The supersede parser must NOT read a row's own id (notice 18's mechanized form
    # exists because the plain grep false-STOPs on exactly that).
    _, sup = parse_ledger(SELF_TEST[4][1])
    if sup != {"CERT-3046"}:
        print(f"  FAIL  supersede parse: want {{'CERT-3046'}}, got {sup}")
        bad += 1
    else:
        print("  PASS  supersede parse names the superseded cert, not the row's own id")
    # A row with no date must stay LIVE, never age out silently.
    rows = classify([("CERT-X", "0" * 40, 1, None)], set(), set(), {"0" * 40},
                    datetime.now(timezone.utc))
    if rows[0]["class"] != "LIVE":
        print(f"  FAIL  undated row aged out as {rows[0]['class']}; must stay LIVE")
        bad += 1
    else:
        print("  PASS  an undated row stays LIVE rather than ageing out unseen")
    print(f"\n  self-test: {'all pass' if not bad else f'{bad} FAILED'}")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="controls + parse, no verdict")
    ap.add_argument("--self-test", action="store_true", dest="self_test",
                    help="pin subject-sha extraction against real ledger rows")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--ledger", help="path to CODEX-CERT-LOG.md (default: this "
                                     "checkout, then ~/bainluck)")
    ap.add_argument("--days", type=float, default=3.0,
                    help="how recent a grant must be to count as the desk's to tray "
                         "(default 3). Older unmerged grants are AGED and belong to "
                         "tools/stranded-sweep.py, D52.")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    ledger = find_ledger(args.ledger)
    if ledger is None:
        tried = args.ledger or ", ".join(str(c) for c in LEDGER_CANDIDATES)
        print(f"FATAL: ledger not found. Tried: {tried}", file=sys.stderr)
        return 2
    print(f"  ledger {ledger}")
    text = ledger.read_text(errors="ignore")

    granted, superseded = parse_ledger(text)
    if not granted:
        print("FATAL: parsed 0 granted tokens — the ledger format moved under this tool.",
              file=sys.stderr)
        return 2

    # ONE rev-list, not one merge-base per sha. The per-sha form is O(n) subprocesses
    # and is why the improvised sweep truncates in the first place.
    rc, out, err = git("rev-list", MASTER)
    if rc != 0:
        print(f"FATAL: git rev-list {MASTER} -> {rc}: {err.strip()}", file=sys.stderr)
        return 2
    ancestors = set(out.split())

    # Which shas exist as commit objects here. `cat-file --batch-check` in one pass.
    shas = sorted({s for _, s, _, _ in granted if s} | {c[0] for c in CONTROLS})
    p = subprocess.run(
        ["git", "-C", str(REPO), "cat-file", "--batch-check"],
        input="\n".join(shas), capture_output=True, text=True, timeout=300,
    )
    present = set()
    for line in p.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "commit":
            present.add(parts[0].lower())

    # ---- CONTROLS, both directions, before any verdict is printed ----------------
    ctl_rows, ctl_ok = [], True
    for sha, expect, why in CONTROLS:
        got = classify(
            [("CONTROL", sha, 0, None)], superseded, ancestors, present, None
        )[0]["class"]
        # The DEAD control is classified by its real cert, not the placeholder id.
        if expect == "DEAD":
            cert = next((c for c, s, _, _ in granted if s == sha), None)
            got = (
                "MERGED" if sha in ancestors
                else "DEAD" if cert and cert in superseded
                else "UNKNOWN" if sha not in present
                else "LIVE"
            )
        ok = got == expect
        ctl_ok &= ok
        ctl_rows.append({"sha": sha[:9], "expected": expect, "got": got, "ok": ok, "why": why})

    for r in ctl_rows:
        print(f"  {'PASS' if r['ok'] else 'FAIL'}  control {r['sha']}  "
              f"expected {r['expected']:<7} got {r['got']:<7}  {r['why']}")

    if not ctl_ok:
        print("\nSTOP: a control misbehaved. This sweep cannot be trusted and prints "
              "no verdict.\n       A sweep that cannot prove it read anything does "
              "not get to report a clean result.", file=sys.stderr)
        return 2

    if args.dry_run:
        print(f"\n--dry-run: controls pass; parsed {len(granted)} granted tokens, "
              f"{len(superseded)} superseded certs. No verdict computed.")
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    rows = classify(granted, superseded, ancestors, present, cutoff)
    counts = {k: sum(1 for r in rows if r["class"] == k)
              for k in ("MERGED", "AGED", "DEAD", "UNKNOWN", "LIVE", "NO_SHA")}
    live = [r for r in rows if r["class"] == "LIVE"]
    unknown = [r for r in rows if r["class"] == "UNKNOWN"]

    if args.as_json:
        print(json.dumps({"master": git("rev-parse", MASTER)[1].strip(),
                          "counts": counts, "live": live, "unknown": unknown}, indent=2))
        return 1 if live else 0

    master = git("rev-parse", MASTER)[1].strip()
    print(f"\n  master {master[:9]} · {len(rows)} granted tokens read (no window) · "
          f"MERGED {counts['MERGED']} · AGED {counts['AGED']} · "
          f"DEAD {counts['DEAD']} · UNKNOWN {counts['UNKNOWN']} · "
          f"NO_SHA {counts['NO_SHA']} · LIVE {counts['LIVE']}")

    if unknown:
        print(f"\n  UNKNOWN ({len(unknown)}) — object not in this checkout. NOT an "
              f"absence (gotcha #53);\n  almost always a pruned merged branch. "
              f"`git fetch --all` then re-run before believing it.")
        for r in unknown[-10:]:
            print(f"    {r['sha'][:9]}  {r['cert']}  ledger line {r['line']}")
        if len(unknown) > 10:
            print(f"    … and {len(unknown) - 10} older")

    if counts["AGED"]:
        print(f"\n  AGED ({counts['AGED']}) — granted more than {args.days:g}d ago and still "
              f"not on master.\n  Not the desk's to merge: that is stranded work. "
              f"`tools/stranded-sweep.py` (D52)\n  rescues or closes it, and reads patch-id "
              f"so it can tell a rebase-landed sha from a lost one.")

    if live:
        print(f"\n  LIVE — GRANTED, NOT SUPERSEDED, NOT ON MASTER. TRAY THESE:")
        for r in live:
            print(f"    {r['sha'][:9]}  {r['cert']}  granted {r['when'] or 'undated'}"
                  f"  ledger line {r['line']}")
        print("\n  Next: run tools/merge-gate.sh on each before merging. Notice 47(a) —"
              "\n  a GREEN sha whose base is materially behind is re-composed by the"
              "\n  OWNING LANE, not merged by the desk on textual composition.")
        return 1

    print("\n  No live unmerged granted tokens.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
