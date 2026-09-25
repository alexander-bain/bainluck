"""#3023: the one schedule move the nightly sentinel may make without a person.

NHL opening week, measured 2026-09-25: five anchored rows stood at midnight
Eastern (04:00Z) while their own ESPN anchors had published the real puck-drop
the same evening. The scheduled ESPN pass refuses the move (19-22 hours is wider
than #1947's 12-hour window) and the live pass only makes it on game day, so the
stand-in sat on the page from announcement to game day, and a StatPal-created
row beside it printed the game twice.

The class is narrow on purpose, and every clause of it is guarded here with
BOTH arms: the specimen that must move, and the near-miss that must not. The
near-misses are the ways a sloppier predicate goes wrong — a UTC hour instead of
the Eastern wall clock, a UTC date instead of the Eastern one, a re-date passed
off as an announcement.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.tasks import reconcile_anchor_schedule as rail
from app.utils.anchor_schedule import (
    AUTHORITY_MOVES_US,
    TEAMS_DISAGREE,
    AnchoredRow,
    is_midnight_placeholder_move,
    schedule_decision,
)
from app.utils.authority_id_collisions import AuthorityRecord

UTC = timezone.utc

#: Midnight EDT on Thursday 2026-10-01 — the stand-in #3023's NHL rows carried.
MIDNIGHT_EDT = datetime(2026, 10, 1, 4, 0, tzinfo=UTC)
#: Midnight EST on Sunday 2026-12-27 — the NFL rows stand at 05:00Z in winter.
MIDNIGHT_EST = datetime(2026, 12, 27, 5, 0, tzinfo=UTC)


def _row(commence_time, *, event_id=15316001, espn_id="401802001", **overrides):
    base = dict(
        event_id=event_id,
        sport_key="icehockey_nhl",
        home_team_name="Buffalo Sabres",
        away_team_name="New York Rangers",
        espn_id=espn_id,
        commence_time=commence_time,
        status="scheduled",
        completed_at=None,
        commence_time_source="espn",
    )
    base.update(overrides)
    return AnchoredRow(**base)


def _record(starts_at, *, espn_id="401802001", home="buffalo sabres", away="new york rangers"):
    return AuthorityRecord(
        authority_id=espn_id,
        home_names=frozenset({home}),
        away_names=frozenset({away}),
        starts_at=starts_at,
        label="Buffalo Sabres v New York Rangers",
    )


def _decide(ours, theirs, **record_kw):
    return schedule_decision(_row(ours), _record(theirs, **record_kw))


class TestTheSpecimenMoves:
    def test_midnight_edt_to_the_announced_evening_puck_drop(self):
        d = _decide(MIDNIGHT_EDT, datetime(2026, 10, 1, 23, 0, tzinfo=UTC))
        assert d.verdict == AUTHORITY_MOVES_US
        assert is_midnight_placeholder_move(d)

    def test_a_late_start_whose_UTC_date_is_the_next_day_is_the_same_eastern_date(self):
        """22:00 EDT is 02:00Z on 10-02. A UTC-date test refuses it; the rows
        #3023 measured included exactly this move (04:00Z -> 02:00Z next day)."""
        d = _decide(MIDNIGHT_EDT, datetime(2026, 10, 2, 2, 0, tzinfo=UTC))
        assert is_midnight_placeholder_move(d)

    def test_winter_midnight_is_05Z(self):
        d = _decide(MIDNIGHT_EST, datetime(2026, 12, 27, 18, 0, tzinfo=UTC))
        assert is_midnight_placeholder_move(d)


class TestEveryNearMissStaysAttended:
    def test_04Z_in_winter_is_11pm_the_night_before_not_a_placeholder(self):
        """A UTC-hour predicate ("04:00Z") would call this a stand-in."""
        ours = datetime(2026, 12, 27, 4, 0, tzinfo=UTC)
        d = _decide(ours, datetime(2026, 12, 27, 18, 0, tzinfo=UTC))
        assert d.verdict == AUTHORITY_MOVES_US
        assert not is_midnight_placeholder_move(d)

    def test_a_move_to_another_eastern_date_is_a_re_date(self):
        d = _decide(MIDNIGHT_EDT, datetime(2026, 10, 2, 23, 0, tzinfo=UTC))
        assert d.verdict == AUTHORITY_MOVES_US
        assert not is_midnight_placeholder_move(d)

    def test_a_move_to_the_evening_before_is_a_re_date(self):
        d = _decide(MIDNIGHT_EDT, datetime(2026, 9, 30, 23, 0, tzinfo=UTC))
        assert d.verdict == AUTHORITY_MOVES_US
        assert not is_midnight_placeholder_move(d)

    @pytest.mark.parametrize("minute,second", [(5, 0), (0, 30)])
    def test_a_start_that_is_not_exactly_midnight_is_somebodys_answer(self, minute, second):
        ours = MIDNIGHT_EDT.replace(minute=minute, second=second)
        d = _decide(ours, datetime(2026, 10, 1, 23, 0, tzinfo=UTC))
        assert d.verdict == AUTHORITY_MOVES_US
        assert not is_midnight_placeholder_move(d)

    def test_teams_that_disagree_never_qualify_however_the_clock_reads(self):
        d = _decide(
            MIDNIGHT_EDT,
            datetime(2026, 10, 1, 23, 0, tzinfo=UTC),
            home="boston bruins",
            away="montreal canadiens",
        )
        assert d.verdict == TEAMS_DISAGREE
        assert not is_midnight_placeholder_move(d)

    def test_an_inverted_orientation_waits_for_a_person(self):
        d = _decide(
            MIDNIGHT_EDT,
            datetime(2026, 10, 1, 23, 0, tzinfo=UTC),
            home="new york rangers",
            away="buffalo sabres",
        )
        assert d.verdict == AUTHORITY_MOVES_US and d.orientation_inverted
        assert not is_midnight_placeholder_move(d)

    def test_an_outranked_clock_never_qualifies(self):
        d = schedule_decision(
            _row(MIDNIGHT_EDT, commence_time_source="mlb_schedule_repair"),
            _record(datetime(2026, 10, 1, 23, 0, tzinfo=UTC)),
        )
        assert d.verdict != AUTHORITY_MOVES_US
        assert not is_midnight_placeholder_move(d)


# ---------------------------------------------------------------------------
# The rail: a narrowed apply writes the class and reports everything else.
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, rowcount):
        self.rowcount = rowcount


class _Session:
    def __init__(self):
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(1)

    async def commit(self):
        pass

    async def rollback(self):
        pass


PLACEHOLDER_ID, REDATE_ID = 15316001, 14780595


@pytest.fixture
def mixed_page(monkeypatch):
    """One placeholder row and one 98-day re-date (#2804's charter case)."""
    rows = [
        _row(MIDNIGHT_EDT),
        _row(
            datetime(2026, 9, 11, 0, 35, tzinfo=UTC),
            event_id=REDATE_ID,
            espn_id="401873124",
        ),
    ]
    records = {
        "401802001": _record(datetime(2026, 10, 1, 23, 0, tzinfo=UTC)),
        "401873124": _record(
            datetime(2026, 12, 18, 1, 15, tzinfo=UTC), espn_id="401873124"
        ),
    }
    saved: list[dict] = []

    async def _load_rows(session, **kwargs):
        return list(rows)

    async def _count_eligible(session, **kwargs):
        return len(rows)

    async def _fetch_record(service, sport_keys, authority_id):
        return records.get(authority_id)

    async def _save(identity, payload):
        saved.append({"identity": identity, "planned": list(payload.get("rows_planned", []))})
        return True, "ok"

    async def _co_commit(session, identity, payload):
        saved.append({"identity": identity, "rows": [dict(r) for r in payload["rows"]]})
        return True, "ok"

    monkeypatch.setattr(rail, "_load_rows", _load_rows)
    monkeypatch.setattr(rail, "_count_eligible", _count_eligible)
    monkeypatch.setattr("app.tasks.repair_authority_id_collisions._fetch_record", _fetch_record)
    monkeypatch.setattr("app.services.espn_api.get_espn_service", lambda: object())
    monkeypatch.setattr(rail, "_save_undo", _save)
    monkeypatch.setattr(rail, "_save_undo_co_commit", _co_commit)
    return saved


def _written_ids(session):
    ids = []
    for statement in session.statements:
        if "UPDATE events" in str(statement):
            ids.append(statement.compile().params["id_1"])
    return ids


class TestTheRailWritesOnlyTheNarrowedClass:
    async def test_the_placeholder_is_written_and_the_re_date_is_only_reported(
        self, mixed_page
    ):
        session = _Session()
        result = await rail.reconcile(
            session, apply=True, apply_only=is_midnight_placeholder_move
        )
        assert _written_ids(session) == [PLACEHOLDER_ID]
        assert result["moved_event_ids"] == [PLACEHOLDER_ID]
        assert {m["event_id"] for m in result["moves"]} == {PLACEHOLDER_ID, REDATE_ID}
        # The re-date is as wrong as it was: the apply did not complete anything.
        assert result["terminal"] == "plan_only"
        # The undo record plans and receipts ONLY what the class allowed.
        assert [r["event_id"] for r in mixed_page[0]["planned"]] == [PLACEHOLDER_ID]
        assert [r["event_id"] for r in mixed_page[-1]["rows"]] == [PLACEHOLDER_ID]
        assert "undo_command" in result

    async def test_CONTROL_an_unfiltered_apply_writes_both(self, mixed_page):
        session = _Session()
        result = await rail.reconcile(session, apply=True)
        assert sorted(_written_ids(session)) == sorted([PLACEHOLDER_ID, REDATE_ID])
        assert result["terminal"] == "complete"

    async def test_a_dry_run_names_no_moved_rows(self, mixed_page):
        session = _Session()
        result = await rail.reconcile(session, apply=False)
        assert _written_ids(session) == []
        assert result["moved_event_ids"] == []
        assert result["terminal"] == "plan_only"
