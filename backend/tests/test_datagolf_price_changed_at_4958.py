"""#4958 — DataGolf stamps `price_changed_at`, and the ORM shape it uses works.

WHAT WAS WRONG. `price_changed_at` (#2024) answers "when did this price last
MOVE", which is the question `last_updated` cannot answer — `last_updated` says
only "when did we last look". The helper that maintains it was rolled out to the
three poll tasks that upsert through Core (`kalshi.py`, `polymarket.py`,
`futures_price_refresh.py`). `datagolf.py` was never one of the three, so on
2026-09-11 production held **57,103 DataGolf legs and 0 stamped, ever** — not a
low rate, none — while 52,031 of them had been touched in the previous 24 hours.
Golf outrights are the DataGolf surface, so every reader keyed on price movement
(line-move copy, "moved today", staleness that tells QUIET from UNREFRESHED) was
blind on all of them.

WHY THIS FILE EXISTS AND NOT JUST THE CLASS SCAN. The sibling guard
(`test_price_stamp_writer_scan_4958.py`) proves the call is PRESENT at every
write site. It cannot prove the call WORKS in the shape DataGolf writes in.
Every pre-existing stamping site is Core — a `.values()` / `set_=` mapping.
DataGolf updates through ORM attribute assignment (`outcome.current_probability
= prob`), so the fix assigns a SQL expression to a mapped attribute, and that is
a shape the column had never been written in before. The risk is specific and
silent: if the expression were evaluated against the NEW row, or bound as a
Python value, the stamp would advance on every poll — reproducing #2024's own
defect in the column added to fix it, while looking fixed. So the round trip is
demonstrated here, not argued from the diff.

WHAT SQLITE CAN AND CANNOT PROVE. There is no local PostgreSQL in this sandbox,
and SQLite does not apply `NUMERIC(7, 6)` rounding on CAST — so the PRECISION
arm (a provider float that is the same price once stored) is not provable here
and is not claimed here; `test_price_change_stamp.py` pins it on the compiled
SQL. What SQLite does share with PostgreSQL is the rule this file turns on:
inside one UPDATE, every SET expression reads the OLD row.
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.models import FuturesOutcome
from app.utils.price_change_stamp import price_changed_at_value

#: A stamp far enough in the past that "did it advance" is unambiguous.
#: SQLite stores naive datetimes, so the read-back is compared as-is.
EARLIER = datetime(2026, 1, 1, 0, 0, 0)


def _session() -> Session:
    engine = sa.create_engine("sqlite://")
    # Just this table: the FK targets are irrelevant to what is under test and
    # SQLite does not resolve them at CREATE time.
    FuturesOutcome.__table__.create(engine)
    return Session(engine)


def _seed(session: Session, probability: float | None) -> FuturesOutcome:
    session.execute(
        sa.insert(FuturesOutcome).values(
            market_id=1,
            external_id="dg_18417",
            name="Scottie Scheffler",
            current_probability=probability,
            price_changed_at=EARLIER,
        )
    )
    session.commit()
    return session.execute(sa.select(FuturesOutcome)).scalar_one()


def _stamp(session: Session) -> object:
    return session.execute(sa.select(FuturesOutcome.price_changed_at)).scalar_one()


def _write(outcome: FuturesOutcome, probability: float | None) -> None:
    """The exact shape `datagolf.py` writes in, both update branches."""
    outcome.price_changed_at = price_changed_at_value(
        FuturesOutcome.current_probability,
        FuturesOutcome.price_changed_at,
        probability,
    )
    outcome.current_probability = probability


def test_a_moved_price_advances_the_stamp() -> None:
    session = _session()
    outcome = _seed(session, 0.15)

    _write(outcome, 0.22)
    session.commit()

    assert _stamp(session) != EARLIER, (
        "the price moved 0.15 -> 0.22 and the stamp did not advance — the "
        "expression is not reaching the UPDATE"
    )
    assert float(session.execute(
        sa.select(FuturesOutcome.current_probability)
    ).scalar_one()) == 0.22


def test_an_unmoved_price_keeps_the_EXISTING_stamp() -> None:
    """The half that makes the column worth having.

    A poll that rewrites the same price must leave the stamp alone; if it did
    not, `price_changed_at` would mean exactly what `last_updated` already
    means and #2024 would be unfixed in a new column. DataGolf polls hourly
    pre-tournament and every five minutes in play, so the quiet case is the
    common one — 52,031 of the 57,103 legs were touched in 24h.

    🔴 THE UPDATE IS ASSERTED, NOT ASSUMED. Rewriting the same price leaves the
    price attribute clean, so "the stamp did not move" would also be true of a
    session that emitted no UPDATE at all — a green test proving nothing. The
    statements are captured and the UPDATE carrying `price_changed_at` is
    required to have run.
    """
    session = _session()
    outcome = _seed(session, 0.15)

    statements: list[str] = []
    sa.event.listen(
        session.get_bind(),
        "before_cursor_execute",
        lambda conn, cursor, statement, *a: statements.append(statement),
    )

    _write(outcome, 0.15)
    session.commit()

    assert any(
        s.upper().startswith("UPDATE") and "price_changed_at" in s
        for s in statements
    ), (
        "no UPDATE touching price_changed_at was emitted, so this test would "
        f"pass on a session that wrote nothing: {statements}"
    )
    assert _stamp(session) == EARLIER


def test_a_vanished_price_advances_the_stamp() -> None:
    """The stale-outcome arm: a price going AWAY is a price change.

    DataGolf nulls the price of any player no longer in the returned field
    (a withdrawal, or a name that was never in it). `IS DISTINCT FROM` is what
    makes that transition visible — `!=` against NULL would swallow it.
    """
    session = _session()
    outcome = _seed(session, 0.15)

    _write(outcome, None)
    session.commit()

    assert _stamp(session) != EARLIER
    assert session.execute(
        sa.select(FuturesOutcome.current_probability)
    ).scalar_one() is None


def test_an_already_unpriced_row_is_not_re_stamped() -> None:
    """NULL -> NULL is not a change, and the helper must not invent one.

    Not a live path today — DataGolf's stale query filters
    `current_probability IS NOT NULL` — but it is what stops a future caller
    that drops the filter from re-stamping the same dead legs every cycle.
    """
    session = _session()
    outcome = _seed(session, None)

    _write(outcome, None)
    session.commit()

    assert _stamp(session) == EARLIER


def test_the_expression_reads_the_OLD_row_not_the_new_one() -> None:
    """The failure mode that would be invisible in production.

    Both SET clauses land in ONE UPDATE, and the price one is assigned AFTER
    the stamp one in the source. If the comparison saw the value being written
    — the `excluded.` mistake, in a different spelling — it would be vacuously
    false and the stamp would freeze forever at whatever the row was born with.
    A moved price with the assignments in the source order is therefore the
    positive control for the ordering itself, not only for the predicate.
    """
    session = _session()
    outcome = _seed(session, 0.40)

    outcome.price_changed_at = price_changed_at_value(
        FuturesOutcome.current_probability,
        FuturesOutcome.price_changed_at,
        0.55,
    )
    outcome.current_probability = 0.55
    session.flush()

    assert _stamp(session) != EARLIER, (
        "SET expressions in one UPDATE must evaluate against the pre-update "
        "row; if this fails the assignment order in datagolf.py is load-bearing "
        "and the comment there is wrong"
    )
