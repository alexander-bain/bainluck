#!/usr/bin/env python3
"""live/059 mutation battery — does the guard suite BITE, or merely pass?

Each mutant restores a defect that was either (a) actually written during this
build and caught by a test, or (b) the obvious "simplification" a future editor
would reach for. A mutant that survives means the guard for that claim is
decorative and the claim is unprotected.

THE RULES THIS HARNESS OBEYS, and they are the ones that have burned this repo:

  * **Prove the edit APPLIED.** A mutant whose `old` string does not appear in
    the file is a mutant that never ran, and a suite passing against unmutated
    code reads exactly like a suite that killed it. Every replacement asserts
    its own landing before the tests run.
  * **`__pycache__` is purged** between arms — a stale `.pyc` re-runs the
    ORIGINAL function under the mutated file's name.
  * **The CONTROL runs first and must be GREEN.** A red control makes every
    subsequent "killed" meaningless: the suite was already failing.
  * **The tree is restored on every exit path**, including a crash.

RUN IT ON A COPY, NOT ON THE BRANCH. The restore is a `finally`, which survives
a crash and does not survive `kill -9`:

    MUT=/tmp/live059-mut-$$ && mkdir -p "$MUT" \
      && rsync -a --exclude __pycache__ --exclude .pytest_cache backend "$MUT"/ \
      && (cd "$MUT/backend" && python3 scripts/live059_mutation_battery.py)

`check_for_residue` is the backstop for when somebody runs it in place anyway:
the next run refuses to start on a tree that still carries a mutant.

Run:  cd backend && python3 scripts/live059_mutation_battery.py
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

SUITE = [
    "tests/test_futures_chart_series.py",
    "tests/test_futures_chart_series_fill.py",
    "tests/test_tennis_line_source.py",
    "tests/test_live_tennis_score_poll.py",
]

#: (name, file, old, new, why it matters)
MUTANTS = [
    (
        "M1 layer_tiers claims a SPAN, not a proximity",
        "app/utils/futures_chart_series.py",
        "            i = bisect.bisect_left(claimed_ts, epoch)\n"
        "            blocked = False\n"
        "            for j in (i - 1, i):\n"
        "                if 0 <= j < len(claimed_ts):\n"
        "                    if abs(claimed_ts[j] - epoch) <= claimed_r[j]:\n"
        "                        blocked = True\n"
        "                        break",
        "            blocked = bool(claimed_ts) and (\n"
        "                min(claimed_ts) <= epoch <= max(claimed_ts)\n"
        "            )",
        "the version actually written first: a venue with a mid-series outage "
        "claims the outage, and our captures cannot fill it",
    ),
    (
        "M2 compaction spends one flat budget over the whole life",
        "app/tasks/futures_chart_series_fill.py",
        "            final = compact_by_band(layered, now)",
        "            final = compact_series(layered)",
        "measured: an 8-month series at a flat 400-point budget leaves the last "
        "DAY with 37 points — a worse 1D than the sampler it replaces",
    ),
    (
        "M3 blend_venues extrapolates a venue BACKWARDS",
        "app/utils/futures_chart_series.py",
        "        num = 0.0\n"
        "        den = 0.0\n"
        "        for name, value in last.items():\n"
        "            if value is None:\n"
        "                continue",
        "        num = 0.0\n"
        "        den = 0.0\n"
        "        for name, value in last.items():\n"
        "            if value is None:\n"
        "                value = active[name][0][1]",
        "a market listed on one venue in January and the other in June would "
        "draw June's opinion of January",
    ),
    (
        "M4 a StatPal set is awarded by simple comparison",
        "app/utils/tennis_line_source.py",
        "    high, low = max(home, away), min(home, away)\n"
        "    won = (high == 6 and low <= 4) or (high == 7 and low in (5, 6))\n"
        "    if not won:\n"
        "        return None",
        "    if home == away:\n"
        "        return None",
        "the inversion `authority_score` refuses 5 of 6 retirements over: an "
        "abandoned set at 3-1 awarded to whoever was ahead",
    ),
    (
        "M5 select_line takes StatPal's points onto an ESPN line",
        "app/utils/tennis_line_source.py",
        "    for field in SCORE_FIELDS:\n"
        "        out[field] = chosen.get(field)",
        "    for field in SCORE_FIELDS:\n"
        "        out[field] = chosen.get(field)\n"
        "    if statpal is not None and out.get('points') is None:\n"
        "        out['points'] = statpal.get('points')\n"
        "        out['serving'] = statpal.get('serving')",
        "THE MIXED LINE — the tempting build. ESPN has no points and StatPal "
        "does, so take them anyway, and print a game score from another game",
    ),
    (
        "M6 the Kalshi batch is sized on periods, not on the product",
        "app/utils/futures_chart_series.py",
        "    per_group = max(1, int(max_candles // max(1, periods)))",
        "    per_group = len(tickers)",
        "8 tickers x 1440 one-minute candles = 400, and ONLY the finest tier "
        "fails, so the chart still draws and quietly lost its resolution",
    ),
    (
        "M7 the coarse CLOB tier drops to fidelity=60",
        "app/utils/futures_chart_series.py",
        "CLOB_COARSE_FIDELITY = 720",
        "CLOB_COARSE_FIDELITY = 60",
        "the measured retention wall: fidelity 60 stops at ~31 days, so ALL "
        "silently means one month and never reaches the draw",
    ),
    (
        "M8 the Kalshi batch response is zipped by position",
        "app/tasks/futures_chart_series_fill.py",
        "            for ticker, candles in (by_ticker or {}).items():",
        "            for ticker, candles in zip(group, (by_ticker or {}).values()):",
        "measured: the venue answers OUT OF ORDER and omits unknown tickers, so "
        "position-zipping draws Shelton's 9% curve as Alcaraz's 43% one",
    ),
    (
        "M9 the read path REPLACES the sampled series instead of layering",
        "app/utils/event_concept.py",
        "        merged = compact_series(layer_tiers([venue, sampled]))",
        "        merged = compact_series(venue)",
        "the chart's right-hand edge ends where the last venue fetch ended — "
        "up to 36 hours ago — instead of at now",
    ),
    (
        "M10 the second clock is left in the no-op comparison",
        "app/tasks/espn_sync.py",
        '    _CLOCKS = ("observed_at", "score_as_of")',
        '    _CLOCKS = ("observed_at",)',
        "`score_as_of` moves every pass, so every pass is a 'change' and the "
        "whole live population is rewritten three times a minute",
    ),
    (
        "M11 an unanchored row is switched to StatPal anyway",
        "app/utils/tennis_line_source.py",
        "    if has_statpal_anchor and statpal is not None:",
        "    if statpal is not None:",
        "an unanchored name-match is exactly the wrong reason to switch "
        "sources — the anchor is what says this row IS that match",
    ),
    (
        "M12 a StatPal-only line borrows StatPal's state",
        "app/utils/tennis_line_source.py",
        "    state_holder = espn or {}",
        "    state_holder = espn or statpal or {}",
        "D27 makes ESPN the state authority; a state word from elsewhere under "
        "`state_source: espn` is a lie in the field nothing downstream doubts",
    ),
]


def run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def purge_pycache() -> None:
    for cache in ROOT.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


def suite() -> tuple[int, str]:
    purge_pycache()
    return run([sys.executable, "-m", "pytest", *SUITE, "-q", "-x", "--no-header"])


def check_for_residue() -> list[str]:
    """Is a mutant from a PREVIOUS run still sitting in the tree?

    The `finally` below restores everything — on every exit path the interpreter
    controls. It does not control `kill -9`, a closed terminal or an OOM, and a
    run that dies there leaves a defect in the working tree wearing the branch's
    name. It happened: this battery's own M10 was found applied hours later, and
    the only reason it did not travel further is that the guard it defeats went
    red in the focused suite.

    So the run REFUSES to start on a mutated tree rather than treating it as its
    own baseline — a mutated file is a red control, and a red control makes
    every "killed" below meaningless.
    """
    residue = []
    for name, rel, old, new, _why in MUTANTS:
        text = (ROOT / rel).read_text()
        if old not in text and new in text:
            residue.append(f"{name}  ({rel})")
    return residue


def main() -> int:
    residue = check_for_residue()
    if residue:
        print("REFUSING TO RUN — a previous run left mutants in this tree:")
        for line in residue:
            print(f"  {line}")
        print("\nRestore them (`git checkout -- <file>`) before running again.")
        return 3

    originals = {
        rel: (ROOT / rel).read_text()
        for _n, rel, _o, _new, _w in MUTANTS
    }

    print("=" * 78)
    print("CONTROL — the suite must be GREEN before any mutant means anything")
    print("=" * 78)
    code, out = suite()
    print(out.strip().splitlines()[-1] if out.strip() else "(no output)")
    if code != 0:
        print("\nCONTROL RED — every 'killed' below would be meaningless. Stopping.")
        return 1

    killed, survived = [], []
    try:
        for name, rel, old, new, why in MUTANTS:
            path = ROOT / rel
            source = originals[rel]
            if old not in source:
                print(f"\n!! {name}\n   ANCHOR MISSING in {rel} — mutant never applied.")
                survived.append((name, "anchor-missing"))
                continue
            mutated = source.replace(old, new, 1)
            assert mutated != source, "replacement was a no-op"
            path.write_text(mutated)
            # PROVE IT LANDED, on disk, before running anything.
            assert new.strip().splitlines()[0] in path.read_text(), "edit did not land"

            code, out = suite()
            path.write_text(source)
            tail = out.strip().splitlines()[-1] if out.strip() else ""
            verdict = "KILLED " if code != 0 else "SURVIVED"
            print(f"\n{verdict}  {name}")
            print(f"          why it matters: {why}")
            print(f"          {tail}")
            (killed if code != 0 else survived).append((name, tail))
    finally:
        for rel, text in originals.items():
            (ROOT / rel).write_text(text)
        purge_pycache()

    print("\n" + "=" * 78)
    print(f"{len(killed)} killed / {len(MUTANTS)} applied")
    for name, tail in survived:
        print(f"  SURVIVED: {name}  ({tail})")
    print("=" * 78)
    return 0 if not survived else 2


if __name__ == "__main__":
    raise SystemExit(main())
