"""Regression tests for #13768 — list-vs-detail parity when external same-league/cross-board twins win `_elect()`."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, selectinload


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models import Event, OddsSnapshot, Sport  # noqa: E402
from app.models.models import Base  # noqa: E402
from app.utils.proven_duplicates import folded_probability_sources_with_revision  # noqa: E402
from app.utils.serve_fold_absorbed import (  # noqa: E402
    serve_fold_absorbed_rows,
    serve_fold_absorbed_rows_with_completeness,
)
from app.utils.unified_game_read import (  # noqa: E402
    load_unified_game_reads,
    resolve_unified_card_chance,
)

S_SERIE_B = 71
S_EUROLEAGUE = 72
S_FCS = 73
S_FBS = 74


class _SyncAsAsync:
    """AsyncSession shim over SQLite sync Session keeping UTC-aware timestamps."""

    def __init__(self, session: Session):
        self._session = session

    async def begin_nested(self):
        nested = self._session.begin_nested()

        class _Tx:
            async def commit(self):
                if nested.is_active:
                    nested.commit()

            async def rollback(self):
                if nested.is_active:
                    nested.rollback()

        return _Tx()

    async def execute(self, statement, *args, **kwargs):
        from sqlalchemy.orm.attributes import set_committed_value

        result = self._session.execute(statement, *args, **kwargs)
        frozen = result.freeze() if hasattr(result, "freeze") else result
        for obj in list(self._session.identity_map.values()):
            for col in ("commence_time", "completed_at", "captured_at", "valid_until"):
                value = getattr(obj, col, None)
                if isinstance(value, datetime) and value.tzinfo is None:
                    set_committed_value(obj, col, value.replace(tzinfo=timezone.utc))
        return frozen() if hasattr(result, "freeze") else frozen


def _portable_odds_query(event_ids):
    return select(OddsSnapshot).where(OddsSnapshot.event_id.in_(event_ids))


def _load_event(db: _SyncAsAsync, eid: int) -> Event:
    return asyncio.run(
        db.execute(select(Event).options(selectinload(Event.sport)).where(Event.id == eid))
    ).scalar_one()


def test_13768_same_league_winner_keeps_betting_and_books_on_detail_and_list():
    """Exact 15346837 / 15350979 shape: live page row loses `_elect()` to scheduled same-league twin."""
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    kickoff = now - timedelta(minutes=25)
    src_stamp = (now - timedelta(minutes=1)).isoformat()

    with Session(eng) as s:
        s.add(Sport(id=S_SERIE_B, key="soccer_italy_serie_b", name="Serie B", group="Soccer"))
        # Live prediction-market-only page row (external_id=None) -> loses _elect() to Odds-API row
        s.add(
            Event(
                id=15346837,
                sport_id=S_SERIE_B,
                away_team_name="US Avellino 1912",
                home_team_name="US Cremonese",
                commence_time=kickoff,
                status="live",
                external_id=None,
                win_probability_sources={"polymarket": {"value": 0.48, "updated_at": src_stamp}},
                win_probability_sources_rev=685,
            )
        )
        # Same-league Odds-API twin (different status -> absent from `status=live` page slice)
        s.add(
            Event(
                id=15350979,
                sport_id=S_SERIE_B,
                away_team_name="Avellino",
                home_team_name="Cremonese",
                commence_time=kickoff + timedelta(minutes=2),
                status="scheduled",
                external_id="e9dde1a356f9972fdba7493f024c1416",
                score_source="odds_api",
                win_probability_sources={
                    "betting": {"value": 0.45, "updated_at": src_stamp},
                    "betting_book_count": 5,
                },
                win_probability_sources_rev=813,
            )
        )
        for i in range(5):
            s.add(
                OddsSnapshot(
                    id=5000 + i,
                    event_id=15350979,
                    bookmaker=f"book_{i}",
                    home_win_probability=0.45,
                    away_win_probability=0.25,
                    captured_at=now - timedelta(minutes=1),
                )
            )
        s.commit()

    # Raw #3391 caller behavior (keep_page_survivor=False) remains unchanged on the loser.
    with Session(eng) as s:
        db = _SyncAsAsync(s)
        ev_live = _load_event(db, 15346837)
        assert asyncio.run(serve_fold_absorbed_rows(db, ev_live)) == []

    # List path (`collapse_in_page=True`, external twin fetched in `_fetch_external_candidates_batch`)
    with Session(eng) as s:
        db = _SyncAsAsync(s)
        ev_live = _load_event(db, 15346837)
        list_batch = asyncio.run(
            load_unified_game_reads(
                db,
                [ev_live],
                collapse_in_page=True,
                include_same_league_external=True,
                include_odds=True,
                odds_query_fn=_portable_odds_query,
                now=now,
            )
        )
        list_read = list_batch.by_id[15346837]
        list_chance = resolve_unified_card_chance(
            list_read, sport_key="soccer_italy_serie_b", served_status="live"
        )

    # Detail path (`len=1`, `collapse_in_page=False`, `include_same_league_external=True`)
    with Session(eng) as s:
        db = _SyncAsAsync(s)
        ev_live = _load_event(db, 15346837)
        detail_batch = asyncio.run(
            load_unified_game_reads(
                db,
                [ev_live],
                collapse_in_page=False,
                include_same_league_external=True,
                include_odds=True,
                include_live_projections=True,
                include_recent_projections=True,
                include_fold_revision=True,
                include_series_fold_ids=True,
                fold_revision_fn=folded_probability_sources_with_revision,
                odds_query_fn=_portable_odds_query,
                now=now,
            )
        )
        detail_read = detail_batch.by_id[15346837]
        detail_chance = resolve_unified_card_chance(
            detail_read, sport_key="soccer_italy_serie_b", served_status="live"
        )

    assert sorted(detail_read.folded_sources.keys()) == sorted(list_read.folded_sources.keys())
    assert "betting" in detail_read.folded_sources
    assert detail_read.bookmaker_count == 5
    assert list_read.bookmaker_count == 5
    assert detail_chance.bookmaker_count == 5
    assert list_chance.bookmaker_count == 5
    assert detail_read.three_way_books == list_read.three_way_books
    assert detail_chance.home_rendered_percent == list_chance.home_rendered_percent
    assert detail_chance.draw_rendered_percent == list_chance.draw_rendered_percent
    assert detail_chance.away_rendered_percent == list_chance.away_rendered_percent
    assert detail_chance.source_mark == list_chance.source_mark
    assert detail_read.blend_fold_revision == {"15346837": 685, "15350979": 813}


def test_13768_cross_board_winner_and_retired_exclusion_and_corner_flip_parity():
    """Cross-board winners absorb cleanly, retired twins stay excluded, and corner-flips orient."""
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    kickoff = now + timedelta(hours=3)
    src_stamp = (now - timedelta(minutes=1)).isoformat()

    with Session(eng) as s:
        s.add(Sport(id=S_FCS, key="americanfootball_ncaaf_fcs", name="FCS"))
        s.add(Sport(id=S_FBS, key="americanfootball_ncaaf", name="FBS"))
        s.add(Sport(id=S_EUROLEAGUE, key="basketball_euroleague", name="EuroLeague"))

        # 1. Cross-board pair: FCS row loses `_elect()` to FBS external_id twin; retired twin must be ignored.
        s.add(
            Event(
                id=16001,
                sport_id=S_FCS,
                away_team_name="Montana Grizzlies",
                home_team_name="Montana State Bobcats",
                commence_time=kickoff,
                status="scheduled",
                external_id=None,
                win_probability_sources={"kalshi": {"value": 0.55, "updated_at": src_stamp}},
            )
        )
        s.add(
            Event(
                id=16002,
                sport_id=S_FBS,
                away_team_name="Montana Grizzlies",
                home_team_name="Montana State Bobcats",
                commence_time=kickoff,
                status="scheduled",
                external_id="fbs-montana",
                win_probability_sources={
                    "betting": {"value": 0.52, "updated_at": src_stamp},
                    "betting_book_count": 4,
                },
            )
        )
        s.add(
            Event(
                id=16003,
                sport_id=S_FBS,
                away_team_name="Montana Grizzlies",
                home_team_name="Montana State Bobcats",
                commence_time=kickoff,
                status="merged",
                external_id="fbs-montana-retired",
                win_probability_sources={"polymarket": {"value": 0.11, "updated_at": src_stamp}},
            )
        )
        for i in range(4):
            s.add(
                OddsSnapshot(
                    id=6000 + i,
                    event_id=16002,
                    bookmaker=f"cfb_bk_{i}",
                    home_win_probability=0.52,
                    away_win_probability=0.48,
                    captured_at=now - timedelta(minutes=1),
                )
            )

        # 2. Corner-flipped winner across status slice: live page row (`16010`,
        # id-less) vs scheduled Odds-API winner (`16011`).
        s.add(
            Event(
                id=16010,
                sport_id=S_EUROLEAGUE,
                away_team_name="Maccabi Tel Aviv",
                home_team_name="FC Bayern Munich",
                commence_time=kickoff,
                status="live",
                external_id=None,
                win_probability_sources={"kalshi": {"value": 0.60, "updated_at": src_stamp}},
            )
        )
        s.add(
            Event(
                id=16011,
                sport_id=S_EUROLEAGUE,
                away_team_name="FC Bayern Munich",
                home_team_name="Maccabi Tel Aviv",
                commence_time=kickoff,
                status="scheduled",
                external_id="oa-flipped-winner",
                win_probability_sources={"polymarket": {"value": 0.35, "updated_at": src_stamp}},
            )
        )
        s.commit()

    with Session(eng) as s:
        db = _SyncAsAsync(s)
        fcs_ev = _load_event(db, 16001)
        absorbed, _ = asyncio.run(
            serve_fold_absorbed_rows_with_completeness(db, fcs_ev, keep_page_survivor=True)
        )
        assert [r.id for r in absorbed] == [16002]  # retired 16003 excluded on detail read

        # Raw callers (`keep_page_survivor=False`) keep master behavior untouched for retired twins.
        fbs_ev = _load_event(db, 16002)
        absorbed_raw_fbs = asyncio.run(serve_fold_absorbed_rows(db, fbs_ev))
        assert [r.id for r in absorbed_raw_fbs] == [16001, 16003]

        detail_fcs = asyncio.run(
            load_unified_game_reads(
                db,
                [fcs_ev],
                collapse_in_page=False,
                include_same_league_external=True,
                include_odds=True,
                odds_query_fn=_portable_odds_query,
                now=now,
            )
        ).by_id[16001]
        assert detail_fcs.bookmaker_count == 4
        assert detail_fcs.folded_sources["betting"]["value"] == pytest.approx(0.52)
        assert "polymarket" not in detail_fcs.folded_sources

    with Session(eng) as s:
        db = _SyncAsAsync(s)
        ev_16010 = _load_event(db, 16010)
        detail_flip = asyncio.run(
            load_unified_game_reads(
                db,
                [ev_16010],
                collapse_in_page=False,
                include_same_league_external=True,
                include_odds=True,
                odds_query_fn=_portable_odds_query,
                now=now,
            )
        ).by_id[16010]
    with Session(eng) as s:
        db = _SyncAsAsync(s)
        ev_16010 = _load_event(db, 16010)
        list_flip = asyncio.run(
            load_unified_game_reads(
                db,
                [ev_16010],
                collapse_in_page=True,
                include_same_league_external=True,
                include_odds=True,
                odds_query_fn=_portable_odds_query,
                now=now,
            )
        ).by_id[16010]

    assert detail_flip.folded_sources["polymarket"]["value"] == pytest.approx(0.65)
    assert list_flip.folded_sources["polymarket"]["value"] == pytest.approx(0.65)
    assert detail_flip.bookmaker_count == list_flip.bookmaker_count == 0


def test_13768_same_league_same_status_loser_does_not_absorb_survivor_odds():
    """In-slice loser (`id=43`, same league & status as `id=42`) stays unfolded on detail."""
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    now = datetime.now(timezone.utc).replace(microsecond=0)

    with Session(eng) as s:
        s.add(Sport(id=75, key="soccer_epl", name="EPL", group="Soccer"))
        s.add(
            Event(
                id=42,
                sport_id=75,
                external_id="fixture42",
                home_team_name="Home",
                away_team_name="Away",
                commence_time=now,
                status="live",
                win_probability_sources={
                    "espn": {
                        "value": 0.63,
                        "home_probability": 0.63,
                        "away_probability": 0.27,
                        "updated_at": now.isoformat(),
                    }
                },
            )
        )
        s.add(
            Event(
                id=43,
                sport_id=75,
                external_id="fixture43",
                home_team_name="Home",
                away_team_name="Away",
                commence_time=now,
                status="live",
                win_probability_sources={
                    "espn": {
                        "value": 0.63,
                        "home_probability": 0.63,
                        "away_probability": 0.27,
                        "updated_at": now.isoformat(),
                    }
                },
            )
        )
        s.add(
            OddsSnapshot(
                id=7001,
                event_id=42,
                bookmaker="draftkings",
                home_moneyline=-170,
                away_moneyline=270,
                home_win_probability=0.63,
                away_win_probability=0.27,
                captured_at=now,
                reading_count=1,
            )
        )
        s.commit()

    with Session(eng) as s:
        db = _SyncAsAsync(s)
        ev43 = _load_event(db, 43)
        absorbed, complete = asyncio.run(
            serve_fold_absorbed_rows_with_completeness(db, ev43, keep_page_survivor=True)
        )
        assert absorbed == []
        assert complete is True

        detail_43 = asyncio.run(
            load_unified_game_reads(
                db,
                [ev43],
                collapse_in_page=False,
                include_same_league_external=True,
                include_odds=True,
                odds_query_fn=_portable_odds_query,
                now=now,
            )
        ).by_id[43]
        assert detail_43.bookmaker_count == 0
        assert detail_43.latest_snapshots == []
        assert detail_43.odds_data is None

    with Session(eng) as s:
        db = _SyncAsAsync(s)
        ev42 = _load_event(db, 42)
        ev43 = _load_event(db, 43)
        list_batch = asyncio.run(
            load_unified_game_reads(
                db,
                [ev42, ev43],
                collapse_in_page=True,
                include_same_league_external=True,
                include_odds=True,
                odds_query_fn=_portable_odds_query,
                now=now,
            )
        )
        assert list(list_batch.by_id.keys()) == [42]
        assert list_batch.by_id[42].bookmaker_count == 1


def test_13768_three_row_cluster_higher_ranked_other_status_loser_still_absorbs():
    """3-row cluster: live page row still absorbs when higher-ranked same-league loser has another status."""
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    kickoff = now - timedelta(minutes=20)
    src_stamp = (now - timedelta(minutes=1)).isoformat()

    with Session(eng) as s:
        s.add(Sport(id=S_SERIE_B, key="soccer_italy_serie_b", name="Serie B", group="Soccer"))
        s.add(Sport(id=76, key="soccer_other", name="Soccer Other", group="Soccer"))

        # 1. Page row: `live`, id-less (`external_id=None`, `espn_id=None`)
        s.add(
            Event(
                id=17001,
                sport_id=S_SERIE_B,
                away_team_name="Modena",
                home_team_name="Reggiana",
                commence_time=kickoff,
                status="live",
                external_id=None,
                win_probability_sources={"polymarket": {"value": 0.48, "updated_at": src_stamp}},
            )
        )
        # 2. Second loser: same league (`soccer_italy_serie_b`), DIFFERENT status (`scheduled`),
        #    ranked ABOVE 17001 via `external_id`, owning the sportsbook snapshots.
        s.add(
            Event(
                id=17002,
                sport_id=S_SERIE_B,
                away_team_name="Modena",
                home_team_name="Reggiana",
                commence_time=kickoff,
                status="scheduled",
                external_id="odds-17002",
                win_probability_sources={
                    "betting": {"value": 0.45, "updated_at": src_stamp},
                    "betting_book_count": 3,
                },
            )
        )
        # 3. Outside winner: `soccer_other` + `espn_id` (highest `twin_identity_rank`).
        s.add(
            Event(
                id=17003,
                sport_id=76,
                away_team_name="Modena",
                home_team_name="Reggiana",
                commence_time=kickoff,
                status="scheduled",
                espn_id="espn-17003",
                win_probability_sources={"kalshi": {"value": 0.52, "updated_at": src_stamp}},
            )
        )
        for i in range(3):
            s.add(
                OddsSnapshot(
                    id=7100 + i,
                    event_id=17002,
                    bookmaker=f"three_bk_{i}",
                    home_win_probability=0.45,
                    away_win_probability=0.25,
                    captured_at=now - timedelta(minutes=1),
                )
            )
        s.commit()

    with Session(eng) as s:
        db = _SyncAsAsync(s)
        ev_17001 = _load_event(db, 17001)
        list_read = asyncio.run(
            load_unified_game_reads(
                db,
                [ev_17001],
                collapse_in_page=True,
                include_same_league_external=True,
                include_odds=True,
                odds_query_fn=_portable_odds_query,
                now=now,
            )
        ).by_id[17001]

    with Session(eng) as s:
        db = _SyncAsAsync(s)
        ev_17001 = _load_event(db, 17001)
        detail_read = asyncio.run(
            load_unified_game_reads(
                db,
                [ev_17001],
                collapse_in_page=False,
                include_same_league_external=True,
                include_odds=True,
                odds_query_fn=_portable_odds_query,
                now=now,
            )
        ).by_id[17001]

    assert sorted(detail_read.folded_sources.keys()) == sorted(list_read.folded_sources.keys())
    for source_name in ("betting", "kalshi", "polymarket"):
        assert source_name in detail_read.folded_sources
    assert detail_read.bookmaker_count == list_read.bookmaker_count == 3

    # Control: once 17002 shares BOTH league and status (`live`) with 17001 and ranks higher,
    # detail must NOT absorb the cluster onto the in-slice loser.
    with Session(eng) as s:
        s.get(Event, 17002).status = "live"
        s.commit()

    with Session(eng) as s:
        db = _SyncAsAsync(s)
        ev_17001 = _load_event(db, 17001)
        absorbed_ctrl, complete_ctrl = asyncio.run(
            serve_fold_absorbed_rows_with_completeness(db, ev_17001, keep_page_survivor=True)
        )
        assert absorbed_ctrl == []
        assert complete_ctrl is True
        detail_ctrl = asyncio.run(
            load_unified_game_reads(
                db,
                [ev_17001],
                collapse_in_page=False,
                include_same_league_external=True,
                include_odds=True,
                odds_query_fn=_portable_odds_query,
                now=now,
            )
        ).by_id[17001]
        assert detail_ctrl.bookmaker_count == 0
        assert "betting" not in detail_ctrl.folded_sources
        assert "kalshi" not in detail_ctrl.folded_sources
