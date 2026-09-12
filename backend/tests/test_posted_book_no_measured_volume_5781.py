"""#5781 — a market born before its first trade must not be frozen forever.

THE SPECIMEN, production 2026-09-12. ``NCAA Football 2026 Big Ten Conference:
Winner`` (market 57792790, Gamma event 779028), tier 2, reachable by a reader
through ``/api/events/search?q=Big+Ten+Conference``. Every rung was last written
**2026-08-01 11:18Z** — the day the venue opened the book — and the card was
still serving those numbers two game weeks into the season:

    Michigan    4.5% served   vs  16.5% at the venue   +12.0 pts
    USC         4.5%              16.0%                +11.5
    Nebraska    4.0%              15.5%                +11.5
    Ohio State 32.5%              28.5%                 -4.0

WHY IT COULD NOT CORRECT ITSELF. ``futures_price_refresh``'s value test admitted
measured volume >= 10,000 at any tier (#3315) or ``market_tier = 1`` at any
volume (#5268). This row is tier 2 with ``volume IS NULL``, so it passed neither
and no run could select it. The NULL is a birthday, not a verdict: the ingest of
2026-08-01 wrote ``liquidity = 8930.67`` and ``volume = NULL`` in the SAME
statement, and the venue today reports volume 4,003.96 on that event. The only
writer that would refresh the volume is a poll that stopped reaching the row, and
the sweep that would re-price it is gated on the volume — a fixed point.

The fix is a third positive value statement: a POSTED BOOK at or above a floor,
where volume was never measured. These tests hold the four properties that make
it safe to add rather than merely correct to add.
"""

import sqlite3

import pytest

import app.tasks.futures_price_refresh as fpr


def _admits(rows, *, volume_floor=10_000, liquidity_floor=1_000):
    """Run ``HIGH_VALUE_SQL``'s real text over rows, in SQL, not in Python.

    Asserted as SQL semantics rather than as a substring match for the reason
    #3315's own guard gives: a rewrite that keeps the words and loses the
    meaning passes a string test. ``NULL >= 1000`` behaving as NULL is the whole
    subject here, and only a database evaluates that.
    """
    con = sqlite3.connect(":memory:")
    con.execute(
        "CREATE TABLE fm (id INT, source TEXT, market_tier INT, "
        "volume INT, liquidity REAL)"
    )
    con.executemany("INSERT INTO fm VALUES (?,?,?,?,?)", rows)
    where = (
        fpr.HIGH_VALUE_SQL.replace("fm.", "")
        .replace(":volume_floor", str(volume_floor))
        .replace(":liquidity_floor", str(liquidity_floor))
    )
    return {r[0] for r in con.execute(f"SELECT id FROM fm WHERE {where}")}


#: The specimen and the controls that make admitting it mean something.
#: (id, source, tier, volume, liquidity)
_SPECIMEN = (57792790, "polymarket", 2, None, 8_930.67)
_THIN_BOOK = (1, "polymarket", 2, None, 120.0)          # under the floor
_NO_BOOK = (2, "polymarket", 2, None, None)             # nothing posted
_MEASURED_SMALL = (3, "polymarket", 2, 12, 50_000.0)    # we DID ask
_KALSHI_SHAPED = (4, "kalshi", 2, None, None)           # kalshi writes no liquidity
_BRAZIL = (5, "polymarket", 2, 114_137_967, 0.0)        # #3315's row
_TIER1_UNMEASURED = (6, "polymarket", 1, None, None)    # #3315's other row


class TestTheThirdValueArm:
    def test_the_specimen_is_admitted(self):
        """The whole ship, in one assertion, on the row that cost 12 points."""
        assert 57792790 in _admits([_SPECIMEN])

    def test_a_posted_book_below_the_floor_is_not(self):
        """The floor is a floor.

        Without this the arm is `volume IS NULL`, which admits 21,148 rows at
        tier 2+ and is a bigger population than the entire value pool. 1,000 is
        where the measured distribution's tail starts.
        """
        assert _admits([_THIN_BOOK]) == set()

    def test_no_posted_book_is_not_a_posted_book(self):
        """``NULL >= 1000`` is NULL, and NULL is not TRUE.

        This is the ONE source-independent property of the arm, and it is why
        the module's note refuses to describe the arm as a Kalshi fence: Kalshi
        rows are excluded today because they carry no `liquidity`, which this
        rejects, and NOT because the predicate names a source. The day the
        column is written for Kalshi they become eligible, deliberately.
        """
        assert _admits([_NO_BOOK, _KALSHI_SHAPED]) == set()

    def test_the_floor_is_inclusive(self):
        """``>=``, matching the volume floor one line up.

        Pinned because a book sitting exactly ON the floor is the one row a
        ``>`` mutation loses, and it loses it silently: the population barely
        moves, so no size stat notices.
        """
        at_floor = (20, "polymarket", 2, None, float(fpr.POSTED_LIQUIDITY_FLOOR))
        just_under = (21, "polymarket", 2, None, fpr.POSTED_LIQUIDITY_FLOOR - 0.01)
        assert _admits([at_floor, just_under]) == {20}

    def test_the_arm_names_no_source(self):
        """Stated once, so the sentence above cannot quietly become a lie."""
        assert "source" not in fpr.VALUE_LIQUID_SQL
        assert "kalshi" not in fpr.VALUE_LIQUID_SQL.lower()
        assert "polymarket" not in fpr.VALUE_LIQUID_SQL.lower()

    def test_a_measured_small_volume_is_a_different_question(self):
        """The arm answers "we never asked", never "we asked and it was small".

        `_MEASURED_SMALL` carries 50,000 of liquidity — four times the floor —
        and stays out, because its volume IS measured. That case is #5268's and
        it is answered by tier, on purpose: a small number is evidence, and
        letting a big book overrule it would make the two arms fight.
        """
        assert _admits([_MEASURED_SMALL]) == set()

    def test_the_two_older_arms_are_untouched(self):
        """A widening that quietly narrows something else is not a widening."""
        got = _admits([_BRAZIL, _TIER1_UNMEASURED, _SPECIMEN])
        assert got == {5, 6, 57792790}

    def test_the_volume_is_null_half_is_load_bearing(self):
        """Mutation: drop ``volume IS NULL`` and the arm becomes a liquidity gate.

        Written as a mutation rather than as a comment because the conjunct
        reads like a redundant safety clause and is not: without it,
        `_MEASURED_SMALL` — measured, tiny, tier 2 — is admitted on its book
        alone, which re-opens #5268's question in the opposite direction.
        """
        mutated = fpr.VALUE_LIQUID_SQL.replace("fm.volume IS NULL AND ", "")
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE fm (id INT, volume INT, liquidity REAL)")
        con.executemany(
            "INSERT INTO fm VALUES (?,?,?)",
            [(3, 12, 50_000.0), (57792790, None, 8_930.67)],
        )
        where = mutated.replace("fm.", "").replace(":liquidity_floor", "1000")
        got = {r[0] for r in con.execute(f"SELECT id FROM fm WHERE {where}")}
        assert got == {3, 57792790}, "the mutant admits the measured-small row"
        # ...and the real predicate does not.
        assert _admits([_MEASURED_SMALL, _SPECIMEN]) == {57792790}


class TestTheNewRowsCannotDisplaceAMeasuredMarket:
    """The safety argument, and it lives in the OUTER ordering, not in the pool.

    `_take_for_source` slices the candidate list at the per-source budget. Every
    row this arm adds has ``volume IS NULL`` by construction, and the outer
    ``ORDER BY fm.volume DESC NULLS LAST`` puts all of them behind every measured
    market — so the arm can only spend budget the measured population did not
    need. That is what makes 971 extra rows a non-event for the existing sweep.
    """

    def test_the_volume_key_says_nulls_last_in_words(self):
        """🔴 SQLITE CANNOT JUDGE THIS ONE AND WOULD REPORT THAT IT PASSES.

        The tests below run the real ORDER BY through sqlite, which is the right
        rig for the tail ordering — but sqlite's DEFAULT for ``DESC`` is NULLS
        LAST and **Postgres's is NULLS FIRST**. So deleting the two words from
        the volume key changes nothing in sqlite and, in production, moves all
        971 net-new rows this arm adds to the FRONT of the list `_take_for_source`
        slices: the new arm would consume the whole per-source budget and starve
        every measured market, which is the exact regression it must not cause.

        Measured, not asserted: the second half of this test demonstrates the
        inversion in the harness itself, so the claim above cannot rot into a
        comment nobody rechecks. The token therefore gets a TEXT assertion, and
        it is not belt-and-braces — it is the only assertion of the two that can
        see the failure.
        """
        order = _normalise(_extract_order_by(fpr._CANDIDATE_SQL.text))
        assert order.startswith("fm.volume desc nulls last"), order

        # The inversion, demonstrated rather than claimed.
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE t (id INT, v INT)")
        con.executemany("INSERT INTO t VALUES (?,?)", [(1, None), (2, 5)])
        sqlite_default = [r[0] for r in con.execute("SELECT id FROM t ORDER BY v DESC")]
        assert sqlite_default == [2, 1], (
            "sqlite puts NULLs last by default on DESC; Postgres puts them "
            "first, which is why the text assertion above exists"
        )

    def test_null_volume_rows_sort_behind_every_measured_row(self):
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE fm (id INT, volume INT, liquidity REAL)")
        con.executemany(
            "INSERT INTO fm VALUES (?,?,?)",
            [
                (10, 114_137_967, 0.0),      # measured, huge
                (11, 10_000, 0.0),           # measured, at the floor
                (57792790, None, 8_930.67),  # #5781, big book
                (12, None, 99_999.0),        # #5781, bigger book
                (13, None, None),            # tier-1 unmeasured tail
            ],
        )
        order = _extract_order_by(fpr._CANDIDATE_SQL.text).replace("fm.", "")
        got = [r[0] for r in con.execute(f"SELECT id FROM fm ORDER BY {order}")]
        assert got[:2] == [10, 11], "a measured market must lead"
        assert set(got[2:]) == {12, 57792790, 13}

    def test_the_null_tail_is_ordered_by_the_key_that_admitted_it(self):
        """The tail used to be arbitrary, which under a budget is a lottery.

        Every NULL-volume row — tier-1 ones since #5268 and liquid ones now —
        came back in whatever order the plan produced. `liquidity DESC NULLS
        LAST, id` makes it deterministic and value-ordered. It cannot touch a
        measured row's position: those separate on the FIRST key.
        """
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE fm (id INT, volume INT, liquidity REAL)")
        con.executemany(
            "INSERT INTO fm VALUES (?,?,?)",
            [(13, None, None), (57792790, None, 8_930.67), (12, None, 99_999.0)],
        )
        order = _extract_order_by(fpr._CANDIDATE_SQL.text).replace("fm.", "")
        got = [r[0] for r in con.execute(f"SELECT id FROM fm ORDER BY {order}")]
        assert got == [12, 57792790, 13]

    def test_take_for_source_gives_the_budget_to_measured_rows_first(self):
        """End to end on the real slicer, not on the SQL alone.

        A budget of two over one measured and two liquid candidates must take
        the measured one; the liquid rows wait for the rotation (the Redis
        attempt marker plus the 6h capture anti-join), which is the same way the
        tier-1 tail has always been reached.
        """
        def _m(mid, volume):
            return {"id": mid, "source": "polymarket", "priority": False,
                    "volume": volume}

        # In the order the outer ORDER BY produces them.
        candidates = [_m(10, 114_137_967), _m(12, None), _m(57792790, None)]
        taken = fpr._take_for_source(candidates, "polymarket", 2)
        assert [m["id"] for m in taken] == [10, 12]


class TestThePoolIsThirdAndSeparate:
    def test_the_pool_has_its_own_limit_and_its_own_ordering(self):
        sql = _normalise(fpr.ELIGIBLE_POOL_SQL)
        assert "liquid_pool as materialized" in sql
        assert "limit :liquid_pool_limit" in sql
        # Ordered by the key that admitted it. Ordering this pool by volume
        # would order it by nothing at all — every row in it is NULL there.
        assert "order by fm.liquidity desc" in sql

    def test_the_two_older_pools_keep_their_own_bounds(self):
        """A third pool must not become a shared bound over three populations.

        That is the failure the per-source budgets replaced and the failure the
        two-pool split was for; a third arm is exactly when it comes back.
        """
        sql = _normalise(fpr.ELIGIBLE_POOL_SQL)
        assert "limit :value_pool_limit" in sql
        assert "limit :tier1_pool_limit" in sql
        assert sql.count("limit :") == 3
        assert "order by fm.volume desc" in sql   # value pool
        assert "order by fm.id" in sql            # tier1 pool

    def test_the_union_dedupes(self):
        """UNION, never UNION ALL.

        A tier-1 market with a posted book and no volume now satisfies the tier
        arm AND the liquid arm. The dedupe is what keeps it one candidate
        instead of two — and two would spend two budget slots on one round trip.
        """
        sql = _normalise(fpr.ELIGIBLE_POOL_SQL)
        assert "union all" not in sql
        assert sql.count("union") == 2

    def test_the_limit_leads_its_population(self):
        """A stable ordering under a BINDING limit is a fixed point.

        The same rule the tier-1 pool's note states: the limit must lead the
        population or the same head is selected every run and the tail — here
        the smallest books — is never seen.

        1,009 measured on production 2026-09-12 by running the ARM, not by
        adding up a census of a retyped predicate: the census said 977 and was
        wrong, because it bounded on `market_tier <> 1` while the arm has no
        tier bound at all.
        """
        measured_population = 1_009
        headroom = 1 - measured_population / fpr.LIQUID_POOL_LIMIT
        assert headroom >= fpr._POOL_LIMIT_HEADROOM_MIN
        assert fpr.LIQUID_POOL_LIMIT > measured_population


class TestTheSizeIsReportedLikeTheOtherTwo:
    """A pool that truncates in silence is the starvation this module ended."""

    class _PoolSession:
        def __init__(self, rows):
            self._rows = rows

        async def execute(self, *_a, **_kw):
            rows = self._rows

            class _R:
                @staticmethod
                def fetchall():
                    return rows

            return _R()

    @staticmethod
    def _row(mid, value_size, tier1_size, liquid_size):
        # id, source, external_id, volume, poly_event_id, venue_settled_since,
        # value_pool_size, tier1_pool_size, liquid_pool_size
        return (
            mid, "polymarket", str(mid), None, str(mid), None,
            value_size, tier1_size, liquid_size,
        )

    async def _scan(self, rows, **kw):
        stats: dict = {}
        await fpr._scan_candidates(
            self._PoolSession(rows),
            volume_floor=10_000,
            stale_hours=6,
            stats=stats,
            **kw,
        )
        return stats

    @pytest.mark.asyncio
    async def test_the_size_is_published(self):
        stats = await self._scan(
            [self._row(1, 10, 20, 30)],
            value_pool_limit=100, tier1_pool_limit=100, liquid_pool_limit=100,
        )
        assert stats["liquid_pool_size"] == 30
        # ...and it did not displace either of the other two, which is the
        # off-by-one this row shape exists to catch.
        assert stats["value_pool_size"] == 10
        assert stats["tier1_pool_size"] == 20

    @pytest.mark.asyncio
    async def test_at_the_limit_is_a_hit(self):
        stats = await self._scan(
            [self._row(1, 10, 20, 50)],
            value_pool_limit=100, tier1_pool_limit=100, liquid_pool_limit=50,
        )
        assert stats[fpr._STAT_LIQUID_POOL_HIT] is True
        assert fpr._STAT_VALUE_POOL_HIT not in stats
        assert fpr._STAT_TIER1_POOL_HIT not in stats

    @pytest.mark.asyncio
    async def test_approaching_the_limit_warns_first(self):
        """The signal that arrives while raising the limit is still free."""
        stats = await self._scan(
            [self._row(1, 10, 20, 99)],
            value_pool_limit=1_000, tier1_pool_limit=1_000,
            liquid_pool_limit=100,
        )
        assert fpr._STAT_LIQUID_POOL_HIT not in stats, "nothing truncated yet"
        assert "liquid 99/100" in stats[fpr._STAT_POOL_HEADROOM_LOW]

    @pytest.mark.asyncio
    async def test_a_quiet_night_does_not_report_an_empty_pool(self):
        """Zero candidates is not a zero pool — the sizes ride on a ROW.

        Everything being fresh returns no rows, so recording `0` would publish
        "the eligible population is empty" on the night the sweep worked.
        """
        stats = await self._scan([])
        assert "liquid_pool_size" not in stats


class TestEverySiteBindsTheNewParameters:
    """🔴 A MISSING BIND DOES NOT DEGRADE — SQLALCHEMY REFUSES THE STATEMENT.

    And in the task's own `remaining_stale` census it refuses inside a `try`,
    so the run reports a number about nobody rather than falling over.

    This class was a hand list first and the hand list missed a site: the PG-only
    integration suite composes `HIGH_VALUE_SQL` and built its own params dict, so
    nothing local could go red and CI said
    `InvalidRequestError: A value is required for bind parameter 'liquidity_floor'`.
    Then the replacement — a text scan for the parameter NAME in each composing
    file — passed a real mutant that deleted the bind from the pool dict, because
    the same word appears three more times in that file for unrelated reasons.

    So the bind set is a VALUE now, the sites take it whole, and what is asserted
    below is executable rather than textual.
    """

    def test_the_bind_set_is_one_value_and_it_is_complete(self):
        """Derived from the statement's own parameters, not from a list."""
        got = set(fpr.pool_bind_params())
        assert got == _binds_of(fpr.ELIGIBLE_POOL_SQL), (
            "the bind helper and the statement disagree"
        )
        # ...and the values are the module's constants, not re-typed numbers.
        p = fpr.pool_bind_params()
        assert p["volume_floor"] == fpr.HIGH_VALUE_VOLUME_FLOOR
        assert p["liquidity_floor"] == fpr.POSTED_LIQUIDITY_FLOOR
        assert p["value_pool_limit"] == fpr.VALUE_POOL_LIMIT
        assert p["tier1_pool_limit"] == fpr.TIER1_POOL_LIMIT
        assert p["liquid_pool_limit"] == fpr.LIQUID_POOL_LIMIT

    def test_the_value_predicate_needs_no_bind_the_helper_lacks(self):
        """`HIGH_VALUE_SQL` is a subset of the pool's binds, so one helper serves
        both — asserted, because a fourth arm could break that assumption."""
        assert _binds_of(fpr.HIGH_VALUE_SQL) <= set(fpr.pool_bind_params())

    def test_all_three_executing_sites_take_the_set_whole(self):
        """A site that spells the dict out for itself is the staleness channel."""
        import inspect

        import app.routes.admin_source_health as _health
        import tests.integration.test_futures_price_refresh_writes_pg as _pg

        assert "pool_params = pool_bind_params()" in inspect.getsource(_health)
        assert "**pool_bind_params()" in inspect.getsource(
            fpr._refresh_stale_futures_prices
        )
        assert "**pool_bind_params()" in inspect.getsource(_pg)
        # and they are the task's helper, not same-named locals.
        assert _health.pool_bind_params is fpr.pool_bind_params

    def test_the_scan_itself_still_binds_every_parameter(self):
        """`_scan_candidates` takes its bounds as keyword arguments rather than
        from the helper — they are per-call, which is what the manual entry
        point and the pool-limit tests need — so it is checked on its own."""
        src = _source_of(fpr._scan_candidates)
        for param in fpr.pool_bind_params():
            assert f'"{param}"' in src, f"_scan_candidates does not bind {param}"

    def test_every_statement_built_on_the_pool_is_discovered_and_classified(self):
        """🔴 I GOT THE POPULATION WRONG TWICE. THIS ASKS THE RIGHT QUESTION.

        Pass 1 was a hand list and missed `test_futures_price_refresh_writes_pg`.
        Pass 2 discovered files by searching for the two shared STRING names —
        and missed `test_kalshi_delisted_leg_retirement_pg`, which executes
        `_CANDIDATE_SQL` and never names `ELIGIBLE_POOL_SQL` at all. Both are
        PG-only, so both failed in CI and nowhere else.

        A caller does not have to name the string to need its binds. It needs
        them if it executes a STATEMENT BUILT FROM the string. So the statement
        names are DERIVED here — every module-level assignment in the two
        defining modules whose body interpolates a shared string — and the repo
        is then scanned for files naming any of them. Deriving rather than
        listing is the point: a fourth statement joins the population without
        anyone remembering to enrol it.
        """
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parents[1]
        definers = (
            root / "app" / "tasks" / "futures_price_refresh.py",
            root / "app" / "routes" / "admin_source_health.py",
        )

        statements = {"ELIGIBLE_POOL_SQL", "HIGH_VALUE_SQL"}
        pattern = re.compile(
            r"^(_?[A-Z][A-Z0-9_]*)\s*=\s*(?:text\(\s*)?\s*f?\"\"\"(.*?)\"\"\"",
            re.S | re.M,
        )
        for path in definers:
            for name, body in pattern.findall(path.read_text(encoding="utf-8")):
                if "{ELIGIBLE_POOL_SQL}" in body or "{HIGH_VALUE_SQL}" in body:
                    statements.add(name)
        assert {"_CANDIDATE_SQL", "_PRICE_DARK_SQL"} <= statements, (
            f"the derivation found {sorted(statements)} — it has stopped "
            "recognising the statement form and would discover nothing"
        )

        EXECUTES, MENTIONS, DEFINES = "executes", "mentions", "defines"
        classified = {
            "app/tasks/futures_price_refresh.py": DEFINES,
            "app/routes/admin_source_health.py": DEFINES,
            "tests/integration/test_futures_price_refresh_writes_pg.py": EXECUTES,
            "tests/integration/test_kalshi_delisted_leg_retirement_pg.py": EXECUTES,
            # Counts interpolation tokens in a source scan; never runs them.
            "tests/test_futures_price_refresh.py": MENTIONS,
            # Reads the strings to assert their shape; never runs them.
            "tests/test_posted_book_no_measured_volume_5781.py": MENTIONS,
        }
        # `polymarket_condition_refresh` and `feed_served_markets` mention
        # `HIGH_VALUE_SQL` in DOCSTRINGS and import neither module, so they are
        # correctly outside the population — prose is not a caller. The
        # pass-2 scan, which keyed on the string name alone, swept them in.
        # `_CANDIDATE_SQL` also names an UNRELATED statement in
        # `polymarket_condition_refresh`, so a bare name search collides. Only
        # files that reach OUR two modules count.
        ours = re.compile(
            r"(?:from|import) app\.tasks\.futures_price_refresh|"
            r"(?:from|import) app\.routes\.admin_source_health"
        )

        found = set()
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            rel = str(path.relative_to(root))
            text = path.read_text(encoding="utf-8", errors="ignore")
            if path in definers:
                found.add(rel)
            elif ours.search(text) and any(
                re.search(rf"\b{re.escape(n)}\b", text) for n in statements
            ):
                found.add(rel)

        assert not found - set(classified), (
            f"{sorted(found - set(classified))} reach a statement built on the "
            "shared value predicate and are not classified. Decide: does it "
            "EXECUTE one (then it must take `pool_bind_params()` whole) or only "
            "MENTION it?"
        )
        assert not set(classified) - found, (
            f"{sorted(set(classified) - found)} are classified but no longer "
            "reach one — drop them, a stale entry hides a deletion"
        )
        executors = [r for r, k in classified.items() if k == EXECUTES]
        assert len(executors) == 2
        for rel in executors:
            assert "pool_bind_params()" in (root / rel).read_text(encoding="utf-8"), (
                f"{rel} executes a pool statement without taking the bind set whole"
            )


# --- helpers -----------------------------------------------------------------


def _binds_of(sql: str) -> set:
    """The named bind parameters a statement actually needs.

    Quoted literals are stripped FIRST and ``::`` casts excluded, because a
    naive ``:(\\w+)`` over this SQL returns ``MI`` and ``SS`` out of a
    ``'HH24:MI:SS'`` time format — a bind census that invents two parameters
    nobody can supply, which is how a parity test starts failing for a reason
    that has nothing to do with parity.
    """
    import re

    without_literals = re.sub(r"'[^']*'", "''", sql)
    return set(re.findall(r"(?<![:\w]):([a-z_][a-z0-9_]*)", without_literals))


def _normalise(sql: str) -> str:
    return " ".join(sql.lower().split())


def _source_of(fn) -> str:
    import inspect

    return inspect.getsource(fn)


def _extract_order_by(sql: str) -> str:
    """The outer ORDER BY of the candidate statement, read from the real text.

    Read rather than retyped: a test that hard-codes the ordering it wants is a
    test that agrees with itself. The outer one is the LAST in the statement —
    the pool CTEs carry their own.
    """
    lowered = sql.lower()
    idx = lowered.rindex("order by")
    return sql[idx + len("order by"):].strip()
