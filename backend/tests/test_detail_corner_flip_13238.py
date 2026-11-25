"""Guard tests for #13238/#13142 detail-page corner-flipping, Defect 3b, & list-vs-page parity."""

from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, event as sa_event, select
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
from app.routes import events as events_route  # noqa: E402
from app.routes.events import (  # noqa: E402
    _settled_prematch_odds,
    get_event,
    get_event_odds_history,
    list_events,
    search_events,
)
from app.utils.event_twin_fold import flip_probability_sources, fold_twin_events  # noqa: E402
from app.utils.history_coverage import read_coverage_prefix  # noqa: E402
from app.utils.proven_duplicates import (  # noqa: E402
    folded_probability_sources_with_revision,
    folded_series_event_ids,
    is_corner_flipped_absorbed,
    oriented_series_event_ids,
)
from app.utils.serve_fold_absorbed import (  # noqa: E402
    serve_fold_absorbed_rows,
    serve_fold_absorbed_rows_with_completeness,
)

S_WNCAAB = 10
S_EUROLEAGUE = 20
S_MLS = 41
S_BASKETBALL_OTHER = 99


class _SyncAsAsync:
    """Minimal async wrapper around SQLAlchemy sync Session with savepoints & UTC-aware timestamps."""

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


class _CapturePrematchDb:
    def __init__(self):
        self.binds = None

    async def begin_nested(self):
        class _Tx:
            async def commit(self):
                pass

            async def rollback(self):
                pass

        return _Tx()

    async def execute(self, statement, binds=None):
        self.binds = binds

        class _Empty:
            def all(self):
                return []

        return _Empty()


def _portable_odds_query(event_ids):
    return select(OddsSnapshot).where(OddsSnapshot.event_id.in_(event_ids))


def _restore_sqlite_utc(_session, instance):
    for attr in ("commence_time", "completed_at", "captured_at", "valid_until"):
        val = getattr(instance, attr, None)
        if isinstance(val, datetime) and val.tzinfo is None:
            setattr(instance, attr, val.replace(tzinfo=timezone.utc))


def _make_orm_event(
    event_id: int,
    *,
    sport_id: int = S_EUROLEAGUE,
    away: str,
    home: str,
    commence: datetime,
    completed_at: datetime | None = None,
    status: str = "scheduled",
    home_score: int | None = None,
    away_score: int | None = None,
    external_id: str | None = None,
    espn_id: str | None = None,
    commence_time_source: str | None = None,
    event_tags: list[str] | None = None,
    win_probability_sources: dict | None = None,
    win_probability_sources_rev: int = 1,
):
    return Event(
        id=event_id,
        sport_id=sport_id,
        away_team_name=away,
        home_team_name=home,
        commence_time=commence,
        completed_at=completed_at,
        commence_time_source=commence_time_source,
        status=status,
        home_score=home_score,
        away_score=away_score,
        external_id=external_id,
        espn_id=espn_id,
        event_tags=event_tags,
        win_probability_sources=win_probability_sources,
        win_probability_sources_rev=win_probability_sources_rev,
    )


def _kalshi_src(
    val: float,
    updated_at: str = "2025-11-24T12:00:00+00:00",
    *,
    source: str = "kalshi",
) -> dict:
    return {
        source: {
            "value": val,
            "observed_value": val,
            "updated_at": updated_at,
        }
    }


def _run_list_and_detail(
    eng,
    *,
    sport_key: str,
    survivor_id: int,
    days: int = 7,
) -> tuple[dict, dict]:
    """Run real `list_events` and real `get_event` over separate sessions on `eng`."""
    events_route._event_detail_cache.clear()
    with (
        patch("app.routes.events._load_gei_percentiles", new=AsyncMock(return_value={})),
        patch("app.routes.events._build_team_lookup", new=AsyncMock(return_value={})),
        patch(
            "app.routes.events.latest_odds_per_bookmaker_query",
            new=_portable_odds_query,
        ),
        patch(
            "app.utils.price_evidence.load_price_evidence",
            new=AsyncMock(return_value="tradeable_book"),
        ),
    ):
        with Session(eng) as s_list:
            sa_event.listen(s_list, "loaded_as_persistent", _restore_sqlite_utc)
            list_payload = asyncio.run(
                list_events(
                    sport=sport_key,
                    status=None,
                    days=days,
                    limit=200,
                    offset=0,
                    db=_SyncAsAsync(s_list),
                )
            )
        with Session(eng) as s_detail:
            sa_event.listen(s_detail, "loaded_as_persistent", _restore_sqlite_utc)
            detail_payload = asyncio.run(
                get_event(
                    survivor_id,
                    db=_SyncAsAsync(s_detail),
                    fresh=True,
                )
            )
    events_route._event_detail_cache.clear()
    return list_payload, detail_payload


@pytest.mark.parametrize("sport_key", ["basketball_euroleague", "basketball_wncaab"])
@pytest.mark.parametrize("state", ["live", "finished"])
def test_reversed_pair_list_and_detail_agree_on_every_source(sport_key: str, state: str):
    """Fable req #2: reversed pairs return identical source values & hero on list and page."""
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    now = datetime.now(timezone.utc).replace(microsecond=0)

    if state == "live":
        anchor_commence = now - timedelta(minutes=30)
        completed_at = None
        anchor_status = "live"
        claim_status = "live"
        anchor_scores = (44, 39)
        src_stamp = (now - timedelta(minutes=1)).isoformat()
    else:
        anchor_commence = now - timedelta(hours=4)
        completed_at = now - timedelta(hours=2)
        anchor_status = "completed"
        claim_status = "completed"
        anchor_scores = (84, 76)
        src_stamp = (now - timedelta(hours=5)).isoformat()

    if sport_key == "basketball_euroleague":
        sport_id = S_EUROLEAGUE
        sport_name = "EuroLeague"
        surv_id, loser_id = 15351534, 15352077
        surv_away, surv_home = "Maccabi Tel Aviv", "FC Bayern München"
        loser_away, loser_home = "Bayern Munich", "Maccabi Tel-Aviv"
        claim_commence = anchor_commence + timedelta(hours=3)
        claim_commence_source = "kalshi"
        venue_key = "kalshi"
        raw_loser_val = 0.415
        anchor_sources = {
            "betting": {"value": 0.5662, "updated_at": src_stamp},
            "betting_book_count": 4,
            "polymarket": {"value": 0.56, "updated_at": src_stamp},
        }
    else:
        sport_id = S_WNCAAB
        sport_name = "WNCAAB"
        surv_id, loser_id = 15351654, 15348230
        surv_away, surv_home = "New Mexico St Aggies", "Arizona Wildcats"
        loser_away, loser_home = "Arizona Wildcats", "New Mexico State Aggies"
        claim_commence = anchor_commence
        claim_commence_source = None
        venue_key = "polymarket"
        raw_loser_val = 0.08
        anchor_sources = {
            "stat_model": {"value": 0.9077, "updated_at": src_stamp},
        }

    with Session(eng) as s:
        s.add(Sport(id=sport_id, key=sport_key, name=sport_name, group="Basketball"))
        s.add(
            _make_orm_event(
                surv_id,
                sport_id=sport_id,
                away=surv_away,
                home=surv_home,
                commence=anchor_commence,
                completed_at=completed_at,
                status=anchor_status,
                home_score=anchor_scores[0],
                away_score=anchor_scores[1],
                external_id=f"odds-{surv_id}",
                win_probability_sources=anchor_sources,
                win_probability_sources_rev=200,
            )
        )
        s.add(
            _make_orm_event(
                loser_id,
                sport_id=sport_id,
                away=loser_away,
                home=loser_home,
                commence=claim_commence,
                completed_at=completed_at,
                status=claim_status,
                home_score=None,
                away_score=None,
                external_id=None,
                commence_time_source=claim_commence_source,
                win_probability_sources=_kalshi_src(
                    raw_loser_val, updated_at=src_stamp, source=venue_key
                ),
                win_probability_sources_rev=50,
            )
        )
        s.commit()

    list_payload, detail_payload = _run_list_and_detail(
        eng, sport_key=sport_key, survivor_id=surv_id
    )
    assert len(list_payload["events"]) == 1
    list_card = list_payload["events"][0]
    assert list_card["id"] == surv_id
    assert detail_payload["id"] == surv_id

    list_wps = list_card["win_probability_sources"]
    detail_wps = detail_payload["win_probability_sources"]
    assert set(detail_wps) == set(list_wps)
    for k in list_wps:
        assert detail_wps[k]["value"] == pytest.approx(list_wps[k]["value"])

    expected_flipped = round(1.0 - raw_loser_val, 10)
    assert list_wps[venue_key]["value"] == pytest.approx(expected_flipped)
    assert detail_wps[venue_key]["value"] == pytest.approx(expected_flipped)

    assert detail_payload["hero_probability"] == pytest.approx(
        list_card["hero_probability"]
    )
    assert detail_payload["hero_probability_source"] == list_card["hero_probability_source"]
    if state == "live":
        assert detail_payload["hero_probability_source"] == "blend"
    else:
        assert detail_payload["hero_probability_source"] == "settled"
        assert detail_payload["hero_probability"] == pytest.approx(1.0)


def test_scheduled_euroleague_15351534_list_and_detail_headline_and_kalshi_agree():
    """Exact 15351534 scheduled pair: flipping kalshi to 0.585 keeps headline at 0.5662 on BOTH."""
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    kickoff = now + timedelta(days=1)
    src_stamp = (now - timedelta(minutes=1)).isoformat()

    with Session(eng) as s:
        s.add(Sport(id=S_EUROLEAGUE, key="basketball_euroleague", name="EuroLeague", group="Basketball"))
        s.add(
            _make_orm_event(
                15351534,
                sport_id=S_EUROLEAGUE,
                away="Maccabi Tel Aviv",
                home="FC Bayern München",
                commence=kickoff,
                external_id="6bcef0e5f7b2a021b7e07514cdfa6493",
                win_probability_sources={
                    "betting": {"value": 0.5662, "updated_at": src_stamp},
                    "betting_book_count": 4,
                    "polymarket": {"value": 0.56, "updated_at": src_stamp},
                },
                win_probability_sources_rev=276,
            )
        )
        s.add(
            _make_orm_event(
                15352077,
                sport_id=S_EUROLEAGUE,
                away="Bayern Munich",
                home="Maccabi Tel-Aviv",
                commence=kickoff + timedelta(hours=3),
                external_id=None,
                commence_time_source="kalshi",
                win_probability_sources=_kalshi_src(0.415, updated_at=src_stamp),
                win_probability_sources_rev=248,
            )
        )
        s.commit()

    list_payload, detail_payload = _run_list_and_detail(
        eng, sport_key="basketball_euroleague", survivor_id=15351534
    )
    assert len(list_payload["events"]) == 1
    list_card = list_payload["events"][0]
    assert list_card["win_probability_sources"]["kalshi"]["value"] == pytest.approx(0.585)
    assert detail_payload["win_probability_sources"]["kalshi"]["value"] == pytest.approx(0.585)
    assert list_card["hero_probability"] == pytest.approx(0.5662)
    assert detail_payload["hero_probability"] == pytest.approx(0.5662)


def test_euroleague_reversed_detail_fold_flips_kalshi_and_keeps_session_clean():
    """All 3 EuroLeague reversed pairs flip value + observed_value without dirtying ORM."""
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    fixtures = [
        (
            15351534,
            "Maccabi Tel Aviv",
            "FC Bayern München",
            datetime(2025, 11, 24, 19, 0, tzinfo=timezone.utc),
            0.5662,
            15352077,
            "Bayern Munich",
            "Maccabi Tel-Aviv",
            datetime(2025, 11, 24, 22, 0, tzinfo=timezone.utc),
            0.415,
            0.585,
        ),
        (
            15351900,
            "Hapoel Tel Aviv",
            "Olympiacos",
            datetime(2025, 11, 25, 19, 15, tzinfo=timezone.utc),
            0.6464,
            15352630,
            "BC Olympiakos Piraeus",
            "Hapoel Tel-Aviv",
            datetime(2025, 11, 25, 22, 15, tzinfo=timezone.utc),
            0.345,
            0.655,
        ),
        (
            15351920,
            "Anadolu Efes",
            "Saski Baskonia",
            datetime(2025, 11, 25, 19, 30, tzinfo=timezone.utc),
            0.4824,
            15352631,
            "Baskonia Vitoria-Gasteiz",
            "Anadolu Efes SK",
            datetime(2025, 11, 25, 22, 30, tzinfo=timezone.utc),
            0.52,
            0.48,
        ),
    ]
    with Session(eng) as s:
        s.add(Sport(id=S_EUROLEAGUE, key="basketball_euroleague", name="EuroLeague"))
        for sid, a1, h1, t1, bval, lid, a2, h2, t2, kval, _ in fixtures:
            s.add(
                _make_orm_event(
                    sid,
                    away=a1,
                    home=h1,
                    commence=t1,
                    external_id=f"odds-{sid}",
                    win_probability_sources={"betting": {"value": bval}},
                    win_probability_sources_rev=200,
                )
            )
            s.add(
                _make_orm_event(
                    lid,
                    away=a2,
                    home=h2,
                    commence=t2,
                    external_id=None,
                    commence_time_source="kalshi",
                    win_probability_sources=_kalshi_src(kval),
                    win_probability_sources_rev=50,
                )
            )
        s.commit()

    for sid, _a1, _h1, _t1, bval, lid, _a2, _h2, _t2, _kval, expected_k in fixtures:
        with Session(eng) as s:
            db = _SyncAsAsync(s)
            surv = asyncio.run(
                db.execute(
                    select(Event).options(selectinload(Event.sport)).where(Event.id == sid)
                )
            ).scalar_one()
            absorbed, complete = asyncio.run(
                serve_fold_absorbed_rows_with_completeness(db, surv)
            )
            assert complete is True
            assert [r.id for r in absorbed] == [lid]
            assert is_corner_flipped_absorbed(absorbed[0]) is True

            sources, rev = asyncio.run(
                folded_probability_sources_with_revision(db, surv, absorbed)
            )
            assert sources["betting"]["value"] == pytest.approx(bval)
            assert sources["kalshi"]["value"] == pytest.approx(expected_k)
            assert sources["kalshi"]["observed_value"] == pytest.approx(expected_k)
            assert rev == {str(sid): 200, str(lid): 50}
            assert not s.dirty


def test_defect_3b_catchall_merged_cluster_does_not_block_reversed_absorbed_fold():
    """Exact live 15351540/15350585(basketball_other)/15352078 triple folds all 3 sources."""
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    kickoff = now + timedelta(days=1)
    src_stamp = (now - timedelta(minutes=1)).isoformat()

    with Session(eng) as s:
        s.add(Sport(id=S_EUROLEAGUE, key="basketball_euroleague", name="EuroLeague", group="Basketball"))
        s.add(Sport(id=S_BASKETBALL_OTHER, key="basketball_other", name="Basketball", group="Basketball"))
        e1540 = _make_orm_event(
            15351540,
            sport_id=S_EUROLEAGUE,
            away="Pallacanestro Olimpia Milano",
            home="ASVEL Lyon Villeurbanne",
            commence=kickoff,
            external_id="1707b8c728b9116472624aa8178ebfce",
            win_probability_sources={"betting": {"value": 0.4773, "updated_at": src_stamp}},
            win_probability_sources_rev=276,
        )
        # Live shape: untagged basketball_other row absorbed into 15351540 by _merge_catchall_leagues
        e0585 = _make_orm_event(
            15350585,
            sport_id=S_BASKETBALL_OTHER,
            away="Olimpia Milano",
            home="ASVEL Lyon-Villeurbanne",
            commence=kickoff,
            external_id=None,
            win_probability_sources={"polymarket": {"value": 0.47, "updated_at": src_stamp}},
            win_probability_sources_rev=29,
        )
        e2078 = _make_orm_event(
            15352078,
            sport_id=S_EUROLEAGUE,
            away="ASVEL Lyon-Villeurbanne",
            home="Olimpia Milano",
            commence=kickoff + timedelta(hours=3),
            external_id=None,
            commence_time_source="kalshi",
            win_probability_sources=_kalshi_src(0.525, updated_at=src_stamp),
            win_probability_sources_rev=61,
        )
        s.add_all([e1540, e0585, e2078])
        s.commit()

    with Session(eng) as s:
        sa_event.listen(s, "loaded_as_persistent", _restore_sqlite_utc)
        rows = (
            s.execute(select(Event).options(selectinload(Event.sport)).order_by(Event.id))
            .scalars()
            .all()
        )
        direct_fold = fold_twin_events(rows)
        assert [e.id for e in direct_fold.events] == [15351540]
        assert direct_fold.flipped_loser_ids == {15352078}
        assert direct_fold.merged_sources[15351540]["betting"]["value"] == pytest.approx(0.4773)
        assert direct_fold.merged_sources[15351540]["polymarket"]["value"] == pytest.approx(0.47)
        assert direct_fold.merged_sources[15351540]["kalshi"]["value"] == pytest.approx(0.475)

        db = _SyncAsAsync(s)
        surv = next(r for r in rows if r.id == 15351540)
        absorbed, complete = asyncio.run(serve_fold_absorbed_rows_with_completeness(db, surv))
        assert complete is True
        assert [r.id for r in absorbed] == [15350585, 15352078]
        by_id = {r.id: r for r in absorbed}
        assert is_corner_flipped_absorbed(by_id[15350585]) is False
        assert is_corner_flipped_absorbed(by_id[15352078]) is True

        sources, rev = asyncio.run(
            folded_probability_sources_with_revision(db, surv, absorbed)
        )
        assert sources["betting"]["value"] == pytest.approx(0.4773)
        assert sources["polymarket"]["value"] == pytest.approx(0.47)
        assert sources["kalshi"]["value"] == pytest.approx(0.475)
        assert rev == {"15351540": 276, "15350585": 29, "15352078": 61}

    events_route._event_detail_cache.clear()
    with (
        patch("app.routes.events._load_gei_percentiles", new=AsyncMock(return_value={})),
        patch("app.routes.events._build_team_lookup", new=AsyncMock(return_value={})),
        patch("app.routes.events.latest_odds_per_bookmaker_query", new=_portable_odds_query),
        patch("app.utils.price_evidence.load_price_evidence", new=AsyncMock(return_value="tradeable_book")),
        Session(eng) as s_detail,
    ):
        sa_event.listen(s_detail, "loaded_as_persistent", _restore_sqlite_utc)
        detail = asyncio.run(get_event(15351540, db=_SyncAsAsync(s_detail), fresh=True))
    events_route._event_detail_cache.clear()
    assert detail["win_probability_sources"]["betting"]["value"] == pytest.approx(0.4773)
    assert detail["win_probability_sources"]["polymarket"]["value"] == pytest.approx(0.47)
    assert detail["win_probability_sources"]["kalshi"]["value"] == pytest.approx(0.475)


def test_defect_3b_tagged_duplicate_excluded_in_serve_fold_and_pure_other_refused():
    """Tagged proven duplicate stays excluded in serve_fold; pure basketball_other reversed pair refuses."""
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    kickoff = datetime(2025, 11, 24, 19, 45, tzinfo=timezone.utc)
    with Session(eng) as s:
        s.add(Sport(id=S_EUROLEAGUE, key="basketball_euroleague", name="EuroLeague"))
        s.add(Sport(id=S_BASKETBALL_OTHER, key="basketball_other", name="Basketball"))
        s.add(
            _make_orm_event(
                15351540,
                sport_id=S_EUROLEAGUE,
                away="Pallacanestro Olimpia Milano",
                home="ASVEL Lyon Villeurbanne",
                commence=kickoff,
                external_id="1707b8c728b9116472624aa8178ebfce",
                win_probability_sources={"betting": {"value": 0.4773}},
                win_probability_sources_rev=276,
            )
        )
        s.add(
            _make_orm_event(
                15350585,
                sport_id=S_BASKETBALL_OTHER,
                away="Olimpia Milano",
                home="ASVEL Lyon-Villeurbanne",
                commence=kickoff,
                external_id="poly-anchored-15350585",
                event_tags=["provenance:duplicate-of:15351540"],
                win_probability_sources={"polymarket": {"value": 0.47}},
                win_probability_sources_rev=29,
            )
        )
        s.add(
            _make_orm_event(
                15352078,
                sport_id=S_EUROLEAGUE,
                away="ASVEL Lyon-Villeurbanne",
                home="Olimpia Milano",
                commence=kickoff + timedelta(hours=3),
                external_id=None,
                commence_time_source="kalshi",
                win_probability_sources=_kalshi_src(0.525),
                win_probability_sources_rev=61,
            )
        )
        # Control: pure basketball_other reversed pair with NO allowlisted league row
        other_a = _make_orm_event(
            9901,
            sport_id=S_BASKETBALL_OTHER,
            away="Alpha BC",
            home="Beta BC",
            commence=kickoff,
            external_id="odds-other-9901",
            win_probability_sources={"betting": {"value": 0.6}},
        )
        other_b = _make_orm_event(
            9902,
            sport_id=S_BASKETBALL_OTHER,
            away="Beta BC",
            home="Alpha BC",
            commence=kickoff,
            external_id=None,
            win_probability_sources=_kalshi_src(0.4),
        )
        s.add_all([other_a, other_b])
        s.commit()

        pure_other_fold = fold_twin_events([other_a, other_b])
        assert pure_other_fold.folded_count == 0

    with Session(eng) as s:
        db = _SyncAsAsync(s)
        surv = asyncio.run(
            db.execute(
                select(Event).options(selectinload(Event.sport)).where(Event.id == 15351540)
            )
        ).scalar_one()
        absorbed = asyncio.run(serve_fold_absorbed_rows(db, surv))
        assert [r.id for r in absorbed] == [15352078]
        assert is_corner_flipped_absorbed(absorbed[0]) is True

        sources, rev = asyncio.run(
            folded_probability_sources_with_revision(db, surv, absorbed)
        )
        assert sources["betting"]["value"] == pytest.approx(0.4773)
        assert sources["polymarket"]["value"] == pytest.approx(0.47)
        assert sources["kalshi"]["value"] == pytest.approx(0.475)
        assert rev == {"15351540": 276, "15350585": 29, "15352078": 61}


def test_series_ids_coverage_prematch_and_route_wiring_option_a():
    """Option A: `folded_series_event_ids` keeps flipped twin for coverage/stream, `oriented_series_event_ids` excludes it."""
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    kickoff = datetime(2025, 11, 24, 19, 0, tzinfo=timezone.utc)
    with Session(eng) as s:
        s.add(Sport(id=S_EUROLEAGUE, key="basketball_euroleague", name="EuroLeague"))
        s.add(
            _make_orm_event(
                15351534,
                away="Maccabi Tel Aviv",
                home="FC Bayern München",
                commence=kickoff,
                external_id="odds-15351534",
                win_probability_sources={"betting": {"value": 0.5662}},
                win_probability_sources_rev=200,
            )
        )
        s.add(
            _make_orm_event(
                15352077,
                away="Bayern Munich",
                home="Maccabi Tel-Aviv",
                commence=datetime(2025, 11, 24, 22, 0, tzinfo=timezone.utc),
                external_id=None,
                commence_time_source="kalshi",
                win_probability_sources=_kalshi_src(0.415),
                win_probability_sources_rev=50,
            )
        )
        s.commit()

    with Session(eng) as s:
        db = _SyncAsAsync(s)
        surv = asyncio.run(
            db.execute(
                select(Event).options(selectinload(Event.sport)).where(Event.id == 15351534)
            )
        ).scalar_one()
        absorbed, complete = asyncio.run(
            serve_fold_absorbed_rows_with_completeness(db, surv)
        )
        assert [r.id for r in absorbed] == [15352077]

        series_ids = asyncio.run(folded_series_event_ids(db, 15351534, absorbed))
        assert series_ids == [15351534, 15352077]
        assert oriented_series_event_ids(series_ids, absorbed) == [15351534]

        prefix = asyncio.run(
            read_coverage_prefix(
                db, surv, absorbed, series_ids, membership_complete=complete
            )
        )
        assert prefix == {"15351534": 200, "15352077": 50}

        cap_db = _CapturePrematchDb()
        surv.status = "completed"
        surv.completed_at = kickoff + timedelta(hours=2)
        asyncio.run(
            _settled_prematch_odds(cap_db, surv, "basketball_euroleague", absorbed)
        )
        assert cap_db.binds is not None
        assert cap_db.binds["ids"] == [15351534]

    from app.utils import unified_game_read

    src_detail = inspect.getsource(get_event)
    assert "load_unified_game_reads(" in src_detail
    src_unified = inspect.getsource(unified_game_read.load_unified_game_reads)
    assert "is_corner_flipped_absorbed(" in src_unified

    src_history = inspect.getsource(get_event_odds_history)
    assert "oriented_series_ids = oriented_series_event_ids(series_event_ids, absorbed)" in src_history
    assert "OddsSnapshot.event_id.in_(oriented_series_ids)" in src_history
    assert "ScoreSnapshot.event_id.in_(oriented_series_ids)" in src_history
    assert "WinProbSnapshot.event_id.in_(oriented_series_ids)" in src_history

    src_list = inspect.getsource(list_events)
    assert "load_unified_game_reads(" in src_list
    src_search = inspect.getsource(search_events)
    assert "load_unified_game_reads(" in src_search


def test_unflippable_source_on_reversed_absorbed_row_fails_closed():
    """Never copy an unflipped reading when flip_probability_sources rejects an unknown key."""
    assert flip_probability_sources({"kalshi": {"value": 0.415, "unexpected": 1}}) == (
        False,
        None,
    )
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    kickoff = datetime(2025, 11, 24, 19, 0, tzinfo=timezone.utc)
    with Session(eng) as s:
        s.add(Sport(id=S_EUROLEAGUE, key="basketball_euroleague", name="EuroLeague"))
        surv = _make_orm_event(
            9001,
            away="Team A",
            home="Team B",
            commence=kickoff,
            external_id="odds-9001",
            win_probability_sources={"betting": {"value": 0.6}},
            win_probability_sources_rev=10,
        )
        loser = _make_orm_event(
            9002,
            away="Team B",
            home="Team A",
            commence=kickoff,
            external_id=None,
            win_probability_sources={"kalshi": {"value": 0.6, "unexpected": 1}},
            win_probability_sources_rev=5,
        )
        s.add_all([surv, loser])
        s.commit()

        setattr(loser, "_serve_fold_corner_flipped", True)
        db = _SyncAsAsync(s)
        sources, rev = asyncio.run(
            folded_probability_sources_with_revision(db, surv, [loser])
        )
        assert sources == {"betting": {"value": 0.6}}
        assert rev == {"9001": 10, "9002": 5}


def test_non_reversed_absorbed_row_preserves_unflipped_behavior_and_flipped_loser_ids():
    """Same-corner fold keeps flipped_loser_ids empty and serves series + sources normally."""
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    kickoff = datetime(2025, 11, 24, 19, 0, tzinfo=timezone.utc)
    with Session(eng) as s:
        s.add(Sport(id=S_MLS, key="soccer_usa_mls", name="MLS"))
        surv = _make_orm_event(
            9101,
            sport_id=S_MLS,
            away="LAFC",
            home="FC Dallas",
            commence=kickoff,
            espn_id="761835",
            win_probability_sources={"betting": {"value": 0.45}},
            win_probability_sources_rev=12,
        )
        loser = _make_orm_event(
            9102,
            sport_id=S_MLS,
            away="Los Angeles FC",
            home="FC Dallas",
            commence=kickoff,
            external_id="ext-9102",
            win_probability_sources=_kalshi_src(0.425),
            win_probability_sources_rev=4,
        )
        s.add_all([surv, loser])
        s.commit()

        direct_fold = fold_twin_events([surv, loser])
        assert direct_fold.flipped_loser_ids == set()

        db = _SyncAsAsync(s)
        surv_loaded = asyncio.run(
            db.execute(
                select(Event).options(selectinload(Event.sport)).where(Event.id == 9101)
            )
        ).scalar_one()
        absorbed, _complete = asyncio.run(
            serve_fold_absorbed_rows_with_completeness(db, surv_loaded)
        )
        assert [r.id for r in absorbed] == [9102]
        assert is_corner_flipped_absorbed(absorbed[0]) is False
        assert oriented_series_event_ids([9101, 9102], absorbed) == [9101, 9102]

        sources, _rev = asyncio.run(
            folded_probability_sources_with_revision(db, surv_loaded, absorbed)
        )
        assert sources["kalshi"]["value"] == pytest.approx(0.425)
