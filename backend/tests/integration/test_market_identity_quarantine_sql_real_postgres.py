"""The identity quarantine's SQL twin, against a REAL PostgreSQL (#6275, #1902).

## why this gate needs a real server

Alex ruled the date-disagreement outcomes QUARANTINED from published calibration
curves (queue 363 item 4, #1902). The published population is assembled entirely
in SQL, so applying that ruling meant giving
:func:`app.utils.market_identity.market_identity_disputed` a SQL form —
:func:`app.utils.market_identity.identity_quarantine_ctes`.

That is a SECOND implementation of a predicate whose own module docstring exists
to say a shared eligibility predicate gets ONE. The two forms are allowed to
coexist only because this gate pins them to each other: it runs BOTH over one
corpus and fails on any disagreement. Delete this gate and the module is back to
the drift it was written about — and the drift would be invisible, because the
Python form is what every unit test exercises while the SQL form is what decides
the curve.

Nothing but a real server can decide this. The divergences are all in PostgreSQL
semantics, and every one of them is a case where the obvious translation is
wrong:

1. **`to_date` does not raise on an impossible day — it rolls over.**
   `to_date('26FEB30','YYMONDD')` is 2026-03-02. Python's `date(2026, 2, 30)`
   raises and the predicate returns None. A market would be quarantined on a
   date it never named. The chain validates by round-trip instead of trusting
   the parse; only a server can prove the round-trip rejects it.

2. **`to_date`'s `YY` is not `2000 + yy`.** PostgreSQL maps 70-99 into the
   1900s. `KXMLB-99DEC31NYY` is 2099-12-31 in Python and would be 1999-12-31
   parsed. The chain builds the year arithmetically for this reason.

3. **A three-letter group that is not a month makes `to_date` RAISE**, which
   inside the calibration beat is not a wrong answer, it is a dead beat. The
   chain uses strict `make_date` so a non-month propagates NULL. The corpus
   carries `-26XYZ05` to prove the chain returns a row rather than an error.

4. **First-match semantics.** Python's `re.search` takes the first
   `-\\d\\d[A-Z]{3}\\d\\d` and THEN validates the month. A SQL regex that
   enumerated the twelve months would skip an invalid first match and find a
   later one, so `KX-26ZZZ05-26AUG05MIN` would be unreadable in Python and
   Aug 5 in SQL. The corpus carries exactly that ticker.

5. **The timezone.** The ticker is a US-Eastern game date and `commence_time` is
   `timestamptz`. Comparing UTC dates manufactures a dispute for every night
   game — a 19:40 ET first pitch is the next UTC day — which would quarantine
   most of the population. Only a server has the tz database.

There is no local PostgreSQL in the agent sandbox, so CI is where this runs, and
the job's skip-detection step is what stops a skipped gate reading as a pass.

## the corpus

Each row is a ticker paired with the divergence it catches. The oracle is not a
literal written here — writing the expected answers down would let a wrong SQL
form and a wrong expectation agree. The oracle is the PYTHON predicate, called
on the same input, which is the implementation the ruling was written against
and which the unit tests already pin independently.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres identity "
        "quarantine differential"
    ),
)

#: 19:40 ET on Aug 5 — deliberately a NIGHT game, so the UTC date (Aug 6) and the
#: Eastern date (Aug 5) differ and divergence 5 is live for every row.
AUG5_NIGHT = datetime(2026, 8, 5, 23, 40, tzinfo=timezone.utc)
#: The wrong game, and the specimen's actual event.
AUG6_NIGHT = datetime(2026, 8, 6, 23, 30, tzinfo=timezone.utc)

#: ticker -> the divergence it exists to catch.
CORPUS: dict[str | None, str] = {
    "KXMLBTOTAL-26AUG051940MINKC": "the #1902 specimen: Aug 5 ticker, Aug 6 event",
    "KXNFLGAME-26SEP14DALNYG": "an ordinary dated ticker, another sport",
    "KXMLB-26AUG05MIN": "agrees with its event — the CONTROL, must not be held",
    "POLY-0xdeadbeef": "no date token at all: unknown, NOT disputed",
    "KXMLB-26FEB30ABC": "divergence 1: to_date rolls Feb 30 to Mar 2",
    "KXMLB-24FEB29SF": "divergence 1, other side: Feb 29 2024 is REAL and parses",
    "KXMLB-25FEB29SF": "divergence 1: Feb 29 2025 does not exist",
    "KXMLB-26XYZ05TOR": "divergence 3: a non-month must not raise",
    "KXMLB-99DEC31NYY": "divergence 2: YY 99 is 2099, not 1999",
    "KXMLB-70JUL04PHI": "divergence 2: YY 70 is 2070, not 1970",
    "KXMLB-26AUG00MIN": "day 00 is not a day",
    "KXMLB-26AUG45MIN": "day 45 is not a day",
    "KX-26ZZZ05-26AUG05MIN": "divergence 4: first match wins, even when invalid",
    "": "empty id",
    None: "null id",
}


@pytest.fixture
async def pg_conn():
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        yield conn
    await engine.dispose()


def _chain_over_corpus_sql() -> str:
    """The SHIPPED chain, pointed at a VALUES corpus instead of ``market_info``.

    ``identity_quarantine_ctes`` is called with the same keyword the calibration
    task calls it with, so what runs here is the text that decides the curve —
    not a paraphrase of it. Only ``source_relation`` moves.
    """
    from app.utils.market_identity import (
        IDENTITY_DISPUTED_CTE,
        identity_quarantine_ctes,
    )

    ctes = identity_quarantine_ctes(source_relation="corpus")
    return f"""
        WITH corpus AS (
            SELECT v.market_id, v.external_id, v.commence_time
            FROM unnest(
                CAST(:ids AS bigint[]),
                CAST(:eids AS text[]),
                CAST(:cts AS timestamptz[])
            ) AS v(market_id, external_id, commence_time)
        ),
        {ctes}
        SELECT c.market_id, (d.market_id IS NOT NULL) AS disputed
        FROM corpus c
        LEFT JOIN {IDENTITY_DISPUTED_CTE} d ON d.market_id = c.market_id
        ORDER BY c.market_id
    """


@needs_postgres
@pytest.mark.parametrize("event_time", [AUG5_NIGHT, AUG6_NIGHT])
async def test_the_sql_chain_and_the_python_predicate_never_disagree(
    pg_conn, event_time
):
    """The whole reason the SQL form is allowed to exist.

    Run at BOTH event times so every ticker is exercised as an agreement AND as
    a disagreement. One event time would let a chain that is stuck on one answer
    pass: at Aug 6 alone, "always disputed when a date parses" is
    indistinguishable from the real predicate.
    """
    from app.utils.market_identity import market_identity_disputed

    tickers = list(CORPUS)
    rows = (
        await pg_conn.execute(
            text(_chain_over_corpus_sql()),
            {
                "ids": list(range(len(tickers))),
                "eids": tickers,
                "cts": [event_time] * len(tickers),
            },
        )
    ).all()
    assert len(rows) == len(tickers), "the chain lost or duplicated a corpus row"

    disagreements = []
    for market_id, sql_disputed in rows:
        ticker = tickers[market_id]
        python_disputed = market_identity_disputed(ticker, event_time)
        if bool(sql_disputed) is not python_disputed:
            disagreements.append(
                f"{ticker!r} ({CORPUS[ticker]}): "
                f"python={python_disputed} sql={bool(sql_disputed)}"
            )
    assert not disagreements, (
        "the SQL twin and the Python predicate disagree, so the curve is "
        "quarantining a different population than the ruling names:\n  "
        + "\n  ".join(disagreements)
    )


@needs_postgres
async def test_the_corpus_is_not_unanimous(pg_conn):
    """A differential over a corpus that is all-True or all-False proves nothing.

    Without this, a chain that returned a constant would pass the test above at
    whichever event time matched the constant — and the parametrize only catches
    that if the corpus actually contains both answers at one of them.
    """
    from app.utils.market_identity import market_identity_disputed

    tickers = list(CORPUS)
    rows = (
        await pg_conn.execute(
            text(_chain_over_corpus_sql()),
            {
                "ids": list(range(len(tickers))),
                "eids": tickers,
                "cts": [AUG6_NIGHT] * len(tickers),
            },
        )
    ).all()
    answers = {bool(d) for _mid, d in rows}
    assert answers == {True, False}, (
        f"the corpus is unanimous at Aug 6 ({answers}), so a constant-returning "
        f"chain would pass the differential"
    )
    # And the control row specifically: agreeing markets are NOT held.
    assert market_identity_disputed("KXMLB-26AUG05MIN", AUG5_NIGHT) is False
    control = [
        d for mid, d in rows if tickers[mid] == "KXMLB-26AUG05MIN"
    ]
    assert control and bool(control[0]) is True, (
        "at the WRONG event time the control must be disputed, or it is not "
        "testing the comparison at all"
    )


@needs_postgres
async def test_a_non_month_ticker_does_not_raise(pg_conn):
    """Divergence 3, on its own, because its failure mode is not a wrong answer.

    `to_date('26XYZ05','YYMONDD')` raises. Inside the calibration beat that is
    not a misgraded row, it is the whole build dying on one odd ticker — so this
    asserts the chain RETURNS for that input rather than asserting what it
    returns (the differential above owns the value).
    """
    rows = (
        await pg_conn.execute(
            text(_chain_over_corpus_sql()),
            {"ids": [1], "eids": ["KXMLB-26XYZ05TOR"], "cts": [AUG6_NIGHT]},
        )
    ).all()
    assert len(rows) == 1


@needs_postgres
async def test_a_night_game_is_read_in_eastern_not_utc(pg_conn):
    """Divergence 5, pinned as a behaviour rather than left to the corpus.

    A 19:40 ET first pitch on Aug 5 is Aug 6 in UTC. If the chain compared UTC
    dates, this correctly-paired market would be quarantined — and since most
    games are night games, the quarantine would swallow the curve. The unit
    tests cannot catch this: Python's `eastern_game_date` is right, and the bug
    would live only in the SQL.
    """
    rows = (
        await pg_conn.execute(
            text(_chain_over_corpus_sql()),
            {"ids": [1], "eids": ["KXMLB-26AUG05MIN"], "cts": [AUG5_NIGHT]},
        )
    ).all()
    assert rows and bool(rows[0][1]) is False, (
        "a 19:40 ET game whose ticker names its own date was quarantined — the "
        "chain is comparing UTC dates, not Eastern ones"
    )
