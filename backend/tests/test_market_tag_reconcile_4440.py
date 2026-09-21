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

## #7814 — the refusal was also catching the opposite row

A market whose column reads `tech` or `weather` is not a sport, so emitting no
sport tag is the CORRECT answer and refusing the drop pins a wrong tag in place
forever. Measured on production 2026-09-21: **23 of 23** OPEN rows standing in
this arm's population were that shape and **none** were the `table_tennis`
shape, so the refusal had become 100% of the arm's remaining work rather than a
rare safety stop. `58015857` "Will Anthropic sign the Open Weights and American
AI Leadership letter?" carried `sport:golf` — #2161's first-match-wins name scan
scoring the word "Open" — and was listed under **MORE GOLF** on the 2027 Masters
page at `/futures/61056094`.

So the refusal is now two clauses and the column decides which one a row gets.
The split keys on an ALLOWLIST of known non-sports, never on "absent from
`ALLOWED_TAGS['sport']`", so a sport the classifier learns before the tag
vocabulary does still fails safe —
`test_an_unknown_category_fails_safe_toward_the_refusal` is that guard, and
`table_tennis` moved from being this file's refusal specimen to being its own
control.
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
NFL = dict(market_id=52755820, sport_category="football", tags=["sport:baseball"])

# #7814's specimens. The refusal's TRUE safety case is a real sport the tag
# vocabulary does not carry — #4440's own filing names it: live US Open ATP
# matches misclassified `table_tennis` whose stored `sport:tennis` is the correct
# half. `geopolitics` used to stand here and no longer can; it is a known
# non-sport, which is the other clause.
TABLE_TENNIS = dict(market_id=25916882, sport_category="table_tennis", tags=["sport:tennis"])
ANTHROPIC = dict(market_id=58015857, sport_category="tech", tags=["sport:golf"])
HURRICANES = dict(market_id=25925283, sport_category="weather", tags=["sport:hockey"])
GEOPOLITICS = dict(market_id=115299, sport_category="geopolitics", tags=["sport:politics"])


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

        `table_tennis` is not in `ALLOWED_TAGS["sport"]` and is not a category we
        know to be a non-sport, so the recompute emits no sport tag at all and
        writing it would strip a marquee fixture's correct tag mid-tournament.
        """
        market = _Market(**TABLE_TENNIS)
        session = _Session([market])

        stats = _run(session)

        assert stats["refused_would_drop_sport"] == 1
        assert stats["changed"] == 0
        assert market.market_tags == ["sport:tennis"], (
            "a correct sport tag was deleted because the CLASSIFICATION is the "
            "thing that is wrong"
        )
        assert session.commits == 0, "nothing changed, so nothing should commit"

    def test_an_unknown_category_fails_safe_toward_the_refusal(self):
        """#7814's direction-of-failure control.

        The split keys on an ALLOWLIST of known non-sports, so a sport the
        classifier learns before the tag vocabulary does must still be refused.
        An implementation that keyed on "not in ALLOWED_TAGS['sport']" instead
        would pass every other test in this class and strip these.
        """
        for unknown in ("pickleball", "padel", "table_tennis"):
            market = _Market(market_id=1, sport_category=unknown, tags=["sport:tennis"])

            stats = _run(_Session([market]))

            assert stats["refused_would_drop_sport"] == 1, unknown
            assert market.market_tags == ["sport:tennis"], (
                f"{unknown} is not a known non-sport, so its tag must survive"
            )

    def test_the_refusal_does_not_stop_the_slice(self):
        """THE CONTROL. A refusal that aborted the pass would strand the rest."""
        good = _Market(**SENATE)
        session = _Session([_Market(**TABLE_TENNIS), good])

        stats = _run(session)

        assert stats["refused_would_drop_sport"] == 1
        assert stats["changed"] == 1
        assert "sport:politics" in good.market_tags

    def test_a_row_that_keeps_a_sport_tag_is_not_refused(self):
        """THE OTHER CONTROL: without it, refusing everything would pass above."""
        market = _Market(**SENATE)
        stats = _run(_Session([market]))

        assert stats["refused_would_drop_sport"] == 0


class TestANonSportColumnMeansTheTagIsTheWrongHalf:
    """#7814. The refusal above also caught the OPPOSITE row and pinned it.

    Measured on production 2026-09-21: 23 of 23 OPEN rows standing in this arm's
    population had a non-sport column and a sport tag, and none had the
    `table_tennis` shape. The refusal was the whole of the arm's remaining work.
    """

    def test_the_anthropic_market_stops_being_golf(self):
        """🔴 The reader-visible defect: an AI-policy question under MORE GOLF.

        `58015857` is classified correctly in every column (`llm_sport_category`
        = tech) and wrongly in its tags — `sport:golf`, because #2161's
        first-match-wins name scan scored the word "Open". The "More Golf" rail
        on `/futures/61056094` (2027 Masters) reads the tag, so it listed it.
        """
        market = _Market(**ANTHROPIC)
        session = _Session([market])

        stats = _run(session)

        assert stats["dropped_sport_non_sport_column"] == 1
        assert stats["refused_would_drop_sport"] == 0
        assert stats["changed"] == 1
        assert not [t for t in market.market_tags if t.startswith("sport:")], (
            "the Anthropic AI-policy market still carries a sport tag — it stays "
            "in the MORE GOLF rail's candidate base"
        )
        assert session.commits == 1

    def test_the_rest_of_the_row_survives_the_drop(self):
        """Dropping the sport tag is not licence to empty the column."""
        market = _Market(**ANTHROPIC, category="prop", source="kalshi")

        _run(_Session([market]))

        assert "category:prop" in market.market_tags
        assert "source:kalshi" in market.market_tags

    def test_every_non_sport_category_in_the_standing_population_moves(self):
        """The 23 are six distinct columns, not one. A fix that only knew `tech`
        would clear the specimen and leave nine hurricanes tagged `sport:hockey`.
        """
        rows = [
            _Market(market_id=i, sport_category=cat, tags=["sport:hockey"])
            for i, cat in enumerate(
                ("tech", "weather", "economics", "crypto", "geopolitics", "legal"), 1
            )
        ]

        stats = _run(_Session(rows))

        assert stats["dropped_sport_non_sport_column"] == 6
        assert stats["refused_would_drop_sport"] == 0
        for market in rows:
            assert not [t for t in market.market_tags if t.startswith("sport:")]

    def test_the_hurricanes_leave_the_hockey_rail(self):
        """Nine of the 23. `sport:hockey` off the Carolina Hurricanes."""
        market = _Market(**HURRICANES)

        _run(_Session([market]))

        assert "sport:hockey" not in market.market_tags

    def test_geopolitics_is_a_drop_now_and_not_a_refusal(self):
        """It stood as this file's refusal specimen until #7814. Naming the
        reversal so a reader of the diff is not left to infer it.
        """
        market = _Market(**GEOPOLITICS)

        stats = _run(_Session([market]))

        assert stats["dropped_sport_non_sport_column"] == 1
        assert stats["refused_would_drop_sport"] == 0

    def test_a_non_sport_column_that_keeps_a_tag_is_untouched_by_the_split(self):
        """THE CONTROL. `politics` is a non-sport AND an allowed tag value, so the
        recompute emits `sport:politics` and the new clause must never be reached
        — otherwise the split would be silently dropping tags it never examined.
        """
        market = _Market(**SENATE)

        stats = _run(_Session([market]))

        assert stats["dropped_sport_non_sport_column"] == 0
        assert stats["changed"] == 1
        assert "sport:politics" in market.market_tags

    def test_the_two_verdicts_never_share_a_counter(self):
        """Opposite outcomes on the same shape, reported separately or an
        operator cannot tell a repairing pass from a refusing one.
        """
        stats = _run(_Session([_Market(**ANTHROPIC), _Market(**TABLE_TENNIS)]))

        assert stats["dropped_sport_non_sport_column"] == 1
        assert stats["refused_would_drop_sport"] == 1
        assert stats["checked"] == 2


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


class TestTheNonSportSetIsDefinedOnce:
    """#7814 gave `NON_SPORT_CATEGORIES` a second reader. The polymarket copy's
    own comment says it exists because it "used to be re-declared inside the
    poller loop's function body, which is a copy waiting to disagree" — a second
    module-level copy is that defect one import further out.
    """

    def test_polymarket_reads_the_same_object_not_a_copy(self):
        from app.tasks import polymarket
        from app.utils import event_taxonomy

        assert polymarket.NON_SPORT_CATEGORIES is event_taxonomy.NON_SPORT_CATEGORIES, (
            "polymarket re-declared the set instead of importing it; the two can "
            "now drift and the taxonomy reconcile will disagree with the poller"
        )

    def test_the_categories_the_23_rows_use_are_all_in_it(self):
        from app.utils.event_taxonomy import NON_SPORT_CATEGORIES

        measured = {"tech", "weather", "economics", "crypto", "geopolitics", "legal"}
        assert measured <= NON_SPORT_CATEGORIES

    def test_a_real_sport_is_never_in_it(self):
        """If a sport ever lands here, this arm starts stripping correct tags."""
        from app.utils.event_taxonomy import ALLOWED_TAGS, NON_SPORT_CATEGORIES

        # `politics` and `entertainment` are in both by design: futures support
        # them as tag values, so the recompute keeps their tag and the split
        # never decides those rows.
        overlap = (ALLOWED_TAGS["sport"] & NON_SPORT_CATEGORIES) - {
            "politics", "entertainment",
        }
        assert overlap == set(), f"{overlap} is both an allowed sport tag and a non-sport"


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
