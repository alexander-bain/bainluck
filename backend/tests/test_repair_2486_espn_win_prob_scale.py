"""#2486 repair — the gates that decide whether a production row is touched.

The repair itself is attended and runs nowhere but `bainluck-heavy`. What is
testable here, and what actually decides whether a reader's chart gets better or
worse, is the set of pure judgements in front of the write:

  * WHICH events are in scope, and which are counted rather than repaired.
  * WHETHER a refetched ESPN series is safe to write over what is stored.
  * WHETHER the image this is running in has the corrected writer at all.
  * WHETHER the undo covers every row before anything is deleted.

Each one is a refusal, and a refusal that fails open is how a repair makes a
page worse than it found it.
"""

import importlib.util
import pathlib

import pytest

_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "scripts"
    / "repair_2486_espn_win_prob_scale.py"
)
_spec = importlib.util.spec_from_file_location("repair_2486", _PATH)
repair = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(repair)


def _row(event_id=1, espn_id="401816947", rows_stored=80, max_stored=0.0066,
         rows_above_floor=0, sport_key="baseball_mlb"):
    return {
        "event_id": event_id,
        "espn_id": espn_id,
        "commence_time": None,
        "sport_key": sport_key,
        "rows_stored": rows_stored,
        "max_stored": max_stored,
        "rows_above_floor": rows_above_floor,
    }


def _series(values):
    return [{"play_id": str(i), "seconds_left": None, "home_win_probability": v}
            for i, v in enumerate(values)]


class TestScreen:
    """Who is repaired, who is reported, who is left alone."""

    def test_a_whole_series_on_the_floor_is_the_plan(self):
        screen = repair.screen_population([_row(max_stored=0.0085)])
        assert [c.event_id for c in screen.plan] == [1]
        assert not screen.suspect and not screen.healthy and not screen.no_anchor

    def test_post_fix_data_is_never_touched(self):
        """An event backfilled after the writer fix reads like any real chart."""
        screen = repair.screen_population(
            [_row(max_stored=0.94, rows_above_floor=78)]
        )
        assert [c.event_id for c in screen.healthy] == [1]
        assert not screen.plan

    def test_a_real_series_keeps_its_genuine_lows(self):
        """🔴 THE ONE THE FIRST DRAFT GOT WRONG. The captured MLB series has 3
        of its 70 points under 2% — ESPN's own end-of-game zeroes. A screen that
        called any event with a sub-floor row "mixed" would have quarantined
        almost every healthy chart on the site, and the screen is the max for
        exactly this reason: a corrupt value and a genuine low value are the
        same number."""
        screen = repair.screen_population(
            [_row(rows_stored=70, max_stored=0.402, rows_above_floor=67)]
        )
        assert [c.event_id for c in screen.healthy] == [1]
        assert not screen.plan and not screen.suspect

    def test_an_event_mostly_on_the_floor_is_reported_not_repaired(self):
        """The only computable hint of a part-corrupt series. Reported for a
        person; a whole-series replacement is the wrong instrument for it."""
        screen = repair.screen_population(
            [_row(rows_stored=100, max_stored=0.94, rows_above_floor=40)]
        )
        assert [c.event_id for c in screen.suspect] == [1]
        assert not screen.plan

    def test_a_corrupt_event_with_no_espn_id_cannot_be_refetched(self):
        """Reported as its own bucket, not quietly folded into the plan — the
        refetch has nothing to ask ESPN for."""
        screen = repair.screen_population([_row(espn_id=None)])
        assert [c.event_id for c in screen.no_anchor] == [1]
        assert not screen.plan

    def test_the_threshold_boundary_is_not_planned(self):
        """0.02 exactly is not the 1/100 signature — dividing a [0,1] fraction
        by 100 cannot produce anything above 0.01."""
        at = repair.screen_population(
            [_row(rows_stored=80, max_stored=repair.CORRUPT_MAX,
                  rows_above_floor=79)]
        )
        assert at.healthy and not at.plan

    def test_every_event_lands_in_exactly_one_bucket(self):
        rows = [
            _row(event_id=1, max_stored=0.0066),
            _row(event_id=2, max_stored=0.94, rows_above_floor=80),
            _row(event_id=3, rows_stored=100, max_stored=0.94, rows_above_floor=40),
            _row(event_id=4, espn_id=None),
        ]
        screen = repair.screen_population(rows)
        seen = [c.event_id for bucket in screen for c in bucket]
        assert sorted(seen) == [1, 2, 3, 4]
        assert len(seen) == len(set(seen))


class TestValidateRefetch:
    """Nothing is deleted until ESPN's replacement is in hand AND believed."""

    def test_a_healthy_refetch_is_accepted(self):
        verdict = repair.validate_refetch(_series([0.271, 0.402, 0.0]), 3)
        assert verdict.ok and verdict.points == 3

    def test_an_empty_answer_is_refused(self):
        """ESPN not answering is not permission to delete (gotcha #53)."""
        assert not repair.validate_refetch([], 80).ok
        assert not repair.validate_refetch(_series([None, None]), 80).ok

    def test_a_still_flat_refetch_is_refused(self):
        """🔴 THE WRITER PRECONDITION, RE-PROVED ON LIVE DATA. If the refetched
        series still maxes below the floor, the corrected normalizer is not in
        this path and the repair would spend its undo replacing corrupt rows
        with corrupt rows."""
        verdict = repair.validate_refetch(
            _series([0.0001, 0.0066, 0.0100]), 3
        )
        assert not verdict.ok
        assert "STILL flat" in verdict.reason

    def test_a_short_series_is_refused(self):
        """A refetch that lost a third of the curve is not the same game."""
        assert not repair.validate_refetch(_series([0.5] * 50), 80).ok

    def test_a_slightly_trimmed_series_is_accepted(self):
        """ESPN does re-publish with a point or two fewer; that is not a
        different game, and refusing it would strand the event forever."""
        assert repair.validate_refetch(_series([0.5] * 76), 80).ok

    @pytest.mark.parametrize("bad", [1.5, -0.2, 101.0])
    def test_a_value_outside_zero_one_is_refused(self, bad):
        assert not repair.validate_refetch(_series([0.4, bad, 0.6]), 3).ok

    def test_points_with_no_probability_are_skipped_not_fatal(self):
        """ESPN publishes plays without a probability; they are not a reading
        and not a reason to refuse the other 79."""
        verdict = repair.validate_refetch(_series([0.4, None, 0.9]), 2)
        assert verdict.ok and verdict.points == 2


class TestTheGatesInFrontOfTheWrite:
    def test_the_app_gate_names_one_app(self):
        assert repair.app_is_permitted("bainluck-heavy")[0]
        for wrong in (None, "", "bainluck", "bainluck-staging"):
            ok, why = repair.app_is_permitted(wrong)
            assert not ok and repair.REQUIRED_APP in why

    def test_the_writer_gate_passes_on_this_tree(self):
        """This tree HAS the fix, so the gate must say so — a gate that refuses
        everything is not a gate (it would never let the repair run at all)."""
        ok, why = repair.writer_is_corrected()
        assert ok, why

    def test_the_writer_gate_refuses_a_helper_that_misbehaves(self, monkeypatch):
        """The negative control the tree cannot provide on its own: a present
        but wrong normalizer must be caught, not just an absent one."""
        import app.services.espn_api as espn_api

        monkeypatch.setattr(
            espn_api, "_normalize_win_percentage", lambda v: float(v) / 100
        )
        ok, why = repair.writer_is_corrected()
        assert not ok and "not behaving" in why

    def test_the_probes_are_the_values_the_defect_turns_on(self):
        """0.0 and 1.0 are in the probe set deliberately: a helper that divides
        at `>= 1.0`, or that refuses a genuine zero, is broken in a way the
        fraction probes alone would not catch."""
        assert 0.0 in repair.WRITER_PROBES and 1.0 in repair.WRITER_PROBES

    def test_a_full_plan_clears_the_floor(self):
        """1,253 events measured on production 2026-09-16; the floor is 1,100."""
        assert not repair.explain_small_plan(1253, 0).blocks_apply

    def test_a_drained_backlog_is_told_apart_from_a_broken_screen(self):
        """Both look like "the plan is small". Only one of them may proceed, and
        the manifest is what separates them — a bare message that changed only
        the wording of an identical refusal cost #5246 a session."""
        drained = repair.explain_small_plan(12, 1300)
        broken = repair.explain_small_plan(12, 3)
        assert not drained.blocks_apply and "DRAINING" in drained.message
        assert broken.blocks_apply and "SCREEN BROKE" in broken.message

    def test_an_empty_reconciliation_is_not_a_pass(self):
        """`all()` over an empty mapping is True, so the emptiness test is the
        whole guard: a backup check that inspected nothing must not read clean."""
        assert not repair.backup_is_exact({})
        assert repair.backup_is_exact({"missing_backup_rows": 0,
                                       "stale_backup_rows": 0})
        assert not repair.backup_is_exact({"missing_backup_rows": 0,
                                           "stale_backup_rows": 3})


class _StubResult:
    def __init__(self, rows=None, scalar=0):
        self._rows = rows or []
        self._scalar = scalar
        self.rowcount = len(self._rows)

    def fetchall(self):
        return self._rows

    def scalar_one(self):
        return self._scalar

    def scalar(self):
        return self._scalar


class _StubSession:
    """Records the statements a repair pass issues, in order.

    Not a database. The question it answers is a sequencing one — what does this
    code touch, and in what order, before it deletes anything — and that is
    decidable from the statements alone.
    """

    def __init__(self, stored_ids=(1, 2, 3), backup_clean=True, delete_returns=None):
        self.log = []
        self.committed = False
        self.rolled_back = False
        self._stored_ids = list(stored_ids)
        self._backup_clean = backup_clean
        self._delete_returns = (
            list(stored_ids) if delete_returns is None else list(delete_returns)
        )
        self._next_id = 9000

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.log.append(sql)
        if "to_regclass" in sql:
            return _StubResult(scalar=True)
        if "ORDER BY id" in sql and "win_prob_snapshots" in sql:
            return _StubResult(rows=[(i,) for i in self._stored_ids])
        if sql.strip().startswith("SELECT count(*) FROM win_prob_snapshots s"):
            return _StubResult(scalar=0 if self._backup_clean else 2)
        if sql.strip().startswith("DELETE FROM win_prob_snapshots s"):
            return _StubResult(rows=[(i,) for i in self._delete_returns])
        if "INSERT INTO win_prob_snapshots" in sql and "RETURNING" in sql:
            self._next_id += 1
            return _StubResult(scalar=self._next_id)
        return _StubResult()

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


class _StubESPN:
    def __init__(self, series):
        self._series = series
        self.calls = 0

    async def get_win_probability(self, sport_key, espn_id):
        self.calls += 1
        return self._series


def _candidate(**kw):
    base = dict(_row())
    base.update(kw)
    from datetime import datetime, timezone

    return repair.Candidate(
        event_id=base["event_id"], espn_id=base["espn_id"],
        commence_time=datetime(2026, 9, 15, 23, 10, tzinfo=timezone.utc),
        sport_key=base["sport_key"], rows_stored=base["rows_stored"],
        max_stored=base["max_stored"], rows_above_floor=base["rows_above_floor"],
    )


def _deletes(session):
    return [s for s in session.log if s.strip().startswith("DELETE FROM win_prob_snapshots s")]


class TestNothingIsDeletedBeforeAValidatedRefetch:
    """The ordering promise, which is the whole difference from #2486's own
    proposed `DELETE … WHERE backfilled` plus hope."""

    async def test_a_refused_refetch_writes_nothing_at_all(self):
        """🔴 THE ARM THAT MATTERS. ESPN answered with a still-flat series, so
        the corrupt rows stay. A repair that deleted here would trade a wrong
        chart for no chart."""
        session = _StubSession()
        service = _StubESPN(_series([0.0001, 0.0066, 0.0100]))
        outcome = await repair.repair_one_event(
            session, service, _candidate(rows_stored=3)
        )

        assert "STILL flat" in outcome["skipped"]
        assert outcome["deleted"] == 0
        assert not _deletes(session)
        assert not session.committed

    async def test_espn_not_answering_writes_nothing(self):
        session = _StubSession()
        outcome = await repair.repair_one_event(session, _StubESPN(None), _candidate())

        assert outcome["skipped"] == "espn returned no series"
        assert not session.log and not session.committed

    async def test_a_raising_fetch_costs_one_event_not_the_pass(self):
        class _Angry:
            async def get_win_probability(self, *a):
                raise RuntimeError("espn timeout")

        session = _StubSession()
        outcome = await repair.repair_one_event(session, _Angry(), _candidate())

        assert "espn fetch raised" in outcome["skipped"]
        assert not session.log

    async def test_the_happy_path_backs_up_then_swaps_then_records(self):
        session = _StubSession(stored_ids=(11, 12, 13))
        service = _StubESPN(_series([0.271, 0.402, 0.118]))
        outcome = await repair.repair_one_event(
            session, service, _candidate(rows_stored=3)
        )

        assert outcome["skipped"] == ""
        assert outcome["deleted"] == 3 and outcome["inserted"] == 3
        assert session.committed

        order = " || ".join(session.log)
        backup_at = order.index(repair.BAK_TABLE)
        delete_at = order.index("DELETE FROM win_prob_snapshots s")
        insert_at = order.index("INSERT INTO win_prob_snapshots")
        manifest_at = order.index(repair.MANIFEST_TABLE)
        assert backup_at < delete_at < insert_at < manifest_at

    async def test_an_incomplete_backup_stops_the_swap(self):
        """D51: no undo, no write."""
        session = _StubSession(backup_clean=False)
        service = _StubESPN(_series([0.271, 0.402, 0.118]))
        outcome = await repair.repair_one_event(
            session, service, _candidate(rows_stored=3)
        )

        assert "backup incomplete" in outcome["skipped"]
        assert not _deletes(session)
        assert session.rolled_back and not session.committed

    async def test_rows_that_moved_under_us_decline_the_whole_event(self):
        """The compare-and-swap found nothing to swap, so nothing is inserted
        either — an event half-replaced is worse than one not touched."""
        session = _StubSession(stored_ids=(11, 12), delete_returns=())
        service = _StubESPN(_series([0.271, 0.402]))
        outcome = await repair.repair_one_event(
            session, service, _candidate(rows_stored=2)
        )

        assert "declined the swap" in outcome["skipped"]
        assert outcome["declined"] == 2
        assert session.rolled_back and not session.committed
        assert "INSERT INTO win_prob_snapshots" not in " || ".join(session.log)


class TestTheWriteIsCompareAndSwapAndUndoable:
    """The SQL, read as the contract it is.

    These are string assertions, and that is their limit — they cannot prove
    Postgres does the right thing. They exist because each clause was put there
    by a named incident and a later edit that drops one would otherwise be
    silent.
    """

    def test_the_delete_swaps_on_the_whole_backed_up_row(self):
        """#5595: a row that moved between reconciliation and the write must be
        declined, or the undo restores a stale copy of it."""
        assert "(b.*) IS NOT DISTINCT FROM (s.*)" in repair.SQL["delete"]

    def test_the_delete_can_only_reach_backfilled_espn_rows(self):
        sql = repair.SQL["delete"]
        assert "s.source = 'espn'" in sql
        assert "game_state->>'backfilled' = 'true'" in sql

    def test_the_backup_is_refreshed_before_it_is_read(self):
        """Eviction must precede the copy: `bak_copy` skips ids already present,
        so a drifted row would otherwise never be re-staged."""
        assert "IS DISTINCT FROM" in repair.SQL["bak_evict_stale"]

    def test_the_restore_puts_rows_back_under_their_original_ids(self):
        assert "INSERT INTO win_prob_snapshots" in repair.SQL["restore_put_back"]
        assert "NOT EXISTS" in repair.SQL["restore_put_back"]

    def test_the_manifest_records_both_sides_of_the_swap(self):
        """A full-row backup says what the rows WERE; only the manifest says
        what this script DID, and the undo needs both (CERT-2439)."""
        create = repair.SQL["man_create"]
        assert "deleted_ids" in create and "inserted_ids" in create

    def test_the_population_only_sees_backfilled_espn_rows(self):
        sql = repair.SQL["population"]
        assert "w.source = 'espn'" in sql
        assert "w.game_state->>'backfilled' = 'true'" in sql
