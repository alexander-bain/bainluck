"""CAL-P1002D — the committed ledger is a SUPERSET, and ``--build`` cannot quietly shrink it.

WHY THIS FILE EXISTS
====================

``calibration_sigma_ledger.py --build`` **replaces** the ledger with exactly the
artifacts named on its command line. It is not an upsert, and nothing in the
tool, its ``--help``, or the runbook in ``PARKED-MEASUREMENTS.md`` says so.

That was found the hard way while landing this branch. The runbook for the six
``odds_api_bookmaker`` cells reads:

    python3 backend/scripts/calibration_sigma_ledger.py --build \\
        artifacts/cal-p1002/sigma-bookmaker-*.json

Run exactly as written, it emits a cheerful ``wrote … (6 cells from 6
artifacts)`` and **deletes the other fourteen entries** — including
``kalshi/golf``, the single cell whose verdict D62 moved. D62's entire ship is
"the needle reads 35/48 where it read 34/48, and one cell moves"; following the
next task's runbook to the letter would have silently put that cell back on the
queue while every test stayed green, because no test asserted that an entry
that used to be there still is.

That is the defect class this file guards, and it is the ledger form of the
"partial revert masks the defect" trap: a rebuild that drops rows looks
identical to a rebuild that never had them.

WHAT IS PINNED, AND WHY EACH ONE
================================

1. **Every cell any prior ship depends on is still in the committed ledger.**
   Named individually rather than counted, so the failure message says *which*
   cell went missing rather than "expected 20, got 6".
2. **The count is a floor, never an equality.** A future measurement ADDING a
   cell must not turn this file red — only a REMOVAL may. An equality here
   would make the guard a chore that gets bumped without being read, which is
   how a ratchet stops catching anything.
3. **The ledger validates.** ``validate()`` recomputes each sigma from the
   stored SE, so a hand-written entry — which the runbook explicitly forbids —
   files as ``ledger_incoherent`` and is caught here rather than in production.

These assert against the REAL committed ledger, not a fixture. A fixture would
pass while the shipped file was empty, which is precisely the failure that
``test_calibration_sigma_ledger_path_p129.py`` exists to prevent on the path
axis; this is the same argument on the contents axis.
"""

from __future__ import annotations

import pytest

from app.utils.calibration_sigma import LEDGER_PATH, load, validate

# The fourteen entries that predate this branch, plus the six it adds.
# Listed rather than counted so a failure names the casualty.
CELLS_BEFORE_THIS_BRANCH = (
    "kalshi/crypto",
    "kalshi/economics",
    "kalshi/entertainment",
    "kalshi/golf",
    "kalshi/tech",
    "polymarket/baseball",
    "polymarket/basketball",
    "polymarket/cricket",
    "polymarket/economics",
    "polymarket/esports",
    "polymarket/golf",
    "polymarket/hockey",
    "polymarket/soccer",
    "polymarket/tech",
)

CELLS_ADDED_BY_THIS_BRANCH = (
    "odds_api_bookmaker/baseball_mlb_preseason",
    "odds_api_bookmaker/basketball_euroleague",
    "odds_api_bookmaker/basketball_nba",
    "odds_api_bookmaker/basketball_wnba",
    "odds_api_bookmaker/basketball_wncaab",
    "odds_api_bookmaker/icehockey_nhl",
)

ALL_REQUIRED_CELLS = CELLS_BEFORE_THIS_BRANCH + CELLS_ADDED_BY_THIS_BRANCH


@pytest.fixture(scope="module")
def committed_ledger() -> dict:
    return load(LEDGER_PATH)


@pytest.mark.parametrize("cell", ALL_REQUIRED_CELLS)
def test_every_required_cell_is_present(committed_ledger: dict, cell: str) -> None:
    """A ``--build`` that omits an artifact must not silently drop its cell.

    This is the guard. ``--build`` replaces rather than upserts, so the only
    thing standing between a partial re-run and a reverted ship is an assertion
    that names the cells by hand.
    """
    assert cell in committed_ledger["entries"], (
        f"{cell} is missing from the committed ledger. If you just ran "
        f"`calibration_sigma_ledger.py --build`, note that it REPLACES the "
        f"ledger with exactly the artifacts you named — it does not merge. "
        f"Re-run it with every artifact listed in this file's docstring."
    )


def test_kalshi_golf_specifically_survives(committed_ledger: dict) -> None:
    """D62's ship is one moved cell, and this is that cell.

    Split out from the parametrised case deliberately: if this one line goes
    red, the message should say *the ship reverted*, not *a cell is missing*.
    """
    assert "kalshi/golf" in committed_ledger["entries"], (
        "kalshi/golf is the single cell D62's needle move depends on "
        "(34/48 -> 35/48). Its absence silently reverts that ship."
    )


def test_entry_count_is_a_floor_not_an_equality(committed_ledger: dict) -> None:
    """Adding a measurement must never redden this file; removing one must."""
    assert len(committed_ledger["entries"]) >= len(ALL_REQUIRED_CELLS)


def test_the_committed_ledger_validates(committed_ledger: dict) -> None:
    """Every sigma recomputes from its stored SE.

    The runbook forbids hand-written entries because ``validate`` recomputes
    each sigma and a hand-built row files as ``ledger_incoherent``. This proves
    the shipped file actually clears that bar rather than merely being
    well-formed JSON.
    """
    assert validate(committed_ledger) == []
