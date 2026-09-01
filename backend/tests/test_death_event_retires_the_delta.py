"""CERT-627 — a writer that KILLS an outcome must retire its movement delta.

## The rule

Three task-side writers mark a futures outcome dead without any market ever
settling it: `tasks/futures.py` zeroes an outcome that vanished from The Odds
API response, and `tasks/datagolf.py` nulls one that vanished from a DataGolf
field (twice — pre-tournament and live). Each of them writes
`last_updated = now` in the same breath.

That stamp is the one `update_max_movement`'s age sweep expires deltas on. So a
writer that refreshes it while leaving `probability_change_24h` alone hands the
row a fresh alibi: it is dead, its price is 0 or NULL, and the age sweep will
never touch it again. `/api/futures/movers` goes on ranking the market it
belongs to, off a delta measured when the outcome was still alive.

The graded sweep (statement A2) cannot cover these: they are not graded — no
`resolution_source` is set, because nothing resolved, the row simply stopped
being offered. Measured on production 2026-08-31 this population is small — 772
rows, 2 of them claiming >= 10 points — but it REGENERATES on every poll, and it
is the population CERT-627 named by hand. Small and self-renewing is exactly the
shape that gets fixed once and silently reverted later.

## Why this file is an AST scan and not a call

Every one of these sites is a few statements deep inside a multi-hundred-line
polling task that opens HTTP sessions and a database before it reaches them.
Driving the real function to touch them costs more fidelity than it buys. What
is worth pinning is structural and local: **in any block where an outcome's
price is killed and its stamp refreshed, the delta is retired too.**

⚠️ The scan RAISES when it finds no subject. A source-text guard that quietly
matches nothing is the standard way this class of test goes vacuous — it keeps
passing while the code it describes is deleted underneath it — so "I found no
death-event block" is a FAILURE here, never a pass.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "app"

#: (module, how many death-event blocks it must contain). The counts are part of
#: the contract: a new stale-killing site has to come here and be admitted, and
#: a deleted one has to be noticed rather than shrugged off.
DEATH_EVENT_SITES = [
    (APP / "tasks" / "futures.py", 1),
    (APP / "tasks" / "datagolf.py", 2),
]

PRICE_FIELDS = {"current_probability"}
STAMP_FIELD = "last_updated"
DELTA_FIELD = "probability_change_24h"


def _is_dead_price(node: ast.AST) -> bool:
    """`= 0`, `= 0.0` or `= None` — the three ways these sites kill a price."""
    if isinstance(node, ast.Constant):
        return node.value is None or node.value == 0
    return False


def _attr_target(stmt: ast.stmt) -> tuple[str, str] | None:
    """('outcome', 'current_probability') for `outcome.current_probability = x`."""
    if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
        return None
    target = stmt.targets[0]
    if not isinstance(target, ast.Attribute) or not isinstance(target.value, ast.Name):
        return None
    return target.value.id, target.attr


def _death_event_blocks(tree: ast.AST) -> list[tuple[int, str, set[str]]]:
    """Every statement-list that kills a price AND refreshes the stamp.

    Returns (lineno, variable, attributes-assigned-to-that-variable-here).
    """
    found: list[tuple[int, str, set[str]]] = []
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if not isinstance(block, list):
                continue
            by_var: dict[str, set[str]] = {}
            killed: dict[str, int] = {}
            for stmt in block:
                hit = _attr_target(stmt)
                if hit is None:
                    continue
                var, attr = hit
                by_var.setdefault(var, set()).add(attr)
                if attr in PRICE_FIELDS and _is_dead_price(stmt.value):
                    killed[var] = stmt.lineno
            for var, lineno in killed.items():
                attrs = by_var[var]
                if STAMP_FIELD in attrs:
                    found.append((lineno, var, attrs))
    return found


@pytest.mark.parametrize(
    "path,expected",
    DEATH_EVENT_SITES,
    ids=[p.name for p, _ in DEATH_EVENT_SITES],
)
def test_a_killed_outcome_loses_its_movement_delta(path: Path, expected: int) -> None:
    source = path.read_text()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:  # pragma: no cover — a parse failure is a failure
        raise AssertionError(f"{path.name} does not parse, so this gate did not run: {exc}")

    blocks = _death_event_blocks(tree)

    # Vacuity guard FIRST: no subject means this test proved nothing.
    assert blocks, (
        f"{path.name}: found no block that both kills an outcome's price and "
        f"refreshes `{STAMP_FIELD}`. Either the stale-kill path moved and this "
        "scan is now inspecting nothing — which is how a source guard silently "
        "stops guarding — or it was deleted. Re-point it; do not delete it."
    )
    assert len(blocks) == expected, (
        f"{path.name}: expected {expected} death-event block(s), found "
        f"{len(blocks)} at lines {[b[0] for b in blocks]}. A NEW stale-kill site "
        "must be admitted here deliberately: confirm it retires the delta, then "
        "update the count in DEATH_EVENT_SITES."
    )

    for lineno, var, attrs in blocks:
        assert DELTA_FIELD in attrs, (
            f"{path.name}:{lineno} kills `{var}.current_probability` and refreshes "
            f"`{var}.{STAMP_FIELD}` but never clears `{var}.{DELTA_FIELD}`.\n\n"
            "That combination is CERT-627 exactly: the row is dead, but the "
            "refreshed stamp makes it permanently invisible to the age sweep in "
            "`update_max_movement`, so it keeps its last live delta forever and "
            "`/api/futures/movers` keeps ranking its market. The graded sweep "
            "cannot rescue it either — nothing resolved, so `resolution_source` "
            f"is NULL. Set `{var}.{DELTA_FIELD} = None` beside the price."
        )


def test_the_scan_can_tell_a_fixed_site_from_a_broken_one() -> None:
    """The detector earns its keep: it must FAIL the unfixed shape.

    Without this, `_death_event_blocks` could return blocks that always satisfy
    the assertion above and the parametrised test would pass on any input.
    """
    broken = ast.parse(
        "for k, existing in items:\n"
        "    if cond:\n"
        "        existing.current_probability = 0\n"
        "        existing.last_updated = now\n"
    )
    fixed = ast.parse(
        "for k, existing in items:\n"
        "    if cond:\n"
        "        existing.current_probability = 0\n"
        "        existing.last_updated = now\n"
        "        existing.probability_change_24h = None\n"
    )
    unrelated = ast.parse(
        "for k, existing in items:\n"
        "    existing.current_probability = 0.42\n"
        "    existing.last_updated = now\n"
    )

    broken_blocks = _death_event_blocks(broken)
    fixed_blocks = _death_event_blocks(fixed)

    assert len(broken_blocks) == 1, "the detector missed an unfixed death event"
    assert DELTA_FIELD not in broken_blocks[0][2], (
        "the detector reports the delta retired on a block that does not retire it"
    )
    assert len(fixed_blocks) == 1
    assert DELTA_FIELD in fixed_blocks[0][2], (
        "the detector cannot see the fix, so the real test passes for the wrong reason"
    )
    assert _death_event_blocks(unrelated) == [], (
        "a LIVE price write (0.42) was read as a death event — this scan would "
        "demand the delta be cleared on every ordinary poll"
    )
