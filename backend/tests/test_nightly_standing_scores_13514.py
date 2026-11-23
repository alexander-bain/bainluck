"""Tests for backend/scripts/nightly_standing_scores.py and its workflow (#13514)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
import yaml

from scripts.nightly_standing_scores import (
    MIN_LIVE_PACE_SECONDS,
    compute_stale_sportsbook_census,
    effective_pace_seconds,
    render_markdown_report,
    run_standing_scores,
    select_audit_games,
    write_artifacts,
)


NOW = datetime(2026, 11, 23, 18, 0, tzinfo=timezone.utc)


def _event_payload(
    eid: int,
    *,
    sport: str = "basketball_nba",
    home: str = "Boston Celtics",
    away: str = "Miami Heat",
    status: str = "scheduled",
    hours_from_now: float = 4.0,
    hero: float = 0.62,
    books: int = 8,
    betting_age_hours: float | None = 1.0,
    extra_sources: list[dict] | None = None,
) -> dict:
    commence = (NOW + timedelta(hours=hours_from_now)).isoformat()
    sources = [
        {"key": "betting", "name": "Sportsbooks", "probability": hero, "count": books},
        *(extra_sources or []),
    ]
    wps: dict[str, dict] = {
        "betting_book_count": {"value": float(books)},
    }
    if betting_age_hours is not None:
        wps["betting"] = {
            "value": hero,
            "updated_at": (NOW - timedelta(hours=betting_age_hours)).isoformat(),
        }
    return {
        "id": eid,
        "sport": sport,
        "home_team": home,
        "away_team": away,
        "commence_time": commence,
        "status": status,
        "hero_probability": hero,
        "current_odds": {
            "home_probability": hero,
            "home_rendered_percent": int(round(hero * 100)),
            "bookmaker_count": books,
        },
        "source_mark": {"state": "single" if len(sources) == 1 else "blend", "sources": sources},
        "win_probability_sources": wps,
    }


def _mock_transport(
    *,
    list_events: list[dict],
    details_by_id: dict[int, dict],
    feed_events: list[dict] | None = None,
    league_events: dict[str, list[dict]] | None = None,
    search_events: dict[str, list[dict]] | None = None,
) -> httpx.MockTransport:
    def _handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/health":
            return httpx.Response(200, json={"status": "ok", "commit": "abc12345"})
        if path == "/api/events":
            qs = parse_qs(request.url.query.decode() if isinstance(request.url.query, bytes) else str(request.url.query))
            req_status = (qs.get("status") or [None])[0]
            offset = int((qs.get("offset") or ["0"])[0])
            rows = [
                ev
                for ev in list_events
                if req_status is None or str(ev.get("status") or "").lower() == req_status.lower()
            ]
            return httpx.Response(200, json={"events": rows[offset:]})
        if path == "/api/feed":
            return httpx.Response(
                200,
                json={"items": [{"type": "event", "data": ev} for ev in (feed_events or [])]},
            )
        if path.startswith("/api/leagues/"):
            sk = path.split("/api/leagues/", 1)[1]
            return httpx.Response(200, json={"upcoming_games": (league_events or {}).get(sk, [])})
        if path == "/api/events/search":
            q = parse_qs(request.url.query.decode() if isinstance(request.url.query, bytes) else str(request.url.query)).get("q", [""])[0]
            return httpx.Response(200, json={"results": (search_events or {}).get(q, [])})
        if path.startswith("/api/events/"):
            eid = int(path.rsplit("/", 1)[-1])
            return httpx.Response(200, json=details_by_id[eid])
        return httpx.Response(404, json={"detail": "not found"})

    return httpx.MockTransport(_handler)


def test_clean_parity_and_dated_outputs(tmp_path: Path):
    ev1 = _event_payload(101, sport="basketball_nba", home="Celtics", away="Heat", hero=0.64, books=9)
    ev2 = _event_payload(102, sport="soccer_epl", home="Arsenal", away="Chelsea", hero=0.52, books=10, status="live", hours_from_now=-1.0)
    transport = _mock_transport(
        list_events=[ev1, ev2],
        details_by_id={101: ev1, 102: ev2},
        feed_events=[ev1, ev2],
        league_events={"basketball_nba": [ev1], "soccer_epl": [ev2]},
        search_events={"Arsenal": [ev2], "Celtics": [ev1]},
    )

    result = run_standing_scores(
        base_url="http://test",
        pace_seconds=0.0,
        run_date="2026-11-23",
        transport=transport,
        now_fn=lambda: NOW,
        sleep_fn=lambda _: None,
    )

    assert result["overall_status"] == "PASS"
    assert result["live_commit"] == "abc12345"
    assert result["list_vs_page"]["games_verified"] == 2
    assert result["list_vs_page"]["sports_covered"] == ["basketball_nba", "soccer_epl"]
    assert result["list_vs_page"]["surface_comparisons"] >= 6
    assert result["list_vs_page"]["disagreements_count"] == 0
    assert result["stale_sportsbook_census"]["stale_over_threshold_count"] == 0

    dated_json, latest_json, dated_md = write_artifacts(result, tmp_path)
    assert dated_json.name == "2026-11-23.json"
    assert json.loads(dated_json.read_text()) == json.loads(latest_json.read_text())
    md_text = dated_md.read_text()
    assert "# Nightly Standing Scores — 2026-11-23" in md_text
    assert "`PASS`" in md_text


def test_detects_headline_source_and_bookmaker_disagreements():
    card_list = _event_payload(
        201,
        hero=0.64,
        books=7,
        extra_sources=[{"key": "polymarket", "name": "Polymarket", "probability": 0.61}],
    )
    detail = _event_payload(
        201,
        hero=0.69,
        books=10,
        extra_sources=[{"key": "polymarket", "name": "Polymarket", "probability": 0.66}],
    )
    transport = _mock_transport(
        list_events=[card_list],
        details_by_id={201: detail},
    )

    result = run_standing_scores(
        base_url="http://test",
        pace_seconds=0.0,
        run_date="2026-11-23",
        transport=transport,
        now_fn=lambda: NOW,
        sleep_fn=lambda _: None,
    )

    assert result["overall_status"] == "FAIL"
    fields = {d["field"] for d in result["list_vs_page"]["disagreements"]}
    assert "headline_percent" in fields
    assert "source.polymarket" in fields
    assert "bookmaker_count" in fields


def test_round_robin_selection_covers_all_sports_and_prioritizes_live():
    events = [
        _event_payload(1, sport="nba", status="scheduled", hours_from_now=2.0),
        _event_payload(2, sport="nba", status="scheduled", hours_from_now=3.0),
        _event_payload(3, sport="nba", status="scheduled", hours_from_now=4.0),
        _event_payload(4, sport="nhl", status="live", hours_from_now=-0.5),
        _event_payload(5, sport="epl", status="scheduled", hours_from_now=1.0),
        _event_payload(6, sport="epl", status="scheduled", hours_from_now=80.0),  # outside 48h window
    ]
    chosen = select_audit_games(events, now=NOW, max_games=4, horizon_hours=48.0)
    chosen_ids = [e["id"] for e in chosen]
    assert chosen_ids[0] == 4  # live game first
    assert set(chosen_ids) >= {1, 4, 5}  # every sport represented before filling extra nba
    assert 6 not in chosen_ids


def test_stale_census_catches_untwinned_over_72h_scheduled_game_only():
    events = [
        _event_payload(301, status="scheduled", betting_age_hours=72.5, books=4),
        _event_payload(302, status="scheduled", betting_age_hours=71.9, books=10),
        _event_payload(303, status="completed", betting_age_hours=120.0, books=8),
        _event_payload(304, status="scheduled", betting_age_hours=None, books=0),
    ]
    census = compute_stale_sportsbook_census(events, now=NOW, stale_hours=72.0)
    assert census["scheduled_total"] == 3
    assert census["scheduled_with_betting"] == 2
    assert census["stale_over_threshold_count"] == 1
    assert [g["id"] for g in census["stale_games"]] == [301]


def test_live_pace_guard_enforces_at_least_3_5s():
    assert effective_pace_seconds("https://api.bainluck.com", 1.0) == pytest.approx(MIN_LIVE_PACE_SECONDS)
    assert effective_pace_seconds("https://api.bainluck.com", 4.2) == pytest.approx(4.2)
    assert effective_pace_seconds("http://127.0.0.1:8000", 0.0) == pytest.approx(0.0)


def test_workflow_contract_valid_and_read_only():
    wf_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "nightly-standing-scores.yml"
    wf = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
    on_block = wf.get("on", wf.get(True))
    assert "schedule" in on_block
    assert "workflow_dispatch" in on_block
    assert wf["permissions"] == {"contents": "read"}
    raw = wf_path.read_text(encoding="utf-8")
    assert "actions/upload-artifact@v4" in raw
    assert "GITHUB_STEP_SUMMARY" in raw
    assert "ci-nightly-standing-scores" in raw


def test_live_game_price_tick_reverified_equal_is_not_flagged_as_disagreement():
    ev_76 = _event_payload(401, sport="basketball_other", status="live", hours_from_now=-1.0, hero=0.76, books=0)
    ev_74 = _event_payload(401, sport="basketball_other", status="live", hours_from_now=-1.0, hero=0.74, books=0)
    calls: dict[str, int] = {"events": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/health":
            return httpx.Response(200, json={"status": "ok", "commit": "e1364d7d"})
        if path == "/api/events":
            qs = parse_qs(
                request.url.query.decode()
                if isinstance(request.url.query, bytes)
                else str(request.url.query)
            )
            if (qs.get("status") or [None])[0] == "scheduled":
                return httpx.Response(200, json={"events": []})
            calls["events"] += 1
            return httpx.Response(200, json={"events": [ev_76 if calls["events"] == 1 else ev_74]})
        if path == "/api/feed":
            return httpx.Response(200, json={"items": []})
        if path.startswith("/api/leagues/"):
            return httpx.Response(200, json={"upcoming_games": []})
        if path == "/api/events/search":
            return httpx.Response(200, json={"results": []})
        if path == "/api/events/401":
            return httpx.Response(200, json=ev_74)
        return httpx.Response(404)

    result = run_standing_scores(
        base_url="http://test",
        pace_seconds=0.0,
        run_date="2026-11-23",
        transport=httpx.MockTransport(_handler),
        now_fn=lambda: NOW,
        sleep_fn=lambda _: None,
    )
    assert result["overall_status"] == "PASS"
    assert result["list_vs_page"]["disagreements_count"] == 0
    assert result["list_vs_page"]["live_tick_drifts_count"] == 1
    assert "- **Live Tick Drifts (re-verified equal):** `1`" in render_markdown_report(result)


def test_live_game_persistent_mismatch_still_fails():
    ev_76 = _event_payload(402, sport="basketball_other", status="live", hours_from_now=-1.0, hero=0.76, books=0)
    ev_74 = _event_payload(402, sport="basketball_other", status="live", hours_from_now=-1.0, hero=0.74, books=0)
    transport = _mock_transport(
        list_events=[ev_76],
        details_by_id={402: ev_74},
    )
    result = run_standing_scores(
        base_url="http://test",
        pace_seconds=0.0,
        run_date="2026-11-23",
        transport=transport,
        now_fn=lambda: NOW,
        sleep_fn=lambda _: None,
    )
    assert result["overall_status"] == "FAIL"
    assert result["list_vs_page"]["disagreements_count"] >= 1
    assert result["list_vs_page"]["live_tick_drifts_count"] == 0
