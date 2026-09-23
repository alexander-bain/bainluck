"""The void fact RETIRES the postponed fixture — #7035, CERT-3326's repair.

WHY THIS FILE EXISTS — CERT-3326 (BLOCK, 2026-09-23 05:35Z)
------------------------------------------------------------

The previous presentation shipped a capture that reaches the already-resolved
families and stamps ``market_metadata.venue_voided``. The cert refused it, and
the finding was right:

    "The declared TRUTH ship remains false because the SHA has no runtime
    consumer of that fact outside the capture task: ``event_completion.py``, its
    ``espn_sync.py`` caller, and served routes never read it. ... event 15312871
    therefore remains suspended/served and its card still says 'No result
    reported'."

So the subject here is the CONSUMER, and the chain it completes:

    capture writes ``venue_voided``
      → the retirement screen selects the row
      → ``venue_voided_row_is_retirable`` says yes
      → the arm writes ``UNREACHABLE_SUSPENDED_TERMINAL``
      → every user-facing read already refuses that word

The middle three links are guarded here and, behaviourally against a real
Postgres, in ``tests/integration/test_venue_void_retirement_pg.py`` — that file
seeds the specimen, runs the real arm and reads the row's status back, which is
the only check that can tell a screen that selects the specimen from one that
selects nothing. The last link is guarded by
``tests/test_a_retired_row_is_off_every_user_facing_read.py``, which already
proves ``voided`` is off every list surface and 410s on the by-id route; the
arms below say that the word this arm writes is that word, so the two compose
rather than duplicating.

🔴 THE FINDING THAT SHAPED THE DESIGN, AND IT IS EXECUTABLE BELOW
-----------------------------------------------------------------

The obvious repair — teach ``suspended_row_is_unreachable`` a "the market door
is shut" companion — is INERT ON THE NAMED SPECIMEN, and ``TestWhyTheSibling
CannotDoThis`` runs the real predicate to prove it rather than asserting it in
prose. Event 15312871 is ``soccer_spain_la_liga``, one of the 26 keys of
``ESPN_SPORT_MAPPING``, so ``anchor_acquirable`` refuses it and the sibling
caller's ``sport_id.notin_(espn_covered_ids)`` screen refuses it again — on top
of the market anchor. Opening the market door alone leaves the card exactly
where it is; opening the ESPN door too would widen a rule that retired 13,595
rows in five days, in order to move four. Hence a second warrant with its own
population, and a sibling that is not touched by one row.

MEASURED BEFORE THE PREDICATE WAS WRITTEN (production, 2026-09-23)
-------------------------------------------------------------------

* 93 suspended events carry markets that are ALL Kalshi-and-resolved with
  nothing graded; **0 of them carry a score and 0 carry a ``completed_at``**;
* the arm's own screen — those, past the 96h floor — is **30 rows**;
* 15 of the candidates sit inside the capture's 14-day band as well, and exactly
  one of those 15 is in an ESPN-covered sport: the named specimen;
* at the venue, a 14-ticker sample of this population answered **4 voided / 10
  graded**, which is why the rule is "every market voided" and not "any".
"""

import inspect

import pytest

from app.tasks.espn_sync import (
    UNREACHABLE_SUSPENDED_BACKUP_DDL,
    UNREACHABLE_SUSPENDED_BACKUP_TABLE,
    VENUE_VOIDED_SUSPENDED_MAX_PER_PASS,
    _retire_venue_voided_suspended_rows,
    unreachable_suspended_floor,
)
from app.utils.event_completion import (
    EVENT_SUSPENDED,
    RETIRED_STATUSES,
    UNREACHABLE_SUSPENDED_TERMINAL,
    is_retired_event_status,
    suspended_row_is_unreachable,
    venue_voided_row_is_retirable,
)
from app.utils.kalshi_resolution_window import (
    KALSHI_MARKET_SOURCE,
    KALSHI_RESOLVED_STATUS,
    VENUE_VOID_CHECKED_METADATA_KEY,
    VENUE_VOIDED_METADATA_KEY,
)

import datetime as dt

UTC = dt.timezone.utc

#: Fixed, and every case OFFSETS from it — gotcha #44. No arm in this file may
#: contain an `if` on the clock.
NOW = dt.datetime(2026, 9, 23, 6, 0, tzinfo=UTC)

FLOOR = unreachable_suspended_floor()

#: The production specimen, id for id: Levante v Bilbao, postponed Sep 16, four
#: Kalshi families all `resolved` and all ungraded, event still `suspended`.
SPECIMEN_EVENT = 15312871
SPECIMEN_MARKETS = (60481773, 60636796, 60636798, 60636800)


def _row(**over):
    """The specimen's shape as the verdict sees it. One keyword per case."""
    base = dict(
        status=EVENT_SUSPENDED,
        commence_time=NOW - FLOOR - dt.timedelta(hours=1),
        home_score=None,
        away_score=None,
        completed_at=None,
        now=NOW,
        floor=FLOOR,
        every_market_venue_voided=True,
        has_graded_outcome=False,
    )
    base.update(over)
    return base


def _verdict(**over):
    kwargs = _row(**over)
    return venue_voided_row_is_retirable(
        kwargs.pop("status"),
        kwargs.pop("commence_time"),
        kwargs.pop("home_score"),
        kwargs.pop("away_score"),
        kwargs.pop("completed_at"),
        kwargs.pop("now"),
        kwargs.pop("floor"),
        **kwargs,
    )


# =============================================================================
# Part 0 — why the sibling predicate could not be widened into this.
# =============================================================================


class TestWhyTheSiblingCannotDoThis:
    """The design justification, run rather than asserted in a comment.

    If either arm here ever goes green in the other direction, the second
    warrant has become unnecessary and this file should be deleted, not patched.
    """

    @staticmethod
    def _sibling(**over):
        base = dict(
            status=EVENT_SUSPENDED,
            commence_time=NOW - FLOOR - dt.timedelta(hours=1),
            external_id=None,
            espn_id=None,
            statpal_fixture_id=None,
            home_score=None,
            away_score=None,
            completed_at=None,
            # `soccer_spain_la_liga` IS in ESPN_SPORT_MAPPING — this is the
            # specimen's real value, not a worst case.
            anchor_acquirable=True,
            now=NOW,
            floor=FLOOR,
        )
        base.update(over)
        return suspended_row_is_unreachable(
            base.pop("status"),
            base.pop("commence_time"),
            base.pop("external_id"),
            base.pop("espn_id"),
            base.pop("statpal_fixture_id"),
            base.pop("home_score"),
            base.pop("away_score"),
            base.pop("completed_at"),
            base.pop("anchor_acquirable"),
            base.pop("now"),
            base.pop("floor"),
            commence_time_source="kalshi",
            market_anchored=base.pop("market_anchored", True),
        )

    def test_the_sibling_refuses_the_specimen_today(self):
        assert self._sibling() is False

    def test_opening_only_the_market_door_still_refuses_it(self):
        """The repair the directive sketched, measured inert on the specimen.

        Even granting the market door — pretending `market_anchored=False` the
        way a `_kalshi_market_door_is_shut` companion would — the row is STILL
        refused, because `anchor_acquirable` is the second hold. This is the
        arm that says a companion predicate would have shipped a green guard and
        an unchanged card.
        """
        assert self._sibling(market_anchored=False) is False

    def test_the_specimens_sport_really_is_espn_covered(self):
        """Not a stipulation: the mapping is read.

        `anchor_acquirable=True` above is only honest if La Liga is in the list
        the caller resolves to sport ids. If ESPN coverage ever drops it, the
        two arms above stop meaning what they say and this one goes red first.
        """
        from app.tasks.config import ESPN_SPORT_MAPPING

        assert "soccer_spain_la_liga" in ESPN_SPORT_MAPPING

    def test_the_second_warrant_retires_what_the_sibling_refuses(self):
        """The whole point, in one line: same row, different question."""
        assert self._sibling() is False
        assert _verdict() is True


# =============================================================================
# Part 1 — the verdict.
# =============================================================================


class TestTheVerdictRetiresTheSpecimen:
    def test_the_specimen_shape_is_retirable(self):
        assert _verdict() is True

    def test_one_second_past_the_floor_qualifies(self):
        assert _verdict(
            commence_time=NOW - FLOOR - dt.timedelta(seconds=1)
        ) is True

    def test_two_years_deep_still_qualifies(self):
        assert _verdict(commence_time=NOW - dt.timedelta(days=730)) is True


class TestTheRefusals:
    """One case per refusal, each differing from the specimen in ONE field.

    🔴 A control that differs in two screens proves neither — last session's
    sweep reported a screen SURVIVED because its control was refused by a
    different clause anyway. Every case below moves exactly one key of `_row`.
    """

    def test_a_market_the_capture_has_not_answered_refuses(self):
        assert _verdict(every_market_venue_voided=False) is False

    def test_a_graded_outcome_of_ours_refuses(self):
        """The contradiction test. A winner says a result WAS reported."""
        assert _verdict(has_graded_outcome=True) is False

    @pytest.mark.parametrize("field", ["home_score", "away_score"])
    def test_any_score_refuses(self, field):
        assert _verdict(**{field: 2}) is False

    def test_a_zero_score_refuses_and_is_not_read_as_falsy(self):
        """0-0 is a played draw, and `if score:` would retire it."""
        assert _verdict(home_score=0, away_score=0) is False

    def test_a_completed_at_refuses(self):
        assert _verdict(completed_at=NOW - dt.timedelta(hours=2)) is False

    @pytest.mark.parametrize(
        "status", ["scheduled", "live", "completed", "closed", "voided", "merged"]
    )
    def test_only_suspended_is_judged(self, status):
        """THE PLAYED CONTROL. `completed` is in here by name: on production,
        2,843 completed events hold resolved rows with no graded leg — "played,
        not graded yet" — identical to this population on every other axis."""
        assert _verdict(status=status) is False

    def test_a_row_with_no_clock_is_refused(self):
        assert _verdict(commence_time=None) is False

    def test_a_row_still_inside_the_floor_is_refused(self):
        assert _verdict(commence_time=NOW - FLOOR + dt.timedelta(hours=1)) is False

    def test_the_whole_margin_is_a_refusal_band(self):
        """The floor is not decoration: a row one minute short of it is refused,
        so a `>=`/`>` slip or a dropped margin changes an answer here."""
        assert _verdict(commence_time=NOW - FLOOR + dt.timedelta(minutes=1)) is False
        assert _verdict(commence_time=NOW - FLOOR - dt.timedelta(minutes=1)) is True


class TestTheFlagsFailClosed:
    """Both keyword arguments are REQUIRED and tested against a literal.

    The sibling's `market_anchored` is written this way so "the caller is out of
    date" cannot look like "the row is inert". Same shape, same reason: a stale
    call site must raise, and a non-boolean must refuse.
    """

    @pytest.mark.parametrize(
        "missing", ["every_market_venue_voided", "has_graded_outcome"]
    )
    def test_a_caller_that_does_not_ask_gets_a_typeerror(self, missing):
        kwargs = _row()
        kwargs.pop(missing)
        with pytest.raises(TypeError):
            venue_voided_row_is_retirable(
                kwargs.pop("status"),
                kwargs.pop("commence_time"),
                kwargs.pop("home_score"),
                kwargs.pop("away_score"),
                kwargs.pop("completed_at"),
                kwargs.pop("now"),
                kwargs.pop("floor"),
                **kwargs,
            )

    @pytest.mark.parametrize("truthy", [1, "true", "yes", [1]])
    def test_a_truthy_non_boolean_void_flag_refuses(self, truthy):
        """`is not True`, not `if not x`. A string `"true"`, a `1`, or the
        timestamp the NEGATIVE stamp writes are all truthy and none of them is
        "the venue declined to grade this"."""
        assert _verdict(every_market_venue_voided=truthy) is False

    @pytest.mark.parametrize("falsy", [0, "", None, []])
    def test_a_falsy_non_boolean_graded_flag_refuses(self, falsy):
        """`is not False` on the other side, for the mirror reason: a read that
        could not answer must stop a retirement, not permit one."""
        assert _verdict(has_graded_outcome=falsy) is False

    def test_both_flags_are_keyword_only_with_no_default(self):
        sig = inspect.signature(venue_voided_row_is_retirable)
        for name in ("every_market_venue_voided", "has_graded_outcome"):
            param = sig.parameters[name]
            assert param.kind is inspect.Parameter.KEYWORD_ONLY, name
            assert param.default is inspect.Parameter.empty, name


# =============================================================================
# Part 2 — the bind: the consumer reads the name the capture writes.
# =============================================================================


class TestTheConsumerAndTheCaptureShareOneVocabulary:
    """The seam CERT-3326 said was missing, pinned in both directions.

    The capture spells its key inside a SQL string literal, where no importer
    can see it. So the constant is the reader's name for it and these arms
    assert the capture's statements CONTAIN it — a check that reddens if either
    end is renamed, which two literals cannot do.
    """

    @staticmethod
    def _sweep():
        from app.tasks import kalshi_resolution_sweep as sweep

        return sweep

    def test_the_capture_writes_the_key_the_consumer_reads(self):
        assert VENUE_VOIDED_METADATA_KEY in self._sweep().VOID_UPDATE_SQL

    def test_the_negative_stamp_is_a_different_key(self):
        """"We asked and it graded" must never satisfy "it voided"."""
        sweep = self._sweep()
        assert VENUE_VOID_CHECKED_METADATA_KEY != VENUE_VOIDED_METADATA_KEY
        assert VENUE_VOID_CHECKED_METADATA_KEY in sweep.VOID_CHECKED_UPDATE_SQL
        assert VENUE_VOIDED_METADATA_KEY not in sweep.VOID_CHECKED_UPDATE_SQL

    def test_the_capture_is_keyed_on_the_same_source_and_status(self):
        """The consumer's screen selects `kalshi` + `resolved` rows. If the
        capture's own selection ever stopped covering that pair, the consumer
        would be screening a population nothing stamps."""
        select_sql = self._sweep().RESOLVED_VOID_SELECT_SQL
        assert f"'{KALSHI_MARKET_SOURCE}'" in select_sql
        assert f"'{KALSHI_RESOLVED_STATUS}'" in select_sql

    def test_the_capture_screens_on_both_stamps_so_the_row_drops_out(self):
        select_sql = self._sweep().RESOLVED_VOID_SELECT_SQL
        assert VENUE_VOIDED_METADATA_KEY in select_sql
        assert VENUE_VOID_CHECKED_METADATA_KEY in select_sql


# =============================================================================
# Part 3 — the arm spends the verdict, and the terminal readers already hide.
# =============================================================================


class TestTheArmIsWiredToTheVerdict:
    @staticmethod
    def _src():
        return inspect.getsource(_retire_venue_voided_suspended_rows)

    def test_the_arm_calls_the_shared_verdict(self):
        assert "venue_voided_row_is_retirable(" in self._src()

    def test_the_arm_writes_the_shared_terminal_constant(self):
        src = self._src()
        assert "UNREACHABLE_SUSPENDED_TERMINAL" in src
        assert '"voided"' not in src and "'voided'" not in src

    def test_the_arm_backs_up_before_it_writes(self):
        """D51's ordering as code. The INSERT must precede the status write in
        the source, because they share a transaction and the raise is the
        guard."""
        src = self._src()
        assert src.index("INSERT INTO") < src.index(
            "event.status = UNREACHABLE_SUSPENDED_TERMINAL"
        )

    def test_the_arm_is_bounded(self):
        assert f"limit({VENUE_VOIDED_SUSPENDED_MAX_PER_PASS.__class__.__name__}" \
            not in self._src()
        assert "VENUE_VOIDED_SUSPENDED_MAX_PER_PASS" in self._src()
        assert isinstance(VENUE_VOIDED_SUSPENDED_MAX_PER_PASS, int)
        assert 0 < VENUE_VOIDED_SUSPENDED_MAX_PER_PASS <= 100

    def test_the_arm_is_ordered_oldest_first(self):
        assert "commence_time.asc()" in self._src()

    def test_the_capture_task_calls_the_arm(self):
        """The extraction is only worth anything if a beat still runs it.

        🔴 THE CALLER IS `kalshi_resolution_sweep`, NOT
        `_transition_event_statuses_impl`, AND THIS ARM ONCE PINNED THE LATTER.
        Composed into that task — the obvious home, since the first
        `suspended →` retirement arm lives there — it reddened 79 guards across
        seven other ships. Their session doubles answer `execute` POSITIONALLY
        (`self._selects.pop(0)`), so any new statement anywhere in that function
        shifts every later one onto the wrong canned result. See the arm's own
        docstring. That this structural assertion moved with the call site is
        the point of writing it structurally.

        This is REACHABILITY ONLY. That the beat's call actually runs the phase,
        on the drained path as well as the write path, is behavioural and is
        proved in `test_kalshi_venue_void_7035.py`'s
        `TestTheCaptureSpendsTheFactItWrote`.
        """
        from app.tasks.kalshi_resolution_sweep import run_resolved_voids

        assert "_retire_rows_the_venue_voided(" in inspect.getsource(
            run_resolved_voids
        )

    def test_the_arm_derives_its_floor_rather_than_restating_it(self):
        """`floor` is a parameter, and the caller passes the shared derivation.
        A hand-typed hour count here would drift from the resume window it must
        exceed."""
        from app.tasks.kalshi_resolution_sweep import (
            _retire_rows_the_venue_voided,
        )

        assert "floor" in inspect.signature(
            _retire_venue_voided_suspended_rows
        ).parameters
        caller = inspect.getsource(_retire_rows_the_venue_voided)
        assert "_retire_venue_voided_suspended_rows(" in caller
        assert "unreachable_suspended_floor()" in caller


class TestTheRestoreRailIsAGate:
    def test_the_arm_asks_for_the_backup_table_by_the_shared_constant(self):
        """Structural only. That the arm actually RETIRES NOTHING when the table
        is absent is behavioural and is proved against a real server in
        `tests/integration/test_venue_void_retirement_pg.py`, which drops the
        table and runs the arm — a source scan cannot tell a gate that fires
        from one that is spelled and never reached."""
        src = inspect.getsource(_retire_venue_voided_suspended_rows)
        assert "UNREACHABLE_SUSPENDED_BACKUP_TABLE" in src
        assert "to_regclass" in src
        assert UNREACHABLE_SUSPENDED_BACKUP_TABLE == "backup_unreachable_suspended_5532"

    def test_the_arm_asks_the_catalogue_itself_rather_than_being_told(self):
        """It asks `to_regclass` itself. Being HANDED a `backup_present` would
        tie this arm's safety to whoever computed it — the sibling computes its
        own only while its Redis budget is non-zero, so that value is a stale
        True the moment the budget is zeroed.

        Both halves are asserted, because either alone is satisfiable by an arm
        that is wrong: the read must be IN this function, and it must not be a
        parameter the caller supplies.
        """
        src = inspect.getsource(_retire_venue_voided_suspended_rows)
        assert "to_regclass" in src
        assert "backup_present = (await session.execute(" in src
        assert "backup_present" not in inspect.signature(
            _retire_venue_voided_suspended_rows
        ).parameters

    def test_the_enable_script_and_the_arm_share_one_ddl(self):
        """Three copies of four columns is a gate that can pass against a table
        the script does not create."""
        import pathlib

        script = pathlib.Path(__file__).resolve().parents[1] / (
            "scripts/unreachable_suspended_door.py"
        )
        text = script.read_text()
        assert "UNREACHABLE_SUSPENDED_BACKUP_DDL" in text
        assert "CREATE TABLE IF NOT EXISTS" not in text, (
            "the script must import the DDL, not re-spell it"
        )
        for column in ("event_id", "previous_status", "commence_time", "retired_at"):
            assert column in UNREACHABLE_SUSPENDED_BACKUP_DDL


class TestTheTerminalIsOneEveryReaderAlreadyHides:
    """The last link. `tests/test_a_retired_row_is_off_every_user_facing_read.py`
    proves `voided` is off every list surface and 410s on the by-id route; these
    arms say the word this arm writes is that word, so the chain closes without
    either file restating the other."""

    def test_the_arm_writes_a_retired_status(self):
        assert is_retired_event_status(UNREACHABLE_SUSPENDED_TERMINAL)
        assert UNREACHABLE_SUSPENDED_TERMINAL in RETIRED_STATUSES

    def test_suspended_is_not_a_retired_status(self):
        """The before state. If it were, the card would already be hidden and
        there would be no defect to fix."""
        assert not is_retired_event_status(EVENT_SUSPENDED)

    def test_the_by_id_route_refuses_a_retired_row(self):
        """Structural, because the route needs the whole app to call. The 410
        and the predicate must stay in the same breath."""
        import pathlib

        route = pathlib.Path(__file__).resolve().parents[1] / "app/routes/events.py"
        text = route.read_text()
        assert "if is_retired_event_status(event.status):" in text
        after = text.split("if is_retired_event_status(event.status):", 1)[1][:400]
        assert "410" in after


# =============================================================================
# Part 4 — the specimen ids, recorded so a later reader can re-check them.
# =============================================================================


class TestTheSpecimenIsRecorded:
    def test_the_four_market_ids_are_the_ones_the_cert_named(self):
        assert SPECIMEN_MARKETS == (60481773, 60636796, 60636798, 60636800)

    def test_the_event_is_the_one_the_cert_named(self):
        assert SPECIMEN_EVENT == 15312871
