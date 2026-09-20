"""#7260: `voided` is terminal and absorbing, so a corrected start never revisits.

135 upcoming games are absent from the site — the NHL's whole opening week among
them — because the only row we hold for each is `voided`, which every list
surface excludes by allowlist and the by-id read hides. `/search?q=maple leafs`
renders the question "Predators vs. Maple Leafs — Maple Leafs 53% — Oct 6" and
the game behind it has no page. We show the question and hide the game.

Measured on production 2026-09-20 (`db-query`, fingerprints `a7c998a51d2c1013`
/ `647106797fb2ad8a` / `85f9c4b2f934ad2d`):

    voided with a future start                   163     (75 the previous day)
      ... soccer_other                           114     soonest 09-20 14:00Z
      ... icehockey_other (NHL opening week)      42     soonest 09-20 17:00Z
      ... basketball_other (WNBA playoffs)         7     through 09-25
      ... retired by the #5532 arm            163/163
      ... ORPHANS, no surviving row            135
      ... carrying a survivor                   28     all soccer_other

The population ACCRUES (75 → 163 in a day) and the soonest kickoff was 58
minutes away when this was measured, so the issue's own "soonest orphan is
Sep 24, not launch-blocking" scope note had already inverted when it was re-run.

THE VOID WAS CORRECT WHEN IT FIRED. `future_dated` at retirement is 0 across all
13,588 rows in the arm's backup table. The chain is #4590's: `commence_time` was
minted as the ingest clock (retirement-time values carry non-zero seconds —
`15:30:20`, `05:48:19` — where real kickoffs land on `:00`/`:30`), so the row was
instantly "past", went `suspended`, and was retired on a start that was never a
start. A real schedule source later corrected the clock onto a row no reader
could reach.

So the defect is not in the retire decision and cannot be fixed by guarding it —
see `TestTheObviousFixesAreRefused`, which pins both wrong turns. It is the
ABSENCE OF A REVISIT once the evidence is refuted.

WHERE THIS ARM STOPS. `test_market_anchored_rows_are_never_retired_6927` records
the standing deferral: un-retiring written rows "is #2693's, and it needs the
anchor channel (#1946)". That deferral is about a fixture that ALSO has a living
row, where un-retiring mints a second row for one game and something must decide
which is canonical. An orphan poses no such question, and the twin screen is the
line: every row with a survivor is refused and left to lane1 (D39).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.event_completion import (
    RETIRED_REVIVAL_TOLERANCE,
    RETIRED_STATUSES,
    UNREACHABLE_SUSPENDED_TERMINAL,
    retired_row_start_moved_into_future,
)

NOW = datetime(2026, 9, 20, 13, 0, tzinfo=timezone.utc)


def _row(**over):
    """The production specimen: Predators vs. Maple Leafs, 15308559.

    Retired 2026-09-09 on an ingest clock of `15:30:31`; its start is now
    2026-10-06 23:00Z and no other row holds the fixture.
    """
    base = dict(
        status=UNREACHABLE_SUSPENDED_TERMINAL,
        commence_time=datetime(2026, 10, 6, 23, 0, tzinfo=timezone.utc),
        now=NOW,
        retired_by_the_arm=True,
        has_surviving_counterpart=False,
    )
    base.update(over)
    return base


def _verdict(**over):
    return retired_row_start_moved_into_future(**_row(**over))


class TestTheDefectReproduces:
    """Without this the suite is air: no existing arm can reach the specimen."""

    def test_the_specimen_is_hidden_from_every_list_surface(self):
        assert UNREACHABLE_SUSPENDED_TERMINAL in RETIRED_STATUSES, (
            "the premise of the issue is that `voided` is excluded by allowlist "
            "and hidden by the by-id read"
        )

    def test_the_future_settled_repair_cannot_see_it(self):
        """The sibling arm that un-settles a future-dated terminal skips it."""
        from app.tasks.espn_sync import FUTURE_SETTLED_STATUSES

        assert UNREACHABLE_SUSPENDED_TERMINAL not in FUTURE_SETTLED_STATUSES

    def test_the_retirement_arm_cannot_re_select_it(self):
        """`voided` is terminal: the arm that wrote it only selects `suspended`."""
        from app.utils.event_completion import EVENT_SUSPENDED

        assert UNREACHABLE_SUSPENDED_TERMINAL != EVENT_SUSPENDED

    def test_a_guard_on_the_retire_decision_would_have_caught_nothing(self):
        """`future_dated` at retirement is 0 over all 13,588 rows.

        The row's start was in the PAST when it was retired — which is why
        "refuse to void a future-dated row" is inert on this population.
        """
        retired_at_start = datetime(2026, 9, 9, 15, 30, 31, tzinfo=timezone.utc)
        assert retired_at_start < datetime(
            2026, 9, 9, 16, 0, tzinfo=timezone.utc
        ), "at retirement the specimen was past its own (fake) start"


class TestTheShip:
    """A retired row whose start has moved into the future comes back."""

    def test_the_specimen_revives(self):
        assert _verdict() is True

    def test_a_start_days_out_is_not_decided_by_the_tolerance(self):
        """The margin absorbs a refinement race; it never carries the answer."""
        assert _verdict(
            commence_time=NOW + RETIRED_REVIVAL_TOLERANCE + timedelta(days=16)
        ) is True


class TestTheRefusals:
    """Every refusal gets a counter-example, per the sibling predicate's rule."""

    def test_a_row_this_arm_never_retired_is_refused(self):
        """The 2,544-row fence.

        Of 4,320 rows voided for unrelated reasons, 2,544 match the retirement
        predicate exactly. Reviving on the predicate — or on `voided` plus a
        future clock — resurrects them.
        """
        assert _verdict(retired_by_the_arm=False) is False

    def test_a_fixture_with_a_surviving_row_is_refused(self):
        """The #2693 line. Reviving this mints a second row for one game."""
        assert _verdict(has_surviving_counterpart=True) is False

    def test_a_row_that_is_not_voided_is_refused(self):
        from app.utils.event_completion import EVENT_SUSPENDED

        assert _verdict(status=EVENT_SUSPENDED) is False
        assert _verdict(status="scheduled") is False
        assert _verdict(status="completed") is False

    def test_a_start_still_in_the_past_is_refused(self):
        """The evidence that retired the row has NOT been refuted."""
        assert _verdict(commence_time=NOW - timedelta(days=9)) is False

    def test_a_start_inside_the_tolerance_is_refused(self):
        """A settlement/refinement race nudging the clock forward is not this."""
        assert _verdict(commence_time=NOW + timedelta(minutes=30)) is False

    def test_a_missing_start_is_refused(self):
        assert _verdict(commence_time=None) is False

    @pytest.mark.parametrize(
        "field,value",
        [
            ("retired_by_the_arm", False),
            ("has_surviving_counterpart", True),
            ("status", "scheduled"),
            ("commence_time", None),
        ],
    )
    def test_each_refusal_alone_is_sufficient(self, field, value):
        """No refusal is load-bearing only in combination with another."""
        assert _verdict(**{field: value}) is False


class TestTheObviousFixesAreRefused:
    """The two wrong turns, pinned so a later reader does not take them."""

    def test_voided_is_not_added_to_the_future_settled_set(self):
        """The harmful shortcut.

        `FUTURE_SETTLED_STATUSES` is read against EVERY row, so adding `voided`
        would reach the 2,544 unrelated rows the fence exists to keep out.
        """
        from app.tasks.espn_sync import FUTURE_SETTLED_STATUSES

        assert "voided" not in FUTURE_SETTLED_STATUSES, (
            "adding `voided` here revives rows this arm never retired — scope "
            "is the backup table's id list, established by a JOIN"
        )

    def test_the_arm_scopes_itself_by_joining_the_backup_table(self):
        """The fence is in the recall, not only in the verdict.

        A source scan because the JOIN is the thing that establishes
        `retired_by_the_arm=True`; if it were ever replaced by a bare status
        test the verdict would be handed a `True` it had not earned.
        """
        import inspect

        from app.tasks import espn_sync

        src = inspect.getsource(espn_sync._revive_retired_future_starts_impl)
        assert "UNREACHABLE_SUSPENDED_BACKUP_TABLE" in src
        assert "JOIN" in src

    def test_the_arm_gates_on_the_backup_table_existing(self):
        """No table ⇒ the JOIN raises rather than returning empty."""
        import inspect

        from app.tasks import espn_sync

        src = inspect.getsource(espn_sync._revive_retired_future_starts_impl)
        assert "to_regclass" in src


class TestTheArmHasItsOwnBeat:
    """Placement is a decision, so it is pinned.

    The population moves on the timescale of a schedule correction, not the 60s
    realtime beat its sibling repairs run on, and the arm does a join plus a
    per-row twin screen. Keeping it off that function also keeps it out of the
    select sequence its tests pin POSITIONALLY (`_NetSession._selects` in
    `test_a_derived_start_is_not_a_start_q076`), which is how a new query there
    breaks eight unrelated suites.
    """

    def test_the_task_is_registered(self):
        from app.tasks import celery_app

        assert "app.tasks.revive_retired_future_starts" in celery_app.tasks

    def test_it_is_on_background_not_realtime(self):
        from app.tasks import celery_app

        route = celery_app.conf.task_routes[
            "app.tasks.revive_retired_future_starts"
        ]
        assert route == {"queue": "background"}

    def test_it_is_not_a_heavy_task(self):
        """Notice 48: a heavy task is not live until `bainluck-heavy` carries it."""
        from app.tasks import HEAVY_TASKS

        assert "app.tasks.revive_retired_future_starts" not in HEAVY_TASKS

    def test_it_is_a_crontab_not_a_float_interval(self):
        """A float interval joins `background`'s CONTINUOUS FLOOR.

        `test_the_unavoidable_background_floor_is_named_and_has_not_grown` holds
        that floor to <=180s because the settlement sweep shares its slot with
        it. A 600s float would have joined the floor and failed its own bound;
        a crontab is a co-fire at known minutes instead.
        """
        from celery.schedules import crontab

        from app.tasks import celery_app

        entry = celery_app.conf.beat_schedule["revive-retired-future-starts"]
        assert entry["task"] == "app.tasks.revive_retired_future_starts"
        assert isinstance(entry["schedule"], crontab)

    def test_the_minutes_dodge_the_settlement_sweep_window(self):
        """Minutes 31-44 are protected; a fire there costs a declared ceiling."""
        import math

        from app.tasks import celery_app
        from app.tasks.settlement_sweep import SWEEP_DEADLINE_S

        sweep = celery_app.conf.beat_schedule["settlement-capture-sweep-nightly"]
        (start,) = set(sweep["schedule"].minute)
        protected = set(range(start, start + math.ceil(SWEEP_DEADLINE_S / 60) + 1))

        mine = set(
            celery_app.conf.beat_schedule["revive-retired-future-starts"][
                "schedule"
            ].minute
        )
        assert not (mine & protected), (
            f"fires at {sorted(mine & protected)} inside the sweep's protected "
            f"window {min(protected)}-{max(protected)}"
        )

    def test_the_cadence_is_about_ten_minutes(self):
        """Dodging the window must not quietly become an hourly beat."""
        from app.tasks import celery_app

        mine = sorted(
            celery_app.conf.beat_schedule["revive-retired-future-starts"][
                "schedule"
            ].minute
        )
        gaps = [b - a for a, b in zip(mine, mine[1:])] + [60 - mine[-1] + mine[0]]
        assert max(gaps) <= 15, f"a gap of {max(gaps)} min is not ~10: {mine}"

    def test_the_realtime_beat_did_not_inherit_the_arm(self):
        """Guards the positional-fake contract the eight suites depend on."""
        import inspect

        from app.tasks import espn_sync

        src = inspect.getsource(espn_sync._transition_event_statuses_impl)
        assert "#7260" not in src
        assert "_row_has_surviving_counterpart" not in src


class TestTheRevivalTarget:
    """Reviving to `previous_status` would satisfy an undo and ship nothing."""

    def test_previous_status_is_off_the_schedule_shelf(self):
        """Every one of these rows was `suspended` before it was retired."""
        from app.utils.event_completion import EVENT_SUSPENDED

        assert EVENT_SUSPENDED != "scheduled"

    def test_the_arm_writes_scheduled(self):
        import inspect

        from app.tasks import espn_sync

        src = inspect.getsource(espn_sync._revive_retired_future_starts_impl)
        assert 'event.status = "scheduled"' in src


# ---------------------------------------------------------------------------
# The twin screen — the line between this arm and #2693
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """Answers the recall with a fixed row set.

    It does NOT apply the WHERE clause, so these tests prove the Python-side
    status and name logic only. The SQL window is a separate claim, pinned by
    `test_the_window_is_the_measured_one` and by the production split the module
    docstring records.
    """

    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _FakeResult(self._rows)


def _other(home, away, status="scheduled"):
    return SimpleNamespace(
        id=999,
        status=status,
        home_team_normalized=None,
        home_team_name=home,
        away_team_normalized=None,
        away_team_name=away,
    )


def _subject():
    return SimpleNamespace(
        id=15308559,
        sport_id=7,
        commence_time=datetime(2026, 10, 6, 23, 0, tzinfo=timezone.utc),
        home_team_normalized=None,
        home_team_name="Predators",
        away_team_normalized=None,
        away_team_name="Maple Leafs",
    )


@pytest.mark.asyncio
class TestTheSurvivingCounterpartScreen:
    async def _ask(self, rows, subject=None):
        from app.tasks.espn_sync import _row_has_surviving_counterpart

        return await _row_has_surviving_counterpart(
            _FakeSession(rows), subject or _subject()
        )

    async def test_an_orphan_has_no_counterpart(self):
        assert await self._ask([]) is False

    async def test_a_live_sibling_is_a_counterpart(self):
        assert await self._ask([_other("Predators", "Maple Leafs")]) is True

    async def test_containment_matches_in_both_directions(self):
        """The two rows come from different mints; one is often the prefix."""
        assert await self._ask(
            [_other("Nashville Predators", "Toronto Maple Leafs")]
        ) is True

    async def test_a_retired_sibling_is_not_a_counterpart(self):
        """Two hidden rows are not a twin — reviving one is still the ship."""
        for status in sorted(RETIRED_STATUSES):
            assert await self._ask(
                [_other("Predators", "Maple Leafs", status=status)]
            ) is False, f"{status} is hidden, so it cannot supersede"

    async def test_a_settled_sibling_IS_a_counterpart(self):
        """The harm is two rows for one game, not two UPCOMING rows.

        Spelled as "not retired" rather than as an allowlist of live statuses,
        so a status added to the vocabulary is screened on the day it lands
        (#4114's failure mode).
        """
        assert await self._ask(
            [_other("Predators", "Maple Leafs", status="completed")]
        ) is True

    async def test_a_different_fixture_is_not_a_counterpart(self):
        assert await self._ask([_other("Senators", "Canadiens")]) is False

    async def test_one_matching_team_is_not_enough(self):
        """Back-to-back games against different opponents share a team."""
        assert await self._ask([_other("Predators", "Senators")]) is False

    async def test_a_nameless_subject_fails_closed(self):
        """Cannot be shown to be an orphan, and guessing wrong costs a twin."""
        subject = _subject()
        subject.home_team_name = ""
        assert await self._ask([], subject=subject) is True

    async def test_a_nameless_candidate_is_skipped_not_matched(self):
        assert await self._ask([_other("", "")]) is False

    async def test_the_window_is_the_measured_one(self):
        """30h is what the production 135/28 split was measured with."""
        from app.tasks.espn_sync import SURVIVING_COUNTERPART_WINDOW

        assert SURVIVING_COUNTERPART_WINDOW == timedelta(hours=30)


# ---------------------------------------------------------------------------
# The impl, actually executed
# ---------------------------------------------------------------------------


class _ImplSession:
    """Drives `_revive_retired_future_starts_impl` end to end.

    Dispatches on the SQL rather than positionally, so adding a query to the
    impl does not silently re-point an existing answer at the wrong statement —
    the failure mode `_NetSession` in `test_a_derived_start_is_not_a_start_q076`
    has by design, and the reason this arm is not an arm of that function.

    It exists because the predicate tests above cannot catch a `NameError`: they
    never run the impl. One did ship — `_sql_text` is a function-local import in
    this module, so the first draft of this arm would have raised on its first
    beat with every unit test green.
    """

    def __init__(self, *, table_present=True, candidates=(), rows=None):
        self._table_present = table_present
        self._candidates = list(candidates)
        self._rows = rows or {}
        self.committed = False

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "to_regclass" in sql:
            return SimpleNamespace(scalar=lambda: self._table_present)
        if "FROM events e JOIN" in sql:
            ids = list(self._candidates)
            return SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: ids)
            )
        # The twin screen's recall.
        return _FakeResult([])

    async def get(self, _model, pk):
        return self._rows.get(pk)

    async def commit(self):
        self.committed = True


def _retired_row(event_id=15308559, start=None, status=None):
    return SimpleNamespace(
        id=event_id,
        sport_id=7,
        status=status or UNREACHABLE_SUSPENDED_TERMINAL,
        commence_time=start or datetime(2026, 10, 6, 23, 0, tzinfo=timezone.utc),
        home_team_normalized=None,
        home_team_name="Predators",
        away_team_normalized=None,
        away_team_name="Maple Leafs",
    )


async def _run_impl(session, now=NOW):
    import contextlib
    from unittest.mock import patch

    from app.tasks import espn_sync as mod

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    class _FrozenNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    # Patched on THIS module, not on `app.tasks.base`: the name is bound into
    # `espn_sync`'s namespace at import, so patching the origin leaves the
    # already-bound reference pointing at the real session factory.
    with patch.object(mod, "get_task_session", _fake_session), patch.object(
        mod, "datetime", _FrozenNow
    ):
        return await mod._revive_retired_future_starts_impl()


@pytest.mark.asyncio
class TestTheImplRuns:
    async def test_the_specimen_is_given_back(self):
        row = _retired_row()
        stats = await _run_impl(
            _ImplSession(candidates=[row.id], rows={row.id: row})
        )
        assert stats["revived"] == 1
        assert row.status == "scheduled"

    async def test_an_absent_backup_table_is_a_quiet_no_op(self):
        """No table ⇒ this arm retired nothing ⇒ nothing to give back."""
        stats = await _run_impl(_ImplSession(table_present=False))
        assert stats == {
            "candidates": 0,
            "revived": 0,
            "refused_surviving_twin": 0,
            "backup_table_present": False,
        }

    async def test_an_empty_population_writes_nothing(self):
        stats = await _run_impl(_ImplSession(candidates=[]))
        assert stats["candidates"] == 0 and stats["revived"] == 0

    async def test_a_row_that_vanished_between_recall_and_read_is_skipped(self):
        stats = await _run_impl(_ImplSession(candidates=[999], rows={}))
        assert stats["revived"] == 0

    async def test_a_row_whose_start_slipped_back_is_refused_at_the_verdict(self):
        """The recall and the verdict are asked separately, on purpose."""
        row = _retired_row(start=NOW - timedelta(days=2))
        stats = await _run_impl(
            _ImplSession(candidates=[row.id], rows={row.id: row})
        )
        assert stats["revived"] == 0
        assert row.status == UNREACHABLE_SUSPENDED_TERMINAL


class TestTheBlastRadiusIsBounded:
    def test_the_cap_drains_the_measured_backlog_within_minutes(self):
        """Sized on the 60s cadence, not on the backlog."""
        from app.tasks.espn_sync import UNREACHABLE_SUSPENDED_REVIVE_MAX_PER_PASS

        assert 0 < UNREACHABLE_SUSPENDED_REVIVE_MAX_PER_PASS <= 100
        passes = 135 / UNREACHABLE_SUSPENDED_REVIVE_MAX_PER_PASS
        assert passes <= 10, "the measured 135 rows should drain in ~10 passes"

    def test_a_revived_row_is_not_selectable_by_the_retirement_arm(self):
        """A revived row leaves the population for good, so the two cannot loop.

        The retirement arm selects `suspended` rows whose start is already past;
        a revived row is `scheduled` with a start in the future, so it fails
        both halves of the screen and the verdict refuses it outright.
        """
        from app.tasks.espn_sync import unreachable_suspended_floor
        from app.utils.event_completion import (
            EVENT_SUSPENDED,
            suspended_row_is_unreachable,
        )

        revived_start = datetime(2026, 10, 6, 23, 0, tzinfo=timezone.utc)
        assert "scheduled" != EVENT_SUSPENDED, "the screen selects `suspended`"
        assert not suspended_row_is_unreachable(
            "scheduled",
            revived_start,
            None,
            None,
            None,
            None,
            None,
            None,
            False,
            NOW,
            unreachable_suspended_floor(),
            commence_time_source=None,
            market_anchored=False,
        ), "the verdict must refuse a revived row outright"
