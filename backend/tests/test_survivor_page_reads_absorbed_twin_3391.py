"""#3391 — the one card a reader can tap opens onto its absorbed twin's content.

FC Dallas 1-0 LAFC, 2026-09-27 00:30Z. Search printed the fixture once, as the
ESPN row `15318170` (espn_id, score, 0 markets); the serve-time fold had
absorbed `15314003` (Odds API anchor, 121 markets, 43% pregame, the chart).
The page for the card showed a score and WON, nothing else.

These tests drive the real fold over real rows in SQLite:

  A  the helper returns the absorbed row for the survivor, and nothing for the
     loser, for an unrelated fixture, or for a doubleheader three hours later;
  B  `/game-markets`' real builder serves the absorbed row's market;
  C  the tag folds the detail and chart routes use take the absorbed rows;
  D  the three event-page routes are wired to it.
"""

import asyncio
import inspect
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models import Event, Sport  # noqa: E402
from app.models.models import Base, FuturesMarket, FuturesOutcome  # noqa: E402

S_MLS = 41
S_SOCCER_OTHER = 42
S_EPL = 43
S_MLB = 3
SURVIVOR = 15318170  # ESPN row: espn_id + score, no markets
LOSER = 15314003  # Odds API row: the markets, the opening line, the venues
UNRELATED = 15318171  # another MLS game, same minute
KICKOFF = datetime(2026, 9, 27, 0, 30, tzinfo=timezone.utc)
MARKET_ID = 9301
KALSHI_READING = {"value": 0.425, "updated_at": "2026-09-27T00:20:00+00:00"}


class _SyncAsAsync:
    """`await db.execute(...)` over a sync Session — the real statements run.

    SQLite drops the zone off a TIMESTAMPTZ; Postgres never does. So every
    loaded row's clock is handed back aware, as production hands it, or a
    settled page's `commence_time <= now` raises before the fold is reached.
    """

    def __init__(self, session):
        self._session = session

    async def execute(self, statement, *args):
        from sqlalchemy.orm.attributes import set_committed_value

        # `freeze()` fetches every row now, so the ORM objects exist in the
        # identity map before the loop below; a lazy Result would build them
        # after it, still naive.
        frozen = self._session.execute(statement, *args).freeze()
        for obj in list(self._session.identity_map.values()):
            for col in ("commence_time", "completed_at"):
                value = getattr(obj, col, None)
                if isinstance(value, datetime) and value.tzinfo is None:
                    set_committed_value(obj, col, value.replace(tzinfo=timezone.utc))
        return frozen()


def _event(id, home, away, commence=KICKOFF, sport_id=S_MLS, **kw):
    fields = dict(
        id=id,
        sport_id=sport_id,
        home_team_name=home,
        away_team_name=away,
        commence_time=commence,
        commence_time_source="espn",
        status="completed",
        home_score=1,
        away_score=0,
    )
    fields.update(kw)
    return Event(**fields)


def _engine(*, loser_commence=KICKOFF, loser_sport=S_MLS, loser_away="Los Angeles FC"):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_MLS, key="soccer_usa_mls", name="MLS"))
        s.add(Sport(id=S_SOCCER_OTHER, key="soccer_other", name="Soccer"))
        s.add(Sport(id=S_EPL, key="soccer_epl", name="EPL"))
        s.add(Sport(id=S_MLB, key="baseball_mlb", name="MLB"))
        s.add(_event(SURVIVOR, "FC Dallas", "LAFC", espn_id="761835"))
        s.add(
            _event(
                LOSER,
                "FC Dallas",
                loser_away,
                commence=loser_commence,
                sport_id=loser_sport,
                external_id="1939426b2ba9d98c1142822d3187a776",
                opening_home_probability=0.4308,
                opening_away_probability=0.2950,
                win_probability_sources={"kalshi": KALSHI_READING},
            )
        )
        s.add(_event(UNRELATED, "Seattle Sounders", "Portland Timbers", espn_id="761836"))
        s.add(
            FuturesMarket(
                id=MARKET_ID,
                event_id=LOSER,
                sport_id=loser_sport,
                source="polymarket",
                external_id="pm-dal-lafc-exact",
                name="FC Dallas vs Los Angeles FC - Exact Score",
                category="game",
                llm_sport_category="soccer",
                market_type="game_prop",
                status="open",
            )
        )
        s.add(
            FuturesOutcome(
                id=93011,
                market_id=MARKET_ID,
                external_id="DAL-2-1",
                name="FC Dallas 2-1",
                current_probability=0.09,
            )
        )
        s.commit()
    return eng


def _absorbed(eng, event_id):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.utils.serve_fold_absorbed import serve_fold_absorbed_rows

    with Session(eng) as s:
        db = _SyncAsAsync(s)
        event = asyncio.run(
            db.execute(
                select(Event).options(selectinload(Event.sport)).where(Event.id == event_id)
            )
        ).scalar_one()
        return [r.id for r in asyncio.run(serve_fold_absorbed_rows(db, event))]


class TestTheHelper:
    def test_the_survivor_gets_the_row_it_absorbed(self):
        """🔴 THE SHIP's input: 15318170 names 15314003 as the row it absorbed."""
        assert _absorbed(_engine(), SURVIVOR) == [LOSER]

    def test_the_loser_absorbs_nothing_so_its_own_page_is_unchanged(self):
        assert _absorbed(_engine(), LOSER) == []

    def test_an_unrelated_game_in_the_same_minute_absorbs_nothing(self):
        assert _absorbed(_engine(), UNRELATED) == []

    def test_a_different_club_in_the_away_slot_is_not_absorbed(self):
        """Control: same minute, same league, one club differs — no fold, no read."""
        assert _absorbed(_engine(loser_away="Houston Dynamo"), SURVIVOR) == []

    def test_a_catch_all_row_of_the_same_sport_is_a_candidate(self):
        """`soccer_other` rows fold onto league rows (#2866) — so they are read."""
        assert _absorbed(_engine(loser_sport=S_SOCCER_OTHER), SURVIVOR) == [LOSER]

    def test_another_league_is_never_a_candidate(self):
        assert _absorbed(_engine(loser_sport=S_EPL), SURVIVOR) == []

    def test_an_hour_away_is_outside_every_arm(self):
        later = KICKOFF + timedelta(hours=1)
        assert _absorbed(_engine(loser_commence=later), SURVIVOR) == []

    def test_a_doubleheader_three_hours_later_is_read_but_never_folded(self):
        """🔴 #8884's shape. The +3h arm LOADS game 2 (Kalshi's pad lives there),
        and the fold refuses it: a baseball row's clock is never recovered, so
        the minutes differ and the key does not match. The fold decides, not
        the window."""
        eng = create_engine("sqlite://")
        Base.metadata.create_all(eng)
        with Session(eng) as s:
            s.add(Sport(id=S_MLB, key="baseball_mlb", name="MLB"))
            s.add(_event(1, "Boston Red Sox", "Toronto Blue Jays", sport_id=S_MLB, espn_id="1"))
            s.add(
                _event(
                    2,
                    "Boston Red Sox",
                    "Toronto Blue Jays",
                    commence=KICKOFF + timedelta(hours=3),
                    sport_id=S_MLB,
                    external_id="x",
                )
            )
            s.commit()
        assert _absorbed(eng, 1) == []
        assert _absorbed(eng, 2) == []


def _served_game_markets(eng, event_id):
    from app.routes.events import _build_game_markets

    with Session(eng) as s:
        return asyncio.run(_build_game_markets(event_id, _SyncAsAsync(s)))


class TestTheGameMarketsBuilder:
    def test_the_survivors_page_is_served_the_absorbed_rows_market(self):
        """🔴 THE SHIP, in the payload a reader's page renders."""
        response, _status, market_ids = _served_game_markets(_engine(), SURVIVOR)
        assert market_ids == [MARKET_ID]
        assert "FC Dallas 2-1" in [o["outcome_name"] for o in response["other"]]

    def test_without_the_fold_the_same_market_never_arrives(self):
        """Control: one club differs, so the fold refuses — and the market stays
        on its own row. Proves the fold, not a name/time join, moved it."""
        _response, _status, market_ids = _served_game_markets(
            _engine(loser_away="Houston Dynamo"), SURVIVOR
        )
        assert market_ids == []

    def test_the_losers_own_page_still_serves_its_market(self):
        _response, _status, market_ids = _served_game_markets(_engine(), LOSER)
        assert market_ids == [MARKET_ID]


def _rows(eng, *ids):
    from sqlalchemy import select

    s = Session(eng)
    db = _SyncAsAsync(s)
    return s, [
        asyncio.run(db.execute(select(Event).where(Event.id == i))).scalar_one()
        for i in ids
    ]


class TestTheTagFoldsTakeTheAbsorbedRows:
    def test_series_ids_append_the_absorbed_row_without_the_subset_retest(self):
        """`orientation_agrees('LAFC', 'Los Angeles FC')` is False — the fold's
        own key is the orientation licence, as it is for the card's number."""
        from app.utils.proven_duplicates import folded_series_event_ids, orientation_agrees

        assert not orientation_agrees("FC Dallas", "LAFC", "FC Dallas", "Los Angeles FC")
        s, (survivor, loser) = _rows(_engine(), SURVIVOR, LOSER)
        with s:
            ids = asyncio.run(folded_series_event_ids(_SyncAsAsync(s), SURVIVOR, [loser]))
        assert ids == [SURVIVOR, LOSER]

    def test_market_ids_append_the_absorbed_row(self):
        from app.utils.proven_duplicates import folded_event_ids

        s, (loser,) = _rows(_engine(), LOSER)
        with s:
            assert asyncio.run(folded_event_ids(_SyncAsAsync(s), SURVIVOR, [loser])) == [
                SURVIVOR,
                LOSER,
            ]

    def test_no_absorbed_rows_is_exactly_the_old_answer(self):
        from app.utils.proven_duplicates import folded_event_ids, folded_series_event_ids

        s, _ = _rows(_engine())
        with s:
            db = _SyncAsAsync(s)
            assert asyncio.run(folded_event_ids(db, SURVIVOR)) == [SURVIVOR]
            assert asyncio.run(folded_series_event_ids(db, SURVIVOR)) == [SURVIVOR]

    def test_the_blend_gains_the_absorbed_rows_venue(self):
        from app.utils.proven_duplicates import folded_probability_sources

        s, (survivor, loser) = _rows(_engine(), SURVIVOR, LOSER)
        with s:
            db = _SyncAsAsync(s)
            assert "kalshi" not in (asyncio.run(folded_probability_sources(db, survivor)) or {})
            folded = asyncio.run(folded_probability_sources(db, survivor, [loser]))
        assert folded["kalshi"]["value"] == 0.425


class _CapturingDb:
    """Records the binds `_settled_prematch_odds` sends and answers with rows."""

    def __init__(self, rows):
        self.rows = rows
        self.binds = None

    async def begin_nested(self):
        class _N:
            async def commit(self):
                pass

            async def rollback(self):
                pass

        return _N()

    async def execute(self, statement, binds=None):
        self.binds = binds

        class _R:
            def __init__(self, rows):
                self._rows = rows

            def all(self):
                return self._rows

        return _R(self.rows)


class TestThePregameReading:
    def _row(self, event_id, source, home):
        from types import SimpleNamespace

        return SimpleNamespace(
            event_id=event_id,
            source=source,
            home_win_probability=home,
            away_win_probability=1 - home - 0.28,
            draw_probability=0.28,
        )

    def test_the_absorbed_row_is_read_at_the_survivors_cutoff(self):
        """🔴 The '43% pregame' the loser's page prints reaches the survivor's."""
        from app.routes.events import _settled_prematch_odds

        s, (survivor, loser) = _rows(_engine(), SURVIVOR, LOSER)
        with s:
            db = _CapturingDb([self._row(LOSER, "kalshi", 0.425)])
            reading = asyncio.run(
                _settled_prematch_odds(db, survivor, "soccer_usa_mls", [loser])
            )
        assert db.binds["ids"] == [SURVIVOR, LOSER]
        assert db.binds["cutoffs"][0] == db.binds["cutoffs"][1]
        assert reading["source"] == "kalshi"
        assert reading["home_rendered_percent"] == 43

    def test_the_survivors_own_reading_wins_a_shared_source(self):
        from app.routes.events import _settled_prematch_odds

        s, (survivor, loser) = _rows(_engine(), SURVIVOR, LOSER)
        with s:
            # Loser's row FIRST in the cursor: the rank, not arrival, decides.
            db = _CapturingDb(
                [self._row(LOSER, "kalshi", 0.425), self._row(SURVIVOR, "kalshi", 0.51)]
            )
            reading = asyncio.run(
                _settled_prematch_odds(db, survivor, "soccer_usa_mls", [loser])
            )
        assert reading["home_rendered_percent"] == 51


class TestTheRoutesAreWired:
    """A helper nobody calls ships nothing: each event-page endpoint must read
    the absorbed rows and hand them to every fold it runs."""

    def test_the_detail_route(self):
        from app.routes.events import get_event

        src = inspect.getsource(get_event)
        assert "absorbed = await serve_fold_absorbed_rows(db, event)" in src
        assert "folded_series_event_ids(db, event_id, absorbed)" in src
        assert "folded_probability_sources(db, event, absorbed)" in src
        assert "db, event, event_sport_key, absorbed" in src

    def test_the_history_route(self):
        from app.routes.events import get_event_odds_history

        src = inspect.getsource(get_event_odds_history)
        assert "absorbed = await serve_fold_absorbed_rows(db, event)" in src
        assert "folded_series_event_ids(db, event_id, absorbed)" in src
        assert "folded_probability_sources(db, event, absorbed)" in src

    def test_the_game_markets_builder(self):
        from app.routes.events import _build_game_markets

        src = inspect.getsource(_build_game_markets)
        assert "absorbed = await serve_fold_absorbed_rows(db, event)" in src
        assert "expected_category, absorbed," in src
