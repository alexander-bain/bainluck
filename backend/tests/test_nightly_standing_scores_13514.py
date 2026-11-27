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
    compare_card_against_detail,
    compute_stale_sportsbook_census,
    effective_pace_seconds,
    extract_copy_age,
    extract_headline_percent,
    format_copy_age,
    main as cli_main,
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
    assert wf["permissions"] == {"contents": "write", "issues": "write"}
    raw = wf_path.read_text(encoding="utf-8")
    assert "actions/upload-artifact@v4" in raw
    assert "GITHUB_STEP_SUMMARY" in raw
    assert "ci-nightly-standing-scores" in raw
    assert "standing-scores-data" in raw
    assert "[skip ci]" in raw
    assert "overall_status == 'FAIL'" in raw
    assert "steps.persist.outputs.consecutive_incomplete == 'true'" in raw
    assert "Nightly check: list and page disagree, or sportsbook prices older than 72 hours" in raw
    assert "github.event_name == 'schedule'" in raw


def test_live_game_price_tick_reverified_equal_is_not_flagged_as_disagreement():
    ev_76 = _event_payload(401, sport="basketball_other", status="live", hours_from_now=-1.0, hero=0.76, books=0)
    ev_74 = _event_payload(401, sport="basketball_other", status="live", hours_from_now=-1.0, hero=0.74, books=0)
    calls: dict[str, int] = {"live": 0}

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
            req_status = (qs.get("status") or [None])[0]
            assert req_status in {"live", "scheduled"}
            if req_status == "scheduled":
                return httpx.Response(200, json={"events": []})
            calls["live"] += 1
            return httpx.Response(200, json={"events": [ev_76 if calls["live"] == 1 else ev_74]})
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


def test_scheduled_game_movement_reverified_equal_is_not_flagged():
    ev_64 = _event_payload(501, sport="basketball_nba", status="scheduled", hours_from_now=4.0, hero=0.64, books=8)
    ev_63 = _event_payload(501, sport="basketball_nba", status="scheduled", hours_from_now=4.0, hero=0.63, books=8)
    calls: dict[str, int] = {"scheduled": 0}

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
            req_status = (qs.get("status") or [None])[0]
            assert req_status in {"live", "scheduled"}
            if req_status == "live":
                return httpx.Response(200, json={"events": []})
            calls["scheduled"] += 1
            return httpx.Response(200, json={"events": [ev_64 if calls["scheduled"] == 1 else ev_63]})
        if path == "/api/feed":
            return httpx.Response(200, json={"items": []})
        if path.startswith("/api/leagues/"):
            return httpx.Response(200, json={"upcoming_games": []})
        if path == "/api/events/search":
            return httpx.Response(200, json={"results": []})
        if path == "/api/events/501":
            return httpx.Response(200, json=ev_63)
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
    assert result["list_vs_page"]["live_tick_drifts"][0]["is_live"] is False


def test_scheduled_game_persistent_mismatch_still_fails():
    ev_64 = _event_payload(502, sport="basketball_nba", status="scheduled", hours_from_now=4.0, hero=0.64, books=8)
    ev_61 = _event_payload(502, sport="basketball_nba", status="scheduled", hours_from_now=4.0, hero=0.61, books=8)
    transport = _mock_transport(list_events=[ev_64], details_by_id={502: ev_61})
    result = run_standing_scores(
        base_url="http://test",
        pace_seconds=0.0,
        run_date="2026-11-23",
        transport=transport,
        now_fn=lambda: NOW,
        sleep_fn=lambda _: None,
    )
    assert result["overall_status"] == "FAIL"
    assert {d["field"] for d in result["list_vs_page"]["disagreements"]} == {
        "headline_percent",
        "source.betting",
    }
    assert result["list_vs_page"]["live_tick_drifts_count"] == 0


def test_read_errors_without_disagreement_are_incomplete_not_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    good1 = _event_payload(601, sport="basketball_nba", home="Celtics", away="Heat", hero=0.62, books=8)
    good2 = _event_payload(602, sport="basketball_nba", home="Knicks", away="Nets", hero=0.55, books=8)
    bad = _event_payload(603, sport="basketball_nba", home="Lakers", away="Suns", hero=0.58, books=8)
    sched_calls = 0

    def _handler(request: httpx.Request) -> httpx.Response:
        nonlocal sched_calls
        path = request.url.path
        if path == "/api/health":
            return httpx.Response(200, json={"status": "ok", "commit": "e1364d7d"})
        if path == "/api/events":
            qs = parse_qs(
                request.url.query.decode()
                if isinstance(request.url.query, bytes)
                else str(request.url.query)
            )
            req_status = (qs.get("status") or [None])[0]
            assert req_status in {"live", "scheduled"}
            if req_status == "live":
                return httpx.Response(200, json={"events": []})
            sched_calls += 1
            if sched_calls == 1:
                raise httpx.ReadTimeout("timed out once")
            return httpx.Response(200, json={"events": [good1, good2, bad]})
        if path == "/api/feed":
            return httpx.Response(200, json={"items": []})
        if path.startswith("/api/leagues/"):
            return httpx.Response(503, json={"detail": "busy"})
        if path == "/api/events/search":
            return httpx.Response(200, json={"results": []})
        if path == "/api/events/601":
            return httpx.Response(200, json=good1)
        if path == "/api/events/602":
            return httpx.Response(200, json=good2)
        if path == "/api/events/603":
            return httpx.Response(502, json={"detail": "bad gateway"})
        return httpx.Response(404)

    result = run_standing_scores(
        base_url="http://test",
        pace_seconds=0.0,
        run_date="2026-11-23",
        transport=httpx.MockTransport(_handler),
        now_fn=lambda: NOW,
        sleep_fn=lambda _: None,
    )
    assert sched_calls == 2  # initial scheduled timeout retried once and recovered
    assert result["overall_status"] == "INCOMPLETE"
    assert result["list_vs_page"]["games_verified"] == 2
    assert result["http_errors_count"] == 2  # league + 603; transient /api/events timeout recovered
    assert "2 read(s) failed; no disagreement found in the 2 game(s) read." == result["status_summary"]
    assert "no disagreement found in the 2 game(s) read" in render_markdown_report(result)

    monkeypatch.setattr("scripts.nightly_standing_scores.run_standing_scores", lambda **_: result)
    rc = cli_main(["--date", "2026-11-23", "--out-dir", str(tmp_path), "--fail-on-findings"])
    assert rc == 2


def test_failed_reread_is_unconfirmed_incomplete_never_disagreement():
    ev_64 = _event_payload(702, sport="basketball_nba", status="scheduled", hours_from_now=4.0, hero=0.64, books=8)
    ev_63 = _event_payload(702, sport="basketball_nba", status="scheduled", hours_from_now=4.0, hero=0.63, books=8)
    sched_calls = 0
    seen_queries: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        nonlocal sched_calls
        path = request.url.path
        if path == "/api/health":
            return httpx.Response(200, json={"status": "ok", "commit": "e1364d7d"})
        if path == "/api/events":
            q = request.url.query.decode() if isinstance(request.url.query, bytes) else str(request.url.query)
            seen_queries.append(q)
            qs = parse_qs(q)
            req_status = (qs.get("status") or [None])[0]
            assert req_status in {"live", "scheduled"}
            if req_status == "live":
                return httpx.Response(200, json={"events": []})
            sched_calls += 1
            if sched_calls == 1:
                return httpx.Response(200, json={"events": [ev_64]})
            return httpx.Response(503, json={"detail": "busy"})
        if path == "/api/feed":
            return httpx.Response(200, json={"items": []})
        if path.startswith("/api/leagues/"):
            return httpx.Response(200, json={"upcoming_games": []})
        if path == "/api/events/search":
            return httpx.Response(200, json={"results": []})
        if path == "/api/events/702":
            return httpx.Response(200, json=ev_63)
        return httpx.Response(404)

    result = run_standing_scores(
        base_url="http://test",
        pace_seconds=0.0,
        run_date="2026-11-23",
        transport=httpx.MockTransport(_handler),
        now_fn=lambda: NOW,
        sleep_fn=lambda _: None,
    )
    assert all("status=live" in q or "status=scheduled" in q for q in seen_queries)
    assert result["overall_status"] == "INCOMPLETE"
    assert result["list_vs_page"]["disagreements_count"] == 0
    assert result["list_vs_page"]["unconfirmed_disagreements_count"] == 1
    assert result["list_vs_page"]["unconfirmed_disagreements"][0]["reason"] == "list_reread_failed"
    assert "1 re-read(s) unconfirmed" in result["status_summary"]
    assert "Unconfirmed Initial Diffs (Re-Read Failed)" in render_markdown_report(result)


def test_read_errors_with_real_disagreement_remain_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    card = _event_payload(701, sport="basketball_nba", hero=0.64, books=8)
    detail = _event_payload(701, sport="basketball_nba", hero=0.69, books=10)

    def _handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/health":
            return httpx.Response(200, json={"status": "ok"})
        if path == "/api/events":
            qs = parse_qs(
                request.url.query.decode()
                if isinstance(request.url.query, bytes)
                else str(request.url.query)
            )
            req_status = (qs.get("status") or [None])[0]
            assert req_status in {"live", "scheduled"}
            return httpx.Response(200, json={"events": [card] if req_status == "scheduled" else []})
        if path == "/api/feed":
            return httpx.Response(503)
        if path.startswith("/api/leagues/"):
            return httpx.Response(200, json={"upcoming_games": []})
        if path == "/api/events/search":
            return httpx.Response(200, json={"results": []})
        if path == "/api/events/701":
            return httpx.Response(200, json=detail)
        return httpx.Response(404)

    result = run_standing_scores(
        base_url="http://test",
        pace_seconds=0.0,
        run_date="2026-11-23",
        transport=httpx.MockTransport(_handler),
        now_fn=lambda: NOW,
        sleep_fn=lambda _: None,
    )
    assert result["overall_status"] == "FAIL"
    assert result["http_errors_count"] == 1
    assert result["list_vs_page"]["disagreements_count"] >= 1
    monkeypatch.setattr("scripts.nightly_standing_scores.run_standing_scores", lambda **_: result)
    assert cli_main(["--date", "2026-11-23", "--out-dir", str(tmp_path), "--fail-on-findings"]) == 1


def test_extract_and_format_copy_age_across_surfaces():
    detail_cached = {
        "state_read_fresh": False,
        "state_read_not_after": (NOW - timedelta(seconds=42)).isoformat(),
        "hero_probability_observed_at": (NOW - timedelta(seconds=126)).isoformat(),
    }
    age_detail = extract_copy_age(detail_cached, response_meta={"fetched_at": NOW.isoformat()})
    assert age_detail["copy_age_seconds"] == pytest.approx(42.0)
    assert age_detail["copy_age_source"] == "state_read"
    assert age_detail["cache_status"] == "cached"
    assert age_detail["reading_age_seconds"] == pytest.approx(126.0)
    assert age_detail["summary"] == "copy 42s (cached), read 2.1m"

    feed_card = {
        "hero_probability_observed_at": (NOW - timedelta(seconds=90)).isoformat(),
    }
    age_feed = extract_copy_age(
        feed_card,
        response_meta={
            "fetched_at": NOW.isoformat(),
            "cache_header": "hit",
            "envelope_built_at": (NOW - timedelta(seconds=180)).isoformat(),
        },
    )
    assert age_feed["copy_age_seconds"] == pytest.approx(180.0)
    assert age_feed["copy_age_source"] == "envelope_built_at"
    assert age_feed["cache_status"] == "hit"
    assert age_feed["summary"] == "copy 3.0m (hit), read 90s"

    search_card = _event_payload(801, betting_age_hours=3.0)
    age_search = extract_copy_age(
        search_card,
        response_meta={"fetched_at": NOW.isoformat(), "cache_header": "hit", "age_header_seconds": 45.0},
    )
    assert age_search["copy_age_seconds"] == pytest.approx(45.0)
    assert age_search["copy_age_source"] == "http_age_header"
    assert age_search["summary"] == "copy 45s (hit), read 3.0h"

    list_card = _event_payload(802, betting_age_hours=0.25)
    age_list = extract_copy_age(list_card, response_meta={"fetched_at": NOW.isoformat()})
    assert age_list["copy_age_seconds"] is None
    assert age_list["reading_age_seconds"] == pytest.approx(900.0)
    assert format_copy_age(age_list) == "copy ?, read 15.0m"


def test_disagreements_include_list_and_page_copy_age_in_json_and_markdown():
    feed_card = _event_payload(901, sport="soccer_italy_serie_a", home="Cremonese", away="Avellino", hero=0.45, books=5, betting_age_hours=0.5)
    detail = _event_payload(901, sport="soccer_italy_serie_a", home="Cremonese", away="Avellino", hero=0.52, books=0, betting_age_hours=0.05)
    detail["state_read_fresh"] = True
    detail["state_read_not_after"] = NOW.isoformat()
    detail["hero_probability_observed_at"] = (NOW - timedelta(seconds=180)).isoformat()

    def _handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/health":
            return httpx.Response(200, json={"status": "ok", "commit": "deadbeef"})
        if path == "/api/events":
            qs = parse_qs(request.url.query.decode() if isinstance(request.url.query, bytes) else str(request.url.query))
            req_status = (qs.get("status") or [None])[0]
            return httpx.Response(200, json={"events": [feed_card] if req_status == "scheduled" else []})
        if path == "/api/feed":
            return httpx.Response(
                200,
                headers={"X-Feed-Cache": "hit"},
                json={
                    "cache": {"built_at": (NOW - timedelta(seconds=240)).timestamp()},
                    "items": [{"type": "event", "data": feed_card}],
                },
            )
        if path.startswith("/api/leagues/"):
            return httpx.Response(200, json={"upcoming_games": []})
        if path == "/api/events/search":
            return httpx.Response(200, json={"results": []})
        if path == "/api/events/901":
            return httpx.Response(200, json=detail)
        return httpx.Response(404)

    result = run_standing_scores(
        base_url="http://test",
        pace_seconds=0.0,
        run_date="2026-11-26",
        transport=httpx.MockTransport(_handler),
        now_fn=lambda: NOW,
        sleep_fn=lambda _: None,
    )
    assert result["overall_status"] == "FAIL"
    diffs = result["list_vs_page"]["disagreements"]
    feed_books = [d for d in diffs if d["surface"] == "GET /api/feed?mode=sports" and d["field"] == "bookmaker_count"]
    assert len(feed_books) == 1
    row = feed_books[0]
    assert row["surface_copy_age"]["summary"] == "copy 4.0m (hit), read 30.0m"
    assert row["detail_copy_age"]["summary"] == "copy 0s (fresh), read 3.0m"
    assert row["fetch_gap_seconds"] == pytest.approx(0.0)

    md = render_markdown_report(result)
    assert "| Event | Sport | Matchup | Surface | Field | Surface Val | Detail Val | List Copy Age | Page Copy Age |" in md
    assert "`copy 4.0m (hit), read 30.0m`" in md
    assert "`copy 0s (fresh), read 3.0m (gap 0s)`" in md


@pytest.mark.parametrize(
    ("home_prob", "away_prob", "expected_pct"),
    [
        (0.765, 0.235, 77),
        (0.395, 0.605, 39),
        (0.605, 0.395, 61),
    ],
)
def test_extract_headline_percent_matches_rendered_duel_percents_on_half_boundaries(
    home_prob: float,
    away_prob: float,
    expected_pct: int,
):
    league_card = {
        "id": 950,
        "sport": "basketball_other",
        "home_team": "Qatar",
        "away_team": "South Korea",
        "home_win_probability": home_prob,
        "current_odds": {
            "home_probability": home_prob,
            "away_probability": away_prob,
            "home_rendered_percent": expected_pct,
            "bookmaker_count": 0,
        },
        "source_mark": {
            "state": "single",
            "sources": [{"key": "polymarket", "name": "Polymarket", "probability": home_prob}],
        },
    }
    list_events_card = {
        "id": 950,
        "sport": "basketball_other",
        "home_team": "Qatar",
        "away_team": "South Korea",
        "hero_probability": home_prob,
        "current_odds": {
            "home_probability": home_prob,
            "away_probability": away_prob,
            "bookmaker_count": 0,
        },
        "source_mark": {
            "state": "single",
            "sources": [{"key": "polymarket", "name": "Polymarket", "probability": home_prob}],
        },
    }
    detail = {
        "id": 950,
        "sport": "basketball_other",
        "home_team": "Qatar",
        "away_team": "South Korea",
        "hero_probability": home_prob,
        "current_odds": {
            "home_probability": home_prob,
            "away_probability": away_prob,
            "home_rendered_percent": expected_pct,
            "bookmaker_count": 0,
        },
        "source_mark": {
            "state": "single",
            "sources": [{"key": "polymarket", "name": "Polymarket", "probability": home_prob}],
        },
    }
    assert extract_headline_percent(league_card) == expected_pct
    assert extract_headline_percent(list_events_card) == expected_pct
    assert extract_headline_percent(detail) == expected_pct
    assert (
        compare_card_against_detail(
            surface="GET /api/leagues/basketball_other",
            card=league_card,
            detail=detail,
        )
        == []
    )
    assert (
        compare_card_against_detail(
            surface="GET /api/events?status=scheduled",
            card=list_events_card,
            detail=detail,
        )
        == []
    )


def test_live_source_keys_transition_reverified_equal_is_not_flagged():
    ev_both = _event_payload(
        951,
        sport="esports",
        home="Any Questions Gaming",
        away="Unsettled Resentment",
        status="live",
        hours_from_now=-1.0,
        hero=0.0075,
        books=0,
        betting_age_hours=None,
        extra_sources=[
            {"key": "kalshi", "name": "Kalshi", "probability": 0.01},
            {"key": "polymarket", "name": "Polymarket", "probability": 0.004},
        ],
    )
    ev_both["source_mark"]["sources"] = [
        {"key": "kalshi", "name": "Kalshi", "probability": 0.01},
        {"key": "polymarket", "name": "Polymarket", "probability": 0.004},
    ]
    ev_both["win_probability_sources"] = {
        "kalshi": {"value": 0.01, "updated_at": NOW.isoformat()},
        "polymarket": {"value": 0.004, "updated_at": NOW.isoformat()},
    }
    ev_poly_only = _event_payload(
        951,
        sport="esports",
        home="Any Questions Gaming",
        away="Unsettled Resentment",
        status="live",
        hours_from_now=-1.0,
        hero=0.004,
        books=0,
        betting_age_hours=None,
        extra_sources=[
            {"key": "polymarket", "name": "Polymarket", "probability": 0.004},
        ],
    )
    ev_poly_only["source_mark"]["sources"] = [
        {"key": "polymarket", "name": "Polymarket", "probability": 0.004},
    ]
    ev_poly_only["win_probability_sources"] = {
        "polymarket": {"value": 0.004, "updated_at": NOW.isoformat()},
    }
    calls: dict[str, int] = {"live": 0}

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
            req_status = (qs.get("status") or [None])[0]
            assert req_status in {"live", "scheduled"}
            if req_status == "scheduled":
                return httpx.Response(200, json={"events": []})
            calls["live"] += 1
            return httpx.Response(200, json={"events": [ev_both if calls["live"] == 1 else ev_poly_only]})
        if path == "/api/feed":
            return httpx.Response(200, json={"items": []})
        if path.startswith("/api/leagues/"):
            return httpx.Response(200, json={"upcoming_games": []})
        if path == "/api/events/search":
            return httpx.Response(200, json={"results": []})
        if path == "/api/events/951":
            return httpx.Response(200, json=ev_poly_only)
        return httpx.Response(404)

    result = run_standing_scores(
        base_url="http://test",
        pace_seconds=0.0,
        run_date="2026-11-26",
        transport=httpx.MockTransport(_handler),
        now_fn=lambda: NOW,
        sleep_fn=lambda _: None,
    )
    assert calls["live"] == 2
    assert result["overall_status"] == "PASS"
    assert result["list_vs_page"]["disagreements_count"] == 0
    assert result["list_vs_page"]["live_tick_drifts_count"] == 1


def test_persistent_source_keys_mismatch_still_fails_after_reread():
    card_list = _event_payload(
        952,
        sport="soccer_epl",
        home="Arsenal",
        away="Chelsea",
        hero=0.60,
        books=7,
        extra_sources=[{"key": "polymarket", "name": "Polymarket", "probability": 0.60}],
    )
    detail_missing_books = _event_payload(
        952,
        sport="soccer_epl",
        home="Arsenal",
        away="Chelsea",
        hero=0.60,
        books=0,
        betting_age_hours=None,
        extra_sources=[{"key": "polymarket", "name": "Polymarket", "probability": 0.60}],
    )
    detail_missing_books["source_mark"]["sources"] = [
        {"key": "polymarket", "name": "Polymarket", "probability": 0.60},
    ]
    transport = _mock_transport(
        list_events=[card_list],
        details_by_id={952: detail_missing_books},
    )
    result = run_standing_scores(
        base_url="http://test",
        pace_seconds=0.0,
        run_date="2026-11-26",
        transport=transport,
        now_fn=lambda: NOW,
        sleep_fn=lambda _: None,
    )
    assert result["overall_status"] == "FAIL"
    assert result["list_vs_page"]["live_tick_drifts_count"] == 0
    fields = {d["field"] for d in result["list_vs_page"]["disagreements"]}
    assert "source_keys" in fields
    assert "bookmaker_count" in fields


def _list_transition_handler(
    *,
    eid: int,
    initial_card: dict,
    detail_card: dict,
    reread_live_events: list[dict] | None = None,
    reread_live_status: int = 200,
    completed_events: list[dict] | None = None,
    scheduled_reread_events: list[dict] | None = None,
) -> httpx.MockTransport:
    calls = {"live": 0, "scheduled": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/health":
            return httpx.Response(200, json={"status": "ok", "commit": "c991cfff"})
        if path == "/api/events":
            q = request.url.query.decode() if isinstance(request.url.query, bytes) else str(request.url.query)
            qs = parse_qs(q)
            req_status = (qs.get("status") or [None])[0]
            if req_status == "live":
                calls["live"] += 1
                if calls["live"] == 1:
                    return httpx.Response(
                        200,
                        json={"events": [initial_card] if str(initial_card.get("status") or "").lower() == "live" else []},
                    )
                if reread_live_status != 200:
                    return httpx.Response(reread_live_status, json={"detail": "busy"})
                return httpx.Response(200, json={"events": reread_live_events or []})
            if req_status == "scheduled":
                calls["scheduled"] += 1
                if calls["scheduled"] == 1:
                    return httpx.Response(
                        200,
                        json={
                            "events": [initial_card]
                            if str(initial_card.get("status") or "").lower() == "scheduled"
                            else []
                        },
                    )
                return httpx.Response(200, json={"events": scheduled_reread_events or []})
            if req_status == "completed":
                return httpx.Response(200, json={"events": completed_events or []})
            return httpx.Response(404)
        if path == "/api/feed":
            return httpx.Response(200, json={"items": []})
        if path.startswith("/api/leagues/"):
            return httpx.Response(200, json={"upcoming_games": []})
        if path == "/api/events/search":
            return httpx.Response(200, json={"results": []})
        if path == f"/api/events/{eid}":
            return httpx.Response(200, json=detail_card)
        return httpx.Response(404)

    return httpx.MockTransport(_handler)


def test_live_game_transitioned_to_suspended_off_live_list_is_drift_not_incomplete():
    live_card = _event_payload(
        960,
        sport="tennis_atp",
        home="Donald",
        away="Rincon",
        status="live",
        hours_from_now=-1.5,
        hero=0.96,
        books=0,
        betting_age_hours=None,
        extra_sources=[
            {"key": "kalshi", "name": "Kalshi", "probability": 0.96},
            {"key": "polymarket", "name": "Polymarket", "probability": 0.96},
        ],
    )
    suspended_detail = _event_payload(
        960,
        sport="tennis_atp",
        home="Donald",
        away="Rincon",
        status="suspended",
        hours_from_now=-1.5,
        hero=1.0,
        books=0,
        betting_age_hours=None,
        extra_sources=[
            {"key": "polymarket", "name": "Polymarket", "probability": 1.0},
        ],
    )
    suspended_detail["source_mark"]["sources"] = [
        {"key": "polymarket", "name": "Polymarket", "probability": 1.0},
    ]
    transport = _list_transition_handler(
        eid=960,
        initial_card=live_card,
        detail_card=suspended_detail,
        reread_live_events=[],
    )
    result = run_standing_scores(
        base_url="http://test",
        pace_seconds=0.0,
        run_date="2026-11-27",
        transport=transport,
        now_fn=lambda: NOW,
        sleep_fn=lambda _: None,
    )
    assert result["overall_status"] == "PASS"
    assert result["list_vs_page"]["disagreements_count"] == 0
    assert result["list_vs_page"]["unconfirmed_disagreements_count"] == 0
    assert result["list_vs_page"]["live_tick_drifts_count"] == 1
    drift = result["list_vs_page"]["live_tick_drifts"][0]
    assert drift["reason"] == "status_transitioned_off_surface:live->suspended"
    assert drift["detail_status"] == "suspended"


def test_live_game_transitioned_to_completed_still_fails_when_completed_list_disagrees():
    live_card = _event_payload(961, sport="tennis_atp", status="live", hours_from_now=-2.0, hero=0.90, books=0)
    completed_detail = _event_payload(961, sport="tennis_atp", status="completed", hours_from_now=-2.0, hero=1.00, books=0)
    completed_list_card = _event_payload(961, sport="tennis_atp", status="completed", hours_from_now=-2.0, hero=0.95, books=0)
    transport = _list_transition_handler(
        eid=961,
        initial_card=live_card,
        detail_card=completed_detail,
        reread_live_events=[],
        completed_events=[completed_list_card],
    )
    result = run_standing_scores(
        base_url="http://test",
        pace_seconds=0.0,
        run_date="2026-11-27",
        transport=transport,
        now_fn=lambda: NOW,
        sleep_fn=lambda _: None,
    )
    assert result["overall_status"] == "FAIL"
    assert result["list_vs_page"]["unconfirmed_disagreements_count"] == 0
    assert result["list_vs_page"]["live_tick_drifts_count"] == 0
    assert any(
        d["surface"] == "GET /api/events?status=completed" and d["field"] == "headline_percent"
        for d in result["list_vs_page"]["disagreements"]
    )


def test_live_game_transitioned_to_completed_and_agreed_on_completed_list_passes_as_drift():
    live_card = _event_payload(962, sport="tennis_atp", status="live", hours_from_now=-2.0, hero=0.90, books=0)
    completed_card = _event_payload(962, sport="tennis_atp", status="completed", hours_from_now=-2.0, hero=1.00, books=0)
    transport = _list_transition_handler(
        eid=962,
        initial_card=live_card,
        detail_card=completed_card,
        reread_live_events=[],
        completed_events=[completed_card],
    )
    result = run_standing_scores(
        base_url="http://test",
        pace_seconds=0.0,
        run_date="2026-11-27",
        transport=transport,
        now_fn=lambda: NOW,
        sleep_fn=lambda _: None,
    )
    assert result["overall_status"] == "PASS"
    assert result["list_vs_page"]["disagreements_count"] == 0
    assert result["list_vs_page"]["unconfirmed_disagreements_count"] == 0
    assert result["list_vs_page"]["live_tick_drifts_count"] == 1
    assert (
        result["list_vs_page"]["live_tick_drifts"][0]["reason"]
        == "status_transitioned_off_surface:live->completed"
    )


@pytest.mark.parametrize("reread_status_code", [200, 503])
def test_still_live_game_missing_from_live_reread_or_http_error_remains_unconfirmed(reread_status_code: int):
    live_card = _event_payload(963, sport="tennis_atp", status="live", hours_from_now=-1.0, hero=0.60, books=0)
    still_live_detail = _event_payload(963, sport="tennis_atp", status="live", hours_from_now=-1.0, hero=0.65, books=0)
    transport = _list_transition_handler(
        eid=963,
        initial_card=live_card,
        detail_card=still_live_detail,
        reread_live_events=[],
        reread_live_status=reread_status_code,
    )
    result = run_standing_scores(
        base_url="http://test",
        pace_seconds=0.0,
        run_date="2026-11-27",
        transport=transport,
        now_fn=lambda: NOW,
        sleep_fn=lambda _: None,
    )
    assert result["overall_status"] == "INCOMPLETE"
    assert result["list_vs_page"]["live_tick_drifts_count"] == 0
    assert result["list_vs_page"]["unconfirmed_disagreements_count"] == 1
    assert result["list_vs_page"]["unconfirmed_disagreements"][0]["reason"] == "list_reread_failed"


def test_scheduled_game_transitioned_to_live_off_scheduled_list_is_drift():
    sched_card = _event_payload(964, sport="basketball_nba", status="scheduled", hours_from_now=0.1, hero=0.55, books=8)
    live_detail = _event_payload(964, sport="basketball_nba", status="live", hours_from_now=0.0, hero=0.58, books=8)
    transport = _list_transition_handler(
        eid=964,
        initial_card=sched_card,
        detail_card=live_detail,
        scheduled_reread_events=[],
    )
    result = run_standing_scores(
        base_url="http://test",
        pace_seconds=0.0,
        run_date="2026-11-27",
        transport=transport,
        now_fn=lambda: NOW,
        sleep_fn=lambda _: None,
    )
    assert result["overall_status"] == "PASS"
    assert result["list_vs_page"]["disagreements_count"] == 0
    assert result["list_vs_page"]["unconfirmed_disagreements_count"] == 0
    assert result["list_vs_page"]["live_tick_drifts_count"] == 1
    assert (
        result["list_vs_page"]["live_tick_drifts"][0]["reason"]
        == "status_transitioned_off_surface:scheduled->live"
    )
