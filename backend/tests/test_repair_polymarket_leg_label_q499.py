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
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks import repair_polymarket_leg_label as rail


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aged(days: float) -> datetime:
    """A resolution date exactly ``days`` old, as an OFFSET from now.

    Never a literal date: an anchor that names 2026-09-21 passes today and fails
    in October, and an anchor that BRANCHES on the clock to avoid that is not
    fixed either (Hot List #44). Offsets have neither problem.
    """
    return _now() - timedelta(days=days)


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, rows=(), scalar=0, one=None):
        self._rows = list(rows)
        self._scalar = scalar
        self._one = one

    def fetchall(self):
        return self._rows

    def scalar_one(self):
        return self._scalar

    def one(self):
        if self._one is None:
            raise AssertionError(
                "the rail called .one() on a statement this fake was not "
                "routing — it would otherwise read as a legitimate refusal"
            )
        return self._one


class _Session:
    """Records every statement the rail issues, routed by statement SHAPE.

    Routed on shape rather than call ORDER so that a rail which reorders its
    queries is still measured correctly, instead of silently reading a page as
    a count.
    """

    def __init__(
        self,
        page=(),
        remaining=0,
        landed=None,
        census_rows=(),
        out_of_scope=(0, 0),
        cursor_resolves=True,
        table_legs=None,
    ):
        self.page = list(page)
        #: #7701 rung 3a: what the TABLE holds, when that differs from what the
        #: page select returned. Defaults to ``None`` = "the same rows", which is
        #: what every guard written before this rung means: their fixture page IS
        #: the population, so each market in it is whole and the completeness
        #: test passes without any of them restating it. A fixture sets this
        #: explicitly to build the case the rung exists for — a market whose legs
        #: the page only has SOME of.
        self.table_legs = list(table_legs) if table_legs is not None else None
        self.remaining = remaining
        #: Whether the #7701 rung 2 dangling-cursor probe finds its row.
        #: DEFAULTS TO TRUE so that every guard written before rung 2 keeps
        #: measuring what it was written to measure: those tests hand in an
        #: `after_id` with an empty page to exercise exhaustion and resumption,
        #: and a fake that answered "no such row" would divert all of them into
        #: the new refusal and quietly stop testing their own subject. The
        #: False arm is a deliberate fixture, used by the dangling-cursor test.
        self.cursor_resolves = cursor_resolves
        #: ``(legs, markets)`` the complement-of-scope count answers, or ``None``
        #: to make that count RAISE — the arm that proves the rail reports
        #: "unmeasured" instead of a reassuring zero.
        self.out_of_scope = out_of_scope
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
            if "LIMIT CAST(:cap AS int)" in sql:
                return sql
        raise AssertionError(
            "the rail never issued its page query — every pager assertion in "
            f"this test would be vacuous. Statements seen: {self.statements!r}"
        )

    @property
    def page_params(self) -> dict:
        for sql, params in self.statements:
            if "LIMIT CAST(:cap AS int)" in sql:
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

    def _table(self) -> list:
        """Every collapsed leg the table holds — the page's rows unless told otherwise."""
        return self.table_legs if self.table_legs is not None else self.page

    def _selected(self, sql: str, params: dict) -> list:
        """The page rows a real Postgres would have returned for THIS statement.

        🔴 THE FAKE APPLIES THE SCOPE AND THE BAND ITSELF. A fake that handed
        back ``self.page`` whatever the WHERE clause said would pass every
        #7701 assertion below against a rail that dropped the clause entirely —
        the band tests would be measuring the fixture, not the rail. So the two
        selectors are re-implemented here from the STATEMENT, not from the call
        arguments: the scope is read from which status predicate the SQL carries
        and the band from the binds the rail actually sent.
        """
        rows = list(self.page)

        # Scope: read off the predicate in the SQL, so a page that silently kept
        # the original cohort while reporting the widened one fails here.
        if "fm.status IS DISTINCT FROM 'open'" in sql:
            rows = [r for r in rows if r[7] != "open"]
        elif "fm.status = 'open'" in sql:
            rows = [r for r in rows if r[7] == "open"]

        # Band: MAX age is the OLDER edge, so it is a LOWER bound on the date.
        # Inverting it here would make the rail's own inversion invisible.
        now = _now()
        lo, hi = params.get("band_min_age"), params.get("band_max_age")
        if lo is not None or hi is not None:
            kept = []
            for r in rows:
                when = r[6]
                if when is None:
                    # NULL compares unknown in SQL: an age band cannot see a row
                    # with no resolution_date, and the rail's docstring says so.
                    continue
                age = (now - when).total_seconds() / 86400.0
                if hi is not None and age > hi:
                    continue
                if lo is not None and age < lo:
                    continue
                kept.append(r)
            rows = kept

        # `after_id` and `cap` are deliberately NOT re-implemented here: the
        # existing guards drive them through fixtures that state the page they
        # expect, and a fake that also paged would change what those tests are
        # measuring. The two selectors above are enforced because the #7701
        # guards below would otherwise be vacuous.
        return rows

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
        # #7701 rung 3a. BOTH routed BEFORE the `GROUP BY` census arm below,
        # which the per-market count would otherwise be swallowed by — it groups
        # too, and being answered with `census_rows` is not a wrong number, it is
        # a wrong SHAPE that takes the whole suite down an IndexError.
        if "LIMIT CAST(:topup_cap AS int)" in sql:
            mid, last = params.get("mid"), params.get("last_leg")
            tail = [r for r in self._table() if r[1] == mid and r[0] > last]
            # 🔴 THE FAKE APPLIES THE TOP-UP'S OWN LIMIT, for the same reason it
            # applies the scope and the band: the rail reads a FULL tail as "this
            # market may be bigger than I can prove" and refuses it, so a fake
            # that handed back every remaining leg regardless of `:topup_cap`
            # would make that arm unreachable and let a rail which dropped the
            # LIMIT — an unbounded page — pass every assertion here.
            return _Result(rows=sorted(tail)[: params.get("topup_cap")])
        if "SELECT leg.market_id, COUNT(*)" in sql:
            mids = set(params.get("mids") or [])
            tally: dict[int, int] = {}
            for r in self._table():
                if r[1] in mids:
                    tally[r[1]] = tally.get(r[1], 0) + 1
            return _Result(rows=sorted(tally.items()))
        # Routed BEFORE the complement count, which it also looks like: the
        # census selects the same two aggregates and is told apart by its
        # GROUP BY and nothing else.
        if "GROUP BY" in upper:
            return _Result(rows=self.census_rows)
        # Routed BEFORE the generic count AND before the page, on the aggregate
        # PAIR rather than on the status predicate: since #7701 the widened
        # page and its terminal count both carry `IS DISTINCT FROM 'open'` too,
        # and routing on that string handed the rail's `scalar_one()` a
        # two-column result whose default scalar is 0 — a silent wrong zero in
        # exactly the tests added to stop silent wrong zeros.
        if "count(DISTINCT fm.id) AS markets" in sql:
            if self.out_of_scope is None:
                raise RuntimeError("out-of-scope count failed")
            return _Result(one=tuple(self.out_of_scope))
        if "LIMIT CAST(:cap AS int)" in sql:
            return _Result(rows=self._selected(sql, dict(params or {})))
        # #7701 rung 2's dangling-cursor probe. Routed EXPLICITLY rather than
        # left to the fallthrough, because the fallthrough answers with no rows
        # — which this rail reads as "the cursor names nothing" — so an unrouted
        # probe would turn every empty-page-with-a-cursor guard in this file
        # into a test of the refusal instead of a test of its own subject.
        if "SELECT 1 FROM futures_outcomes" in sql:
            return _Result(rows=[(1,)] if self.cursor_resolves else [])
        if upper.startswith("SELECT COUNT("):
            return _Result(scalar=self.remaining)
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


def _row(
    outcome_id,
    market_id,
    condition_id,
    name,
    category="tennis",
    resolution_date=None,
    market_status="open",
):
    """One page row, in the tuple order the rail's own SELECT emits.

    ``resolution_date`` defaults to None — the age-UNKNOWN case — on purpose.
    Every pre-#7701 test built rows without one and must keep passing unchanged,
    and a default of "30 days ago" would have made the unknown bucket reachable
    only by a test that asked for it, which is the bucket most likely to be
    mis-folded (see ``AGE_BUCKET_UNKNOWN``).
    """
    return (
        outcome_id,
        market_id,
        condition_id,
        name,
        name,
        category,
        resolution_date,
        market_status,
    )


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
async def test_a_market_the_page_cut_in_half_is_completed_before_the_guard_runs(
    monkeypatch, fast
):
    """#7701 rung 3a. The collision guard groups the PAGE, and `LIMIT` cuts the
    leg stream wherever the cap falls — not on a market boundary. A market whose
    two collapsed legs straddle that cut arrives as two groups of one, each
    trivially distinct, so BOTH were written the same label and
    `refused_collision` stayed 0: not a weakened guard, a bypassed one.

    Here the page select returns only the first leg (cap 1) while the table holds
    both. The trailing market must be completed before the guard runs, so the
    collision is seen and refused — against the unfixed rail this writes leg 1."""
    same = "Manacor: A vs B"
    markets = [
        _Market("0xaa", same, ["Anna Player", "Bea Player"]),
        _Market("0xbb", same, ["Anna Player", "Bea Player"]),
    ]
    _venue(monkeypatch, _FakeService(markets))
    leg1, leg2 = _row(1, 10, "0xaa", same), _row(2, 10, "0xbb", same)
    session = _Session(page=[leg1], table_legs=[leg1, leg2])

    out = await rail.repair(session, apply=True, limit=1)

    assert out["counts"]["refused_collision"] == 2, (
        "the split market was not reassembled, so the guard tested a fragment"
    )
    assert out["counts"]["relabelled"] == 0
    assert session.writes == [], "a page-boundary split wrote the colliding pair"


@pytest.mark.asyncio
async def test_a_market_examined_only_in_part_is_refused_rather_than_written(
    monkeypatch, fast
):
    """#7701 rung 3a, the general case the top-up does NOT cover. A venue pause
    or the deadline breaks the loop mid-market, and a cursor handed in mid-market
    starts the page there; both present the guard with a fragment that is
    trivially distinct. The page here is under the cap, so no top-up fires — the
    completeness test against the table is the only thing standing between a
    half-examined market and the write. Unfixed, this writes leg 1."""
    same = "Manacor: A vs B"
    markets = [_Market("0xaa", same, ["Anna Player", "Bea Player"])]
    _venue(monkeypatch, _FakeService(markets))
    leg1, leg2 = _row(1, 10, "0xaa", same), _row(2, 10, "0xbb", same)
    session = _Session(page=[leg1], table_legs=[leg1, leg2])

    out = await rail.repair(session, apply=True)

    assert out["counts"]["refused_group_incomplete"] == 1
    assert out["counts"]["relabelled"] == 0
    assert session.writes == [], "a market only half examined was written anyway"


@pytest.mark.asyncio
async def test_a_whole_market_is_still_written_when_the_table_holds_no_more_legs(
    monkeypatch, fast
):
    """The control for the two guards above, and the one that keeps them honest:
    the completeness test refuses what it cannot prove, so a bug making it refuse
    EVERYTHING would pass both of them. The table here holds exactly the legs the
    page returned, which is the ordinary case for all 212 pages of the drain."""
    markets = [
        _Market("0xaa", "Manacor: A vs B", ["Anna Player", "Bea"]),
        _Market("0xbb", "Lujan: A vs C", ["Anna Player", "Cara"]),
    ]
    _venue(monkeypatch, _FakeService(markets))
    legs = [
        _row(1, 10, "0xaa", "Manacor: A vs B"),
        _row(2, 11, "0xbb", "Lujan: A vs C"),
    ]
    session = _Session(page=list(legs), table_legs=list(legs))

    out = await rail.repair(session, apply=True)

    assert out["counts"]["refused_group_incomplete"] == 0
    assert out["counts"]["relabelled"] == 2, "the completeness test refuses everything"


@pytest.mark.asyncio
async def test_a_market_too_large_for_the_top_up_is_refused_not_half_written(
    monkeypatch, fast
):
    """The top-up is bounded, so it can come back full without having proven it
    reached the end of the market. That is "we could not tell", and the rung's
    whole claim is that we do not write on it — counted, and named, rather than
    passed through as a group that happened to look distinct."""
    monkeypatch.setattr(rail, "GROUP_COMPLETION_CAP", 1)
    same = "Manacor: A vs B"
    markets = [
        _Market("0xaa", same, ["Anna Player", "Bea Player"]),
        _Market("0xbb", same, ["Anna Player", "Bea Player"]),
        _Market("0xcc", same, ["Anna Player", "Bea Player"]),
    ]
    _venue(monkeypatch, _FakeService(markets))
    legs = [
        _row(1, 10, "0xaa", same),
        _row(2, 10, "0xbb", same),
        _row(3, 10, "0xcc", same),
    ]
    session = _Session(page=[legs[0]], table_legs=list(legs))

    out = await rail.repair(session, apply=True, limit=1)

    assert out["counts"]["refused_group_incomplete"] == 2
    assert session.writes == []


@pytest.mark.asyncio
async def test_a_zero_after_id_is_refused_and_never_reports_an_exhausted_scan(fast):
    """#7701 rung 3a. `?after_id=0` is a cursor to the statement and an absent one
    to Python: `CAST(:after_id AS bigint) IS NULL` is false for 0, so the page
    took the cursor arm, `cursor_market` resolved to NULL and the page came back
    empty — while every Python test was `if after_id`, which 0 is falsy for, so
    the dangling probe was skipped and the empty page fell through to
    `scan_exhausted`. A drain scripted from a cursor initialised to 0 meets this
    on its FIRST call and is told the cohort is finished."""
    session = _Session(page=[])

    out = await rail.repair(session, after_id=0)

    assert out["terminal"] == "refused"
    assert out["refused_code"] == "CURSOR_DANGLING"
    assert out["scan_exhausted"] is False, (
        "a walk that examined nothing reported the cohort drained"
    )
    assert out["counts"]["legs_examined"] == 0
    assert session.statements == [], (
        "the refusal must land before the page select, not after reading"
    )


@pytest.mark.asyncio
async def test_a_real_cursor_still_walks_so_the_zero_refusal_is_not_too_wide(
    monkeypatch, fast
):
    """The control. `after_id` is refused for values below 1 and NOTHING else —
    a refusal keyed on the wrong test would stop all 212 pages of the resume."""
    markets = [_Market("0xaa", "Manacor: A vs B", ["Anna Player", "Bea"])]
    _venue(monkeypatch, _FakeService(markets))
    leg = _row(7, 10, "0xaa", "Manacor: A vs B")
    session = _Session(page=[leg], table_legs=[leg])

    out = await rail.repair(session, apply=True, after_id=1)

    assert out["terminal"] != "refused"
    assert out["counts"]["relabelled"] == 1


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
            if "LIMIT CAST(:cap AS int)" in sql:
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
    # #7701 rung 2 moved the keyset from `fo.id` alone to the composite
    # `(fm.id, fo.id)`, because the page is now driven from the market side.
    # The CONTRACT is unchanged — one `?after_id=` on `futures_outcomes.id`,
    # and the market half is derived from it inside the statement — but the
    # exclusivity now lives in the row-wise comparison, so that is what this
    # guard reads.
    assert "(fm.id, fo.id) > (" in second.page_sql, (
        "the cursor is not exclusive, so the last leg of every page is examined "
        "twice"
    )
    # 🔴 THE TWO COMPARISONS BESIDE EACH OTHER HAVE DIFFERENT STRICTNESS AND
    # BOTH ARE DELIBERATE. The row-wise one must be STRICT or the boundary leg
    # is re-examined; the `fm.id >=` bound must be NON-STRICT or the rest of a
    # split market's legs are stepped over — and because they sit two lines
    # apart, making them agree is the natural-looking edit that breaks one of
    # them. Neither mistake changes a row count in any other test here: a
    # re-examined leg is merely counted `unchanged`, and a stepped-over leg is
    # simply never drained.
    assert "(fm.id, fo.id) >= (" not in second.page_sql, (
        "the row-wise keyset went non-strict: the last leg of every page is "
        "now examined twice"
    )
    assert "fm.id >= (SELECT" in second.page_sql, (
        "the indexable range start is gone. Without it a resume is applied as "
        "a FILTER and re-walks the whole market keyspace: measured on "
        "production 2026-09-23, 302,453 markets and 5.1s at a mid-cohort "
        "cursor, against 11,652 and 738ms with it."
    )
    assert "OFFSET 0" in second.page_sql, (
        "the LATERAL's optimization fence is gone. Postgres pulls a simple "
        "LATERAL subquery up and re-derives the hash join this change exists "
        "to avoid — measured cost 603,538, every page 14s or a timeout. It "
        "reads like a no-op, it changes no row, and no result-checking test "
        "can see it go."
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
    # 🔴 THE RULE IS COUNTED WITHOUT ITS ALIAS, WHICH IS STRICTLY STRONGER THAN
    # COUNTING `fo.name IS NOT DISTINCT FROM fm.name` WAS. Since #7701 rung 2
    # the pager names the outcome table inside a LATERAL and needs the same
    # sentence under the alias `leg`, so the rule is rendered by
    # `collapsed_leg_predicate()` and the old full-literal count would read 0.
    # Matching on the alias-free tail means a hand-written second copy under
    # ANY alias — `leg.name IS NOT DISTINCT FROM fm.name` pasted into the
    # lateral, which is exactly the shortcut this change invites — fails here.
    # The old assertion could not have seen that.
    assert src.count(".name IS NOT DISTINCT FROM fm.name") == 1, (
        "the collapse predicate is written more than once; the census and the "
        "pager can now disagree about their own population"
    )
    assert src.count("{COLLAPSED_LEG_PREDICATE}") == 3, (
        "the shared predicate is no longer interpolated into all three "
        "statements that take it under the default alias (census, remaining "
        "count, out-of-scope count). The out-of-scope count is the one that "
        "MOST needs it: its whole job is to be the same cohort on the other "
        "side of the status test, so a second spelling there would compare two "
        "different populations and report the difference as a finding."
    )
    assert src.count('{collapsed_leg_predicate("leg")}') == 3, (
        "the pager no longer renders the shared rule under its LATERAL alias. "
        "SIX statements must ask one question: three through the constant, and "
        "three through the function that builds it — the page, #7701 rung 3a's "
        "trailing-market top-up, and its per-market completeness count. The last "
        "two are why the number moved from 1: both decide whether a market is "
        "WHOLE, so a second spelling in either would count a different "
        "population than the page walked and silently call a fragment complete "
        "— which is the exact write this rung exists to refuse."
    )
    # The scope test is written once for the same reason, and the two halves
    # must be complements — if they ever overlap or leave a gap, the rail's
    # "in scope 0, out of scope N" sentence stops adding up to the whole defect.
    assert src.count("fm.status = 'open'") == 1
    assert src.count("fm.status IS DISTINCT FROM 'open'") == 1
    # The census still names its own cohort directly; the PAGER and its terminal
    # count now reach a scope through the shared map, which is what lets
    # `status_scope` widen them without minting a third spelling of the status
    # test (#7701).
    assert src.count("{IN_SCOPE_STATUS_SQL}") == 1
    assert src.count("{OUT_OF_SCOPE_STATUS_SQL}") == 1
    assert src.count("{STATUS_SCOPE_SQL[scope]}") == 2, (
        "the pager and its terminal count no longer share one scope "
        "expression; a banded page walking one cohort while its own "
        "'remaining' counts another is the same number meaning two things"
    )
    # 🔴 THE IDENTITY, NOT JUST THE SPELLING. The widened scope is only safe to
    # read as "the other half of the defect" while it IS the complement the
    # counter counts. Written as a value comparison rather than a substring
    # count because a third cohort added here — `resolved`, say, which is
    # narrower than the complement — would leave every text assertion above
    # passing while the rail's "in scope 0, out of scope N" sentence quietly
    # stopped adding up.
    assert rail.STATUS_SCOPE_SQL == {
        "open": rail.IN_SCOPE_STATUS_SQL,
        "not_open": rail.OUT_OF_SCOPE_STATUS_SQL,
    }


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


def test_the_completeness_count_is_bounded_by_the_wall_not_by_a_constant():
    """CERT-3341, and the regression guard it required.

    #7701 rung 3a's per-market completeness count runs AFTER the venue loop, so
    unlike the page select its cost is ADDITIVE to the wall — `started` is
    already spent by the time it begins. Bounded at
    `TARGET_SELECT_BUDGET_SECONDS` the declared worst case was 10.0 deadline +
    6.0 final batch pair + 0.35 pause + 8.0 count + 0.5 pool slack + 8.0
    post-loop reserve = 32.85s against a 30s wall: `budget_headroom_seconds()`
    silently reversed, and an H12 with no body and no cursor — the one failure
    this rail is built not to have.

    Two things are asserted, because either alone is weak. The STRUCTURAL half
    says the bound is still derived; the ARITHMETIC half says the derivation
    still leaves the count enough room to start, which is what breaks if anyone
    raises the deadline, the batch pair or the post-loop reserve.
    """
    src = inspect.getsource(rail)
    assert "server_budget_s=completeness_budget" in src, (
        "the completeness count no longer takes a wall-derived bound"
    )
    assert src.count("server_budget_s=TARGET_SELECT_BUDGET_SECONDS") == 2, (
        "a statement other than the page select and its trailing-market top-up "
        "took the fixed select budget. Both of those run BEFORE the loop, where "
        "the deadline check absorbs them by starting fewer batches; anything "
        "after the loop that takes a constant is additive to the wall."
    )

    worst_spent = (
        rail.DEADLINE_SECONDS + rail.BATCH_PAIR_BUDGET_SECONDS + rail.VENUE_PAUSE
    )
    derived = (
        rail.ROUTER_WALL_SECONDS
        - worst_spent
        - rail.POST_LOOP_RESERVE_SECONDS
        - rail.client_db_budget_seconds(0.0)
    )
    assert derived >= rail.COMPLETENESS_MIN_BUDGET_SECONDS, (
        f"in the worst case the completeness count is left {derived:.2f}s, under "
        f"the {rail.COMPLETENESS_MIN_BUDGET_SECONDS}s it needs to start — so every "
        "such call refuses every group and the drain writes nothing, which is "
        "safe but is not a drain"
    )


def test_the_page_select_bound_cannot_exceed_the_loop_deadline():
    """`started` is captured BEFORE the page SELECT, so a slow SELECT does not
    add to the total — it just leaves the loop less room. That argument holds
    only while this inequality does."""
    assert rail.TARGET_SELECT_BUDGET_SECONDS <= rail.DEADLINE_SECONDS


def test_everything_the_non_count_reserve_names_actually_fits_inside_it():
    """The DERIVED client bounds, not the server budgets, and the FAILURE path,
    not the happy one.

    Asserting the server bound fits and leaving the pool slack unaccounted is
    how the sibling rail's bound came to be described but not enforced
    (CERT-670). Sizing from the happy path and forgetting the cleanup is how its
    round two reached a 31.10s declared worst path against a 30s wall
    (CERT-681). This asserts both, on the four things the reserve names.
    """
    charged = (
        rail.client_db_budget_seconds(rail.WRITE_BUDGET_SECONDS)
        + rail.client_db_budget_seconds(rail.COMMIT_BUDGET_SECONDS)
        + rail.CLEANUP_RESERVE_SECONDS
        + rail.SERIALIZATION_RESERVE_SECONDS
    )
    assert charged <= rail.POST_LOOP_NON_COUNT_RESERVE_SECONDS, (
        f"the write, its commit, one cleanup and the serialization are charged "
        f"{charged}s against a {rail.POST_LOOP_NON_COUNT_RESERVE_SECONDS}s reserve"
    )


def test_the_terminal_count_has_a_budget_left_after_everything_else():
    """The count is degradable, but it must be degradable by CHOICE — a reserve
    that leaves it nothing means it never runs and `remaining_legs` is
    permanently null, which reads as a broken rail rather than a busy one."""
    left = rail.POST_LOOP_RESERVE_SECONDS - rail.POST_LOOP_NON_COUNT_RESERVE_SECONDS
    assert left >= rail.client_db_budget_seconds(rail.REMAINING_COUNT_MIN_BUDGET_SECONDS)


@pytest.mark.asyncio
async def test_a_failed_write_does_not_also_start_the_terminal_count(monkeypatch, fast):
    """🔴 THE CERT-681 GUARD, applied here before a certifier had to find it.

    A failed write has already paid one cleanup. Starting the count anyway puts
    a SECOND cleanup on a reserve that budgets one, and that is precisely the
    arithmetic that took the sibling rail's declared worst path to 31.10s
    against a 30s router wall — the H12-with-no-body that every budget in this
    file exists to prevent, reached through the failure path rather than the
    happy one.
    """
    market = _Market("0xaa", "Manacor: A vs B", ["Anna Player", "Bea"])
    _venue(monkeypatch, _FakeService([market]))

    class _WriteDies(_Session):
        async def execute(self, stmt, params=None):
            sql = " ".join(str(stmt).split())
            if sql.upper().startswith("UPDATE"):
                raise RuntimeError("canceling statement due to statement timeout")
            return await super().execute(stmt, params)

    session = _WriteDies(page=[_row(1, 10, "0xaa", "Manacor: A vs B")], remaining=99)
    out = await rail.repair(session, apply=True)

    assert out["terminal"] == "paused_write_timeout"
    counts = [s for s, _p in session.statements if s.upper().startswith("SELECT COUNT(")]
    assert counts == [], (
        "the terminal count ran after a failed write, so a second cleanup is "
        f"now on the worst path. Count statements issued: {counts!r}"
    )
    assert out["remaining_legs"] is None
    assert out["remaining_legs_measured"] is False, (
        "an unmeasured count reported itself measured — the operator would read "
        "a null as zero remaining"
    )


@pytest.mark.asyncio
async def test_the_count_still_runs_on_the_ordinary_path(monkeypatch, fast):
    """The control for the guard above. Skipping the count ALWAYS would also
    pass it, and would leave every successful call unable to say how much is
    left."""
    market = _Market("0xaa", "Manacor: A vs B", ["Anna Player", "Bea"])
    _venue(monkeypatch, _FakeService([market]))
    session = _Session(page=[_row(1, 10, "0xaa", "Manacor: A vs B")], remaining=1152)

    out = await rail.repair(session, apply=True)

    assert out["terminal"] == "ok"
    assert out["remaining_legs"] == 1152
    assert out["remaining_legs_measured"] is True


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


# ---------------------------------------------------------------------------
# 7167 — the rail could not execute its own page select for 16 days
# ---------------------------------------------------------------------------


async def test_every_statement_this_rail_emits_actually_binds_its_parameters():
    """The guard for 7167's CLASS, and it compiles the REAL statement.

    From 2026-09-05 to 2026-09-21 this rail errored on every invocation:
    `text()` will not read a bind name followed by a colon, so `:cap::int` was
    passed to Postgres as literal SQL with nothing bound to it and the page
    select died on `syntax error at or near ":"`.

    🔴 THE SUITE COULD NOT SEE IT, AND THAT IS THE POINT OF THIS TEST. Every
    pager assertion here runs against a fake session that is handed the SQL as
    a STRING — nothing in the old suite ever asked SQLAlchemy to parse it, so
    the broken spelling was not merely unnoticed, it was load-bearing: four
    pins IDENTIFIED the page query by the substring `LIMIT :cap::int`. A pin
    can hold a broken spelling as correct forever. Compiling cannot.

    🔴 AND IT COMPILES WHAT THE RAIL ACTUALLY ISSUED, NOT A RE-RENDERING OF IT.
    A reconstructed copy of the SQL is a second spelling that drifts, and it
    would specifically miss a bind SMUGGLED INTO A COMMENT — a `:word` inside a
    `--` line is a BIND to `text()`, this rail's SQL now carries a long comment
    explaining the very defect, and a hand-built copy would simply omit it.
    """
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import asyncpg as asyncpg_dialect

    dialect = asyncpg_dialect.dialect()

    # Drive the rail so the fake session records its real statements.
    session = _Session(page=[], out_of_scope=(1, 1))
    await rail.repair(session, apply=False, sport="tennis", after_id=7)
    assert session.statements, "the rail issued nothing — this guard is vacuous"

    expected = {
        # The two band binds are ALWAYS present in the page SQL, bound to None
        # on an unbanded call — the clause is `CAST(:band_max_age AS ...) IS
        # NULL OR ...`, so an unbanded page passes the bind and short-circuits
        # rather than rendering a different statement. That is deliberate: one
        # statement shape means the banded and unbanded forms cannot drift, and
        # it is why this guard covers the band clause without a second call.
        "LIMIT CAST(:cap AS int)": {
            "after_id", "sport", "cap", "band_min_age", "band_max_age",
        },
        "IS DISTINCT FROM 'open'": {"sport"},
    }
    seen = 0
    for marker, want in expected.items():
        for sql, _params in session.statements:
            if marker not in sql:
                continue
            seen += 1
            compiled = text(sql).compile(dialect=dialect)
            bound = set(compiled.params)
            assert bound == want, (
                f"{marker!r}: SQLAlchemy bound {sorted(bound)}, not "
                f"{sorted(want)} — either a parameter spelled `name` followed "
                "by a colon was silently dropped, or a `:word` in a comment was "
                "smuggled in as an extra bind nobody supplies"
            )
            # The compiled text is what Postgres receives. A surviving colon
            # means a parameter marker was never substituted.
            assert ":" not in str(compiled), (
                f"{marker!r}: a literal colon survives compilation — Postgres "
                'will answer `syntax error at or near ":"`. '
                f"Compiled: {compiled!s}"
            )
            break
    assert seen == len(expected), (
        f"only {seen} of {len(expected)} statements were found and compiled; "
        f"statements seen: {[s[:80] for s, _ in session.statements]}"
    )


@pytest.mark.asyncio
async def test_the_update_binds_every_parameter_the_caller_supplies(monkeypatch, fast):
    """🔴 THE ARM CERT-3218 BLOCKED THIS RAIL FOR MISSING, AND WHY IT WAS MISSED.

    The guard above compiles real statements, but it drives `apply=False` over
    an EMPTY page, so `if apply and writable:` never runs and the UPDATE is
    never emitted — it cannot be in the compiled set. The source scan below
    cannot see the UPDATE either: it looks for `:name::type`, and the f-string
    writes the index BETWEEN the name and the cast (`:id{i}::bigint`), so the
    offending token exists only AFTER interpolation. A defect can hide between
    two guards that each look like they cover it.

    What the live spelling actually did, measured: SQLAlchemy bound
    ``{id, new, old}`` — three phantom names matching NONE of the six the
    caller supplies (``id0/old0/new0/id1/old1/new1``) — and the compiled text
    still carried a literal ``:id0::bigint``, so every real apply against a
    writable row failed and relabelled nothing.

    So this arm drives a REAL apply over a NON-EMPTY page and compiles the
    statement the rail issued, never a re-rendering of it.
    """
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import asyncpg as asyncpg_dialect

    market = _Market("0xaa", "Manacor: A vs B", ["Anna Player", "Bea Player"])
    _venue(monkeypatch, _FakeService([market]))
    session = _Session(page=[_row(1, 10, "0xaa", "Manacor: A vs B")])

    await rail.repair(session, apply=True)

    # `write_sql` raises if the rail issued no UPDATE, so this cannot go vacuous
    # the way the empty-page guard above silently did.
    sql, params = session.writes[0]
    assert params, "the rail issued an UPDATE with no parameters at all"

    compiled = text(sql).compile(dialect=asyncpg_dialect.dialect())
    bound = set(compiled.params)
    assert bound == set(params), (
        f"the UPDATE bound {sorted(bound)} but the rail supplies "
        f"{sorted(params)}. A bind written `name` + `::type` is not read by "
        "text(): it reaches Postgres as literal SQL, and the parameters the "
        "caller passes have nowhere to land, so every apply fails."
    )
    assert ":" not in str(compiled), (
        "a literal colon survives compilation of the UPDATE — Postgres will "
        f'answer `syntax error at or near ":"`. Compiled: {compiled!s}'
    )


def test_no_statement_in_this_rail_uses_the_postfix_cast_bind_spelling():
    """The cheap half of the guard above, stated over the real source.

    `CAST(x AS t)` is not a style preference here. Both halves of every pair are
    cast because asyncpg prepares with no parameter types: untyped, the first
    occurrence fixes the parameter as `unknown` and the later comparison can no
    longer resolve it (the sibling rail `repair_kalshi_fabricated_loss` carries
    the same note — and its comment cited THIS file as the exemplar that got it
    right, which it did not).

    🔴 The `{...}` alternative below is not decoration. This guard passed for
    the whole life of #7167 while the rail's UPDATE rendered
    `(:id{i}::bigint, ...)`: an f-string replacement field sits BETWEEN the
    bind name and the cast, so `:name::` never appears in the source and the
    scan read the file as clean. The offending token is built at runtime. The
    compiled-UPDATE arm above is the real guard for that; this one now refuses
    the spelling that produces it, so the two meet instead of leaving a gap.
    """
    import re

    src = inspect.getsource(rail)
    offenders = []
    # `:name::type` directly, or `:name{...}::type` assembled by an f-string.
    pattern = re.compile(r"(?<![:\w]):([a-z_][a-z_0-9]*)(\{[^{}]*\})?::")
    for i, line in enumerate(src.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("--"):
            continue  # the comments that WARN about it must stay legal
        if pattern.search(line):
            offenders.append(f"{i}: {stripped}")
    assert not offenders, (
        "a bind written `name` + `::type` is dropped by text() and reaches "
        f"Postgres as literal SQL: {offenders}"
    )


async def test_an_empty_page_does_not_report_the_defect_drained():
    """🔴 THE REGRESSION THE 7167 FIX WOULD OTHERWISE HAVE INTRODUCED.

    Fixing the binds makes the page select run. Its scope — markets we still
    hold `open` — was measured EMPTY on production 2026-09-21, while 25,469
    collapsed legs sat one status away. So the first thing the repaired rail
    would have done is return `terminal: ok`, `scan_exhausted: true`,
    "no collapsed legs remain in this population": a drain that had never
    executed once, reporting that it had finished. A louder failure replaced by
    a quiet false success is a worse bug than the one being fixed.
    """
    session = _Session(page=[], out_of_scope=(25469, 25402))
    out = await rail.repair(session, apply=False)

    assert out["terminal"] == "ok"
    assert out["scan_exhausted"] is True
    assert out["out_of_scope_measured"] is True
    assert out["out_of_scope_legs"] == 25469
    assert "25469" in out["reason"]
    assert "25402" in out["reason"]
    # The exact sentence that must no longer be sayable on its own.
    assert out["reason"] != "no collapsed legs remain in this population"


async def test_an_empty_page_with_an_empty_complement_may_say_it_is_done():
    """The other side of the guard above — otherwise it only proves the rail
    can be pessimistic, which is not the claim."""
    session = _Session(page=[], out_of_scope=(0, 0))
    out = await rail.repair(session, apply=False)

    assert out["out_of_scope_measured"] is True
    assert out["out_of_scope_legs"] == 0
    assert "in scope or out of it" in out["reason"]


async def test_an_unmeasurable_complement_is_never_reported_as_zero():
    """gotcha #53. A counter that answered 0 on a timeout would reintroduce the
    lie it exists to prevent, one layer down — and it would do it silently,
    because `None` and `0` render the same way in a terminal an operator skims.
    """
    session = _Session(page=[], out_of_scope=None)
    out = await rail.repair(session, apply=False)

    assert out["out_of_scope_measured"] is False
    assert out["out_of_scope_legs"] is None
    assert "NOT a statement that the defect is drained" in out["reason"]


async def test_the_census_reports_the_cohort_its_own_scope_excludes():
    """The census answered `measured: true, total_legs: 0` on production while
    the defect stood at 25,469 legs. The three original fields are unchanged —
    they describe this rail's scope, which is what they always meant — and the
    new ones are what stop that zero being read as "Q499 is finished"."""
    session = _Session(census_rows=[], out_of_scope=(25469, 25402))
    out = await rail.census(session)

    assert out["measured"] is True
    assert out["total_legs"] == 0
    assert out["out_of_scope_measured"] is True
    assert out["out_of_scope_legs"] == 25469
    assert out["out_of_scope_markets"] == 25402


async def test_this_rails_sql_carries_no_dash_comment():
    """A `--` comment inside the SQL is two hazards, both found on this rail.

    Found while writing the 7167 guard: the explanation of the bind fix was
    first written as a `--` block INSIDE the page SQL, and compiling the
    statement the rail actually issued is what exposed it.

    1. SQLAlchemy does not treat a `--` line as a comment. Any colon-prefixed
       word in it becomes a BIND nobody supplies — the exact failure
       `test_no_sql_comment_smuggles_a_bind_parameter` was written for, after a
       comment citing this file's own line numbers compiled them into `$1`/`$2`.
    2. A `--` comment survives only as long as the newline after it does. Any
       layer that collapses the statement to one line — a logger, a recorder, a
       normaliser — turns the rest of the query into comment text.

    Both are avoided completely by explaining the SQL in Python, above it.
    """
    session = _Session(page=[], out_of_scope=(1, 1))
    await rail.repair(session, apply=False, sport="tennis", after_id=7)
    await rail.census(_Session(census_rows=[], out_of_scope=(1, 1)))
    assert session.statements, "no statements issued — this guard is vacuous"

    for sql, _params in session.statements:
        assert "--" not in sql, (
            "this rail's SQL carries a `--` comment; put the explanation in a "
            f"Python comment above the statement instead: {sql[:160]}"
        )


# ---------------------------------------------------------------------------
# 7. #7701 rung 1 — the widened scope is a LOOKING instrument
#
# The ship these guards protect: on 2026-09-21 this rail's writable cohort
# measured 0 while 25,469 collapsed legs — every one of them a card printing
# "US Open WTA: Iga Swiatek vs Nadia Podoroska 89.5%" instead of a side name —
# sat one status value away. The drain could not so much as LOOK at them, so
# Polymarket's retention edge for resolved markets was unmeasurable and the
# widening that fixes those cards had nothing to be sized against.
#
# The three ways this rung can go wrong, in the order they would happen:
#   1. A selector silently not binding, so a "sample" is the whole population
#      wearing a band's label.
#   2. The widened scope learning to WRITE before the bound exists.
#   3. A banded page reporting `scan_exhausted` — one 30-day slice running out,
#      read as the defect being drained. That is the same lie
#      `out_of_scope_legs` was added to stop, one layer further in.
# ---------------------------------------------------------------------------


def _resolved_row(outcome_id, condition_id, name, *, age_days, status="resolved"):
    return _row(
        outcome_id,
        outcome_id * 10,
        condition_id,
        name,
        resolution_date=None if age_days is None else _aged(age_days),
        market_status=status,
    )


def test_the_default_scope_is_the_original_cohort_and_nothing_moved():
    """The widening is additive or it is a regression. An operator who passes
    neither selector must get the rail that was certed."""
    assert rail.parse_status_scope(None) == rail.DEFAULT_STATUS_SCOPE == "open"
    assert rail.parse_band(None) is None
    assert rail.STATUS_SCOPE_SQL["open"] == rail.IN_SCOPE_STATUS_SQL


async def test_an_unknown_scope_is_refused_by_name_and_never_served_from_open():
    """🔴 THE MOST DANGEROUS DEFAULT THIS RAIL COULD HAVE.

    `status_scope=resolved` is the spelling an operator will reach for first —
    the issue itself calls it "the resolved cohort" — and it is not the name of
    the complement. Served quietly from `open`, it returns a truthful empty page
    for a cohort measured at 0 and reads as "the resolved legs are clean", which
    is the strongest possible wrong answer this rail can give.
    """
    session = _Session(page=[_resolved_row(1, "0xa", "A vs B", age_days=10)])
    out = await rail.repair(session, apply=False, status_scope="resolved")

    assert out["terminal"] == "refused"
    assert out["refused_code"] == "STATUS_SCOPE_UNKNOWN"
    assert "not_open" in out["reason"], "the refusal must name the spelling that works"
    assert session.statements == [], (
        "the rail queried the database before validating its selector — a "
        "refusal that still reads is a refusal that can still be misread"
    )
    assert out["counts"]["legs_examined"] == 0


async def test_the_widened_scope_walks_the_complement_and_not_the_open_cohort(
    monkeypatch, fast
):
    """The page must carry the complement predicate, and the rows it examines
    must be the ones the open cohort excludes."""
    page = [
        _resolved_row(1, "0xa", "A vs B", age_days=10),
        _resolved_row(2, "0xb", "C vs D", age_days=10, status="open"),
    ]
    session = _Session(page=page, remaining=1)
    _venue(monkeypatch, _FakeService([_Market("0xa", "A vs B", ["A", "B"])]))

    out = await rail.repair(session, apply=False, status_scope="not_open")

    assert out["status_scope"] == "not_open"
    assert rail.OUT_OF_SCOPE_STATUS_SQL in session.page_sql
    assert rail.IN_SCOPE_STATUS_SQL not in session.page_sql
    # The `open` row is the control: if the scope predicate never bound, the
    # rail would have examined both.
    assert out["counts"]["legs_examined"] == 1
    assert out["by_status"] == {"resolved": 1}


async def test_an_apply_against_the_widened_scope_is_refused_by_name(monkeypatch, fast):
    """Rung 2's guard, planted at rung 1. The widened scope may not learn to
    write until Gamma's retention edge is measured AND this rail stages an undo
    receipt — 25,469 rows is not the population to debut an unreversible write
    on, and a drain that crosses an unmeasured retention edge counts the purged
    tail `not_at_venue` and stops, which is indistinguishable from finishing."""
    page = [_resolved_row(1, "0xa", "A vs B", age_days=10)]
    session = _Session(page=page)
    _venue(monkeypatch, _FakeService([_Market("0xa", "A vs B", ["A", "B"])]))

    out = await rail.repair(session, apply=True, status_scope="not_open")

    assert out["terminal"] == "refused"
    assert out["refused_code"] == "STATUS_SCOPE_APPLY_REFUSED"
    assert out["applied"] is False
    assert session.writes == [], "the rail wrote in the scope it refuses to write in"
    assert session.statements == []


async def test_an_apply_against_the_default_scope_still_writes(monkeypatch, fast):
    """The negative control for the refusal above. A guard that only proves the
    new scope cannot write is satisfied by a rail that cannot write at all."""
    page = [_row(1, 10, "0xa", "A vs B")]
    session = _Session(page=page)
    _venue(monkeypatch, _FakeService([_Market("0xa", "A vs B", ["A", "B"])]))

    out = await rail.repair(session, apply=True)

    assert out["terminal"] != "refused"
    assert out["applied"] is True
    assert session.writes, "the ORIGINAL cohort stopped writing — the refusal is too wide"
    assert out["counts"]["relabelled"] == 1


async def test_the_band_actually_bounds_the_page_it_claims_to_sample(
    monkeypatch, fast
):
    """🔴 THE GUARD THE WHOLE RUNG RESTS ON.

    The deliverable of this rung is a retention CURVE, and a curve read from a
    band that never bound is one number repeated six times with six different
    labels on it. The fake applies the band itself, from the binds the rail
    actually sent, so a rail that dropped the clause fails here rather than
    quietly returning the whole population.
    """
    page = [
        _resolved_row(1, "0xa", "A vs B", age_days=10),
        _resolved_row(2, "0xb", "C vs D", age_days=45),
        _resolved_row(3, "0xc", "E vs F", age_days=200),
    ]
    session = _Session(page=page, remaining=1)
    _venue(
        monkeypatch,
        _FakeService(
            [
                _Market("0xa", "A vs B", ["A", "B"]),
                _Market("0xb", "C vs D", ["C", "D"]),
                _Market("0xc", "E vs F", ["E", "F"]),
            ]
        ),
    )

    out = await rail.repair(session, apply=False, status_scope="not_open", band="30-60")

    assert out["band"] == [30, 60]
    assert out["counts"]["legs_examined"] == 1, (
        "the band did not bind — a 30-60 day slice examined rows aged 10 and 200"
    )
    assert out["by_age_bucket"] == {"30-60": {"relabellable": 1}}
    assert session.page_params["band_min_age"] == 30
    assert session.page_params["band_max_age"] == 60


async def test_the_bands_max_is_the_older_edge_and_the_sql_bounds_it_that_way():
    """Reading the pair as "max age => max date" inverts the window and returns
    the slice NEXT to the one asked for — a page that looks entirely plausible
    and is off by a bucket. Pinned on the SQL, because the fake's own filter
    would otherwise be the only thing asserting the direction."""
    session = _Session(page=[], out_of_scope=(1, 1))
    await rail.repair(session, apply=False, status_scope="not_open", band="30-60")
    sql = " ".join(session.page_sql.split())

    assert "fm.resolution_date >= NOW() - (CAST(:band_max_age AS double precision)" in sql, (
        "the OLDER edge (max age) must be a LOWER bound on the date"
    )
    assert "fm.resolution_date <= NOW() - (CAST(:band_min_age AS double precision)" in sql, (
        "the YOUNGER edge (min age) must be an UPPER bound on the date"
    )


async def test_a_banded_page_never_reports_the_scan_exhausted(monkeypatch, fast):
    """#3257's ruling, and the reason this rung cannot borrow the default
    branch's vocabulary: a slice running out of rows is not a cohort being
    drained. Band exhaustion and population exhaustion are two fields."""
    session = _Session(page=[], out_of_scope=(25469, 25402))

    out = await rail.repair(session, apply=False, status_scope="not_open", band="30-60")

    assert out["scan_exhausted"] is False, (
        "an empty 30-day slice reported the whole cohort scanned"
    )
    assert out["band_exhausted"] is True
    assert "THIS BAND" in out["reason"] or "band" in out["reason"].lower()


async def test_an_unbanded_page_still_reports_the_scan_exhausted(monkeypatch, fast):
    """The negative control for the one above: the two-field split must not have
    been bought by making `scan_exhausted` permanently False."""
    page = [_resolved_row(1, "0xa", "A vs B", age_days=10)]
    session = _Session(page=page, remaining=0)
    _venue(monkeypatch, _FakeService([_Market("0xa", "A vs B", ["A", "B"])]))

    out = await rail.repair(session, apply=False, status_scope="not_open")

    assert out["scan_exhausted"] is True
    assert out["band_exhausted"] is None, (
        "an unbanded page has no band to exhaust; reporting False would read as "
        "a band that still has rows in it"
    )


async def test_an_age_unknown_row_gets_its_own_bucket_and_is_not_aged_into_the_tail(
    monkeypatch, fast
):
    """🔴 THE CLASSIFIER TRAP. `resolution_date` is NULL on a real part of this
    cohort, and folding those into `365+` would manufacture exactly the reading
    this rung exists to take: a pile of old rows the venue cannot answer for.
    "We do not know when this resolved" is a different fact and gets a different
    bucket."""
    page = [
        _resolved_row(1, "0xa", "A vs B", age_days=None),
        _resolved_row(2, "0xb", "C vs D", age_days=400),
    ]
    session = _Session(page=page, remaining=0)
    _venue(monkeypatch, _FakeService([_Market("0xb", "C vs D", ["C", "D"])]))

    out = await rail.repair(session, apply=False, status_scope="not_open")

    assert out["by_age_bucket"] == {
        rail.AGE_BUCKET_UNKNOWN: {"not_at_venue": 1},
        "365+": {"relabellable": 1},
    }


async def test_a_band_cannot_see_an_age_unknown_row_and_the_rail_says_so(
    monkeypatch, fast
):
    """The other half of the trap: every comparison against NULL is unknown, so
    an age band silently excludes the age-unknown tail. That is correct SQL and
    a reader who sampled six bands would conclude they had covered the cohort.
    The unbanded page is the only thing that counts those rows."""
    page = [_resolved_row(1, "0xa", "A vs B", age_days=None)]
    session = _Session(page=page, out_of_scope=(1, 1))

    out = await rail.repair(session, apply=False, status_scope="not_open", band="0-3650")

    assert out["counts"]["legs_examined"] == 0
    assert "NULL" in out["reason"], (
        "a band that cannot see the age-unknown tail must say so in the answer "
        "an operator actually reads"
    )
    assert "resolution_date" in rail.repair.__doc__ or "resolution_date" in rail.__doc__


async def test_a_banded_resume_is_refused_rather_than_silently_re_anchored():
    """CERT-1935 on the sibling rail: a band's ages re-measured from today while
    the keyset stays put strand every row sharing the cursor's own timestamp —
    after the cursor AND outside the new window — and report it as the band
    being exhausted. That rail closed it with a `band_as_of` anchor. This rung
    does not need a banded WALK, so it refuses the case instead of implementing
    it subtly wrong."""
    session = _Session(page=[], out_of_scope=(1, 1))

    out = await rail.repair(
        session, apply=False, status_scope="not_open", band="30-60", after_id=99
    )

    assert out["terminal"] == "refused"
    assert out["refused_code"] == "BAND_RESUME_UNSUPPORTED"
    assert out["next_cursor"] == {"after_id": 99}, (
        "a refusal must hand back the cursor it was given, unchanged — a "
        "refusal that advances the cursor loses the page it declined to walk"
    )
    assert session.statements == []


async def test_a_banded_apply_is_refused():
    """A banded apply drains one age slice and then reports that slice running
    out, which an operator reads as the population being drained."""
    out = await rail.repair(_Session(page=[]), apply=True, band="30-60")
    assert out["refused_code"] == "BAND_ON_APPLY_REFUSED"
    assert out["applied"] is False


@pytest.mark.parametrize(
    "band",
    ["60-30", "30", "", "thirty-sixty", "30-30", "-30", "30-60-90"],
)
async def test_a_band_this_rail_cannot_read_is_refused_never_dropped(band):
    """🔴 NEVER `None` FOR A VALUE THAT WAS SUPPLIED. A band silently dropped
    walks the whole population while the response echoes the band the operator
    asked for — a 120-row sample of 25,469 rows, labelled "30-60 days", used to
    size a write."""
    out = await rail.repair(_Session(page=[]), apply=False, band=band)
    assert out["terminal"] == "refused", f"?band={band!r} was not refused"
    assert out["refused_code"].startswith("BAND_")


def test_the_band_parser_is_not_the_kalshi_one_and_has_no_retention_floor():
    """🔴 THE SHARED-HELPER TRAP, DECLINED ON PURPOSE.

    `repair_kalshi_fabricated_loss.parse_band` is the same grammar and the
    wrong rule here: it refuses any band reaching past `PROVABLY_PURGED_AGE_DAYS`
    because Kalshi's retention floor is a MEASURED constant. Polymarket has no
    such constant — finding where its edge is, is the entire point of banding
    here — so importing that parser would have refused exactly the slices worth
    reading, and the failure would have looked like an empty tail.
    """
    assert rail.parse_band("300-3650") == (300, 3650)
    # Read from the IMPORT NODES, not from the source text: the docstring on
    # `parse_band` explains at length why the Kalshi parser is not imported, and
    # a substring guard would read that explanation as the thing it forbids.
    tree = ast.parse(inspect.getsource(rail))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not any("repair_kalshi_fabricated_loss" in m for m in imported), (
        "this rail imported the Kalshi band parser; its retention floor is a "
        "measurement over a different venue and would refuse this cohort's "
        "oldest slices by name"
    )


def test_the_age_buckets_are_contiguous_and_the_labels_do_not_wrap():
    """A running lower bound rather than `EDGES.index(edge) - 1`, which wraps to
    the LAST edge on the first bucket and labels 0-30 as "365-30"."""
    now = _now()
    assert rail.age_bucket(_aged(1), now) == "0-30"
    assert rail.age_bucket(_aged(45), now) == "30-60"
    assert rail.age_bucket(_aged(75), now) == "60-90"
    assert rail.age_bucket(_aged(120), now) == "90-180"
    assert rail.age_bucket(_aged(300), now) == "180-365"
    assert rail.age_bucket(_aged(400), now) == "365+"
    assert rail.age_bucket(None, now) == rail.AGE_BUCKET_UNKNOWN
    # A close date in the FUTURE on a market we no longer hold open: its own
    # bucket, because folding it into `0-30` reports a row that has not reached
    # its own close as a fresh resolution.
    assert rail.age_bucket(_aged(-5), now) == "future_date"


def test_the_bucket_clock_is_an_argument_and_never_read_inside_the_fold():
    """Hot List #44. A bucket boundary re-read per row sorts two rows of one
    resolution into two slices while the loop is still running, and a guard
    built on a live clock changes its own answer as it runs."""
    assert "now" in inspect.signature(rail.age_bucket).parameters
    # Walked as CALLS, not as text: this function's own docstring is about
    # reading the clock, so a substring guard fails on the explanation rather
    # than on the behaviour.
    fn = ast.parse(inspect.getsource(rail.age_bucket)).body[0]
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
    }
    assert not called & {"now", "utcnow", "today", "time", "monotonic"}, (
        f"age_bucket reads the clock instead of being handed one: {sorted(called)}"
    )


async def test_only_examined_rows_are_folded_into_the_retention_reading(
    monkeypatch, fast
):
    """🔴 A ROW THE LOOP NEVER REACHED IS NOT A VENUE ANSWER. When the venue
    refuses a batch nothing in it was examined, and folding those rows into a
    bucket would put `not_at_venue`-shaped absences into the very table whose
    only value is that its absences ARE venue answers."""
    page = [_resolved_row(i, f"0x{i}", f"A{i} vs B{i}", age_days=45) for i in range(1, 4)]
    session = _Session(page=page, out_of_scope=(1, 1))
    _venue(monkeypatch, _FakeService([], raises=RuntimeError("429 from Gamma")))

    out = await rail.repair(session, apply=False, status_scope="not_open")

    assert out["counts"]["legs_examined"] == 0
    assert out["by_age_bucket"] == {}, (
        "rows the venue never answered for were folded into an age bucket; the "
        "reading would show a retention cliff that is really a rate limit"
    )
    assert out["terminal"] == "paused_venue"


# ---------------------------------------------------------------------------
# #7701 rung 2 — the selector that made the widened scope servable at all.
#
# Rung 1 left rung 2 owing "an index (or a selector that is not a double seq
# scan)". This is the second branch: the join is DRIVEN from the market side.
# Measured on production 2026-09-23, widened scope, 120-leg page —
#
#     driven by            head page   deep resume   terminal page
#     planner (was)        14.0s / timeout on every page, cost 603,538
#     futures_outcomes     626ms       —             20.5s  (cannot say "done")
#     futures_markets      102ms       738ms         2.57s
#
# Every guard below pins a token whose removal is invisible to a result-checking
# test: the plan changes, the answer does not. That is the whole hazard class.
# ---------------------------------------------------------------------------


def test_the_page_is_driven_from_the_market_side():
    """🔴 THE JOIN ORDER IS THE FIX, AND IT READS LIKE A REFACTOR.

    The predicate, the scope test, the band and the columns are all unchanged;
    the only thing rung 2 altered is which table the walk is driven from. A
    later edit that "simplifies" the LATERAL back into a plain JOIN returns the
    identical rows and restores the 603,538 hash join, so nothing that checks an
    answer can catch it.
    """
    src = inspect.getsource(rail)
    page = src.split("page_sql = f")[1]

    assert "JOIN LATERAL" in page, (
        "the page is no longer driven from the market side. A plain JOIN lets "
        "the planner hash 4.34M outcomes against 463K markets: measured cost "
        "603,538, every page 14s or a timeout."
    )
    assert "FROM futures_markets fm" in page and page.index(
        "FROM futures_markets fm"
    ) < page.index("futures_outcomes"), (
        "futures_markets is no longer the driving relation — the outcome table "
        "is named first, which is the 4.34M-row side"
    )
    assert "ORDER BY fm.id, fo.id" in page, (
        "the page no longer orders by the composite key, so a market whose "
        "legs straddle a page boundary cannot be resumed inside itself"
    )


def test_the_offset_0_fence_is_load_bearing():
    """🔴 THE ONE TOKEN IN THIS RAIL THAT LOOKS LIKE A TYPO AND IS NOT.

    `OFFSET 0` blocks Postgres from pulling the LATERAL subquery up into the
    outer join. Measured: without it the planner re-derives a plan
    byte-identical to the pre-rung-2 hash join. It changes no row, returns no
    different answer, and has no effect any other test in this file can
    observe — so it gets a test of its own, or the next reader deletes it as
    dead syntax.
    """
    src = inspect.getsource(rail)
    page = src.split("page_sql = f")[1].split('"""')[1]
    assert "OFFSET 0" in page, (
        "the LATERAL's optimization fence is gone; the pull-up restores the "
        "603,538 hash join and the widened drain stops working"
    )
    # Inside the subquery, not trailing the outer statement — an `OFFSET 0` on
    # the outer SELECT is a genuine no-op and would satisfy a bare substring
    # check while fencing nothing.
    assert page.index("OFFSET 0") < page.index(") fo ON TRUE"), (
        "OFFSET 0 has moved outside the LATERAL subquery, where it fences "
        "nothing at all"
    )


def test_the_resume_keeps_both_of_its_comparisons_and_their_strictness():
    """🔴 TWO COMPARISONS, TWO LINES APART, DELIBERATELY DIFFERENT.

    `fm.id >=` is the indexable range start and MUST be non-strict, or the rest
    of a split market's legs are stepped over. `(fm.id, fo.id) >` is the
    exclusivity and MUST be strict, or the boundary leg is examined twice.
    Making them agree is the natural-looking edit, and neither mistake shows up
    as a failure anywhere else: a re-examined leg is counted `unchanged`, and a
    stepped-over leg is simply never drained.
    """
    src = inspect.getsource(rail)
    page = src.split("page_sql = f")[1].split('"""')[1]
    assert "fm.id >= {cursor_market}" in page
    assert "(fm.id, fo.id) > ({cursor_market}," in page
    assert "(fm.id, fo.id) >= (" not in page


@pytest.mark.asyncio
async def test_a_dangling_cursor_is_refused_not_reported_as_exhausted(
    monkeypatch, fast
):
    """🔴 THE FAILURE THIS RAIL CAN AFFORD LEAST: A FALSE "DONE".

    Rung 2 derives the market half of the keyset from `?after_id=` inside the
    statement. If that leg row has gone the scalar subquery is NULL, every
    comparison against it is NULL, and the page is empty — indistinguishable
    from a drained cohort. At the end of a 212-page walk that empty page is the
    answer everybody is waiting for, so it must be refused BY NAME.
    """
    _venue(monkeypatch, _FakeService([]))
    session = _Session(page=[], out_of_scope=(1, 1), cursor_resolves=False)

    out = await rail.repair(session, apply=False, after_id=999)

    assert out["terminal"] == "refused"
    assert out["refused_code"] == "CURSOR_DANGLING"
    assert out["scan_exhausted"] is False, (
        "a dangling cursor was reported as an exhausted scan — the drain would "
        "bank a finish it never earned"
    )
    assert out["next_cursor"] == {"after_id": 999}, (
        "the operator's cursor must come back untouched so a retry repeats the "
        "page rather than stepping over it"
    )


@pytest.mark.asyncio
async def test_an_empty_page_on_a_cursor_that_RESOLVES_is_still_exhaustion(
    monkeypatch, fast
):
    """The control for the test above, and the reason it is not vacuous.

    Without this arm the refusal could be firing on every empty page with a
    cursor — which would take the rail's ONLY way of saying "finished" away
    while the dangling test still passed.
    """
    _venue(monkeypatch, _FakeService([]))
    session = _Session(page=[], out_of_scope=(1, 1), cursor_resolves=True)

    out = await rail.repair(session, apply=False, after_id=999)

    assert out["terminal"] == "ok"
    assert out.get("refused_code") is None
    assert out["scan_exhausted"] is True


@pytest.mark.asyncio
async def test_the_dangling_probe_does_not_run_on_a_page_that_found_rows(
    monkeypatch, fast
):
    """The probe is bounded by WHEN it runs, not only by its own timeout.

    It is a primary-key lookup, but it is inside the same budget the venue
    round-trips come out of. Running it on every page would put one extra
    statement on all 212 of them to answer a question only the last page asks.
    """
    market = _Market("0xaa", "Manacor: A vs B", ["Anna Player", "Bea"])
    _venue(monkeypatch, _FakeService([market]))
    session = _Session(page=[_row(9, 10, "0xaa", "Manacor: A vs B")])

    await rail.repair(session, apply=False, after_id=3)

    probes = [s for s, _ in session.statements if "SELECT 1 FROM futures_outcomes" in s]
    assert probes == [], (
        "the dangling-cursor probe ran on a page that returned rows; it is only "
        "ever needed to disambiguate an EMPTY page"
    )
