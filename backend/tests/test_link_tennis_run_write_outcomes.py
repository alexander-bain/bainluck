"""The LOOP obeys the whitelist. CERT-883 FOLLOW-UP `AUTHORITY-008-WRITE-OUTCOME-BEHAVIOR-GUARD`.

`tests/test_link_tennis_write_outcomes.py` proves what `COMMITTABLE_OUTCOMES`
CONTAINS: `{WROTE, CONFIRMED}`, everything else refused, and a sixth outcome
appearing in `anchor_channel` fails the file until somebody classifies it.

That is a guard on a frozenset. It says nothing about whether
`_run_link_tennis_statpal_fixtures` still consults it. Delete the

    if outcome not in COMMITTABLE_OUTCOMES:
        await session.rollback()

branch from the loop and restore the original `if outcome == COLLISION`, and the
whitelist test goes on passing with the defect back in production — the frozenset
is still correct, it is just no longer asked. The cert named the gap exactly: the
new unit guard "proves the whitelist contents but not that the loop continues to
use it".

## what this file drives

The real `_run_link_tennis_statpal_fixtures`, over a session that records
`commit()` and `rollback()`, with `record_anchor` forced to each outcome in turn.
The assertion is transactional, not textual: **the scalar write is committed if
and only if the anchor outcome is committable**, and the fixture lands in the
bucket that matches what happened to it.

The outcomes are DISCOVERED off `anchor_channel` rather than listed, so a new one
is driven through the loop the day it is added — the whitelist test says it must
be classified, this one says the loop must act on the classification.

## why a fake session and not Postgres

The question is control flow — which branch runs, and whether the transaction is
committed or rolled back — and a fake session answers it exactly while a real one
answers it with more machinery. The statements themselves are proven against a
real server next door in `tests/integration/test_link_tennis_already_linked_pg.py`
and `..._real_postgres.py`; the fake here refuses any statement it does not
recognise BY EXACT TEXT, so a query added or reworded in the task cannot slip
through this file silently pretending to have run.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from importlib import import_module
from types import SimpleNamespace

import pytest

from app.services import anchor_channel
from app.services.statpal_api import StatPalFixture

#: The MODULE, not the Celery task of the same name.
#:
#: `app/tasks/__init__.py` registers a task called `link_tennis_statpal_fixtures`
#: as an attribute of the `app.tasks` package, which shadows the submodule: both
#: `from app.tasks import link_tennis_statpal_fixtures` and the dotted
#: `import ... as` form hand back the task object, and `monkeypatch.setattr` then
#: fails on a name the module plainly has. `import_module` reads `sys.modules`
#: and is unambiguous.
task = import_module("app.tasks.link_tennis_statpal_fixtures")

#: The fixture and the row that matches it, so every run below reaches a
#: `VERDICT_LINK` and the only thing under test is what happens at the write.
FIXTURE_ID = "2631673"
EVENT_ID = 301
START = datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc)

#: Every outcome `record_anchor` can return, read off the module rather than
#: retyped — the same discovery `test_link_tennis_write_outcomes.py` uses, so the
#: two files cannot drift apart about what the vocabulary is.
ANCHOR_OUTCOMES = sorted(
    value
    for name, value in vars(anchor_channel).items()
    if name.isupper() and isinstance(value, str) and value == name
)


def _fixture() -> StatPalFixture:
    return StatPalFixture(
        fixture_id=FIXTURE_ID,
        home_team="Botic van de Zandschulp",
        away_team="Alex de Minaur",
        start_time=START,
        status="scheduled",
        league="US Open",
    )


class FakeResult:
    def __init__(self, rows=(), rowcount=0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def fetchall(self):
        return self._rows


class RecordingSession:
    """Answers the task's three statements; counts commits and rollbacks.

    Statements are matched by EXACT text against the task's own constants. An
    unrecognised statement raises rather than returning an empty result, because
    a fake that quietly answers "no rows" to a query it does not know turns a
    real change in the task into a green test (gotcha #53: an empty answer is a
    response shape, not an absence).
    """

    def __init__(self, *, candidates, holders, update_rowcount=1):
        self._candidates = candidates
        # A SEQUENCE of answers, because the task asks twice: once up front for
        # the batch, and again after a lost race, when the whole point is that
        # the world changed underneath (CERT-895 repair). A plain list is
        # wrapped so the common case reads unchanged.
        if holders and isinstance(holders[0], tuple):
            holders = [holders]
        self._holders = list(holders) or [[]]
        self._update_rowcount = update_rowcount
        self.commits = 0
        self.rollbacks = 0
        self.updates: list[dict] = []
        self.holder_reads = 0

    async def execute(self, statement, params=None):
        sql = str(statement)
        if sql == task.CANDIDATES:
            return FakeResult(self._candidates)
        if sql == task.SCALAR_HOLDERS:
            # Last answer repeats, so a test that does not care about the
            # re-read does not have to say anything about it.
            answer = self._holders[min(self.holder_reads, len(self._holders) - 1)]
            self.holder_reads += 1
            return FakeResult(answer)
        if sql == task.SET_FIXTURE_ID:
            self.updates.append(dict(params or {}))
            return FakeResult(rowcount=self._update_rowcount)
        raise AssertionError(
            "the task executed a statement this guard does not know:\n"
            f"{sql}\nAdd it here deliberately — do not let it return nothing."
        )

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


@pytest.fixture
def drive(monkeypatch):
    """Run one pass with `record_anchor` forced to `outcome`.

    Returns `(summary, session)`.
    """

    async def _drive(
        outcome,
        *,
        candidates=None,
        holders=(),
        update_rowcount=1,
        raises=None,
    ):
        if candidates is None:
            candidates = [
                (
                    EVENT_ID,
                    "tennis_atp_us_open",
                    "Botic van de Zandschulp",
                    "Alex de Minaur",
                    START,
                    1,
                )
            ]
        session = RecordingSession(
            candidates=candidates,
            holders=holders,
            update_rowcount=update_rowcount,
        )

        @asynccontextmanager
        async def _session():
            yield session

        import app.tasks.base as task_base

        monkeypatch.setattr(task_base, "get_task_session", _session)

        service = SimpleNamespace(
            get_live_fixtures=lambda sport: _fixtures_for(sport),
            get_schedule_fixtures=lambda sport, offset: _empty(),
            close=_empty_none,
        )
        monkeypatch.setattr(task, "get_statpal_service", lambda: service)

        async def _record_anchor(*args, **kwargs):
            if raises is not None:
                raise raises
            return SimpleNamespace(outcome=outcome)

        monkeypatch.setattr(task, "record_anchor", _record_anchor)

        summary = await task._run_link_tennis_statpal_fixtures(now=START)
        return summary, session

    return _drive


async def _fixtures_for(sport):
    return [_fixture()]


async def _empty():
    return []


async def _empty_none():
    return None


class TestTheLoopCommitsOnlyWhatTheWhitelistAllows:
    @pytest.mark.parametrize("outcome", ANCHOR_OUTCOMES)
    async def test_commit_happens_exactly_when_the_outcome_is_committable(
        self, drive, outcome
    ):
        """The whole guard, in one assertion, over the discovered vocabulary.

        Restoring the original `if outcome == COLLISION: rollback / else commit`
        fails this for `NO_KEY` and `STALE_INCUMBENT` — the two that shipped a
        scalar with no anchor behind it.
        """
        summary, session = await drive(outcome)

        committable = outcome in task.COMMITTABLE_OUTCOMES
        assert session.commits == (1 if committable else 0), (
            f"{outcome}: expected {'a commit' if committable else 'no commit'}, "
            f"got {session.commits} commit(s) and {session.rollbacks} rollback(s)"
        )
        assert session.rollbacks == (0 if committable else 1)

    @pytest.mark.parametrize("outcome", ANCHOR_OUTCOMES)
    async def test_the_column_write_is_attempted_before_the_anchor_either_way(
        self, drive, outcome
    ):
        """The rollback is what makes the refusal safe, not a skipped write.

        The column goes first on purpose — it is the `IS NULL` guard that wins
        the race — so every outcome, refused or not, has already written it. If
        a refusal ever stopped rolling back, this is the write that would stand.
        """
        _, session = await drive(outcome)

        assert session.updates == [
            {"event_id": EVENT_ID, "fixture_id": FIXTURE_ID}
        ]

    @pytest.mark.parametrize("outcome", ANCHOR_OUTCOMES)
    async def test_the_fixture_lands_in_the_bucket_that_matches_what_happened(
        self, drive, outcome
    ):
        summary, _ = await drive(outcome)

        if outcome in task.COMMITTABLE_OUTCOMES:
            assert summary["linked"] == 1
            assert summary["write_refusals"] == 0
            return

        assert summary["linked"] == 0, (
            f"{outcome} refused the anchor; counting it as a link is the report "
            "that hid the original defect"
        )
        assert summary["write_refusals"] == 1
        assert summary["unmatched"] == 0, "a refusal is not a miss"

    @pytest.mark.parametrize("outcome", ANCHOR_OUTCOMES)
    async def test_a_refusal_receipt_names_the_outcome_that_caused_it(
        self, drive, outcome
    ):
        if outcome in task.COMMITTABLE_OUTCOMES:
            pytest.skip("committable outcomes write no refusal receipt")

        summary, _ = await drive(outcome)

        (receipt,) = summary["write_refusal_receipts"]
        assert receipt["outcome"] == outcome
        assert receipt["event_id"] == EVENT_ID
        assert receipt["statpal_id"] == FIXTURE_ID, (
            "a refusal nobody can trace back to a fixture is not a finding"
        )

    async def test_a_collision_is_counted_twice_on_purpose(self, drive):
        """It is both a refused write and the duplicate-id signal ruling 048 wants."""
        summary, _ = await drive(anchor_channel.COLLISION)

        assert summary["write_refusals"] == 1
        assert summary["collisions"] == 1

    @pytest.mark.parametrize(
        "outcome", [o for o in ANCHOR_OUTCOMES if o != anchor_channel.COLLISION]
    )
    async def test_no_other_refusal_inflates_the_collision_count(
        self, drive, outcome
    ):
        summary, _ = await drive(outcome)

        assert summary["collisions"] == 0


class TestTheRefusalsThatAreNotAnchorOutcomes:
    async def test_losing_the_column_race_rolls_back_and_re_reads_the_pair(
        self, drive
    ):
        """`UPDATE ... WHERE statpal_fixture_id IS NULL` touched no row.

        CERT-895 repair. Another pass claimed the column between our candidate
        query and our write. This used to count `already_linked` on the spot —
        asserting a pair nobody had looked at. Now the pair is RE-READ after the
        rollback; here the winner finished the job, so it really is a link.
        """
        summary, session = await drive(
            anchor_channel.WROTE,
            update_rowcount=0,
            holders=[
                [],  # the up-front batch read: nobody held it yet
                [(FIXTURE_ID, 777, "tennis_atp_us_open", f"tennis:{FIXTURE_ID}")],
            ],
        )

        assert session.commits == 0
        assert session.rollbacks == 1
        assert summary["linked"] == 0
        assert summary["already_linked"] == 1
        assert summary["unpaired"] == 0
        assert session.holder_reads == 2, (
            "the pair must be asked for a SECOND time after the race is lost — "
            "the first answer is known to be out of date, that is what losing means"
        )

    async def test_losing_the_race_to_a_half_link_is_not_counted_as_linked(
        self, drive
    ):
        """The winner wrote the scalar and left no anchor.

        Counting this as `already_linked` — which is what the unconditional
        increment did — reports a healthy pass over a row that is broken in
        exactly the way this whole ship exists to surface.
        """
        summary, session = await drive(
            anchor_channel.WROTE,
            update_rowcount=0,
            holders=[[], [(FIXTURE_ID, 777, "tennis_atp_us_open", None)]],
        )

        assert session.commits == 0
        assert summary["already_linked"] == 0
        assert summary["unpaired"] == 1
        assert summary["unpaired_receipts"][0]["state"] == task.PRIOR_UNANCHORED

    async def test_losing_the_race_to_a_writer_that_then_rolled_back(self, drive):
        """Nobody holds the id on the re-read.

        The winner claimed the column and then refused its own anchor, so it
        rolled the scalar back too. We lost a race to a pass that gave up. That
        is neither a link nor a state any counter had a name for, so it gets
        one rather than being folded into a success.
        """
        summary, session = await drive(
            anchor_channel.WROTE, update_rowcount=0, holders=[[], []]
        )

        assert session.commits == 0
        assert summary["already_linked"] == 0
        assert summary["unpaired"] == 1
        assert summary["unpaired_receipts"][0]["state"] == task.PRIOR_VANISHED

    async def test_a_raising_anchor_write_rolls_back_and_is_receipted(
        self, drive
    ):
        """One bad row never wipes the pass (gotcha #42) — but it is not silent."""
        summary, session = await drive(
            None, raises=RuntimeError("anchor channel exploded")
        )

        assert session.commits == 0
        assert session.rollbacks == 1
        assert summary["linked"] == 0
        (receipt,) = summary["unmatched_receipts"]
        assert "anchor channel exploded" in receipt["error"]


class TestTheLoopBranchesOnTheNewPriorState:
    """CERT-883 FOLLOW-UP `AUTHORITY-008-PAIR-AWARE-ALREADY-LINKED`, at run level.

    `classify_prior` is proved pure next door. What is proved here is that the
    loop reads its `state` rather than the truthiness of the answer — the exact
    shape of the old bug, where any holder at all meant "linked".
    """

    #: No candidate row, so the fixture reaches the UNMATCHED branch, which is
    #: where the prior lookup is consulted.
    NO_CANDIDATES: list = []

    async def test_a_paired_prior_is_a_link_and_writes_nothing(self, drive):
        summary, session = await drive(
            anchor_channel.WROTE,
            candidates=self.NO_CANDIDATES,
            holders=[
                (FIXTURE_ID, EVENT_ID, "tennis_atp_us_open", f"tennis:{FIXTURE_ID}")
            ],
        )

        assert summary["already_linked"] == 1
        assert summary["unpaired"] == 0
        assert summary["unmatched"] == 0
        assert session.updates == [], "an already-linked fixture is not rewritten"

    async def test_a_half_linked_prior_is_reported_not_counted_as_linked(
        self, drive
    ):
        """The scalar is there, the anchor is not. This is the regression.

        Before the pair check, this run reported `already_linked: 1` — a healthy
        pass with a broken row inside it, on every pass, forever.
        """
        summary, _ = await drive(
            anchor_channel.WROTE,
            candidates=self.NO_CANDIDATES,
            holders=[(FIXTURE_ID, EVENT_ID, "tennis_atp_us_open", None)],
        )

        assert summary["already_linked"] == 0
        assert summary["unpaired"] == 1
        (receipt,) = summary["unpaired_receipts"]
        assert receipt["state"] == task.PRIOR_UNANCHORED
        assert receipt["event_id"] == EVENT_ID
        assert receipt["statpal_id"] == FIXTURE_ID

    async def test_a_cross_sport_holder_leaves_the_fixture_reported(self, drive):
        summary, _ = await drive(
            anchor_channel.WROTE,
            candidates=self.NO_CANDIDATES,
            holders=[(FIXTURE_ID, 999, "baseball_mlb", None)],
        )

        assert summary["already_linked"] == 0
        assert summary["unpaired"] == 1
        assert summary["unpaired_receipts"][0]["state"] == task.PRIOR_FOREIGN_SPORT

    async def test_a_half_link_plus_a_matching_candidate_writes_nothing(
        self, drive
    ):
        """🔴 CERT-895's finding, as a regression. The one that mattered.

        The prior check used to live INSIDE the `VERDICT_UNMATCHED` arm, on the
        reasoning that a fixture we already hold cannot have a candidate —
        `CANDIDATES` filters `statpal_fixture_id IS NULL`. True of the HOLDER;
        silent about every other row.

        Here event 301 holds `2631673` with no anchor, and event 302 is a
        DIFFERENT row matching the same two players inside the window. The loop
        reached `VERDICT_LINK`, never asked about the holder, and wrote the
        scalar onto 302 — manufacturing the two-rows-for-one-id duplicate this
        task's new job is to REPORT, and reporting it as `linked: 1`.
        """
        summary, session = await drive(
            anchor_channel.WROTE,
            candidates=[
                (
                    302,
                    "tennis_atp_us_open",
                    "Botic van de Zandschulp",
                    "Alex de Minaur",
                    START,
                    1,
                )
            ],
            holders=[(FIXTURE_ID, 301, "tennis_atp_us_open", None)],
        )

        assert session.updates == [], (
            "the task wrote the scalar onto a SECOND row while the first still "
            "held it — it manufactured the duplicate it exists to report"
        )
        assert session.commits == 0
        assert summary["linked"] == 0
        assert summary["unpaired"] == 1
        assert summary["unpaired_receipts"][0]["state"] == task.PRIOR_UNANCHORED
        assert summary["unpaired_receipts"][0]["event_id"] == 301, (
            "the receipt must name the row that HOLDS the id, not the candidate "
            "we declined to write"
        )

    async def test_a_paired_prior_plus_a_matching_candidate_writes_nothing(
        self, drive
    ):
        """Same shape, healthy holder. Still no second write.

        A genuinely-linked fixture whose players also match some other row is
        the commonest way the above would fire in production — and linking the
        second row would break a working link's uniqueness to fix nothing.
        """
        summary, session = await drive(
            anchor_channel.WROTE,
            candidates=[
                (
                    302,
                    "tennis_atp_us_open",
                    "Botic van de Zandschulp",
                    "Alex de Minaur",
                    START,
                    1,
                )
            ],
            holders=[
                (FIXTURE_ID, 301, "tennis_atp_us_open", f"tennis:{FIXTURE_ID}")
            ],
        )

        assert session.updates == []
        assert session.commits == 0
        assert summary["linked"] == 0
        assert summary["already_linked"] == 1
        assert summary["unpaired"] == 0

    async def test_a_cross_sport_holder_blocks_the_write_too(self, drive):
        """An NFL row holding the integer must not license a tennis write.

        This is the arm where refusing is arguable — the tennis fixture really
        is unlinked. It is refused anyway: writing would put the same scalar on
        two rows in two sports, which is strictly harder to diagnose later than
        the reported collision. D35 — file it, do not resolve it.
        """
        summary, session = await drive(
            anchor_channel.WROTE,
            candidates=[
                (
                    302,
                    "tennis_atp_us_open",
                    "Botic van de Zandschulp",
                    "Alex de Minaur",
                    START,
                    1,
                )
            ],
            holders=[(FIXTURE_ID, 999, "baseball_mlb", None)],
        )

        assert session.updates == []
        assert summary["linked"] == 0
        assert summary["unpaired"] == 1
        assert summary["unpaired_receipts"][0]["state"] == task.PRIOR_FOREIGN_SPORT

    async def test_a_fixture_nobody_holds_is_still_an_ordinary_miss(self, drive):
        """The bucket that must NOT grow.

        A genuine miss is the signal this whole classification exists to protect;
        if it drifted into `unpaired` the report would be quieter, not truer.
        """
        summary, _ = await drive(
            anchor_channel.WROTE, candidates=self.NO_CANDIDATES, holders=[]
        )

        assert summary["unmatched"] == 1
        assert summary["unpaired"] == 0
        assert summary["already_linked"] == 0


class TestTheDarkArmStillWritesNothing:
    async def test_apply_false_commits_nothing_and_counts_the_plan(
        self, monkeypatch
    ):
        """`apply=False` must not reach the write path at all.

        Asserted here rather than assumed because every other test in this file
        drives the write path, and a guard suite that only ever runs the arm that
        writes cannot notice the day the dark arm starts writing too.
        """
        session = RecordingSession(
            candidates=[
                (
                    EVENT_ID,
                    "tennis_atp_us_open",
                    "Botic van de Zandschulp",
                    "Alex de Minaur",
                    START,
                    1,
                )
            ],
            holders=[],
        )

        @asynccontextmanager
        async def _session():
            yield session

        import app.tasks.base as task_base

        monkeypatch.setattr(task_base, "get_task_session", _session)
        monkeypatch.setattr(
            task,
            "get_statpal_service",
            lambda: SimpleNamespace(
                get_live_fixtures=lambda sport: _fixtures_for(sport),
                get_schedule_fixtures=lambda sport, offset: _empty(),
                close=_empty_none,
            ),
        )

        async def _must_not_be_called(*args, **kwargs):
            raise AssertionError("the dark arm wrote an anchor")

        monkeypatch.setattr(task, "record_anchor", _must_not_be_called)

        summary = await task._run_link_tennis_statpal_fixtures(
            apply=False, now=START
        )

        assert summary["linked"] == 1, "the plan still counts what it would link"
        assert session.updates == []
        assert session.commits == 0


class TestTheWindowThePassAsksFor:
    async def test_the_candidate_window_is_built_around_the_fixture_start(
        self, monkeypatch
    ):
        """Guards the one thing the fake cannot check by matching text.

        `RecordingSession` matches statements exactly but ignores their params,
        so a window computed from the wrong instant would still return the seeded
        candidate here. Asserted directly instead.
        """
        seen: list[dict] = []

        class _Session(RecordingSession):
            async def execute(self, statement, params=None):
                if str(statement) == task.CANDIDATES:
                    seen.append(dict(params or {}))
                return await super().execute(statement, params)

        session = _Session(candidates=[], holders=[])

        @asynccontextmanager
        async def _session():
            yield session

        import app.tasks.base as task_base

        monkeypatch.setattr(task_base, "get_task_session", _session)
        monkeypatch.setattr(
            task,
            "get_statpal_service",
            lambda: SimpleNamespace(
                get_live_fixtures=lambda sport: _fixtures_for(sport),
                get_schedule_fixtures=lambda sport, offset: _empty(),
                close=_empty_none,
            ),
        )

        await task._run_link_tennis_statpal_fixtures(now=START)

        (window,) = seen
        assert window["window_start"] == START - task.MATCH_WINDOW
        assert window["window_end"] == START + task.MATCH_WINDOW
        assert task.MATCH_WINDOW == timedelta(hours=36)
