#!/usr/bin/env python3
"""CAL-P1084 (#4730) mutation battery for the candle price policy.

Same harness as `tools/cal-1076-mutations.py` (back up as its OWN statement,
assert the backup, substitute on an asserted-unique occurrence, run the guards,
restore, assert the restore). Each mutation removes exactly one clause of
`app/utils/kalshi_candle_price.candle_yes_price` and asks whether the guard
file notices.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
TARGET = "app/utils/kalshi_candle_price.py"

GUARDS = ["tests/test_kalshi_candle_price.py"]

#: (label, relative path, old, new, expected verdict)
MUTATIONS = [
    (
        "M1 the spread guard is dropped — any two-sided book midpoints",
        TARGET,
        "        and ask >= bid\n        and (ask - bid) <= WIDE_SPREAD_DOLLARS\n",
        "        and ask >= bid\n",
        "RED",
    ),
    (
        "M2 the trade loses to the one-sided quote (the old order)",
        TARGET,
        "    if _usable(last):\n        return last\n\n    if _usable(bid) and not _usable(ask):",
        "    if _usable(bid) and not _usable(ask):",
        "RED",
    ),
    (
        "M3 the settled shell counts as a quote (ask 1.00 usable)",
        TARGET,
        "    return value is not None and 0.0 < value < 1.0",
        "    return value is not None and 0.0 < value <= 1.0",
        "RED",
    ),
    (
        "M4 the spread widens to a quarter",
        TARGET,
        "WIDE_SPREAD_DOLLARS = 0.10",
        "WIDE_SPREAD_DOLLARS = 0.25",
        "RED",
    ),
    (
        "M5 `previous_dollars` is no longer read (the trade after a quiet hour)",
        TARGET,
        '        candle.get("price"), "close_dollars", "mean_dollars", "previous_dollars"',
        '        candle.get("price"), "close_dollars", "mean_dollars"',
        "RED",
    ),
    (
        "M6 an unpriceable candle returns 0.0 instead of None",
        TARGET,
        "    if _usable(bid) and _usable(ask):\n        return (bid + ask) / 2.0\n    return None",
        "    if _usable(bid) and _usable(ask):\n        return (bid + ask) / 2.0\n    return 0.0",
        "RED",
    ),
    # NEGATIVE CONTROL. Renaming the local binding changes nothing a reader of
    # the policy could observe, so the guards must stay green — this is what
    # tells us the RED rows above are the policy failing and not the harness
    # reporting every edit as a catch.
    (
        "M7 a pure rename inside the function (negative control)",
        TARGET,
        "    last = _dollars(",
        "    traded = _dollars(",
        "GREEN",
    ),
]


def run_guards() -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *GUARDS, "-q", "--no-header"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
    )
    last = proc.stdout.strip().splitlines()[-1] if proc.stdout else ""
    return proc.returncode, last


def main() -> int:
    code, line = run_guards()
    print(f"CONTROL (unmutated): exit {code} — {line}")
    if code != 0:
        print("!! the control run is already red; nothing below means anything")
        return 2

    results = []
    for label, rel, old, new, expect in MUTATIONS:
        target = BACKEND / rel
        src = target.read_text()
        n = src.count(old)
        if n != 1:
            print(f"{label}: SUBSTITUTION NOT UNIQUE ({n} occurrences) — skipped")
            results.append((label, expect, "SKIPPED"))
            continue

        backup = pathlib.Path(tempfile.gettempdir()) / f"cal1084-{target.name}.bak"
        shutil.copyfile(target, backup)
        assert backup.exists() and backup.stat().st_size == len(src.encode()), (
            f"{label}: backup was not written — refusing to mutate"
        )

        try:
            mutated = src.replace(old, new)
            # M7 renames the binding; its two later reads must move with it or
            # the "pure rename" is really a NameError, which would read as a
            # catch the policy did not make.
            if new == "    traded = _dollars(":
                mutated = mutated.replace("_usable(last)", "_usable(traded)").replace(
                    "return last", "return traded"
                )
            target.write_text(mutated)
            code, line = run_guards()
            got = "RED" if code != 0 else "GREEN"
            mark = "ok " if got == expect else "!! "
            print(f"{mark}{label}: expected {expect}, got {got} — {line}")
            results.append((label, expect, got))
        finally:
            shutil.copyfile(backup, target)
            assert target.read_text() == src, f"{label}: RESTORE FAILED"
            backup.unlink()

    code, line = run_guards()
    print(f"CONTROL (restored): exit {code} — {line}")
    bad = [r for r in results if r[1] != r[2]]
    print(
        f"\n{len(results) - len(bad)}/{len(results)} mutations behaved as expected; "
        f"restored control exit {code}"
    )
    for label, expect, got in bad:
        print(f"  MISMATCH {label}: expected {expect}, got {got}")
    return 0 if not bad and code == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
