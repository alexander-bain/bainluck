"""#5821 — guards for the listing-date repair's REFUSALS and its runbook.

CERT-2793's required repair is `5821-EXISTING-SPLIT-CONTAINERS-COLLAPSE`, and
`scripts/repair_5821_polymarket_listing_dates.py` is it: re-date the
Polymarket-born rows carrying a Gamma LISTING stamp where `commence_time`
should hold the kickoff, so the pairs that today serve as two cards fold
through `event_twin_fold` — machinery already trusted on five rails.

WHAT THIS FILE CAN AND CANNOT TEST, STATED UP FRONT SO NOBODY READS IT AS MORE
THAN IT IS. The population query is Postgres-only by construction (`::timestamptz`,
`extract(epoch …)`, `now()`, a JSONB `->>`), and the only real-Postgres job in CI
runs exactly one file — `tests/integration/test_search_recall_contract.py`. So
these guards cover the parts that are decidable without a database and that a
future edit can silently break:

  * **what the repair DECIDES for one row** — `planned_write` is pure and takes
    no database, which is the whole reason it exists as a separate function.
    `TestTheSuspendedPopulation` drives the two production siblings through it
    and then through the real `fold_twin_events` and the real
    `served_event_status`, so the reader's three facts (one card, dated at the
    kickoff, reading as upcoming) are asserted rather than described;
  * the runbook names the app the PRODUCER actually runs on, tied to live
    `HEAVY_TASKS` membership rather than to a sentence somebody typed;
  * the write refusals fire on the wrong app and on no app at all;
  * the runbook's commands only use flags the parser really has;
  * the UNDO line the apply prints names a restore script that exists and
    accepts the flag it is printed with.

The first bullet is here because its absence cost a presentation: CERT-2797
BLOCKed the previous sha for writing `commence_time` alone, which fixes the 40
`live` rows (the serve layer downgrades those) and leaves the 302 `suspended`
ones reading paused for a match days away. Nothing in the old file could have
caught that, because nothing in it executed a decision.

The population itself was measured on production (see the script header:
603 → 27 ambiguous → 234 past → **342 in scope**, 0 scored, 0 finished, 0 moving
backwards) and the apply is attended. A test asserting those counts would be
asserting a snapshot of a live table, which is worse than not asserting them.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
REPAIR_PATH = _SCRIPTS / "repair_5821_polymarket_listing_dates.py"
RESTORE_PATH = _SCRIPTS / "restore_5821_polymarket_listing_dates.py"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def repair():
    return _load(REPAIR_PATH)


@pytest.fixture(scope="module")
def restore():
    return _load(RESTORE_PATH)


class TestTheRunbookTargetsTheProducer:
    def test_the_producer_app_is_where_the_minting_task_runs(self, repair):
        """🔴 The runbook's app is derived from HEAVY_TASKS, not asserted in prose.

        `match_prediction_markets` is the task that auto-creates these rows and
        stamps the Gamma listing instant onto `commence_time`. Since the heavy
        split it runs on `bainluck-heavy`, released separately from the web app
        and routinely behind it (notice 48). If it is ever moved off heavy, this
        test fails — instead of the runbook quietly sending an operator to an
        app where the producer is not running.
        """
        from app.tasks import HEAVY_TASKS

        assert "app.tasks.match_prediction_markets" in HEAVY_TASKS, (
            "the task that mints these rows is no longer a HEAVY_TASK — the "
            "repair's PRODUCER_APP and its whole app-pin argument need "
            "re-deriving, not editing"
        )
        assert repair.PRODUCER_APP == "bainluck-heavy"

    def test_the_poller_is_named_as_the_thing_it_is_not(self, repair):
        """The header's one correction worth pinning.

        `poll_polymarket_markets` is NOT heavy — it runs on the main app — and
        an earlier draft of this script said it was. It matters because the
        app-pin's whole justification is "the producer runs there": the poller
        writes `market_metadata` and never `events.commence_time`, so it is the
        matcher that makes the argument, and the header now says so. This test
        keeps the false claim from coming back.
        """
        from app.tasks import HEAVY_TASKS

        assert "app.tasks.poll_polymarket_markets" not in HEAVY_TASKS
        header = REPAIR_PATH.read_text()
        assert "is NOT heavy" in header, (
            "the header stopped distinguishing the poller from the matcher; "
            "the app pin then rests on a claim that is false"
        )


class TestTheWriteRefusals:
    def _args(self, **kw):
        return argparse.Namespace(
            apply=kw.get("apply", False),
            backup=kw.get("backup", False),
            dry_run=kw.get("dry_run", False),
        )

    def test_a_dry_run_needs_no_app_at_all(self, repair, monkeypatch):
        """Reading is safe anywhere — a laptop, either dyno, CI."""
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)

        assert repair.wrong_app_refusal(self._args()) is None

    def test_an_unset_app_refuses_to_WRITE(self, repair, monkeypatch):
        """🔴 THE ONE THAT MATTERS. Unset means "not on a dyno" — a laptop
        pointed at the production database with whatever is checked out. A gate
        that fell through on unset would be no gate at all on the only machine
        where nobody is watching the deploy."""
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)

        for args in (self._args(apply=True), self._args(backup=True)):
            refusal = repair.wrong_app_refusal(args)
            assert refusal and "REFUSING to write" in refusal
            assert "HEROKU_APP_NAME is unset" in refusal

    def test_the_wrong_app_refuses_and_says_which_one_it_is_on(
        self, repair, monkeypatch
    ):
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")

        refusal = repair.wrong_app_refusal(self._args(apply=True))

        assert refusal and "'bainluck'" in refusal
        assert repair.PRODUCER_APP in refusal, (
            "a refusal that does not name the app to use costs the operator a "
            "round trip to the runbook"
        )

    def test_the_producer_app_may_write(self, repair, monkeypatch):
        monkeypatch.setenv("HEROKU_APP_NAME", repair.PRODUCER_APP)

        assert repair.wrong_app_refusal(self._args(apply=True)) is None
        assert repair.wrong_app_refusal(self._args(backup=True)) is None


class TestTheRunbookMatchesTheProgram:
    """A runbook is a promise about a CLI. These two drift silently."""

    def _flags(self, path: Path) -> set[str]:
        """Every flag the script's parser declares.

        Read off the source rather than by building the parser: both scripts
        construct theirs inside `main()`, which also calls `sys.exit`, so there
        is no parser to introspect without running the program.
        """
        return set(re.findall(r'add_argument\(\s*"(--[a-z-]+)"', path.read_text()))

    def _runbook_flags(self, path: Path) -> set[str]:
        text = path.read_text()
        used = set()
        for line in text.splitlines():
            if path.stem in line and ".py" in line:
                used |= set(re.findall(r"(--[a-z-]+)", line))
        return used

    def test_every_flag_the_repair_runbook_uses_exists(self):
        """🔴 Catches the runbook that tells an operator to pass `--commit`.

        Both halves are read from the file: the flags `add_argument` declares,
        and the flags the header's own command lines pass. A rename that
        updates one and not the other fails here rather than at 3am on a dyno.
        """
        declared = self._flags(REPAIR_PATH)
        used = self._runbook_flags(REPAIR_PATH)

        assert used, "the header stopped showing any command line at all"
        assert used <= declared, (
            f"the runbook passes {sorted(used - declared)}, which the parser "
            f"does not accept (it declares {sorted(declared)})"
        )

    def test_every_flag_the_restore_runbook_uses_exists(self):
        declared = self._flags(RESTORE_PATH)
        used = self._runbook_flags(RESTORE_PATH)

        assert used, "the restore header stopped showing any command line"
        assert used <= declared


class TestTheUndoIsReachable:
    def test_the_apply_prints_a_restore_command_that_exists(self, repair):
        """🔴 D51 is "backs up first AND ships a one-command restore".

        The apply prints the undo line; this asserts the line names a file that
        exists and a flag it accepts. A repair whose printed undo is a typo has
        a restore in the repo and none in the operator's hands.
        """
        found = re.findall(
            r"UNDO: python3 (scripts/\S+\.py) (--[a-z-]+)", REPAIR_PATH.read_text()
        )
        assert found, "the apply no longer prints an UNDO line"

        # EVERY occurrence, not the first. The header states the undo line too,
        # and `re.search` matched THAT one — so an earlier cut of this test went
        # green against a typo in the line the program actually prints. A
        # docstring is not the program (found by mutating the printed string).
        assert len(found) >= 2, (
            "the undo line appears in only one place; it should be both stated "
            f"in the header and printed by the apply (found {found})"
        )
        for script, flag in found:
            target = _SCRIPTS.parent / script
            assert target.exists(), (
                f"an UNDO line names {script}, which does not exist — the "
                "operator's copy-pasteable undo is a typo"
            )
            assert flag in re.findall(
                r'add_argument\(\s*"(--[a-z-]+)"', target.read_text()
            ), f"{script} does not accept {flag}"

    def test_the_restore_names_the_table_the_repair_writes(self, repair, restore):
        """One table name, two files. A rename in one is a restore that refuses
        with "nothing to restore from" on a database that has the backup."""
        assert restore.BACKUP_TABLE == "backup_5821_event_dates"
        assert (
            restore.BACKUP_TABLE in REPAIR_PATH.read_text()
        ), "the repair and its undo disagree about where the backup lives"


class TestThePopulationsExclusions:
    """The SQL cannot be executed here (Postgres-only). What IS checkable is
    that each exclusion the header PROMISES is still a clause, and that the
    binds the caller supplies are the binds the statement asks for — a renamed
    parameter is a runtime failure on a dyno, which is the worst place to find
    one."""

    def test_the_binds_the_caller_passes_are_the_binds_the_sql_wants(self, repair):
        from sqlalchemy import text

        wanted = set(text(repair._POPULATION_SQL).compile().params)

        assert wanted == {"source", "min_seconds"}, (
            "the statement's bind parameters changed; `run()` supplies exactly "
            f"source/min_seconds and would fail on a dyno with {wanted}"
        )

    @pytest.mark.parametrize(
        "clause,why",
        [
            ("commence_time_source = :source", "provenance pin — this defect only"),
            ("v.n_starts = 1", "refuse events whose markets disagree on the instant"),
            (
                "v.start > now()",
                "future fixtures only; settled clocks are out of scope",
            ),
            ("m.source = 'polymarket'", "only the venue that stamps the key"),
        ],
    )
    def test_each_promised_exclusion_is_still_a_clause(self, repair, clause, why):
        """Deliberately a text assertion, and deliberately narrow. It cannot
        prove the query is right; it can only stop an exclusion the header
        advertises from being quietly deleted, which is the edit that would
        widen a production write."""
        assert clause in repair._POPULATION_SQL, f"lost the clause for: {why}"

    def test_the_ceilings_are_above_the_measured_population(self, repair):
        """A ceiling below the measured population is a script that can never
        run; one wildly above it is not a ceiling. 342 rows and a 27.44-day
        largest move were measured on production 2026-09-13."""
        assert repair.MAX_EXPECTED_POPULATION > 342
        assert repair.MAX_MOVE_DAYS > 27.44
        assert repair.MIN_DISAGREEMENT_SECONDS > 0


# ---------------------------------------------------------------------------
# CERT-2797's required repair: the 302 suspended rows
# ---------------------------------------------------------------------------


class TestTheSuspendedPopulation:
    """`5821-FUTURE-SUSPENDED-ROWS-BECOME-SCHEDULED`.

    The first cut wrote `commence_time` alone and argued that
    `served_event_status` would do the rest. It does — for `live`, which is 40
    of the 342 rows. The other 302 are `suspended`, and
    `enforce_live_requires_start` passes `suspended` through verbatim *by
    design*: "this rule only ever downgrades a premature `live`". So those rows
    would have kept reading paused-with-no-result for matches days away.

    These tests are written against the two production siblings the issue names
    and assert the reader's three facts: ONE card, dated at the kickoff, reading
    as upcoming.
    """

    #: The pair, verbatim (`db-query`, production 2026-09-13 10:2xZ). Both
    #: `suspended`, both linked to a Gamma container whose `venue_game_start` is
    #: the same instant two days out, and 30 minutes apart on nothing but the
    #: minute they were ingested.
    SIBLING_A = 15311503
    SIBLING_B = 15311506
    HOME = "Al Ain FC"
    AWAY = "Al Nassr Club"
    S_ACL = 1622

    def _siblings(self, now):
        from app.models.models import Event

        venue = now + timedelta(days=2)
        rows = [
            Event(
                id=self.SIBLING_A,
                sport_id=self.S_ACL,
                home_team_name=self.HOME,
                away_team_name=self.AWAY,
                # The two LISTING stamps, both in the past, 30 minutes apart.
                commence_time=now - timedelta(hours=7),
                status="suspended",
            ),
            Event(
                id=self.SIBLING_B,
                sport_id=self.S_ACL,
                home_team_name=self.HOME,
                away_team_name=self.AWAY,
                commence_time=now - timedelta(hours=7, minutes=30),
                status="suspended",
            ),
        ]
        return rows, venue

    def _repair(self, repair, rows, venue, now):
        """Apply the script's own decision to the rows, as `--apply` would."""
        for row in rows:
            plan = repair.planned_write(row.status, row.commence_time, venue, now)
            for column, value in plan.items():
                setattr(row, column, value)
        return rows

    def test_future_suspended_population_serves_scheduled_after_repair_5821(
        self, repair
    ):
        """🔴 THE REQUIRED TEST. Two linked siblings, one card, upcoming status.

        All three assertions are made BEFORE as well as AFTER, so the test
        cannot pass against a repair that does nothing: before it, the pair is
        two cards both reading `suspended`.
        """
        from app.utils.event_twin_fold import fold_twin_events
        from app.utils.lifecycle import served_event_status

        now = datetime.now(timezone.utc)
        rows, venue = self._siblings(now)

        before = fold_twin_events(rows)
        assert len(before.events) == 2, (
            "the pair folded before the repair — then the repair is not what "
            "collapses it and this whole test is measuring something else"
        )
        assert {served_event_status(r.status, r.commence_time, now) for r in rows} == {
            "suspended"
        }

        self._repair(repair, rows, venue, now)
        after = fold_twin_events(rows)

        # ONE READER CARD.
        assert len(after.events) == 1, (
            "the two rows still serve as two cards after the re-date — the "
            f"fold key did not collapse them (got {[e.id for e in after.events]})"
        )
        # DATED AT THE KICKOFF, not at either ingest instant.
        assert after.events[0].commence_time == venue
        # UPCOMING PUBLIC STATUS — the half CERT-2797 blocked on.
        assert served_event_status(after.events[0].status, venue, now) == "scheduled", (
            "the surviving card still reads as a match in progress for a "
            "fixture two days away"
        )

    def test_the_clock_alone_would_not_have_fixed_the_status(self, repair):
        """🔴 READ THIS ONE SECOND. It is the BLOCK, as a test.

        Re-dating without lifting the status leaves `served_event_status`
        returning `suspended`, because that function deliberately declines to
        touch it. A future edit that drops the status half of `planned_write`
        reddens here with the reason attached.
        """
        from app.utils.lifecycle import served_event_status

        now = datetime.now(timezone.utc)
        venue = now + timedelta(days=2)

        assert served_event_status("suspended", venue, now) == "suspended"
        assert (
            repair.planned_write("suspended", now - timedelta(hours=7), venue, now)[
                "status"
            ]
            == "scheduled"
        )

    def test_a_live_row_is_lifted_too_even_though_the_serve_layer_would_cope(
        self, repair
    ):
        """The 40. `served_event_status` would already downgrade these, so the
        write is belt and braces — but leaving the COLUMN saying `live` for a
        fixture two days out means every admin surface, every raw reader and
        every future rule keyed on the column still sees a match in progress."""
        now = datetime.now(timezone.utc)
        venue = now + timedelta(days=2)

        plan = repair.planned_write("live", now - timedelta(hours=7), venue, now)

        assert plan["status"] == "scheduled"

    @pytest.mark.parametrize("status", ["closed", "completed", "voided", "merged"])
    def test_a_terminal_row_keeps_its_status(self, repair, status):
        """🔴 The allowlist, from the other side. `LIFTABLE_IN_PROGRESS_STATUSES`
        is an allowlist rather than a denylist for the reason written beside
        `EVENT_PLAYABLE_STATUSES`: a status nobody thought of must be left alone,
        not quietly rewritten. A repair that lifted `closed` to `scheduled`
        would un-settle a finished match."""
        now = datetime.now(timezone.utc)
        venue = now + timedelta(days=2)

        plan = repair.planned_write(status, now - timedelta(hours=7), venue, now)

        assert plan == {
            "commence_time": venue
        }, f"a `{status}` row had its status rewritten by a date repair"

    def test_a_past_correction_moves_the_clock_and_not_the_status(self, repair):
        """Out-of-scope for the population query, and refused a second time
        here. A fixture whose corrected instant is in the PAST may really be
        live or suspended right now — the whole argument for lifting the status
        is that the match has not started."""
        now = datetime.now(timezone.utc)
        past = now - timedelta(hours=1)

        plan = repair.planned_write("suspended", now - timedelta(days=3), past, now)

        assert plan == {"commence_time": past}

    def test_a_row_already_holding_the_venue_instant_plans_nothing(self, repair):
        """Idempotence at the decision, not only at the population query: an
        empty plan is a skip, so a second apply writes nothing and the receipt
        stays honest about what the FIRST one did."""
        now = datetime.now(timezone.utc)
        venue = now + timedelta(days=2)

        assert repair.planned_write("suspended", venue, venue, now) == {}
