"""#1527 (CERT-4099's ``1527-REINGEST-WRITER-GUARD``): a repaired, settled
three-way soccer field survives the REAL Polymarket poll, and a reader sees it as
a result — against a real PostgreSQL, on the real ORM schema.

PILLAR: TRUTH. SHIP: after a soccer fixture is settled, its market no longer
appears live while its one real winner remains visible.

The two repair rails write the stored state: one winner at 1.0 and two losses at
0.0 (``repair_winner_field``), honest openings (a genuine 0.41 kept, impossible
1.0s NULLed), then ``status='resolved'`` (``repair_settled_status_1527``). The
poll that minted the three-winner field still runs every hour and still upserts
these rows whenever Gamma returns their event. Nothing about the repair is worth
anything if that writer undoes it, so this drives the REAL parser
(``PolymarketAPIService._parse_event``) and the REAL ``_process_event_batch``
over the repaired rows and reads what it left.

The Gamma payload is the 8466 fixture's real event and market schema
(``tests/fixtures/polymarket_leg_dates_8466``) re-labelled as the specimen
fixture: three negRisk legs whose condition ids are the stored legs' own, so the
upsert lands on the repaired rows rather than beside them. It is SYNTHETIC in
its values (every name carries ``SYNTHETIC-1527``), not production bytes; the
sandbox has no venue network.

Replays, each from the repaired state:

* **closed, terminal** — what Gamma returns for the settled fixture: the winner
  at 1/0 on a real trade, the losers at 0/1 with a 0.001 ask and a last trade.
  Winner, losers, ``resolution_source``, the winner's 1.0 and every opening (the
  honest 0.41 AND the honest NULLs) survive. DISCLOSED: each loser's 0.0 is
  re-priced to the venue's last trade (0.003 here) — the poll's existing
  behaviour on every settled leg it prices, and visible on the detail route as
  a loss at 0.3%, never as a winner.
* **closed, incoherent** — the original 1.00/1.00/1.00 feed that minted the
  defect. The field gate refuses the legs; nothing on them moves.
* **open control** — the same rows re-polled as a LIVE market with real quotes.
  The opening stamp DOES fire here (``COALESCE`` fills the NULL). That is the
  arm that proves the replay reaches the opening writer at all, so the two
  closed arms are not vacuous: what protects the honest NULL is the venue's own
  ``closed`` flag (``opening_capture_is_hindsight``), and the status rail refuses
  a venue-open market for the same reason. Grades still never move.

Then the whole lifecycle once, with the real detail route as the reader:
``open`` + one winner → status rail → re-poll (closed) → ``/api/futures/{id}``
serves ``resolved`` with exactly one winner at 1.0.
"""

import copy
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.services.polymarket_api as polymarket_api
import app.tasks.repair_settled_status_1527 as rs

URL = os.environ.get("SEARCH_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not URL, reason="SEARCH_TEST_DATABASE_URL required for real-PG #1527 re-ingest gate"
    ),
]

UTC = timezone.utc
OPENED_AT = datetime(2024, 11, 20, 12, 0, tzinfo=UTC)
LABEL = "SYNTHETIC-1527"

FIXTURE = (Path(__file__).resolve().parent.parent / "fixtures"
           / "polymarket_leg_dates_8466" / "gamma-event-1038648.json")

SPEC, HONEST = 55254886, 55254887
EVENT = {SPEC: "1527001", HONEST: "1527002"}
TITLE = {SPEC: f"{LABEL} Slavia Praha vs. Anderlecht",
         HONEST: f"{LABEL} Real Sociedad vs. Dynamo Kyiv"}

#: The REPAIRED state. (outcome id, market, label, is_winner, current_probability,
#: resolution_source, opening_probability, calibration_probability)
LEGS = [
    (205060693, SPEC, "Slavia Praha", False, 0.0, "clob_field_repair", None, None),
    (205060694, SPEC, "Anderlecht", True, 1.0, "clob_field_repair", None, None),
    (205060695, SPEC, "Draw", False, 0.0, "clob_field_repair", None, None),
    (205060700, HONEST, "Real Sociedad", False, 0.0, "clob_field_repair", 0.41, None),
    (205060701, HONEST, "Dynamo Kyiv", False, 0.0, "clob_field_repair", None, None),
    (205060702, HONEST, "Draw", True, 1.0, "clob_field_repair", None, None),
]
WINNER = {SPEC: 205060694, HONEST: 205060702}


def _cid(oid: int) -> str:
    return f"0x{oid:064x}"


def _gamma(mid: int, *, closed: bool, prices: dict[int, tuple]) -> dict:
    """A Gamma event in the fixture's real schema. ``prices``: outcome id ->
    (yes price, best bid, best ask, last trade)."""
    raw = copy.deepcopy(json.loads(FIXTURE.read_text()))
    template = raw["markets"][0]
    raw.update(id=EVENT[mid], slug=f"synthetic-1527-{EVENT[mid]}", title=TITLE[mid],
               ticker=f"synthetic-1527-{EVENT[mid]}", negRisk=True, enableNegRisk=True,
               active=True, closed=closed, archived=False,
               endDate="2024-12-12T20:00:00Z" if closed else "2099-12-12T20:00:00Z")
    raw["markets"] = []
    for oid, m, label, *_ in LEGS:
        if m != mid:
            continue
        yes, bid, ask, last = prices[oid]
        leg = copy.deepcopy(template)
        leg.update(
            id=str(oid), conditionId=_cid(oid), slug=f"synthetic-1527-{oid}",
            question=f"{LABEL}: will {label} be the result?", groupItemTitle=label,
            outcomes='["Yes", "No"]', outcomePrices=json.dumps([str(yes), str(1 - yes)]),
            active=True, closed=closed, negRisk=True, bestBid=bid, bestAsk=ask,
            lastTradePrice=last, endDate=raw["endDate"],
            clobTokenIds=json.dumps([f"{oid}1", f"{oid}2"]))
        raw["markets"].append(leg)
    return raw


#: A settled loser leg as Gamma sends it — ``["0", "1"]``, no bid, a 0.001 ask
#: and a last trade, the shape of every closed loser in the repo's real Gamma
#: fixtures (``polymarket_sunk_starved_9605``).
LOSER_LAST_TRADE = 0.003


def _terminal(mid):
    return _gamma(mid, closed=True, prices={
        oid: ((1, 0.999, 1, 0.999) if oid == WINNER[mid]
              else (0, None, 0.001, LOSER_LAST_TRADE))
        for oid, m, *_ in LEGS if m == mid})


def _incoherent(mid):
    return _gamma(mid, closed=True, prices={
        oid: (1, 0.999, 1, 0.999) for oid, m, *_ in LEGS if m == mid})


def _live(mid):
    quotes = iter([(0.55, 0.54, 0.56, 0.55), (0.25, 0.24, 0.26, 0.25),
                   (0.20, 0.19, 0.21, 0.20)])
    return _gamma(mid, closed=False, prices={
        oid: next(quotes) for oid, m, *_ in LEGS if m == mid})


class FakeClob:
    """The CLOB for the status rail: closed, and the stored winner won."""

    async def get_clob_market_by_condition(self, condition_id):
        won = condition_id in {_cid(WINNER[SPEC]), _cid(WINNER[HONEST])}
        return {"condition_id": condition_id, "closed": True,
                "tokens": [{"outcome": "Yes", "winner": won},
                           {"outcome": "No", "winner": not won}]}


@pytest.fixture(scope="session")
def isolated_database():
    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    url = make_url(URL)
    assert url.host in ("localhost", "127.0.0.1"), "gate may only use local PostgreSQL"
    database = "reingest_1527_" + uuid4().hex
    admin = create_engine(url.set(drivername="postgresql+psycopg2"),
                          isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{database}"'))
    schema = create_engine(url.set(drivername="postgresql+psycopg2", database=database))
    Base.metadata.create_all(schema)
    schema.dispose()
    try:
        yield url.set(database=database)
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE "{database}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
async def db(isolated_database, monkeypatch):
    import app.tasks.base as task_base
    from app.models.models import FuturesMarket, FuturesOutcome

    url = isolated_database.render_as_string(hide_password=False)
    monkeypatch.setattr(task_base, "DATABASE_URL", url)
    engine = create_async_engine(isolated_database)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        await s.execute(text(f"DROP TABLE IF EXISTS {rs.BAK_TABLE}"))
        await s.execute(text("TRUNCATE futures_markets CASCADE"))
        for mid in (SPEC, HONEST):
            s.add(FuturesMarket(
                id=mid, source="polymarket", external_id=EVENT[mid], name=TITLE[mid],
                category="championship", llm_sport_category="soccer",
                market_type="field", mutually_exclusive=True, status="open",
                resolution_date=datetime(2024, 12, 12, 20, 0, tzinfo=UTC)))
        await s.flush()
        for oid, mid, label, won, prob, src, opening, cp in LEGS:
            s.add(FuturesOutcome(
                id=oid, market_id=mid, external_id=_cid(oid), name=label,
                is_winner=won, current_probability=prob, resolution_source=src,
                opening_probability=opening,
                opening_american_odds=None if opening is None else 144,
                opening_captured_at=None if opening is None else OPENED_AT,
                opening_source=None if opening is None else "first_snapshot",
                calibration_probability=cp))
        await s.commit()
    yield maker
    await engine.dispose()


_REAL_SERVICE = polymarket_api.PolymarketAPIService


_GRADES = ("SELECT id, is_winner, current_probability, resolution_source,"
           " opening_probability, opening_american_odds, opening_captured_at,"
           " opening_source, calibration_probability FROM futures_outcomes"
           " WHERE market_id = ANY(:m) ORDER BY id")


async def _grades(maker, mids=(SPEC, HONEST)):
    async with maker() as s:
        return [tuple(r) for r in
                (await s.execute(text(_GRADES), {"m": list(mids)})).all()]


async def _market(maker, mid):
    async with maker() as s:
        return (await s.execute(text(
            "SELECT status, settled_at, market_metadata, xmin::text"
            " FROM futures_markets WHERE id = :m"), {"m": mid})).one()


async def _leg_count(maker):
    async with maker() as s:
        return (await s.execute(text(
            "SELECT count(*) FROM futures_outcomes WHERE market_id = ANY(:m)"),
            {"m": [SPEC, HONEST]})).scalar_one()


async def _poll(raws: list[dict]) -> dict:
    """The REAL discovery-poll writer, handed one batch."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
    from app.tasks.polymarket import _process_event_batch
    from app.utils.market_label_normalization import compute_market_tier
    from app.utils.odds_math import probability_to_american

    class _Counting(dict):
        def __missing__(self, key):
            return 0

    stats = _Counting({"errors": []})
    service = _REAL_SERVICE()
    events = [service._parse_event(r) for r in raws]
    assert all(e is not None and len(e.markets) == 3 for e in events)
    await _process_event_batch(
        events, stats, FuturesMarket, FuturesOutcome, FuturesOddsSnapshot,
        pg_insert, probability_to_american, compute_market_tier,
    )
    assert not stats["errors"], stats["errors"]
    return stats


def _by_id(rows):
    return {r[0]: r for r in rows}


def _without_price(rows):
    """Every graded and opening field, i.e. everything but ``current_probability``."""
    return {r[0]: r[:2] + r[3:] for r in rows}


def _loser_ids(mids=(SPEC, HONEST)):
    return {oid for oid, m, *_ in LEGS if m in mids and oid != WINNER[m]}


# ---------------------------------------------------------------------------
# the re-ingest guard
# ---------------------------------------------------------------------------

async def test_a_closed_terminal_repoll_keeps_every_grade_and_every_honest_opening(db):
    before = await _grades(db)
    stats = await _poll([_terminal(SPEC), _terminal(HONEST)])
    assert stats["events_processed"] == 2
    rows = await _grades(db)
    after = _by_id(rows)
    # The poll reached every leg and stamped no opening on any of them.
    assert stats["outcomes_updated"] == len(LEGS)
    assert _without_price(rows) == _without_price(before)
    # Spelled out, so a reader of a failure sees which promise broke.
    assert after[205060694][1:4] == (True, Decimal("1"), "clob_field_repair")
    assert after[205060700][4:8] == (Decimal("0.41"), 144, OPENED_AT, "first_snapshot")
    assert all(after[o][4] is None for o in (205060693, 205060694, 205060695,
                                             205060701, 205060702))
    assert all(after[o][2] == Decimal("1") for o in WINNER.values())
    # DISCLOSED, not endorsed: a loser's settlement price 0.0 is re-stamped to the
    # venue's own last trade. Its grade (False, this rail's source) does not move.
    # Pre-existing poll behaviour for every settled leg it prices, not the
    # repair's; pinned so a change in either direction is seen.
    assert {o: after[o][2] for o in _loser_ids()} == {
        o: Decimal(str(LOSER_LAST_TRADE)) for o in _loser_ids()}
    assert await _leg_count(db) == len(LEGS)
    # And a closed event is resolved by the poll's own rule.
    assert (await _market(db, SPEC))[0] == "resolved"


async def test_the_incoherent_feed_that_minted_the_defect_moves_no_leg(db):
    before = await _grades(db)
    stats = await _poll([_incoherent(SPEC), _incoherent(HONEST)])
    assert stats["incoherent_fields_skipped"] == 2
    assert await _grades(db) == before
    assert await _leg_count(db) == len(LEGS)


async def test_open_control_the_replay_reaches_the_opening_writer(db):
    """Not vacuous: re-polled as a LIVE market, the opening stamp fires on the
    honest NULLs. The grades still never move. This is why the status rail
    refuses a venue-open market, and why the closed arms above are real."""
    before = _by_id(await _grades(db))
    await _poll([_live(SPEC), _live(HONEST)])
    after = _by_id(await _grades(db))
    stamped = {o for o in after if before[o][4] is None and after[o][4] is not None}
    assert stamped, "the live replay never reached the opening writer: the rig is blind"
    assert {o: after[o][1] for o in after} == {o: before[o][1] for o in before}
    assert {o: after[o][3] for o in after} == {o: before[o][3] for o in before}
    assert after[205060700][4] == Decimal("0.41")  # COALESCE-first: kept
    assert (await _market(db, SPEC))[0] == "open"


# ---------------------------------------------------------------------------
# the lifecycle, read through the reader's own route
# ---------------------------------------------------------------------------

@pytest.fixture
async def client(db, isolated_database, monkeypatch):
    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.services.database import get_db, get_db_rw

    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    engine = create_async_engine(isolated_database)

    async def _get_db():
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session

    async def _anon():
        return None

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_db_rw] = _get_db
    app.dependency_overrides[get_optional_user] = _anon
    try:
        async with AsyncClient(transport=ASGITransport(app=app),
                               base_url="http://test") as c:
            yield c
    finally:
        for dep in (get_db, get_db_rw, get_optional_user):
            app.dependency_overrides.pop(dep, None)
        await engine.dispose()


async def _served(client, mid):
    r = await client.get(f"/api/futures/{mid}")
    assert r.status_code == 200, r.text
    body = r.json()
    return body["status"], sorted(
        (o["name"], o["is_winner"], o["probability"]) for o in body["outcomes"])


async def test_a_settled_fixture_stops_reading_live_and_keeps_its_one_winner(db, client):
    status, _ = await _served(client, SPEC)
    assert status == "open"  # the defect, as the reader's route serves it

    plan = await _run_status(db, only_ids=str(SPEC))
    assert plan["planned_market_ids"] == [SPEC]
    out = await _run_status(db, only_ids=str(SPEC), apply=True,
                            plan_hash=plan["plan_hash"])
    assert out["settled"] == 1
    settled_at = (await _market(db, SPEC))[1]

    status, legs = await _served(client, SPEC)
    assert status == "resolved"
    assert [leg for leg in legs if leg[1]] == [("Anderlecht", True, 1.0)]
    assert sorted(leg[0] for leg in legs if leg[1] is False) == ["Draw", "Slavia Praha"]

    # The hourly poll reaches it again. It stays settled, keeps its first
    # observation, and keeps its one winner.
    grades = await _grades(db, (SPEC,))
    await _poll([_terminal(SPEC)])
    row = await _market(db, SPEC)
    assert row[0] == "resolved" and row[1] == settled_at
    assert _without_price(await _grades(db, (SPEC,))) == _without_price(grades)
    status, again = await _served(client, SPEC)
    assert status == "resolved"
    # Still one winner at 1.0. The two losses read the venue's last trade
    # (disclosed above), never a winner.
    assert again == [("Anderlecht", True, 1.0), ("Draw", False, LOSER_LAST_TRADE),
                     ("Slavia Praha", False, LOSER_LAST_TRADE)]


async def test_the_poll_replaces_the_status_rails_provenance_stamp(db):
    """DISCLOSED, not endorsed. The poll REPLACES ``market_metadata`` and carries
    back only the keys ``preserve_venue_settled`` names, so the status rail's
    ``resolution_gate`` stamp does not survive a re-poll; the Polymarket resolve
    sync's stamp is in the same position. The status, the first observation and
    the grades do survive (above) — what is lost is provenance, not the result.
    Pinned so a change to that writer is seen, in either direction."""
    plan = await _run_status(db, only_ids=str(SPEC))
    await _run_status(db, only_ids=str(SPEC), apply=True, plan_hash=plan["plan_hash"])
    meta = (await _market(db, SPEC))[2]
    meta = json.loads(meta) if isinstance(meta, str) else meta
    assert meta["resolution_gate"]["task"] == rs.TASK
    await _poll([_terminal(SPEC)])
    status, _, meta, _ = await _market(db, SPEC)
    meta = json.loads(meta) if isinstance(meta, str) else meta
    assert status == "resolved"
    assert "resolution_gate" not in (meta or {})


async def _run_status(maker, **kw):
    """The status rail, with the fake CLOB swapped in for its call only: the
    poll above never sees anything but the real service."""
    polymarket_api.PolymarketAPIService = FakeClob
    try:
        async with maker() as s:
            return await rs.repair(s, **kw)
    finally:
        polymarket_api.PolymarketAPIService = _REAL_SERVICE
