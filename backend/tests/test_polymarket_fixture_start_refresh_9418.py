"""#9418: a near-kickoff Polymarket match is kept on the venue's CURRENT start.

The specimen is Angelini v Johns (ATP Challenger Bari, event 15319927) on
2026-09-28. Our row carried the 12:35Z start from the Polymarket listing; the
venue's own record (Gamma /events/1091219, read 17:21Z) said 13:50Z. The hourly
poll no longer reached the day-old listing, so the stamp the #6073 re-date reads
never moved, and the unobserved-tennis clock (start + 3.5h) suspended the row at
16:05Z in the middle of the third set. The match finished at 16:53Z.

The payload below is that record, trimmed to the fields the parser reads.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

from app.services.polymarket_api import PolymarketAPIService
from app.utils.event_completion import wall_clock_bound_hours
from app.utils.polymarket_fixture_start import (
    AGREEMENT_TOLERANCE,
    STAMP_VENUE_GAME_START_SQL,
    gamma_event_id_from_group,
    row_fixture_start,
    stamp_for,
)


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "TEXT"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "TEXT"


HOME = "Angelini"
AWAY = "Johns"
GROUP = "polymarket:1091219"
LISTING_START = datetime(2026, 9, 28, 12, 35, tzinfo=timezone.utc)
VENUE_START = datetime(2026, 9, 28, 13, 50, tzinfo=timezone.utc)
#: The string the poll wrote for the listing start, as stored on production.
STORED_STALE_STAMP = "2026-09-28T12:35:00+00:00"

SPECIMEN = {
    "id": "1091219",
    "title": "Bari: Lorenzo Angelini vs Garrett Johns",
    "slug": "atp-angelin-johns-2026-09-28",
    "gameId": 6340752,
    "live": False,
    "ended": True,
    "period": "FT",
    "score": "4-6, 7-6(7-4), 7-5",
    "startTime": "2026-09-28T13:50:00Z",
    "finishedTimestamp": "2026-09-28T16:53:42.411093Z",
    "startDate": "2026-09-27T11:05:30Z",
    "endDate": "2026-10-05T08:00:00Z",
    "markets": [
        {
            "question": "Bari: Lorenzo Angelini vs Garrett Johns",
            "gameStartTime": "2026-09-28 13:50:00+00",
        }
    ],
}

#: Sqlite has no jsonb; this is the same one-key merge in its dialect. The
#: Postgres statement itself is pinned by shape below and was run against a
#: local Postgres 14 (other keys kept, NULL metadata handled, other groups and
#: other sources untouched).
_SQLITE_STAMP_SQL = """
    UPDATE futures_markets
       SET market_metadata = json_set(COALESCE(market_metadata, '{}'),
                                      '$.venue_game_start', :stamp)
     WHERE group_id = :group_id
       AND source = 'polymarket'
       AND json_extract(market_metadata, '$.venue_game_start') IS NOT :stamp
"""


def _parse(payload):
    return PolymarketAPIService._parse_event(
        object.__new__(PolymarketAPIService), payload
    )


# ── pure ─────────────────────────────────────────────────────────────────────


def test_the_stamp_is_the_string_the_poll_writes():
    """Same parser, same ``isoformat()`` — so the poll, when it does reach the
    event again, writes an identical value and nothing churns."""
    instant = _parse(SPECIMEN).game_start_time
    assert instant == VENUE_START
    assert stamp_for(instant) == "2026-09-28T13:50:00+00:00"
    # The production stale value has the same shape, so IS DISTINCT FROM is a
    # comparison between like strings, not between two spellings of one instant.
    assert len(stamp_for(instant)) == len(STORED_STALE_STAMP)


@pytest.mark.parametrize(
    "group_id, expected",
    [
        ("polymarket:1091219", "1091219"),
        ("polymarket:abc", None),
        ("kalshi:KXATPCHALLENGERMATCH-26SEP28ANGJOH", None),
        (None, None),
    ],
)
def test_group_id_to_gamma_event_id(group_id, expected):
    assert gamma_event_id_from_group(group_id) == expected


def test_one_group_is_its_own_answer():
    assert row_fixture_start([VENUE_START]) == VENUE_START


def test_groups_that_agree_to_the_minute_decide():
    assert row_fixture_start([VENUE_START, VENUE_START + timedelta(seconds=30)]) == VENUE_START


def test_groups_a_real_distance_apart_hold_the_row():
    assert row_fixture_start([VENUE_START, VENUE_START + AGREEMENT_TOLERANCE]) is None


def test_a_group_with_no_instant_holds_the_row():
    assert row_fixture_start([VENUE_START, None]) is None
    assert row_fixture_start([]) is None


def test_the_stamp_merges_one_key_and_skips_an_agreeing_group():
    sql = " ".join(STAMP_VENUE_GAME_START_SQL.split())
    assert "COALESCE(market_metadata, '{}'::jsonb) || jsonb_build_object('venue_game_start'" in sql
    assert "IS DISTINCT FROM CAST(:stamp AS text)" in sql
    assert "source = 'polymarket'" in sql
    assert "updated_at" not in sql  # the poll's "last ingested" signal is not ours


def test_the_corrected_start_is_what_keeps_the_specimen_live_at_1605z():
    """The ship, at the level of the rule that suspended it: nothing about the
    bound changes, only the start it is measured from."""
    bound = wall_clock_bound_hours("tennis_other", 6.0, True) + 0.5
    at = datetime(2026, 9, 28, 16, 6, tzinfo=timezone.utc)
    assert (at - LISTING_START).total_seconds() / 3600 > bound  # what happened
    assert (at - VENUE_START).total_seconds() / 3600 < bound  # what now happens
    finished = datetime(2026, 9, 28, 16, 53, 42, tzinfo=timezone.utc)
    assert (finished - VENUE_START).total_seconds() / 3600 < bound


# ── the pass, on a real session ──────────────────────────────────────────────


class _AsyncShim:
    def __init__(self, session):
        self._s = session

    async def execute(self, statement, *a, **k):
        return self._s.execute(statement, *a, **k)

    def add(self, obj):
        self._s.add(obj)

    async def commit(self):
        self._s.commit()

    async def flush(self):
        self._s.flush()

    async def rollback(self):
        self._s.rollback()


class _Service:
    def __init__(self, payloads=(), fail=False):
        self.payloads = {str(p["id"]): p for p in payloads}
        self.fail = fail
        self.calls = []
        self.closed = False

    async def get_events_by_ids(self, ids):
        self.calls.append(list(ids))
        if self.fail:
            raise RuntimeError("gamma 503")
        return [self.payloads[i] for i in ids if i in self.payloads]

    def _parse_event(self, payload):
        return _parse(payload)

    async def close(self):
        self.closed = True


def _rail():
    from sqlalchemy import create_engine
    from sqlalchemy import event as sa_event
    from sqlalchemy.orm import Session

    from app.models.models import Base, Event, FuturesMarket, Sport, Team

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[Sport.__table__, Event.__table__, Team.__table__, FuturesMarket.__table__],
    )
    session = Session(engine, expire_on_commit=False)

    @sa_event.listens_for(session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    tennis = Sport(key="tennis_other", name="Tennis (other)")
    session.add(tennis)
    session.flush()
    return session, tennis


def _event(session, sport, *, commence=LISTING_START, source="polymarket_venue",
           status="live", completed_at=None, home=HOME, away=AWAY):
    from app.models.models import Event

    e = Event(
        sport_id=sport.id, home_team_name=home, away_team_name=away,
        commence_time=commence, commence_time_source=source, status=status,
        external_id=None, completed_at=completed_at,
    )
    session.add(e)
    session.flush()
    return e


def _market(session, event, *, group=GROUP, name="Bari: Lorenzo Angelini vs Garrett Johns",
            external_id="0x00a8", stamp=STORED_STALE_STAMP, event_id=True,
            group_type="polymarket_sub_market", status="open"):
    from app.models.models import FuturesMarket

    m = FuturesMarket(
        source="polymarket", external_id=external_id, name=name,
        category="game_prop", status=status,
        event_id=event.id if event_id else None,
        sport_id=event.sport_id, llm_sport_category="tennis",
        group_id=group, group_type=group_type,
        market_metadata={"venue_game_start": stamp, "event_title": "Bari"},
    )
    session.add(m)
    session.commit()
    return m


def _specimen_rows(session, sport, **event_kw):
    event = _event(session, sport, **event_kw)
    parent = _market(session, event, external_id="1091219-parent", event_id=False,
                     group_type="polymarket_event")
    child = _market(session, event)
    return event, parent, child


async def _run(monkeypatch, session, service, now):
    from app.tasks import polymarket_fixture_start_refresh as mod

    @asynccontextmanager
    async def _session_ctx():
        yield _AsyncShim(session)

    monkeypatch.setattr(mod, "get_task_session", _session_ctx)
    monkeypatch.setattr(mod, "STAMP_VENUE_GAME_START_SQL", _SQLITE_STAMP_SQL)
    stats = await mod._refresh_polymarket_fixture_starts(service=service, now=now)
    session.expire_all()
    return stats


def _stamps(session):
    from app.models.models import FuturesMarket

    return sorted(
        (m.market_metadata or {}).get("venue_game_start")
        for m in session.query(FuturesMarket).all()
    )


@pytest.mark.asyncio
async def test_the_specimen_moves_to_the_venue_start_and_stays_live(monkeypatch):
    session, sport = _rail()
    event, _parent, _child = _specimen_rows(session, sport)
    service = _Service([SPECIMEN])

    stats = await _run(monkeypatch, session, service, datetime(2026, 9, 28, 14, 5, tzinfo=timezone.utc))

    from app.models.models import Event

    row = session.get(Event, event.id)
    assert row.commence_time.replace(tzinfo=timezone.utc) == VENUE_START
    assert row.status == "live"
    assert row.commence_time_source == "polymarket_venue"
    assert stats["redated"] == 1 and stats["redated_and_unstarted"] == 0
    assert service.calls == [["1091219"]]
    # Parent AND child carry the venue instant, so Phase 1.5 — reading the
    # parent first — agrees with this write instead of moving it back.
    assert _stamps(session) == ["2026-09-28T13:50:00+00:00"] * 2
    assert stats["groups_stamped"] == 1 and stats["rows_stamped"] == 2
    # Every other metadata key survives the merge.
    from app.models.models import FuturesMarket

    assert all(m.market_metadata.get("event_title") == "Bari"
               for m in session.query(FuturesMarket).all())


@pytest.mark.asyncio
async def test_a_row_live_by_the_clock_before_the_venue_start_is_unstarted(monkeypatch):
    """12:50Z: the row went LIVE at the listing's 12:35Z for a match the venue
    starts at 13:50Z — the Piros v Hassan shape. It goes back to scheduled."""
    session, sport = _rail()
    event, *_ = _specimen_rows(session, sport)

    stats = await _run(monkeypatch, session, _Service([SPECIMEN]),
                       datetime(2026, 9, 28, 12, 50, tzinfo=timezone.utc))

    from app.models.models import Event

    row = session.get(Event, event.id)
    assert row.status == "scheduled"
    assert row.commence_time.replace(tzinfo=timezone.utc) == VENUE_START
    assert stats["redated_and_unstarted"] == 1


@pytest.mark.asyncio
async def test_an_agreeing_row_writes_nothing(monkeypatch):
    session, sport = _rail()
    event = _event(session, sport, commence=VENUE_START)
    _market(session, event, stamp="2026-09-28T13:50:00+00:00")

    stats = await _run(monkeypatch, session, _Service([SPECIMEN]),
                       datetime(2026, 9, 28, 14, 5, tzinfo=timezone.utc))

    assert stats["redated"] == 0
    assert stats["groups_stamped"] == 0 and stats["rows_stamped"] == 0


@pytest.mark.parametrize("source", ["espn", "statpal", "odds_api", None])
@pytest.mark.asyncio
async def test_a_row_polymarket_does_not_date_is_never_read(monkeypatch, source):
    session, sport = _rail()
    event, *_ = _specimen_rows(session, sport, source=source)
    service = _Service([SPECIMEN])

    stats = await _run(monkeypatch, session, service, datetime(2026, 9, 28, 14, 5, tzinfo=timezone.utc))

    from app.models.models import Event

    assert service.calls == []
    assert stats["candidates"] == 0
    assert session.get(Event, event.id).commence_time.replace(tzinfo=timezone.utc) == LISTING_START
    assert _stamps(session) == [STORED_STALE_STAMP] * 2


@pytest.mark.parametrize("status", ["completed", "suspended"])
@pytest.mark.asyncio
async def test_a_finished_row_is_never_read(monkeypatch, status):
    """A completion is the row's own verdict, whatever the status beside it."""
    session, sport = _rail()
    _specimen_rows(session, sport, status=status,
                   completed_at=datetime(2026, 9, 28, 16, 53, tzinfo=timezone.utc))
    service = _Service([SPECIMEN])

    stats = await _run(monkeypatch, session, service, datetime(2026, 9, 28, 17, 0, tzinfo=timezone.utc))

    assert service.calls == [] and stats["candidates"] == 0


@pytest.mark.asyncio
async def test_a_row_outside_the_window_is_never_read(monkeypatch):
    session, sport = _rail()
    _specimen_rows(session, sport, commence=LISTING_START + timedelta(days=3))
    service = _Service([SPECIMEN])

    stats = await _run(monkeypatch, session, service, datetime(2026, 9, 28, 14, 5, tzinfo=timezone.utc))

    assert service.calls == [] and stats["candidates"] == 0


@pytest.mark.asyncio
async def test_an_unreadable_batch_holds_the_row_and_writes_nothing(monkeypatch):
    session, sport = _rail()
    event, *_ = _specimen_rows(session, sport)

    stats = await _run(monkeypatch, session, _Service([SPECIMEN], fail=True),
                       datetime(2026, 9, 28, 14, 5, tzinfo=timezone.utc))

    from app.models.models import Event

    assert stats["batches_unreadable"] == 1 and stats["held_unreadable"] == 1
    assert session.get(Event, event.id).commence_time.replace(tzinfo=timezone.utc) == LISTING_START
    assert _stamps(session) == [STORED_STALE_STAMP] * 2


@pytest.mark.asyncio
async def test_a_record_gamma_did_not_return_holds_the_row(monkeypatch):
    session, sport = _rail()
    event, *_ = _specimen_rows(session, sport)

    stats = await _run(monkeypatch, session, _Service([]),
                       datetime(2026, 9, 28, 14, 5, tzinfo=timezone.utc))

    from app.models.models import Event

    assert stats["held_disagreeing"] == 1 and stats["redated"] == 0
    assert session.get(Event, event.id).commence_time.replace(tzinfo=timezone.utc) == LISTING_START


@pytest.mark.asyncio
async def test_two_groups_publishing_two_starts_hold_the_row(monkeypatch):
    session, sport = _rail()
    event, *_ = _specimen_rows(session, sport)
    _market(session, event, group="polymarket:1091300", external_id="0xmore",
            name="Angelini vs. Johns: Match O/U 22.5")
    other = dict(SPECIMEN, id="1091300", startTime="2026-09-28T18:00:00Z",
                 markets=[{"question": "x", "gameStartTime": "2026-09-28 18:00:00+00"}])

    stats = await _run(monkeypatch, session, _Service([SPECIMEN, other]),
                       datetime(2026, 9, 28, 14, 5, tzinfo=timezone.utc))

    from app.models.models import Event

    assert stats["held_disagreeing"] == 1 and stats["redated"] == 0
    assert session.get(Event, event.id).commence_time.replace(tzinfo=timezone.utc) == LISTING_START
    assert STORED_STALE_STAMP in _stamps(session)  # a held group is left as the poll wrote it


@pytest.mark.asyncio
async def test_a_market_about_two_other_players_never_redates_the_row(monkeypatch):
    """The #6073 pairing check, asked verbatim: the start is not written onto an
    event whose players the market does not name."""
    session, sport = _rail()
    event = _event(session, sport, home="Piros", away="Hassan")
    _market(session, event)

    stats = await _run(monkeypatch, session, _Service([SPECIMEN]),
                       datetime(2026, 9, 28, 14, 5, tzinfo=timezone.utc))

    from app.models.models import Event

    assert stats["refused_link"] == 1 and stats["redated"] == 0
    assert session.get(Event, event.id).commence_time.replace(tzinfo=timezone.utc) == LISTING_START


def test_the_pass_is_scheduled_on_heavy_every_five_minutes():
    from app.tasks import celery_app

    entry = celery_app.conf.beat_schedule["refresh-polymarket-fixture-starts"]
    assert entry["task"] == "app.tasks.refresh_polymarket_fixture_starts"
    assert entry["options"]["queue"] == "heavy"
    # Offset two minutes from the #3017 sibling so the two Gamma reads do not
    # land on the same minute.
    assert entry["schedule"].minute == set(range(2, 60, 5))
    assert "app.tasks.refresh_polymarket_fixture_starts" in celery_app.tasks
