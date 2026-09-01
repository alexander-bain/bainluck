"""Q499 guards — the residual drain for prices that name no side.

PILLAR: FORMATTING. SHIP: a price on the US Open page names its side, for the
1,152 markets Q492's writer-only fix could never reach.

The three things these guards exist to stop, in the order they would actually
happen:

1. **The rail growing a label rule of its own.** Splitting "Venue: X vs Y" on
   " vs " is the shortcut that looks right and is the exact mutant Q492's own
   guard was written to catch — it cannot tell which side the price belongs to,
   which IS the defect. An AST guard fails the build if this file learns one.
2. **The venue read quietly covering 18% of its population.**
   `/markets?condition_ids=…` applies a `closed=false` filter nobody asked for.
   Measured on a 40-id sample from this cohort: 7 of 40 on the default call, the
   other 33 on the `closed=true` pass. A drain on the default read would report
   82% `not_at_venue` and look finished.
3. **A budget that reads as bounded and is not.** Every terminal here must hand
   back a cursor; an H12 returns no body, so an attended drain loses its place.
"""

import ast
import inspect

import pytest

from app.tasks import repair_polymarket_leg_label as rail


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, rows=(), scalar=0):
        self._rows = list(rows)
        self._scalar = scalar

    def fetchall(self):
        return self._rows

    def scalar_one(self):
        return self._scalar


class _Session:
    """Records every statement the rail issues, routed by statement SHAPE.

    Routed on shape rather than call ORDER so that a rail which reorders its
    queries is still measured correctly, instead of silently reading a page as
    a count.
    """

    def __init__(self, page=(), remaining=0, landed=None, census_rows=()):
        self.page = list(page)
        self.remaining = remaining
        #: ids the compare-and-set is allowed to return. ``None`` = all of them,
        #: which is the un-raced case.
        self.landed = landed
        self.census_rows = list(census_rows)
        self.statements: list[tuple[str, dict]] = []
        self.writes: list[tuple[str, dict]] = []
        self.commits = 0
        self.rollbacks = 0
        self.invalidations = 0

    @property
    def page_sql(self) -> str:
        for sql, _p in self.statements:
            if "LIMIT :cap::int" in sql:
                return sql
        raise AssertionError(
            "the rail never issued its page query — every pager assertion in "
            f"this test would be vacuous. Statements seen: {self.statements!r}"
        )

    @property
    def page_params(self) -> dict:
        for sql, params in self.statements:
            if "LIMIT :cap::int" in sql:
                return params
        raise AssertionError("the rail never issued its page query")

    @property
    def write_sql(self) -> str:
        if not self.writes:
            raise AssertionError(
                "the rail issued no UPDATE — a write assertion here would be "
                f"vacuous. Statements seen: {self.statements!r}"
            )
        return self.writes[0][0]

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        self.statements.append((sql, dict(params or {})))
        upper = sql.upper()
        if upper.startswith("SET LOCAL"):
            return _Result()
        if upper.startswith("UPDATE"):
            self.writes.append((sql, dict(params or {})))
            ids = [v for k, v in (params or {}).items() if k.startswith("id")]
            if self.landed is not None:
                ids = [i for i in ids if i in self.landed]
            return _Result(rows=[(i,) for i in ids])
        if "LIMIT :cap::int" in sql:
            return _Result(rows=self.page)
        if upper.startswith("SELECT COUNT("):
            return _Result(scalar=self.remaining)
        if "GROUP BY" in upper:
            return _Result(rows=self.census_rows)
        return _Result()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def invalidate(self):
        self.invalidations += 1


class _Market:
    """The shape ``_leg_label`` actually reads. Deliberately not a Mock: a Mock
    answers every attribute, so a rail reading the WRONG field would pass."""

    def __init__(self, condition_id, question, outcomes, group_item_title=None):
        self.condition_id = condition_id
        self.question = question
        self.outcomes = list(outcomes)
        self.group_item_title = group_item_title


def _row(outcome_id, market_id, condition_id, name, category="tennis"):
    """One page row, in the tuple order the rail's own SELECT emits."""
    return (outcome_id, market_id, condition_id, name, name, category)


class _FakeService:
    def __init__(self, markets, *, raises=None):
        self.markets = {m.condition_id: m for m in markets}
        self.raises = raises
        self.calls: list[dict] = []
        self.closed = False

    async def get_markets_by_conditions(self, condition_ids, **kwargs):
        self.calls.append({"ids": list(condition_ids), **kwargs})
        if self.raises is not None:
            raise self.raises
        return [self.markets[c] for c in condition_ids if c in self.markets]

    async def close(self):
        self.closed = True


def _venue(monkeypatch, service):
    """Patch the SERVICE CLASS the rail constructs, not `_fetch_batch`.

    Patching `_fetch_batch` would make guard 2 below — that the drain asks for
    closed markets — untestable, because the kwarg it asserts on is passed
    inside the function it would have replaced.
    """
    import app.services.polymarket_api as svc

    monkeypatch.setattr(svc, "PolymarketAPIService", lambda: service)
    return service


@pytest.fixture
def fast(monkeypatch):
    """Remove the deliberate venue pause so the suite is not paced by it.

    Defined locally rather than imported from a sibling test module: importing a
    fixture shadows it at every use site (14 x F811 on the sibling rail's files).
    `test_the_venue_pause_is_real_in_production` keeps the real value honest, so
    this fixture cannot hide its removal.
    """
    monkeypatch.setattr(rail, "VENUE_PAUSE", 0)


# ---------------------------------------------------------------------------
# 1. The rail must never learn a label rule of its own
# ---------------------------------------------------------------------------


def test_the_drain_calls_the_shipped_labeller_and_does_not_restate_it():
    """The M2 mutant, killed by construction rather than by review.

    A second labeller is a second classifier free to drift from the poller, and
    the drift would be invisible because both answers look plausible. So the
    rail must CALL `_leg_label` — and this asserts the call exists, because a
    guard that only banned the shortcut would pass on a file that had deleted
    the labelling entirely.
    """
    tree = ast.parse(inspect.getsource(rail))
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_leg_label" in called, (
        "the rail no longer calls the shipped `_leg_label`; whatever it labels "
        "with now is a second classifier"
    )


def test_the_drain_has_no_matchup_splitting_rule_of_its_own():
    """Bans the shortcut in EXECUTABLE code only.

    Docstring prose legitimately discusses "Venue: X vs Y" at length — naming the
    trap is how the next reader avoids re-introducing it, and a guard that banned
    the words would delete its own explanation. Split with the AST rather than a
    regex over source, because a regex is how a guard like this quietly stops
    seeing half its subject.
    """
    src = inspect.getsource(rail)
    assert len(src) > 5000, "source unexpectedly short — this guard would be vacuous"

    tree = ast.parse(src)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docstrings.add(doc)

    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value not in docstrings
    ]
    # Non-vacuity: the scan must actually be finding executable literals.
    assert len(literals) > 20, (
        f"only {len(literals)} executable string literals found — the AST split "
        "has stopped seeing its subject"
    )

    banned = [lit for lit in literals if " vs " in lit.lower() or " vs. " in lit.lower()]
    assert not banned, (
        f"executable code contains a matchup separator {banned!r} — this rail is "
        "one line from deriving a side by splitting the market name, which is the "
        "mutant Q492's guard exists to catch"
    )

    called_attrs = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not ({"split", "partition", "rsplit"} & called_attrs), (
        "the rail is splitting strings; the only label it may store is the "
        "venue's own, via `_leg_label`"
    )


# ---------------------------------------------------------------------------
# 2. The venue read — the closed=false trap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_drain_asks_the_venue_for_closed_markets_too(monkeypatch, fast):
    """The single most load-bearing kwarg in this rail.

    Measured against production Gamma: on a 40-id sample from this exact cohort
    the default read returned 7 of 40. Without `include_closed=True` this drain
    would classify 33 of every 40 legs `not_at_venue` and report itself done.
    """
    market = _Market(
        "0xaa", "Manacor: Mark Lajal vs Gabi Adrian Boitan", ["Mark Lajal", "Gabi"]
    )
    service = _venue(monkeypatch, _FakeService([market]))
    session = _Session(page=[_row(1, 10, "0xaa", "Manacor: Mark Lajal vs Gabi Adrian Boitan")])

    await rail.repair(session, apply=False)

    assert service.calls, "the rail never asked the venue anything"
    assert service.calls[0].get("include_closed") is True, (
        "the drain asked the venue with the DEFAULT read, which silently filters "
        f"closed=false. Call was: {service.calls[0]!r}"
    )


@pytest.mark.asyncio
async def test_the_service_issues_two_requests_when_closed_markets_are_wanted():
    """The other half: the kwarg must actually change the wire traffic.

    `closed` is a strict FILTER, not an include-toggle — asking with
    `closed=true` DROPS the open markets — so covering a mixed cohort costs two
    requests. Both arms are asserted, because a helper that always made two
    requests would pass a one-armed test and would change every existing
    caller's traffic.
    """
    from app.services.polymarket_api import PolymarketAPIService

    class _Resp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class _Client:
        def __init__(self):
            self.params_seen = []

        async def get(self, _path, params=None):
            self.params_seen.append(list(params or []))
            closed = dict(params or {}).get("closed")
            if closed == "true":
                return _Resp([{"conditionId": "0xclosed", "question": "c",
                               "outcomes": '["A", "B"]', "outcomePrices": "[]"}])
            return _Resp([{"conditionId": "0xopen", "question": "o",
                           "outcomes": '["C", "D"]', "outcomePrices": "[]"}])

    service = PolymarketAPIService()
    service.gamma_client = _Client()

    default = await service.get_markets_by_conditions(["0xopen", "0xclosed"])
    assert len(service.gamma_client.params_seen) == 1, (
        "the DEFAULT call changed shape — every existing caller (the UX-P139 "
        "register, the token top-up) would start issuing double the traffic"
    )
    assert {m.condition_id for m in default} == {"0xopen"}

    service.gamma_client = _Client()
    both = await service.get_markets_by_conditions(
        ["0xopen", "0xclosed"], include_closed=True
    )
    assert len(service.gamma_client.params_seen) == 2
    assert dict(service.gamma_client.params_seen[1]).get("closed") == "true"
    assert {m.condition_id for m in both} == {"0xopen", "0xclosed"}, (
        "the two responses were not unioned — the closed pass replaced the open "
        "one rather than adding to it"
    )


# ---------------------------------------------------------------------------
# 3. What the rail does with an answer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_dry_run_plans_the_rename_and_writes_nothing(monkeypatch, fast):
    market = _Market("0xaa", "Manacor: A vs B", ["Anna Player", "Bea Player"])
    _venue(monkeypatch, _FakeService([market]))
    session = _Session(page=[_row(1, 10, "0xaa", "Manacor: A vs B")])

    out = await rail.repair(session, apply=False)

    assert out["applied"] is False
    assert session.writes == [], "a dry run issued an UPDATE"
    assert session.commits == 0
    assert out["planned"] == 1
    assert out["samples"][0]["to"] == "Anna Player"
    assert out["counts"]["relabelled"] == 0


@pytest.mark.asyncio
async def test_an_apply_stores_the_venue_label_by_compare_and_set(monkeypatch, fast):
    market = _Market("0xaa", "Manacor: A vs B", ["Anna Player", "Bea Player"])
    _venue(monkeypatch, _FakeService([market]))
    session = _Session(page=[_row(1, 10, "0xaa", "Manacor: A vs B")])

    out = await rail.repair(session, apply=True)

    assert out["counts"]["relabelled"] == 1
    assert session.commits == 1
    sql = session.write_sql
    assert "IS NOT DISTINCT FROM v.old_name" in sql, (
        "the write is not a compare-and-set on the name it selected on, so a "
        "concurrent re-ingest would be clobbered"
    )
    assert "RETURNING" in sql.upper(), (
        "without RETURNING the rail cannot tell a row that landed from a row "
        "that raced, and `relabelled` becomes a guess"
    )


@pytest.mark.asyncio
async def test_the_write_names_one_column_and_never_the_touch_stamp(monkeypatch, fast):
    """`futures_outcomes.last_updated` answers "when did the poller last SEE
    this row" and `app/routes/playoffs.py` reads it as liveness (#2024). A
    repair that bumped it would forge a venue observation that never happened.
    """
    market = _Market("0xaa", "Manacor: A vs B", ["Anna Player", "Bea Player"])
    _venue(monkeypatch, _FakeService([market]))
    session = _Session(page=[_row(1, 10, "0xaa", "Manacor: A vs B")])

    await rail.repair(session, apply=True)

    sql = session.write_sql
    set_clause = sql.upper().split(" SET ", 1)[1].split(" FROM ", 1)[0]
    assert "NAME =" in set_clause
    for forbidden in ("LAST_UPDATED", "UPDATED_AT", "PRICE_CHANGED_AT", "CURRENT_PROBABILITY"):
        assert forbidden not in set_clause, (
            f"the write also sets {forbidden}; this rail repairs a LABEL and "
            "nothing else"
        )


@pytest.mark.asyncio
async def test_a_leg_the_venue_does_not_return_is_counted_not_skipped(monkeypatch, fast):
    """Gotcha #53: an empty answer is a response shape, not an absence. The
    count is how an operator sees a drain that is finding nothing."""
    _venue(monkeypatch, _FakeService([]))
    session = _Session(page=[_row(1, 10, "0xaa", "Manacor: A vs B")])

    out = await rail.repair(session, apply=True)

    assert out["counts"]["not_at_venue"] == 1
    assert out["counts"]["legs_examined"] == 1
    assert session.writes == []


@pytest.mark.asyncio
async def test_a_venue_label_that_still_collapses_is_counted_unchanged(monkeypatch, fast):
    """A bare Yes/No names no side either, so `_leg_label` refuses to call it a
    rescue and the leg keeps its title. That is a real outcome with a real
    count, not a silent skip."""
    market = _Market("0xaa", "Manacor: A vs B", ["Yes", "No"])
    _venue(monkeypatch, _FakeService([market]))
    session = _Session(page=[_row(1, 10, "0xaa", "Manacor: A vs B")])

    out = await rail.repair(session, apply=True)

    assert out["counts"]["unchanged"] == 1
    assert out["counts"]["relabelled"] == 0
    assert session.writes == []


@pytest.mark.asyncio
async def test_two_legs_of_one_market_that_would_take_the_same_label_are_refused(
    monkeypatch, fast
):
    """Measured: one market in the cohort carries two collapsed legs, on two
    different condition ids. If both resolve to the same side, writing them
    replaces an unreadable card with one that prints the same side twice."""
    same = "Manacor: A vs B"
    markets = [
        _Market("0xaa", same, ["Anna Player", "Bea Player"]),
        _Market("0xbb", same, ["Anna Player", "Bea Player"]),
    ]
    _venue(monkeypatch, _FakeService(markets))
    session = _Session(page=[_row(1, 10, "0xaa", same), _row(2, 10, "0xbb", same)])

    out = await rail.repair(session, apply=True)

    assert out["counts"]["refused_collision"] == 2
    assert out["counts"]["relabelled"] == 0
    assert session.writes == [], "the colliding pair was written anyway"


@pytest.mark.asyncio
async def test_two_legs_of_DIFFERENT_markets_sharing_a_label_are_both_written(
    monkeypatch, fast
):
    """The control for the guard above. The refusal is scoped to ONE market;
    two different matchups can legitimately share a player name, and a refusal
    that fired on those would stall the drain on its most common case."""
    markets = [
        _Market("0xaa", "Manacor: A vs B", ["Anna Player", "Bea"]),
        _Market("0xbb", "Lujan: A vs C", ["Anna Player", "Cara"]),
    ]
    _venue(monkeypatch, _FakeService(markets))
    session = _Session(
        page=[_row(1, 10, "0xaa", "Manacor: A vs B"), _row(2, 11, "0xbb", "Lujan: A vs C")]
    )

    out = await rail.repair(session, apply=True)

    assert out["counts"]["refused_collision"] == 0
    assert out["counts"]["relabelled"] == 2


@pytest.mark.asyncio
async def test_a_row_the_poller_re_ingested_is_counted_raced_not_relabelled(
    monkeypatch, fast
):
    markets = [
        _Market("0xaa", "Manacor: A vs B", ["Anna Player", "Bea"]),
        _Market("0xbb", "Lujan: A vs C", ["Cara Player", "Dee"]),
    ]
    _venue(monkeypatch, _FakeService(markets))
    session = _Session(
        page=[_row(1, 10, "0xaa", "Manacor: A vs B"), _row(2, 11, "0xbb", "Lujan: A vs C")],
        landed=[1],  # the compare-and-set matched only the first
    )

    out = await rail.repair(session, apply=True)

    assert out["counts"]["relabelled"] == 1
    assert out["counts"]["raced"] == 1


# ---------------------------------------------------------------------------
# 4. Every terminal hands back a cursor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_venue_failure_writes_nothing_and_retries_that_batch(monkeypatch, fast):
    """Gotcha #36: a throttled fetch that read as an empty answer would relabel
    nothing and report the cohort drained."""
    _venue(monkeypatch, _FakeService([], raises=RuntimeError("429 Too Many Requests")))
    session = _Session(page=[_row(1, 10, "0xaa", "Manacor: A vs B")])

    out = await rail.repair(session, apply=True)

    assert out["terminal"] == "paused_venue"
    assert out["counts"]["legs_examined"] == 0
    assert session.writes == []
    assert out["next_cursor"] is None, (
        "the first batch failed, so nothing was examined and the cursor must be "
        "the one handed in — advancing it would skip the legs the venue refused"
    )
    assert out["scan_exhausted"] is False
    assert "429" in (out["reason"] or "")


@pytest.mark.asyncio
async def test_a_venue_failure_mid_page_keeps_the_legs_already_examined(monkeypatch, fast):
    """The cursor must name the last leg EXAMINED, not the last leg planned, or
    a retry re-reads work that is already done — or worse, steps over it."""
    monkeypatch.setattr(rail, "GAMMA_BATCH_SIZE", 1)

    calls = {"n": 0}
    market = _Market("0xaa", "Manacor: A vs B", ["Anna Player", "Bea"])

    class _FlakyService(_FakeService):
        async def get_markets_by_conditions(self, condition_ids, **kwargs):
            calls["n"] += 1
            if calls["n"] > 1:
                raise RuntimeError("503 from the venue")
            return await super().get_markets_by_conditions(condition_ids, **kwargs)

    _venue(monkeypatch, _FlakyService([market]))
    session = _Session(
        page=[_row(1, 10, "0xaa", "Manacor: A vs B"), _row(2, 11, "0xbb", "Lujan: A vs C")]
    )

    out = await rail.repair(session, apply=True)

    assert out["terminal"] == "paused_venue"
    assert out["counts"]["legs_examined"] == 1
    assert out["next_cursor"] == {"after_id": 1}
    assert out["stopped_before"] == 2


@pytest.mark.asyncio
async def test_a_page_select_that_never_finishes_returns_the_incoming_cursor(
    monkeypatch, fast
):
    class _PageDies(_Session):
        async def execute(self, stmt, params=None):
            sql = " ".join(str(stmt).split())
            if "LIMIT :cap::int" in sql:
                raise RuntimeError("canceling statement due to statement timeout")
            return await super().execute(stmt, params)

    session = _PageDies(page=[_row(1, 10, "0xaa", "x")])
    out = await rail.repair(session, apply=True, after_id=77)

    assert out["terminal"] == "paused_target_timeout"
    assert out["next_cursor"] == {"after_id": 77}, (
        "nothing was examined, so the cursor must come back unchanged"
    )
    assert out["counts"]["legs_examined"] == 0
    assert session.rollbacks >= 1


@pytest.mark.asyncio
async def test_a_write_that_does_not_land_retries_the_page_and_counts_no_races(
    monkeypatch, fast
):
    """A write that never ran leaves every leg unwritten for ONE shared reason.
    Counting those as `raced` would tell the operator that N concurrent
    re-ingests had happened, which is a different investigation."""
    market = _Market("0xaa", "Manacor: A vs B", ["Anna Player", "Bea"])
    _venue(monkeypatch, _FakeService([market]))

    class _WriteDies(_Session):
        async def execute(self, stmt, params=None):
            sql = " ".join(str(stmt).split())
            if sql.upper().startswith("UPDATE"):
                raise RuntimeError("canceling statement due to statement timeout")
            return await super().execute(stmt, params)

    session = _WriteDies(page=[_row(1, 10, "0xaa", "Manacor: A vs B")], remaining=5)
    out = await rail.repair(session, apply=True, after_id=42)

    assert out["terminal"] == "paused_write_timeout"
    assert out["counts"]["relabelled"] == 0
    assert out["counts"]["raced"] == 0
    assert out["next_cursor"] == {"after_id": 42}
    assert session.rollbacks >= 1


@pytest.mark.asyncio
async def test_the_cursor_is_exclusive_and_the_next_call_asks_past_it(monkeypatch, fast):
    market = _Market("0xaa", "Manacor: A vs B", ["Anna Player", "Bea"])
    _venue(monkeypatch, _FakeService([market]))
    session = _Session(page=[_row(9, 10, "0xaa", "Manacor: A vs B")])

    out = await rail.repair(session, apply=True)
    assert out["next_cursor"] == {"after_id": 9}

    second = _Session(page=[])
    _venue(monkeypatch, _FakeService([market]))
    await rail.repair(second, apply=True, after_id=out["next_cursor"]["after_id"])

    assert second.page_params["after_id"] == 9
    assert "fo.id > :after_id" in second.page_sql, (
        "the cursor is not exclusive, so the last leg of every page is examined "
        "twice"
    )


@pytest.mark.asyncio
async def test_a_short_page_reports_the_scan_exhausted(monkeypatch, fast):
    market = _Market("0xaa", "Manacor: A vs B", ["Anna Player", "Bea"])
    _venue(monkeypatch, _FakeService([market]))
    session = _Session(page=[_row(1, 10, "0xaa", "Manacor: A vs B")], remaining=0)

    out = await rail.repair(session, apply=True)
    assert out["scan_exhausted"] is True

    full = [
        _row(i, i, f"0x{i:02x}", "Manacor: A vs B") for i in range(1, rail.APPLY_LEG_CAP + 1)
    ]
    _venue(monkeypatch, _FakeService([market]))
    session2 = _Session(page=full)
    out2 = await rail.repair(session2, apply=False)
    assert out2["scan_exhausted"] is False, (
        "a FULL page reported the scan exhausted — the drain would stop with "
        "the tail of its population untouched"
    )


# ---------------------------------------------------------------------------
# 5. The census cannot answer zero when it could not look
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_census_reports_unmeasured_never_zero_when_it_times_out():
    """Gotcha #54. A zero here reads as "drained", which is the one answer this
    census must never invent."""

    class _CensusDies(_Session):
        async def execute(self, stmt, params=None):
            sql = " ".join(str(stmt).split())
            if "GROUP BY" in sql.upper():
                raise RuntimeError("canceling statement due to statement timeout")
            return await super().execute(stmt, params)

    out = await rail.census(_CensusDies())

    assert out["measured"] is False
    assert out["total_legs"] is None, "an unmeasured census reported a number"
    assert out["by_category"] == {}
    assert "timeout" in (out["reason"] or "").lower()


@pytest.mark.asyncio
async def test_the_census_splits_by_category_and_totals_them():
    session = _Session(census_rows=[("table_tennis", 984, 984), ("tennis", 92, 92)])
    out = await rail.census(session)

    assert out["measured"] is True
    assert out["total_legs"] == 1076
    assert out["by_category"]["tennis"] == {"legs": 92, "markets": 92}


@pytest.mark.asyncio
async def test_the_census_never_writes_even_when_told_to_apply():
    session = _Session(census_rows=[("tennis", 1, 1)])
    await rail.census(session, apply=True)
    assert session.writes == []
    assert session.commits == 0


def test_the_census_and_the_pager_share_one_population_predicate():
    """Two spellings of "collapsed leg" is how a drain comes to report progress
    against a population it is not actually walking."""
    src = inspect.getsource(rail)
    assert src.count("fo.name IS NOT DISTINCT FROM fm.name") == 1, (
        "the collapse predicate is written more than once; the census and the "
        "pager can now disagree about their own population"
    )
    assert src.count("{COLLAPSED_LEG_PREDICATE}") == 3, (
        "the shared predicate is no longer interpolated into all three "
        "statements (page, census, remaining count)"
    )


def test_the_predicate_is_the_null_safe_spelling_that_makes_the_query_run():
    """Not a null-safety flourish: with `=` the planner BitmapAnds the name
    index into every per-market probe and the query times out at 10s even
    narrowed to one category. `IS NOT DISTINCT FROM` is non-indexable, so the
    planner probes `ix_futures_outcomes_market_id` alone — measured 10s timeout
    -> 152ms on production."""
    assert "IS NOT DISTINCT FROM" in rail.COLLAPSED_LEG_PREDICATE
    assert "fo.name = fm.name" not in inspect.getsource(rail)


# ---------------------------------------------------------------------------
# 6. Budgets — every one of them derived, none of them a comment
# ---------------------------------------------------------------------------


def test_the_worst_case_still_fits_under_the_router_wall():
    """Positive means an over-running call returns a partial answer WITH its
    cursor. Negative means H12 with no body, and an attended drain silently
    loses its place."""
    assert rail.budget_headroom_seconds() > 0, (
        f"the worst case is {rail.ROUTER_WALL_SECONDS - rail.budget_headroom_seconds():.2f}s "
        f"against a {rail.ROUTER_WALL_SECONDS}s wall"
    )


def test_the_page_select_bound_cannot_exceed_the_loop_deadline():
    """`started` is captured BEFORE the page SELECT, so a slow SELECT does not
    add to the total — it just leaves the loop less room. That argument holds
    only while this inequality does."""
    assert rail.TARGET_SELECT_BUDGET_SECONDS <= rail.DEADLINE_SECONDS


def test_both_post_loop_database_units_fit_inside_the_reserve_they_are_charged_to():
    """The DERIVED client bounds, not the server budgets. Asserting the server
    bound fits and leaving the pool slack unaccounted is exactly how the sibling
    rail's bound came to be described but not enforced (CERT-670)."""
    charged = rail.client_db_budget_seconds(
        rail.WRITE_BUDGET_SECONDS
    ) + rail.client_db_budget_seconds(rail.COMMIT_BUDGET_SECONDS)
    assert charged <= rail.POST_LOOP_NON_COUNT_RESERVE_SECONDS, (
        f"the write and its commit are charged {charged}s against a "
        f"{rail.POST_LOOP_NON_COUNT_RESERVE_SECONDS}s reserve that also has to "
        "cover response serialization and the dependency's own commit"
    )


def test_the_non_count_reserve_fits_inside_the_whole_post_loop_reserve():
    assert (
        rail.POST_LOOP_NON_COUNT_RESERVE_SECONDS < rail.POST_LOOP_RESERVE_SECONDS
    ), "the terminal count has no budget at all"


def test_the_venue_pause_is_real_in_production():
    """The `fast` fixture removes this. Without this guard the whole suite could
    run against a rail that had quietly stopped pacing itself, and Polymarket's
    Gamma limiter is real."""
    assert rail.VENUE_PAUSE >= 0.3


@pytest.mark.asyncio
async def test_a_limit_may_narrow_the_page_but_never_widen_it(monkeypatch, fast):
    """`?limit=` may only narrow. An operator who could widen it would be
    choosing the H12 the whole budget exists to prevent."""
    _venue(monkeypatch, _FakeService([]))
    narrow = _Session(page=[])
    await rail.repair(narrow, apply=False, limit=5)
    assert narrow.page_params["cap"] == 5

    _venue(monkeypatch, _FakeService([]))
    wide = _Session(page=[])
    await rail.repair(wide, apply=False, limit=10_000)
    assert wide.page_params["cap"] == rail.APPLY_LEG_CAP, (
        "an operator widened the cap past the module constant and bought "
        "themselves the H12 the budget exists to prevent"
    )


# ---------------------------------------------------------------------------
# 7. Wiring
# ---------------------------------------------------------------------------


def test_both_halves_are_reachable_as_endpoints():
    """A rail with no address is a rail nobody can run — registered in the same
    commit that builds it."""
    from app.routes.admin_repairs import _REPAIRS

    assert _REPAIRS["polymarket-leg-label-census"] == (
        "app.tasks.repair_polymarket_leg_label",
        "census",
    )
    assert _REPAIRS["polymarket-leg-label"] == (
        "app.tasks.repair_polymarket_leg_label",
        "repair",
    )

    import app.routes.admin_repairs as mod

    assert "polymarket-leg-label" in (mod.__doc__ or ""), (
        "the docstring catalog has drifted from the registry again"
    )


def test_the_dispatcher_can_forward_every_param_this_rail_declares():
    """FastAPI drops an unknown query param SILENTLY, so a rail that declared a
    cursor the dispatcher cannot pass would re-read page one forever while the
    response looked perfectly busy."""
    import app.routes.admin_repairs as mod

    declared = set(inspect.signature(mod.run_repair).parameters)
    mine = set(inspect.signature(rail.repair).parameters) - {"session", "apply"}
    assert mine, "the repair takes no optional params — this guard is vacuous"
    assert mine <= declared, f"the dispatcher cannot forward {sorted(mine - declared)}"


def test_the_drain_is_attended_only_and_is_not_on_the_beat():
    """It is a drain with an end state, not a standing job. A beat entry would
    also put an unattended Gamma read on a rate-limited venue."""
    from app.tasks import celery_app

    schedule = celery_app.conf.beat_schedule or {}
    assert schedule, "the beat schedule is empty — this guard would be vacuous"
    for name, entry in schedule.items():
        assert "repair_polymarket_leg_label" not in str(entry.get("task", "")), (
            f"beat entry {name!r} schedules the attended drain"
        )
