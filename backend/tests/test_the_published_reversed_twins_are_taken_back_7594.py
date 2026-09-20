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
from sqlalchemy import create_engine, event as sa_event
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

    Base.metadata.create_all(
        engine, tables=[Sport.__table__, Team.__table__, Event.__table__]
    )
    return Session(engine, expire_on_commit=False)


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

    async def test_an_apply_banks_before_it_writes_and_commits(
        self, repair, monkeypatch
    ):
        code, rec = await _run_with(
            repair, monkeypatch, _args(apply=True, backup=True)
        )
        assert code == 0
        assert rec.committed >= 1
        assert rec.rolled_back == 0
        banked = rec.inserts_into_bank(repair.BANK_TABLE)
        assert len(banked) == 1
        # The bank entry precedes the write it makes reversible.
        assert rec.sql.index(banked[0]) < rec.sql.index(rec.updates()[0])

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
