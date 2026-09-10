#!/usr/bin/env python3
"""#4745 (CAL-P1086) mutation battery — does each guard catch what it claims?

Run from the repo root or anywhere; paths are absolute. Each mutation: back the
file up as its OWN statement and assert the backup exists (CAL-P1075's banked
lesson — `cd x && cp` short-circuits when the shell is already in `x`, the
backup is never written, and the mutations stack silently until the control run
reads as a broken fix); substitute with an asserted occurrence count; run the
guards; restore; assert the file is byte-identical before the next one.

WHAT THIS CANNOT REACH, said out loud. The real-Postgres gate
(`tests/integration/test_repair_kalshi_empty_book_openings_1086_real_postgres.py`)
skips on every machine an agent can use — `initdb` cannot take the postmaster
lock in the sandbox — so every mutation below is scored against the guards that
RUN here. Mutations aimed only at behaviour the integration gate observes are
marked SKIPPED-NO-PG and are scored by CI, not by this battery. Reporting them
as survivors would be a lie in the other direction.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"

GUARDS = [
    "tests/test_repair_kalshi_empty_book_openings_1086.py",
    "tests/test_kalshi_empty_book.py",
    "tests/test_pg_gate_seed_completeness.py",
]

RAIL = "app/tasks/repair_kalshi_empty_book_openings.py"
TASK = "app/tasks/backfill_winners.py"
ROUTE = "app/routes/admin_repairs.py"

#: (label, relative path, old, new, expected verdict)
#: RED = the guards must fail. GREEN = they must NOT (a negative control).
MUTATIONS = [
    (
        "M1 the rail widens to is_winner",
        RAIL,
        "    SET opening_probability = s.honest_value,",
        "    SET is_winner = false,\n        opening_probability = s.honest_value,",
        "RED",
    ),
    (
        "M2 the rail forges a poller touch-stamp",
        RAIL,
        "        calibration_probability = CASE\n            WHEN fo.calibration_probability IS NOT NULL",
        "        last_updated = NOW(),\n        calibration_probability = CASE\n            WHEN fo.calibration_probability IS NOT NULL",
        "RED",
    ),
    (
        "M3 the provenance clause is dropped",
        RAIL,
        "      AND fo.opening_probability = bad.probability\n",
        "",
        "RED",
    ),
    (
        "M4 the shipped predicate is restated instead of imported",
        RAIL,
        "_GUARD_ON_EARLIEST = lone_ask_on_empty_book_sql(\"bad\")",
        "_GUARD_ON_EARLIEST = (\"(bad.bookmaker = 'kalshi' AND COALESCE(bad.yes_bid, -1) = 0\"\n"
        "                      \" AND COALESCE(bad.last_price, 0) = 0\"\n"
        "                      \" AND COALESCE(bad.yes_ask, 0) > 0.5)\")",
        "RED",
    ),
    (
        "M5 the replacement takes the LAST honest snapshot, not the first",
        RAIL,
        "          AND NOT {_GUARD_ON_CANDIDATE}\n        ORDER BY fos.captured_at ASC",
        "          AND NOT {_GUARD_ON_CANDIDATE}\n        ORDER BY fos.captured_at DESC",
        "RED",
    ),
    (
        "M6 a threshold of the rail's own creeps in",
        RAIL,
        "    if honest is None:\n        return \"withdraw\", None, None",
        "    if honest is None:\n        return \"withdraw\", None, None\n    if honest < 0.02:\n        return \"withdraw\", None, None",
        "RED",
    ),
    (
        "M7 the backup overwrites an existing row",
        RAIL,
        "    ON CONFLICT (outcome_id) DO NOTHING",
        "    ON CONFLICT (outcome_id) DO UPDATE SET backed_up_at = NOW()",
        "RED",
    ),
    (
        "M8 the apply proceeds on an incomplete backup",
        RAIL,
        "    if missing:\n        await session.rollback()",
        "    if False:\n        await session.rollback()",
        "RED",
    ),
    (
        "M9 the restore silently reports zero instead of refusing",
        RAIL,
        "        return {\n            \"issue\": ISSUE,\n            \"terminal\": \"refused_no_backup\",",
        "        return {\n            \"issue\": ISSUE,\n            \"terminal\": \"restored\",",
        "RED",
    ),
    (
        "M10 the restore forgets one of the three columns",
        RAIL,
        "    SET opening_probability = b.opening_probability,\n        opening_source = b.opening_source,",
        "    SET opening_probability = b.opening_probability,",
        "RED",
    ),
    (
        "M11 the backup schema is hand-typed instead of inherited",
        RAIL,
        "    SELECT fo.id AS outcome_id,\n           fo.opening_probability,\n           fo.opening_source,\n           fo.calibration_probability,\n           NOW() AS backed_up_at\n    FROM futures_outcomes fo\n    WHERE false",
        "    SELECT fo.id AS outcome_id,\n           fo.opening_probability::NUMERIC(5,4) AS opening_probability,\n           fo.opening_source,\n           fo.calibration_probability,\n           NOW() AS backed_up_at\n    FROM futures_outcomes fo\n    WHERE false",
        "RED",
    ),
    (
        "M12 Phase 0c loses the guard that keeps a withdrawal withdrawn",
        TASK,
        "              AND NOT {lone_ask_on_empty_book_sql(\"fos\")}\n            ORDER BY fos.captured_at ASC",
        "            ORDER BY fos.captured_at ASC",
        "RED",
    ),
    (
        "M13 Phase 0c is inlined back into the task body",
        TASK,
        "                r = await session.execute(text(PHASE_0C_REPAIR_SQL))",
        "                r = await session.execute(text(f\"\"\"\n                        WITH first_snaps AS (\n                            SELECT 1\n                        )\n                        UPDATE futures_outcomes fo SET opening_probability = 1\n                    \"\"\"))",
        "RED",
    ),
    (
        "M14 the restore name is dropped from the registry",
        ROUTE,
        "    \"kalshi-empty-book-openings-restore\": (\n        \"app.tasks.repair_kalshi_empty_book_openings\",\n        \"restore\",\n    ),",
        "",
        "RED",
    ),
    (
        "M15 the rail is registered but omitted from the docstring catalog",
        ROUTE,
        "             | kalshi-empty-book-openings\n             | kalshi-empty-book-openings-restore }",
        " }",
        "RED",
    ),
    # NEGATIVE CONTROLS. A battery in which every mutation is red proves the
    # guards are loud, not that they are aimed. These two change the module in
    # ways that are genuinely none of the guards' business.
    (
        "M16 a decimal in PROSE only (negative control)",
        RAIL,
        "ISSUE = \"#4745\"",
        "# The specimen published 0.98 against a 0.084 realised rate.\nISSUE = \"#4745\"",
        "GREEN",
    ),
    (
        "M17 the page size changes (negative control)",
        RAIL,
        "DEFAULT_LIMIT = 2000",
        "DEFAULT_LIMIT = 1500",
        "GREEN",
    ),
]


def run_guards() -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *GUARDS, "-q", "--no-header", "-x"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
    )
    last = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
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

        # The backup is its own statement, and its existence is asserted.
        backup = pathlib.Path(tempfile.gettempdir()) / f"cal1086-{target.name}.bak"
        shutil.copyfile(target, backup)
        assert backup.exists() and backup.stat().st_size == len(src.encode()), (
            f"{label}: backup was not written — refusing to mutate"
        )

        try:
            target.write_text(src.replace(old, new))
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
