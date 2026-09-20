"""#7594 — the take-back of the twins #7260's orientation-blind screen published.

CERT-3187 blocked the forward fix for a hole that is real and measured: the
screen stopped the arm publishing NEW reversed twins, but 16 rows were already
on the site, and `/api/events/search?q=hurricanes` served `15302884`
"Hurricanes v Panthers" next to canonical `15312312` "Florida Panthers v
Carolina Hurricanes" at the same kickoff. This file guards the repair that takes
those rows back.

🔴 THE PROPERTY THAT MATTERS MOST HERE IS THAT THE REPAIR DOES NOT OWN A COPY OF
THE RULE. It calls the shipped screen, so the repair cannot decide a row is a
duplicate that the beat would revive again ten minutes later, and it cannot run
at all on a dyno that has not taken the #7594 release. `test_the_repair_asks_the
_shipped_screen_and_not_a_copy` is the whole of that guarantee: re-spell the
predicate here and the ordering the cert required silently stops being enforced.
"""

from __future__ import annotations

import argparse
import importlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event as sa_event, text as sa_text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.utils.event_completion import UNREACHABLE_SUSPENDED_TERMINAL


@pytest.fixture()
def repair():
    """The repair module, imported by path the way `scripts/` modules are."""
    return importlib.import_module(
        "scripts.repair_7594_revoid_published_reversed_twins"
    )


@pytest.fixture()
def restore():
    return importlib.import_module(
        "scripts.restore_7594_revoid_published_reversed_twins"
    )


def _args(**over):
    ns = argparse.Namespace(apply=False, backup=False)
    for k, v in over.items():
        setattr(ns, k, v)
    return ns


class TestTheGatesD51b:
    """A production write buys its unattended licence with a backup (D51(b))."""

    def test_apply_without_backup_is_refused(self, repair):
        refusal = repair.missing_backup_refusal(_args(apply=True))
        assert refusal is not None
        assert "--apply requires --backup" in refusal

    def test_backup_and_apply_together_pass_the_backup_gate(self, repair):
        assert repair.missing_backup_refusal(_args(apply=True, backup=True)) is None

    def test_a_plan_needs_no_backup(self, repair):
        assert repair.missing_backup_refusal(_args()) is None

    def test_a_write_off_the_producer_app_is_refused(self, repair, monkeypatch):
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
        refusal = repair.wrong_app_refusal(_args(apply=True, backup=True))
        assert refusal is not None
        assert "bainluck-heavy" in refusal

    def test_an_unset_app_is_refused_because_that_is_a_laptop(
        self, repair, monkeypatch
    ):
        """UNSET is the case the gate exists for, not the case it waves through."""
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
        refusal = repair.wrong_app_refusal(_args(apply=True, backup=True))
        assert refusal is not None
        assert "HEROKU_APP_NAME is unset" in refusal

    def test_the_producer_app_passes(self, repair, monkeypatch):
        monkeypatch.setenv("HEROKU_APP_NAME", repair.PRODUCER_APP)
        assert repair.wrong_app_refusal(_args(apply=True, backup=True)) is None

    def test_a_plan_is_allowed_anywhere(self, repair, monkeypatch):
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
        assert repair.wrong_app_refusal(_args()) is None

    def test_the_undo_earns_the_same_gate_by_importing_it(self, repair, restore):
        """Not a copy — the same function object, so the two cannot drift."""
        assert restore.wrong_app_refusal is repair.wrong_app_refusal


class TestTheRepairDoesNotOwnACopyOfTheRule:
    def test_the_repair_asks_the_shipped_screen_and_not_a_copy(self, repair):
        """The ordering the cert required is enforced by this identity alone.

        A pre-#7594 dyno's screen is orientation-blind, so it answers False for
        exactly this population and the repair selects nothing. That is only
        true while the repair calls the shipped function; a local re-spelling
        would happily take rows back that the beat then re-revives.
        """
        from app.tasks import espn_sync

        assert (
            repair._row_has_surviving_counterpart
            is espn_sync._row_has_surviving_counterpart
        )

    def test_the_scope_is_the_arms_own_ledger(self, repair):
        """Never the retirement predicate: 2,544 rows match it for other reasons."""
        from app.tasks.espn_sync import UNREACHABLE_SUSPENDED_BACKUP_TABLE

        assert repair.UNREACHABLE_SUSPENDED_BACKUP_TABLE == (
            UNREACHABLE_SUSPENDED_BACKUP_TABLE
        )

    def test_the_bank_is_named_for_this_repair(self, repair):
        assert repair.BANK_TABLE == "bak_7594_revoid_published_reversed_twins"


# ─── the screen's verdict on the real production shapes ──────────────────────
# Same rail as `TestTheScreenAgainstARealDatabase` in the #7260 file, and for the
# same reason: the repair's selector IS that statement, so a test that re-spells
# it is not testing the repair. `strpos` is Postgres; sqlite spells it `instr`.


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):  # pragma: no cover - test rail
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_sqlite(type_, compiler, **kw):  # pragma: no cover - test rail
    return "JSON"


class _AsyncShim:  # pragma: no cover - test rail
    def __init__(self, session):
        self._s = session

    async def execute(self, statement, params=None):
        if params is None:
            return self._s.execute(statement)
        return self._s.execute(statement, params)


START = datetime(2026, 10, 7, 23, 30, tzinfo=timezone.utc)


#: What `now()` answers on the sqlite rail. Before `START`, so the fixtures are
#: upcoming games and `candidates()`'s `commence_time > now()` admits them.
#: SQLAlchemy stores sqlite DATETIME as `YYYY-MM-DD HH:MM:SS.ffffff`, which
#: orders lexicographically, so a string of the same shape compares correctly.
NOW = "2026-10-07 20:00:00.000000"


def _database():
    from app.models.models import Base, Event, Sport, Team

    engine = create_engine("sqlite://")

    @sa_event.listens_for(engine, "connect")
    def _register(dbapi_conn, _record):  # pragma: no cover - test rail
        dbapi_conn.create_function(
            "strpos",
            2,
            lambda haystack, needle: (haystack or "").find(needle or "") + 1,
        )
        # `now()` and `to_regclass()` are Postgres. They are registered here
        # rather than in a second rail so that the tests which drive the whole
        # of `run()` use the SAME database as the screen tests above — one rail
        # per file, so a divergence between them cannot hide a defect.
        dbapi_conn.create_function("now", 0, lambda: NOW)
        dbapi_conn.create_function(
            "to_regclass",
            1,
            lambda name: _regclass(name),
        )

    Base.metadata.create_all(
        engine, tables=[Sport.__table__, Team.__table__, Event.__table__]
    )
    return Session(engine, expire_on_commit=False)


#: Tables `to_regclass` should answer for on the rail. `run()` asks it whether
#: the #7260 arm's ledger exists; the tests that want the "arm published
#: nothing" branch drop the name from this set instead of faking a result.
_REGCLASS_PRESENT: set[str] = set()


def _regclass(name):  # pragma: no cover - test rail
    bare = (name or "").split(".")[-1]
    return bare if bare in _REGCLASS_PRESENT else None


@pytest.fixture(autouse=True)
def _reset_regclass():
    """Module-level state is per-test state, or the order of the file decides.

    `_ledger` adds names to `_REGCLASS_PRESENT` and nothing removed them, so a
    later test asking for the "the arm published nothing here" branch would have
    silently got the opposite answer depending on which tests ran before it.
    """
    _REGCLASS_PRESENT.clear()
    yield
    _REGCLASS_PRESENT.clear()


def _world(*rows):
    """A database holding exactly the rows a test names.

    ``rows`` are ``(sport_key, home, away, status, offset)``. Returns the session
    and the Event objects in the order given.
    """
    from app.models.models import Event, Sport

    session = _database()
    sport_ids = {}
    made = []

    def sport_id(key):
        if key not in sport_ids:
            row = Sport(key=key, name=key, active=True)
            session.add(row)
            session.flush()
            sport_ids[key] = row.id
        return sport_ids[key]

    for key, home, away, status, offset in rows:
        e = Event(
            sport_id=sport_id(key),
            home_team_name=home,
            away_team_name=away,
            commence_time=START + offset,
            status=status,
        )
        session.add(e)
        made.append(e)
    session.flush()
    return session, made


async def _screen(session, subject):
    from app.tasks.espn_sync import _row_has_surviving_counterpart

    return await _row_has_surviving_counterpart(_AsyncShim(session), subject)


@pytest.mark.asyncio
class TestWhichPublishedRowsTheRepairSelects:
    async def test_the_production_specimen_is_selected(self):
        """`15309597` Penguins v Capitals, beside canonical `15169786`.

        The pair that was revived at 20:55Z on 2026-09-20 while its canonical
        sibling sat on the site — reversed sides, same minute, same sport family
        under two league keys.
        """
        session, (revived, _canonical) = _world(
            ("icehockey_other", "Penguins", "Capitals", "scheduled", timedelta()),
            (
                "icehockey_nhl",
                "Washington Capitals",
                "Pittsburgh Penguins",
                "scheduled",
                timedelta(),
            ),
        )
        assert await _screen(session, revived) is True

    async def test_a_genuine_orphan_is_left_alone(self):
        """`15308559` Predators v Maple Leafs had no counterpart anywhere.

        It is the row #7260 exists for, and the repair must not take it back.
        """
        session, (revived,) = _world(
            ("icehockey_other", "Predators", "Maple Leafs", "scheduled", timedelta()),
        )
        assert await _screen(session, revived) is False

    async def test_a_retired_sibling_is_not_a_survivor(self):
        """A reader cannot reach a voided row, so it is not a second card."""
        session, (revived, _dead) = _world(
            ("icehockey_other", "Penguins", "Capitals", "scheduled", timedelta()),
            (
                "icehockey_nhl",
                "Washington Capitals",
                "Pittsburgh Penguins",
                UNREACHABLE_SUSPENDED_TERMINAL,
                timedelta(),
            ),
        )
        assert await _screen(session, revived) is False

    async def test_a_different_fixture_at_the_same_minute_is_not_a_twin(self):
        session, (revived, _other) = _world(
            ("icehockey_other", "Avalanche", "Jets", "scheduled", timedelta()),
            (
                "icehockey_nhl",
                "Washington Capitals",
                "Pittsburgh Penguins",
                "scheduled",
                timedelta(),
            ),
        )
        assert await _screen(session, revived) is False


# ─── what the pass actually issues ───────────────────────────────────────────


class _Result:  # pragma: no cover - test rail
    def __init__(self, scalar=None, rowcount=0):
        self._scalar = scalar
        self.rowcount = rowcount

    def scalar(self):
        return self._scalar

    def scalar_one(self):
        return self._scalar


class _Recorder:  # pragma: no cover - test rail
    """A session that records SQL instead of running it."""

    def __init__(self, events):
        self.sql: list[str] = []
        self.committed = 0
        self.rolled_back = 0
        self._events = {e.id: e for e in events}

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.sql.append(sql)
        if "to_regclass" in sql:
            return _Result(scalar=True)
        if "count(*)" in sql:
            return _Result(scalar=0)
        if sql.strip().upper().startswith("UPDATE EVENTS"):
            return _Result(rowcount=1)
        return _Result()

    async def get(self, _model, pk):
        return self._events.get(pk)

    async def flush(self):
        return None

    async def commit(self):
        self.committed += 1

    async def rollback(self):
        self.rolled_back += 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    def inserts_into_bank(self, bank):
        return [s for s in self.sql if f"INSERT INTO {bank}" in s]

    def updates(self):
        return [s for s in self.sql if s.strip().upper().startswith("UPDATE EVENTS")]


def _event(event_id=15309597):
    from types import SimpleNamespace

    return SimpleNamespace(
        id=event_id,
        status="scheduled",
        home_team_name="Penguins",
        away_team_name="Capitals",
        commence_time=START,
    )


async def _run_with(repair, monkeypatch, args, events=None):
    """Drive `run()` over a recording session, with the screen forced to True."""
    import app.tasks.base as base

    events = events if events is not None else [_event()]
    recorder = _Recorder(events)
    # The producer-app gate is exercised on its own in `TestTheGatesD51b`; here
    # it is satisfied so these tests can reach the statements they are about.
    monkeypatch.setenv("HEROKU_APP_NAME", repair.PRODUCER_APP)
    monkeypatch.setattr(base, "get_task_session", lambda: recorder)

    async def _always_a_twin(_s, _e):
        return True

    monkeypatch.setattr(repair, "_row_has_surviving_counterpart", _always_a_twin)
    monkeypatch.setattr(
        repair, "candidates", lambda _s: _wrap([e.id for e in events])
    )
    code = await repair.run(args)
    return code, recorder


def _wrap(value):
    async def _coro():
        return value

    return _coro()


@pytest.mark.asyncio
class TestWhatThePassIssues:
    async def test_a_plan_commits_nothing_and_rolls_back(self, repair, monkeypatch):
        """The plan is the apply, discarded — so it must end in a rollback."""
        code, rec = await _run_with(repair, monkeypatch, _args())
        assert code == 0
        assert rec.rolled_back == 1
        assert rec.committed == 0

    async def test_a_plan_without_backup_never_touches_the_bank(
        self, repair, monkeypatch
    ):
        """A bare plan is the safest invocation and must not be the one that errors.

        The bank is created by `--backup`; inserting into it from a plan that
        never asked for one would fail the whole pass with `undefined_table`.
        """
        _code, rec = await _run_with(repair, monkeypatch, _args())
        assert rec.inserts_into_bank(repair.BANK_TABLE) == []

    async def test_a_plan_still_issues_the_update_it_predicts(
        self, repair, monkeypatch
    ):
        """Rolled back, but issued — otherwise the plan is not the apply.

        Each take-back changes the screen's answer for the row after it, so a
        plan that skipped the writes would print a list the apply does not
        reproduce.
        """
        _code, rec = await _run_with(repair, monkeypatch, _args())
        assert len(rec.updates()) == 1

    async def test_an_apply_banks_after_the_swap_it_won_and_commits(
        self, repair, monkeypatch
    ):
        """The bank follows the write, because the write is the claim.

        This assertion used to run the other way, on the reasoning that a bank
        entry preceding its write is what makes the write reversible. Both
        statements are in one transaction, so that ordering buys nothing —
        neither can commit without the other — and banking first is what let a
        lost compare-and-swap commit a bank row for a write that never landed
        (see `TestALostRaceBanksNothingAndIsNotReportedClean`).
        """
        code, rec = await _run_with(
            repair, monkeypatch, _args(apply=True, backup=True)
        )
        assert code == 0
        assert rec.committed >= 1
        assert rec.rolled_back == 0
        banked = rec.inserts_into_bank(repair.BANK_TABLE)
        assert len(banked) == 1
        assert rec.sql.index(banked[0]) > rec.sql.index(rec.updates()[0])

    async def test_the_write_is_a_compare_and_swap_on_the_status_read(
        self, repair, monkeypatch
    ):
        """A game that has gone `live` under us must be skipped, not overwritten."""
        _code, rec = await _run_with(
            repair, monkeypatch, _args(apply=True, backup=True)
        )
        update = rec.updates()[0]
        assert "status = :before" in update


@pytest.mark.asyncio
class TestAPairThatIsEntirelyOursKeepsOneRow:
    async def test_taking_the_first_back_makes_the_second_an_orphan(self):
        """The reason the loop flushes between rows.

        Both halves of this fixture were revived by the arm. Taking both back
        would delete the game from the site — the #7260 defect, reached from the
        other side — so the screen is re-asked against the live transaction and
        the second half then reads as an orphan and is kept.
        """
        session, (first, second) = _world(
            ("icehockey_other", "Penguins", "Capitals", "scheduled", timedelta()),
            (
                "icehockey_nhl",
                "Washington Capitals",
                "Pittsburgh Penguins",
                "scheduled",
                timedelta(),
            ),
        )

        # Each is the other's twin while both are live.
        assert await _screen(session, first) is True
        assert await _screen(session, second) is True

        # The loop takes the first back and flushes.
        first.status = UNREACHABLE_SUSPENDED_TERMINAL
        session.flush()

        # The second is now the only row a reader can reach, and is kept.
        assert await _screen(session, second) is False


# ─── the whole pass, over a real database, through a real lost race ──────────
# CERT-3194 required the run path be exercised "through `scheduled -> live`
# without a false-clean result". It cannot be done on `_Recorder`: that fake
# answers `rowcount=1` to every UPDATE, so a lost compare-and-swap is not
# representable on it and a test written there would pass against the defect.
# These drive `run()` over the sqlite rail, where the CAS is a real statement
# whose rowcount is whatever the data says.


class _AsyncSession:  # pragma: no cover - test rail
    """The async surface `run()` expects, over a session that really executes.

    `before_update` is invoked once, immediately before the first
    `UPDATE events` reaches the database — the instant a competing writer would
    land in production. It fires inside this transaction rather than a second
    connection because sqlite serialises writers; what the test needs is that
    the row's status has changed between the read and the compare-and-swap, and
    that is exactly what this produces.
    """

    def __init__(self, session, before_update=None):
        self._s = session
        self._before_update = before_update
        self.sql: list[str] = []

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.sql.append(sql)
        if sql.strip().upper().startswith("UPDATE EVENTS") and self._before_update:
            hook, self._before_update = self._before_update, None
            hook(self._s)
        return self._s.execute(statement, params if params is not None else {})

    async def get(self, model, pk):
        return self._s.get(model, pk)

    async def flush(self):
        self._s.flush()

    async def commit(self):
        self._s.commit()

    async def rollback(self):
        self._s.rollback()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


def _ledger(session, repair, ids):
    """Create the #7260 arm's ledger and record the ids it revived."""
    table = repair.UNREACHABLE_SUSPENDED_BACKUP_TABLE
    session.execute(sa_text(f"CREATE TABLE {table} (event_id INTEGER)"))
    for event_id in ids:
        session.execute(
            sa_text(f"INSERT INTO {table} (event_id) VALUES (:i)"), {"i": event_id}
        )
    session.flush()
    _REGCLASS_PRESENT.add(table)
    _REGCLASS_PRESENT.add(repair.BANK_TABLE)


def _a_revived_twin_and_its_canonical_row():
    """The production shape: one game, two cards, sides reversed."""
    return _world(
        ("icehockey_other", "Penguins", "Capitals", "scheduled", timedelta()),
        (
            "icehockey_nhl",
            "Washington Capitals",
            "Pittsburgh Penguins",
            "scheduled",
            timedelta(),
        ),
    )


async def _drive(module, monkeypatch, session, args, before_update=None):
    """Run a script's real `run()` over `session`, returning the async wrapper.

    `module` is the repair or the restore. The producer app is read off the
    repair either way, because the restore deliberately owns no copy of it — it
    imports `wrong_app_refusal`, which is the point of
    `test_the_undo_earns_the_same_gate_by_importing_it`.
    """
    import app.tasks.base as base

    producer = importlib.import_module(
        "scripts.repair_7594_revoid_published_reversed_twins"
    ).PRODUCER_APP

    shim = _AsyncSession(session, before_update=before_update)
    monkeypatch.setenv("HEROKU_APP_NAME", producer)
    monkeypatch.setattr(base, "get_task_session", lambda: shim)
    code = await module.run(args)
    return code, shim


def _bank_rows(session, repair):
    return session.execute(
        sa_text(f"SELECT event_id, status_before, status_after FROM {repair.BANK_TABLE}")
    ).all()


def _status(session, event_id):
    return session.execute(
        sa_text("SELECT status FROM events WHERE id = :i"), {"i": event_id}
    ).scalar()


@pytest.mark.asyncio
class TestALostRaceBanksNothingAndIsNotReportedClean:
    """CERT-3194's required repair, 7594-CONCURRENT-TAKEBACK-CANNOT-STRAND-OR-MISBANK."""

    async def test_the_control_a_clean_pass_really_does_bank_and_void(
        self, repair, monkeypatch, capsys
    ):
        """THE STRAWMAN GUARD. Without this the race tests prove nothing.

        Every assertion below is of the form "the bank is empty" / "the status
        did not move". A rig that silently selected no rows at all would satisfy
        all of them. This is the same rig with no competing writer, and it must
        take the row back and bank exactly one row.
        """
        session, (revived, _canonical) = _a_revived_twin_and_its_canonical_row()
        _ledger(session, repair, [revived.id])

        code, _shim = await _drive(
            session=session,
            module=repair,
            monkeypatch=monkeypatch,
            args=_args(apply=True, backup=True),
        )

        assert code == 0
        assert _status(session, revived.id) == UNREACHABLE_SUSPENDED_TERMINAL
        assert _bank_rows(session, repair) == [
            (revived.id, "scheduled", UNREACHABLE_SUSPENDED_TERMINAL)
        ]
        out = capsys.readouterr().out
        assert "took back 1" in out
        assert "NOT CLEAN" not in out

    async def test_a_row_that_goes_live_under_the_pass_is_not_banked(
        self, repair, monkeypatch, capsys
    ):
        """The misbank. The whole defect in one assertion.

        Under the old order the INSERT preceded the UPDATE, so this pass
        committed a bank row asserting a `status_after` it never wrote.
        """
        session, (revived, _canonical) = _a_revived_twin_and_its_canonical_row()
        _ledger(session, repair, [revived.id])

        def kickoff(s):
            s.execute(
                sa_text("UPDATE events SET status = 'live' WHERE id = :i"),
                {"i": revived.id},
            )

        code, _shim = await _drive(
            session=session,
            module=repair,
            monkeypatch=monkeypatch,
            args=_args(apply=True, backup=True),
            before_update=kickoff,
        )

        assert code == 0
        # The compare-and-swap correctly refused to overwrite the live row...
        assert _status(session, revived.id) == "live"
        # ...and nothing was banked for a write that never happened.
        assert _bank_rows(session, repair) == []
        assert "SKIPPED, moved under us" in capsys.readouterr().out

    async def test_the_lost_row_is_not_reported_as_a_clean_sweep(
        self, repair, monkeypatch, capsys
    ):
        """The false clean.

        `candidates()` filters `status = 'scheduled'`, and this row lost the
        swap precisely because something moved it out of `scheduled`. So the
        read-back counts zero and the pass's worst outcome would otherwise print
        as `0 revived rows remain ahead of their kickoff`.
        """
        session, (revived, _canonical) = _a_revived_twin_and_its_canonical_row()
        _ledger(session, repair, [revived.id])

        def kickoff(s):
            s.execute(
                sa_text("UPDATE events SET status = 'live' WHERE id = :i"),
                {"i": revived.id},
            )

        await _drive(
            session=session,
            module=repair,
            monkeypatch=monkeypatch,
            args=_args(apply=True, backup=True),
            before_update=kickoff,
        )

        out = capsys.readouterr().out
        # The misleading line is still printed — it is a true statement about
        # the `scheduled` population — but it is no longer the last word.
        assert "0 revived rows remain" in out
        assert "NOT CLEAN" in out
        # Named by id, and by where it actually went, which no population
        # predicate can hide.
        assert f"{revived.id} is now 'live'" in out

    async def test_the_undo_cannot_later_claim_a_row_the_repair_never_wrote(
        self, repair, restore, monkeypatch, capsys
    ):
        """The consequence CERT-3194 named, closed end to end.

        An orphan bank row is not inert. `restore_…` matches on
        `e.status = b.status_after` — what WE wrote — so once any other arm
        moves that event to the terminal status, an undo would match a row this
        repair never touched and put it back on `scheduled`, re-publishing the
        duplicate. With nothing banked there is nothing for it to match.
        """
        session, (revived, _canonical) = _a_revived_twin_and_its_canonical_row()
        _ledger(session, repair, [revived.id])

        def kickoff(s):
            s.execute(
                sa_text("UPDATE events SET status = 'live' WHERE id = :i"),
                {"i": revived.id},
            )

        await _drive(
            session=session,
            module=repair,
            monkeypatch=monkeypatch,
            args=_args(apply=True, backup=True),
            before_update=kickoff,
        )
        capsys.readouterr()

        # Some other arm now legitimately retires the event — the state the
        # orphan bank row would have falsely claimed the repair had written.
        session.execute(
            sa_text("UPDATE events SET status = :s WHERE id = :i"),
            {"s": UNREACHABLE_SUSPENDED_TERMINAL, "i": revived.id},
        )
        session.flush()

        code, _shim = await _drive(
            session=session,
            module=restore,
            monkeypatch=monkeypatch,
            args=_args(apply=True),
        )

        assert code == 0
        # NOT dragged back to `scheduled`.
        assert _status(session, revived.id) == UNREACHABLE_SUSPENDED_TERMINAL
        assert "restored 0" in capsys.readouterr().out
