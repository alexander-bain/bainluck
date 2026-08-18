"""#1947 — ruling 048 arm A is necessary and NOT sufficient, proved at the delete.

Queue 364 measured every ``espn_id``-sharing event pair in a 60-day production
window: 13 of them, and at least **three join genuinely different games**.

    401816142   Dodgers @ Yankees      /   Dodgers @ Mets
    401882919   Real Sociedad @ Real Madrid   /   Real Betis @ Real Sociedad
    401856667   Ohio State @ Texas     /   Texas State @ Texas

Arm A — "a shared provider id establishes identity" — licenses deleting one of
each pair. The only thing that has ever prevented it is
``ABS(EXTRACT(EPOCH FROM (a.commence_time - b.commence_time))) < 21600``, a
constant inside ONE caller's 90-line SQL string. It is not in the invariant, it
is absent from two of the other three rails, and nothing tests it as safety
because it reads as query tuning.

So the property under test is not "the drain refuses these pairs today". It is:
**the refusal does not depend on the caller's window.** Every specimen below
hands the real caller a pair its own SELECT would have filtered out — which is
exactly what a hand-edit to that SQL, or a rail that never had the window, does.

## On the fake session, deliberately

These tests fake the TRANSPORT and nothing above it: the session answers with
rows, and every predicate, branch, refusal and destructive statement comes from
production code. That boundary is chosen on purpose, because report 364's
sharpest finding was the opposite habit — the R2 corrupt-artifact test
monkeypatched ``_load_plan``, the very function containing the bug, and was
green by construction. A test that patches past the boundary containing the bug
proves only that the code is self-consistent. The bug here would live in the
guard and in the rails' use of it, so both run for real.

The load-bearing assertion in every case is on ``session.deletes`` — what the
database was actually told to destroy.
"""

import contextlib
from datetime import datetime, timedelta, timezone

import pytest

from app.utils.event_merge_invariant import (
    MAX_ABSORPTION_SEPARATION_SECONDS,
    UncorroboratedMergeRefused,
    assert_absorbable,
    corroboration_reason,
    matchup_agrees,
)

BASE = datetime(2026, 7, 17, 23, 5, tzinfo=timezone.utc)


def _event(
    *, id, espn_id=None, external_id=None, statpal_fixture_id=None,
    home="Yankees", away="Dodgers", commence=BASE,
):
    return {
        "id": id,
        "espn_id": espn_id,
        "external_id": external_id,
        "statpal_fixture_id": statpal_fixture_id,
        "home_team_name": home,
        "away_team_name": away,
        "home_team_normalized": None,
        "away_team_normalized": None,
        "commence_time": commence,
    }


# ── the pure half: both arms, against the measured specimens ─────────────────


class TestArmAIsNotSufficient:
    """Each case is a real production pair, named by its ``espn_id``."""

    @pytest.mark.parametrize("home_a,away_a,home_b,away_b,espn", [
        ("Yankees", "Dodgers", "Mets", "Dodgers", "401816142"),
        ("Real Madrid", "Real Sociedad", "Real Sociedad", "Real Betis", "401882919"),
        ("Texas", "Ohio State", "Texas", "Texas State", "401856667"),
    ])
    def test_a_shared_id_over_different_games_is_refused(
        self, home_a, away_a, home_b, away_b, espn
    ):
        a = _event(id=1, espn_id=espn, home=home_a, away=away_a)
        b = _event(id=2, espn_id=espn, home=home_b, away=away_b)
        with pytest.raises(UncorroboratedMergeRefused) as exc:
            assert_absorbable(a, b, context="t")
        assert "DIFFERENT participants" in str(exc.value)

    def test_the_series_shape_is_refused_on_SEPARATION_not_matchup(self):
        """42.0h apart, same clubs, same id — White Sox @ Orioles, Jun 29 / Jul 1.

        Matchup agreement cannot save this one: it is two real games between the
        same two clubs. It is the specimen ``event_merge_invariant``'s own
        docstring cites, and it is why the separation arm exists at all.
        """
        a = _event(id=1, espn_id="401815951", home="Orioles", away="White Sox")
        b = _event(id=2, espn_id="401815951", home="Orioles", away="White Sox",
                   commence=BASE + timedelta(hours=42))
        assert matchup_agrees(a, b) is True
        with pytest.raises(UncorroboratedMergeRefused) as exc:
            assert_absorbable(a, b, context="t")
        assert "42.0h apart" in str(exc.value)

    def test_a_genuine_duplicate_still_absorbs(self):
        """The negative control that matters: this must NOT become a refusal.

        A guard that refuses everything is not a guard, it is an outage, and
        the drain exists because unmerged duplicates are a named P1 failure
        class. Same id, same matchup, 40 minutes apart.
        """
        a = _event(id=1, espn_id="401816999")
        b = _event(id=2, espn_id="401816999", commence=BASE + timedelta(minutes=40))
        assert corroboration_reason(a, b) is None
        assert_absorbable(a, b, context="t")  # does not raise

    def test_swapped_home_away_is_still_the_same_game(self):
        a = _event(id=1, espn_id="x", home="Yankees", away="Dodgers")
        b = _event(id=2, espn_id="x", home="Dodgers", away="Yankees")
        assert matchup_agrees(a, b) is True
        assert corroboration_reason(a, b) is None

    def test_a_row_with_no_labels_cannot_CORROBORATE(self):
        """``None`` means "no evidence", and no evidence never licenses a delete.

        This is the ``NULL == NULL`` reading one layer up, in the other
        vocabulary: a row that says nothing about who is playing has not agreed
        with anything.
        """
        a = _event(id=1, espn_id="x")
        b = _event(id=2, espn_id="x", home=None, away=None)
        assert matchup_agrees(a, b) is None
        assert corroboration_reason(a, b) is not None

    def test_the_boundary_is_the_named_constant_not_a_literal(self):
        a = _event(id=1, espn_id="x")
        inside = _event(id=2, espn_id="x", commence=BASE + timedelta(
            seconds=MAX_ABSORPTION_SEPARATION_SECONDS - 1))
        outside = _event(id=3, espn_id="x", commence=BASE + timedelta(
            seconds=MAX_ABSORPTION_SEPARATION_SECONDS + 1))
        assert corroboration_reason(a, inside) is None
        assert corroboration_reason(a, outside) is not None

    def test_the_refusal_is_catchable_as_the_invariants_own_exception(self):
        """Every rail catches ``UnanchoredMergeRefused`` and drains the rest.

        If this subclassing were dropped, a refusal would escape the per-pair
        handler and take the whole pass with it (gotcha #42) — a safety fix
        that causes an outage gets reverted, which is worse than not shipping it.
        """
        from app.utils.event_merge_invariant import UnanchoredMergeRefused

        assert issubclass(UncorroboratedMergeRefused, UnanchoredMergeRefused)


# ── the behavioural half: through the REAL caller ────────────────────────────


class _CandidateRow:
    """One row of ``_merge_duplicate_events_impl``'s candidate SELECT."""

    def __init__(self, a, b, *, snaps_a=True, snaps_b=False):
        self.id_a, self.id_b = a["id"], b["id"]
        self.ext_a, self.ext_b = a["external_id"], b["external_id"]
        self.espn_a, self.espn_b = a["espn_id"], b["espn_id"]
        self.statpal_a = a["statpal_fixture_id"]
        self.statpal_b = b["statpal_fixture_id"]
        self.has_snaps_a, self.has_snaps_b = snaps_a, snaps_b
        self.source_a = self.source_b = "odds_api"
        self.end_a = self.end_b = None
        self.htid_a = self.atid_a = self.htid_b = self.atid_b = None
        self.home_team_name = a["home_team_name"]
        self.away_team_name = a["away_team_name"]


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def mappings(self):
        return self


class _Session:
    """Candidate SELECT, then the guard's ``FOR UPDATE`` reload. Records writes."""

    def __init__(self, pair_rows, live_rows):
        self._pairs = pair_rows
        self._live = {r["id"]: r for r in live_rows}
        self.deletes: list = []
        self.updates: list = []
        self._first = True

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "DELETE FROM events" in sql:
            self.deletes.append(params)
            return _Result([])
        if "FOR UPDATE" in sql:
            wanted = {params["keep_id"], params["orphan_id"]}
            return _Result([self._live[i] for i in wanted if i in self._live])
        if sql.strip().upper().startswith("UPDATE"):
            self.updates.append((sql.split("\n")[0].strip(), params))
            return _Result([])
        if self._first:
            self._first = False
            return _Result(self._pairs)
        return _Result([])

    async def commit(self):
        pass


def _drive(monkeypatch, session):
    @contextlib.asynccontextmanager
    async def _fake():
        yield session

    import app.tasks.base as base
    monkeypatch.setattr(base, "get_task_session", lambda: _fake())


class TestThroughTheRealDrain:
    """``_merge_duplicate_events_impl``, unmodified, with a faked transport."""

    @pytest.mark.asyncio
    async def test_the_drain_does_NOT_delete_a_different_game(self, monkeypatch):
        """THE specimen. Fails on any build where the window is the only guard.

        The pair is handed to the caller directly, so its ``< 21600`` clause
        never runs — the situation #1947 describes and the situation a fourth
        rail is already in.
        """
        from app.tasks.sports import _merge_duplicate_events_impl

        a = _event(id=15199901, espn_id="401816142", external_id="odds-a",
                   home="Yankees", away="Dodgers")
        b = _event(id=15199902, espn_id="401816142",
                   home="Mets", away="Dodgers",
                   commence=BASE + timedelta(days=7))
        session = _Session([_CandidateRow(a, b)], [a, b])
        _drive(monkeypatch, session)

        result = await _merge_duplicate_events_impl(dry_run=False)

        assert session.deletes == [], (
            "the drain deleted a real game: espn_id 401816142 joins "
            "Dodgers @ Yankees and Dodgers @ Mets in production, and arm A "
            "alone called that one event"
        )
        assert result["refused_uncorroborated"] >= 1, (
            "the pair was skipped without being COUNTED as uncorroborated — a "
            "silent skip and a refusal read identically in the metrics, and "
            "this counter is what tells an operator arm A produced a collision"
        )
        assert result["refused_unanchored"] == 0, (
            "an uncorroborated refusal was filed under the arm-A counter; the "
            "two are different findings and must not share a bucket"
        )

    @pytest.mark.asyncio
    async def test_the_drain_STILL_merges_a_genuine_duplicate(self, monkeypatch):
        """The other direction, asserted in the same file (gotcha #43).

        A cap's guard tests must prove both that the bad case is refused and
        that the adjacent good case still works.
        """
        from app.tasks.sports import _merge_duplicate_events_impl

        a = _event(id=900, espn_id="401816999", external_id="odds-a")
        b = _event(id=901, espn_id="401816999",
                   commence=BASE + timedelta(minutes=40))
        session = _Session([_CandidateRow(a, b)], [a, b])
        _drive(monkeypatch, session)

        result = await _merge_duplicate_events_impl(dry_run=False)

        assert session.deletes == [{"orphan": 901}]
        assert result["merged"] == 1

    @pytest.mark.asyncio
    async def test_a_vanished_keeper_refuses_rather_than_deleting_the_survivor(
        self, monkeypatch
    ):
        """The race the caller-side check cannot see.

        If the keeper is gone by delete time, proceeding destroys the last copy
        of the game. The stale read from the candidate SELECT says both rows are
        healthy; only a re-read can know.
        """
        from app.tasks.sports import _merge_duplicate_events_impl

        a = _event(id=910, espn_id="e1", external_id="odds-a")
        b = _event(id=911, espn_id="e1", commence=BASE + timedelta(minutes=10))
        session = _Session([_CandidateRow(a, b)], [b])  # keeper 910 is gone
        _drive(monkeypatch, session)

        result = await _merge_duplicate_events_impl(dry_run=False)

        assert session.deletes == []
        assert result["refused_uncorroborated"] >= 1

    @pytest.mark.asyncio
    async def test_the_guard_reads_the_LIVE_row_not_the_candidate_row(
        self, monkeypatch
    ):
        """The whole reason it re-reads.

        The candidate SELECT saw two rows that agreed on matchup. By delete time
        the database holds a different away team on one of them — a repair, a
        correction, another rail's write. The stale values would sail through;
        the live ones must not.
        """
        from app.tasks.sports import _merge_duplicate_events_impl

        seen_a = _event(id=920, espn_id="e9", external_id="odds-a")
        seen_b = _event(id=921, espn_id="e9", commence=BASE + timedelta(minutes=5))
        live_b = dict(seen_b, away_team_name="Mets")
        session = _Session([_CandidateRow(seen_a, seen_b)], [seen_a, live_b])
        _drive(monkeypatch, session)

        result = await _merge_duplicate_events_impl(dry_run=False)

        assert session.deletes == []
        assert result["refused_uncorroborated"] >= 1


class TestTheGuardIsWiredIntoEveryDestructiveRail:
    """A predicate nothing calls is a document — the ruling this queue banks.

    ``enforce_live_requires_start`` shipped with zero callers while the surface
    it governed served four wrong cards. This asserts the same thing cannot be
    true of the guard, per rail, by name.
    """

    @pytest.mark.parametrize("module,rail", [
        ("app/tasks/sports.py", "_merge_duplicate_events_impl"),
        ("app/tasks/reconcile_unanchored_events.py", "_absorb"),
        ("app/routes/admin_events.py", "merge_duplicate_events_sql"),
        ("app/routes/admin_data_quality.py", "merge_duplicate_events"),
    ])
    def test_the_rail_calls_the_in_transaction_guard(self, module, rail):
        import ast
        import pathlib

        source = (pathlib.Path(__file__).parent.parent / module).read_text()
        tree = ast.parse(source)
        fn = next(
            (n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name == rail),
            None,
        )
        assert fn is not None, f"{rail}() no longer exists in {module}"

        # A CALL NODE, not a substring of the source.
        #
        # This assertion was written as `"assert_absorbable_now" in source` and
        # the mutant that deletes the call from `_absorb` left it GREEN — the
        # name still appeared in the docstring one line above, which I had just
        # written to explain the call. A guard test satisfied by prose ABOUT the
        # guard is the dead-oracle class this queue exists to convert, reproduced
        # inside the conversion. Found by running the mutant; kept as the reason.
        called = {
            n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", None)
            for n in ast.walk(fn) if isinstance(n, ast.Call)
        }
        assert "assert_absorbable_now" in called, (
            f"{module}:{rail}() deletes or absorbs events without CALLING the "
            "in-transaction ruling-048 guard. #1947: arm A on a stale read is "
            "not enough, and a time window in a query string is not the rule."
        )
