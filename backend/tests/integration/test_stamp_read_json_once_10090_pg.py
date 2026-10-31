"""Ship: a live game's new Polymarket price reaches the page sooner, because
the stamp read stops decoding the same JSON once per outcome row (#10090).

`STAMP_READ_JSON_ONCE` (default on) sends each event's JSON and each market's
content-understanding object on ONE row of the same single statement. These
controls run the real statement on real Postgres and prove the graph, the
reading and the stamp are identical with the switch on and off, including when
the JSON-carrying row arrives last.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport
from app.tasks.live_blend_refresh import (
    LiveBlendRefresher, PREPARED_EVENT_FIELDS, PREPARED_MARKET_FIELDS, STAMP_READ_JSON_ONCE_ENV,
)
from app.utils.content_understanding import CONTENT_UNDERSTANDING_KEY as KEY
from app.utils.live_blend import compute_source_home_probability
from tests.integration.test_live_blend_grouped_commit_8129_pg import (
    DB_URL, refresher, rig, stage,
)

pytestmark = [pytest.mark.asyncio,
              pytest.mark.skipif(not DB_URL, reason="disposable PostgreSQL required")]

HOME, AWAY = "Los Angeles Lakers", "Golden State Warriors"
#: Event 2's bag is NULL: preview reads it as {} and the source entry as None.
BAGS = {
    1: {"espn": {"value": 0.61}, "polymarket": {"value": 0.58, "updated_at": "2026-10-31T04:00:00+00:00"},
        "kalshi": {"value": 0.6, "eligibility": {"v": 1, "status": "verified"}}},
    2: None,
}


async def seed(rig, source):
    """Two live events, each a winner, props, a shell with no outcomes, a
    many-outcome container and a venue refusal; every market's metadata differs."""
    now = datetime.now(timezone.utc)
    async with rig.maker() as s:
        sport = Sport(key="basketball_nba", name="NBA")
        s.add(sport)
        await s.flush()
        mid = oid = 0
        for eid, bag in BAGS.items():
            s.add(Event(id=eid, sport_id=sport.id, home_team_name=HOME, away_team_name=AWAY,
                        commence_time=now - timedelta(minutes=40), status="live",
                        win_probability_sources=bag, opening_home_probability=0.5))
            await s.flush()
            markets = [
                ("Lakers vs. Warriors", ["Lakers", "Warriors"],
                 {KEY: {"v": 1, "semantic_type": "moneyline", "venue_type": "moneyline"}}),
                ("LeBron James: Points O/U 25.5", ["Over", "Under"], {"other": "x" * 500}),
                ("Spread: Lakers (-3.5)", ["Lakers", "Warriors"], None),
                ("Lakers vs. Warriors - Halftime Result", [], {KEY: []}),
                ("Lakers vs. Warriors", [f"Player {i}: Rebounds O/U 5.5" for i in range(9)],
                 {KEY: {"v": 1, "semantic_type": "moneyline", "venue_type": "moneyline"}}),
                ("Lakers vs. Warriors: Completed Match", ["Yes", "No"],
                 {KEY: {"v": 1, "semantic_type": "other", "venue_type": "tennis_completed_match"}}),
            ]
            for i, (name, outcomes, metadata) in enumerate(markets):
                mid += 1
                s.add(FuturesMarket(
                    id=mid, source=source, sport_id=sport.id, event_id=eid, name=name,
                    external_id=(f"KXNBAGAME-26OCT31LALGSW-{mid}" if i == 0 else f"KXNBAPTS-{mid}")
                    if source == "kalshi" else f"pm-{mid}",
                    status="open", category="game", market_type="duel", market_metadata=metadata,
                ))
                await s.flush()
                for rank, outcome in enumerate(outcomes, 1):
                    oid += 1
                    s.add(FuturesOutcome(
                        id=oid, market_id=mid, external_id=f"o-{oid}", name=outcome, rank=rank,
                        current_probability=(0.64 if outcome == "Lakers" else 0.36) if i == 0
                        else 0.5, last_updated=now - timedelta(seconds=oid),
                    ))
        await s.commit()


class LastRowCarries:
    """The real statement's real rows, reversed: each JSON row now comes LAST."""

    def __init__(self, session):
        self.session = session

    async def execute(self, statement):
        result = await self.session.execute(statement)
        rows, keys = list(reversed(result.all())), result.keys()
        return type("Reversed", (), {"all": lambda _self: rows, "keys": lambda _self: keys})()


class OtherMarketsFirst(LastRowCarries):
    """Markets newest first, outcomes oldest first: an event's JSON row is now
    the FIRST row of a market seen after its event."""

    async def execute(self, statement):
        result = await self.session.execute(statement)
        outcome_at = len(PREPARED_MARKET_FIELDS) + len(PREPARED_EVENT_FIELDS)
        rows = sorted(result.all(), key=lambda r: (-r[0], r[outcome_at] or 0))
        keys = result.keys()
        return type("Ordered", (), {"all": lambda _self: rows, "keys": lambda _self: keys})()


class NoJsonRow(LastRowCarries):
    """A statement whose flags name no row: never a quiet market or event."""

    async def execute(self, statement):
        result = await self.session.execute(statement)
        keys = list(result.keys())
        at = keys.index("market_json_row")
        rows = [tuple(r[:at]) + (False, False) + tuple(r[at + 2:]) for r in result.all()]
        return type("Unflagged", (), {"all": lambda _self: rows, "keys": lambda _self: keys})()


def snapshot(grouped):
    """The whole graph, ordered by id (row order is the statement's choice)."""
    return {
        # `preview_context_at` is each statement's own `statement_timestamp()`.
        eid: ({k: v for k, v in vars(event).items() if k != "preview_context_at"}, sorted((
            (vars(entry.market), entry.event_has_result, entry.event_commence_time,
             sorted((vars(o) for o in entry.outcomes), key=lambda o: o["id"]))
            for entry in group
        ), key=lambda m: m[0]["id"]))
        for eid, (event, group) in grouped.items()
    }


def reading(grouped, eid):
    result = compute_source_home_probability(grouped[eid][1], HOME, AWAY)
    return None if result is None else result.home_probability


async def read(rig, monkeypatch, source, *, once, preview, wrap=None):
    monkeypatch.setenv(STAMP_READ_JSON_ONCE_ENV, "1" if once else "0")
    r = LiveBlendRefresher(source)
    r.preview_events = frozenset(BAGS) if preview else frozenset()

    async def no_ticket():
        return None
    r._preview_admission_read = no_ticket
    async with rig.maker() as session:
        grouped = await r._read_groups(wrap(session) if wrap else session, sorted(BAGS))
    return grouped, r.stamp_spans


@pytest.mark.parametrize("source", ["polymarket", "kalshi"])
@pytest.mark.parametrize("preview", [False, True])
async def test_on_and_off_build_the_same_graph_and_reading(rig, monkeypatch, source, preview):
    await seed(rig, source)
    off, off_spans = await read(rig, monkeypatch, source, once=False, preview=preview)
    on, on_spans = await read(rig, monkeypatch, source, once=True, preview=preview)
    last, _ = await read(rig, monkeypatch, source, once=True, preview=preview, wrap=LastRowCarries)
    later, _ = await read(rig, monkeypatch, source, once=True, preview=preview,
                          wrap=OtherMarketsFirst)
    assert snapshot(on) == snapshot(off) == snapshot(last) == snapshot(later)
    for eid in BAGS:
        assert reading(on, eid) == reading(off, eid) == reading(last, eid) == reading(later, eid)
    if source == "polymarket":
        assert reading(off, 1) is not None  # the control speaks, so parity is not vacuous
    if preview:
        assert on[2][0].preview_sources == {} and on[1][0].preview_sources == BAGS[1]
        assert isinstance(on[1][0].preview_context_at, datetime)
    assert on[1][0].win_probability_sources == {source: BAGS[1][source]}
    assert on[2][0].win_probability_sources == {source: None}
    # Every market keeps ITS metadata, the shell and the container included.
    async with rig.maker() as s:
        stored = dict((await s.execute(select(FuturesMarket.id, FuturesMarket.market_metadata))).all())
    for eid in BAGS:
        for entry in on[eid][1]:
            raw = stored[entry.market.id]
            assert entry.market.market_metadata == {KEY: raw.get(KEY) if isinstance(raw, dict) else None}
    # The cut itself: same rows, one JSON value per market and per event.
    markets = sum(len(group) for _event, group in on.values())
    assert on_spans.read_rows == off_spans.read_rows > markets
    assert off_spans.read_json == 2 * off_spans.read_rows
    assert on_spans.read_json == markets + len(BAGS)
    assert "stamp_read_rows=%d stamp_read_json=%d " % (
        on_spans.read_rows, markets + len(BAGS)) in on_spans.line()


@pytest.mark.parametrize("preview", [False, True])
async def test_a_statement_with_no_json_row_refuses_the_graph(rig, monkeypatch, preview):
    await seed(rig, "polymarket")
    with pytest.raises(RuntimeError, match="no JSON row"):
        await read(rig, monkeypatch, "polymarket", once=True, preview=preview, wrap=NoJsonRow)


async def test_off_restores_the_per_row_statement(rig, monkeypatch):
    await seed(rig, "polymarket")
    statements = []

    class Capture:
        def __init__(self, session):
            self.session = session

        async def execute(self, statement):
            statements.append(statement)
            return await self.session.execute(statement)

    await read(rig, monkeypatch, "polymarket", once=False, preview=True, wrap=Capture)
    await read(rig, monkeypatch, "polymarket", once=True, preview=True, wrap=Capture)
    off_sql, on_sql = (str(s.compile()) for s in statements)
    assert "row_number()" not in off_sql and "CASE WHEN" not in off_sql
    assert on_sql.count("row_number() OVER") == 4
    assert [c.name for c in statements[1].selected_columns][-5:] == [
        "market_json_row", "event_json_row", "preview_sources", "preview_rev", "preview_context_at",
    ]


@pytest.mark.parametrize("once", [True, False])
async def test_the_stamp_writes_the_same_value_on_and_off(rig, monkeypatch, once):
    await seed(rig, "polymarket")
    monkeypatch.setenv(STAMP_READ_JSON_ONCE_ENV, "1" if once else "0")
    r, frames, _calls, _resolved, _publish = refresher(rig)
    stage(r, [1])
    await r.refresh([1])
    await r.drain_history()
    async with rig.maker() as s:
        stored = (await s.execute(select(Event.win_probability_sources).where(Event.id == 1))).scalar_one()
    # Off and on stamp the reading the off graph computes, to the same 4 places.
    off, _ = await read(rig, monkeypatch, "polymarket", once=False, preview=False)
    assert stored["polymarket"]["value"] == round(reading(off, 1), 4)
    assert [f["source_value"] for f in frames] == [stored["polymarket"]["value"]]
    # The untouched siblings survive the stamp exactly.
    assert stored["espn"] == BAGS[1]["espn"] and stored["kalshi"] == BAGS[1]["kalshi"]
    async with rig.engine.begin() as conn:
        await conn.execute(update(Event).where(Event.id == 1).values(win_probability_sources=BAGS[1]))
