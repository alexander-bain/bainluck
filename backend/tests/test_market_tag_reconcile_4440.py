"""#4440 — `market_tags` is written once at ingest and nothing re-derives it.

## The defect

`market_tags` is the JSONB column the Discover feed's static `tags=` filter keys
its candidate base on. Two arms ever rewrite it and neither can see this
population:

* the backfill arm selects on ABSENCE (`market_tags` null or `[]`), and
* the refresh arm selects OPEN rows inside a 30-minute `updated_at` window,

so a row that already HAS tags and was updated an hour ago is in neither. When a
classification repair corrects `llm_sport_category` — #4229 corrected 21
Senate-confirmation rows — the row keeps its old sport tag forever.

Measured on production 2026-09-09: 32 OPEN rows disagreeing when #4440 was
filed, 19 the same evening, including `25924714` "Which Senators will vote for
the Clarity Act?" carrying **`sport:hockey`**. That is the row lane1b/109 found
sitting in the "MORE HOCKEY" rail on a US-Senate page.

## The arm that carries the safety argument

`test_a_recompute_that_would_drop_the_sport_tag_is_refused`. Three of the
nineteen are `llm_sport_category='geopolitics'`, which is **not** in
`ALLOWED_TAGS["sport"]`, so a blind re-derive emits no sport tag and the write
would DELETE the row's only sport tag. #4440's own filing caught the same shape
on two live US Open ATP matches stored as `table_tennis` while their
`sport:tennis` tag was correct — re-deriving those would have stripped a
marquee fixture's tag mid-tournament.

**The refusal is the difference between a repair and a regression**, so it is
counted rather than silent: that shape means the classification is wrong, not
the tag, and it belongs to the classifier (#3559).
"""

from __future__ import annotations

import asyncio

import pytest

from app.tasks import taxonomy as mod


class _Market:
    """The attributes `compute_market_tags` reads, plus the column it writes."""

    def __init__(self, market_id, sport_category, tags, **kw):
        self.id = market_id
        self.llm_sport_category = sport_category
        self.market_tags = list(tags)
        self.llm_league = kw.get("llm_league")
        self.llm_gender = kw.get("llm_gender")
        self.llm_level = kw.get("llm_level")
        self.market_tier = kw.get("market_tier")
        self.category = kw.get("category")
        self.status = kw.get("status", "open")
        self.resolution_date = kw.get("resolution_date")
        self.source = kw.get("source", "kalshi")


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _Result:
    def __init__(self, rows=(), count=0):
        self._rows = list(rows)
        self._count = count

    def scalars(self):
        return _Scalars(self._rows)

    def scalar(self):
        return self._count


class _Session:
    """Dispatches the row select from the count select on the compiled SQL."""

    def __init__(self, rows, remaining=None):
        self.rows = list(rows)
        self.remaining = len(self.rows) if remaining is None else remaining
        self.commits = 0
        self.limits: list[int] = []

    async def execute(self, stmt):
        sql = str(stmt).lower()
        if "count(" in sql:
            return _Result(count=self.remaining)
        limit = getattr(stmt, "_limit", None)
        if limit is None:  # SQLAlchemy 2 keeps it in a clause element
            clause = getattr(stmt, "_limit_clause", None)
            limit = getattr(clause, "value", None)
        self.limits.append(limit)
        return _Result(rows=self.rows)

    async def commit(self):
        self.commits += 1


def _run(session, **kw):
    return asyncio.run(mod._reconcile_disagreeing_market_tags(session, **kw))


# The production specimens, as data, so every arm argues about a real row.
SENATE = dict(market_id=25924714, sport_category="politics", tags=["sport:hockey"])
GEOPOLITICS = dict(market_id=115299, sport_category="geopolitics", tags=["sport:politics"])
NFL = dict(market_id=52755820, sport_category="football", tags=["sport:baseball"])


class TestItRepairsWhatNeitherOtherArmCanReach:
    def test_a_corrected_classification_finally_moves_its_tag(self):
        market = _Market(**SENATE)
        session = _Session([market])

        stats = _run(session)

        assert stats["changed"] == 1
        assert "sport:politics" in market.market_tags
        assert "sport:hockey" not in market.market_tags, (
            "the Clarity Act row kept sport:hockey — it stays in the MORE HOCKEY "
            "rail's candidate base"
        )
        assert session.commits == 1

    def test_the_nfl_rows_move_off_baseball(self):
        market = _Market(**NFL)
        stats = _run(_Session([market]))

        assert stats["changed"] == 1
        assert "sport:football" in market.market_tags

    def test_every_row_in_a_slice_is_repaired_not_just_the_first(self):
        rows = [_Market(**SENATE), _Market(**NFL)]
        stats = _run(_Session(rows))

        assert stats["changed"] == 2
        assert stats["checked"] == 2


class TestTheRefusalIsTheSafetyArgument:
    def test_a_recompute_that_would_drop_the_sport_tag_is_refused(self):
        """🔴 The write that would be a regression, not a repair.

        `geopolitics` is not in `ALLOWED_TAGS["sport"]`, so the recompute emits
        no sport tag at all. Writing it would delete the row's only sport tag.
        """
        market = _Market(**GEOPOLITICS)
        session = _Session([market])

        stats = _run(session)

        assert stats["refused_would_drop_sport"] == 1
        assert stats["changed"] == 0
        assert market.market_tags == ["sport:politics"], (
            "a correct sport tag was deleted because the CLASSIFICATION is the "
            "thing that is wrong"
        )
        assert session.commits == 0, "nothing changed, so nothing should commit"

    def test_the_refusal_does_not_stop_the_slice(self):
        """THE CONTROL. A refusal that aborted the pass would strand the rest."""
        good = _Market(**SENATE)
        session = _Session([_Market(**GEOPOLITICS), good])

        stats = _run(session)

        assert stats["refused_would_drop_sport"] == 1
        assert stats["changed"] == 1
        assert "sport:politics" in good.market_tags

    def test_a_row_that_keeps_a_sport_tag_is_not_refused(self):
        """THE OTHER CONTROL: without it, refusing everything would pass above."""
        market = _Market(**SENATE)
        stats = _run(_Session([market]))

        assert stats["refused_would_drop_sport"] == 0


class TestTheReportCannotShareAZero:
    def test_a_drained_backlog_and_a_stuck_one_are_different_reports(self):
        drained = _run(_Session([], remaining=0))
        stuck = _run(_Session([], remaining=7))

        assert drained["checked"] == 0 and drained["remaining"] == 0
        assert stuck["checked"] == 0 and stuck["remaining"] == 7, (
            "an arm that cannot move its own population reports the same thing "
            "as a drained one"
        )

    def test_an_over_selected_row_is_counted_as_unchanged_not_changed(self):
        """The SQL predicate is a text match; the recompute is the authority."""
        market = _Market(
            market_id=1,
            sport_category="politics",
            # exactly what the recompute produces for this row, so the only
            # thing selecting it could be the SQL text match
            tags=["market_status:open", "source:kalshi", "sport:politics"],
        )
        session = _Session([market])

        stats = _run(session)

        assert stats["unchanged"] == 1
        assert stats["changed"] == 0
        assert session.commits == 0

    def test_one_poison_row_cannot_wipe_the_pass(self, monkeypatch):
        """Gotcha #42 — per-item try/except, healthy siblings survive."""
        good = _Market(**SENATE)
        bad = _Market(market_id=999, sport_category="politics", tags=["sport:hockey"])
        real = mod.compute_market_tags

        def _explode(**kw):
            if kw.get("source") == "poison":
                raise RuntimeError("boom")
            return real(**kw)

        bad.source = "poison"
        monkeypatch.setattr(mod, "compute_market_tags", _explode)

        stats = _run(_Session([bad, good]))

        assert stats["errors"] == 1
        assert stats["changed"] == 1, "a healthy sibling was lost to a poison row"


class TestItIsWiredAndOnItsOwnBudget:
    def test_it_does_not_share_the_starved_500_row_budget(self):
        """#4440's mechanism: the two existing arms are ~10:1 oversubscribed on
        one shared 500 ordered `updated_at DESC`. An arm added to that pool is
        starved on arrival — the #4253 defect, one column over."""
        session = _Session([])
        _run(session)

        assert session.limits == [mod.MARKET_TAG_RECONCILE_SLICE]
        assert mod.MARKET_TAG_RECONCILE_SLICE != 500

    def test_the_task_actually_calls_it(self):
        """Parsed with `ast`, not grepped: this module's docstrings name the
        function, so a source scan is satisfied by the prose ABOUT the call and
        passes with the call deleted. Today's lesson, twice over — a ship
        nothing invokes is inert and no behavioural test of a helper sees it.
        """
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(mod))
        callers = [
            fn.name
            for fn in ast.walk(tree)
            if isinstance(fn, (ast.AsyncFunctionDef, ast.FunctionDef))
            for call in ast.walk(fn)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "_reconcile_disagreeing_market_tags"
        ]
        assert "_update_event_tags_impl" in callers, (
            "#4440's reconcile arm is not called by the taxonomy task; it is inert"
        )

    @pytest.mark.asyncio
    async def test_the_task_reports_it_under_its_own_key(self):
        """The summary must carry the arm, or an operator cannot watch it drain."""
        import contextlib

        session = _Session([])

        @contextlib.asynccontextmanager
        async def _fake():
            yield session

        with pytest.MonkeyPatch.context() as mp:
            # On `mod`, not on `app.tasks.base`: the task binds the name at
            # import (`from app.tasks.base import get_task_session`), so
            # patching the source module leaves the bound name pointing at the
            # real one and the test opens a socket to a database that is not
            # there. Found the hard way, exactly once.
            mp.setattr(mod, "get_task_session", _fake)

            async def _noop_events(*a, **kw):
                return 0

            async def _noop_drain(*a, **kw):
                return {}

            mp.setattr(mod, "_update_market_tags", _noop_events)
            mp.setattr(mod, "_drain_missing_tags_oldest_first", _noop_drain)
            out = await mod._update_event_tags_impl(limit=1)

        assert "reconcile" in out
        assert out["reconcile"]["remaining"] == 0
