"""#3879 — `price_observed_at`, the freshness clock, and the coupling that keeps
it honest.

The column answers "when did a writer last hold a REAL price for this outcome,
from the venue". Its two neighbours cannot: `last_updated` is written by
`backfill_winners` grading a row, and `price_changed_at` stands still on a price
that is read constantly and correctly does not move.

WHAT THIS FILE DEFENDS, in the order the defects would arrive:

  1. The three refusals in `price_observed_at_value` — asserted on RENDERED SQL,
     not on the Python that builds it. A stamp expression is only ever executed
     by Postgres, so a test that inspects the object graph and never looks at
     the text is testing a data structure.
  2. That every site writing the MOVEMENT stamp also writes the FRESHNESS stamp.
     This is the failure that costs the most and the one no unit test can see:
     the expressions are both right, and one file forgets to call one of them,
     so the column goes stale for a single provider while the other two look
     healthy. There is exactly one allowed exception and it is named.
  3. That the upsert INSERT arms are wired too, because a column wired only on
     the conflict arm reads NULL for every row its writer CREATES — and NULL is
     the value #3879's census counts.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from sqlalchemy.dialects import postgresql

from app.models import FuturesOutcome
from decimal import Decimal

from app.utils.price_change_stamp import (
    apply_observed_price,
    apply_unobserved_price,
    price_observed_at_insert,
    price_observed_at_value,
)

BACKEND = Path(__file__).resolve().parents[1]


def _sql(expr) -> str:
    """The expression as Postgres will actually receive it."""
    return str(
        expr.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


# ---------------------------------------------------------------------------
# 1. The three refusals
# ---------------------------------------------------------------------------


def test_a_real_price_stamps_the_observation() -> None:
    sql = _sql(price_observed_at_value(FuturesOutcome.price_observed_at, 0.42))
    assert "now()" in sql
    assert "greatest" in sql.lower()


def test_no_price_is_not_an_observation() -> None:
    """Refusal 1. The kalshi null-out must not read as a fresh look.

    Asserted on the rendered predicate rather than on a returned object: the
    guard is `NULL IS NOT NULL`, which Postgres evaluates to false, so the CASE
    falls to the ELSE and the stored stamp survives untouched. A leg the venue
    returned without a book keeps whatever age it had earned.
    """
    sql = _sql(price_observed_at_value(FuturesOutcome.price_observed_at, None))
    assert "CASE WHEN (NULL IS NOT NULL)" in sql, sql
    assert sql.endswith("ELSE futures_outcomes.price_observed_at END"), sql


def test_the_stamp_is_the_instant_observed_not_the_instant_written() -> None:
    """Refusal 2. A writer replaying history dates the price, not the import."""
    observed = dt.datetime(2026, 9, 1, 6, 53, 42, tzinfo=dt.timezone.utc)
    sql = _sql(
        price_observed_at_value(
            FuturesOutcome.price_observed_at, 0.42, observed_at=observed
        )
    )
    assert "2026-09-01 06:53:42" in sql, sql
    assert "now()" not in sql, "a historical replay must not stamp itself now()"


def test_the_stamp_never_moves_backwards() -> None:
    """Refusal 3, and the reason refusal 2's parameter is not a loaded gun.

    Without `GREATEST` an out-of-order backfill — a candlestick import landing
    after a live poll — would rewrite a current row as ancient. The floor is the
    stored value itself.
    """
    observed = dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)
    sql = _sql(
        price_observed_at_value(
            FuturesOutcome.price_observed_at, 0.42, observed_at=observed
        )
    )
    assert re.search(
        r"greatest\(futures_outcomes\.price_observed_at, '2020-01-01", sql
    ), sql


def test_greatest_not_python_max_so_a_first_observation_is_not_swallowed() -> None:
    """The reason this is SQL and not `max()` in Python.

    On a row that has never been observed the stored value is NULL. Postgres's
    `GREATEST` ignores NULL arguments and returns the incoming instant;
    Python's `max()` would raise, and a hand-rolled `or` chain is where somebody
    writes `max(None, ts)`. The expression must name `greatest` and must take
    the stored column as an argument — asserted together, because either half
    alone passes while the pair is wrong.
    """
    sql = _sql(price_observed_at_value(FuturesOutcome.price_observed_at, 0.42))
    assert "greatest(futures_outcomes.price_observed_at, now())" in sql, sql


# ---------------------------------------------------------------------------
# The INSERT half
# ---------------------------------------------------------------------------


def test_insert_half_stamps_a_priced_row() -> None:
    assert price_observed_at_insert(0.42) is not None


def test_insert_half_refuses_an_unpriced_row() -> None:
    """Same refusal 1, on the arm that has no stored value to fall back to."""
    assert price_observed_at_insert(None) is None


def test_insert_half_honours_an_observed_instant() -> None:
    observed = dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)
    assert price_observed_at_insert(0.42, observed_at=observed) is observed


# ---------------------------------------------------------------------------
# 2. The coupling census — the defect no unit test can see
# ---------------------------------------------------------------------------

#: The one site in the tree that carries the MOVEMENT stamp and deliberately
#: carries no FRESHNESS stamp, with the reason it is allowed to.
#:
#: `tasks/kalshi.py`'s unpriced-ticker null-out writes `current_probability =
#: None` to legs the venue returned without a book. That is a real write and a
#: real price change — a price going away IS a change — but it is not an
#: observation OF a price, and stamping it would let a leg unpriced for a month
#: report itself freshly observed.
#:
#: A count, not a boolean: if a second exception appears, this reds and somebody
#: has to justify it in writing rather than adding it to a set.
ALLOWED_MOVEMENT_ONLY_SITES = 1

_COMMENT = re.compile(r"#.*$", re.MULTILINE)
_DOCSTRING = re.compile(r'("""|\'\'\')(?:.|\n)*?\1')


def _code_only(src: str) -> str:
    """Source with comments and docstrings removed.

    A raw scan cannot tell a banned call from prose ABOUT the banned call, and
    this file's own subject is full of prose about both helper names — every
    call site here carries a `# #3879` comment. Documenting the rule must not be
    able to satisfy the rule.
    """
    return _COMMENT.sub("", _DOCSTRING.sub("", src))


def _task_sources() -> dict[str, str]:
    return {
        str(p.relative_to(BACKEND)): _code_only(p.read_text(encoding="utf-8"))
        for p in sorted((BACKEND / "app/tasks").rglob("*.py"))
    }


def test_comment_stripper_actually_strips() -> None:
    """The census's own instrument, checked before it is trusted.

    A stripper that silently returned its input would make every assertion
    below vacuous — they would all pass by finding the names in the comments.
    """
    src = '"""price_observed_at_value in a docstring."""\nx = 1  # price_observed_at_value\n'
    assert "price_observed_at_value" not in _code_only(src)


def test_every_movement_stamp_has_an_observation_stamp() -> None:
    """The coupling. One expression forgotten in one file is the real defect.

    Both stamps are written at the same sites from the same local variable, so
    a file that calls `price_changed_at_value` and never calls
    `price_observed_at_value` is a provider whose freshness column quietly stops
    advancing while the other providers look healthy — invisible to every unit
    test, and visible in the #3879 census only as a population that seems
    unreachable.
    """
    offenders = [
        rel
        for rel, src in _task_sources().items()
        if "price_changed_at_value(" in src and "price_observed_at_value(" not in src
    ]
    assert offenders == [], {
        "files_stamping_movement_but_not_freshness": offenders,
        "why": "#3879 — both stamps are written at the same sites; one without "
        "the other means this provider's freshness clock stops advancing",
    }


def test_the_movement_only_exception_is_still_exactly_one() -> None:
    """The null-out, counted rather than trusted.

    Sites are matched by the argument the movement stamp is given: a
    `price_changed_at_value(...)` whose new-price argument is the literal `None`
    is a price being REMOVED, and that is the only shape entitled to skip the
    freshness stamp.
    """
    pattern = re.compile(
        r"price_changed_at_value\(\s*[^)]*?,\s*[^)]*?,\s*None\s*,?\s*\)", re.S
    )
    found = sum(len(pattern.findall(src)) for src in _task_sources().values())
    assert found == ALLOWED_MOVEMENT_ONLY_SITES, (
        f"movement-stamp-with-no-price sites = {found}, expected "
        f"{ALLOWED_MOVEMENT_ONLY_SITES}. A new one is a new place a leg could "
        "claim a fresh observation of nothing — justify it here, do not bump "
        "the number."
    )


# ---------------------------------------------------------------------------
# 3. The INSERT arms are wired
# ---------------------------------------------------------------------------

#: `pg_insert(FuturesOutcome)` sites that write a price and are ALLOWED to skip
#: the freshness stamp, by the marker text that identifies each one.
#:
#: `kalshi.py`'s settled/gap create is the only member. It mints rows for
#: markets that already SETTLED, carrying the venue's final price — a real
#: price, but a historical one, and the block has no captured instant to pass as
#: `observed_at`. Stamping `now()` would date a settlement-era number to the
#: moment somebody happened to backfill it, which is refusal 2 exactly. #3879's
#: census excludes graded rows, so the omission costs the measurement nothing.
#:
#: Identified by a marker rather than a line number so the entry survives the
#: file moving, and named rather than counted so that adding a member requires
#: writing down which price is historical and why.
PRICED_INSERTS_EXEMPT = {
    "kalshi settled/gap create": "volume=int(m.volume) if m.volume is not None else None",
}

_PG_INSERT = "pg_insert(FuturesOutcome)"


def _priced_insert_blocks(src: str) -> list[str]:
    """Each `pg_insert(FuturesOutcome)` block that writes a REAL price.

    Block-scoped for the reason `test_futures_stamp_semantics` gives about its
    own crude first draft: a character window classifies by whatever happens to
    be nearby. The block ends at the conflict clause, which every one of these
    statements has.

    A site writing the literal `current_probability=None` is an UNPRICED
    creator — `kalshi.py` mints those deliberately for tickers the venue
    returned without a book — and owes no observation stamp, by refusal 1.
    """
    blocks = []
    for m in re.finditer(re.escape(_PG_INSERT), src):
        rest = src[m.end() : m.end() + 2500]
        end = rest.find(".on_conflict")
        block = rest[: end if end != -1 else len(rest)]
        if "current_probability=" not in block:
            continue
        if "current_probability=None" in block.replace(" ", ""):
            continue
        blocks.append(block)
    return blocks


def test_the_priced_insert_census_finds_something() -> None:
    """The instrument before the measurement.

    A parser whose block-end marker or price predicate stopped matching would
    return an empty list and every assertion below would pass by finding
    nothing. #3879 is an issue about a population that looked empty.
    """
    total = sum(len(_priced_insert_blocks(s)) for s in _task_sources().values())
    assert total >= 5, f"priced-insert parser found only {total} sites; it broke"


def test_every_priced_insert_stamps_the_observation() -> None:
    """A column wired only on the conflict arm reads NULL for every row its own
    writer creates.

    #3879's census reads NULL as "no price rail reaches this leg". Rows a rail
    reached on the way IN must not be counted there — that is the population
    being measured, diluted by the instrument. This caught two real misses on
    the way in: `kalshi.py`'s linked-game create and `polymarket.py`'s
    league-scan create, both of which write a live price and neither of which
    was wired by the first pass over the conflict arms.
    """
    offenders = []
    for rel, src in _task_sources().items():
        for block in _priced_insert_blocks(src):
            if "price_observed_at_insert(" in block:
                continue
            if any(marker in block for marker in PRICED_INSERTS_EXEMPT.values()):
                continue
            offenders.append({"file": rel, "head": " ".join(block.split())[:120]})
    assert offenders == [], {
        "priced_inserts_without_a_freshness_stamp": offenders,
        "why": "#3879 — an outcome CREATED with a price has been observed; "
        "leaving it NULL puts a reachable leg into the unreachable census",
    }


def test_the_exemption_still_matches_exactly_one_site() -> None:
    """An exemption that stops matching is an exemption that silently widens.

    If the marker text drifts, `test_every_priced_insert_stamps_the_observation`
    would start reporting the settled/gap create as an offender — noisy but
    safe. The dangerous direction is the other one: a marker generic enough to
    excuse a second site. Pinned at one.
    """
    for label, marker in PRICED_INSERTS_EXEMPT.items():
        hits = [
            rel
            for rel, src in _task_sources().items()
            for block in _priced_insert_blocks(src)
            if marker in block
        ]
        assert len(hits) == 1, f"exemption {label!r} matches {len(hits)} sites: {hits}"


# ---------------------------------------------------------------------------
# 4. The ORM writers — the census CERT-2302 found blind
# ---------------------------------------------------------------------------
#
# Sections 2 and 3 police `set_=` clauses and `pg_insert` blocks, which is every
# shape the first pass over this ship happened to look at. CERT-2302's finding:
# a writer that does `outcome.current_probability = prob` is neither, so it
# satisfies both censuses by not resembling them.
#
# The cost was not hypothetical. `tasks/futures.py` PASSED section 2 — it calls
# both helpers, at its upsert — while the `if existing:` branch of the same
# function, the path the Odds API takes for every outcome that already exists,
# wrote a real venue price and `last_updated` and stamped neither clock. That is
# the majority of that poll's writes. `tasks/datagolf.py` passed both sections
# by mentioning neither helper anywhere: pure ORM in both loops, four price-
# writing arms, no stamps.
#
# So this section asks the question at the level the defect lives at — a PATH,
# not a file — and it uses the AST rather than a regex because the thing being
# counted is an assignment to an attribute, which is a syntactic fact and not a
# string. A `_code_only` scan cannot tell `outcome.current_probability = prob`
# from the same characters inside an f-string or a SQL literal.

import ast  # noqa: E402  (kept beside the census it serves)

#: ORM price assignments that are NOT this lane's to rewire, by
#: `file:function`, with why.
#:
#: 🟢 EMPTY, AND THE EMPTINESS IS THE POINT. It held one entry — both sites in
#: `prediction_market_matching._poll_live_prediction_market_prices`, the
#: 2-minute realtime poll, parked because that file is lane1's under D39.
#: CERT-2354 blocked #3879's acceptance-1 on precisely that park: the arms wrote
#: a real venue price and `last_updated` while leaving the freshness clock NULL,
#: so a live-only observation could never refresh it. Fable-5 waived D39 for
#: that one function (Wed 2026-09-09 4:15am PT) and lane1b/102 made the repair
#: (`4157-LIVE-MATCHER-ADVANCES-THE-OBSERVATION-CLOCK`); both arms now go
#: through `apply_observed_price`, and the executed proof on a real server is
#: `tests/integration/test_live_poll_stamps_observation_clock_4157_real_postgres.py`.
#:
#: An entry added here is a defect parked at a boundary, never a justified
#: omission — it needs the owning lane, the handed-over patch and the measured
#: cost of the wait, as the retired one did.
#:
#: Keyed by function, not by line number, so an entry survives the file moving
#: — and an exact-set pin never carries a `file:line`, because a comment added
#: above the site reds the guard for a reason the guard does not mean.
ORM_PRICE_ASSIGNMENTS_NOT_OURS: dict[tuple[str, str], str] = {}

#: Assignments to a `current_probability` attribute that is not a
#: `FuturesOutcome` column at all. `tasks/event_chart_backfill.py` defines a
#: local row-shaped class and assigns its own field in `__init__`; there is no
#: database column within a mile of it.
_NON_ORM_RECEIVERS = {"self"}


def _task_trees() -> dict[str, ast.Module]:
    return {
        str(p.relative_to(BACKEND)): ast.parse(p.read_text(encoding="utf-8"))
        for p in sorted((BACKEND / "app/tasks").rglob("*.py"))
    }


def _enclosing_function(tree: ast.Module, line: int) -> str | None:
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno <= line <= (node.end_lineno or node.lineno):
                if best is None or node.lineno > best.lineno:
                    best = node
    return best.name if best else None


def _scan_for_orm_price_assignments(
    trees: dict[str, ast.Module],
) -> list[tuple[str, str, int]]:
    """Every `<x>.current_probability = ...` in `trees`, as
    (file, function, line), excluding non-ORM receivers.

    Takes its trees as an argument so the instrument can be pointed at a
    specimen it is KNOWN to match. Reading `app/tasks` from inside the matcher
    would tie the parser's proof of life to the production population, which
    since #4157 is legitimately empty.
    """
    found = []
    for rel, tree in trees.items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if not isinstance(target, ast.Attribute):
                    continue
                if target.attr != "current_probability":
                    continue
                if (
                    isinstance(target.value, ast.Name)
                    and target.value.id in _NON_ORM_RECEIVERS
                ):
                    continue
                found.append((rel, _enclosing_function(tree, node.lineno), node.lineno))
    return found


def _orm_price_assignments() -> list[tuple[str, str, int]]:
    """Every unstamped ORM price write under `app/tasks`. Empty is the goal."""
    return _scan_for_orm_price_assignments(_task_trees())


#: A file that the walk MUST match, held as source rather than as a fixture on
#: disk so the specimen and the predicate it exercises are read together.
_ORM_ASSIGNMENT_SPECIMEN = """
def writes_a_price(outcome, prob):
    outcome.current_probability = prob


class Row:
    def __init__(self):
        self.current_probability = None   # excluded: not an ORM receiver
"""


def test_the_orm_census_instrument_still_finds_assignments() -> None:
    """The parser before the measurement, as section 3 does for its own.

    An AST walk that stopped matching — because `ast.Assign` became
    `ast.AnnAssign` at a site, or the attribute was reached through a
    subscript — would return an empty list and make every assertion below pass
    by finding nothing. #3879 is an issue about a population that looked empty;
    its guards do not get to fail that way.

    🔴 This asserts against a SPECIMEN, not against `app/tasks`. It used to
    assert the production scan was non-empty, which worked only for as long as
    the defect existed: #4157 removed the last bare assignment in the tree, and
    the guard that was supposed to prove the instrument works started reporting
    the ship as a broken parser. A liveness check that goes red when the bug is
    fixed is measuring the bug, not the instrument.
    """
    found = _scan_for_orm_price_assignments(
        {"specimen.py": ast.parse(_ORM_ASSIGNMENT_SPECIMEN)}
    )
    assert [(fn, line) for _, fn, line in found] == [("writes_a_price", 3)], (
        f"the ORM price-assignment walk no longer matches its own specimen: {found}"
    )


def test_no_task_writes_an_orm_price_without_the_stamp_helpers() -> None:
    """The path-level coupling. A bare assignment stamps nothing.

    `apply_observed_price` / `apply_unobserved_price` assign the price
    THEMSELVES, so a site that still assigns the attribute directly is by
    construction a site that did not go through either — there is no way to
    call the helper and also write this line.
    """
    offenders = [
        {"file": rel, "function": fn, "line": line}
        for rel, fn, line in _orm_price_assignments()
        if (rel, fn) not in ORM_PRICE_ASSIGNMENTS_NOT_OURS
    ]
    assert offenders == [], {
        "orm_price_writes_with_no_stamp": offenders,
        "why": "#3879 / CERT-2302 — an ORM attribute write is invisible to the "
        "upsert censuses above; route it through apply_observed_price (a venue "
        "handed us this number) or apply_unobserved_price (we inferred it)",
    }


def test_every_exemption_still_matches_a_real_site() -> None:
    """A stale excuse outlives the defect it excuses.

    Vacuous while the dict is empty, and deliberately kept: the next entry is
    the one that needs policing. An exemption whose site has since been fixed
    or moved silently widens the census above.
    """
    actual = {(rel, fn) for rel, fn, _ in _orm_price_assignments()}
    for key in ORM_PRICE_ASSIGNMENTS_NOT_OURS:
        assert key in actual, (
            f"exemption {key} matches no site — if the patch has been applied, "
            "delete the entry rather than leaving a stale excuse in place"
        )


def test_the_live_matcher_has_no_unstamped_price_write_left() -> None:
    """#4157 / CERT-2354: the two parked sites are gone, and stayed gone.

    Stated as its own assertion rather than folded into the census above so a
    regression here names the issue that paid for it. The census would also
    catch it, with a message about a population.
    """
    matcher_sites = [
        (rel, fn, line)
        for rel, fn, line in _orm_price_assignments()
        if rel == "app/tasks/prediction_market_matching.py"
    ]
    assert matcher_sites == [], (
        f"the live matcher writes a price without a stamp again: {matcher_sites}. "
        "Both arms of `_poll_live_prediction_market_prices` must go through "
        "`apply_observed_price` — see CERT-2354 for what a NULL freshness clock "
        "costs a live leg."
    )


def test_both_live_matcher_arms_call_the_observed_price_helper() -> None:
    """The other direction: deleting the writes entirely also empties the census.

    `test_the_live_matcher_has_no_unstamped_price_write_left` is satisfied by a
    file with no price writes at all, which is what a bad rebase produces. This
    pins the two CALLS, scoped to the function rather than the file, and pins
    the `observed_at` keyword — the argument that carries the ship — rather than
    a neighbouring token that a nearby edit could supply.
    """
    tree = _task_trees()["app/tasks/prediction_market_matching.py"]
    fn = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "_poll_live_prediction_market_prices"
        ),
        None,
    )
    assert fn is not None, (
        "`_poll_live_prediction_market_prices` is gone from the matcher — this "
        "guard cannot testify about a function that does not exist"
    )
    calls = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "apply_observed_price"
        and any(kw.arg == "observed_at" for kw in n.keywords)
    ]
    assert len(calls) == 2, (
        f"expected both venue arms to stamp through apply_observed_price("
        f"..., observed_at=...), found {len(calls)}. One means a venue arm "
        "regressed to a bare assignment or was deleted."
    )


def _orm_created_outcomes() -> list[tuple[str, int, bool]]:
    """Every `FuturesOutcome(...)` constructed with a real price, and whether it
    stamps the observation."""
    out = []
    for rel, tree in _task_trees().items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not (
                isinstance(node.func, ast.Name) and node.func.id == "FuturesOutcome"
            ):
                continue
            kwargs = {k.arg: k.value for k in node.keywords}
            if "current_probability" not in kwargs:
                continue
            price = kwargs["current_probability"]
            if isinstance(price, ast.Constant) and price.value is None:
                continue  # an unpriced create owes nothing — refusal 1
            out.append((rel, node.lineno, "price_observed_at" in kwargs))
    return out


def test_the_orm_create_census_finds_something() -> None:
    assert _orm_created_outcomes(), "the FuturesOutcome(...) walk found nothing"


def test_every_orm_created_priced_outcome_stamps_the_observation() -> None:
    """The constructor is an INSERT arm and section 3's rule applies to it.

    `price_observed_at_insert`'s docstring states it: wire only the update path
    and a newly-created priced outcome reads NULL until its SECOND poll, so
    every row the writer mints lands in the census of legs no rail reaches.
    `pg_insert` is not the only way to insert a row, and both DataGolf loops
    mint theirs with the ORM constructor.
    """
    offenders = [
        {"file": rel, "line": line}
        for rel, line, stamped in _orm_created_outcomes()
        if not stamped
    ]
    assert offenders == [], {
        "orm_created_priced_outcomes_without_a_stamp": offenders,
        "why": "#3879 — an outcome CREATED with a price has been observed",
    }


# ---------------------------------------------------------------------------
# 5. The ORM helpers, EXECUTED
# ---------------------------------------------------------------------------
#
# Sections 1-4 are rendered SQL and static census. These run the Python, on a
# stand-in row, because the ORM helpers are the first part of this ship whose
# logic lives in Python rather than in an expression Postgres evaluates — the
# `GREATEST`-vs-`max` asymmetry and the `Numeric(7,6)` rounding are both
# Python-side here, and both are silent when wrong.


class _Row:
    """The three columns the helpers touch. Not a `FuturesOutcome`, because
    instantiating a mapped class pulls in a registry this test does not need and
    would let a default mask a stamp the helper failed to write."""

    def __init__(self, current=None, changed=None, observed=None):
        self.current_probability = current
        self.price_changed_at = changed
        self.price_observed_at = observed


_T0 = dt.datetime(2026, 9, 8, 12, 0, tzinfo=dt.timezone.utc)
_T1 = dt.datetime(2026, 9, 8, 13, 0, tzinfo=dt.timezone.utc)


def test_apply_observed_price_writes_the_price_and_both_stamps() -> None:
    row = _Row(current=0.40)
    apply_observed_price(row, 0.42, observed_at=_T1)
    assert row.current_probability == 0.42
    assert row.price_changed_at == _T1
    assert row.price_observed_at == _T1


def test_apply_observed_price_stamps_freshness_even_when_the_price_did_not_move() -> (
    None
):
    """The whole reason the column exists. A price read every two minutes and
    correctly unchanged all week is FRESH and has not MOVED, and #3879 is the
    issue about the second fact hiding the first."""
    row = _Row(current=0.42, changed=_T0, observed=_T0)
    apply_observed_price(row, 0.42, observed_at=_T1)
    assert (
        row.price_changed_at == _T0
    ), "an unmoved price must not move the movement stamp"
    assert row.price_observed_at == _T1, "an unmoved price WAS still observed"


def test_apply_observed_price_compares_at_stored_precision() -> None:
    """The precision trap, on the ORM path. `current_probability` is
    `Numeric(7,6)`, so the stored value is what the last poll ROUNDED to; a
    naive `!=` against the provider's full-precision float reports a movement on
    every poll of an unmoved Polymarket midpoint."""
    row = _Row(current=Decimal("0.051235"), changed=_T0, observed=_T0)
    apply_observed_price(row, 0.0512345678, observed_at=_T1)
    assert (
        row.price_changed_at == _T0
    ), "0.0512345678 rounds to the stored 0.051235 — that is not a movement"
    assert row.price_observed_at == _T1


def test_apply_observed_price_refuses_a_none_price() -> None:
    """Refusal 1, on the ORM path. A price going away is a real change and not
    an observation of a price."""
    row = _Row(current=0.42, changed=_T0, observed=_T0)
    apply_observed_price(row, None, observed_at=_T1)
    assert row.current_probability is None
    assert row.price_changed_at == _T1, "a price going away IS a movement"
    assert row.price_observed_at == _T0, "nothing was observed; the stamp stands still"


def test_apply_observed_price_takes_a_first_stamp_on_a_null_column() -> None:
    """Refusal 3's Python trap, which is the inverse of the SQL one.

    `GREATEST` in Postgres IGNORES a NULL argument, so a first-ever observation
    on a NULL column takes the incoming value. `max(None, t)` in Python RAISES.
    Every row in the table reads NULL here until its market is next polled, so
    this is not an edge case — it is the first write to every row."""
    row = _Row(current=0.42, observed=None)
    apply_observed_price(row, 0.42, observed_at=_T1)
    assert row.price_observed_at == _T1


def test_apply_observed_price_never_moves_the_stamp_backwards() -> None:
    row = _Row(current=0.42, observed=_T1)
    apply_observed_price(row, 0.42, observed_at=_T0)
    assert row.price_observed_at == _T1


def test_apply_unobserved_price_moves_movement_and_never_freshness() -> None:
    """`tasks/futures.py`'s stale zeroing. Zero is a real number that nobody
    read: the venue stopped returning the leg and the price was inferred from
    the silence. Stamping it would make an abandoned outcome the freshest row in
    the table."""
    row = _Row(current=0.42, changed=_T0, observed=_T0)
    apply_unobserved_price(row, 0, at=_T1)
    assert row.current_probability == 0
    assert row.price_changed_at == _T1
    assert row.price_observed_at == _T0


def test_apply_unobserved_price_on_a_null_out_leaves_freshness_alone() -> None:
    """`tasks/datagolf.py`'s stale nulling, for a player who left the field."""
    row = _Row(current=0.08, changed=_T0, observed=_T0)
    apply_unobserved_price(row, None, at=_T1)
    assert row.current_probability is None
    assert row.price_changed_at == _T1
    assert row.price_observed_at == _T0


def test_apply_unobserved_price_has_no_way_to_ask_for_a_freshness_stamp() -> None:
    """The distinction is in the verb, not in an argument a caller can default
    wrong. A future caller reaching for `observed_at=` here is telling us it
    picked the wrong function."""
    import inspect

    params = inspect.signature(apply_unobserved_price).parameters
    assert "observed_at" not in params
