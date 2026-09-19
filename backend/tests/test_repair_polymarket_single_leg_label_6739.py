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

    def scalar_one_or_none(self):
        """What the durable store reads off its own upsert.

        Absent, this raised `AttributeError` INSIDE the store's own `except`,
        which classifies it as a failed publish — so every apply test read as a
        rolled-back page and the four that failed were failing about the
        harness, not about the rail.
        """
        return self._scalar

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None


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
        receipt_generation=1,
    ):
        self.page = list(page)
        self.remaining = remaining
        #: ids the compare-and-set is allowed to return. ``None`` = all of them,
        #: which is the un-raced case.
        self.landed = landed
        self.census_rows = list(census_rows)
        #: What the durable store's upsert RETURNS. ``None`` is the store's own
        #: "nothing was written" — a superseded or occupied identity — which is
        #: how the receipt-failure path is driven without patching the rail.
        self.receipt_generation = receipt_generation
        self.statements: list[tuple[str, dict]] = []
        self.writes: list[tuple[str, dict]] = []
        #: Every undo payload the rail staged, decoded from the JSON the store
        #: binds. The receipt assertions read THIS, not a mock's call args, so
        #: they see what would actually be stored.
        self.receipts: list[dict] = []
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
        if "INSERT INTO DURABLE_STATE_SNAPSHOTS" in upper:
            import json as _json

            self.receipts.append(_json.loads((params or {})["payload"]))
            return _Result(scalar=self.receipt_generation)
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


# ---------------------------------------------------------------------------
# 9. Reversibility (D51) — the receipt, and the one command that uses it
#
# The four things THESE guards exist to stop:
#
# 1. **A receipt built from the PLAN.** `writable` is what the rail meant to
#    write; `RETURNING` is what it wrote. A row the poller re-ingested is in the
#    first and not the second, and a restore that offered to put it back would
#    rewrite a label this rail never touched.
# 2. **A write that outlives its receipt.** Stage the record on its own
#    connection, or after the commit, and one crash leaves a relabelled row
#    whose old name exists nowhere. The receipt goes in the write's own
#    transaction and a failure to stage it rolls the write back.
# 3. **A restore keyed on the id alone.** Between apply and reversal the poller,
#    a person, or a later repair may have corrected a leg. `WHERE id = ANY(...)`
#    drags those corrections back to "Yes"; the compare-and-set on the label
#    this rail wrote leaves them alone.
# 4. **A reversal that reports its INPUT.** Counting the receipt's length prints
#    a full restore over a run that put nothing back (gotcha #53).
# ---------------------------------------------------------------------------


class _RestoreSession:
    """A session for the reversal path, keyed on the names rows carry NOW.

    Separate from `_Session` deliberately: the restore reads a shape the apply
    harness has no route for, and teaching one fake both jobs is how a test ends
    up asserting against a branch that never ran.
    """

    def __init__(self, names: dict, *, select_raises=None, write_raises=None):
        #: outcome_id -> the name the row carries right now. A missing key is a
        #: row that no longer exists.
        self.names = dict(names)
        self.select_raises = select_raises
        self.write_raises = write_raises
        self.statements: list[tuple[str, dict]] = []
        self.writes: list[tuple[str, dict]] = []
        self.commits = 0
        self.rollbacks = 0
        self.invalidations = 0

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        params = dict(params or {})
        self.statements.append((sql, params))
        upper = sql.upper()
        if upper.startswith("SET LOCAL"):
            return _Result()
        if upper.startswith("SELECT FO.ID, FO.NAME"):
            if self.select_raises:
                raise self.select_raises
            wanted = params.get("ids") or []
            return _Result(
                rows=[(i, self.names[i]) for i in wanted if i in self.names]
            )
        if upper.startswith("UPDATE"):
            self.writes.append((sql, params))
            if self.write_raises:
                raise self.write_raises
            landed = []
            i = 0
            while f"id{i}" in params:
                row_id = params[f"id{i}"]
                # The fake honours the compare-and-set; a fake that returned
                # every id would make guard 3 vacuous.
                if self.names.get(row_id) == params[f"new{i}"]:
                    self.names[row_id] = params[f"old{i}"]
                    landed.append(row_id)
                i += 1
            return _Result(rows=[(r,) for r in landed])
        return _Result()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def invalidate(self):
        self.invalidations += 1


@pytest.fixture
def receipt(monkeypatch):
    """Serve one stored undo record, with its store status under test control."""
    state = {"status": "ok", "payload": None}

    async def _read(identity, expected_version=None, max_age_s=None):
        from app.utils.durable_state import DurableEnvelope, EnvelopeRead

        if state["status"] != "ok":
            return EnvelopeRead(status=state["status"], tier="durable")
        return EnvelopeRead(
            status="ok",
            tier="durable",
            envelope=DurableEnvelope.build(
                identity=identity,
                schema_version=rail.UNDO_SCHEMA,
                payload=state["payload"],
                complete=True,
                source="test",
            ),
        )

    monkeypatch.setattr(
        "app.services.durable_snapshots.read_snapshot_standalone", _read
    )
    return state


def _receipt_payload(changes):
    return {
        rail.UNDO_OWNER_KEY: "abc123",
        "taken_at": "2026-09-19T11:00:00+00:00",
        "repair": "polymarket-single-leg-label",
        "window_days": 30,
        "sport": None,
        "changes": list(changes),
    }


@pytest.mark.asyncio
async def test_the_receipt_names_the_rows_that_landed_not_the_rows_planned(
    monkeypatch, fast
):
    """Guard 1. Leg 2 is planned and RACED — it must not appear in the receipt.

    Without this the restore would offer to rewrite a leg whose current label
    some other writer owns.
    """
    _venue(
        monkeypatch,
        _FakeService(
            [
                _Market("0xaa", "KooKoo vs. SaiPa", ["KooKoo", "SaiPa"]),
                _Market("0xbb", "Ilves vs. Tappara", ["Ilves", "Tappara"]),
            ]
        ),
    )
    session = _Session(
        page=[
            _row(1, 10, "0xaa", "KooKoo vs. SaiPa"),
            _row(2, 20, "0xbb", "Ilves vs. Tappara"),
        ],
        landed=[1],
    )

    out = await rail.repair(session, apply=True)

    assert out["counts"]["relabelled"] == 1
    assert out["counts"]["raced"] == 1
    assert len(session.receipts) == 1, (
        "the rail staged no receipt — every assertion below would be vacuous"
    )
    assert [c["outcome_id"] for c in session.receipts[0]["changes"]] == [1]
    assert session.receipts[0]["changes"][0] == {
        "outcome_id": 1,
        "market_id": 10,
        "category": "hockey",
        "from": "Yes",
        "to": "KooKoo",
    }
    assert [c["outcome_id"] for c in out["changes"]] == [1]


@pytest.mark.asyncio
async def test_the_receipt_is_staged_before_the_commit_that_carries_the_write(
    monkeypatch, fast
):
    """Guard 2, read off ONE timeline.

    Ordering asserted against the statement transcript rather than against two
    separate counters: the property is "these land together", and only the
    transcript can show that the receipt went in before the transaction closed.
    """
    _venue(monkeypatch, _FakeService([_Market("0xaa", "A vs. B", ["A", "B"])]))
    session = _Session(page=[_row(1, 10, "0xaa", "A vs. B")])

    await rail.repair(session, apply=True)

    shapes = [
        (
            "update"
            if s.upper().startswith("UPDATE")
            else "receipt"
            if "INSERT INTO DURABLE_STATE_SNAPSHOTS" in s.upper()
            else "other"
        )
        for s, _p in session.statements
    ]
    assert "update" in shapes and "receipt" in shapes
    assert shapes.index("update") < shapes.index("receipt"), (
        "the receipt was staged BEFORE the write, so it describes rows that may "
        "yet roll back"
    )
    assert session.commits == 1, (
        "the write and its receipt did not share one commit"
    )


@pytest.mark.asyncio
async def test_a_receipt_that_will_not_persist_rolls_the_relabel_back(
    monkeypatch, fast
):
    """Guard 2's other half — the property Codex asked to see proved.

    `receipt_generation=None` is the store's own "nothing was written"
    (superseded / occupied). The rail must treat an unrecorded write as no write
    at all, and hand the operator back the SAME cursor so the page is retried
    rather than stepped over.
    """
    _venue(monkeypatch, _FakeService([_Market("0xaa", "A vs. B", ["A", "B"])]))
    session = _Session(
        page=[_row(1, 10, "0xaa", "A vs. B")], receipt_generation=None
    )

    out = await rail.repair(session, apply=True, after_id=99)

    assert out["terminal"] == "paused_receipt_unpersisted"
    assert out["counts"]["relabelled"] == 0
    assert out["counts"]["raced"] == 0, (
        "a rolled-back page reported concurrent re-ingests that never happened"
    )
    assert out["changes"] == []
    assert out["undo_identity"] is None
    assert out["restore_command"] is None
    assert session.rollbacks == 1
    assert session.commits == 0, "the page committed without a durable receipt"
    assert out["next_cursor"] == {"after_id": 99}
    assert out["scan_exhausted"] is False


@pytest.mark.asyncio
async def test_every_apply_prints_the_one_command_that_reverses_it(
    monkeypatch, fast
):
    """D51's actual requirement: a restore that is runnable, not described."""
    _venue(monkeypatch, _FakeService([_Market("0xaa", "A vs. B", ["A", "B"])]))
    session = _Session(page=[_row(1, 10, "0xaa", "A vs. B")])

    out = await rail.repair(session, apply=True)

    assert out["undo_identity"]
    assert out["undo_identity"].startswith(
        "repair:polymarket_single_leg_label:undo:"
    )
    assert out["restore_command"] == rail.restore_command(out["undo_identity"])
    assert f"undo_identity={out['undo_identity']}" in out["restore_command"]
    assert "apply=true" in out["restore_command"]


@pytest.mark.asyncio
async def test_two_pages_bank_two_different_receipts(monkeypatch, fast):
    """A 186-leg drain is two calls, so a reversal is two commands.

    An identity shared between calls would let the second page's receipt replace
    the first's, and the store's owner guard would refuse it — either way one
    page becomes unreversible.
    """
    _venue(
        monkeypatch,
        _FakeService(
            [
                _Market("0xaa", "A vs. B", ["A", "B"]),
                _Market("0xbb", "C vs. D", ["C", "D"]),
            ]
        ),
    )
    first = await rail.repair(
        _Session(page=[_row(1, 10, "0xaa", "A vs. B")]), apply=True
    )
    second = await rail.repair(
        _Session(page=[_row(2, 20, "0xbb", "C vs. D")]), apply=True, after_id=1
    )

    assert first["undo_identity"] != second["undo_identity"]


@pytest.mark.asyncio
async def test_a_dry_run_banks_no_receipt_and_offers_no_restore(monkeypatch, fast):
    _venue(monkeypatch, _FakeService([_Market("0xaa", "A vs. B", ["A", "B"])]))
    session = _Session(page=[_row(1, 10, "0xaa", "A vs. B")])

    out = await rail.repair(session, apply=False)

    assert session.receipts == []
    assert out["undo_identity"] is None
    assert out["restore_command"] is None
    assert out["changes"] == [], "a dry run reported rows it did not write"


@pytest.mark.asyncio
async def test_the_dry_run_shows_the_whole_plan_not_a_sample_of_it(
    monkeypatch, fast
):
    """An operator cannot authorise a write they can only see a sixth of.

    25 rows: `samples` caps at 20 by design, `planned_changes` must not.
    """
    markets = [_Market(f"0x{i:02x}", f"H{i} vs. A{i}", [f"H{i}", f"A{i}"])
               for i in range(25)]
    _venue(monkeypatch, _FakeService(markets))
    session = _Session(
        page=[_row(i + 1, 100 + i, f"0x{i:02x}", f"H{i} vs. A{i}")
              for i in range(25)]
    )

    out = await rail.repair(session, apply=False)

    assert out["planned"] == 25
    assert len(out["samples"]) == 20
    assert len(out["planned_changes"]) == 25
    assert out["planned_changes"][24]["to"] == "H24"


@pytest.mark.asyncio
async def test_the_restore_puts_the_old_label_back(receipt):
    receipt["payload"] = _receipt_payload(
        [{"outcome_id": 1, "market_id": 10, "from": "Yes", "to": "KooKoo"}]
    )
    session = _RestoreSession({1: "KooKoo"})

    out = await rail.repair(session, apply=True, undo_identity="id-1")

    assert out["mode"] == "restore"
    assert out["counts"]["restored"] == 1
    assert session.names[1] == "Yes"
    assert session.commits == 1


@pytest.mark.asyncio
async def test_a_real_applys_own_receipt_drives_a_real_restore(
    monkeypatch, fast, receipt
):
    """The producer/consumer round trip: apply -> its OWN receipt -> restore.

    Every other reversal test feeds the restore a payload THIS FILE built, so
    together they prove only that the restore reads the shape the test writes.
    Neither half can see the apply renaming a key -- "from", "to", "outcome_id"
    -- because the hand-built payload would go on carrying the old spelling.
    Both halves stay green and the printed undo command is dead at the one
    moment it is ever invoked: after a bad apply on 187 live legs.

    So here the receipt is the one the apply actually staged, and the world the
    restore meets is the one the apply actually wrote -- derived from that
    receipt, never typed out beside it.
    """
    _venue(
        monkeypatch,
        _FakeService(
            [
                _Market("0xaa", "KooKoo vs. SaiPa", ["KooKoo", "SaiPa"]),
                _Market("0xbb", "Ilves vs. Tappara", ["Ilves", "Tappara"]),
            ]
        ),
    )
    apply_session = _Session(
        page=[
            _row(1, 10, "0xaa", "KooKoo vs. SaiPa"),
            _row(2, 20, "0xbb", "Ilves vs. Tappara"),
        ]
    )

    applied = await rail.repair(apply_session, apply=True)

    assert applied["counts"]["relabelled"] == 2
    assert len(apply_session.receipts) == 1, (
        "the apply staged no receipt — the round trip below would be vacuous"
    )

    staged = apply_session.receipts[0]
    receipt["payload"] = staged

    # Stated before the derivation so a drifted key fails HERE, naming both
    # sides, rather than as a bare KeyError inside the harness. Reading these
    # with `.get` instead would be worse than useless: a missing "to" would make
    # the restore compare None against None, match every row, and pass.
    reads = {"outcome_id", "from", "to"}
    assert reads <= set(staged["changes"][0]), (
        f"the apply stages {sorted(staged['changes'][0])} but the reversal reads "
        f"{sorted(reads)} — the undo command every apply prints cannot put these "
        "rows back"
    )

    # The post-apply world, read off the receipt itself rather than typed out
    # beside it: every leg now carries the name the apply actually wrote.
    restore_session = _RestoreSession(
        {c["outcome_id"]: c["to"] for c in staged["changes"]}
    )

    out = await rail.repair(restore_session, apply=True, undo_identity="id-1")

    assert out["mode"] == "restore"
    assert out["counts"]["restored"] == 2, (
        "the restore did not read the shape the apply staged — receipt was "
        f"{staged['changes']!r}, restore reported {out['counts']!r}"
    )
    assert restore_session.names == {1: "Yes", 2: "Yes"}, (
        "the round trip did not land both legs back on the name they started on"
    )


@pytest.mark.asyncio
async def test_the_restore_leaves_a_row_something_else_has_corrected_since(
    receipt,
):
    """Guard 3 — the reason a broad id-keyed UPDATE is refused.

    Leg 2 now reads "Tappara": somebody corrected it after the apply. A reversal
    that dragged it back to "Yes" would undo work nobody asked it to undo.
    """
    receipt["payload"] = _receipt_payload(
        [
            {"outcome_id": 1, "market_id": 10, "from": "Yes", "to": "KooKoo"},
            {"outcome_id": 2, "market_id": 20, "from": "Yes", "to": "Ilves"},
            {"outcome_id": 3, "market_id": 30, "from": "Yes", "to": "Lukko"},
        ]
    )
    session = _RestoreSession({1: "KooKoo", 2: "Tappara"})

    out = await rail.repair(session, apply=True, undo_identity="id-1")

    assert out["counts"]["restored"] == 1
    assert out["counts"]["refused_changed_since"] == 1
    assert out["counts"]["missing"] == 1, "leg 3 is gone and was not counted"
    assert session.names[1] == "Yes"
    assert session.names[2] == "Tappara", "a later correction was overwritten"
    assert "IS NOT DISTINCT FROM v.new_name" in session.writes[0][0], (
        "the reversal is not a compare-and-set on the label this rail wrote"
    )


@pytest.mark.asyncio
async def test_a_second_restore_of_the_same_page_reports_already_old(receipt):
    """Re-running a reversal is not an error and it is not a restoration."""
    receipt["payload"] = _receipt_payload(
        [{"outcome_id": 1, "market_id": 10, "from": "Yes", "to": "KooKoo"}]
    )
    session = _RestoreSession({1: "Yes"})

    out = await rail.repair(session, apply=True, undo_identity="id-1")

    assert out["counts"]["already_old"] == 1
    assert out["counts"]["restored"] == 0
    assert session.writes == [], "the reversal rewrote a row already back"


@pytest.mark.asyncio
async def test_the_restore_counts_what_postgres_returned_not_the_receipt(receipt):
    """Guard 4. The fake loses leg 1's compare between the read and the write —
    the row-lock race — and the count must follow Postgres, not the input."""
    receipt["payload"] = _receipt_payload(
        [{"outcome_id": 1, "market_id": 10, "from": "Yes", "to": "KooKoo"}]
    )
    session = _RestoreSession({1: "KooKoo"})
    real_execute = session.execute

    async def _racing_execute(stmt, params=None):
        if " ".join(str(stmt).split()).upper().startswith("UPDATE"):
            session.names[1] = "somebody else"
        return await real_execute(stmt, params)

    session.execute = _racing_execute

    out = await rail.repair(session, apply=True, undo_identity="id-1")

    assert out["counts"]["restored"] == 0
    assert out["counts"]["refused_changed_since"] == 1


@pytest.mark.asyncio
async def test_the_restore_dry_run_reports_the_plan_and_writes_nothing(receipt):
    receipt["payload"] = _receipt_payload(
        [{"outcome_id": 1, "market_id": 10, "from": "Yes", "to": "KooKoo"}]
    )
    session = _RestoreSession({1: "KooKoo"})

    out = await rail.repair(session, apply=False, undo_identity="id-1")

    assert out["applied"] is False
    assert out["would_restore"] == 1
    assert out["counts"]["restored"] == 0
    assert session.writes == []
    assert session.commits == 0
    assert out["samples"][0] == {
        "outcome_id": 1, "market_id": 10, "from": "KooKoo", "to": "Yes",
    }


@pytest.mark.asyncio
async def test_a_store_outage_is_not_reported_as_a_missing_receipt(receipt):
    """`read_snapshot_standalone` never raises — it returns `unavailable`.

    Telling an operator mid-reversal that their receipt does not exist is how a
    reversible apply becomes an unreversed one.
    """
    receipt["status"] = "unavailable"
    session = _RestoreSession({1: "KooKoo"})

    out = await rail.repair(session, apply=True, undo_identity="id-1")

    assert out["refused"] == rail.REASON_UNDO_UNREADABLE
    assert session.writes == []
    assert session.commits == 0


@pytest.mark.asyncio
async def test_a_receipt_that_is_genuinely_absent_says_so_by_its_own_name(receipt):
    receipt["status"] = "missing"
    session = _RestoreSession({1: "KooKoo"})

    out = await rail.repair(session, apply=True, undo_identity="id-1")

    assert out["refused"] == rail.REASON_UNDO_MISSING
    assert session.writes == []


@pytest.mark.asyncio
async def test_a_receipt_whose_shape_is_wrong_is_refused_not_read_as_empty(
    receipt,
):
    """A payload with no `changes` list is CORRUPT, and "corrupt" must not
    arrive as "nothing to restore" — the two send an operator to very different
    places."""
    receipt["payload"] = {"invocation": "abc", "rows": []}
    session = _RestoreSession({1: "KooKoo"})

    out = await rail.repair(session, apply=True, undo_identity="id-1")

    assert out["refused"] == rail.REASON_UNDO_CORRUPT
    assert session.writes == []


@pytest.mark.asyncio
async def test_the_reversal_names_one_column_and_never_the_touch_stamp(receipt):
    """The apply may not forge `last_updated` (#2024) and neither may the
    reversal — a rollback that bumped it would claim a venue observation on the
    way back out."""
    receipt["payload"] = _receipt_payload(
        [{"outcome_id": 1, "market_id": 10, "from": "Yes", "to": "KooKoo"}]
    )
    session = _RestoreSession({1: "KooKoo"})

    await rail.repair(session, apply=True, undo_identity="id-1")

    sql = session.writes[0][0].lower()
    assert "set name = v.old_name" in sql
    assert "last_updated" not in sql
    assert "is_winner" not in sql


@pytest.mark.asyncio
async def test_the_restore_takes_precedence_over_every_other_parameter(receipt):
    """An operator reversing a page must never be able to start a NEW drain by
    leaving a stale `sport=` or `after_id=` on the command line."""
    receipt["payload"] = _receipt_payload(
        [{"outcome_id": 1, "market_id": 10, "from": "Yes", "to": "KooKoo"}]
    )
    session = _RestoreSession({1: "KooKoo"})

    out = await rail.repair(
        session, apply=True, undo_identity="id-1", sport="hockey", after_id=5
    )

    assert out["mode"] == "restore"
    assert not any(
        "LIMIT CAST(:cap AS int)" in s for s, _p in session.statements
    ), "the reversal also ran a page of the drain"


def test_the_restore_is_reachable_by_the_documented_parameter():
    """`undo_identity` is forwarded only to repairs whose SIGNATURE names it;
    FastAPI drops an unknown query param silently, so a restore nobody can
    address is a restore that does not exist."""
    assert "undo_identity" in inspect.signature(rail.repair).parameters

    import app.routes.admin_repairs as mod

    assert "undo_identity" in set(inspect.signature(mod.run_repair).parameters)


def test_the_receipt_budget_fits_inside_the_post_loop_reserve():
    """The receipt is charged against the same reserve as the write and its
    commit, and the guard reads the DERIVED client bounds — the arithmetic
    CERT-681 withheld a token over on the sibling rail."""
    charged = (
        rail.client_db_budget_seconds(rail.WRITE_BUDGET_SECONDS)
        + rail.RECEIPT_BUDGET_SECONDS
        + rail.client_db_budget_seconds(rail.COMMIT_BUDGET_SECONDS)
        + rail.CLEANUP_RESERVE_SECONDS
        + rail.SERIALIZATION_RESERVE_SECONDS
    )
    assert charged <= rail.POST_LOOP_NON_COUNT_RESERVE_SECONDS, (
        f"the write, its receipt, the commit, one cleanup and the serialization "
        f"are charged {charged}s against a "
        f"{rail.POST_LOOP_NON_COUNT_RESERVE_SECONDS}s reserve"
    )


def test_the_undo_record_is_not_aged_out_of_readability():
    """The store's default max age is 7 days. A label repair is reversible for
    as long as the row exists, and a receipt typed too-old reads to an operator
    exactly like a receipt that was never written."""
    from app.utils.durable_state import DEFAULT_MAX_AGE_S

    assert rail.UNDO_MAX_AGE_S > DEFAULT_MAX_AGE_S
    assert rail.UNDO_MAX_AGE_S >= 90 * 86400


@pytest.mark.asyncio
async def test_every_bind_on_the_reversal_path_survives_parsing(receipt):
    """The reversal's SQL is built inline, so the module-level bind guard above
    cannot see it — and the reversal is the one path nobody exercises until they
    need it. Compiled here from the statements the rail ACTUALLY issued.

    `= ANY(:ids)` is asserted by name because it is the spelling with production
    history on this driver (`backfill_winners` runs it against this very table
    every six hours); a CAST spelling would be a debut on the rollback path.
    """
    from sqlalchemy import text

    receipt["payload"] = _receipt_payload(
        [
            {"outcome_id": 1, "market_id": 10, "from": "Yes", "to": "KooKoo"},
            {"outcome_id": 2, "market_id": 20, "from": "Yes", "to": "Ilves"},
        ]
    )
    session = _RestoreSession({1: "KooKoo", 2: "Ilves"})

    out = await rail.repair(session, apply=True, undo_identity="id-1")
    assert out["counts"]["restored"] == 2, "the write never ran; this is vacuous"

    read_sql = next(
        s for s, _p in session.statements if s.upper().startswith("SELECT FO.ID")
    )
    assert set(text(read_sql)._bindparams) == {"ids"}
    assert "= ANY(:ids)" in read_sql

    write_sql, write_params = session.writes[0]
    assert set(text(write_sql)._bindparams) == set(write_params)
