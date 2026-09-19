"""#4079 gap 3 — a stored move is never the only record of itself.

`update_max_movement`'s statement A4 is the only thing in the system that can
say "this row did not travel that far today". It asks the question of
`futures_odds_snapshots`, through a lateral aggregate bounded to the movement
window, and it declines any outcome whose window holds no rows::

    AND obs.lo IS NOT NULL          -- "we never looked" is not "it never went there"

That clause is correct and `test_a_row_we_never_observed_in_the_window_is_left_to_the_age_sweep`
(real Postgres) pins it. But it has a consequence nothing pinned: **an outcome
that carries a delta and no observation is unjudgeable.** A4 skips it, A only
reaches it once it goes 24 h untouched, and until then the card names a mover
on a claim no instrument in the codebase can check. That is the residual the
revision-A package filed as gap 3 — "a missing observation still authorises a
claim".

## Why that population is empty today, and it is not luck

Every writer that can STORE a non-null `probability_change_24h` records a
`FuturesOddsSnapshot` for the same outcome in the same pass — Kalshi's 2-hourly
poll (`_poll_kalshi_markets`), both Polymarket sockets (`_process_event_batch`),
the dormant odds_api futures poll (`_poll_futures_odds`), and the delta-blind
price refresher (`_write_prices`). The delta and the evidence for it are born
together, so A4's window can never be empty for a row whose delta is inside it.

**Measured on production 2026-09-19 06:50–06:58Z**, against the served page
rather than the table: of 48 movement chips at or above the card floor on
`/api/feed?limit=100`, **48 were judgeable, 0 unobserved, 0 declined on the
foreign-scale guard, 0 unsupportable**. Fleet-wide at the same floor over open
markets: 2,939 in scope, **0 unobserved**. Gap 3 has no population because of
the pairing above, not because the sweep is generous.

## What this file is for

The pairing is an emergent property of four unrelated writers, held together by
nothing. A fifth writer — or an edit that moves a snapshot insert out of a
branch — reopens gap 3 **silently**: no test reddens, no counter moves, A4 goes
blind on exactly those rows, and the only symptom is a card naming a mover that
nothing can contradict. This is the test that reddens instead.

## What it proves, and what it does not

It proves the CLASS: a delta write site in `app/tasks/**` sits in a function
that also writes an observation. It does not prove per-row pairing, per-branch
pairing, or one transaction — a function could insert its snapshot on a path the
delta write does not take. The row-level claim is the production read above, and
`tests/integration/test_movement_window_pg.py` is where A4's own behaviour on
rows is proved. A static guard is the right instrument for "a new writer
appeared", which is the failure this is aimed at, and the wrong one for "this
row has evidence".

Clearing is exempt, and that is the semantics rather than a carve-out: writing
`None` retires a claim, and retiring a claim needs no evidence. Five of the ten
sites are clears (`datagolf` ×2, `prediction_market_matching`, `kalshi`'s
linked-game refresher, `futures.py`'s null-out).
"""

from __future__ import annotations

import ast
import pathlib

import pytest

TASKS_DIR = pathlib.Path(__file__).resolve().parent.parent / "app" / "tasks"

#: The observation table a delta write must be accompanied by.
OBSERVATION = "FuturesOddsSnapshot"

#: The verbs that WRITE one. `sa_delete` is deliberately not among them, and it
#: is the reason this is an AST test rather than a substring one: the first
#: draft asked whether the function text mentioned `FuturesOddsSnapshot` at all,
#: and `_poll_kalshi_markets` mentions it four times — an import, an orphan
#: `sa_delete(...)`, a comment and the insert. Deleting that function's only
#: insert left the guard GREEN (mutation run 2026-09-19: 2 of 4 mutants
#: survived, both of them the real regression this file exists to catch).
INSERT_VERBS = {"pg_insert", "insert"}

#: Every site that STORES a delta today, as ``module::function``. Membership is
#: asserted in both directions on purpose: a new writer must be looked at by a
#: person, because "does it write a snapshot too?" is the question this whole
#: file exists to force. Adding a line here without adding the snapshot insert
#: still fails :func:`test_every_stored_delta_is_born_beside_its_own_observation`.
KNOWN_STORING_WRITERS = {
    "futures.py::_poll_futures_odds",
    "futures_price_refresh.py::_write_prices",
    "kalshi.py::_poll_kalshi_markets",
    "polymarket.py::_process_event_batch",
}


class _Site:
    def __init__(self, module: str, function: str, line: int, clears: bool, paired: bool):
        self.module = module
        self.function = function
        self.line = line
        self.clears = clears
        self.paired = paired

    @property
    def key(self) -> str:
        return f"{self.module}::{self.function}"

    def __repr__(self) -> str:  # pragma: no cover — only ever read in a failure
        verb = "clears" if self.clears else "stores"
        return f"{self.module}:{self.line} {self.function} ({verb}, paired={self.paired})"


def _delta_write_sites(source: str, module: str) -> list[_Site]:
    """Every place `source` assigns `probability_change_24h`, by AST.

    Four shapes reach this column and all four are live in the tree, which is
    why none of them may be dropped: a dict literal key (`kalshi`'s
    ``update_set``), a subscript assignment onto a dict built earlier
    (`polymarket`'s ``over_update[...]``), an ORM attribute store
    (`futures.py`'s ``existing.probability_change_24h``) and a call keyword
    (`futures_price_refresh`'s ``sa_update(...).values(...)``).

    A regex over the same text finds all four and also finds the column inside
    comments, docstrings, raw SQL and read-only comparisons — `app/tasks` holds
    more than twenty of those. The AST is not caution here, it is the only way
    to separate a write from a mention.
    """
    tree = ast.parse(source)
    functions = [
        n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    def enclosing(line: int):
        best = None
        for fn in functions:
            if fn.lineno <= line <= (fn.end_lineno or fn.lineno):
                if best is None or fn.lineno > best.lineno:
                    best = fn
        return best

    found: list[_Site] = []

    def writes_an_observation(fn) -> bool:
        """Does `fn` INSERT a snapshot row — not merely name the table?

        Two shapes are accepted because both are real: the Core upsert every
        venue poll uses (``pg_insert(FuturesOddsSnapshot).values(...)``) and an
        ORM construction handed to ``session.add``. A ``sa_delete`` of the same
        table is not an observation and must not answer this question.
        """
        if fn is None:
            return False
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            verb = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr if isinstance(func, ast.Attribute) else None
            )
            if verb == OBSERVATION:
                return True  # FuturesOddsSnapshot(...) for session.add
            if (
                verb in INSERT_VERBS
                and node.args
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == OBSERVATION
            ):
                return True
        return False

    def record(line: int, value: ast.AST) -> None:
        fn = enclosing(line)
        found.append(
            _Site(
                module=module,
                function=fn.name if fn is not None else "<module>",
                line=line,
                clears=isinstance(value, ast.Constant) and value.value is None,
                paired=writes_an_observation(fn),
            )
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "probability_change_24h":
                    record(key.lineno, value)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.slice, ast.Constant)
                    and target.slice.value == "probability_change_24h"
                ):
                    record(target.lineno, node.value)
                if (
                    isinstance(target, ast.Attribute)
                    and target.attr == "probability_change_24h"
                ):
                    record(target.lineno, node.value)
        if isinstance(node, ast.keyword) and node.arg == "probability_change_24h":
            record(node.value.lineno, node.value)

    return found


def _all_sites() -> list[_Site]:
    sites: list[_Site] = []
    for path in sorted(TASKS_DIR.rglob("*.py")):
        text = path.read_text()
        if "probability_change_24h" not in text:
            continue
        sites.extend(_delta_write_sites(text, path.name))
    return sites


# ---------------------------------------------------------------------------
# The claim
# ---------------------------------------------------------------------------


def test_every_stored_delta_is_born_beside_its_own_observation() -> None:
    """THE gate. A writer that stores a move must record the move it saw.

    A site that fails this is not a style problem: its rows enter A4's scope
    (`probability_change_24h IS NOT NULL`, above the card floor, open market)
    and leave it again unjudged, because the lateral finds nothing and
    `obs.lo IS NOT NULL` declines them. They then sit on cards, naming a mover,
    until the age sweep retires them up to 24 hours later.
    """
    orphans = [s for s in _all_sites() if not s.clears and not s.paired]

    assert orphans == [], (
        "a writer stores `probability_change_24h` without recording a "
        f"{OBSERVATION} in the same function: {orphans}. A4 cannot judge those "
        "rows — `obs.lo IS NOT NULL` skips them — so the claim they make is "
        "unfalsifiable until the 24-hour age sweep reaches it. Either write the "
        "snapshot beside the delta (what the other writers do), or store no "
        "delta at all: `None` is exempt, because retiring a claim needs no "
        "evidence."
    )


def test_the_set_of_storing_writers_is_the_one_that_was_looked_at() -> None:
    """A new delta writer is a person's decision, not a diff that slips by.

    Both directions. An ADDED writer fails because nobody has asked whether its
    rows are judgeable; a REMOVED one fails because this file would otherwise go
    on passing while proving less and less, which is how a guard becomes
    decorative.
    """
    live = {s.key for s in _all_sites() if not s.clears}

    assert live == KNOWN_STORING_WRITERS, (
        "the set of functions that STORE a 24-hour move changed.\n"
        f"  new, unreviewed : {sorted(live - KNOWN_STORING_WRITERS)}\n"
        f"  gone            : {sorted(KNOWN_STORING_WRITERS - live)}\n"
        "If it is new: check it writes a snapshot for the same outcome in the "
        "same pass (the test above), then add it here. If it is gone: delete "
        "the line. Do not relax the test above to make this pass."
    )


# ---------------------------------------------------------------------------
# The instrument. A guard that cannot fail proves nothing about the tree.
# ---------------------------------------------------------------------------


def test_the_detector_finds_the_writers_that_are_actually_there() -> None:
    """Anti-vacuity: an empty scan would make both tests above pass silently.

    A renamed column, a moved package, a `rglob` that stops matching — each
    turns the gate into `[] == []`. The counts are deliberately floors and not
    exact: the shapes churn, the existence of the population does not.
    """
    sites = _all_sites()

    assert len(sites) >= 10, f"the AST scan found almost nothing: {sites}"
    assert len({s.module for s in sites}) >= 5, (
        f"delta writes are spread over at least five task modules; scan saw "
        f"{sorted({s.module for s in sites})}"
    )
    assert any(s.clears for s in sites), "no clearing site found — the exemption is untested"
    assert any(not s.clears for s in sites), "no storing site found — the gate is vacuous"


@pytest.mark.parametrize(
    "source,expect_orphan",
    [
        # A new writer, delta stored, no observation. THE regression.
        (
            "async def _poll_new_venue(session):\n"
            "    await session.execute(update(FuturesOutcome).values(\n"
            "        probability_change_24h=prob - FuturesOutcome.current_probability))\n",
            True,
        ),
        # The same writer, doing what the four real ones do.
        (
            "async def _poll_new_venue(session):\n"
            "    await session.execute(update(FuturesOutcome).values(\n"
            "        probability_change_24h=prob - FuturesOutcome.current_probability))\n"
            "    await session.execute(pg_insert(FuturesOddsSnapshot).values(\n"
            "        outcome_id=outcome_id, probability=prob))\n",
            False,
        ),
        # Retiring a claim. No evidence owed, so no observation owed.
        (
            "async def _withdraw(session):\n"
            "    outcome.probability_change_24h = None\n",
            False,
        ),
        # A dict-literal writer, the `kalshi` shape, unpaired.
        (
            "async def _poll(session):\n"
            "    update_set = {'probability_change_24h': prob - old}\n",
            True,
        ),
        # THE MUTANT THAT SURVIVED THE FIRST DRAFT. The function names the
        # table three times — import, comment, delete — and inserts nothing.
        # A substring test calls this paired; it is the exact shape of
        # `_poll_kalshi_markets` with its one insert removed.
        (
            "async def _poll(session):\n"
            "    # FuturesOddsSnapshot rows for dead outcomes are dropped here\n"
            "    await session.execute(sa_delete(FuturesOddsSnapshot).where(\n"
            "        FuturesOddsSnapshot.outcome_id.in_(orphans)))\n"
            "    update_set = {'probability_change_24h': prob - old}\n",
            True,
        ),
        # An ORM construction handed to session.add is an observation too.
        (
            "async def _poll(session):\n"
            "    update_set = {'probability_change_24h': prob - old}\n"
            "    session.add(FuturesOddsSnapshot(outcome_id=1, probability=prob))\n",
            False,
        ),
        # A mention is not a write: comparison, comment and raw SQL must not
        # register, or the gate fires on the sweeps that READ the column.
        (
            "async def _sweep(session):\n"
            "    # probability_change_24h is a per-write delta\n"
            "    await session.execute(text('SET probability_change_24h = NULL'))\n"
            "    rows = [o for o in outcomes if o.probability_change_24h is not None]\n",
            False,
        ),
    ],
)
def test_the_detector_can_actually_fail(source: str, expect_orphan: bool) -> None:
    """The checker run against sources whose answer is known by construction.

    Without this the gate is a claim about `app/tasks` AND an unexamined claim
    about the checker. The fourth case is the one that matters most: it is the
    shape a new venue poll is most likely to take, and it must be refused.
    """
    sites = _delta_write_sites(source, "synthetic.py")
    orphans = [s for s in sites if not s.clears and not s.paired]

    assert bool(orphans) is expect_orphan, (
        f"the detector answered {bool(orphans)} for a source whose answer is "
        f"{expect_orphan} by construction. sites={sites}"
    )
