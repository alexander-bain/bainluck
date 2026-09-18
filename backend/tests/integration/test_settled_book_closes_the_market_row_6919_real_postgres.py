"""#6919's deferred settlement close, EXECUTED against a real PostgreSQL.

## why the unit suite is not enough, stated precisely

`test_settled_book_closes_the_market_row_6919.py` drives the shipped rail through
a `RecordingSession` and asserts on the statement it ISSUES — the SQL text, the
bound parameters, that there is exactly one of them per pass. That is the right
tool for "is the write addressed the way the fix claims", and it is what caught
the parent-ladder reach wall in the first place.

It cannot observe a single thing the SERVER does, and every one of this
statement's load-bearing parts is server-side:

* **`fo.external_id = ANY(:leg_keys)` is a Python `list` bound into a `text()`
  statement and executed through asyncpg.** Whether that binds as a PostgreSQL
  array at all — rather than raising, or worse, silently comparing against a
  string rendering of the list — is a driver fact. A recording session records
  the list and asserts nothing about it.
* **Three correlated subqueries decide the row set.** `NOT EXISTS (a leg with
  `resolution_source IS NULL`)` is the whole safety of the widening: without it
  the statement closes 389 open markets on production, 322 of them tier 1-3.
  Whether it actually excludes a partial ladder is a question about how the
  server evaluates a correlated `NOT EXISTS` over rows, and mock-asserting that
  the clause is PRESENT in the text is not the same claim.
* **`rowcount` is now the value of `markets_settled`**, and the after-check for
  this ship reads that counter as its proof the fix is live. A `rowcount` is
  produced by the driver from an executed statement. The unit suite fakes it.
* **`COALESCE(fm.settled_at, :now)` must not move a date that is already set.**
  That is a server-side expression over a stored value.

CERT-3075 graded the fix GREEN and named this file's contract as its one
nonblocking follow-up (`6919-COMMIT-REAL-PG-SETTLEMENT-CLOSE-CONTRACT`): the bus
proved the behaviour by executing the UPDATE in its own session, and that proof
lived nowhere a later change could trip over. This is that proof, wired into CI.

## it runs the SHIPPED function, not a copy of the SQL

The statement is never restated here. Every arm calls
`_write_refreshed_prices` — the real rail — with `get_task_session` pointed at
the test database and markets built by the real Gamma parser, so the grading
loop, the `#3868` by-condition leg lookup and the deferred close all execute as
production runs them. A gate that re-types the UPDATE proves the typist agreed
with themselves; this one goes red if the shipped statement changes meaning.

## the corpus: two rows that must close, five that must not

One settled condition arrives from the venue. Its three leg keys — the bare
`<cid>` and `<cid>_yes` / `<cid>_no` — are spread across seven market rows
exactly as `_process_event_batch` spreads them in production.

* **`SUB`** (`external_id` = the 64-hex condition, legs `_yes`/`_no`) — the
  sub-market copy. **Closes.** The pre-#6919 key reached this row and only this
  row.
* **`LADDER`** (`external_id` = `1004380`, a numeric Gamma EVENT id, one leg
  under the bare condition) — the parent ladder. **Closes.** This is the shape
  the CPBL specimens 60755454 / 60755456 / 60755459 had on production when the
  first fix's own after-check found them still `status='open'` under legs it had
  just graded. `test_the_old_market_keyed_close_cannot_reach_the_ladder` runs
  the superseded predicate over this same corpus and requires it to MISS here,
  so a green run means the widening was proved necessary rather than merely
  unobjected-to.
* **`PARTIAL`** (a ladder owning the settled leg AND an unanswered one) — **must
  not close.** The 389-market clause, in miniature and on real rows.
  `test_without_the_guard_the_same_statement_retires_the_live_ladder` executes
  the guard-less form against the same corpus and requires it to close this row,
  so the guard is proved load-bearing here and not just asserted to exist.
* **`KALSHI`** (a Kalshi row carrying `<cid>_yes`) — **must not close.**
  Manufactured, and deliberately so: no Kalshi ticker is ever a 64-hex
  condition, so `fm.source = 'polymarket'` has an empty population on production
  and no natural specimen can exercise it. Worth manufacturing because the
  GRADING lookup beside it (`by_condition`, #3868) carries no source scope at
  all — it selects on `fo.external_id` alone — so this row's leg really is
  graded by the pass, and only the close's own source clause keeps the row open.
  The control therefore fails if that clause is dropped.
* **`ALREADY`** (`status='resolved'`, `settled_at` already stamped a day
  earlier) — **must not close, must not be restamped, and must not be counted.**
  Proves `status <> 'resolved'` and the `COALESCE` together, which is what makes
  `rowcount` mean "rows that MOVED".
* **`LEGLESS`** (a Polymarket row with no outcomes at all) — **must not close.**
  Recorded honestly: the shipped comment says the third `EXISTS` is what saves
  this row because "`NOT EXISTS` is vacuously true for a legless row", and the
  vacuity is real, but the row is already excluded one clause earlier — the
  first `EXISTS` needs a leg matching `leg_keys` and a legless row has none. The
  third clause is therefore belt-and-braces rather than the only thing standing
  between us and the row. The control is kept because the invariant it states is
  the one a reader cares about; the note is here so nobody later "discovers" the
  redundancy and reads it as a defect.
* **`UNRELATED`** (a fully graded Polymarket row whose legs name a different
  condition) — **must not close.** Without it, a statement that closed every
  graded Polymarket market would pass every other arm in this file.
"""

from __future__ import annotations

import contextlib
import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #6919 settlement "
        "close gate (CI job `search-recall` provides one)"
    ),
)

NOW = datetime(2026, 9, 18, 17, 30, tzinfo=timezone.utc)
#: `ALREADY`'s existing settlement date. A day before the pass, so a restamp
#: would be unmistakable rather than a rounding difference.
ALREADY_SETTLED_AT = NOW - timedelta(days=1)

#: The condition the venue settles in this pass — the same one the unit suite
#: uses, so the two files are talking about one row.
CID = "0x3d060eff715e0aa1d15e3758ec37866519686f88c7e0cb0704314d8c844e3e2e"
#: A sibling child of the same parent ladder, still trading. This is the leg
#: that makes `PARTIAL` partial.
OTHER_CID = "0x9f1c44ab0d5e27b8c6a3f01e8d72b45a9c0e61f3a84d7b25e9c18f60d3a7b4c2"
#: A condition this pass never mentions.
UNRELATED_CID = "0x51aa93cc7e20f84b16d9e37c05b8a2f4d6019e7c3b85a04f2d9c6e18b70a3f5d"

SUB, LADDER, PARTIAL, KALSHI, ALREADY, LEGLESS, UNRELATED = (
    69190101,
    69190102,
    69190103,
    69190104,
    69190105,
    69190106,
    69190107,
)

#: Every market row that must be CLOSED by the pass, and every one that must
#: survive it. Named once so no arm can drift from the docstring.
MUST_CLOSE = (SUB, LADDER)
MUST_SURVIVE = (PARTIAL, KALSHI, ALREADY, LEGLESS, UNRELATED)


def _asyncpg_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    return url.replace("postgres://", "postgresql://", 1).replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )


@pytest.fixture
async def session():
    """Real Postgres with the real schema, dropped and rebuilt."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(_asyncpg_url(DB_URL))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _seed(session):
    """Insert the corpus through the ORM.

    The ORM and not raw INSERT: `futures_markets` carries client-side defaults
    (`category`, `status`, `mutually_exclusive`) a raw INSERT would not apply,
    and `test_pg_gate_seed_completeness.py`'s raw-INSERT arm keys on the
    presence of `INSERT INTO`.
    """
    from app.models import FuturesMarket, FuturesOutcome

    # (id, source, external_id, status, settled_at)
    markets = (
        # The sub-market copy: keyed on the condition itself.
        (SUB, "polymarket", CID, "open", None),
        # The parent ladder: keyed on the numeric Gamma EVENT id. `1004380` is
        # 60755454's real production value.
        (LADDER, "polymarket", "1004380", "open", None),
        # A live ladder that happens to own the settled child.
        (PARTIAL, "polymarket", "1004999", "open", None),
        # Same leg key, different venue.
        (KALSHI, "kalshi", "KXCPBLGAME-26SEP18-WEI", "open", None),
        # Closed a day ago by somebody else.
        (ALREADY, "polymarket", "1004778", "resolved", ALREADY_SETTLED_AT),
        # No legs at all.
        (LEGLESS, "polymarket", "1004666", "open", None),
        # Graded, Polymarket, and nothing to do with this condition.
        (UNRELATED, "polymarket", "1004555", "open", None),
    )
    for mid, source, external_id, status, settled_at in markets:
        session.add(
            FuturesMarket(
                id=mid,
                source=source,
                external_id=external_id,
                name=f"seed market {mid}",
                llm_sport_category="baseball",
                status=status,
                settled_at=settled_at,
                event_id=None,
                commence_time=NOW - timedelta(hours=6),
            )
        )

    # (id, market, external_id, name, is_winner, resolution_source)
    outcomes = (
        # SUB's two sides, ungraded when the pass starts.
        (69190201, SUB, f"{CID}_yes", "Yes", None, None),
        (69190202, SUB, f"{CID}_no", "No", None, None),
        # The ladder's leg for this child, under the BARE condition.
        (69190203, LADDER, CID, "Wei Chuan Dragons", None, None),
        # PARTIAL owns the same child AND one that is still trading.
        (69190204, PARTIAL, CID, "Wei Chuan Dragons", None, None),
        (69190205, PARTIAL, OTHER_CID, "Fubon Guardians", None, None),
        # A Kalshi leg wearing a Polymarket condition key.
        (69190206, KALSHI, f"{CID}_yes", "Yes", None, None),
        # ALREADY's leg was graded when it was closed, a day ago.
        (69190207, ALREADY, f"{CID}_no", "No", True, "api_settlement"),
        # A fully graded row this pass never names.
        (
            69190208,
            UNRELATED,
            UNRELATED_CID,
            "Rakuten Monkeys",
            False,
            "api_settlement",
        ),
    )
    for oid, mid, external_id, name, is_winner, resolution_source in outcomes:
        session.add(
            FuturesOutcome(
                id=oid,
                market_id=mid,
                external_id=external_id,
                name=name,
                is_winner=is_winner,
                resolution_source=resolution_source,
            )
        )
    await session.commit()


def _settled_market():
    """A Gamma nested market, through the REAL parser, settled Yes.

    Rig 249: a hand-built DTO cannot drop the field the fix rests on, so it
    passes on both sides of the change. `outcomePrices` really does arrive as a
    stringified JSON array and `closed` really is a separate key from `active`.
    """
    import app.services.polymarket_api as poly_api

    market = poly_api.PolymarketAPIService()._parse_market(
        {
            "conditionId": CID,
            "question": "Will the Wei Chuan Dragons beat the TSG Hawks?",
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["1", "0"]',
            "clobTokenIds": '["11", "22"]',
            "active": True,
            "closed": True,
            "acceptingOrders": False,
            "bestBid": None,
            "bestAsk": 0.009,
            "lastTradePrice": 0.995,
            "volume24hr": 1234.0,
        }
    )
    assert market is not None, "the real parser refused the specimen"
    return market


def _stats() -> dict:
    return {
        "outcomes_updated": 0,
        "snapshots_written": 0,
        "unpriced": 0,
        "volume_observed": 0,
        "legs_settled": 0,
        "markets_settled": 0,
        "closed_without_result": 0,
        "legs_reached_by_condition": 0,
    }


async def _run_the_rail(session, monkeypatch) -> dict:
    """Execute the SHIPPED rail against this database. Returns its stats."""
    import app.tasks.base as base
    import app.tasks.tournament_price_refresh as rail

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    monkeypatch.setattr(base, "get_task_session", _fake_session)

    stats = _stats()
    await rail._write_refreshed_prices([_settled_market()], stats, now=NOW)
    return stats


async def _rows(session) -> dict[int, tuple[str, datetime | None]]:
    """`{market_id: (status, settled_at)}` as STORED, for all seven rows."""
    from sqlalchemy import text

    got = await session.execute(
        text("SELECT id, status, settled_at FROM futures_markets ORDER BY id")
    )
    return {r[0]: (r[1], r[2]) for r in got.all()}


# ---------------------------------------------------------------------------
# ANTI-VACUITY. Before asserting what the close does, prove the corpus reaches
# it: the specimen must take the settled branch, and the legs the close depends
# on must really be graded by this pass. A gate whose subject never enters the
# statement passes identically on both sides of the change.
# ---------------------------------------------------------------------------
@needs_postgres
class TestTheCorpusReallyReachesTheClose:
    async def test_the_pass_grades_the_legs_the_close_then_reads(
        self, session, monkeypatch
    ):
        """The bare-condition ladder leg is graded, not just the `_yes`/`_no`."""
        from sqlalchemy import text

        await _seed(session)
        await _run_the_rail(session, monkeypatch)

        graded = await session.execute(
            text(
                "SELECT id, resolution_source FROM futures_outcomes "
                "WHERE id IN (69190201, 69190202, 69190203, 69190204) "
                "ORDER BY id"
            )
        )
        assert [(r[0], r[1]) for r in graded.all()] == [
            (69190201, "api_settlement"),
            (69190202, "api_settlement"),
            (69190203, "api_settlement"),
            (69190204, "api_settlement"),
        ], (
            "the pass did not grade the legs this close is addressed through, "
            "so every assertion below would be vacuous"
        )

    async def test_the_live_sibling_leg_stays_unanswered(self, session, monkeypatch):
        """`PARTIAL` is only a control while its other leg is still NULL."""
        from sqlalchemy import text

        await _seed(session)
        await _run_the_rail(session, monkeypatch)

        got = await session.execute(
            text("SELECT resolution_source FROM futures_outcomes WHERE id = 69190205")
        )
        assert got.scalar() is None, (
            "the pass graded the sibling child, so PARTIAL is no longer a "
            "partial ladder and the guard arm below proves nothing"
        )


@needs_postgres
class TestTheCloseReachesBothKeySpaces:
    async def test_both_intended_rows_are_closed(self, session, monkeypatch):
        await _seed(session)
        await _run_the_rail(session, monkeypatch)

        rows = await _rows(session)
        assert [rows[m][0] for m in MUST_CLOSE] == ["resolved", "resolved"], (
            "the settled condition reaches a sub-market row keyed on the "
            "condition AND a parent ladder row keyed on the Gamma event id; "
            f"stored statuses were {[rows[m][0] for m in MUST_CLOSE]}"
        )

    async def test_the_ladder_row_is_the_one_the_old_key_could_not_reach(
        self, session, monkeypatch
    ):
        """`LADDER.external_id` is numeric — never a condition. That is the bug."""
        await _seed(session)
        await _run_the_rail(session, monkeypatch)

        rows = await _rows(session)
        assert rows[LADDER][0] == "resolved"
        assert rows[LADDER][1] == NOW, "settled_at is stamped with the pass time"

    async def test_the_old_market_keyed_close_cannot_reach_the_ladder(self, session):
        """RED-FIRST, on rows: the superseded predicate MISSES the ladder.

        This is the arm that makes a green run mean the widening was NECESSARY.
        The pre-#6919-arm-three statement keyed the close on the MARKET's own
        `external_id`; executed over this same corpus it closes the sub-market
        and leaves the parent ladder open, which is exactly the production state
        the first fix's own after-check found.
        """
        from sqlalchemy import text

        await _seed(session)
        closed = await session.execute(
            text("""
                UPDATE futures_markets fm
                   SET status = 'resolved',
                       settled_at = COALESCE(fm.settled_at, :now),
                       updated_at = :now
                 WHERE fm.source = 'polymarket'
                   AND fm.external_id = :cid
                """),
            {"now": NOW, "cid": CID},
        )
        await session.commit()

        rows = await _rows(session)
        assert closed.rowcount == 1, (
            "the old key matched something other than the single sub-market "
            "row, so this red-first arm is not describing the old behaviour"
        )
        assert rows[SUB][0] == "resolved"
        assert rows[LADDER][0] == "open", (
            "the old market-keyed close reached the parent ladder, so the "
            "widening this file guards would not have been needed"
        )


@needs_postgres
class TestNothingElseIsClosed:
    async def test_all_five_controls_survive_the_pass(self, session, monkeypatch):
        await _seed(session)
        await _run_the_rail(session, monkeypatch)

        rows = await _rows(session)
        survived = {m: rows[m][0] for m in MUST_SURVIVE}
        assert survived == {
            PARTIAL: "open",
            KALSHI: "open",
            ALREADY: "resolved",
            LEGLESS: "open",
            UNRELATED: "open",
        }, f"a control moved: {survived}"

    async def test_the_already_resolved_row_keeps_its_own_settlement_date(
        self, session, monkeypatch
    ):
        """`COALESCE(fm.settled_at, :now)` must not restamp a stored date."""
        await _seed(session)
        await _run_the_rail(session, monkeypatch)

        rows = await _rows(session)
        assert (
            rows[ALREADY][1] == ALREADY_SETTLED_AT
        ), "a row closed a day ago was restamped with this pass's clock"

    async def test_without_the_guard_the_same_statement_retires_the_live_ladder(
        self, session
    ):
        """RED-FIRST, on rows: the `NOT EXISTS` clause is load-bearing.

        The guard-less form of the shipped statement, over this same corpus,
        closes `PARTIAL` — a ladder with an unanswered leg. On production that
        difference was measured at 389 open markets, 322 of them tier 1-3.
        """
        from sqlalchemy import text

        await _seed(session)
        leg_keys = [CID, f"{CID}_yes", f"{CID}_no"]
        closed = await session.execute(
            text("""
                UPDATE futures_markets fm
                   SET status = 'resolved',
                       settled_at = COALESCE(fm.settled_at, :now),
                       updated_at = :now
                 WHERE fm.source = 'polymarket'
                   AND fm.status <> 'resolved'
                   AND EXISTS (SELECT 1 FROM futures_outcomes fo
                                WHERE fo.market_id = fm.id
                                  AND fo.external_id = ANY(:leg_keys))
                """),
            {"now": NOW, "leg_keys": leg_keys},
        )
        await session.commit()

        rows = await _rows(session)
        assert rows[PARTIAL][0] == "resolved", (
            "the guard-less statement left the partial ladder open, so this "
            "corpus cannot show what the guard is for"
        )
        assert closed.rowcount == 3, (
            "expected the guard-less form to close SUB, LADDER and PARTIAL; "
            f"it closed {closed.rowcount}"
        )


@needs_postgres
class TestTheCounterIsTheRowCount:
    async def test_markets_settled_is_what_the_server_changed(
        self, session, monkeypatch
    ):
        """Two rows moved, so the counter reads 2 — not the number of books."""
        await _seed(session)
        stats = await _run_the_rail(session, monkeypatch)

        assert stats["markets_settled"] == 2, (
            "`markets_settled` is the after-check's proof this ship works; it "
            "must be the UPDATE's rowcount and nothing else"
        )

    async def test_a_second_pass_closes_nothing_and_counts_zero(
        self, session, monkeypatch
    ):
        """`status <> 'resolved'` is what makes the counter honest on a re-run."""
        await _seed(session)
        await _run_the_rail(session, monkeypatch)
        again = await _run_the_rail(session, monkeypatch)

        assert again["markets_settled"] == 0, (
            "a re-run reported closures it did not make — the counter is "
            "reading intentions again"
        )
        rows = await _rows(session)
        assert (
            rows[SUB][1] == NOW and rows[LADDER][1] == NOW
        ), "the re-run restamped rows it should not have touched at all"


@needs_postgres
class TestTheArrayBindReallyBinds:
    async def test_a_list_bound_into_any_matches_by_element_not_by_rendering(
        self, session, monkeypatch
    ):
        """asyncpg must see a PostgreSQL array, not a string of one.

        If the bind degraded to a text rendering of the Python list, no
        `external_id` would ever equal it and the close would match zero rows
        while raising nothing at all — green tests, silent no-op, exactly the
        failure this ship was written to end.
        """
        await _seed(session)
        stats = await _run_the_rail(session, monkeypatch)

        assert stats["markets_settled"] > 0, (
            "the close matched nothing: `= ANY(:leg_keys)` did not bind as an " "array"
        )
