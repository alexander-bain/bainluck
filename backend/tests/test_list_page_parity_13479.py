"""Regression and parity guards for #13479: list card equals game page.

Covers PR 2's two root causes plus Fable's reversed-twin orientation gate and
shared-helper controls:
1. Cause 1 — ``GET /api/events?sport=<league>`` folds unlinked catch-all twins
   (e.g. ``soccer_other`` / ``basketball_other``) using the shared
   ``serve_fold_absorbed`` machinery without leaking unmatched ``*_other`` rows
   onto the scoped league list or replacing the league's own canonical row.
2. Cause 2 — ``list_events`` feeds same-orientation absorbed twin IDs into
   ``latest_odds_per_bookmaker_query`` and picks the freshest snapshot per
   bookmaker via ``group_latest_snapshots_by_event`` ->
   ``latest_snapshot_for_each_bookmaker`` (identical to ``get_event``),
   preventing stale survivor snapshots from hiding a twin's fresh lines.
3. Condition 2 — Reversed-team absorbed twins (whether flagged in-memory via
   ``flipped_loser_ids`` or stored via ``duplicate_of:<id>`` with swapped home
   and away teams) have their ``odds_snapshots`` excluded on BOTH ``list_events``
   and ``get_event`` so unflipped prices are never blended onto the card.
4. Zero-extra-query controls when ``sport=None`` or ``sport="soccer_other"``.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import Event, OddsSnapshot, Sport
from app.routes.events import get_event, list_events
from app.utils.proven_duplicates import duplicate_tag


NOW = datetime(2026, 11, 23, 18, 0, tzinfo=timezone.utc)
COMMENCE = NOW + timedelta(hours=3)

SOCCER_LEAGUE = Sport(
    id=77,
    key="soccer_italy_serie_b",
    name="Serie B",
)
SOCCER_OTHER = Sport(
    id=88,
    key="soccer_other",
    name="Soccer Other",
)
BASKET_LEAGUE = Sport(
    id=99,
    key="basketball_euroleague",
    name="EuroLeague",
)
BASKET_OTHER = Sport(
    id=111,
    key="basketball_other",
    name="Basketball Other",
)


def _event(
    eid: int,
    *,
    sport=SOCCER_LEAGUE,
    home: str = "Bari",
    away: str = "Mantova",
    commence: datetime = COMMENCE,
    status: str = "scheduled",
    espn_id: str | None = None,
    external_id: str | None = None,
    sources: dict | None = None,
    tags: list[str] | None = None,
    opening_home: float | None = None,
    opening_away: float | None = None,
) -> Event:
    ev = Event(
        id=eid,
        sport_id=sport.id,
        home_team_name=home,
        away_team_name=away,
        home_team_id=eid * 10 + 1,
        away_team_id=eid * 10 + 2,
        commence_time=commence,
        status=status,
        espn_id=espn_id,
        external_id=external_id,
        win_probability_sources=sources if sources is not None else {},
        event_tags=tags if tags is not None else [],
        opening_home_probability=opening_home,
        opening_away_probability=opening_away,
    )
    ev.sport = sport
    return ev


def _ml_for_prob(p: float) -> int:
    return -round(100 * p / (1.0 - p)) if p >= 0.5 else round(100 * (1.0 - p) / p)


def _snap(
    snap_id: int,
    event_id: int,
    bookmaker: str,
    home_prob: float,
    away_prob: float,
    *,
    captured_at: datetime,
    home_spread: float | None = None,
    over_under: float | None = None,
) -> OddsSnapshot:
    return OddsSnapshot(
        id=snap_id,
        event_id=event_id,
        bookmaker=bookmaker,
        home_moneyline=_ml_for_prob(home_prob),
        away_moneyline=_ml_for_prob(away_prob),
        home_win_probability=home_prob,
        away_win_probability=away_prob,
        home_spread=home_spread,
        over_under=over_under,
        captured_at=captured_at,
    )


def _make_route_db(
    *,
    sports: list,
    page_events: list,
    other_events: list,
    tagged_twins: list | None = None,
    snapshots: list | None = None,
):
    """Build a statement-routing AsyncMock DB for ``list_events`` & ``get_event``."""
    all_events = list(page_events) + list(other_events) + list(tagged_twins or [])
    by_id = {ev.id: ev for ev in all_events}
    snaps = list(snapshots or [])
    recorded_odds_event_ids: list[list[int]] = []
    sports_like_queries: list[str] = []

    def _result(rows=None, *, scalar=None, one_row=None):
        res = MagicMock()
        rows_list = list(rows or [])
        res.all.return_value = rows_list
        res.fetchall.return_value = rows_list
        res.scalars.return_value.all.return_value = rows_list
        res.scalar_one_or_none.return_value = (
            scalar if scalar is not None else (rows_list[0] if len(rows_list) == 1 else None)
        )
        res.scalar.return_value = scalar
        res.one.return_value = one_row
        return res

    async def execute(stmt, *args, **kwargs):
        sql = str(stmt)
        low = sql.lower()
        try:
            params = stmt.compile().params
        except Exception:
            params = {}
        param_vals = list(params.values())

        # _pinned_live_probability over win_prob_snapshots
        if "win_prob_snapshots" in low and "count(" in low:
            return _result(one_row=(0, 0, None, None, None))

        # Sports lookup (_partition_foldable_sport_ids or list_events sport check)
        if "from sports" in low:
            if "sports.key like" in low:
                sports_like_queries.append(sql)
                prefixes = [v for v in param_vals if isinstance(v, str) and v.endswith("%")]
                matched = [
                    (s.id, s.key)
                    for s in sports
                    if not prefixes or any(s.key.startswith(p[:-1]) for p in prefixes)
                ]
                return _result(matched)
            key_params = {v for v in param_vals if isinstance(v, str)}
            matched = [s for s in sports if s.key in key_params]
            return _result(matched, scalar=matched[0] if matched else None)

        # Latest odds per bookmaker (WITH RECURSIVE odds_bookmakers / odds_snapshots)
        if "odds_snapshots" in low and "percentile_cont" not in low:
            req_ids: set[int] = set()
            for k, v in params.items():
                if "id_" not in k:
                    continue
                if isinstance(v, (list, tuple, set)):
                    req_ids.update(int(x) for x in v if isinstance(x, int))
                elif isinstance(v, int):
                    req_ids.add(v)
            recorded_odds_event_ids.append(sorted(req_ids))
            latest_by_pair: dict[tuple[int, str], OddsSnapshot] = {}
            for snap in snaps:
                if req_ids and snap.event_id not in req_ids:
                    continue
                pair = (snap.event_id, snap.bookmaker)
                inc = latest_by_pair.get(pair)
                if inc is None or (snap.captured_at, snap.id) > (inc.captured_at, inc.id):
                    latest_by_pair[pair] = snap
            return _result(list(latest_by_pair.values()))

        # Narrow proven-duplicate column queries (folded_card_numbers_batch /
        # folded_series_event_ids / folded_probability_sources_with_revision) —
        # distinguish from full `select(Event)` by checking `commence_time` absence.
        if (
            "from events" in low
            and "events.home_team_name" in low
            and "events.commence_time" not in low
        ):
            wanted_tags: set[str] = set()
            wanted_ids: set[int] = set()
            for k, v in params.items():
                for found in re.findall(r"provenance:duplicate-of:\d+", str(v)):
                    wanted_tags.add(found)
                if "id" in k and isinstance(v, int):
                    wanted_ids.add(v)
                elif "id" in k and isinstance(v, (list, tuple, set)):
                    wanted_ids.update(int(x) for x in v if isinstance(x, int))
            matched_ev = [
                ev
                for ev in all_events
                if (ev.id in wanted_ids)
                or any(tag in wanted_tags for tag in (ev.event_tags or []))
            ]
            if "events.opening_home_probability" in low:
                # _folded_twins_batch
                return _result([
                    (
                        ev.id,
                        ev.home_team_name,
                        ev.away_team_name,
                        ev.win_probability_sources,
                        ev.event_tags,
                        ev.opening_home_probability,
                        ev.opening_away_probability,
                    )
                    for ev in matched_ev
                    if any(tag in wanted_tags for tag in (ev.event_tags or []))
                ])
            if "events.win_probability_sources" in low:
                return _result([
                    (
                        ev.id,
                        ev.home_team_name,
                        ev.away_team_name,
                        ev.win_probability_sources,
                    )
                    for ev in matched_ev
                    if any(tag in wanted_tags for tag in (ev.event_tags or []))
                ])
            # folded_series_event_ids (select id, home_team_name, away_team_name)
            return _result([(ev.id, ev.home_team_name, ev.away_team_name) for ev in matched_ev])

        # get_event direct fetch by events.id = :id_1
        if "from events" in low and "where events.id =" in low and "events.id !=" not in low:
            for v in param_vals:
                if isinstance(v, int) and v in by_id:
                    return _result([by_id[v]], scalar=by_id[v])
            return _result([], scalar=None)

        # _read_candidates / extra catch-all fetch (excludes page IDs / own event ID)
        if "from events" in low and ("events.id !=" in low or "events.id not in" in low):
            sport_filter_ids: set[int] = set()
            sport_filter_keys: set[str] = set()
            excl_ids: set[int] = set()
            for k, v in params.items():
                if "sport_id" in k:
                    if isinstance(v, (list, tuple, set)):
                        sport_filter_ids.update(int(x) for x in v if isinstance(x, int))
                    elif isinstance(v, int):
                        sport_filter_ids.add(v)
                elif "key" in k:
                    if isinstance(v, (list, tuple, set)):
                        sport_filter_keys.update(str(x) for x in v)
                    elif isinstance(v, str):
                        sport_filter_keys.add(v)
                elif "id" in k:
                    if isinstance(v, (list, tuple, set)):
                        excl_ids.update(int(x) for x in v if isinstance(x, int))
                    elif isinstance(v, int):
                        excl_ids.add(v)
            candidates = [
                ev
                for ev in (other_events + page_events)
                if ev.id not in excl_ids
                and (not sport_filter_ids or ev.sport_id in sport_filter_ids)
                and (not sport_filter_keys or (getattr(ev, "sport", None) and ev.sport.key in sport_filter_keys))
                and not any(str(t).startswith("duplicate_of:") for t in (ev.event_tags or []))
            ]
            return _result(candidates)

        # list_events main query
        if "from events" in low:
            return _result(page_events)

        return _result([])

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=execute)
    db.begin_nested = MagicMock()
    db.recorded_odds_event_ids = recorded_odds_event_ids
    db.sports_like_queries = sports_like_queries
    return db


async def _call_list(db, *, sport_key: str):
    with (
        patch("app.routes.events._load_gei_percentiles", new=AsyncMock(return_value={})),
        patch("app.routes.events._build_team_lookup", new=AsyncMock(return_value={})),
    ):
        return await list_events(
            sport=sport_key,
            status=None,
            days=7,
            limit=200,
            offset=0,
            db=db,
        )


async def _call_page(db, event_id: int):
    with (
        patch("app.routes.events._load_gei_percentiles", new=AsyncMock(return_value={})),
        patch("app.routes.events._build_team_lookup", new=AsyncMock(return_value={})),
    ):
        return await get_event(event_id=event_id, db=db, fresh=True)


# ── Cause 1: single-sport list folds unlinked *_other catch-all twins ─────────


@pytest.mark.asyncio
async def test_single_sport_list_folds_catchall_twin_sources_and_odds():
    """Models #13479 #15351540: league row lacks Polymarket, catch-all row holds it."""
    canonical = _event(
        15351540,
        sport=BASKET_LEAGUE,
        home="Hapoel Tel Aviv",
        away="Barcelona",
        status="scheduled",
        sources={},  # no venue sources on league row
    )
    # Unlinked basketball_other twin carrying Polymarket (and extra sources so
    # `_elect` would score it above `canonical` unless the list keeps its own row).
    catchall_twin = _event(
        15350585,
        sport=BASKET_OTHER,
        home="Hapoel Tel Aviv",
        away="Barcelona",
        status="scheduled",
        sources={
            "polymarket": {"value": 0.47, "updated_at": NOW.isoformat()},
            "kalshi": {"value": 0.49, "updated_at": NOW.isoformat()},
        },
    )
    # Unrelated basketball_other game in the same window must NEVER leak onto
    # the EuroLeague list.
    unrelated_other = _event(
        15359999,
        sport=BASKET_OTHER,
        home="Unrelated Club A",
        away="Unrelated Club B",
        status="scheduled",
        sources={"polymarket": {"value": 0.61, "updated_at": NOW.isoformat()}},
    )
    book_snap = _snap(
        901,
        catchall_twin.id,
        "draftkings",
        0.52,
        0.48,
        captured_at=NOW - timedelta(minutes=2),
    )

    db = _make_route_db(
        sports=[BASKET_LEAGUE, BASKET_OTHER],
        page_events=[canonical],
        other_events=[catchall_twin, unrelated_other],
        snapshots=[book_snap],
    )

    list_payload = await _call_list(db, sport_key="basketball_euroleague")
    assert not db.sports_like_queries
    page_payload = await _call_page(db, canonical.id)

    assert len(list_payload["events"]) == 1
    card = list_payload["events"][0]
    assert card["id"] == canonical.id
    assert "polymarket" in (card.get("win_probability_sources") or {})
    assert {s["key"] for s in (card.get("source_mark", {}).get("sources") or [])} == {
        "kalshi",
        "polymarket",
    }
    assert card["current_odds"]["bookmaker_count"] == 1
    assert card["bookmaker_odds"][0]["bookmaker"] == "draftkings"
    assert card["current_odds"]["home_probability"] is not None
    assert card["current_odds"]["home_probability"] == pytest.approx(
        page_payload["current_odds"]["home_probability"], abs=1e-4
    )
    assert card["current_odds"]["away_probability"] == pytest.approx(
        page_payload["current_odds"]["away_probability"], abs=1e-4
    )


# ── Cause 2: freshest snapshot per bookmaker across survivor + same-orient twin ─


@pytest.mark.asyncio
async def test_list_picks_freshest_twin_bookmaker_snapshots_matching_page():
    """Models #13479 #15315470 / #15315471: twin holds newer bookmaker lines."""
    canonical = _event(
        15315470,
        sport=SOCCER_LEAGUE,
        home="Bari",
        away="Mantova",
        espn_id="740001",
        status="scheduled",
        sources={"polymarket": {"value": 0.43, "updated_at": NOW.isoformat()}},
    )
    tagged_twin = _event(
        15352302,
        sport=SOCCER_LEAGUE,
        home="Bari",
        away="Mantova",
        status="scheduled",
        tags=[duplicate_tag(canonical.id)],
    )

    stale_ts = NOW - timedelta(days=30)
    fresh_ts = NOW - timedelta(minutes=1)
    snapshots = [
        # Canonical still holds a month-old snapshot for DraftKings.
        _snap(10, canonical.id, "draftkings", 0.72, 0.14, captured_at=stale_ts),
        # Absorbed twin carries the live pre-kickoff board for DraftKings + BetMGM.
        _snap(11, tagged_twin.id, "draftkings", 0.44, 0.28, captured_at=fresh_ts),
        _snap(12, tagged_twin.id, "betmgm", 0.42, 0.29, captured_at=fresh_ts),
    ]

    db = _make_route_db(
        sports=[SOCCER_LEAGUE, SOCCER_OTHER],
        page_events=[canonical],
        other_events=[],
        tagged_twins=[tagged_twin],
        snapshots=snapshots,
    )

    list_payload = await _call_list(db, sport_key="soccer_italy_serie_b")
    page_payload = await _call_page(db, canonical.id)

    card = list_payload["events"][0]
    assert card["current_odds"]["bookmaker_count"] == 2
    assert {b["bookmaker"] for b in card["bookmaker_odds"]} == {"draftkings", "betmgm"}
    dk = next(b for b in card["bookmaker_odds"] if b["bookmaker"] == "draftkings")
    assert dk["home_probability"] == pytest.approx(0.44, abs=1e-4)
    assert card["current_odds"]["home_probability"] == pytest.approx(
        page_payload["current_odds"]["home_probability"], abs=1e-4
    )
    assert card["current_odds"]["away_probability"] == pytest.approx(
        page_payload["current_odds"]["away_probability"], abs=1e-4
    )


# ── Condition 2: reversed-twin odds_snapshots strictly excluded on list & page ──


@pytest.mark.asyncio
async def test_reversed_twin_fresher_odds_snapshots_excluded_on_list_and_page():
    """A corner-flipped twin's fresher unflipped sportsbook rows are NEVER blended."""
    canonical = _event(
        15390001,
        sport=BASKET_LEAGUE,
        home="Real Madrid",
        away="Olympiacos",
        espn_id="750001",
        status="scheduled",
        sources={},
    )
    # Stored twin with SWAPPED home/away (`Olympiacos` home, `Real Madrid` away)
    # tagged `duplicate_of` — orientation gate excludes its odds_snapshots.
    reversed_tagged = _event(
        15390002,
        sport=BASKET_LEAGUE,
        home="Olympiacos",
        away="Real Madrid",
        status="scheduled",
        tags=[duplicate_tag(canonical.id)],
    )

    canonical_snap = _snap(
        201,
        canonical.id,
        "draftkings",
        0.64,
        0.36,
        captured_at=NOW - timedelta(minutes=15),
    )
    # Reversed twin has fresher snapshots, but its `home_win_probability=0.80`
    # means Olympiacos (canonical AWAY), NOT Real Madrid!
    reversed_dk_fresher = _snap(
        202,
        reversed_tagged.id,
        "draftkings",
        0.80,
        0.20,
        captured_at=NOW - timedelta(minutes=1),
    )
    reversed_extra_book = _snap(
        203,
        reversed_tagged.id,
        "betmgm",
        0.82,
        0.18,
        captured_at=NOW - timedelta(minutes=1),
    )

    db = _make_route_db(
        sports=[BASKET_LEAGUE, BASKET_OTHER],
        page_events=[canonical],
        other_events=[],
        tagged_twins=[reversed_tagged],
        snapshots=[canonical_snap, reversed_dk_fresher, reversed_extra_book],
    )

    list_payload = await _call_list(db, sport_key="basketball_euroleague")
    assert not db.sports_like_queries
    page_payload = await _call_page(db, canonical.id)

    card = list_payload["events"][0]
    assert card["current_odds"]["bookmaker_count"] == 1
    assert len(card["bookmaker_odds"]) == 1
    assert card["bookmaker_odds"][0]["bookmaker"] == "draftkings"
    assert card["bookmaker_odds"][0]["home_probability"] == pytest.approx(0.64, abs=1e-4)
    assert page_payload["current_odds"]["bookmaker_count"] == 1
    assert len(page_payload["bookmaker_odds"]) == 1
    assert page_payload["bookmaker_odds"][0]["home_probability"] == pytest.approx(0.64, abs=1e-4)


@pytest.mark.asyncio
async def test_runtime_flipped_loser_excluded_from_list_odds_query():
    """In-memory runtime fold with flipped_loser_ids keeps twin out of owner_by_event_id."""
    canonical = _event(
        15391001,
        sport=BASKET_LEAGUE,
        home="Panathinaikos",
        away="Fenerbahce",
        espn_id="760001",
        status="scheduled",
        sources={},
    )
    flipped_runtime = _event(
        15391002,
        sport=BASKET_LEAGUE,
        home="Fenerbahce",
        away="Panathinaikos",
        status="scheduled",
    )
    canonical_snap = _snap(301, canonical.id, "fanduel", 0.58, 0.42, captured_at=NOW - timedelta(minutes=10))
    flipped_snap = _snap(302, flipped_runtime.id, "fanduel", 0.90, 0.10, captured_at=NOW)

    fake_fold = SimpleNamespace(
        events=[canonical],
        dropped_ids=[flipped_runtime.id],
        survivor_of={flipped_runtime.id: canonical.id},
        merged_sources={},
        flipped_loser_ids={flipped_runtime.id},
        folded_count=1,
    )

    db = _make_route_db(
        sports=[BASKET_LEAGUE],
        page_events=[canonical],
        other_events=[],
        snapshots=[canonical_snap, flipped_snap],
    )
    with patch(
        "app.routes.events.fold_list_with_catchall_twins",
        new=AsyncMock(return_value=fake_fold),
    ):
        list_payload = await _call_list(db, sport_key="basketball_euroleague")

    card = list_payload["events"][0]
    assert card["current_odds"]["bookmaker_count"] == 1
    assert len(card["bookmaker_odds"]) == 1
    assert card["bookmaker_odds"][0]["home_probability"] == pytest.approx(0.58, abs=1e-4)
    # The flipped twin's ID must never be sent to latest_odds_per_bookmaker_query.
    assert all(flipped_runtime.id not in batch for batch in db.recorded_odds_event_ids)


# ── Shared snapshot picker + catch-all fold zero-extra-query controls ─────────


def test_group_latest_snapshots_by_event_picks_freshest_and_handles_missing_attrs():
    """Shared picker prefers newest captured_at, breaks ties to canonical, ignores unowned."""
    from app.utils.proven_duplicates import (
        group_latest_snapshots_by_event,
        latest_snapshot_for_each_bookmaker,
    )

    t0 = NOW - timedelta(minutes=20)
    t1 = NOW - timedelta(minutes=5)

    # Twin holds fresher DraftKings; canonical & twin tie on FanDuel (canonical wins).
    s_can_dk = SimpleNamespace(event_id=10, bookmaker="draftkings", captured_at=t0, home_win_probability=0.60)
    s_twin_dk = SimpleNamespace(event_id=20, bookmaker="draftkings", captured_at=t1, home_win_probability=0.52)
    s_twin_fd = _snap(500, 20, "fanduel", 0.49, 0.51, captured_at=t1)
    s_can_fd = _snap(100, 10, "fanduel", 0.51, 0.49, captured_at=t1)
    s_flipped_ignored = _snap(999, 30, "betmgm", 0.99, 0.01, captured_at=t1)
    s_missing_bk = SimpleNamespace(event_id=10, bookmaker=None, captured_at=t1)

    owner_map = {10: 10, 20: 10}
    grouped = group_latest_snapshots_by_event(
        [s_can_dk, s_twin_dk, s_twin_fd, s_can_fd, s_flipped_ignored, s_missing_bk],
        owner_map,
    )
    direct = latest_snapshot_for_each_bookmaker(
        [s_can_dk, s_twin_dk, s_twin_fd, s_can_fd],
        10,
    )

    assert [s.bookmaker for s in grouped[10]] == ["draftkings", "fanduel"]
    assert grouped[10][0] is s_twin_dk
    assert grouped[10][1] is s_can_fd
    assert grouped[10] == direct


@pytest.mark.asyncio
async def test_fold_list_with_catchall_twins_skips_extra_queries_for_unscoped_or_other():
    """Unscoped lists (`sport=None`) and `*_other` catch-all lists emit zero DB queries."""
    from app.utils.serve_fold_absorbed import fold_list_with_catchall_twins

    ev = _event(1, sport=SOCCER_OTHER, sources={"kalshi": {"home_prob": 0.5}})
    db = AsyncMock()

    res_none = await fold_list_with_catchall_twins(db, [ev], None)
    res_other = await fold_list_with_catchall_twins(db, [ev], "soccer_other")

    assert db.execute.await_count == 0
    assert [e.id for e in res_none.events] == [1]
    assert [e.id for e in res_other.events] == [1]
