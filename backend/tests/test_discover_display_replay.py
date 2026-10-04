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


def _no_network_stub(*_a, **_k):
    """Stands in for a socket call that would have reached the network — so a
    candidate the fence misses completes instead of failing, and no test
    ever makes real traffic."""
    return SimpleNamespace(close=lambda: None)


async def test_a_candidate_arm_that_reaches_the_network_is_refused(harness, monkeypatch):
    """#10290 review: the candidate arm runs under the SAME fence as the chain.
    Before the fix the arm ran before ``offline()`` and this stub was reached."""
    artifact = await _capture(harness)
    monkeypatch.setattr(socket, "create_connection", _no_network_stub)
    reached = []

    def hydrating_arm(pool):
        socket.create_connection(("api.bainluck.com", 443), timeout=1)
        reached.append(True)
        return pool

    with pytest.raises(ddr.DisplayReplayError) as exc:
        ddr.replay_capture(artifact, arm=hydrating_arm)
    assert exc.value.code == ddr.OFFLINE_VIOLATION
    assert reached == [], "the stub was reached: the arm ran outside the fence"
    # The fence is lifted afterwards: the pre-installed stub is back.
    assert socket.create_connection is _no_network_stub


async def test_a_candidate_arm_that_queries_the_database_is_refused(harness):
    artifact = await _capture(harness)

    def querying_arm(pool):
        from sqlalchemy.orm import Session

        Session.execute(None, "SELECT 1")
        return pool

    with pytest.raises(ddr.DisplayReplayError) as exc:
        ddr.replay_capture(artifact, arm=querying_arm)
    assert exc.value.code == ddr.OFFLINE_VIOLATION

    # Control: the same capture with a pure arm replays to the oracle.
    replay = ddr.replay_capture(artifact, arm=lambda pool: pool)
    assert replay["deck_identities"] == artifact["expected"]["full_deck_identities"]


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


def _set_request(**changes):
    """Rewrite facts inside the encoded ``effective_request``."""

    def tamper(d):
        d["effective_request"].update(changes)

    return tamper


def _venue(**changes):
    def tamper(d):
        d["downstream"]["venue_settlement"].update(changes)

    return tamper


# #10290 review, BLOCKER 1: each of these is a loaded capture the replay would
# otherwise have taken to PASS with full deck and page parity — the replay
# ignored browse metadata and treated an unknown branch as "nothing happened".
_UNSUPPORTED_LOADED = [
    ("venue-unknown-branch", _venue(branch="future_unimplemented_branch"), ddr.UNSUPPORTED),
    (
        "collections-unknown-branch-inactive-capture",
        lambda d: d["downstream"].update(
            collections={
                "active": True,
                "branch": "future_unimplemented_branch",
                "page_window": 20,
                "collections": None,
            }
        ),
        ddr.INVALID,  # also disagrees with request.collections_enabled
    ),
    ("category-browse", _set_request(category="politics"), ddr.UNSUPPORTED),
    ("sport-browse", _set_request(sport="basketball_nba"), ddr.UNSUPPORTED),
    ("tags-browse", _set_request(tags="nfl"), ddr.UNSUPPORTED),
    ("mode-sports", _set_request(mode="sports"), ddr.UNSUPPORTED),
    ("events-only", _set_request(include_futures=False), ddr.UNSUPPORTED),
    ("debug", _set_request(debug=True), ddr.UNSUPPORTED),
    ("reviewed-filter", _set_request(exclude_reviewed=True), ddr.UNSUPPORTED),
    ("session-principal", _set_request(principal_session=True), ddr.UNSUPPORTED),
    ("user-principal", _set_request(principal_user=True), ddr.UNSUPPORTED),
    ("cache-hit", _set_request(cache_status="hit"), ddr.UNSUPPORTED),
    ("unknown-build-quality", _set_request(build_quality="partial"), ddr.UNSUPPORTED),
    (
        "degraded-reason-on-complete",
        _set_request(degraded_reason="futures_timeout"),
        ddr.INVALID,
    ),
    ("unknown-request-fact", _set_request(region="eu"), ddr.INVALID),
    ("missing-request-fact", lambda d: d["effective_request"].pop("category"), ddr.INVALID),
    ("limit-disagrees", lambda d: d["chain_kwargs"].update(limit=50), ddr.INVALID),
    (
        "event-pct-disagrees",
        lambda d: d["chain_kwargs"].update(event_pct=d["chain_kwargs"]["event_pct"] + 0.1),
        ddr.INVALID,
    ),
    ("unknown-chain-kwarg", lambda d: d["chain_kwargs"].update(boost=1), ddr.INVALID),
    ("support-claims-more", lambda d: d["support"].update(sports="supported"), ddr.UNSUPPORTED),
    ("context-changed", lambda d: d["effective_context"].update(cold_start="forced"), ddr.UNSUPPORTED),
    ("edition-without-request", lambda d: d["downstream"].update(
        edition={"active": True, "manifest": None, "requested_policy": "x",
                 "now": 0.0, "status": "pinned"}), ddr.INVALID),
    ("edition-request-without-pin", _set_request(edition="tok"), ddr.INVALID),
    ("deltas-on-fail-open", _venue(
        branch="failed_open",
        deltas=[{"position": 0, "identity": "event:1",
                 "changes": {"venue_settled": {"before": {"absent": True},
                                               "after": {"value": True}}}}],
    ), ddr.INVALID),
    ("delta-outside-venue-fields", _venue(
        branch="read",
        deltas=[{"position": 0, "identity": "event:1",
                 "changes": {"probability": {"before": {"absent": True},
                                             "after": {"value": 0.9}}}}],
    ), ddr.UNSUPPORTED),
    ("unknown-downstream-stage", lambda d: d["downstream"].update(boosts={}), ddr.INVALID),
    ("config-digest", lambda d: d["provenance"].update(effective_config_digest="0" * 64), ddr.INVALID),
    ("naive-clock", lambda d: d["clocks"].update(
        scoring_now=d["clocks"]["scoring_now"][:19]), ddr.INVALID),
]


@pytest.mark.parametrize(
    "tamper,code",
    [(t, c) for _, t, c in _UNSUPPORTED_LOADED],
    ids=[name for name, _, _ in _UNSUPPORTED_LOADED],
)
async def test_a_loaded_capture_outside_the_contract_never_passes(harness, tamper, code):
    artifact = await _capture(harness)
    # Not vacuous: the untouched capture is a real PASS through the shared chain.
    assert ddr.verify_baseline(copy.deepcopy(artifact))["verdict"] == ddr.PASS
    tamper(artifact)
    report = ddr.verify_baseline(artifact)
    assert report["verdict"] == code, report
    assert "scope" not in report, "a refusal carries no fidelity statement or metric"
    # And the replay refuses on its own — it does not rely on load_capture.
    with pytest.raises(ddr.DisplayReplayError) as exc:
        ddr.replay_capture(artifact)
    assert exc.value.code == code


async def test_an_unknown_branch_on_an_active_collection_capture_is_unsupported(
    harness, monkeypatch, collection_card
):
    read = AsyncMock(return_value=SimpleNamespace(collections=[collection_card]))
    _enable_collections(monkeypatch, read)
    artifact = await _capture(harness)
    assert ddr.verify_baseline(copy.deepcopy(artifact))["verdict"] == ddr.PASS

    unknown = copy.deepcopy(artifact)
    unknown["downstream"]["collections"].update(
        branch="future_unimplemented_branch", collections=None
    )
    assert ddr.verify_baseline(unknown)["verdict"] == ddr.UNSUPPORTED

    # The read branch with its input missing is incomplete, not "no insertion".
    missing = copy.deepcopy(artifact)
    missing["downstream"]["collections"]["collections"] = None
    assert ddr.verify_baseline(missing)["verdict"] == ddr.INCOMPLETE

    # A fail-open branch that carries cards it never read is not consistent.
    phantom = copy.deepcopy(artifact)
    phantom["downstream"]["collections"]["branch"] = "read_failed"
    assert ddr.verify_baseline(phantom)["verdict"] == ddr.INVALID


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


# --------------------------------------------------------------------------- #
# #10290 warm-capture: the explicit operator warm-rail rebuild mode
# --------------------------------------------------------------------------- #
#
# The sole production attempt refused INCOMPLETE before any build was captured,
# and the caller had thrown the Response away, so which branch returned was
# unknowable. These drive the SCRIPT's own `capture_mixed_build` — the real
# `get_feed`, called in-process exactly as the runner calls it — over warm
# caches: the ordinary default must still refuse (and now say which tier
# served it), and only the explicit mode reaches the seam and the final return.


def _route_session(harness, monkeypatch):
    from contextlib import asynccontextmanager

    from app.tasks import base as tasks_base

    @asynccontextmanager
    async def _session():
        yield harness.session

    monkeypatch.setattr(tasks_base, "get_task_session", _session)


async def _warm(harness, monkeypatch):
    """Publish the anonymous Discover shape into every cache tier, the way the
    warm rail leaves production: response fresh + :stale, page base, edition."""
    from tests.integration.test_route_feed_collections_cache_10003 import _DictRedis

    fake = _DictRedis()
    harness.set_redis(fake)
    scheduled: list = []
    monkeypatch.setattr(_rc, "schedule_background", scheduled.append)
    first = await harness.get("/api/feed?limit=20")
    assert first.headers["x-feed-cache"] == "miss"
    while scheduled:
        await scheduled.pop(0)
    assert any(k.startswith("feed_cache") and not k.endswith(":stale") for k in fake.store)
    harness.reset_process_caches()
    fake.reads.clear()
    return fake, scheduled


async def _script_capture(harness, monkeypatch, tmp_path, *, warm_rail, name="c.json"):
    import scripts.replay_discover_ranking as runner

    _route_session(harness, monkeypatch)
    harness.reset_process_caches()
    out = tmp_path / name
    result = await runner.capture_mixed_build(
        str(out), origin="synthetic", limit=20, offset=0, warm_rail_rebuild=warm_rail
    )
    return result, out


def _hook_spy(monkeypatch, name):
    calls: list = []
    real = getattr(ddr.DiscoverDisplayCapture, name)

    def spy(self, *a, **k):
        calls.append(self.status)
        return real(self, *a, **k)

    spy.__name__ = name
    monkeypatch.setattr(ddr.DiscoverDisplayCapture, name, spy)
    return calls


async def test_the_ordinary_capture_still_refuses_a_warm_cache_and_names_the_tier(
    harness, monkeypatch, tmp_path
):
    await _warm(harness, monkeypatch)
    entries = _hook_spy(monkeypatch, "record_chain_entry")
    result, out = await _script_capture(harness, monkeypatch, tmp_path, warm_rail=False)

    assert result["captured"] is False and result["code"] == ddr.INCOMPLETE
    assert result["capture_mode"] == ddr.CAPTURE_MODE_ORDINARY
    assert not out.exists(), "cached output must never become a capture"
    assert entries == [], "a cache-tier return never reaches the seam"
    disposition = result["disposition"]
    assert disposition == {
        "classification": "cache_tier_early_return",
        "capture_mode": ddr.CAPTURE_MODE_ORDINARY,
        "recorder_status": "armed",
        "refusal_code": None,
        "x_feed_cache": "hit",
        "x_feed_singleflight": "none",
        "payload_cache_status": "hit",
        "payload_cache_reason": None,
    }


async def test_the_explicit_warm_rail_mode_reaches_the_seam_and_the_final_return(
    harness, monkeypatch, tmp_path
):
    from app.utils.feed_cache import warm_rail_max_shared_artifact_age_s

    fake, scheduled = await _warm(harness, monkeypatch)
    entries = _hook_spy(monkeypatch, "record_chain_entry")
    returns = _hook_spy(monkeypatch, "record_response")
    result, out = await _script_capture(harness, monkeypatch, tmp_path, warm_rail=True)

    assert result["captured"] is True, result
    assert result["capture_mode"] == ddr.CAPTURE_MODE_WARM_RAIL
    assert entries == ["armed"] and returns == ["recording"]
    # The rebuild read no response tier and no page base: the warm entries
    # were there (`_warm`) and were skipped, not missed.
    assert not [k for k in fake.reads if k.startswith("feed_cache")], fake.reads
    # Ordinary publication ran: the route scheduled its own response-cache write.
    published = {getattr(c, "__qualname__", "") for c in scheduled}
    assert any("_publish_feed_cache" in q for q in published), published

    artifact = ddr.load_capture(str(out))
    provenance = artifact["provenance"]
    assert provenance["capture_mode"] == ddr.CAPTURE_MODE_WARM_RAIL
    operational = provenance["operational"]
    assert operational["claims"] == {
        "public_request_served": False,
        "upstream_admission_and_scoring_replayed": False,
    }
    assert operational["shared_artifact_max_age_s"] == warm_rail_max_shared_artifact_age_s()
    assert operational["resolved_cache_key_written_back"] is True
    assert operational["publication_eligible"] is True
    assert ddr.decode_value(artifact["effective_request"])["cache_status"] == "miss"
    clocks = artifact["clocks"]
    assert clocks["armed_wall"] <= clocks["chain_entry_wall"] <= clocks["response_wall"]
    report = ddr.verify_baseline(str(out))
    assert report["verdict"] == ddr.PASS, report
    assert report["scope"]["capture_mode"] == ddr.CAPTURE_MODE_WARM_RAIL
    for coro in scheduled:
        coro.close()


async def test_an_armed_warm_rail_capture_does_not_change_the_rebuild(harness, monkeypatch):
    """Enabled vs disabled parity for the new mode: the warm rail's own rebuild
    (the precompute task's marker request, no recorder) and the armed capture
    return the same page from the same inputs."""
    from fastapi import Response

    from app.routes.feed import get_feed
    from app.tasks.precompute_category_pages import _build_prewarm_request
    from app.utils.feed_cache import FEED_PREWARM_SCOPE_KEY

    kwargs = dict(
        limit=20, offset=0, sport=None, category=None, include_events=True,
        include_futures=True, my_teams_only=False, mode=None, tags=None,
        event_pct=None, edition=None, debug=False, debug_ground_truth=False,
        debug_personalization=False, exclude_reviewed=False, reviewer=None,
        reviewed_surface=None, secret=None, db=harness.session, user=None,
    )
    harness.reset_process_caches()
    plain = await get_feed(
        response=Response(), request=_build_prewarm_request(FEED_PREWARM_SCOPE_KEY), **kwargs
    )
    harness.reset_process_caches()
    capture = ddr.DiscoverDisplayCapture(origin="synthetic", mode=ddr.CAPTURE_MODE_WARM_RAIL)
    armed = await get_feed(response=Response(), request=ddr.capture_request(capture), **kwargs)
    assert capture.status == "complete", capture.refusal
    assert ddr.canonical(_without_cache(armed)) == ddr.canonical(_without_cache(plain))
    assert len(plain["items"]) == 20


async def test_both_modes_capture_the_same_build_from_the_same_inputs(
    harness, monkeypatch, tmp_path
):
    """Cold caches: the ordinary capture succeeds too. The two modes then
    differ in their declared operation and nothing else that a replay reads."""
    ordinary, o_path = await _script_capture(
        harness, monkeypatch, tmp_path, warm_rail=False, name="o.json"
    )
    warm, w_path = await _script_capture(
        harness, monkeypatch, tmp_path, warm_rail=True, name="w.json"
    )
    assert ordinary["captured"] and warm["captured"]
    a, b = ddr.load_capture(str(o_path)), ddr.load_capture(str(w_path))
    assert a["provenance"]["operational"] == {
        "kind": ddr.CAPTURE_MODE_ORDINARY,
        "cache_reads": a["provenance"]["operational"]["cache_reads"],
    }
    assert a["scored_pool"]["identities"] == b["scored_pool"]["identities"]
    assert a["expected"]["full_deck_identities"] == b["expected"]["full_deck_identities"]
    assert a["expected"]["full_public_deck_digest"] == b["expected"]["full_public_deck_digest"]
    want = ddr.decode_value(a["expected"]["public_response"])
    got = ddr.decode_value(b["expected"]["public_response"])
    assert ddr.canonical(_without_cache(want)) == ddr.canonical(_without_cache(got))
    assert ddr.verify_baseline(a)["verdict"] == ddr.verify_baseline(b)["verdict"] == ddr.PASS


async def test_a_warm_rail_capture_armed_outside_capture_request_refuses(harness):
    capture = ddr.DiscoverDisplayCapture(origin="synthetic", mode=ddr.CAPTURE_MODE_WARM_RAIL)
    response = await harness.get("/api/feed?limit=20", capture=capture)
    assert response.status_code == 200
    with pytest.raises(ddr.DisplayReplayError) as exc:
        capture.artifact()
    assert exc.value.code == ddr.INVALID
    assert "capture_request" in exc.value.detail


async def _direct(harness, capture, *, mutate_scope=None):
    from fastapi import Response

    from app.routes.feed import get_feed

    request = ddr.capture_request(capture)
    if mutate_scope:
        mutate_scope(request.scope)
    harness.reset_process_caches()
    return await get_feed(
        response=Response(), request=request, limit=20, offset=0, sport=None,
        category=None, include_events=True, include_futures=True,
        my_teams_only=False, mode=None, tags=None, event_pct=None, edition=None,
        debug=False, debug_ground_truth=False, debug_personalization=False,
        exclude_reviewed=False, reviewer=None, reviewed_surface=None, secret=None,
        db=harness.session, user=None,
    )


async def test_an_ordinary_capture_carrying_the_marker_is_not_ordinary(harness):
    from app.utils.feed_cache import FEED_PREWARM_SCOPE_KEY

    capture = ddr.DiscoverDisplayCapture(origin="synthetic")
    await _direct(
        harness, capture, mutate_scope=lambda s: s.__setitem__(FEED_PREWARM_SCOPE_KEY, True)
    )
    with pytest.raises(ddr.DisplayReplayError) as exc:
        capture.artifact()
    assert exc.value.code == ddr.UNSUPPORTED


async def test_a_warm_rail_capture_the_route_did_not_honour_refuses(harness, monkeypatch):
    from app.utils import principal_independent_cache as _pic

    monkeypatch.setattr(_pic, "bind_max_shared_age", lambda _bound: None)
    capture = ddr.DiscoverDisplayCapture(origin="synthetic", mode=ddr.CAPTURE_MODE_WARM_RAIL)
    await _direct(harness, capture)
    with pytest.raises(ddr.DisplayReplayError) as exc:
        capture.artifact()
    assert exc.value.code == ddr.INCOMPLETE
    assert "not honoured" in exc.value.detail


def test_an_unknown_capture_mode_cannot_be_constructed():
    with pytest.raises(ValueError):
        ddr.DiscoverDisplayCapture(origin="synthetic", mode="force_build")


async def _warm_artifact(harness):
    capture = ddr.DiscoverDisplayCapture(origin="synthetic", mode=ddr.CAPTURE_MODE_WARM_RAIL)
    await _direct(harness, capture)
    return json.loads(json.dumps(capture.artifact()))


def _op(**changes):
    return lambda d: d["provenance"]["operational"].update(**changes)


@pytest.mark.parametrize(
    "tamper,code",
    [
        (lambda d: d["provenance"].pop("capture_mode"), ddr.INVALID),
        (lambda d: d["provenance"].update(capture_mode="force_build"), ddr.UNSUPPORTED),
        (lambda d: d["provenance"].update(capture_mode=None), ddr.UNSUPPORTED),
        (lambda d: d["provenance"].pop("operational"), ddr.INVALID),
        (lambda d: d["provenance"]["operational"].pop("shared_artifact_max_age_s"), ddr.INVALID),
        (_op(shared_artifact_max_age_s=-1), ddr.INVALID),
        (_op(shared_artifact_max_age_s="10"), ddr.INVALID),
        (_op(shared_artifact_max_age_s=True), ddr.INVALID),
        (_op(claims={"public_request_served": True,
                     "upstream_admission_and_scoring_replayed": False}), ddr.INVALID),
        (_op(trigger="an HTTP header"), ddr.INVALID),
        (_op(resolved_cache_key_written_back=False), ddr.INVALID),
        (_op(publication_eligible=False), ddr.INVALID),
        (_op(extra=1), ddr.INVALID),
        (lambda d: d["provenance"].update(capture_mode=ddr.CAPTURE_MODE_ORDINARY), ddr.INVALID),
        (lambda d: d["clocks"].pop("armed_wall"), ddr.INVALID),
        (lambda d: d["expected"].update(returned_build_digest="0" * 64), ddr.INVALID),
        (lambda d: d.update(schema_version="mixed_display_replay_v1"), ddr.INVALID),
    ],
    ids=["mode-missing", "mode-unknown", "mode-null", "operational-missing",
         "bound-missing", "bound-negative", "bound-string", "bound-bool",
         "claims-served", "trigger-text", "key-writeback-flip", "publication-flip",
         "operational-extra", "ordinary-with-warm-declaration", "armed-wall-missing",
         "returned-digest", "schema-v1"],
)
async def test_a_warm_rail_capture_outside_its_declaration_never_passes(
    harness, tamper, code
):
    artifact = await _warm_artifact(harness)
    assert ddr.verify_baseline(copy.deepcopy(artifact))["verdict"] == ddr.PASS
    tamper(artifact)
    report = ddr.verify_baseline(artifact)
    assert report["verdict"] == code, report
    assert "scope" not in report


async def test_a_warm_rail_build_that_resolved_no_cache_key_declares_no_publication(
    harness,
):
    """`disabled` (an unreadable collections fingerprint) resolves no key: the
    route writes no key back and publishes nothing, and the declaration must
    say so — the consistency check binds in both directions."""
    artifact = await _warm_artifact(harness)
    request = ddr.decode_value(artifact["effective_request"])
    request["cache_status"] = "disabled"
    artifact["effective_request"] = ddr.encode_value(request)
    assert ddr.verify_baseline(copy.deepcopy(artifact))["verdict"] == ddr.INVALID
    artifact["provenance"]["operational"].update(
        resolved_cache_key_written_back=False, publication_eligible=False
    )
    assert ddr.verify_baseline(artifact)["verdict"] == ddr.PASS


def test_the_refusal_disposition_is_allowlisted():
    capture = ddr.DiscoverDisplayCapture(origin="synthetic")
    secret_text = "Bearer sk-live-10290 Will the Chiefs win"
    headers = {
        "x-feed-cache": secret_text,
        "x-feed-singleflight": "leader",
        "authorization": secret_text,
    }
    payload = {
        "items": [{"type": "futures", "data": {"name": secret_text}}],
        "cache": {"status": "stale_hit", "reason": secret_text},
    }
    disposition = ddr.refusal_disposition(
        capture, response_headers=headers, payload=payload
    )
    assert secret_text not in json.dumps(disposition)
    assert disposition["x_feed_cache"] == "unrecognized"
    assert disposition["payload_cache_reason"] == "unrecognized"
    assert disposition["payload_cache_status"] == "stale_hit"
    assert disposition["x_feed_singleflight"] == "leader"
    assert disposition["classification"] == "returned_before_seam"
    assert set(disposition) == {
        "classification", "capture_mode", "recorder_status", "refusal_code",
        "x_feed_cache", "x_feed_singleflight", "payload_cache_status",
        "payload_cache_reason",
    }
    # No Response, no payload: still a bounded answer, never a crash.
    bare = ddr.refusal_disposition(capture, response_headers=None, payload=None)
    assert bare["x_feed_cache"] is None and bare["payload_cache_status"] is None

    capture.status = "recording"
    capture.abandon("input_age_ceiling")
    assert ddr.refusal_disposition(capture, response_headers={}, payload={})[
        "classification"
    ] == "build_abandoned"


def test_every_cache_state_the_route_writes_is_on_the_allowlist():
    """The disposition reads the route's own stamps through closed sets; a new
    state in the route must be added here or it reports as `unrecognized`."""
    import re

    source = (BACKEND / "app/routes/feed.py").read_text()
    statuses = set(re.findall(r'cache_status\s*=\s*"([a-z_]+)"', source))
    statuses |= set(re.findall(r'"((?:shared|page_base)_(?:stale_)?hit)"', source))
    reasons = set(re.findall(r'reason="([a-z_]+)"', source))
    flights = set(re.findall(r'singleflight="([a-z_]+)"', source))
    assert statuses and reasons and flights
    assert statuses <= ddr.FEED_CACHE_DISPOSITIONS, statuses - ddr.FEED_CACHE_DISPOSITIONS
    assert reasons <= ddr.FEED_CACHE_REASONS, reasons - ddr.FEED_CACHE_REASONS
    assert flights <= ddr.FEED_SINGLEFLIGHT_STATES, flights - ddr.FEED_SINGLEFLIGHT_STATES
    assert ddr.CACHED_EARLY_RETURNS <= ddr.FEED_CACHE_DISPOSITIONS


async def test_an_exception_in_the_build_is_not_a_cache_refusal(
    harness, monkeypatch, tmp_path
):
    from app.routes import feed as feed_route

    async def _boom(**_kwargs):
        raise RuntimeError("build failed")

    monkeypatch.setattr(feed_route, "get_feed", _boom)
    with pytest.raises(RuntimeError, match="build failed"):
        await _script_capture(harness, monkeypatch, tmp_path, warm_rail=True)
