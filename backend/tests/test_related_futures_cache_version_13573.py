"""#13573 Part A: keep `/related-futures` copies across unrelated deploys and pin
`RELATED_FUTURES_CACHE_VERSION` to the deterministic built payload.

Why this exists:
- Before this change, `related_futures_cache` and `_related_futures_cache` stamped
  `current_build_id()` (deploy git SHA), invalidating every event page's
  Season Futures copy ~15-20 times/day on unrelated ships (`4.3-14.4 s` cold rebuilds).
- Now `/related-futures` stamps `RELATED_FUTURES_CACHE_VERSION` (`rf-v1`), while
  `/game-markets` keeps its deploy stamp and all TTLs/ceilings remain unchanged.
- `test_season_futures_payload_fingerprint_matches_cache_version` builds real
  `live` + `completed` payloads (including a withheld Kalshi leg removed by
  `_related_futures_withheld_ids`) from a frozen deterministic fixture and fails
  with `"bump the version"` if output changes without bumping `RELATED_FUTURES_CACHE_VERSION`.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.encoders import jsonable_encoder

from app.routes import events as events_route
from app.utils import db_session_identity
from app.utils import futures_market_snapshot as fms
from app.utils import game_markets_cache as gmc
from app.utils import market_staleness
from app.utils import related_futures as related_futures_utils
from app.utils import related_futures_cache as rfc

FIXED_NOW = datetime(2026, 11, 26, 12, 0, 0, tzinfo=timezone.utc)


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return FIXED_NOW.replace(tzinfo=None)
        return FIXED_NOW.astimezone(tz)


class _SimpleResult:
    def __init__(self, *, scalar=None, rows=None, first=None, scalar_rows=None):
        self._scalar = scalar
        self._rows = list(rows or [])
        self._first = first
        self._scalar_rows = list(self._rows if scalar_rows is None else scalar_rows)

    def scalar_one_or_none(self):
        return self._scalar

    def scalar(self):
        return self._scalar

    def all(self):
        return self._rows

    def fetchall(self):
        return self._rows

    def first(self):
        return self._first

    def scalars(self):
        res = MagicMock()
        res.all.return_value = self._scalar_rows
        res.first.return_value = self._scalar_rows[0] if self._scalar_rows else None
        res.unique.return_value.all.return_value = self._scalar_rows
        return res


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    def get(self, k):
        return self.store.get(k)

    def setex(self, k, ttl, v):
        self.ttls[k] = ttl
        self.store[k] = v.encode() if isinstance(v, str) else v

    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.store:
            return None
        self.store[k] = v.encode() if isinstance(v, str) else v
        if ex is not None:
            self.ttls[k] = ex
        return True

    def delete(self, k):
        self.ttls.pop(k, None)
        return int(self.store.pop(k, None) is not None)


@pytest.fixture(autouse=True)
def _clean_l1():
    events_route._related_futures_cache.clear()
    events_route._game_markets_cache.clear()
    yield
    events_route._related_futures_cache.clear()
    events_route._game_markets_cache.clear()


def _freeze_clocks(monkeypatch) -> None:
    for mod in (events_route, fms, market_staleness, related_futures_utils):
        monkeypatch.setattr(mod, "datetime", _FrozenDateTime)


def _fixture_event(*, event_id: int, status: str) -> SimpleNamespace:
    completed_at = FIXED_NOW - timedelta(hours=2) if status == "completed" else None
    return SimpleNamespace(
        id=event_id,
        external_id=f"ext-{event_id}",
        home_team_name="Boston Celtics",
        away_team_name="Philadelphia 76ers",
        status=status,
        sport_key="basketball_nba",
        sport_id=1,
        sport=SimpleNamespace(id=1, key="basketball_nba", name="Basketball"),
        commence_time=FIXED_NOW - timedelta(hours=3 if status == "completed" else 1),
        completed_at=completed_at,
        home_score=112 if status == "completed" else 88,
        away_score=104 if status == "completed" else 82,
        win_probability_sources={"betting": {"home_probability": 0.65}},
        current_home_probability=0.65,
        current_away_probability=0.35,
        espn_game_id=None,
        espn_id=None,
        espn_data=None,
        espn_win_prob_home=None,
        game_clock="04:12" if status == "live" else None,
        period="Q3" if status == "live" else None,
        broadcast_info=None,
        event_tags=[],
        pulse_score=None,
        pulse_label=None,
        excite_index=None,
        raw_ei=None,
        home_team_id=10,
        away_team_id=20,
        home_team=None,
        away_team=None,
        llm_gender=None,
        llm_level=None,
        llm_league=None,
        llm_importance=None,
        box_score_data=None,
    )


def _fixture_market(
    *,
    market_id: int,
    name: str,
    source: str,
    bookmaker_count: int = 1,
    metadata: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=market_id,
        name=name,
        source=source,
        status="open",
        category="championship",
        market_tier=1,
        event_id=None,
        external_id=f"{source}-{market_id}",
        commence_time=None,
        resolution_date=FIXED_NOW + timedelta(days=120),
        updated_at=FIXED_NOW - timedelta(minutes=15),
        bookmaker_count=bookmaker_count,
        market_type=None,
        mutually_exclusive=True,
        group_id=None,
        llm_sport_category="basketball",
        sport_id=1,
        market_metadata=metadata,
        outcomes=[],
    )


def _fixture_outcome(
    *,
    outcome_id: int,
    market: SimpleNamespace,
    name: str,
    probability: float,
    change_24h: float,
    yes_bid: float | None,
    yes_ask: float | None,
    resolution_source: str | None,
) -> SimpleNamespace:
    o = SimpleNamespace(
        id=outcome_id,
        market_id=market.id,
        market=market,
        name=name,
        external_id=f"out-{outcome_id}",
        current_probability=probability,
        current_american_odds=None,
        probability_change_24h=change_24h,
        opening_probability=probability - change_24h,
        current_yes_bid=yes_bid,
        current_yes_ask=yes_ask,
        resolution_source=resolution_source,
        is_winner=None,
        volume=None,
        rank=None,
        team_id=None,
        last_updated=FIXED_NOW - timedelta(minutes=15),
        updated_at=FIXED_NOW - timedelta(minutes=15),
    )
    market.outcomes.append(o)
    return o


def _make_deterministic_session(event: SimpleNamespace):
    session = AsyncMock()

    kalshi_champ = _fixture_market(
        market_id=101,
        name="2026 NBA Champion",
        source="kalshi",
        bookmaker_count=1,
    )
    pm_champ = _fixture_market(
        market_id=102,
        name="NBA Champion",
        source="polymarket",
        bookmaker_count=4,
        metadata={
            fms.DATED_BASIS_METADATA_KEY: {
                "202": [0.42, (FIXED_NOW - timedelta(hours=18)).isoformat()],
            }
        },
    )
    away_champ = _fixture_market(
        market_id=103,
        name="Eastern Conference Champion",
        source="kalshi",
        bookmaker_count=2,
    )
    withheld_mkt = _fixture_market(
        market_id=104,
        name="Boston Celtics NBA Playoff Seed",
        source="kalshi",
        bookmaker_count=1,
    )

    o_home_kalshi = _fixture_outcome(
        outcome_id=201,
        market=kalshi_champ,
        name="Boston Celtics",
        probability=0.42,
        change_24h=0.03,
        yes_bid=0.41,
        yes_ask=0.43,
        resolution_source=None,
    )
    o_home_pm = _fixture_outcome(
        outcome_id=202,
        market=pm_champ,
        name="Boston Celtics",
        probability=0.44,
        change_24h=0.02,
        yes_bid=None,
        yes_ask=None,
        resolution_source=None,
    )
    o_away_kalshi = _fixture_outcome(
        outcome_id=203,
        market=away_champ,
        name="Philadelphia 76ers",
        probability=0.18,
        change_24h=-0.01,
        yes_bid=0.17,
        yes_ask=0.19,
        resolution_source=None,
    )
    # Empty Kalshi book (0.500 midpoint on 2c/97c book, #6676/#9008) -> withheld by `_related_futures_withheld_ids`.
    o_withheld = _fixture_outcome(
        outcome_id=204,
        market=withheld_mkt,
        name="Boston Celtics",
        probability=0.50,
        change_24h=0.05,
        yes_bid=0.02,
        yes_ask=0.97,
        resolution_source=None,
    )

    outcomes = [o_home_kalshi, o_home_pm, o_away_kalshi, o_withheld]
    boards = [kalshi_champ, pm_champ, away_champ, withheld_mkt]
    bookmaker_rows = [
        SimpleNamespace(outcome_id=201, bm_count=1),
        SimpleNamespace(outcome_id=202, bm_count=4),
        SimpleNamespace(outcome_id=203, bm_count=2),
        SimpleNamespace(outcome_id=204, bm_count=1),
    ]
    team_rows = [
        SimpleNamespace(
            id=10,
            sport_id=1,
            name="Boston Celtics",
            abbreviation="BOS",
            location="Boston",
            alternate_names=[],
            logo_url_small=None,
            logo_url=None,
        ),
        SimpleNamespace(
            id=20,
            sport_id=1,
            name="Philadelphia 76ers",
            abbreviation="PHI",
            location="Philadelphia",
            alternate_names=["Sixers"],
            logo_url_small=None,
            logo_url=None,
        ),
    ]

    async def mock_execute(stmt, *args, **kwargs):
        stmt_str = str(stmt).lower().lstrip() if hasattr(stmt, "__str__") else ""

        if "from events" in stmt_str:
            return _SimpleResult(scalar=event)

        if "select sports.id" in stmt_str:
            return _SimpleResult(rows=[SimpleNamespace(id=1)])

        if "from teams" in stmt_str and "join sports" in stmt_str:
            return _SimpleResult(rows=team_rows)

        if stmt_str.startswith("select futures_markets.id, futures_markets.market_tier"):
            return _SimpleResult(
                rows=[
                    SimpleNamespace(id=101, market_tier=1),
                    SimpleNamespace(id=102, market_tier=1),
                    SimpleNamespace(id=103, market_tier=1),
                    SimpleNamespace(id=104, market_tier=1),
                ]
            )

        if "count(" in stmt_str and "from futures_outcomes" in stmt_str:
            return _SimpleResult(rows=[])

        if stmt_str.startswith("select futures_outcomes."):
            return _SimpleResult(scalar_rows=outcomes)

        if "from futures_odds_snapshots" in stmt_str:
            return _SimpleResult(rows=bookmaker_rows)

        if stmt_str.startswith("select futures_markets."):
            if "where futures_markets.id in" in stmt_str:
                return _SimpleResult(scalar_rows=boards)
            return _SimpleResult(rows=[])

        return _SimpleResult()

    session.execute = AsyncMock(side_effect=mock_execute)
    return session


async def _build_fixture_pair(monkeypatch) -> dict[str, dict]:
    _freeze_clocks(monkeypatch)
    out: dict[str, dict] = {}
    with (
        patch(
            "app.services.league_context.enrich_event_with_context",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.utils.season_market_discovery.read",
            return_value=None,
        ),
        patch(
            "app.utils.season_market_discovery.claim_or_await",
            new_callable=AsyncMock,
            return_value=(None, None),
        ),
        patch("app.utils.season_market_discovery.write"),
        patch("app.utils.season_market_discovery.release_build"),
    ):
        for event_id, status in ((4201, "live"), (4202, "completed")):
            ev = _fixture_event(event_id=event_id, status=status)
            sess = _make_deterministic_session(ev)
            resp, _raw_status, _mids, _cacheable = await events_route._build_related_futures(
                event_id, sess
            )
            events_route._strip_related_futures_american_odds(resp)
            out[status] = jsonable_encoder(resp)
    return out


def _canonical_for_fingerprint(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "all_sources" and isinstance(v, list):
                out[k] = sorted(v)
            else:
                out[k] = _canonical_for_fingerprint(v)
        return out
    if isinstance(obj, list):
        return [_canonical_for_fingerprint(v) for v in obj]
    return obj


def _fingerprint(payload_pair: dict[str, dict]) -> str:
    canonical = json.dumps(
        _canonical_for_fingerprint(payload_pair),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# Map each `RELATED_FUTURES_CACHE_VERSION` to the exact canonical SHA-256 of the
# fixed live + completed + withheld fixture pair. Any change to `_build_related_futures`
# output without bumping `RELATED_FUTURES_CACHE_VERSION` fails the test below.
PINNED_VERSION_FINGERPRINTS: dict[int, str] = {
    1: "ab37043a6f5824aae734d38201a5f782bf03e224d70a8fb10ba9c1edbb1881f8",
}


def _assert_version_matches_fingerprint(
    version: int,
    payload_pair: dict[str, dict],
    pinned_map: dict[int, str] = PINNED_VERSION_FINGERPRINTS,
) -> None:
    expected = pinned_map.get(version)
    actual = _fingerprint(payload_pair)
    assert expected is not None, (
        f"RELATED_FUTURES_CACHE_VERSION={version} has no pinned fingerprint — "
        "bump the version and record its new fixture fingerprint."
    )
    assert actual == expected, (
        "Season Futures (/related-futures) output changed while "
        f"RELATED_FUTURES_CACHE_VERSION stayed at {version} "
        f"(expected {expected}, got {actual}) — bump the version."
    )


@pytest.mark.asyncio
async def test_season_futures_payload_fingerprint_matches_cache_version(monkeypatch):
    pair = await _build_fixture_pair(monkeypatch)
    # Fixture non-vacuity checks: live game, completed game, and withheld Kalshi row (204).
    assert pair["live"]["event_status"] == "live"
    assert pair["completed"]["event_status"] == "completed"
    live_outcome_ids = {
        r["outcome_id"]
        for r in pair["live"]["home_team_futures"] + pair["live"]["away_team_futures"]
    }
    assert 201 in live_outcome_ids or 202 in live_outcome_ids
    assert 203 in live_outcome_ids
    assert 204 not in live_outcome_ids, "withheld Kalshi outcome 204 must be filtered out"

    _assert_version_matches_fingerprint(rfc.RELATED_FUTURES_CACHE_VERSION, pair)


@pytest.mark.asyncio
async def test_fingerprint_guard_fails_with_bump_message_when_output_changes_without_version_bump(
    monkeypatch,
):
    pair = await _build_fixture_pair(monkeypatch)
    real_fp = _fingerprint(pair)
    pinned = {rfc.RELATED_FUTURES_CACHE_VERSION: real_fp}

    drifted = json.loads(json.dumps(pair))
    drifted["live"]["home_team_futures"][0]["probability"] = 0.99

    with pytest.raises(AssertionError, match="bump the version"):
        _assert_version_matches_fingerprint(
            rfc.RELATED_FUTURES_CACHE_VERSION, drifted, pinned
        )

    # Also verify that if withholding stops filtering row 204, the built output moves and fails.
    with patch.object(
        events_route, "_related_futures_withheld_ids", new_callable=AsyncMock, return_value=set()
    ):
        unwithheld_pair = await _build_fixture_pair(monkeypatch)
    with pytest.raises(AssertionError, match="bump the version"):
        _assert_version_matches_fingerprint(
            rfc.RELATED_FUTURES_CACHE_VERSION, unwithheld_pair, pinned
        )


def test_related_futures_survives_unrelated_deploy_while_game_markets_invalidates(monkeypatch):
    rc = _FakeRedis()
    monkeypatch.setattr(gmc, "current_build_id", lambda: "v6636")
    monkeypatch.setattr(db_session_identity, "current_build_id", lambda: "v6636")

    rf_body = rfc.stamp({"event_id": 7, "away_team_futures": []}, source_status="live")
    gm_body = gmc.stamp({"event_id": 7, "spreads": []}, source_status="completed")
    rfc.write(7, rf_body, rc=rc)
    gmc.write(7, gm_body, rc=rc)
    events_route._write_related_futures_memo(7, "live", rf_body)

    # Simulate an unrelated deploy rolling from v6636 -> v6637.
    monkeypatch.setattr(gmc, "current_build_id", lambda: "v6637")
    monkeypatch.setattr(db_session_identity, "current_build_id", lambda: "v6637")

    assert events_route._read_related_futures_memo(7) is rf_body
    rf_out, rf_state = rfc.read(7, rc=rc)
    assert rf_state == "live" and rf_out is not None
    # Game-markets copy now uses `gm-v1` too and survives the unrelated deploy (#13573).
    gm_out, gm_state = gmc.read(7, rc=rc)
    assert gm_state == "live" and gm_out is not None

    # Stale mirror for /related-futures also survives an unrelated deploy within ceiling.
    rc.delete(rfc.keys_for(7).primary)
    rf_stale_out, rf_stale_state = rfc.read(7, rc=rc)
    assert rf_stale_state == "stale_ok" and rf_stale_out is not None


def test_old_deploy_stamped_copies_are_refused_once_and_version_bump_invalidates(monkeypatch):
    rc = _FakeRedis()
    # Pre-rollout slot carrying an old deploy SHA stamp (`"v6636"`).
    old_style = gmc.stamp({"event_id": 9, "away_team_futures": []}, source_status="completed")
    old_style[rfc.ENVELOPE_FIELD][rfc.BUILD_FIELD] = "v6636"
    rfc.write(9, old_style, rc=rc)

    body, state = rfc.read(9, rc=rc)
    assert state == "stale_build" and body is None
    rc.delete(rfc.keys_for(9).primary)
    body_mirror, state_mirror = rfc.read(9, rc=rc)
    assert state_mirror == "stale_build" and body_mirror is None

    # Versioned copy in L1 & L2 invalidates immediately when RELATED_FUTURES_CACHE_VERSION bumps.
    v1_body = rfc.stamp({"event_id": 11, "away_team_futures": []}, source_status="completed")
    rfc.write(11, v1_body, rc=rc)
    events_route._write_related_futures_memo(11, "completed", v1_body)

    monkeypatch.setattr(rfc, "RELATED_FUTURES_CACHE_VERSION", rfc.RELATED_FUTURES_CACHE_VERSION + 1)
    assert events_route._read_related_futures_memo(11) is None
    assert rfc.read(11, rc=rc) == (None, "stale_build")


def test_time_limits_are_unchanged():
    assert rfc.FRESH_TTL_LIVE == 60
    assert rfc.FRESH_TTL_FINAL == 3600
    assert rfc.stale_serve_ceiling_seconds("live") == 150
    assert rfc.stale_serve_ceiling_seconds("completed") == 18000
