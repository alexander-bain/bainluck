"""#9827 rung 2 (CERT-3864) — an EXISTING esports row takes its ticker's start.

## The block this answers

CERT-3864 BLOCKed `3f303ee1c2`: its mint arm dates a NEW esports row at the
ticker's HHMM, but `/events/15321207` already existed — minted from Kalshi's
expected expiration (14:30Z) — and a linked market never re-enters the
registry. #4965's ±3h fixture guard then refuses Polymarket's winner (10:30Z)
on it, so the named page stayed four hours late and Kalshi-only. Required
repair `9827-EXISTING-ESPORTS-ROW-RETIME`: correct eligible existing
open/scheduled esports rows from their linked Kalshi HHMM ticker, with
provenance and ambiguity/refusal bounds, and prove through the real combined
matcher path that the 14:30Z specimen becomes 10:30Z and its Polymarket
moneyline links without minting a duplicate.

## What this file gates

* the ship, end to end on a real database: the real `_phase15_revalidate`
  re-dates the specimen, and the real `_attempt_market` — real
  `_find_matching_event`, real `_try_link_market` — then joins Polymarket's
  winner onto THAT row, with no second row; and the same join, asked BEFORE
  the re-date, refuses (the control that proves the re-date is what moved it);
* reach: the arm's own probe slice claims the specimen, so it does not wait on
  the rotation;
* the bounds, each alone: provenance (only Kalshi's expiration is corrected,
  stamped `kalshi_ticker_time`), status (`scheduled` only), direction (earlier
  only), the esports window, the family, a date-only ticker, a link naming the
  wrong teams, two tickers or a Polymarket fixture naming another instant;
* idempotence: a second pass writes nothing;
* the authority door: the correction is directional.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

from app.services.event_registry import (
    commence_time_write_authorized,
    kalshi_ticker_time_corrects_a_kalshi_expiration,
)
from app.tasks import prediction_market_matching as pmm
from app.utils import match_receipts as _receipts
from app.utils.event_completion import KALSHI_TICKER_TIME_COMMENCE_SOURCE


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "TEXT"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "TEXT"


UTC = timezone.utc
# ── The production specimen (read 2026-09-30 12:37Z) ─────────────────────────
ROW = 15321207
HOME, AWAY = "Passion Academy", "Revenge"
TICKER = "KXCS2GAME-26OCT010630PSNAREV"
REAL_START = datetime(2026, 10, 1, 10, 30, tzinfo=UTC)  # 06:30 EDT
EXPECTED_EXPIRATION = datetime(2026, 10, 1, 14, 30, tzinfo=UTC)  # what the row held
PRODUCTION_KALSHI_LEGS = (
    (TICKER, "Passion Academy vs. Revenge"),
    ("KXCS2MAP-26OCT010630PSNAREV-1", "Passion Academy vs. Revenge: Map 1"),
    ("KXCS2MAP-26OCT010630PSNAREV-2", "Passion Academy vs. Revenge: Map 2"),
    ("KXCS2TOTALMAPS-26OCT010630PSNAREV", "Passion Academy vs. Revenge: Total Maps"),
)
PM_WINNER = "Counter-Strike: Revenge vs Passion Academy (BO3) - United21 Group B"
NOW = datetime(2026, 9, 30, 12, 37, tzinfo=UTC)


class _AsyncShim:
    """Async surface over a real sync session (no aiosqlite in this sandbox)."""

    def __init__(self, session):
        self._s = session

    async def execute(self, statement, *a, **k):
        return self._s.execute(statement, *a, **k)

    def add(self, obj):
        self._s.add(obj)

    async def commit(self):
        self._s.commit()

    async def rollback(self):
        self._s.rollback()

    async def flush(self):
        self._s.flush()

    def begin_nested(self):
        return self._s.begin_nested()

    async def refresh(self, obj, *a, **k):
        self._s.refresh(obj, *a, **k)

    async def get(self, *a, **k):
        return self._s.get(*a, **k)

    def __getattr__(self, name):
        return getattr(self._s, name)


def _new_rail():
    from sqlalchemy import create_engine
    from sqlalchemy import event as sa_event
    from sqlalchemy.orm import Session

    from app.models.models import Base

    engine = create_engine("sqlite://")

    # `_find_matching_event`'s name prefilter is Postgres SQL (`strpos`,
    # `translate`). Registered here with Postgres' semantics so the REAL finder
    # runs on this rail rather than a stub of it.
    @sa_event.listens_for(engine, "connect")
    def _postgres_functions(dbapi_conn, _record):  # pragma: no cover - rail
        dbapi_conn.create_function(
            "strpos", 2,
            lambda hay, needle: None if hay is None or needle is None
            else hay.find(needle) + 1,
        )
        dbapi_conn.create_function(
            "translate", 3,
            lambda s, frm, to: None if s is None
            else s.translate({ord(c): (to[i] if i < len(to) else None)
                              for i, c in enumerate(frm)}),
        )

    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)

    @sa_event.listens_for(session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=UTC)

    from app.models.models import Sport

    esports = Sport(key="esports", name="Esports")
    session.add(esports)
    session.flush()
    return session, esports


def _event(session, sport, *, commence=EXPECTED_EXPIRATION, source="kalshi",
           status="scheduled", home=HOME, away=AWAY, event_id=ROW):
    from app.models.models import Event

    e = Event(
        id=event_id, sport_id=sport.id, home_team_name=home, away_team_name=away,
        commence_time=commence, commence_time_source=source, status=status,
        external_id=None,
    )
    session.add(e)
    session.flush()
    return e


def _kalshi(session, event, *, ticker=TICKER, side="PSNA",
            name=f"{HOME} vs. {AWAY}"):
    from app.models.models import FuturesMarket

    m = FuturesMarket(
        source="kalshi", external_id=f"{ticker}-{side}" if side else ticker,
        name=name,
        category="game", status="open", event_id=event.id,
        sport_id=event.sport_id, llm_sport_category="esports",
        commence_time=EXPECTED_EXPIRATION, market_metadata={},
    )
    session.add(m)
    session.commit()
    return m


def _polymarket(session, *, event_id=None, venue_start=REAL_START,
                external_id="0x71dc04570c0888c7ed82"):
    from app.models.models import FuturesMarket

    m = FuturesMarket(
        source="polymarket", external_id=external_id, name=PM_WINNER,
        category="game_prop", status="open", event_id=event_id,
        llm_sport_category="esports",
        group_id="polymarket:1107298", group_type="polymarket_sub_market",
        commence_time=None,
        market_metadata={
            "content_understanding_v1": {
                "v": 1, "semantic_type": "moneyline", "venue_type": "moneyline",
                "agreement": "corroborated", "rule": "content_understanding@5273",
            },
            "venue_game_start": venue_start.isoformat(),
            "polymarket_event_id": "1107298",
        },
    )
    session.add(m)
    session.commit()
    return m


def _stats():
    return {
        "markets_scanned": 0,
        "newly_linked": 0,
        "orphaned_snapshots_deleted": 0,
        "errors": [],
        "funnel": {
            "stale_relinked": 0, "mislink_fixed": 0,
            "not_game_level": 0, "sample_not_game_level": [],
            "linked": 0, "no_matchup_extracted": 0, "game_level_detected": 0,
            "no_event_found": 0, "sample_game_level_no_event": [],
        },
    }


async def _run_phase15(session):
    stats = _stats()
    await pmm._phase15_revalidate(_AsyncShim(session), stats, NOW, lambda: 600.0, [])
    session.commit()
    return stats


async def _attempt(session, market):
    stats, queue, receipts = _stats(), [], []
    await pmm._attempt_market(
        _AsyncShim(session), market, stats, NOW, queue, lambda: 600.0,
        receipts, _receipts.PHASE_PASS2_GENERAL,
    )
    session.commit()
    return stats, receipts[0]


def _event_count(session):
    from app.models.models import Event

    return session.execute(select(func.count()).select_from(Event)).scalar_one()


def _refresh(session, obj):
    """`refresh` does not fire `loaded_as_persistent`; re-attach UTC the same way
    (production columns are timestamptz, SQLite hands back naive values)."""
    session.refresh(obj)
    for attr, value in list(obj.__dict__.items()):
        if isinstance(value, datetime) and value.tzinfo is None:
            obj.__dict__[attr] = value.replace(tzinfo=UTC)


def _start(session, event):
    _refresh(session, event)
    return event.commence_time.replace(tzinfo=UTC), event.commence_time_source


# ═══ 1. The ship, through the real combined path ════════════════════════════


@pytest.mark.asyncio
async def test_the_specimen_is_redated_and_polymarket_then_joins_it_without_a_twin():
    session, esports = _new_rail()
    event = _event(session, esports)
    # The four Kalshi rows linked to 15321207 on production, verbatim (read
    # 2026-09-30 13:1xZ): the game leg, both map legs and total maps share the
    # match's one ticker token.
    for ticker, name in PRODUCTION_KALSHI_LEGS:
        _kalshi(session, event, ticker=ticker, side=None, name=name)
    winner = _polymarket(session)

    # CONTROL, before the re-date: the real join refuses the 4h-late row and
    # may not mint — the page is Kalshi-only, exactly what the reader saw.
    _stats_before, receipt_before = await _attempt(session, winner)
    _refresh(session, winner)
    assert winner.event_id is None
    assert receipt_before.outcome != _receipts.OUTCOME_LINKED
    assert _event_count(session) == 1

    stats = await _run_phase15(session)

    assert _start(session, event) == (REAL_START, KALSHI_TICKER_TIME_COMMENCE_SOURCE)
    assert event.status == "scheduled"
    assert stats["funnel"]["phase15_kalshi_esports_ticker_corrected"] == 1
    assert stats["funnel"]["phase15_esports_ticker_candidates"] == 4

    _stats_after, receipt_after = await _attempt(session, winner)
    _refresh(session, winner)
    assert receipt_after.outcome == _receipts.OUTCOME_LINKED
    assert winner.event_id == ROW
    assert _event_count(session) == 1, "the join minted a second row"


@pytest.mark.asyncio
async def test_a_second_pass_writes_nothing():
    session, esports = _new_rail()
    event = _event(session, esports)
    _kalshi(session, event)
    await _run_phase15(session)

    stats = await _run_phase15(session)

    assert _start(session, event) == (REAL_START, KALSHI_TICKER_TIME_COMMENCE_SOURCE)
    assert stats["funnel"]["phase15_esports_ticker_candidates"] == 0
    assert not any(
        k.startswith("phase15_kalshi_esports_ticker_") for k in stats["funnel"]
    )


# ═══ 2. Reach: the probe claims the specimen ════════════════════════════════


def test_the_probe_claims_the_specimen_and_orders_it_soonest_first():
    later = EXPECTED_EXPIRATION + timedelta(hours=5)
    rows = [
        (2, "KXCS2GAME-26OCT011130AAABBB-AAA", later, "kalshi", "scheduled"),
        (1, f"{TICKER}-PSNA", EXPECTED_EXPIRATION, "kalshi", "scheduled"),
        # Already corrected: the probe's own band excludes it in SQL, and the
        # predicate refuses it here too.
        (3, f"{TICKER}-REV", REAL_START, KALSHI_TICKER_TIME_COMMENCE_SOURCE, "scheduled"),
    ]
    assert pmm._phase15_esports_ticker_candidate_ids(rows) == [1, 2]


@pytest.mark.asyncio
async def test_the_probe_reads_the_specimen_off_a_real_database():
    session, esports = _new_rail()
    event = _event(session, esports)
    market = _kalshi(session, event)
    other_sport_event = _event(
        session, esports, event_id=ROW + 1, home="X", away="Y",
        source="odds_api",
    )
    _kalshi(session, other_sport_event, ticker="KXCS2GAME-26OCT010630XXXYYY", name="X vs. Y")

    rows = session.execute(pmm._phase15_esports_ticker_probe_query(NOW)).all()

    assert [r[0] for r in rows] == [market.id]


# ═══ 3. The bounds, each alone ══════════════════════════════════════════════


def _pure(ticker=f"{TICKER}-PSNA", *, commence=EXPECTED_EXPIRATION,
          source="kalshi", status="scheduled", market_source="kalshi"):
    return pmm.kalshi_esports_ticker_redate(
        SimpleNamespace(source=market_source, external_id=ticker),
        SimpleNamespace(
            commence_time=commence, commence_time_source=source, status=status,
        ),
    )


def test_the_pure_rule_on_the_specimen():
    assert _pure() == REAL_START
    assert _pure(source="kalshi_occurrence") == REAL_START
    # the map leg shares the match's token and its instant
    assert _pure("KXCS2MAP-26OCT010630PSNAREV-2") == REAL_START


@pytest.mark.parametrize(
    "kwargs, why",
    [
        ({"source": "odds_api"}, "a schedule source dated it"),
        ({"source": "polymarket_venue"}, "Polymarket's fixture dated it"),
        ({"source": KALSHI_TICKER_TIME_COMMENCE_SOURCE}, "already corrected"),
        ({"source": None}, "unattributable provenance"),
        ({"status": "live"}, "something is reported on it"),
        ({"status": "completed"}, "settled"),
        ({"commence": REAL_START}, "already at the start"),
        ({"commence": REAL_START + timedelta(seconds=30)}, "inside a minute"),
        ({"commence": REAL_START - timedelta(hours=1)}, "the ticker is LATER"),
        ({"commence": REAL_START + timedelta(hours=12, minutes=1)}, "past the window"),
        ({"ticker": "KXCS2GAME-26OCT01PSNAREV-PSNA"}, "date-only ticker"),
        ({"ticker": "KXMLBGAME-26OCT010630NYYBOS-NYY"}, "not the esports family"),
        ({"market_source": "polymarket"}, "not Kalshi"),
    ],
)
def test_each_bound_refuses_alone(kwargs, why):
    assert _pure(**kwargs) is None, why


@pytest.mark.asyncio
async def test_a_market_naming_other_teams_is_refused_and_writes_nothing():
    session, esports = _new_rail()
    event = _event(session, esports)
    _kalshi(session, event, name="Somebody vs. Else")

    stats = await _run_phase15(session)

    assert _start(session, event) == (EXPECTED_EXPIRATION, "kalshi")
    assert stats["funnel"]["phase15_kalshi_esports_ticker_refused_teams_absent"] == 1


@pytest.mark.asyncio
async def test_two_tickers_naming_two_instants_are_refused_not_guessed():
    session, esports = _new_rail()
    event = _event(session, esports)
    _kalshi(session, event)
    _kalshi(session, event, ticker="KXCS2GAME-26OCT010930PSNAREV", side="REV")

    stats = await _run_phase15(session)

    assert _start(session, event) == (EXPECTED_EXPIRATION, "kalshi")
    assert stats["funnel"]["phase15_kalshi_esports_ticker_refused_tickers_disagree"] >= 1


@pytest.mark.asyncio
async def test_a_linked_polymarket_fixture_naming_another_game_is_refused():
    session, esports = _new_rail()
    event = _event(session, esports)
    _kalshi(session, event)
    _polymarket(session, event_id=event.id, venue_start=REAL_START + timedelta(hours=2))

    stats = await _run_phase15(session)

    assert event.commence_time_source != KALSHI_TICKER_TIME_COMMENCE_SOURCE
    assert stats["funnel"]["phase15_kalshi_esports_ticker_refused_venue_disagrees"] >= 1


@pytest.mark.asyncio
async def test_a_linked_polymarket_fixture_that_agrees_does_not_block():
    session, esports = _new_rail()
    event = _event(session, esports)
    _kalshi(session, event)
    _polymarket(session, event_id=event.id)

    await _run_phase15(session)

    _refresh(session, event)
    assert event.commence_time.replace(tzinfo=UTC) == REAL_START


# ═══ 4. The authority door ══════════════════════════════════════════════════


@pytest.mark.parametrize("current", ["kalshi", "kalshi_occurrence"])
def test_the_ticker_start_may_correct_kalshis_expiration(current):
    assert kalshi_ticker_time_corrects_a_kalshi_expiration(
        current, KALSHI_TICKER_TIME_COMMENCE_SOURCE,
    )
    assert commence_time_write_authorized(current, KALSHI_TICKER_TIME_COMMENCE_SOURCE)[0]


@pytest.mark.parametrize(
    "current, incoming",
    [
        # the reverse: the expiration never comes back over the start
        (KALSHI_TICKER_TIME_COMMENCE_SOURCE, "kalshi"),
        (KALSHI_TICKER_TIME_COMMENCE_SOURCE, "kalshi_occurrence"),
        # a schedule source is never corrected by it
        ("odds_api", KALSHI_TICKER_TIME_COMMENCE_SOURCE),
        ("espn", KALSHI_TICKER_TIME_COMMENCE_SOURCE),
        ("polymarket_venue", KALSHI_TICKER_TIME_COMMENCE_SOURCE),
        # a date at midnight is a different question
        ("kalshi_ticker", KALSHI_TICKER_TIME_COMMENCE_SOURCE),
    ],
)
def test_the_door_is_directional(current, incoming):
    assert not commence_time_write_authorized(current, incoming)[0]


def test_a_schedule_source_still_corrects_the_ticker_start():
    assert commence_time_write_authorized(KALSHI_TICKER_TIME_COMMENCE_SOURCE, "odds_api")[0]
