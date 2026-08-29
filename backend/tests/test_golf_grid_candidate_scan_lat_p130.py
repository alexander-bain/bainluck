"""LAT-P130 — the golf grid stops running the same whole-table scan once per tour.

``/api/playoffs/golf`` builds one grid per active DataGolf tour, and each tour
called ``_query_tournament_db_markets`` to find its candidate markets. That
function ran::

    external_id ILIKE 'golf_pga%' OR ... OR llm_sport_category = 'golf'
    AND status != 'resolved' AND source != 'datagolf'

Two defects sat on top of each other.

**One:** the predicate ORs two unrelated columns, so no index can serve it and
Postgres reads the whole table. Measured on production 2026-08-29 against the
exact SQL SQLAlchemy emits: a parallel Seq Scan over all 911,284 rows,
455,594 discarded per worker, **6,122 ms** and 50,364 blocks off disk — to
return **96** markets.

**Two:** the SQL is identical for every tour. Nothing in it depends on the
tournament; only the Python filter underneath it does. Three tours were live
(PGA, European, Korn Ferry) plus any upcoming major, so a cold build paid for
that scan three or more times inside a 25 s request budget — and lost. Before
this change, an uncached ``/api/playoffs/golf`` rebuild returned **HTTP 503**
after 25 s: "timed out and no last-good payload is available".

The fix is the pairing ``models.py`` already documents. ``external_id`` holds
"sport_key or event_ticker" and which one is decided entirely by ``source``, so
golf's Odds API sport keys can only ever match ``odds_api`` rows — twelve in the
whole table. Naming that turns the branch into an index scan: **483 ms** via a
``BitmapOr`` over ``ix_fm_source_created_at`` + ``ix_fm_golf_identity_category``,
returning the identical 96 rows. And the load is hoisted to once per build.

**Why these tests look the way they do.** Neither defect was visible on the
page. The predicate selected exactly the right markets and the repetition
returned exactly the right rows every time — the only tells were a query plan
and a query count. A results test passes against both defects and a timing test
merely gets slower on a bad day. So these guards assert the emitted predicate's
SHAPE and the number of loads, and ``_matches`` evaluates the real clause object
the route hands SQLAlchemy so the behavioural cases cannot drift into being a
re-implementation of the filter. No database is needed.
"""

import pytest
from sqlalchemy import and_, or_
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import (
    BinaryExpression,
    BooleanClauseList,
    Grouping,
)

from app.config.league_configs import get_league_config
from app.models import FuturesMarket
from app.routes import playoffs
from app.routes.playoffs import (
    GolfCandidateMarkets,
    _GOLF_SPORT_KEY_ID_SPACE_SOURCE,
    _build_golf_candidate_filters,
)


GOLF = get_league_config("golf")


# ---------------------------------------------------------------------------
# A tiny evaluator over the REAL clause object.
#
# The filter only ever uses `=`, `!=`, `ILIKE`, `AND` and `OR`, so a fixture row
# can be matched against the actual expression the route builds. The behavioural
# assertions therefore cannot pass against a filter the route does not use.
# ---------------------------------------------------------------------------

def _ilike_to_regex(pattern: str):
    import re as _re

    out = []
    for ch in pattern:
        if ch == "%":
            out.append(".*")
        elif ch == "_":
            out.append(".")
        else:
            out.append(_re.escape(ch))
    return _re.compile("^" + "".join(out) + "$", _re.IGNORECASE | _re.DOTALL)


def _matches(clause, row: dict) -> bool:
    """Evaluate a golf candidate-filter clause against a fixture market row."""
    if isinstance(clause, Grouping):
        return _matches(clause.element, row)
    if isinstance(clause, BooleanClauseList):
        results = [_matches(c, row) for c in clause.clauses]
        if clause.operator is operators.and_:
            return all(results)
        if clause.operator is operators.or_:
            return any(results)
        raise AssertionError(f"unhandled boolean operator {clause.operator!r}")
    if isinstance(clause, BinaryExpression):
        column = clause.left.key
        value = row.get(column)
        bound = clause.right.value
        if clause.operator is operators.eq:
            return value == bound
        if clause.operator is operators.ne:
            return value != bound
        if clause.operator is operators.ilike_op:
            return value is not None and bool(_ilike_to_regex(bound).match(value))
        raise AssertionError(f"unhandled operator {clause.operator!r}")
    raise AssertionError(f"unhandled clause node {type(clause).__name__}")


def _matches_all(clauses, row: dict) -> bool:
    return all(_matches(c, row) for c in clauses)


def _walk(clause):
    """Yield ``(node, ancestors)`` for every node in the clause tree."""

    def rec(node, ancestors):
        yield node, ancestors
        chain = ancestors + [node]
        if isinstance(node, Grouping):
            yield from rec(node.element, chain)
        elif isinstance(node, BooleanClauseList):
            for child in node.clauses:
                yield from rec(child, chain)

    yield from rec(clause, [])


def _source_equalities_under(node) -> set:
    """Every ``source = <value>`` equality anywhere under ``node``."""
    found = set()
    for child, _ in _walk(node):
        if (
            isinstance(child, BinaryExpression)
            and child.operator is operators.eq
            and getattr(child.left, "key", None) == "source"
        ):
            found.add(child.right.value)
    return found


def _guarding_source_scope(ancestors) -> set:
    """Sources pinned by an ancestor ``AND`` of the node being inspected."""
    scopes = set()
    for anc in ancestors:
        if isinstance(anc, BooleanClauseList) and anc.operator is operators.and_:
            for sibling in anc.clauses:
                scopes |= _source_equalities_under(sibling)
    return scopes


# The historical shape, pinned here so the behavioural comparison is against the
# predicate that actually shipped rather than a description of it.
def _legacy_golf_filters(config):
    return [
        or_(
            *[FuturesMarket.external_id.ilike(f"{sk}%") for sk in config.sport_keys],
            FuturesMarket.llm_sport_category == "golf",
        ),
        FuturesMarket.status != "resolved",
        FuturesMarket.source != "datagolf",
    ]


def _row(**over):
    base = {
        "source": "kalshi",
        "external_id": "KXPGATOUR-26",
        "llm_sport_category": "golf",
        "status": "open",
        "name": "PGA Tour Winner",
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# Shape — the defect's only symptom was a query plan, so assert the plan's cause
# ---------------------------------------------------------------------------

class TestSportKeyBranchIsSourceScoped:
    def test_every_external_id_ilike_is_scoped_to_the_source_owning_that_id_space(self):
        """A bare ``external_id ILIKE`` at OR-level is the whole defect.

        This is the test that must go red if someone reinstates the flat OR.
        """
        clauses = _build_golf_candidate_filters(GOLF)
        seen = 0
        for clause in clauses:
            for node, ancestors in _walk(clause):
                if (
                    isinstance(node, BinaryExpression)
                    and node.operator is operators.ilike_op
                    and getattr(node.left, "key", None) == "external_id"
                ):
                    seen += 1
                    scope = _guarding_source_scope(ancestors)
                    assert scope == {_GOLF_SPORT_KEY_ID_SPACE_SOURCE}, (
                        f"external_id ILIKE {node.right.value!r} is guarded by "
                        f"source scope {scope or '{}'} — it must be scoped to "
                        f"{_GOLF_SPORT_KEY_ID_SPACE_SOURCE!r}, the only source "
                        f"whose external_id holds Odds API sport keys. An "
                        f"unscoped external_id predicate ORed against "
                        f"llm_sport_category spans two columns, which no index "
                        f"serves, which is a full scan of futures_markets."
                    )
        assert seen == len(GOLF.sport_keys), (
            f"expected one external_id ILIKE per golf sport key "
            f"({len(GOLF.sport_keys)}), found {seen}"
        )

    def test_the_id_space_source_is_odds_api(self):
        assert _GOLF_SPORT_KEY_ID_SPACE_SOURCE == "odds_api"

    def test_legacy_flat_or_would_fail_the_shape_test(self):
        """The guard is only worth having if the old shape fails it."""
        offenders = []
        for clause in _legacy_golf_filters(GOLF):
            for node, ancestors in _walk(clause):
                if (
                    isinstance(node, BinaryExpression)
                    and node.operator is operators.ilike_op
                    and getattr(node.left, "key", None) == "external_id"
                    and _guarding_source_scope(ancestors)
                    != {_GOLF_SPORT_KEY_ID_SPACE_SOURCE}
                ):
                    offenders.append(node.right.value)
        assert offenders, (
            "the legacy flat OR must be detected as unscoped, otherwise the "
            "shape test above proves nothing"
        )


class TestSecondDoor:
    """The fast, silent, empty-grid mistake.

    Scoping BOTH branches to ``odds_api`` is even faster and returns twelve
    candidate rows instead of ninety-six — the grid would go blank and every
    timing check would look excellent.
    """

    def test_category_branch_is_not_source_scoped(self):
        clauses = _build_golf_candidate_filters(GOLF)
        found = 0
        for clause in clauses:
            for node, ancestors in _walk(clause):
                if (
                    isinstance(node, BinaryExpression)
                    and node.operator is operators.eq
                    and getattr(node.left, "key", None) == "llm_sport_category"
                ):
                    found += 1
                    assert not _guarding_source_scope(ancestors), (
                        "llm_sport_category is written for kalshi and polymarket "
                        "rows too, and they are where every candidate actually "
                        "comes from. Scoping this branch to a source drops them."
                    )
        assert found == 1, f"expected exactly one llm_sport_category branch, got {found}"

    def test_kalshi_and_polymarket_rows_still_match_by_category(self):
        clauses = _build_golf_candidate_filters(GOLF)
        for source in ("kalshi", "polymarket"):
            row = _row(source=source, external_id=f"{source}-xyz-1")
            assert _matches_all(clauses, row), (
                f"a {source} market categorised as golf must remain a candidate"
            )


class TestNonNegotiableExclusions:
    def test_resolved_markets_are_excluded(self):
        clauses = _build_golf_candidate_filters(GOLF)
        assert not _matches_all(clauses, _row(status="resolved"))

    def test_datagolf_rows_are_excluded(self):
        clauses = _build_golf_candidate_filters(GOLF)
        assert not _matches_all(clauses, _row(source="datagolf"))

    def test_non_golf_categories_are_excluded(self):
        clauses = _build_golf_candidate_filters(GOLF)
        assert not _matches_all(
            clauses, _row(llm_sport_category="baseball", external_id="KXMLB-26")
        )


class TestBehaviouralAgreementWithTheLegacyFilter:
    """Same rows, on the population that exists.

    Equivalence here is a POPULATION fact, not a logical identity, and it is
    stated as one. Verified whole-table on production 2026-08-29: zero rows with
    ``source <> 'odds_api'`` carry any of golf's five sport-key prefixes in
    ``external_id`` (0 of 911,284 scanned), and zero rows have a NULL source. The
    one row shape where old and new disagree is asserted explicitly below so the
    divergence is a decision on the record rather than a surprise.
    """

    CORPUS = [
        _row(source="odds_api", external_id="golf_pga", llm_sport_category=None),
        _row(source="odds_api", external_id="golf_masters", llm_sport_category=None),
        _row(source="odds_api", external_id="golf_us_open", llm_sport_category="golf"),
        _row(source="odds_api", external_id="golf_pga_championship_winner"),
        _row(source="odds_api", external_id="baseball_mlb", llm_sport_category="baseball"),
        _row(source="kalshi", external_id="KXPGATOUR-26TOURCH"),
        _row(source="kalshi", external_id="KXMLB-26", llm_sport_category="baseball"),
        _row(source="polymarket", external_id="0xabc", llm_sport_category="golf"),
        _row(source="polymarket", external_id="0xdef", llm_sport_category=None),
        _row(source="kalshi", external_id="KXPGATOUR-26", status="resolved"),
        _row(source="datagolf", external_id="dg-1"),
        _row(source="kalshi", external_id=None, llm_sport_category="golf"),
        _row(source="kalshi", external_id=None, llm_sport_category=None),
    ]

    @pytest.mark.parametrize("row", CORPUS, ids=lambda r: f"{r['source']}:{r['external_id']}")
    def test_old_and_new_agree_on_every_real_row_shape(self, row):
        old = _matches_all(_legacy_golf_filters(GOLF), row)
        new = _matches_all(_build_golf_candidate_filters(GOLF), row)
        assert old == new, (
            f"candidate membership changed for {row!r}: legacy={old} new={new}"
        )

    def test_the_one_documented_divergence_is_a_row_that_does_not_exist(self):
        """A non-odds_api row carrying an Odds API sport key.

        The new filter drops it; the old one kept it. Production has zero such
        rows across the whole table, which is why this is a safe trade and why
        it is written down instead of assumed. If this ever becomes reachable,
        the source-scoping premise is broken and the equivalence script
        (``scripts/lat_p130_verify_golf_equivalence.py``) is what says so.
        """
        impossible = _row(
            source="kalshi", external_id="golf_pga_something", llm_sport_category=None
        )
        assert _matches_all(_legacy_golf_filters(GOLF), impossible) is True
        assert _matches_all(_build_golf_candidate_filters(GOLF), impossible) is False


class TestDegenerateConfig:
    def test_no_sport_keys_falls_back_to_the_category_branch_alone(self):
        """``or_()`` with no clauses is a SQLAlchemy footgun, not a filter."""

        class _Cfg:
            sport_keys: list = []

        clauses = _build_golf_candidate_filters(_Cfg())
        assert _matches_all(clauses, _row(source="kalshi", llm_sport_category="golf"))
        assert not _matches_all(
            clauses, _row(source="odds_api", external_id="golf_pga", llm_sport_category=None)
        )


# ---------------------------------------------------------------------------
# Count — the second defect returned the right rows every time it ran
# ---------------------------------------------------------------------------

class _CountingLoader:
    """Stands in for ``_load_golf_candidate_markets`` and counts real loads."""

    def __init__(self, markets=None):
        self.calls = 0
        self.markets = markets if markets is not None else ["m1", "m2"]

    async def __call__(self, db, config):
        self.calls += 1
        return list(self.markets)


class TestGolfCandidateMarkets:
    @pytest.mark.asyncio
    async def test_repeated_gets_issue_exactly_one_query(self, monkeypatch):
        loader = _CountingLoader()
        monkeypatch.setattr(playoffs, "_load_golf_candidate_markets", loader)
        holder = GolfCandidateMarkets(db=object(), config=GOLF)

        first = await holder.get()
        for _ in range(4):
            assert await holder.get() == first

        assert loader.calls == 1, (
            f"five consumers caused {loader.calls} scans of futures_markets; the "
            f"whole point of this ship is that they cause one"
        )
        assert holder.loads == 1

    @pytest.mark.asyncio
    async def test_it_is_lazy_so_an_off_season_build_queries_nothing(self, monkeypatch):
        loader = _CountingLoader()
        monkeypatch.setattr(playoffs, "_load_golf_candidate_markets", loader)
        holder = GolfCandidateMarkets(db=object(), config=GOLF)
        assert loader.calls == 0
        assert holder.loads == 0

    @pytest.mark.asyncio
    async def test_two_holders_share_no_state(self, monkeypatch):
        """Gotcha #6: a cache surviving between requests would hold ORM rows
        bound to a closed session. This one is per-build and must stay so."""
        loader = _CountingLoader()
        monkeypatch.setattr(playoffs, "_load_golf_candidate_markets", loader)

        await GolfCandidateMarkets(db=object(), config=GOLF).get()
        await GolfCandidateMarkets(db=object(), config=GOLF).get()

        assert loader.calls == 2
        assert "_markets" in GolfCandidateMarkets.__slots__, (
            "the candidate set must live in per-instance storage, never as "
            "class state that outlives the session its ORM rows are bound to"
        )
        assert type(GolfCandidateMarkets.__dict__["_markets"]).__name__ == (
            "member_descriptor"
        )

    @pytest.mark.asyncio
    async def test_an_empty_result_is_still_only_fetched_once(self, monkeypatch):
        """``None`` means unloaded; ``[]`` means loaded and empty."""
        loader = _CountingLoader(markets=[])
        monkeypatch.setattr(playoffs, "_load_golf_candidate_markets", loader)
        holder = GolfCandidateMarkets(db=object(), config=GOLF)
        assert await holder.get() == []
        assert await holder.get() == []
        assert loader.calls == 1


class TestConsumersUseTheSharedHolder:
    @pytest.mark.asyncio
    async def test_query_tournament_db_markets_uses_the_holder_when_given_one(
        self, monkeypatch
    ):
        loader = _CountingLoader(markets=[])
        monkeypatch.setattr(playoffs, "_load_golf_candidate_markets", loader)
        holder = GolfCandidateMarkets(db=object(), config=GOLF)

        for tour in ("pga", "euro", "kft"):
            await playoffs._query_tournament_db_markets(
                object(), GOLF, "TOUR Championship", tour, candidates=holder
            )

        assert loader.calls == 1

    @pytest.mark.asyncio
    async def test_query_tournament_db_markets_still_works_standalone(self, monkeypatch):
        """The holder is an optimisation, not a new required argument."""
        loader = _CountingLoader(markets=[])
        monkeypatch.setattr(playoffs, "_load_golf_candidate_markets", loader)
        await playoffs._query_tournament_db_markets(object(), GOLF, "Masters", "pga")
        assert loader.calls == 1

    @pytest.mark.asyncio
    async def test_upcoming_major_grid_reuses_the_holder(self, monkeypatch):
        loader = _CountingLoader(markets=[])
        monkeypatch.setattr(playoffs, "_load_golf_candidate_markets", loader)
        holder = GolfCandidateMarkets(db=object(), config=GOLF)
        await holder.get()

        await playoffs._build_upcoming_golf_event_grid(
            tournament_name="Masters Tournament",
            start_date="2026-04-09",
            end_date="2026-04-12",
            course=None,
            location=None,
            country=None,
            config=GOLF,
            db=object(),
            trend_hours=168,
            top=10,
            candidates=holder,
        )

        assert loader.calls == 1, (
            "the upcoming-major grid ran the identical query a second time"
        )


class TestBuildWiring:
    """One holder must reach every tour and every upcoming major in a build.

    This is the guard that goes red if the plumbing is dropped: the stubs stand
    where the real grid builders stand and record the holder they were handed,
    so ``candidates=None`` — the pre-P130 behaviour, one scan each — fails.
    """

    @pytest.mark.asyncio
    async def test_one_holder_reaches_every_tour(self, monkeypatch):
        monkeypatch.setenv("DATAGOLF_API_KEY", "test-key")

        class _FakeService:
            async def get_schedule(self, tour):
                return []

            async def close(self):
                return None

        import app.services.datagolf_api as dg_mod

        monkeypatch.setattr(dg_mod, "DataGolfAPIService", lambda: _FakeService())

        received = []
        loader = _CountingLoader(markets=["m"])
        monkeypatch.setattr(playoffs, "_load_golf_candidate_markets", loader)

        async def _stub_tour_grid(
            service, tour, config, db, trend_hours, top, candidates=None
        ):
            received.append((tour, candidates))
            assert candidates is not None, (
                f"tour {tour!r} was not given the build's candidate holder and "
                f"would run its own full scan of futures_markets"
            )
            await candidates.get()
            return {"tour": tour, "teams": [], "tournament": {"name": tour}}

        monkeypatch.setattr(playoffs, "_build_golf_tour_grid", _stub_tour_grid)

        result = await playoffs._build_golf_grid_from_datagolf(
            GOLF, db=object(), trend_hours=168, top=10
        )

        assert result is not None
        assert [t for t, _ in received] == ["pga", "euro", "kft", "opp", "alt"]
        holders = {id(c) for _, c in received}
        assert len(holders) == 1, "each tour got its own holder — that is N scans, not one"
        assert loader.calls == 1, (
            f"a five-tour build issued {loader.calls} candidate scans"
        )

    @pytest.mark.asyncio
    async def test_upcoming_major_gets_the_same_holder_as_the_tours(self, monkeypatch):
        monkeypatch.setenv("DATAGOLF_API_KEY", "test-key")

        class _Tourney:
            event_name = "Masters Tournament"
            start_date = "2026-04-09"
            end_date = "2026-04-12"
            course = None
            location = None
            country = None
            status = "upcoming"

        class _FakeService:
            async def get_schedule(self, tour):
                return [_Tourney()] if tour == "pga" else []

            async def close(self):
                return None

        import app.services.datagolf_api as dg_mod

        monkeypatch.setattr(dg_mod, "DataGolfAPIService", lambda: _FakeService())

        loader = _CountingLoader(markets=["m"])
        monkeypatch.setattr(playoffs, "_load_golf_candidate_markets", loader)

        seen = []

        async def _stub_tour_grid(
            service, tour, config, db, trend_hours, top, candidates=None
        ):
            if tour != "pga":
                return None
            seen.append(("tour", candidates))
            await candidates.get()
            return {"tour": "pga", "teams": [], "tournament": {"name": "TOUR Championship"}}

        async def _stub_major(**kwargs):
            seen.append(("major", kwargs.get("candidates")))
            assert kwargs.get("candidates") is not None
            await kwargs["candidates"].get()
            return {"tour": "pga", "teams": [], "tournament": {"name": "Masters Tournament"}}

        monkeypatch.setattr(playoffs, "_build_golf_tour_grid", _stub_tour_grid)
        monkeypatch.setattr(playoffs, "_build_upcoming_golf_event_grid", _stub_major)

        await playoffs._build_golf_grid_from_datagolf(
            GOLF, db=object(), trend_hours=168, top=10
        )

        kinds = [k for k, _ in seen]
        assert "major" in kinds, "the upcoming-major branch did not run"
        assert len({id(c) for _, c in seen}) == 1
        assert loader.calls == 1


class TestTheQueryIsStillTheOneWeMeasured:
    def test_compiled_sql_is_the_shape_that_was_explained_on_production(self):
        """Pins the emitted SQL against the plan captured in the audit doc.

        Not a duplicate of the shape tests: those assert structure, this asserts
        the literal text whose ``EXPLAIN ANALYZE`` is the evidence for 6,122 ms
        -> 483 ms. If the text drifts, the measurement no longer describes the
        code and the audit doc needs re-running, not re-reading.
        """
        from sqlalchemy import select

        stmt = select(FuturesMarket.id).where(*_build_golf_candidate_filters(GOLF))
        sql = " ".join(
            str(stmt.compile(compile_kwargs={"literal_binds": True})).split()
        )
        assert (
            "WHERE (futures_markets.source = 'odds_api' AND "
            "(lower(futures_markets.external_id) LIKE lower('golf_pga%')" in sql
        )
        assert "OR futures_markets.llm_sport_category = 'golf')" in sql
        assert "futures_markets.status != 'resolved'" in sql
        assert "futures_markets.source != 'datagolf'" in sql


def test_and_or_imports_are_used_so_the_module_still_builds_both_forms():
    """Trivial, but it keeps ruff from being the only thing that notices."""
    assert and_ is not None and or_ is not None
