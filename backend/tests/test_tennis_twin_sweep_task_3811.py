"""#3811 — the twin fold runs on a clock, and its two zeros do not share a verdict.

THE SHIP THESE GUARD: a twin that forms tonight is folded tonight. The #2693
read-side fold works and was STARVED — `provenance:duplicate-of:` had exactly two
writers, an ingest-time predicate that cannot reach a pair sharing no provider id,
and a hand-run script. On 2026-09-07 a twin formed at 03:03Z, its canonical landed
at 04:35Z, and 92 minutes later `/events/15306813` — a US Open semi-final, 34 hours
out — still rendered with no markets section at all.

So these tests are NOT about the judgement. `plan_twin_tags` was correct the whole
time and `test_tennis_twin_sweep_2878.py` already pins it. These pin the four
things that were missing around it:

    Part A   the sweep is SCHEDULED, at a cadence sized against the measured race
    Part B   there is ONE implementation, not a scheduled copy of the script
    Part C   the verdict contract — "already labelled" and "the judgement stopped
             reaching the population" are both zero writes and must never share a
             verdict (gotcha #53, and the reason this task is in ENFORCED_TASKS)
    Part D   the deploy-order guard, made mechanical: no fold, no unplayed tags

🔴 Part C is the one with teeth. The obvious way to satisfy acceptance 5 — "be
loud on zero yield" — is to make every zero-write run read NOT-GREEN. On a 30
minute clock that is ninety-six false REDs a day, because the healthy steady
state IS a zero-write run. The tests below fail on both halves of that mistake.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.tasks import tennis_twin_sweep as sweep  # noqa: E402
from app.utils.task_verdict import ENFORCED_TASKS  # noqa: E402

GHOST_ID = 15306391
CANON_ID = 15306813

#: The specimen's real stamps. The ghost carries Kalshi's CLOSE time (gotcha
#: #14), which is why it is 3h off and why `_proven_duplicates`' 30-minute fence
#: could never have paired these two.
GHOST_TIME = datetime(2026, 9, 8, 18, 30, tzinfo=timezone.utc)
CANON_TIME = datetime(2026, 9, 8, 15, 30, tzinfo=timezone.utc)


class _Row:
    """A `load_rows` row — a SQLAlchemy Row, not an ORM object.

    Field names are exactly what the module's SELECT projects, so renaming a
    column in the query breaks these. That is the point.
    """

    def __init__(
        self,
        *,
        id,
        sport_key,
        home,
        away,
        at,
        hs=None,
        aws=None,
        tags="[]",
        external_id=None,
        espn_id=None,
        statpal_fixture_id=None,
    ):
        self.id = id
        self.sport_key = sport_key
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = at
        self.home_score = hs
        self.away_score = aws
        self.tags_text = tags
        self.external_id = external_id
        self.espn_id = espn_id
        self.statpal_fixture_id = statpal_fixture_id


def _ghost(**kw):
    """The Kalshi-minted row: bare tour key, no provider id, no score."""
    base = dict(id=GHOST_ID, sport_key="tennis_atp", home="Shelton",
                away="Alcaraz", at=GHOST_TIME)
    return _Row(**{**base, **kw})


def _canon(**kw):
    """The odds_api row: tournament key, all three provider ids."""
    base = dict(
        id=CANON_ID,
        sport_key="tennis_atp_us_open",
        home="Ben Shelton",
        away="Carlos Alcaraz",
        at=CANON_TIME,
        external_id="387a94ba15ee0d940a884ffd32ace827",
        espn_id="182780",
        statpal_fixture_id="2632640",
    )
    return _Row(**{**base, **kw})


def _filler(n):
    """`n` decidable pairs, so a plan can clear `MIN_EXPECTED_TAGS`.

    The floor is on the PLAN, so any test about an INCREMENTAL run needs a
    realistic backdrop of already-decided pairs or it trips the floor instead of
    testing what it meant to.
    """
    rows = []
    for i in range(n):
        gid, cid = 900000 + i * 2, 900001 + i * 2
        rows.append(_Row(id=gid, sport_key="tennis_atp", home=f"Aa{i}b",
                         away=f"Cc{i}d", at=GHOST_TIME,
                         tags=f'["provenance:duplicate-of:{cid}"]'))
        rows.append(_Row(id=cid, sport_key="tennis_wta_us_open", home=f"Xx{i} Aa{i}b",
                         away=f"Yy{i} Cc{i}d", at=CANON_TIME, espn_id=str(cid)))
    return rows


# ════════════════════════════════════════════════════════════════════════════
# A fake session — enough SQL dispatch to run the real `run_tennis_twin_sweep`
# ════════════════════════════════════════════════════════════════════════════


class _Result:
    def __init__(self, rows=(), rowcount=0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def all(self):
        return self._rows


class _Id:
    def __init__(self, id):
        self.id = id


class _FakeSession:
    """Dispatches on the SQL text so the real task body runs end to end.

    Deliberately NOT a mock of `run_tennis_twin_sweep`'s helpers: the ordering
    this has to prove — that the backup lands BEFORE the first append — is only
    observable if the real function issues the real statements. `calls` records
    every statement in order for exactly that assertion.
    """

    def __init__(self, rows, *, read_raises=False, write_fails=False,
                 write_silently_noops=False):
        self.rows = list(rows)
        self.read_raises = read_raises
        self.write_fails = write_fails
        self.write_silently_noops = write_silently_noops
        self.calls: list[str] = []
        self.tagged: set[int] = {
            r.id for r in self.rows if "duplicate-of" in (r.tags_text or "")
        }
        self.banked: list[tuple[int, int, str]] = []

    async def execute(self, clause, params=None):
        sql = " ".join(str(clause).split())
        params = params or {}
        if "FROM events e" in sql:
            self.calls.append("population")
            if self.read_raises:
                raise RuntimeError("connection reset by peer")
            if params.get("cursor", 0):
                return _Result([])
            return _Result(self.rows)
        if sql.startswith("CREATE TABLE IF NOT EXISTS"):
            self.calls.append("create_backup_table")
            return _Result()
        if sql.startswith("INSERT INTO bak_"):
            self.calls.append("bank")
            self.banked.append((params["eid"], params["cid"], params["old"]))
            return _Result(rowcount=1)
        if sql.startswith("UPDATE events"):
            self.calls.append("append_tag")
            if self.write_fails:
                raise RuntimeError("deadlock detected")
            if not self.write_silently_noops:
                self.tagged.add(params["eid"])
            return _Result(rowcount=0 if self.write_silently_noops else 1)
        if sql.startswith("SELECT id FROM events"):
            self.calls.append("verify")
            return _Result([_Id(i) for i in params["ids"] if i in self.tagged])
        raise AssertionError(f"unexpected SQL: {sql[:120]}")

    async def commit(self):
        return None

    async def rollback(self):
        return None


def _run(rows, monkeypatch, *, apply=True, fold_live=True, **kw):
    """Run the real sweep against a fake session; returns (summary, session)."""
    session = _FakeSession(rows, **kw)

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    import app.tasks.base as base

    monkeypatch.setattr(base, "get_task_session", _fake_session)
    monkeypatch.setattr(sweep, "fold_is_live", lambda: fold_live)
    summary = asyncio.run(sweep.run_tennis_twin_sweep(apply=apply))
    return summary, session


# ════════════════════════════════════════════════════════════════════════════
# Part A — it is actually scheduled, at a cadence sized against the race
# ════════════════════════════════════════════════════════════════════════════


class TestTheSweepRunsWithoutAHuman:
    """The whole defect in one sentence: the judgement only ran when a human ran it."""

    def _entry(self):
        from app.tasks import celery_app

        schedule = celery_app.conf.beat_schedule
        assert "tennis-twin-sweep" in schedule, (
            "the sweep has no beat entry — this is #3811 itself, restored"
        )
        return schedule["tennis-twin-sweep"]

    def test_the_beat_entry_points_at_the_registered_task(self):
        from app.tasks import celery_app

        entry = self._entry()
        assert entry["task"] == "app.tasks.tennis_twin_sweep"
        assert entry["task"] in celery_app.tasks, (
            "a beat entry naming an unregistered task is a schedule that raises "
            "every 30 minutes and tags nothing"
        )

    def test_it_applies_rather_than_dry_running(self):
        """A dry-run schedule ships the measurement and not the fix.

        `reconcile_unanchored_events` is scheduled dry BECAUSE its apply path
        DELETEs. This one appends a reversible label with no deleter and banks
        the prior value first, which is D51's shape.
        """
        assert self._entry()["kwargs"]["apply"] is True

    def test_the_cadence_beats_the_fastest_thing_that_can_mint_a_ghost(self):
        """Sized against the race, not guessed — acceptance 3.

        The harm window opens when the SECOND row is created and closes when this
        next runs, so cadence T bounds the double-print at T. Polymarket ingests
        hourly, so an hourly sweep only matches the fastest generator and lags
        half a generation on average.
        """
        minutes = sorted(int(m) for m in self._entry()["schedule"].minute)
        gaps = [b - a for a, b in zip(minutes, minutes[1:])] + [
            60 - minutes[-1] + minutes[0]
        ]
        assert max(gaps) <= 30, (
            f"the sweep's longest gap is {max(gaps)} min; the measured race was 92 "
            f"min and Polymarket ingests hourly, so anything above 30 gives back "
            f"the headroom this task exists to buy"
        )

    def test_it_is_enrolled_in_enforced_tasks(self):
        """Acceptance 5. Its founding defect IS the false GREEN."""
        assert "tennis_twin_sweep" in ENFORCED_TASKS


# ════════════════════════════════════════════════════════════════════════════
# Part B — one implementation, not a scheduled copy
# ════════════════════════════════════════════════════════════════════════════


class TestOneMatcherNotTwo:
    """Acceptance 1: call the same pure planner, do not reimplement the judgement.

    Ruling 048 exists to end two matchers that disagree, and the easiest way to
    create a second one is to schedule a copy of a hand-run script.
    """

    def test_the_task_delegates_the_judgement_to_the_pure_planner(self):
        import inspect

        from app.utils.tennis_twin_pairs import plan_twin_tags

        assert "plan_twin_tags" in inspect.getsource(sweep.build_plan)
        assert sweep.plan_twin_tags is plan_twin_tags

    def test_the_cli_and_the_task_share_one_object_per_helper(self):
        """Not "the same code" — the SAME OBJECT. A copy cannot pass this."""
        from scripts import repair_2878_tennis_twin_ghosts as cli

        for name in ("load_rows", "build_plan", "already_tagged_ids",
                     "plan_refusal_reason", "ensure_backup", "write_tags"):
            assert getattr(cli, name) is getattr(sweep, name), (
                f"{name} has forked between the CLI and the beat"
            )
        assert cli.BAK_TABLE == sweep.BAK_TABLE, (
            "two backup tables means the one-command undo only undoes half"
        )

    def test_the_cli_no_longer_defines_its_own_copies(self):
        """A re-export is only one implementation while nothing shadows it."""
        import inspect

        source = inspect.getsource(
            __import__("scripts.repair_2878_tennis_twin_ghosts",
                       fromlist=["x"])
        )
        for name in ("load_rows", "build_plan", "plan_refusal_reason",
                     "ensure_backup", "write_tags"):
            assert f"def {name}(" not in source, (
                f"{name} is defined again in the CLI — the fork is back"
            )


# ════════════════════════════════════════════════════════════════════════════
# Part C — the verdict contract. The two zeros.
# ════════════════════════════════════════════════════════════════════════════


class TestTheTwoZerosDoNotShareAVerdict:
    def test_the_steady_state_writes_nothing_and_reads_green(self, monkeypatch):
        """🔴 The one that stops acceptance 5 from being over-applied.

        Every pair decidable, every pair already labelled. Zero writes. This is
        ~96 runs a day and the artifact IS on disk, so it must be `complete`.
        """
        rows = _filler(30)
        summary, session = _run(rows, monkeypatch)

        assert summary["terminal"] == "complete"
        assert summary["written"] == 0
        assert summary["pairs_found"] >= sweep.MIN_EXPECTED_TAGS
        assert "append_tag" not in session.calls
        assert "already labelled" in summary["reason"]

    def test_a_plan_that_stops_reaching_the_population_is_failed(self, monkeypatch):
        """The dangerous zero. One untagged pair, and a plan far under the floor.

        This is the shape of the judgement breaking — a renamed sport key, a
        changed name column — and it must never be reported as a small quiet run.
        """
        summary, session = _run([_ghost(), _canon()], monkeypatch)

        assert summary["terminal"] == "failed"
        assert summary["written"] == 0
        assert str(sweep.MIN_EXPECTED_TAGS) in summary["reason"]
        assert "append_tag" not in session.calls, (
            "the floor must refuse BEFORE the write, not report it afterwards"
        )

    def test_the_specimen_gets_tagged_on_a_healthy_plan(self, monkeypatch):
        """The ship, end to end: the Shelton/Alcaraz ghost folds onto its canonical."""
        rows = _filler(30) + [_ghost(), _canon()]
        summary, session = _run(rows, monkeypatch)

        assert summary["terminal"] == "complete"
        assert summary["written"] == 1
        assert GHOST_ID in session.tagged
        assert CANON_ID not in session.tagged, (
            "tagging the CANONICAL hides the row we are keeping"
        )
        assert summary["undo"].endswith("restore_2878_tennis_twin_ghosts.py --apply")

    def test_the_backup_is_banked_before_the_first_append(self, monkeypatch):
        """D51 is what allows this to write unattended, so the ORDER is load-bearing."""
        rows = _filler(30) + [_ghost(), _canon()]
        _, session = _run(rows, monkeypatch)

        assert session.calls.index("bank") < session.calls.index("append_tag")
        assert session.banked == [(GHOST_ID, CANON_ID, "[]")], (
            "the undo needs the PRE-repair tag array, keyed by ghost"
        )

    def test_a_write_that_silently_does_not_land_is_partial(self, monkeypatch):
        """`rowcount` cannot tell "already tagged" from "did not land" — only a read can."""
        rows = _filler(30) + [_ghost(), _canon()]
        summary, session = _run(rows, monkeypatch, write_silently_noops=True)

        assert summary["terminal"] == "partial"
        assert summary["still_untagged"] == [GHOST_ID]
        assert "verify" in session.calls

    def test_a_write_that_raises_is_partial_and_names_the_row(self, monkeypatch):
        rows = _filler(30) + [_ghost(), _canon()]
        summary, _ = _run(rows, monkeypatch, write_fails=True)

        assert summary["terminal"] == "partial"
        assert GHOST_ID in summary["failed_ids"]

    def test_a_read_that_raises_is_failed_and_unmeasured(self, monkeypatch):
        """"I could not look" and "there was nothing to do" are opposite facts."""
        summary, _ = _run([_ghost(), _canon()], monkeypatch, read_raises=True)

        assert summary["terminal"] == "failed"
        assert summary["measured"] is False
        assert "RuntimeError" in summary["reason"]

    def test_an_empty_window_is_no_work_not_complete(self, monkeypatch):
        """A sweep over an empty population cannot vouch for anything."""
        summary, _ = _run([], monkeypatch)

        assert summary["terminal"] == "no_work"
        assert summary["rows_read"] == 0

    def test_an_already_tagged_ghost_is_left_alone(self, monkeypatch):
        """Re-tagging would be the sweep arbitrating against its own prior finding."""
        rows = _filler(30) + [
            _ghost(tags=f'["provenance:duplicate-of:{CANON_ID}"]'),
            _canon(),
        ]
        summary, session = _run(rows, monkeypatch)

        assert summary["terminal"] == "complete"
        assert summary["written"] == 0
        assert "append_tag" not in session.calls


# ════════════════════════════════════════════════════════════════════════════
# Part D — the deploy-order guard, made mechanical
# ════════════════════════════════════════════════════════════════════════════


class TestNoFoldNoUnplayedTags:
    """🔴 Acceptance 2's last clause.

    An unplayed ghost is usually the row holding the prices — Andreeva/Potapova
    was 13 markets on the ghost against 0 on its canonical. Tagging it while the
    read side is not folding does not remove a duplicate card, it removes the
    only card with prices. For the CLI that check was a human curling the API
    before `--apply`; a task on a 30-minute clock has nobody to do that.
    """

    def test_the_fold_is_live_today(self):
        """The guard is only worth having if it reads TRUE on the shipped tree."""
        assert sweep.fold_is_live() is True

    def test_it_detects_the_fold_being_unwired(self, monkeypatch):
        """Not a constant `True`. Unwire the call and the probe must say so."""
        import app.routes.events as events

        def _no_fold(*a, **kw):  # pragma: no cover - source is what is read
            return None

        monkeypatch.setattr(events, "_build_game_markets", _no_fold)
        assert sweep.fold_is_live() is False

    def test_an_unplayed_ghost_is_withheld_when_the_fold_is_gone(self, monkeypatch):
        """Withheld AND loud — a clean small run here would be the #3811 defect again."""
        rows = _filler(30) + [_ghost(), _canon()]
        summary, session = _run(rows, monkeypatch, fold_live=False)

        assert summary["fold_live"] is False
        assert summary["terminal"] == "failed"
        assert summary["withheld_unplayed"] == [GHOST_ID]
        assert "append_tag" not in session.calls
        assert "folded_event_ids" in summary["reason"]

    def test_a_settled_pair_is_unaffected_by_the_fold(self, monkeypatch):
        """The settled arm shipped and ran before the fold existed; it does not regress.

        Same two rows, one field moved — the canonical now carries a score — and
        the tag is written despite the fold being gone. Paired with the test
        above so the suite cannot be satisfied by withholding everything
        (gotcha #43).
        """
        rows = _filler(30) + [_ghost(), _canon(hs=3, aws=1)]
        summary, session = _run(rows, monkeypatch, fold_live=False)

        assert summary["terminal"] == "complete"
        assert summary["written"] == 1
        assert summary["withheld_unplayed"] == []
        assert GHOST_ID in session.tagged

    def test_unplayed_ghost_ids_reads_the_canonicals_score(self, monkeypatch):
        """The arm split is recovered from the same field `classify_pair` split on."""
        unplayed = sweep.build_plan([_ghost(), _canon()])
        settled = sweep.build_plan([_ghost(), _canon(hs=3, aws=1)])

        assert sweep.unplayed_ghost_ids(unplayed, [_ghost(), _canon()]) == {GHOST_ID}
        assert sweep.unplayed_ghost_ids(
            settled, [_ghost(), _canon(hs=3, aws=1)]
        ) == set()


# ════════════════════════════════════════════════════════════════════════════
# Part E — the diagnosis, pinned so nobody re-guesses it
# ════════════════════════════════════════════════════════════════════════════


def test_the_ingest_time_tagger_could_never_have_paired_the_specimen():
    """#3811 asked for this to be confirmed, not assumed. Read off the real rows.

    `_proven_duplicates` guards 1-3 need a shared provider id and guard 4 needs
    the two rows within `_SAME_FIXTURE_MAX_SEPARATION`. The specimen fails both,
    which is why the answer is a sweep and not a repaired predicate.
    """
    from app.services.event_registry import _SAME_FIXTURE_MAX_SEPARATION

    ghost, canon = _ghost(), _canon()

    assert not any((ghost.external_id, ghost.espn_id, ghost.statpal_fixture_id))
    assert all((canon.external_id, canon.espn_id, canon.statpal_fixture_id))

    apart = abs(canon.commence_time - ghost.commence_time)
    assert apart == timedelta(hours=3)
    assert apart > _SAME_FIXTURE_MAX_SEPARATION

    # …and the sweep's own fence, which is what makes it reachable at all.
    assert apart <= sweep.MAX_TWIN_SEPARATION
    assert sweep.build_plan([ghost, canon]).tags[0].ghost_id == GHOST_ID


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-v"]))
