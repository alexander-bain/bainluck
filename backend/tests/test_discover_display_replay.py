"""#10290 — capture one Discover build at the display-chain seam and replay it
offline through the same chain.

Every capture here is taken from the REAL ``get_feed`` through the real ASGI
app: the upstream stages run against a mocked session, and the scored pool is
substituted at ``_suppress_zero_probability_cards`` — the last call before the
seam — so everything from the seam on (the shared chain, collections, the
edition pin, venue settlement, publication, the envelope) is production code.
These are SYNTHETIC captures (``origin='synthetic'``): they prove the
machinery, never a claim about the production feed.

The replay is never handed the oracle. ``verify_baseline`` compares the
replayed deck and page against ``capture['expected']``; the tests that mutate
the capture prove that comparison can fail where it must (outside the top 20,
in a nested bundle member, on a single probability).
"""

from __future__ import annotations

import copy
import json
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from app.utils import discover_display_replay as ddr
from app.utils import request_cache as _rc

BACKEND = Path(__file__).resolve().parents[1]
_POOL_FUTURES = 320
_AWARD_ID = 99001
_SIBLING_IDS = (99002, 99003)
_ASKABLE_IDS = (7101, 7102, 7103)
_FINAL_ID = 7201


# --------------------------------------------------------------------------- #
# The mixed pool
# --------------------------------------------------------------------------- #


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _event(i: int, score: float, start: datetime) -> dict:
    return {
        "type": "event",
        "score": score,
        "_rank_score": score,
        "_sort_time": start.timestamp(),
        "reason": "Game",
        "headline": None,
        "data": {
            "id": i,
            "status": "scheduled",
            "sport": "americanfootball_nfl",
            "sport_name": "NFL",
            "commence_time": _iso(start),
            "home_team": f"Home {i}",
            "away_team": f"Away {i}",
            "home_score": None,
            "away_score": None,
            "home_team_data": {"logo": "h"},
            "away_team_data": {"logo": "a"},
            "home_win_probability": 0.55,
        },
    }


def _futures(i: int, score: float, category: str, prob: float, **extra) -> dict:
    item = {
        "type": "futures",
        "score": score,
        "_rank_score": score,
        "_sort_time": 0,
        "reason": f"why {i}",
        "headline": f"f{i}",
        "data": {
            "id": i,
            "name": f"Will market {i} happen?",
            "llm_sport_category": category,
            "sport": category,
            "outcomes": [
                {"name": "Yes", "probability": prob},
                {"name": "No", "probability": round(1 - prob, 4)},
            ],
        },
    }
    item.update(extra)
    return item


def _mixed_pool(now: datetime) -> list[dict]:
    """event, futures, tournament, concept and an award cluster that the chain
    folds into a bundle — 300+ cards, with three-way score ties throughout."""
    pool: list[dict] = []
    # NFL games scored >= 80 are a Discover demotion exception, so the chain
    # keeps them instead of filing them under Sports.
    for n in range(10):
        pool.append(_event(7001 + n, 90 - n, now + timedelta(hours=2 + n)))
    for n, ident in enumerate(_ASKABLE_IDS):
        # Started hours ago with no result — the venue-settlement gate's
        # "started without a result" branch admits these.
        pool.append(_event(ident, 86 - n, now - timedelta(hours=6 + n)))
    # A marquee final, kept only while it is inside the client's finished-card
    # window measured from the BUILD's clock — the card that makes the deck
    # depend on which clock the replay reads.
    final = _event(_FINAL_ID, 60, now - timedelta(hours=4))
    final["data"].update(
        status="completed", home_score=27, away_score=24, event_tags=["tier:1"]
    )
    pool.append(final)
    categories = ("politics", "economics", "tech", "geopolitics", "science", "culture")
    for n in range(_POOL_FUTURES):
        extra = {}
        if n % 50 == 0:
            # Private, non-JSON values the chain may read: the capture must
            # restore their TYPES, not their str().
            extra = {
                "_probe_seen_at": now - timedelta(minutes=n),
                "_probe_volume": Decimal("1234.50"),
                "_probe_tokens": {"alpha", f"t{n}"},
                "_probe_pair": (n, "x"),
            }
        pool.append(
            _futures(
                90001 + n,
                # Three cards share every score: the canonical rank key, not
                # input order luck, has to decide them.
                round(80 - (n // 3) * 0.1, 2),
                categories[n % len(categories)],
                round(0.2 + (n % 60) / 100, 2),
                **extra,
            )
        )
    siblings = [
        _futures(sid, 40.0, "entertainment", 0.3, _quality_story_key="emmys")
        for sid in _SIBLING_IDS
    ]
    for s in siblings:
        s["data"]["group_id"] = "polymarket:emmys-2026"
    award = _futures(_AWARD_ID, 79.95, "entertainment", 0.41, _grouped_members=siblings)
    award["data"]["group_id"] = "polymarket:emmys-2026"
    award["data"]["name"] = "Will Severance win Best Drama Series at the 2026 Emmys?"
    for s, name in zip(siblings, ("The Pitt", "The Bear")):
        s["data"]["name"] = f"Will {name} win Best Drama Series at the 2026 Emmys?"
    pool.append(award)
    pool.append(
        {
            "type": "tournament",
            "score": 75.0,
            "_rank_score": 75.0,
            "_sort_time": 0,
            "reason": "Tournament",
            "headline": None,
            "data": {"key": "golf-tour-championship-2026", "name": "Tour Championship"},
        }
    )
    pool.append(
        {
            "type": "concept",
            "score": 74.0,
            "_rank_score": 74.0,
            "_sort_time": 0,
            "reason": "Concept",
            "headline": None,
            "data": {"key": "ryder-cup-2026", "name": "Ryder Cup"},
        }
    )
    return pool


# --------------------------------------------------------------------------- #
# The route harness
# --------------------------------------------------------------------------- #


def _empty_result():
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalars.return_value.unique.return_value.all.return_value = []
    result.scalars.return_value.first.return_value = None
    result.scalar_one_or_none.return_value = None
    result.scalar.return_value = None
    result.fetchall.return_value = []
    result.all.return_value = []
    result.first.return_value = None
    return result


class _Harness:
    def __init__(self, monkeypatch):
        from app.main import app
        from app.routes import feed as feed_module

        self.app = app
        self.feed = feed_module
        self.monkeypatch = monkeypatch
        self.now = datetime.now(timezone.utc)
        self.pool = _mixed_pool(self.now)
        self.venue_rows: list = []
        self.session = AsyncMock()
        self.session.execute.side_effect = self._execute

        monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
        monkeypatch.setenv("FEED_SHARED_BUILD_CROSS_WORKER", "0")

        def _inject(_items):
            return copy.deepcopy(self.pool), 0

        # The pool lands at the last call before the seam.
        monkeypatch.setattr(feed_module, "_suppress_zero_probability_cards", _inject)
        for name in ("_score_golf_tournaments", "_score_event_concepts"):
            monkeypatch.setattr(feed_module, name, AsyncMock(return_value=[]))
        monkeypatch.setattr(feed_module, "_score_events", AsyncMock(return_value=[]))

        async def _db():
            yield self.session

        async def _user():
            return None

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_db_rw] = _db
        app.dependency_overrides[get_optional_user] = _user
        self.set_redis(None)

    async def _execute(self, statement, *args, **kwargs):
        text = str(statement)
        if text.startswith(
            "SELECT events.id, events.status, events.commence_time, events.home_team_name"
        ):
            result = _empty_result()
            result.all.return_value = list(self.venue_rows)
            return result
        return _empty_result()

    def set_redis(self, fake) -> None:
        async def _client():
            return fake

        self.monkeypatch.setattr(_rc, "get_shared_async_redis", _client)

    def reset_process_caches(self) -> None:
        from app.utils.principal_independent_cache import clear_shared_builds

        _rc._reset_last_good_for_tests()
        _rc._reset_inflight_for_tests()
        clear_shared_builds()

    async def get(self, url: str, *, capture=None, headers=None):
        self.reset_process_caches()
        app = self.app

        async def wrapped(scope, receive, send):
            if scope.get("type") == "http" and capture is not None:
                scope = dict(scope)
                scope[ddr.DISCOVER_DISPLAY_CAPTURE_SCOPE_KEY] = capture
            await app(scope, receive, send)

        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(
                transport=ASGITransport(app=wrapped), base_url="http://test"
            ) as client:
                return await client.get(url, headers=headers or {})


@pytest.fixture
def harness(monkeypatch):
    h = _Harness(monkeypatch)
    yield h
    h.app.dependency_overrides.clear()
    h.reset_process_caches()


@pytest.fixture
def collection_card():
    path = BACKEND / "tests/fixtures/container_discovery_9653/search_by_games.json"
    card = json.loads(path.read_text())["response"]["collections"][0]
    card["matched_event_ids"] = [7001, 7002]
    return card


def _without_cache(body: dict) -> dict:
    return {k: v for k, v in body.items() if k != "cache"}


async def _capture(harness, url="/api/feed?limit=20", **kw) -> dict:
    capture = ddr.DiscoverDisplayCapture(origin="synthetic")
    response = await harness.get(url, capture=capture, **kw)
    assert response.status_code == 200, response.text
    artifact = capture.artifact()
    # A JSON round trip is the only form a capture is ever replayed from.
    return json.loads(json.dumps(artifact))


def _kinds(items) -> set[str]:
    return {item["type"] for item in items}


# --------------------------------------------------------------------------- #
# Capture is passive
# --------------------------------------------------------------------------- #


async def test_an_armed_capture_does_not_change_the_served_response(harness):
    plain = await harness.get("/api/feed?limit=20")
    capture = ddr.DiscoverDisplayCapture(origin="synthetic")
    armed = await harness.get("/api/feed?limit=20", capture=capture)

    assert plain.status_code == armed.status_code == 200
    # The capture actually recorded — otherwise the two responses are equal
    # because nothing ran (gotcha #53).
    assert capture.status == "complete", capture.refusal
    assert _without_cache(armed.json()) == _without_cache(plain.json())
    assert len(plain.json()["items"]) == 20


def test_the_runner_request_is_anonymous_and_armed():
    capture = ddr.DiscoverDisplayCapture(origin="local")
    request = ddr.capture_request(capture)
    assert ddr.display_capture_from_request(request) is capture
    assert list(request.headers.keys()) == []


async def test_an_http_request_cannot_arm_a_capture(harness):
    """The arm lives in the ASGI scope. A header or query naming the key is
    just text — the route never sees a recorder."""
    seen = []
    real = ddr.display_capture_from_request

    def spy(request):
        found = real(request)
        seen.append(found)
        return found

    harness.monkeypatch.setattr(harness.feed, "display_capture_from_request", spy)
    response = await harness.get(
        f"/api/feed?limit=20&{ddr.DISCOVER_DISPLAY_CAPTURE_SCOPE_KEY}=1",
        headers={ddr.DISCOVER_DISPLAY_CAPTURE_SCOPE_KEY: "1"},
    )
    assert response.status_code == 200
    assert seen == [None]


# --------------------------------------------------------------------------- #
# Capture → load → same chain → full parity
# --------------------------------------------------------------------------- #


async def test_a_capture_replays_to_pass_over_the_whole_deck(harness, tmp_path):
    artifact = await _capture(harness)
    pool = ddr.decode_value(artifact["scored_pool"]["items"])
    assert len(pool) > 300, "the pool must exceed the futures snapshot's 300 cap"
    assert _kinds(pool) == {"event", "futures", "tournament", "concept"}
    assert artifact["expected"]["total"] > 20, "parity must reach past the page"
    deck_kinds = {i.split(":")[0] for i in artifact["expected"]["full_deck_identities"]}
    assert "bundle" in deck_kinds, "the award cluster must be folded by the chain"
    assert {"event", "futures"} <= deck_kinds
    assert artifact["provenance"]["origin"] == "synthetic"

    path = tmp_path / "capture.json"
    ddr.write_capture(artifact, str(path))
    report = ddr.verify_baseline(str(path))
    assert report["verdict"] == ddr.PASS, report
    assert report["replayed_total"] == artifact["expected"]["total"]
    assert "upstream admission and scoring (the pool is taken as scored)" in (
        report["scope"]["not_replayed"]
    )
    assert report["chain_exit_matches"] is True

    # A file over the bound is refused before it is parsed.
    with pytest.raises(ddr.DisplayReplayError) as exc:
        ddr.load_capture(str(path), max_bytes=1000)
    assert exc.value.code == ddr.INVALID


async def test_the_replay_runs_the_shared_chain_not_a_copy(harness, monkeypatch):
    artifact = await _capture(harness)
    calls = []
    real = harness.feed.apply_discover_display_chain

    def spy(items, **kw):
        calls.append(len(items))
        return real(items, **kw)

    monkeypatch.setattr(harness.feed, "apply_discover_display_chain", spy)
    assert ddr.verify_baseline(artifact)["verdict"] == ddr.PASS
    assert calls == [artifact["scored_pool"]["count"]]


async def test_ties_are_decided_by_the_rank_key_not_by_input_order(harness):
    """Reversing the frozen pool's ORDER changes nothing the chain decides —
    its sort is total — so the replay still passes. The chain's own key is
    what breaks the three-way ties; the replay preserves it, invents none."""
    artifact = await _capture(harness)
    reversed_pool = ddr.decode_value(artifact["scored_pool"]["items"])[::-1]
    replay = ddr.replay_capture(artifact, arm=lambda _pool: reversed_pool)
    assert replay["deck_identities"] == artifact["expected"]["full_deck_identities"]


# --------------------------------------------------------------------------- #
# The comparison can fail where it must
# --------------------------------------------------------------------------- #


async def test_an_ordered_mismatch_after_the_top_20_fails(harness):
    artifact = await _capture(harness)
    ids = artifact["expected"]["full_deck_identities"]
    assert len(ids) > 27
    ids[25], ids[26] = ids[26], ids[25]
    report = ddr.verify_baseline(artifact)
    assert report["verdict"] == ddr.MISMATCH
    assert report["first_divergence"] == 25


async def test_a_changed_probability_off_the_page_fails(harness):
    artifact = await _capture(harness)
    target = artifact["expected"]["full_deck_identities"][40]
    assert target.startswith("futures:")
    for card in artifact["scored_pool"]["items"]:
        if f"futures:{card['data']['id']}" == target:
            card["data"]["outcomes"][0]["probability"] += 0.01
            break
    else:  # pragma: no cover
        pytest.fail("target card missing from the pool")
    report = ddr.verify_baseline(artifact)
    assert report["verdict"] == ddr.MISMATCH, report
    assert report["detail"].startswith("same identities, different public card content")


async def test_a_changed_nested_bundle_member_fails(harness):
    artifact = await _capture(harness)
    for card in artifact["scored_pool"]["items"]:
        if card["data"]["id"] == _AWARD_ID:
            card["_grouped_members"][0]["data"]["outcomes"][0]["probability"] = 0.31
            break
    report = ddr.verify_baseline(artifact)
    assert report["verdict"] == ddr.MISMATCH, report


async def test_the_replay_never_reads_the_oracle(harness):
    """Gutting the expected block cannot make the replay's output move."""
    artifact = await _capture(harness)
    first = ddr.replay_capture(ddr.load_capture(copy.deepcopy(artifact)))
    gutted = copy.deepcopy(artifact)
    gutted["expected"]["public_response"] = {"items": []}
    second = ddr.replay_capture(gutted)
    assert ddr.canonical(first["public_response"]) == ddr.canonical(
        second["public_response"]
    )


# --------------------------------------------------------------------------- #
# Isolation, clocks, offline
# --------------------------------------------------------------------------- #


async def test_each_arm_gets_its_own_copy_of_the_pool(harness):
    artifact = await _capture(harness)
    handed: list[list] = []

    def vandal(pool):
        handed.append(pool)
        for card in pool:
            card["score"] = 0
            card["_rank_score"] = 0
        return pool

    ddr.replay_capture(artifact, arm=vandal)
    baseline = ddr.replay_capture(artifact, arm=lambda pool: handed.append(pool) or pool)
    assert handed[0] is not handed[1]
    assert not {id(c) for c in handed[0]} & {id(c) for c in handed[1]}
    assert baseline["deck_identities"] == artifact["expected"]["full_deck_identities"]
    assert ddr.verify_baseline(artifact)["verdict"] == ddr.PASS


def _shifted_datetime(fake_now: datetime):
    class _Shifted(datetime):
        @classmethod
        def now(cls, tz=None):
            return fake_now if tz else fake_now.replace(tzinfo=None)

    return _Shifted


async def test_the_replay_reads_the_frozen_clock_not_the_wall(harness, monkeypatch):
    """Captured on a build clock three days back, replayed at two other wall
    clocks: still exact. The marquee final is inside its window only on the
    build's clock, so a replay that read the wall would drop it."""
    from app.utils import tonights_games

    build_now = datetime.now(timezone.utc) - timedelta(days=3)
    harness.pool = _mixed_pool(build_now)
    with monkeypatch.context() as m:
        m.setattr(harness.feed, "datetime", _shifted_datetime(build_now))
        artifact = await _capture(harness)
    assert artifact["clocks"]["scoring_now"] == build_now.isoformat()
    assert f"event:{_FINAL_ID}" in artifact["expected"]["full_deck_identities"]

    outputs = []
    for wall in (datetime.now(timezone.utc), build_now + timedelta(days=400)):
        with monkeypatch.context() as m:
            m.setattr(harness.feed, "datetime", _shifted_datetime(wall))
            m.setattr(tonights_games, "datetime", _shifted_datetime(wall))
            m.setattr(time, "time", lambda: wall.timestamp())
            report = ddr.verify_baseline(artifact)
            assert report["verdict"] == ddr.PASS, report
            outputs.append(
                ddr.canonical(ddr.replay_capture(artifact)["public_response"])
            )
    assert outputs[0] == outputs[1]


async def test_network_or_database_access_during_replay_is_refused(harness, monkeypatch):
    artifact = await _capture(harness)
    real = harness.feed.apply_discover_display_chain

    def hydrating(items, **kw):
        socket.create_connection(("api.bainluck.com", 443), timeout=1)
        return real(items, **kw)

    monkeypatch.setattr(harness.feed, "apply_discover_display_chain", hydrating)
    report = ddr.verify_baseline(artifact)
    assert report["verdict"] == ddr.OFFLINE_VIOLATION

    def querying(items, **kw):
        from sqlalchemy.orm import Session

        Session.execute(None, "SELECT 1")
        return real(items, **kw)

    monkeypatch.setattr(harness.feed, "apply_discover_display_chain", querying)
    assert ddr.verify_baseline(artifact)["verdict"] == ddr.OFFLINE_VIOLATION
    # And the guard is gone afterwards.
    assert socket.create_connection is not None
    with ddr.offline():
        pass
    from sqlalchemy.orm import Session

    assert Session.execute.__name__ == "execute"


# --------------------------------------------------------------------------- #
# Unsupported, missing, unknown, duplicate — refused, never "faithful"
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "url,headers,code",
    [
        ("/api/feed?limit=20&mode=sports", None, ddr.UNSUPPORTED),
        ("/api/feed?limit=20&sport=politics", None, ddr.UNSUPPORTED),
        ("/api/feed?limit=20", {"X-Session-Id": "s-10290"}, ddr.UNSUPPORTED),
        # my_teams_only without a user returns before the build.
        ("/api/feed?limit=20&my_teams_only=true", None, ddr.INCOMPLETE),
    ],
)
async def test_unsupported_requests_refuse_and_serve_normally(harness, url, headers, code):
    capture = ddr.DiscoverDisplayCapture(origin="synthetic")
    armed = await harness.get(url, capture=capture, headers=headers)
    plain = await harness.get(url, headers=headers)
    assert armed.status_code == plain.status_code == 200
    assert _without_cache(armed.json()) == _without_cache(plain.json())
    with pytest.raises(ddr.DisplayReplayError) as exc:
        capture.artifact()
    assert exc.value.code == code
    if "mode=sports" in url:
        assert "SPORTS FIRST CAPTURE UNSUPPORTED" in exc.value.detail


async def test_a_debug_build_refuses(harness, monkeypatch):
    monkeypatch.setattr(harness.feed, "_check_admin_auth", AsyncMock(return_value=True))
    capture = ddr.DiscoverDisplayCapture(origin="synthetic")
    response = await harness.get(
        "/api/feed?limit=20&debug=true&debug_ground_truth=false", capture=capture
    )
    assert response.status_code == 200
    with pytest.raises(ddr.DisplayReplayError) as exc:
        capture.artifact()
    assert exc.value.code == ddr.UNSUPPORTED


async def test_a_cached_response_is_never_a_capture(harness):
    from tests.integration.test_route_feed_collections_cache_10003 import _DictRedis

    fake = _DictRedis()
    harness.set_redis(fake)
    scheduled: list = []
    harness.monkeypatch.setattr(_rc, "schedule_background", scheduled.append)
    first = await harness.get("/api/feed?limit=20")
    assert first.headers["x-feed-cache"] == "miss"
    while scheduled:
        await scheduled.pop(0)
    capture = ddr.DiscoverDisplayCapture(origin="synthetic")
    second = await harness.get("/api/feed?limit=20", capture=capture)
    assert second.headers["x-feed-cache"] != "miss"
    with pytest.raises(ddr.DisplayReplayError) as exc:
        capture.artifact()
    assert exc.value.code == ddr.INCOMPLETE
    assert "cache" in exc.value.detail


@pytest.mark.parametrize(
    "corrupt,code",
    [
        (lambda pool: pool.append({"type": "mystery", "score": 1, "data": {"id": 1}}), ddr.UNSUPPORTED),
        (lambda pool: pool.append({"type": "bundle", "score": 1, "data": {"id": "b"}}), ddr.UNSUPPORTED),
        (lambda pool: pool[20]["data"].pop("id"), ddr.INVALID),
        (lambda pool: pool.append(copy.deepcopy(pool[30])), ddr.INVALID),
    ],
    ids=["unknown-kind", "bundle-in-pool", "missing-identity", "duplicate-identity"],
)
async def test_a_bad_pool_refuses_the_capture_and_leaves_the_feed_alone(
    harness, corrupt, code
):
    corrupt(harness.pool)
    plain = await harness.get("/api/feed?limit=20")
    capture = ddr.DiscoverDisplayCapture(origin="synthetic")
    armed = await harness.get("/api/feed?limit=20", capture=capture)
    assert _without_cache(armed.json()) == _without_cache(plain.json())
    with pytest.raises(ddr.DisplayReplayError) as exc:
        capture.artifact()
    assert exc.value.code == code


async def test_an_oversized_capture_is_refused_not_truncated(harness):
    capture = ddr.DiscoverDisplayCapture(origin="synthetic", max_bytes=10_000)
    response = await harness.get("/api/feed?limit=20", capture=capture)
    assert response.status_code == 200
    with pytest.raises(ddr.DisplayReplayError) as exc:
        capture.artifact()
    assert exc.value.code == ddr.INCOMPLETE
    assert "refused rather than truncated" in exc.value.detail


def test_an_abandoned_build_is_incomplete():
    capture = ddr.DiscoverDisplayCapture(origin="synthetic")
    capture.status = "recording"
    capture.abandon("input_age_ceiling")
    with pytest.raises(ddr.DisplayReplayError) as exc:
        capture.artifact()
    assert exc.value.code == ddr.INCOMPLETE
    assert "input_age_ceiling" in exc.value.detail


@pytest.mark.parametrize(
    "tamper,code",
    [
        (lambda d: d.update(schema_version="mixed_display_replay_v0"), ddr.INVALID),
        (lambda d: d.update(extra=1), ddr.INVALID),
        (lambda d: d.pop("downstream"), ddr.INVALID),
        (lambda d: d["scored_pool"]["identities"].reverse(), ddr.INVALID),
        (lambda d: d["downstream"].update(venue_settlement=None), ddr.INCOMPLETE),
        (lambda d: d["effective_context"].update(principal_mode="personalized"), ddr.UNSUPPORTED),
        (lambda d: d["chain_kwargs"].update(sports_mode=True), ddr.UNSUPPORTED),
    ],
    ids=["schema", "unknown-key", "missing-key", "identities", "venue-missing",
         "personalized", "sports"],
)
async def test_load_refuses_a_malformed_capture(harness, tamper, code):
    artifact = await _capture(harness)
    tamper(artifact)
    report = ddr.verify_baseline(artifact)
    assert report["verdict"] == code, report
    assert "scope" not in report, "a refusal carries no fidelity statement or metric"


# --------------------------------------------------------------------------- #
# Downstream stages: inactive and active
# --------------------------------------------------------------------------- #


def _enable_collections(monkeypatch, read):
    from app.services import container_discovery
    from app.utils import feed_collections

    monkeypatch.setattr(
        feed_collections, "feed_collections_enabled", lambda **_k: True
    )
    monkeypatch.setattr(
        feed_collections, "feed_collections_cache_fingerprint", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(container_discovery, "discover_collections", read)


async def test_inactive_collections_are_declared_inactive(harness):
    artifact = await _capture(harness)
    assert artifact["downstream"]["collections"] == {"active": False}
    assert artifact["downstream"]["edition"] == {"active": False}


async def test_an_active_collection_read_is_frozen_and_replayed(
    harness, monkeypatch, collection_card
):
    read = AsyncMock(return_value=SimpleNamespace(collections=[collection_card]))
    _enable_collections(monkeypatch, read)
    artifact = await _capture(harness)
    block = artifact["downstream"]["collections"]
    assert block["active"] and block["branch"] == "read"
    assert "collection:70" in artifact["expected"]["full_deck_identities"][:21]
    read.reset_mock()
    assert ddr.verify_baseline(artifact)["verdict"] == ddr.PASS
    read.assert_not_awaited()


async def test_a_failed_collection_read_replays_its_fail_open_branch(
    harness, monkeypatch
):
    _enable_collections(monkeypatch, AsyncMock(side_effect=RuntimeError("db")))
    artifact = await _capture(harness)
    assert artifact["downstream"]["collections"]["branch"] == "read_failed"
    assert ddr.verify_baseline(artifact)["verdict"] == ddr.PASS


async def test_venue_settlement_deltas_keep_absent_apart_from_false(harness, monkeypatch):
    from app.utils import venue_settlement_reader

    harness.venue_rows = [
        SimpleNamespace(
            _mapping={
                "id": ident,
                "status": "scheduled",
                "commence_time": harness.now - timedelta(hours=6),
                "home_team_name": "H",
                "away_team_name": "A",
                "home_score": None,
                "away_score": None,
                "win_probability_sources": {},
            },
            commence_time=harness.now - timedelta(hours=6),
        )
        for ident in _ASKABLE_IDS
    ]

    async def attach(db, rows, briefs, now):
        for brief in briefs:
            if brief["id"] == _ASKABLE_IDS[0]:
                brief["venue_settled"] = True
                brief["venue_settled_result"] = "Home 7101 wins"
            elif brief["id"] == _ASKABLE_IDS[1]:
                brief["venue_settled"] = False
            elif brief["id"] == _ASKABLE_IDS[2]:
                brief["venue_settled"] = True
                brief["venue_settled_result"] = None
                brief["venue_closed_no_winner"] = True

    monkeypatch.setattr(venue_settlement_reader, "attach_venue_settlement", attach)
    artifact = await _capture(harness)
    venue = artifact["downstream"]["venue_settlement"]
    assert venue["branch"] == "read"
    by_ident = {d["identity"]: ddr.decode_value(d["changes"]) for d in venue["deltas"]}
    assert set(by_ident) == {f"event:{i}" for i in _ASKABLE_IDS}, by_ident
    second = by_ident[f"event:{_ASKABLE_IDS[1]}"]
    assert second["venue_settled"] == {"before": {"absent": True}, "after": {"value": False}}
    assert "venue_closed_no_winner" not in second, "absent must stay absent"
    assert by_ident[f"event:{_ASKABLE_IDS[2]}"]["venue_closed_no_winner"]["after"] == {
        "value": True
    }
    assert ddr.verify_baseline(artifact)["verdict"] == ddr.PASS

    # The delta's precondition is checked, not assumed.
    venue["deltas"][0]["changes"]["venue_settled"]["before"] = {"value": False}
    assert ddr.verify_baseline(artifact)["verdict"] == ddr.MISMATCH


async def test_a_failed_venue_read_is_recorded_as_fail_open(harness, monkeypatch):
    from app.utils import venue_settlement_reader

    harness.venue_rows = []
    monkeypatch.setattr(
        venue_settlement_reader,
        "attach_venue_settlement",
        AsyncMock(side_effect=RuntimeError("venue down")),
    )
    artifact = await _capture(harness)
    venue = artifact["downstream"]["venue_settlement"]
    assert venue == {"branch": "failed_open", "deltas": []}
    assert ddr.verify_baseline(artifact)["verdict"] == ddr.PASS


async def test_a_pinned_edition_is_frozen_and_replayed(harness):
    from tests.integration.test_route_feed_collections_cache_10003 import _DictRedis

    fake = _DictRedis()
    harness.set_redis(fake)
    scheduled: list = []
    harness.monkeypatch.setattr(_rc, "schedule_background", scheduled.append)
    first = await harness.get("/api/feed?limit=20")
    while scheduled:
        await scheduled.pop(0)
    token = first.json()["edition"]
    url = f"/api/feed?limit=20&offset=20&edition={token}"

    # With the page base present, page two is pinned off the CACHED base: a
    # cache tier, so it is not a capture.
    capture = ddr.DiscoverDisplayCapture(origin="synthetic")
    cached = await harness.get(url, capture=capture)
    assert cached.json()["edition_status"] == "pinned"
    with pytest.raises(ddr.DisplayReplayError) as exc:
        capture.artifact()
    assert exc.value.code == ddr.INCOMPLETE

    # Keep only the manifest, so page two is BUILT and pinned on the build path.
    for key in [k for k in fake.store if not k.startswith("feed_cache:edition:")]:
        del fake.store[key]
    assert fake.store, "the manifest must survive for the pin to be exercised"
    artifact = await _capture(harness, url=url)
    edition = artifact["downstream"]["edition"]
    assert edition["active"] and edition["status"] == "pinned"
    assert artifact["expected"]["public_response"]["edition_status"] == "pinned"
    assert ddr.verify_baseline(artifact)["verdict"] == ddr.PASS


# --------------------------------------------------------------------------- #
# The live helpers the replay borrows
# --------------------------------------------------------------------------- #


def test_the_venue_attach_reports_its_branch():
    from app.routes.feed import (
        VENUE_ATTACH_FAILED_OPEN,
        VENUE_ATTACH_NOTHING_ASKABLE,
        _attach_feed_venue_settlement,
    )
    import asyncio

    now = datetime.now(timezone.utc)
    upcoming = [_event(1, 50, now + timedelta(hours=3))]
    assert (
        asyncio.run(_attach_feed_venue_settlement(AsyncMock(), upcoming, now))
        == VENUE_ATTACH_NOTHING_ASKABLE
    )
    db = AsyncMock()
    db.execute.side_effect = RuntimeError("db down")
    started = [_event(2, 50, now - timedelta(hours=5))]
    assert (
        asyncio.run(_attach_feed_venue_settlement(db, started, now))
        == VENUE_ATTACH_FAILED_OPEN
    )
    assert "venue_settled" not in started[0]["data"]


def test_the_codec_restores_types_and_refuses_what_it_does_not_know():
    now = datetime(2026, 10, 3, 6, 0, tzinfo=timezone.utc)
    value = {
        "when": now,
        "day": now.date(),
        "money": Decimal("1.10"),
        "tags": {"b", "a"},
        "frozen": frozenset({1}),
        "pair": (1, "x"),
        "keys": {7: "seven"},
        "nan": float("nan"),
        "flag": True,
        "one": 1,
        "onef": 1.0,
        "none": None,
    }
    back = ddr.decode_value(json.loads(json.dumps(ddr.encode_value(value))))
    assert back["when"] == now and isinstance(back["when"], datetime)
    assert back["money"] == Decimal("1.10") and isinstance(back["money"], Decimal)
    assert back["tags"] == {"a", "b"} and back["frozen"] == frozenset({1})
    assert back["pair"] == (1, "x") and back["keys"] == {7: "seven"}
    assert back["nan"] != back["nan"]
    assert ddr.canonical(1) != ddr.canonical(1.0) != ddr.canonical(True)
    with pytest.raises(ddr.DisplayReplayError) as exc:
        ddr.encode_value({"x": object()})
    assert exc.value.code == ddr.UNSUPPORTED


# --------------------------------------------------------------------------- #
# The script mode
# --------------------------------------------------------------------------- #


async def test_the_script_exits_zero_only_on_pass(harness, tmp_path):
    artifact = await _capture(harness)
    good = tmp_path / "good.json"
    ddr.write_capture(artifact, str(good))
    artifact["expected"]["full_deck_identities"][30] = "futures:0"
    bad = tmp_path / "bad.json"
    ddr.write_capture(artifact, str(bad))
    script = BACKEND / "scripts/replay_discover_ranking.py"
    ok = subprocess.run(
        [sys.executable, str(script), "--mixed-capture", str(good), "--json"],
        capture_output=True, text=True, cwd=BACKEND, timeout=300,
    )
    assert ok.returncode == 0, ok.stderr[-2000:]
    assert json.loads(ok.stdout)["verdict"] == "PASS"
    nope = subprocess.run(
        [sys.executable, str(script), "--mixed-capture", str(bad), "--json"],
        capture_output=True, text=True, cwd=BACKEND, timeout=300,
    )
    assert nope.returncode == 1
    report = json.loads(nope.stdout)
    assert report["verdict"] == "MISMATCH" and report["first_divergence"] == 30
