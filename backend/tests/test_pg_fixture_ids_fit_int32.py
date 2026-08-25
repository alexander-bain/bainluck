"""Guard: a test fixture's primary-key sentinel must fit in int32.

THE CLASS THIS CATCHES, and why it needed a guard rather than a fix.

`events.id` is `Mapped[int]`, which SQLAlchemy renders as INTEGER, not BIGINT —
ceiling 2147483647. A fixture that seeds an id above that ceiling cannot INSERT
and cannot DELETE: asyncpg raises `DataError: value out of int32 range` before
the query reaches Postgres. The test does not fail on its assertion; it fails on
its own scaffolding, which makes the traceback point at `_cleanup` rather than
at the constant that is actually wrong.

WHAT MADE IT EXPENSIVE IS *WHERE* IT FAILS. These `*_pg.py` modules are skipped
unless `SEARCH_TEST_DATABASE_URL` (or `CALIBRATION_TEST_DATABASE_URL`) is set,
and there is no local Postgres in the agent sandbox — `initdb` dies on `shmget`.
So the whole class reports "skipped" on every machine a human or an agent
actually runs, and the CI `search-recall` job is its only reader. On 2026-08-25
that meant a full local backend suite of 19,709 passed over a tree carrying the
bug, a GREEN cert that never ran the real-Postgres gate either, and master going
red with the `deploy` job SKIPPED — holding four already-certified merges out of
production behind a fixture typo. Two separate pushes were needed because the
first fix was scoped to the one file CI happened to name.

This guard is deliberately a PLAIN TEXT SCAN and not a database test, because a
database test would inherit exactly the skip that hid the defect. It runs
everywhere, needs nothing, and fails on the constant instead of on the cleanup.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

#: PostgreSQL INTEGER. `events.id`, `sports.id`, `futures_markets.id` and friends
#: are all `Mapped[int]` -> INTEGER; nothing in the schema promises BIGINT.
INT32_MAX = 2147483647

TESTS_ROOT = Path(__file__).resolve().parent

#: Module-level constants that name themselves as row ids. Matched by NAME on
#: purpose: an arbitrary large literal may legitimately be a millisecond
#: timestamp, a Polymarket token id (which is a *string*), or a Decimal's digits,
#: and flagging those would make this guard noise that people learn to skip.
_ID_CONSTANT = re.compile(
    r"^\s*((?:[A-Z0-9_]+_)?(?:EVENT|SPORT|MARKET|OUTCOME|TEAM|SNAPSHOT)_ID[A-Z0-9_]*)"
    r"\s*=\s*(\d+)\s*$"
)


def _id_constants() -> list[tuple[Path, int, str, int]]:
    found: list[tuple[Path, int, str, int]] = []
    for path in sorted(TESTS_ROOT.rglob("*.py")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):  # pragma: no cover - unreadable file
            continue
        for lineno, line in enumerate(lines, 1):
            match = _ID_CONSTANT.match(line)
            if match:
                found.append((path, lineno, match.group(1), int(match.group(2))))
    return found


def test_the_scan_actually_finds_id_constants() -> None:
    """The guard's own floor.

    A regex that silently stops matching would leave this file passing over
    nothing at all, which is the failure mode of every scan-based test — and is
    gotcha #53's shape: "found no violations" and "looked at no files" produce
    an identical green.
    """
    found = _id_constants()
    #: 10 at the time of writing (2026-08-25). The floor is deliberately well
    #: below that: its job is to catch the pattern drifting to ~zero, NOT to
    #: ratchet on the exact count — a floor set to today's number reds the guard
    #: the first time someone legitimately deletes a fixture, which teaches
    #: people to lower it, which is how a floor stops meaning anything.
    assert len(found) >= 6, (
        f"the id-constant scan matched only {len(found)} constants across "
        f"{TESTS_ROOT}, which means the pattern has drifted away from how "
        "fixtures are written and this guard is now passing over nothing."
    )


@pytest.mark.parametrize("ceiling", [INT32_MAX])
def test_no_test_fixture_seeds_a_row_id_above_the_int32_ceiling(ceiling: int) -> None:
    over = [(p, n, name, value) for p, n, name, value in _id_constants() if value > ceiling]
    assert not over, "\n".join(
        [
            "These fixture row ids exceed PostgreSQL INTEGER and cannot be "
            f"inserted or deleted (ceiling {ceiling}):",
            *(
                f"  {p.relative_to(TESTS_ROOT)}:{n}  {name} = {value}"
                f"  ({value / ceiling:.1f}x over)"
                for p, n, name, value in over
            ),
            "",
            "asyncpg raises DataError before the statement reaches Postgres, so "
            "the traceback will point at your INSERT or at _cleanup rather than "
            "at the constant. Drop a digit. If you genuinely need a value this "
            "large, the column has to be BIGINT first — and that is a migration, "
            "not a test edit.",
        ]
    )
