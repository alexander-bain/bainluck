"""#6739 guards — the settled drain for game pages that never name the winner.

PILLAR: TRUTH. SHIP: a settled Polymarket game page says who won, for the 183
markets the writer fix (`301a2174a`) could never reach.

The four things these guards exist to stop, in the order they would actually
happen:

1. **The rail copying its SIBLING's labeller.** `repair_polymarket_leg_label`
   calls `_leg_label`, and this rail sits beside it doing a visibly similar job
   — so reaching for the same helper is the natural move and it is wrong.
   `_leg_label` falls back to `_extract_outcome_name`, which renames a genuine
   binary question to a fragment of itself. The writer commit chose
   `_sub_market_side_label` deliberately and pinned that choice in
   `test_leg_label_would_have_renamed_a_genuine_binary_question`; an AST guard
   here fails the build if this rail drifts to the sibling's helper.
2. **Taking index 0 on a row where index 0 is not this leg's side.** A venue
   market with a `group_item_title` is the DECOMPOSED writer's shape, where the
   stored leg can be index 1. Index 0 there names the LOSER, on a settled page,
   with total confidence — the one failure mode that is worse than the defect.
3. **The venue read covering approximately none of its population.**
   `/markets?condition_ids=…` applies a `closed=false` filter nobody asked for,
   and every row in THIS cohort is settled. Without `include_closed=True` the
   drain reads an empty venue and reports itself finished.
4. **A window silently read as a whole.** Both halves are scoped to a 30-day
   event window for plan reasons, so `scan_exhausted` means "none left inside
   the window" and every response must carry the window back.
"""

import ast
import inspect

import pytest

from app.tasks import repair_polymarket_single_leg_label as rail


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
        if "LIMIT CAST(:cap AS int)" in sql:
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
    """The shape ``_sub_market_side_label`` actually reads.

    Deliberately not a Mock: a Mock answers every attribute, so a rail reading
    the WRONG field would pass.
    """

    def __init__(self, condition_id, question, outcomes, group_item_title=None):
        self.condition_id = condition_id
        self.question = question
        self.outcomes = list(outcomes)
        self.group_item_title = group_item_title


def _row(outcome_id, market_id, condition_id, market_name, category="hockey"):
    """One page row, in the tuple order the rail's own SELECT emits.

    The stored leg name is always the literal "Yes" — that IS the population.
    """
    return (outcome_id, market_id, condition_id, "Yes", market_name, category)


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

    Patching `_fetch_batch` would make the `include_closed` guard untestable,
    because the kwarg it asserts on is passed inside the function it would have
    replaced.
    """
    import app.services.polymarket_api as svc

    monkeypatch.setattr(svc, "PolymarketAPIService", lambda: service)
    return service


@pytest.fixture
def fast(monkeypatch):
    """Remove the deliberate venue pause so the suite is not paced by it.

    Defined locally rather than imported from a sibling test module: importing a
    fixture shadows it at every use site. `test_the_venue_pause_is_real` keeps
    the real value honest, so this fixture cannot hide its removal.
    """
    monkeypatch.setattr(rail, "VENUE_PAUSE", 0)


# ---------------------------------------------------------------------------
# 1. The label rule — and specifically, NOT the sibling's
# ---------------------------------------------------------------------------


def test_the_drain_calls_the_shipped_side_labeller_and_does_not_restate_it():
    """A second labeller is a second classifier free to drift from the writer,
    and the drift would be invisible because both answers look plausible.

    This asserts the call EXISTS, because a guard that only banned the wrong
    helper would pass on a file that had deleted the labelling entirely.
    """
    tree = ast.parse(inspect.getsource(rail))
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_sub_market_side_label" in called, (
        "the rail no longer calls the shipped `_sub_market_side_label`; whatever "
        "it labels with now is a second classifier"
    )


def test_the_drain_does_not_reach_for_its_siblings_labeller():
    """🔴 THE MOST LIKELY WRONG EDIT ANYONE WILL EVER MAKE TO THIS FILE.

    `repair_polymarket_leg_label` sits beside this rail doing a visibly similar
    job and calls `_leg_label`. The handoff note that queued this work said the
    sibling was the template and "only the population filter changes" — which is
    wrong in exactly the way this guard catches.

    `_leg_label` falls back to `_extract_outcome_name`, which renames a genuine
    binary question to a fragment of its own question. The writer commit pinned
    that in `test_leg_label_would_have_renamed_a_genuine_binary_question`; this
    stops the drain quietly re-acquiring it.
    """
    src = inspect.getsource(rail)
    tree = ast.parse(src)

    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "_leg_label" not in imported, (
        "the drain imports `_leg_label` — the sibling rail's labeller, which "
        "renames genuine binary questions to a fragment of their own question"
    )

    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_leg_label" not in called, (
        "the drain calls `_leg_label`; it must call `_sub_market_side_label`"
    )


def test_the_drain_has_no_matchup_splitting_rule_of_its_own():
    """Bans the shortcut in EXECUTABLE code only.

    Docstring prose legitimately discusses matchups at length — naming the trap
    is how the next reader avoids re-introducing it, and a guard that banned the
    words would delete its own explanation. Split with the AST rather than a
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
    assert len(literals) > 20, (
        f"only {len(literals)} executable string literals found — the AST split "
        "has stopped seeing its subject"
    )

    banned = [lit for lit in literals if " vs " in lit.lower() or " vs. " in lit.lower()]
    assert not banned, (
        f"executable code contains a matchup separator {banned!r} — this rail is "
        "one line from deriving a side by splitting the market name, which "
        "cannot tell which of X and Y the price belongs to"
    )

    called_attrs = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not ({"split", "partition", "rsplit"} & called_attrs), (
        "the rail is splitting strings; the only label it may store is the "
        "venue's own, via `_sub_market_side_label`"
    )


# ---------------------------------------------------------------------------
# 2. Orientation — index 0 must provably be this leg's side
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_grouped_venue_market_is_refused_and_never_written(monkeypatch, fast):
    """🔴 THE GUARD AGAINST A CONFIDENT WRONG WINNER.

    `group_item_title` is the decomposed sub-market writer's shape. There the
    stored leg can be `outcome_prices[1]`, so `outcomes[0]` names the OTHER
    side — on a settled page that is the loser's name presented as the result.

    Measured 0 of 183 in the cohort this rail was built for. Refused anyway,
    because "it did not happen in the sample" is not a guarantee, and counted
    rather than skipped so an operator can see it happened at all.
    """
    grouped = _Market(
        "0xaa",
        "Jukurit Mikkeli",
        ["Jukurit Mikkeli", "Vaasan Sport"],
        group_item_title="Jukurit Mikkeli",
    )
    _venue(monkeypatch, _FakeService([grouped]))
    session = _Session(page=[_row(1, 10, "0xaa", "Jukurit Mikkeli vs. Vaasan Sport")])

    out = await rail.repair(session, apply=True)

    assert out["counts"]["refused_grouped"] == 1
    assert out["counts"]["relabelled"] == 0
    assert out["planned"] == 0
    assert not session.writes, (
        "a grouped venue market reached the UPDATE — index 0 is not provably "
        "this leg's side there"
    )


@pytest.mark.asyncio
async def test_an_ungrouped_market_on_the_same_path_is_written(monkeypatch, fast):
    """The other direction, so the refusal above is a DISCRIMINATOR and not a
    rail that refuses everything."""
    plain = _Market("0xbb", "KooKoo vs. SaiPa", ["KooKoo", "SaiPa"])
    _venue(monkeypatch, _FakeService([plain]))
    session = _Session(page=[_row(2, 20, "0xbb", "KooKoo vs. SaiPa")])

    out = await rail.repair(session, apply=True)

    assert out["counts"]["refused_grouped"] == 0
    assert out["counts"]["relabelled"] == 1
    assert session.writes, "the ungrouped row was not written"


# ---------------------------------------------------------------------------
# 3. The venue read — the closed=false trap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_drain_asks_the_venue_for_closed_markets_too(monkeypatch, fast):
    """The single most load-bearing kwarg in this rail.

    Every row in this cohort is settled, and `/markets?condition_ids=` silently
    applies `closed=false`. Without `include_closed=True` the drain reads an
    empty venue, counts its whole population `not_at_venue`, and reports itself
    finished having changed nothing.
    """
    market = _Market("0xaa", "KooKoo vs. SaiPa", ["KooKoo", "SaiPa"])
    service = _venue(monkeypatch, _FakeService([market]))
    session = _Session(page=[_row(1, 10, "0xaa", "KooKoo vs. SaiPa")])

    await rail.repair(session, apply=False)

    assert service.calls, "the rail never asked the venue anything"
    assert service.calls[0].get("include_closed") is True, (
        "the drain asked the venue with the DEFAULT read, which silently filters "
        f"closed=false. Call was: {service.calls[0]!r}"
    )


# ---------------------------------------------------------------------------
# 4. Dry run / apply / the write itself
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_dry_run_plans_the_rename_and_writes_nothing(monkeypatch, fast):
    market = _Market("0xaa", "KooKoo vs. SaiPa", ["KooKoo", "SaiPa"])
    _venue(monkeypatch, _FakeService([market]))
    session = _Session(page=[_row(1, 10, "0xaa", "KooKoo vs. SaiPa")])

    out = await rail.repair(session, apply=False)

    assert out["applied"] is False
    assert out["planned"] == 1
    assert out["counts"]["relabelled"] == 0
    assert out["samples"][0]["from"] == "Yes"
    assert out["samples"][0]["to"] == "KooKoo"
    assert not session.writes, "a dry run issued an UPDATE"


@pytest.mark.asyncio
async def test_an_apply_stores_the_venue_label_by_compare_and_set(monkeypatch, fast):
    market = _Market("0xaa", "KooKoo vs. SaiPa", ["KooKoo", "SaiPa"])
    _venue(monkeypatch, _FakeService([market]))
    session = _Session(page=[_row(1, 10, "0xaa", "KooKoo vs. SaiPa")])

    out = await rail.repair(session, apply=True)

    assert out["counts"]["relabelled"] == 1
    assert "IS NOT DISTINCT FROM v.old_name" in session.write_sql, (
        "the write is not a compare-and-set; a concurrent re-ingest would be "
        "clobbered rather than counted `raced`"
    )
    assert session.commits >= 1


@pytest.mark.asyncio
async def test_the_write_names_one_column_and_never_the_touch_stamp(monkeypatch, fast):
    """`last_updated` is a poller touch-stamp another surface reads as liveness
    (#2024). A repair that bumped it would forge a venue observation that never
    happened."""
    market = _Market("0xaa", "KooKoo vs. SaiPa", ["KooKoo", "SaiPa"])
    _venue(monkeypatch, _FakeService([market]))
    session = _Session(page=[_row(1, 10, "0xaa", "KooKoo vs. SaiPa")])

    await rail.repair(session, apply=True)

    sql = session.write_sql.lower()
    assert "set name = v.new_name" in sql
    assert "last_updated" not in sql, "the repair forged the poller's touch-stamp"
    assert "is_winner" not in sql, "the repair touched a settlement field"


@pytest.mark.asyncio
async def test_a_row_the_poller_re_ingested_is_counted_raced_not_relabelled(
    monkeypatch, fast
):
    market = _Market("0xaa", "KooKoo vs. SaiPa", ["KooKoo", "SaiPa"])
    _venue(monkeypatch, _FakeService([market]))
    # The compare-and-set returns nothing: the row's name changed underneath us.
    session = _Session(page=[_row(1, 10, "0xaa", "KooKoo vs. SaiPa")], landed=set())

    out = await rail.repair(session, apply=True)

    assert out["counts"]["raced"] == 1
    assert out["counts"]["relabelled"] == 0


# ---------------------------------------------------------------------------
# 5. Every leg reaches a NAMED verdict (ruling 054, gotcha #53)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_leg_the_venue_does_not_return_is_counted_not_skipped(
    monkeypatch, fast
):
    _venue(monkeypatch, _FakeService([]))
    session = _Session(page=[_row(1, 10, "0xaa", "KooKoo vs. SaiPa")])

    out = await rail.repair(session, apply=True)

    assert out["counts"]["not_at_venue"] == 1
    assert out["counts"]["legs_examined"] == 1
    assert not session.writes


@pytest.mark.asyncio
async def test_a_genuine_yes_no_question_is_counted_unchanged_and_kept(
    monkeypatch, fast
):
    """The rescue may FAIL to improve a row; it may never guess one.

    A venue payload whose own outcomes are ["Yes","No"] names no side either, so
    the helper returns the fallback and the leg keeps "Yes". Counted, not
    silent: a drain that "found nothing to do" must say how many times.
    """
    binary = _Market("0xaa", "Will the Fed cut rates in October?", ["Yes", "No"])
    _venue(monkeypatch, _FakeService([binary]))
    session = _Session(page=[_row(1, 10, "0xaa", "Fed October")])

    out = await rail.repair(session, apply=True)

    assert out["counts"]["unchanged"] == 1
    assert out["counts"]["relabelled"] == 0
    assert not session.writes


@pytest.mark.asyncio
async def test_a_leg_with_no_condition_id_is_counted_not_skipped(monkeypatch, fast):
    _venue(monkeypatch, _FakeService([]))
    session = _Session(page=[_row(1, 10, "", "KooKoo vs. SaiPa")])

    out = await rail.repair(session, apply=True)

    assert out["counts"]["no_condition_id"] == 1
    assert out["counts"]["legs_examined"] == 1


def test_every_named_verdict_is_initialised_in_the_counts():
    """A verdict that only appears when it fires reads as absent rather than
    zero on every other run."""
    assert set(rail.LEG_VERDICTS) >= {
        "relabelled",
        "unchanged",
        "not_at_venue",
        "no_condition_id",
        "refused_grouped",
        "refused_collision",
        "raced",
    }


# ---------------------------------------------------------------------------
# 6. Pausing, cursors, and the window
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_venue_failure_writes_nothing_and_retries_that_batch(
    monkeypatch, fast
):
    """A throttled fetch treated as an empty answer would relabel nothing and
    report the cohort drained (gotcha #36)."""
    _venue(monkeypatch, _FakeService([], raises=RuntimeError("429 Too Many Requests")))
    session = _Session(page=[_row(7, 10, "0xaa", "KooKoo vs. SaiPa")])

    out = await rail.repair(session, apply=True)

    assert out["terminal"] == "paused_venue"
    assert out["scan_exhausted"] is False
    assert out["counts"]["relabelled"] == 0
    assert not session.writes
    assert out["stopped_before"] == 7


@pytest.mark.asyncio
async def test_the_cursor_is_exclusive_and_the_next_call_asks_past_it(
    monkeypatch, fast
):
    market = _Market("0xaa", "KooKoo vs. SaiPa", ["KooKoo", "SaiPa"])
    _venue(monkeypatch, _FakeService([market]))
    session = _Session(page=[_row(41, 10, "0xaa", "KooKoo vs. SaiPa")])

    out = await rail.repair(session, apply=True)

    assert out["next_cursor"] == {"after_id": 41}
    assert "min(fo.id) > CAST(:after_id AS bigint)" in " ".join(session.page_sql.split())


@pytest.mark.asyncio
async def test_a_short_page_reports_the_scan_exhausted(monkeypatch, fast):
    market = _Market("0xaa", "KooKoo vs. SaiPa", ["KooKoo", "SaiPa"])
    _venue(monkeypatch, _FakeService([market]))
    session = _Session(page=[_row(1, 10, "0xaa", "KooKoo vs. SaiPa")])

    out = await rail.repair(session, apply=True)

    assert out["scan_exhausted"] is True


@pytest.mark.asyncio
async def test_every_response_carries_the_window_it_was_scoped_to(monkeypatch, fast):
    """🔴 `scan_exhausted` MEANS "NONE LEFT INSIDE THE WINDOW".

    Both halves are bounded to a 30-day event window for plan reasons — the
    unbounded population times out. A response that reported exhaustion without
    reporting its window would read as "the cohort is empty", which is the
    reading that let the sibling's partial fix look complete.
    """
    market = _Market("0xaa", "KooKoo vs. SaiPa", ["KooKoo", "SaiPa"])
    _venue(monkeypatch, _FakeService([market]))

    session = _Session(page=[_row(1, 10, "0xaa", "KooKoo vs. SaiPa")])
    out = await rail.repair(session, apply=False)
    assert out["window_days"] == rail.DEFAULT_WINDOW_DAYS

    # The empty-page terminal is a DIFFERENT return path and the easiest one to
    # forget, because it is the one that says "exhausted".
    empty = _Session(page=[])
    out_empty = await rail.repair(empty, apply=False)
    assert out_empty["scan_exhausted"] is True
    assert out_empty["window_days"] == rail.DEFAULT_WINDOW_DAYS
    assert str(rail.DEFAULT_WINDOW_DAYS) in out_empty["reason"]

    # And a paused-before-examining path.
    census_out = await rail.census(_Session(census_rows=[]))
    assert census_out["window_days"] == rail.DEFAULT_WINDOW_DAYS


@pytest.mark.asyncio
async def test_the_window_reaches_the_statement_as_a_bound_parameter(
    monkeypatch, fast
):
    """The window must be IN the SQL, not merely reported beside it.

    Driven by monkeypatching the CONSTANT rather than passing a parameter,
    because the window deliberately is not one: the dispatcher forwards a fixed
    set of names and a rail that declared `days` would advertise a knob no
    caller could turn (`test_the_dispatcher_can_forward_every_param_this_rail_declares`).
    """
    market = _Market("0xaa", "KooKoo vs. SaiPa", ["KooKoo", "SaiPa"])
    _venue(monkeypatch, _FakeService([market]))
    monkeypatch.setattr(rail, "DEFAULT_WINDOW_DAYS", 7)
    session = _Session(page=[_row(1, 10, "0xaa", "KooKoo vs. SaiPa")])

    out = await rail.repair(session, apply=False)

    assert "make_interval(days => CAST(:days AS int))" in " ".join(
        session.page_sql.split()
    )
    assert session.page_params["days"] == 7
    assert out["window_days"] == 7


# ---------------------------------------------------------------------------
# 7b. Reachability — a rail with no address is a rail nobody can run
# ---------------------------------------------------------------------------


def test_both_halves_are_reachable_as_endpoints():
    """Registered in the same commit that builds it."""
    from app.routes.admin_repairs import _REPAIRS

    assert _REPAIRS["polymarket-single-leg-label-census"] == (
        "app.tasks.repair_polymarket_single_leg_label",
        "census",
    )
    assert _REPAIRS["polymarket-single-leg-label"] == (
        "app.tasks.repair_polymarket_single_leg_label",
        "repair",
    )

    import app.routes.admin_repairs as mod

    assert "polymarket-single-leg-label" in (mod.__doc__ or ""), (
        "the docstring catalog has drifted from the registry again"
    )


def test_the_dispatcher_can_forward_every_param_this_rail_declares():
    """FastAPI drops an unknown query param SILENTLY, so a rail that declared a
    cursor the dispatcher cannot pass would re-read page one forever while the
    response looked perfectly busy.

    This is also why the event window is a module constant and not a `days`
    parameter — it would fail right here.
    """
    import app.routes.admin_repairs as mod

    declared = set(inspect.signature(mod.run_repair).parameters)
    mine = set(inspect.signature(rail.repair).parameters) - {"session", "apply"}
    assert mine, "the repair takes no optional params — this guard is vacuous"
    assert mine <= declared, f"the dispatcher cannot forward {sorted(mine - declared)}"


# ---------------------------------------------------------------------------
# 7. The census
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_census_reports_unmeasured_never_zero_when_it_times_out():
    """A zero here would read as "drained" (gotcha #54)."""

    class _Boom(_Session):
        async def execute(self, stmt, params=None):
            sql = " ".join(str(stmt).split())
            if sql.upper().startswith("SET LOCAL"):
                return _Result()
            raise RuntimeError("canceling statement due to statement timeout")

    out = await rail.census(_Boom())

    assert out["measured"] is False
    assert out["total_legs"] is None, "a census that could not look reported a number"
    assert out["reason"]


@pytest.mark.asyncio
async def test_the_census_splits_by_category_and_totals_them():
    """A bare total cannot tell a drain that is working from one that is only
    reaching the category the poller happens to rotate through."""
    session = _Session(census_rows=[("hockey", 120, 119), ("baseball", 63, 62)])

    out = await rail.census(session)

    assert out["measured"] is True
    assert out["by_category"]["hockey"] == {"legs": 120, "markets": 119}
    assert out["total_legs"] == 183
    assert out["total_markets"] == 181


@pytest.mark.asyncio
async def test_the_census_never_writes_even_when_told_to_apply():
    """A census that could write would be a repair with a reassuring name."""
    session = _Session(census_rows=[("hockey", 1, 1)])

    await rail.census(session, apply=True)

    assert not session.writes
    assert session.commits == 0


# ---------------------------------------------------------------------------
# 8. One population, written once
# ---------------------------------------------------------------------------


def test_the_census_and_the_pager_share_one_population():
    """Two spellings of "side-less settled leg" is how a drain comes to report
    progress against a population it is not actually walking."""
    src = inspect.getsource(rail)
    assert src.count("{POPULATION_FROM}") == 3, (
        "the shared FROM/WHERE is no longer interpolated into all three "
        "statements (page, census, remaining count)"
    )
    assert src.count("{POPULATION_HAVING}") == 3, (
        "the shared HAVING is no longer interpolated into all three statements"
    )


def test_the_population_is_the_literal_yes_and_not_a_broader_set():
    """🔴 `'No'` MUST NOT BE IN THIS POPULATION.

    The single-market branch wrote the literal "Yes" and nothing else, so index
    0 is that leg's side. A leg stored as "No" is some OTHER writer's row, and
    taking index 0 for it would name the wrong side.
    """
    assert "min(fo.name) = 'Yes'" in rail.POPULATION_HAVING
    assert "'No'" not in rail.POPULATION_HAVING
    assert "IN (" not in rail.POPULATION_HAVING.upper()


def test_the_population_is_single_leg_by_construction():
    """`count(*) = 1` is not a tidiness filter — it is what makes `min(fo.id)`
    the leg's own id and `min(fo.name)` that leg's own name, both of which the
    keyset and the predicate depend on."""
    assert "count(*) = 1" in rail.POPULATION_HAVING


def test_the_population_is_settled_rows_the_poller_cannot_reach():
    """The whole reason this rail exists: `poll_polymarket_markets` fetches
    `closed=False`, so a resolved market never re-enters its rotation and the
    upsert's `on_conflict_do_update` never fires on it again."""
    assert "fm.status = 'resolved'" in rail.POPULATION_FROM
    assert "fm.source = 'polymarket'" in rail.POPULATION_FROM


# ---------------------------------------------------------------------------
# 9. Budgets — every one derived, none of them a comment
# ---------------------------------------------------------------------------


def test_the_worst_case_still_fits_under_the_router_wall():
    """Positive means an over-running call returns a partial answer WITH its
    cursor. Negative means H12 with no body, and an attended drain silently
    loses its place."""
    assert rail.budget_headroom_seconds() > 0, (
        f"the worst case exceeds the {rail.ROUTER_WALL_SECONDS}s wall"
    )


def test_the_page_select_bound_cannot_exceed_the_loop_deadline():
    """`started` is captured BEFORE the page SELECT, so a slow SELECT does not
    add to the total — it just leaves the loop less room. That argument holds
    only while this inequality does."""
    assert rail.TARGET_SELECT_BUDGET_SECONDS <= rail.DEADLINE_SECONDS


def test_everything_the_non_count_reserve_names_actually_fits_inside_it():
    """The DERIVED client bounds, not the server budgets, and the FAILURE path,
    not the happy one — the arithmetic CERT-681 withheld a token over on the
    sibling rail."""
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


def test_the_venue_pause_is_real():
    """The `fast` fixture zeroes this; if the shipped value were also zero the
    whole suite would be pacing-blind and Gamma's limiter would find out in
    production instead."""
    src = inspect.getsource(rail)
    assert "VENUE_PAUSE = 0.35" in src


def test_the_rail_is_attended_only_and_not_wired_to_a_beat():
    """A drain has an end state. A beat does not."""
    from app.tasks import celery_app

    beats = dict(celery_app.conf.beat_schedule or {})
    assert len(beats) > 50, (
        f"only {len(beats)} beat entries read — this guard would be vacuous"
    )
    for name, entry in beats.items():
        assert "single_leg_label" not in str(entry.get("task", "")), (
            f"beat entry {name!r} runs the drain on a schedule"
        )


def test_every_bind_in_the_rails_sql_actually_parses_as_a_bind():
    """A `:name::type` bind is silently mis-parsed and never reaches Postgres bound.

    Shipped in `d1b1bb8b9` and INERT on production the moment it released: both
    halves of the rail answered
    `syntax error at or near ":"` and relabelled nothing. SQLAlchemy's `text()`
    bindparam scanner refuses a name followed by a colon — that lookahead exists so
    `::` casts are not eaten — so `:days::int` does not yield `days`. It yields
    `day`, a name the caller never supplies, and the unconsumed remainder is sent to
    the server as literal SQL.

    Nothing in the 33 guards above could see it: every one of them drives the rail
    against a fake session, so the SQL is built, passed as a string, and never
    parsed by SQLAlchemy or by Postgres. The class is "SQL that is only ever
    constructed in a test, never compiled", and the fix is to compile it here.

    Asserts the POSITIVE form — the exact bind names the callers pass — rather than
    grepping for `::`, because `CAST(x AS int)` is not the only safe spelling and a
    grep would forbid legitimate casts on non-bind expressions.
    """
    import re

    from sqlalchemy import text

    # The window bind lives in the shared FROM both halves interpolate.
    assert set(text(rail.POPULATION_FROM)._bindparams) == {"days"}, (
        f"POPULATION_FROM binds {sorted(text(rail.POPULATION_FROM)._bindparams)}, "
        f"expected exactly ['days'] — a `:days::int` spelling yields 'day'"
    )

    # Every `:name` written anywhere in the module's source must survive parsing
    # under its own name. This is what catches the next one.
    src = inspect.getsource(rail)
    written = set(re.findall(r"(?<![:\w]):([a-z_][a-z_0-9]*)(?=::)", src))
    assert not written, (
        f"these binds are written as `:name::type` and will be mis-parsed by "
        f"SQLAlchemy: {sorted(written)} — use CAST(:name AS type)"
    )
