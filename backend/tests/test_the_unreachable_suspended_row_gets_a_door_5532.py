"""A GAME THAT ENDED TWO YEARS AGO STOPS SAYING IT IS PAUSED. #5532 / #5130.

═══ WHY THIS SUITE EXISTS ═══

``event_completion.play_resumes`` argues, in as many words, that ``suspended``
is not a trap:

    *"between them, a suspended row is reachable from both of the states it can
    legally become, which is what stops the new state being a trap."*

That sentence is true of the PREDICATES and false of the ROWS. A predicate
returning True says a door is *permitted*; it says nothing about whether
anything will ever walk through it. Every writer on the far side of both doors
is keyed on a provider id **and** bounded to 48h past kick-off:

    espn_sync._settle_authority_stragglers   espn_id NOT NULL, commence >= -48h
    espn_sync  suspended -> live             commence >= -SUSPENDED_RESUME_WINDOW
    espn_helpers / espn_tennis_anchor        dereference espn_id
    statpal_sync, odds_polling scores path   write a terminal only if status
                                             == "live" — not doors at all

So a suspended row with no ``external_id``, no ``espn_id`` and no
``statpal_fixture_id``, past that window, satisfies both predicates forever and
is selected by nothing. It is not waiting. It is finished being written to, and
it keeps telling every surface that buckets ``suspended`` — the reader's
"Live & Paused" shelf — that a match is paused.

MEASURED on production 2026-09-12 (fingerprints ``e48d6a8fe259b231`` /
``30e8106636cf022b`` / ``d38af42ed4dd42ed``): **10,704** rows, arriving at
**~600 a day**, the oldest from 2024-10-02. Zero were stuck in ``live`` — the
staleness net works; everything is stuck one step later.

═══ THE CONTROLS ARE THE POINT OF THIS SUITE ═══

The easy version of this fix retires everything that looks abandoned, and the
expensive mistakes are all in what it must REFUSE. Four refusals, each with a
named channel behind it and each measured:

    a score, or a completed_at    something DID reach the row, which refutes the
                                  premise directly. Measured 0 of 10,704 today;
                                  this predicate is what keeps that true.
    any provider id               external_id / espn_id / statpal_fixture_id —
                                  each one is a live channel.
    an ESPN-covered sport         🔴 `_backfill_espn_ids` is the ONE channel
                                  that needs no id: it is the pass that GOES AND
                                  GETS the espn_id, selects `espn_id IS NULL`
                                  with NO time window, and #3790 widened it to
                                  admit `suspended` precisely because for an
                                  unanchored row it is the only door. Its reach
                                  is `ESPN_SPORT_MAPPING`. Measured 111 of the
                                  10,704 — the whole soccer-big-five + MMA slice.
    inside the resume window      the floor is DERIVED from
                                  SUSPENDED_RESUME_WINDOW, never restated.

``_backfill_espn_ids`` is ordered ``commence_time DESC``, so an old row is
starved in practice (gotcha #41). **Starved is not unreachable.** A starving
order can be fixed later; a retired status cannot be re-selected by the pass
that would have fixed it. That asymmetry is why the exclusion is by sport and
not by "would it realistically ever get there".

═══ OFF BY DEFAULT, AND THAT IS TESTED FIRST ═══

The population is a standing backlog and a flow at once and no row property
separates them, so an unbudgeted first pass would retire ~10,700 rows in one
60-second beat with no backup — the thing D51 exists to stop. The arm therefore
reads a per-pass budget from Redis, absent means 0, and 0 means it does not even
issue its SELECT. Every failure mode of that read returns 0: an arm that writes
a terminal status fails CLOSED, because "the config read broke" and "an operator
asked for this" must never look alike.

═══ RED-FIRST ═══

``TestTheDefectReproduces`` runs the PRE-FIX reachability rule — the union of
the two doors' real WHERE clauses — over the specimen and shows it selected by
neither. Without that, the tests below could be certifying a predicate against a
population the old code already handled.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.event_completion import (
    EVENT_SUSPENDED,
    RETIRED_STATUSES,
    UNREACHABLE_SUSPENDED_MARGIN,
    UNREACHABLE_SUSPENDED_TERMINAL,
    suspended_row_is_unreachable,
)

NOW = datetime(2026, 9, 12, 18, 0, tzinfo=timezone.utc)


def _floor():
    """The floor exactly as the caller derives it — never a hand-typed 72h."""
    from app.tasks.espn_sync import SUSPENDED_RESUME_WINDOW

    return SUSPENDED_RESUME_WINDOW + UNREACHABLE_SUSPENDED_MARGIN


def _row(**over):
    """The production specimen: a Polymarket-minted soccer_other fixture."""
    base = dict(
        status=EVENT_SUSPENDED,
        commence_time=NOW - timedelta(days=9),
        external_id=None,
        espn_id=None,
        statpal_fixture_id=None,
        home_score=None,
        away_score=None,
        completed_at=None,
        anchor_acquirable=False,
        now=NOW,
        floor=_floor(),
    )
    base.update(over)
    return base


def _verdict(**over):
    return suspended_row_is_unreachable(**_row(**over))


class TestTheDefectReproduces:
    """The specimen is selected by NEITHER door. Without this the suite is air."""

    def test_the_resume_arm_cannot_see_it(self):
        from app.tasks.espn_sync import SUSPENDED_RESUME_WINDOW

        row = _row()
        # `suspended -> live`: Event.commence_time >= now - SUSPENDED_RESUME_WINDOW
        assert not (
            row["commence_time"] >= NOW - SUSPENDED_RESUME_WINDOW
        ), "specimen is inside the resume window — pick an older one"

    def test_the_authority_straggler_arm_cannot_see_it(self):
        from app.tasks.espn_sync import (
            AUTHORITY_STRAGGLER_LOOKBACK,
            AUTHORITY_STRAGGLER_MIN_AGE,
        )

        row = _row()
        selected = (
            row["espn_id"] is not None
            and row["commence_time"] >= NOW - AUTHORITY_STRAGGLER_LOOKBACK
            and row["commence_time"] <= NOW - AUTHORITY_STRAGGLER_MIN_AGE
        )
        assert not selected, "the straggler arm would have reached it"

    def test_and_the_status_it_keeps_telling_readers_is_paused(self):
        """The reader-visible half: `suspended` is not in the retired set, so a
        surface that buckets it shows the row as paused. That IS the defect."""
        assert EVENT_SUSPENDED not in RETIRED_STATUSES


class TestTheDoorOpensForTheSpecimen:
    def test_the_production_specimen_is_unreachable(self):
        assert _verdict() is True

    def test_the_terminal_is_one_every_reader_already_hides(self):
        """Chosen over a new word because no consumer has to be taught it —
        the precondition CERT-786 says a new state is not shipped without."""
        assert UNREACHABLE_SUSPENDED_TERMINAL in RETIRED_STATUSES

    def test_the_terminal_is_not_merged(self):
        """The other member of RETIRED_STATUSES, and it would pass the test
        above while asserting something false: `merged` means this row was
        absorbed into another row that kept its markets. We are claiming no
        such correspondence — that is lane1's to claim, under D35."""
        assert UNREACHABLE_SUSPENDED_TERMINAL != "merged"

    def test_two_years_deep_still_qualifies(self):
        assert _verdict(commence_time=NOW - timedelta(days=710)) is True


class TestTheRefusals:
    """Each one names a live channel. These are the tests that cost rows."""

    @pytest.mark.parametrize("field", ["external_id", "espn_id", "statpal_fixture_id"])
    def test_any_provider_id_refuses(self, field):
        assert _verdict(**{field: "abc-123"}) is False

    @pytest.mark.parametrize("field", ["external_id", "espn_id", "statpal_fixture_id"])
    def test_a_blank_id_is_not_an_id(self, field):
        """A provider that wrote an empty string told us nothing."""
        assert _verdict(**{field: "   "}) is True

    def test_an_espn_covered_sport_refuses(self):
        """#3790's channel: `_backfill_espn_ids` can still go and get an anchor
        for this row, with no time window, and retiring it would end that."""
        assert _verdict(anchor_acquirable=True) is False

    @pytest.mark.parametrize("field", ["home_score", "away_score"])
    def test_any_score_refuses(self, field):
        """A score means something DID reach the row — the premise is refuted."""
        assert _verdict(**{field: 0}) is False

    def test_a_zero_score_refuses_and_is_not_read_as_falsy(self):
        assert _verdict(home_score=0, away_score=0) is False

    def test_a_completed_at_refuses(self):
        assert _verdict(completed_at=NOW - timedelta(days=8)) is False

    @pytest.mark.parametrize(
        "status", ["live", "scheduled", "completed", "closed", "voided", "merged"]
    )
    def test_only_suspended_is_judged(self, status):
        assert _verdict(status=status) is False

    def test_a_row_with_no_clock_is_refused(self):
        assert _verdict(commence_time=None) is False


class TestTheFloorIsDerivedFromTheWindowItMustExceed:
    """Two constants answering one capability question — assert the gap."""

    def test_the_floor_strictly_exceeds_the_resume_window(self):
        from app.tasks.espn_sync import SUSPENDED_RESUME_WINDOW

        assert _floor() > SUSPENDED_RESUME_WINDOW
        assert UNREACHABLE_SUSPENDED_MARGIN > timedelta(0)

    def test_a_row_still_inside_the_resume_window_is_refused(self):
        from app.tasks.espn_sync import SUSPENDED_RESUME_WINDOW

        just_inside = NOW - SUSPENDED_RESUME_WINDOW + timedelta(minutes=1)
        assert _verdict(commence_time=just_inside) is False

    def test_the_whole_margin_is_a_refusal_band(self):
        """Every instant between the window and the floor must refuse, or the
        margin is decoration."""
        from app.tasks.espn_sync import SUSPENDED_RESUME_WINDOW

        span = (UNREACHABLE_SUSPENDED_MARGIN.total_seconds()) / 3600.0
        for hours_past_window in (0.0, span / 2, span - 0.01):
            at = NOW - SUSPENDED_RESUME_WINDOW - timedelta(hours=hours_past_window)
            assert _verdict(commence_time=at) is False, hours_past_window

    def test_one_second_past_the_floor_qualifies(self):
        at = NOW - _floor() - timedelta(seconds=1)
        assert _verdict(commence_time=at) is True


class TestTheArmIsOffUntilSomebodyTurnsItOn:
    """The D51 half. Nothing here touches the database."""

    def test_absent_key_is_zero(self, monkeypatch):
        import app.tasks.redis_state as redis_state
        from app.tasks import espn_sync

        monkeypatch.setattr(
            redis_state, "get_redis_client", lambda: _FakeRedis(None)
        )
        assert espn_sync._unreachable_suspended_budget() == 0

    @pytest.mark.parametrize("raw", [b"0", b"-5", b"", b"nonsense", b"3.5"])
    def test_every_unusable_value_is_zero(self, monkeypatch, raw):
        import app.tasks.redis_state as redis_state
        from app.tasks import espn_sync

        monkeypatch.setattr(
            redis_state, "get_redis_client", lambda: _FakeRedis(raw)
        )
        assert espn_sync._unreachable_suspended_budget() == 0

    def test_a_broken_redis_is_zero_not_unbounded(self, monkeypatch):
        """Fail CLOSED: 'the config read broke' must not look like consent."""
        import app.tasks.redis_state as redis_state
        from app.tasks import espn_sync

        def _boom():
            raise RuntimeError("redis down")

        monkeypatch.setattr(redis_state, "get_redis_client", _boom)
        assert espn_sync._unreachable_suspended_budget() == 0

    def test_a_set_budget_is_honoured(self, monkeypatch):
        import app.tasks.redis_state as redis_state
        from app.tasks import espn_sync

        monkeypatch.setattr(
            redis_state, "get_redis_client", lambda: _FakeRedis(b"50")
        )
        assert espn_sync._unreachable_suspended_budget() == 50

    def test_a_fat_fingered_budget_is_capped(self, monkeypatch):
        import app.tasks.redis_state as redis_state
        from app.tasks import espn_sync

        monkeypatch.setattr(
            redis_state, "get_redis_client", lambda: _FakeRedis(b"999999")
        )
        assert (
            espn_sync._unreachable_suspended_budget()
            == espn_sync.UNREACHABLE_SUSPENDED_MAX_BUDGET
        )

    def test_the_cap_is_a_real_bound_not_a_formality(self):
        from app.tasks import espn_sync

        assert 0 < espn_sync.UNREACHABLE_SUSPENDED_MAX_BUDGET < 2000


class _FakeRedis:
    def __init__(self, value):
        self._value = value

    def get(self, key):
        from app.tasks.espn_sync import UNREACHABLE_SUSPENDED_BUDGET_KEY

        assert key == UNREACHABLE_SUSPENDED_BUDGET_KEY
        return self._value


class TestTheArmSpendsTheSharedPredicateRatherThanACopyOfIt:
    """Structural half. The behavioural tests above run the pure predicate; these
    say the arm in the task actually calls it, and applies the same exclusions in
    its own SELECT. A predicate nothing spends is a predicate that certifies
    nothing (the failure mode #3790's docstring names)."""

    @staticmethod
    def _arm_source():
        import inspect

        from app.tasks.espn_sync import _transition_event_statuses_impl

        src = inspect.getsource(_transition_event_statuses_impl)
        marker = "suspended → retired"
        assert marker in src, "the arm's banner comment moved — re-aim this scan"
        return src[src.index(marker):]

    def test_the_arm_calls_the_shared_predicate(self):
        assert "suspended_row_is_unreachable(" in self._arm_source()

    def test_the_arm_writes_the_shared_terminal_constant(self):
        src = self._arm_source()
        assert "UNREACHABLE_SUSPENDED_TERMINAL" in src
        assert '"voided"' not in src and "'voided'" not in src, (
            "the terminal is a constant so D-live176 option B is one line"
        )

    def test_the_arm_derives_its_floor_from_the_resume_window(self):
        src = self._arm_source()
        assert "SUSPENDED_RESUME_WINDOW + UNREACHABLE_SUSPENDED_MARGIN" in src
        assert "hours=72" not in src, "the floor must never be restated"

    @pytest.mark.parametrize(
        "clause",
        [
            "Event.external_id.is_(None)",
            "Event.espn_id.is_(None)",
            "Event.statpal_fixture_id.is_(None)",
            "Event.home_score.is_(None)",
            "Event.away_score.is_(None)",
            "Event.completed_at.is_(None)",
            "Event.sport_id.notin_(espn_covered_ids)",
        ],
    )
    def test_the_screen_carries_every_refusal_the_verdict_does(self, clause):
        """The SELECT is only a screen, but a screen that omits a refusal pulls
        rows the verdict must then throw away — and an `espn_covered_ids` omitted
        HERE would silently spend the whole budget on rows it cannot retire."""
        assert clause in self._arm_source()

    def test_the_arm_is_ordered_oldest_first(self):
        """gotcha #41: newest-first starves the tail, and the tail here is two
        years old."""
        assert "Event.commence_time.asc()" in self._arm_source()

    def test_the_arm_is_bounded_by_the_budget(self):
        assert ".limit(stats[\"unreachable_suspended_budget\"])" in self._arm_source()

    def test_no_backup_table_means_no_writes(self):
        """D51 as code rather than as a runbook step: the arm zeroes its own
        budget when the restore rail is absent, so it cannot retire a row
        nobody could give back."""
        src = self._arm_source()
        assert "to_regclass" in src
        assert "if not backup_present:" in src
        after = src[src.index("if not backup_present:"):]
        assert 'stats["unreachable_suspended_budget"] = 0' in after

    def test_the_row_is_backed_up_before_its_status_changes(self):
        """Order matters: an INSERT that raises must leave the status alone."""
        src = self._arm_source()
        insert_at = src.index("INSERT INTO")
        write_at = src.index("event.status = UNREACHABLE_SUSPENDED_TERMINAL")
        assert insert_at < write_at
        assert "previous_status" in src

    def test_the_arm_passes_the_real_anchor_acquirable_value(self):
        """MUTATION SURVIVOR, found and closed. Hard-coding this argument to
        `False` survived every test above: the SELECT already excludes ESPN
        sports, so the verdict's copy of the exclusion is never the thing that
        decides, and the behavioural tests call the predicate directly. The
        second half of a defence in depth is invisible at the public surface by
        construction — so it is pinned structurally or not at all."""
        src = self._arm_source()
        assert "event.sport_id in espn_covered_ids," in src

    def test_an_empty_espn_allowlist_zeroes_the_budget(self):
        """`notin_([])` is TRUE in SQL and `x in []` is False in Python, so an
        empty allowlist makes BOTH halves of the exclusion say "retire" in
        unison — the one input on which the guard silently inverts. Structural
        only: the guard sits mid-way through a six-query async body, so there is
        no seam to call it through. Stated as a known weaker assertion rather
        than dressed up as behavioural."""
        src = self._arm_source()
        assert "if not espn_covered_ids:" in src
        zeroing = 'stats["unreachable_suspended_budget"] = 0'
        assert zeroing in src[src.index("if not espn_covered_ids:"):]

    def test_the_espn_exclusion_reads_the_mapping_rather_than_a_copied_list(self):
        """A hand-copied list of 26 sport keys goes stale the day coverage
        changes; this must resolve `ESPN_SPORT_MAPPING` itself."""
        assert "ESPN_SPORT_MAPPING.keys()" in self._arm_source()


class TestRestoreClosesTheDoorBeforeRestoringRows:
    """CERT-2753's named repair, `5532-RESTORE-CLOSES-THE-DOOR-FIRST`.

    The first version restored the rows and then PRINTED "run --close if you also
    want it shut". That is not a rollback. The arm runs every 60s off the same
    budget key and every restored row is still eligible by construction — the
    predicate that selected it has not changed — so the next pass re-retires
    exactly what was just handed back. The claimed one-command undo was two
    commands with a race between them, and the race runs in the direction that
    silently reverses the operator.

    Three claims, which is what the cert asked for: the Redis deletion PRECEDES
    the UPDATE; a close that fails PREVENTS the UPDATE; and after a successful
    close the arm's own budget reader sees zero.
    """

    @staticmethod
    def _load():
        import importlib.util
        import pathlib

        path = (
            pathlib.Path(__file__).resolve().parents[1]
            / "scripts"
            / "unreachable_suspended_door.py"
        )
        spec = importlib.util.spec_from_file_location("_door_script", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    class _Journal:
        """One ordered record of everything both halves did."""

        def __init__(self, delete_raises=False, still_there_after_delete=False):
            self.calls = []
            self._delete_raises = delete_raises
            self._still = still_there_after_delete

        # -- redis half --
        def delete(self, key):
            self.calls.append(("redis.delete", key))
            if self._delete_raises:
                raise RuntimeError("redis down")

        def get(self, key):
            self.calls.append(("redis.get", key))
            return b"200" if self._still else None

        # -- session half --
        async def execute(self, *a, **k):
            self.calls.append(("sql.execute", None))

            class _R:
                rowcount = 7

            return _R()

        async def commit(self):
            self.calls.append(("sql.commit", None))

    def _patched(self, monkeypatch, journal):
        """Wire both halves of the script to one journal."""
        import contextlib

        import app.tasks.base as task_base
        import app.tasks.redis_state as redis_state

        mod = self._load()
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: journal)

        @contextlib.asynccontextmanager
        async def _session():
            yield journal

        monkeypatch.setattr(task_base, "get_task_session", _session)
        return mod

    def test_the_delete_precedes_the_update(self, monkeypatch):
        import asyncio

        j = self._Journal()
        mod = self._patched(monkeypatch, j)
        assert asyncio.run(mod._restore()) == 0
        names = [c[0] for c in j.calls]
        assert "redis.delete" in names and "sql.execute" in names
        assert names.index("redis.delete") < names.index("sql.execute"), names

    def test_a_close_that_raises_prevents_the_update(self, monkeypatch):
        import asyncio

        j = self._Journal(delete_raises=True)
        mod = self._patched(monkeypatch, j)
        assert asyncio.run(mod._restore()) == 2
        assert "sql.execute" not in [c[0] for c in j.calls], j.calls

    def test_a_delete_that_did_not_take_prevents_the_update(self, monkeypatch):
        """`delete` returning without raising says the command was accepted, not
        that the key is gone. The read-back is the guarantee."""
        import asyncio

        j = self._Journal(still_there_after_delete=True)
        mod = self._patched(monkeypatch, j)
        assert asyncio.run(mod._restore()) == 2
        assert "sql.execute" not in [c[0] for c in j.calls], j.calls

    def test_after_a_successful_close_the_next_pass_reads_zero(self, monkeypatch):
        """The claim that matters: the ARM's own budget reader — not the
        script's opinion of it — returns 0 against the post-close Redis."""
        import asyncio

        import app.tasks.redis_state as redis_state
        from app.tasks import espn_sync

        j = self._Journal()
        mod = self._patched(monkeypatch, j)
        assert asyncio.run(mod._restore()) == 0

        monkeypatch.setattr(redis_state, "get_redis_client", lambda: j)
        assert espn_sync._unreachable_suspended_budget() == 0

    def test_close_alone_reports_failure_rather_than_success(self, monkeypatch):
        """`--close` used on its own must not print a reassuring line when the
        key is still armed."""
        import app.tasks.redis_state as redis_state

        j = self._Journal(still_there_after_delete=True)
        mod = self._load()
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: j)
        assert mod._set_budget(None) == 2

    def test_restore_no_longer_tells_the_operator_to_run_close_afterwards(self):
        """The defect was a sentence as much as a control flow."""
        import pathlib

        src = (
            pathlib.Path(__file__).resolve().parents[1]
            / "scripts" / "unreachable_suspended_door.py"
        ).read_text()
        assert "run --close if you also want it shut" not in src


class TestAnAbsentAppNameIsNotTheNamedApp:
    """Follow-up `5532-REQUIRE-NAMED-HEROKU-APP` (nonblocking, taken anyway).

    The first version refused a WRONG `HEROKU_APP_NAME` and let an ABSENT one
    through — and absent is the case that covers every laptop and lane worktree,
    so it was the one path that could point a mutating run at whatever
    `DATABASE_URL` was exported."""

    @staticmethod
    def _main_with(monkeypatch, argv, app_name):
        import pathlib
        import sys

        import pytest as _pytest

        from tests.test_the_unreachable_suspended_row_gets_a_door_5532 import (
            TestRestoreClosesTheDoorBeforeRestoringRows as _T,
        )

        assert pathlib.Path  # keep the import meaningful
        mod = _T._load()
        if app_name is None:
            monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
        else:
            monkeypatch.setenv("HEROKU_APP_NAME", app_name)
        monkeypatch.setattr(sys, "argv", ["unreachable_suspended_door.py"] + argv)
        with _pytest.raises(SystemExit) as exc:
            mod.main()
        return exc.value.code

    @pytest.mark.parametrize("argv", [["--open", "50"], ["--close"], ["--restore"],
                                      ["--create-backup"]])
    def test_a_mutating_action_refuses_with_no_app_name(self, monkeypatch, argv):
        assert self._main_with(monkeypatch, argv, None) != 0

    @pytest.mark.parametrize("argv", [["--open", "50"], ["--restore"]])
    def test_a_mutating_action_refuses_on_a_foreign_app(self, monkeypatch, argv):
        assert self._main_with(monkeypatch, argv, "some-other-app") != 0

    def test_dry_run_is_exempt_because_it_writes_nothing(self, monkeypatch):
        """Exempt deliberately: --dry-run is how the population is read locally,
        and it is the command this script's own docstring leads with."""
        import sys

        import app.tasks.base as task_base

        mod = TestRestoreClosesTheDoorBeforeRestoringRows._load()
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
        monkeypatch.setattr(sys, "argv", ["x", "--dry-run"])

        called = {"n": 0}

        async def _boom():
            called["n"] += 1
            return 0

        monkeypatch.setattr(mod, "_dry_run", _boom)
        assert task_base  # the guard must not be what stops us
        assert mod.main() == 0
        assert called["n"] == 1
