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
from app.utils.price_change_stamp import (
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
