#!/usr/bin/env python3
"""Nightly standing-scores check (#13514 Workstreams 3.1 & Item 7).

Read-only verification across public API surfaces:
1. Item 4: List-vs-page parity across up to 60 live or <=48h scheduled games
   spanning every represented sport, comparing `/api/events`, `/api/leagues/{sport}`,
   `/api/feed?mode=sports`, and `/api/events/search` cards against `/api/events/{id}`
   for headline percentage, every shared source probability, and sportsbook count.
2. Item 7: Standing census of all scheduled games (including games with no twin)
   whose `betting` sportsbook reading is older than 72 hours.

Writes dated `<YYYY-MM-DD>.json`, `latest.json`, and `<YYYY-MM-DD>.md` artifacts.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.utils.agent_origin import ORIGIN_HEADER, tagged  # noqa: E402

DEFAULT_BASE_URL = "https://api.bainluck.com"
MIN_LIVE_PACE_SECONDS = 3.5
DEFAULT_USER_AGENT = "bainluck-nightly-standing-scores/1.0"
DEFAULT_BL_AGENT = "ci-nightly-standing-scores"


def _parse_iso_utc(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _matchup_label(ev: dict[str, Any]) -> str:
    away = str(ev.get("away_team") or ev.get("away_team_name") or "").strip()
    home = str(ev.get("home_team") or ev.get("home_team_name") or "").strip()
    if away and home:
        return f"{away} @ {home}"
    return str(ev.get("title") or ev.get("name") or f"event-{ev.get('id')}")


def _as_percent(val: Any) -> int | None:
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        return None
    f = float(val)
    if 0.0 <= f <= 1.0:
        return int(round(f * 100.0))
    return int(round(f))


def extract_headline_percent(card: dict[str, Any]) -> int | None:
    """Return rounded integer headline probability [0..100] from any event payload."""
    hero = card.get("hero_probability")
    if isinstance(hero, (int, float)) and not isinstance(hero, bool):
        return _as_percent(hero)
    co = card.get("current_odds")
    if isinstance(co, dict):
        hrp = co.get("home_rendered_percent")
        if isinstance(hrp, int) and not isinstance(hrp, bool):
            return hrp
    hwp = card.get("home_win_probability")
    if isinstance(hwp, (int, float)) and not isinstance(hwp, bool):
        return _as_percent(hwp)
    if isinstance(co, dict):
        hp = co.get("home_probability")
        if isinstance(hp, (int, float)) and not isinstance(hp, bool):
            return _as_percent(hp)
    return None


def extract_source_percents(card: dict[str, Any]) -> dict[str, int]:
    """Return rounded integer percentage per source key from source_mark + wps."""
    out: dict[str, int] = {}
    sm = card.get("source_mark")
    if isinstance(sm, dict):
        for entry in sm.get("sources") or ():
            if not isinstance(entry, dict):
                continue
            key = str(entry.get("key") or "").strip()
            pct = _as_percent(entry.get("probability"))
            if key and pct is not None:
                out[key] = pct
    wps = card.get("win_probability_sources")
    if isinstance(wps, dict):
        for key, entry in wps.items():
            if key == "betting_book_count" or not isinstance(entry, dict):
                continue
            pct = _as_percent(entry.get("value"))
            if key and pct is not None:
                out.setdefault(str(key), pct)
    return out


def extract_bookmaker_count(card: dict[str, Any]) -> int | None:
    """Return sportsbook count when exposed on a card or detail payload."""
    co = card.get("current_odds")
    if isinstance(co, dict):
        bc = co.get("bookmaker_count")
        if isinstance(bc, int) and not isinstance(bc, bool):
            return bc
    hsc = card.get("hero_sportsbook_count")
    if isinstance(hsc, int) and not isinstance(hsc, bool):
        return hsc
    sm = card.get("source_mark")
    if isinstance(sm, dict):
        for entry in sm.get("sources") or ():
            if isinstance(entry, dict) and entry.get("key") == "betting":
                cnt = entry.get("count")
                if isinstance(cnt, int) and not isinstance(cnt, bool):
                    return cnt
    wps = card.get("win_probability_sources")
    if isinstance(wps, dict):
        bbc = wps.get("betting_book_count")
        if isinstance(bbc, dict):
            val = bbc.get("value")
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                return int(round(float(val)))
    b_odds = card.get("bookmaker_odds")
    if isinstance(b_odds, list) and len(b_odds) > 0:
        return len(b_odds)
    if "betting" in extract_source_percents(card) or isinstance(co, dict):
        return None
    if isinstance(card.get("source_mark"), dict) or isinstance(card.get("win_probability_sources"), dict):
        return 0
    return None


def compare_card_against_detail(
    *,
    surface: str,
    card: dict[str, Any],
    detail: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compare one surface event card against its canonical `/api/events/{id}` detail."""
    diffs: list[dict[str, Any]] = []
    event_id = detail.get("id") or card.get("id")
    matchup = _matchup_label(detail)
    sport_key = str(detail.get("sport") or card.get("sport") or "")

    c_head = extract_headline_percent(card)
    d_head = extract_headline_percent(detail)
    if c_head is not None and d_head is not None and c_head != d_head:
        diffs.append(
            {
                "event_id": event_id,
                "sport_key": sport_key,
                "matchup": matchup,
                "surface": surface,
                "field": "headline_percent",
                "surface_value": c_head,
                "detail_value": d_head,
            }
        )

    c_srcs = extract_source_percents(card)
    d_srcs = extract_source_percents(detail)
    for src_key in sorted(set(c_srcs) & set(d_srcs)):
        if c_srcs[src_key] != d_srcs[src_key]:
            diffs.append(
                {
                    "event_id": event_id,
                    "sport_key": sport_key,
                    "matchup": matchup,
                    "surface": surface,
                    "field": f"source.{src_key}",
                    "surface_value": c_srcs[src_key],
                    "detail_value": d_srcs[src_key],
                }
            )
    if isinstance(card.get("source_mark"), dict) and isinstance(detail.get("source_mark"), dict):
        missing_on_card = sorted(set(d_srcs) - set(c_srcs))
        missing_on_detail = sorted(set(c_srcs) - set(d_srcs))
        if missing_on_card or missing_on_detail:
            diffs.append(
                {
                    "event_id": event_id,
                    "sport_key": sport_key,
                    "matchup": matchup,
                    "surface": surface,
                    "field": "source_keys",
                    "surface_value": sorted(c_srcs),
                    "detail_value": sorted(d_srcs),
                }
            )

    c_books = extract_bookmaker_count(card)
    d_books = extract_bookmaker_count(detail)
    if c_books is not None and d_books is not None and c_books != d_books:
        diffs.append(
            {
                "event_id": event_id,
                "sport_key": sport_key,
                "matchup": matchup,
                "surface": surface,
                "field": "bookmaker_count",
                "surface_value": c_books,
                "detail_value": d_books,
            }
        )

    return diffs


def compute_stale_sportsbook_census(
    events: list[dict[str, Any]],
    *,
    now: datetime,
    stale_hours: float = 72.0,
) -> dict[str, Any]:
    """Audit all scheduled games (including untwinned) with betting readings older than threshold."""
    scheduled_total = 0
    scheduled_with_betting = 0
    stale_games: list[dict[str, Any]] = []

    for ev in events:
        if str(ev.get("status") or "").lower() != "scheduled":
            continue
        scheduled_total += 1
        wps = ev.get("win_probability_sources")
        if not isinstance(wps, dict):
            continue
        betting = wps.get("betting")
        if not isinstance(betting, dict):
            continue
        updated_raw = betting.get("updated_at")
        updated_at = _parse_iso_utc(updated_raw)
        if updated_at is None:
            continue
        scheduled_with_betting += 1
        age_hours = (now - updated_at).total_seconds() / 3600.0
        if age_hours > stale_hours:
            stale_games.append(
                {
                    "id": ev.get("id"),
                    "sport_key": ev.get("sport"),
                    "matchup": _matchup_label(ev),
                    "commence_time": ev.get("commence_time"),
                    "betting_updated_at": updated_raw,
                    "age_hours": round(age_hours, 2),
                    "bookmaker_count": extract_bookmaker_count(ev),
                }
            )

    stale_games.sort(key=lambda g: g["age_hours"], reverse=True)
    return {
        "stale_threshold_hours": stale_hours,
        "scheduled_total": scheduled_total,
        "scheduled_with_betting": scheduled_with_betting,
        "stale_over_threshold_count": len(stale_games),
        "stale_games": stale_games,
    }


def select_audit_games(
    events: list[dict[str, Any]],
    *,
    now: datetime,
    max_games: int = 60,
    horizon_hours: float = 48.0,
) -> list[dict[str, Any]]:
    """Select live or <=48h scheduled games round-robin across every represented sport."""
    horizon_end = now + timedelta(hours=horizon_hours)
    recent_start = now - timedelta(hours=6)
    by_sport: dict[str, list[tuple[int, float, dict[str, Any]]]] = defaultdict(list)

    for ev in events:
        status = str(ev.get("status") or "").lower()
        is_live = status in {"live", "in_progress"}
        ct = _parse_iso_utc(ev.get("commence_time"))
        if not is_live:
            if status != "scheduled" or ct is None:
                continue
            if ct < recent_start or ct > horizon_end:
                continue
        sport_key = str(ev.get("sport") or "unknown")
        sort_ts = ct.timestamp() if ct is not None else now.timestamp()
        # Priority 0 for live games, 1 for upcoming scheduled games
        by_sport[sport_key].append((0 if is_live else 1, sort_ts, ev))

    queues: dict[str, list[dict[str, Any]]] = {}
    for sport_key in sorted(by_sport):
        rows = sorted(by_sport[sport_key], key=lambda item: (item[0], item[1], int(item[2].get("id") or 0)))
        queues[sport_key] = [item[2] for item in rows]

    selected: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    sport_order = sorted(
        queues.keys(),
        key=lambda sk: (
            0 if str(queues[sk][0].get("status") or "").lower() in {"live", "in_progress"} else 1,
            -len(queues[sk]),
            sk,
        ),
    )
    while len(selected) < max_games and queues:
        progressed = False
        for sk in list(sport_order):
            q = queues.get(sk)
            if not q:
                continue
            ev = q.pop(0)
            eid = ev.get("id")
            if isinstance(eid, int) and eid in seen_ids:
                continue
            if isinstance(eid, int):
                seen_ids.add(eid)
            selected.append(ev)
            progressed = True
            if not q:
                queues.pop(sk, None)
            if len(selected) >= max_games:
                break
        if not progressed:
            break
    return selected


class PacedClient:
    """Thin paced GET wrapper enforcing minimum spacing between public reads."""

    def __init__(
        self,
        client: httpx.Client,
        *,
        pace_seconds: float,
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.client = client
        self.pace_seconds = max(0.0, float(pace_seconds))
        self._sleep = sleep_fn
        self._monotonic = monotonic_fn
        self._last_request_at: float | None = None
        self.request_count = 0

    def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
        retries: int = 0,
    ) -> tuple[int | None, Any | None, str | None]:
        last_result: tuple[int | None, Any | None, str | None] = (None, None, "no attempts")
        attempts = max(0, int(retries)) + 1
        for _ in range(attempts):
            if self._last_request_at is not None and self.pace_seconds > 0:
                elapsed = self._monotonic() - self._last_request_at
                remaining = self.pace_seconds - elapsed
                if remaining > 0:
                    self._sleep(remaining)
            self._last_request_at = self._monotonic()
            self.request_count += 1
            try:
                full_url = f"{str(self.client.base_url).rstrip('/')}/{path.lstrip('/')}"
                extra: dict[str, Any] = {}
                if timeout is not None:
                    extra["timeout"] = timeout
                resp = self.client.get(path, params=params, headers=tagged(full_url), **extra)
            except Exception as exc:
                last_result = (None, None, f"{type(exc).__name__}: {exc}")
                continue
            if resp.status_code != 200:
                last_result = (resp.status_code, None, f"HTTP {resp.status_code} on {path}")
                continue
            try:
                return resp.status_code, resp.json(), None
            except Exception as exc:
                last_result = (resp.status_code, None, f"JSONDecodeError on {path}: {exc}")
        return last_result


def effective_pace_seconds(base_url: str, requested_pace: float) -> float:
    host = (urlparse(base_url).hostname or "").lower()
    if host in {"127.0.0.1", "localhost", "test", "testserver"}:
        return max(0.0, float(requested_pace))
    return max(MIN_LIVE_PACE_SECONDS, float(requested_pace))


def run_standing_scores(
    *,
    base_url: str = DEFAULT_BASE_URL,
    pace_seconds: float = 3.6,
    max_games: int = 60,
    max_leagues: int = 12,
    max_searches: int = 10,
    stale_hours: float = 72.0,
    run_date: str | None = None,
    transport: httpx.BaseTransport | None = None,
    now_fn: Callable[[], datetime] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    clock_now = (now_fn() if now_fn is not None else datetime.now(timezone.utc)).astimezone(timezone.utc)
    date_str = run_date or clock_now.strftime("%Y-%m-%d")
    pace = effective_pace_seconds(base_url, pace_seconds)
    bl_agent = os.environ.get("BL_AGENT") or DEFAULT_BL_AGENT
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "X-BL-Agent": bl_agent,
        ORIGIN_HEADER: bl_agent,
    }

    http_errors: list[dict[str, Any]] = []
    client_kwargs: dict[str, Any] = {
        "base_url": base_url.rstrip("/"),
        "headers": headers,
        "timeout": 20.0,
    }
    if transport is not None:
        client_kwargs["transport"] = transport

    with httpx.Client(**client_kwargs) as raw_client:
        paced = PacedClient(raw_client, pace_seconds=pace, sleep_fn=sleep_fn)

        # 1. Health / live commit
        st, health_body, err = paced.get_json("/api/health")
        if err:
            http_errors.append({"path": "/api/health", "status": st, "error": err})
            live_commit = None
        else:
            live_commit = (
                health_body.get("commit")
                or health_body.get("git_sha")
                or health_body.get("version")
            ) if isinstance(health_body, dict) else None

        # 2. Live + upcoming window (/api/events?days=3&limit=500) for Item 4 parity
        # Unfiltered /api/events can take >20s when cold, so give it 45s + 1 retry.
        st, ev_body, err = paced.get_json(
            "/api/events",
            params={"days": 3, "limit": 500},
            timeout=45.0,
            retries=1,
        )
        if err or not isinstance(ev_body, dict):
            http_errors.append({"path": "/api/events", "status": st, "error": err or "non-dict payload"})
            all_events: list[dict[str, Any]] = []
        else:
            all_events = [e for e in (ev_body.get("events") or ()) if isinstance(e, dict)]

        # 3. Item 7: Standing >72h sportsbook census (ALL scheduled games, including untwinned)
        scheduled_events: list[dict[str, Any]] = []
        seen_sched_ids: set[int] = set()
        for page_idx in range(4):
            offset = page_idx * 500
            st_s, sched_body, err_s = paced.get_json(
                "/api/events",
                params={"status": "scheduled", "days": 14, "past_days": 0, "limit": 500, "offset": offset},
                timeout=45.0,
                retries=1,
            )
            if err_s or not isinstance(sched_body, dict):
                http_errors.append(
                    {"path": f"/api/events?status=scheduled&offset={offset}", "status": st_s, "error": err_s or "non-dict payload"}
                )
                break
            batch = [e for e in (sched_body.get("events") or ()) if isinstance(e, dict)]
            for row in batch:
                rid = row.get("id")
                if isinstance(rid, int):
                    if rid in seen_sched_ids:
                        continue
                    seen_sched_ids.add(rid)
                scheduled_events.append(row)
            if len(batch) < 500:
                break
        if not scheduled_events and all_events:
            scheduled_events = all_events

        census = compute_stale_sportsbook_census(scheduled_events, now=clock_now, stale_hours=stale_hours)

        # 4. Select up to max_games live / <=48h scheduled games across all represented sports
        combined_by_id: dict[int, dict[str, Any]] = {}
        for ev in [*all_events, *scheduled_events]:
            eid = ev.get("id")
            if isinstance(eid, int) and eid not in combined_by_id:
                combined_by_id[eid] = ev
        selected_games = select_audit_games(list(combined_by_id.values()), now=clock_now, max_games=max_games)
        selected_by_id = {int(g["id"]): g for g in selected_games if isinstance(g.get("id"), int)}
        sports_covered = sorted({str(g.get("sport") or "") for g in selected_games if g.get("sport")})

        surface_cards: dict[tuple[int, str], dict[str, Any]] = {}
        for g in selected_games:
            gid = g.get("id")
            if isinstance(gid, int):
                surface_cards[(gid, "GET /api/events")] = g

        # 5. Sports feed (/api/feed?mode=sports&limit=200)
        st, feed_body, err = paced.get_json("/api/feed", params={"mode": "sports", "limit": 200})
        if err or not isinstance(feed_body, dict):
            http_errors.append({"path": "/api/feed?mode=sports", "status": st, "error": err or "non-dict payload"})
        else:
            for item in feed_body.get("items") or ():
                if isinstance(item, dict) and item.get("type") == "event":
                    data = item.get("data")
                    if isinstance(data, dict) and isinstance(data.get("id"), int):
                        eid = int(data["id"])
                        if eid in selected_by_id:
                            surface_cards[(eid, "GET /api/feed?mode=sports")] = data

        # 6. League pages (/api/leagues/{sport_key})
        for sk in sports_covered[:max_leagues]:
            path = f"/api/leagues/{sk}"
            st, lg_body, err = paced.get_json(path)
            if err or not isinstance(lg_body, dict):
                http_errors.append({"path": path, "status": st, "error": err or "non-dict payload"})
                continue
            for key in ("upcoming_games", "recent_results", "unreported_games", "events", "live_events"):
                rows = lg_body.get(key)
                if isinstance(rows, list):
                    for ev in rows:
                        if isinstance(ev, dict) and isinstance(ev.get("id"), int):
                            eid = int(ev["id"])
                            if eid in selected_by_id:
                                surface_cards[(eid, f"GET {path}")] = ev

        # 7. Search spot-checks across sports (/api/events/search)
        searched_sports: set[str] = set()
        search_query_by_id: dict[int, str] = {}
        for g in selected_games:
            if len(searched_sports) >= max_searches:
                break
            sk = str(g.get("sport") or "")
            if not sk or sk in searched_sports:
                continue
            q = str(g.get("home_team") or g.get("away_team") or "").strip()
            if len(q) < 3:
                continue
            searched_sports.add(sk)
            st, sr_body, err = paced.get_json("/api/events/search", params={"q": q, "per_page": 15})
            if err or not isinstance(sr_body, dict):
                http_errors.append({"path": f"/api/events/search?q={q}", "status": st, "error": err or "non-dict payload"})
                continue
            for ev in sr_body.get("results") or ():
                if isinstance(ev, dict) and isinstance(ev.get("id"), int):
                    eid = int(ev["id"])
                    if eid in selected_by_id:
                        surface_cards[(eid, "GET /api/events/search")] = ev
                        search_query_by_id[eid] = q

        def _refetch_surface_card(
            eid: int,
            surface: str,
            sport_key: str,
        ) -> dict[str, Any] | None:
            if surface == "GET /api/events":
                params = {"days": 3, "limit": 200}
                if sport_key:
                    params["sport"] = sport_key
                _, b, e = paced.get_json("/api/events", params=params)
                if e or not isinstance(b, dict):
                    return None
                for row in b.get("events") or ():
                    if isinstance(row, dict) and row.get("id") == eid:
                        return row
                return None
            if surface == "GET /api/feed?mode=sports":
                _, b, e = paced.get_json("/api/feed", params={"mode": "sports", "limit": 200})
                if e or not isinstance(b, dict):
                    return None
                for item in b.get("items") or ():
                    if isinstance(item, dict) and item.get("type") == "event":
                        data = item.get("data")
                        if isinstance(data, dict) and data.get("id") == eid:
                            return data
                return None
            if surface.startswith("GET /api/leagues/"):
                path = surface[len("GET ") :]
                _, b, e = paced.get_json(path)
                if e or not isinstance(b, dict):
                    return None
                for k in ("upcoming_games", "recent_results", "unreported_games", "events", "live_events"):
                    for row in b.get(k) or ():
                        if isinstance(row, dict) and row.get("id") == eid:
                            return row
                return None
            if surface == "GET /api/events/search":
                q = search_query_by_id.get(eid)
                if not q:
                    return None
                _, b, e = paced.get_json("/api/events/search", params={"q": q, "per_page": 15})
                if e or not isinstance(b, dict):
                    return None
                for row in b.get("results") or ():
                    if isinstance(row, dict) and row.get("id") == eid:
                        return row
                return None
            return None

        # 8. Game detail reads (/api/events/{id}) + comparisons
        disagreements: list[dict[str, Any]] = []
        live_tick_drifts: list[dict[str, Any]] = []
        surface_comparisons = 0
        games_verified = 0
        for eid in [int(g["id"]) for g in selected_games if isinstance(g.get("id"), int)]:
            path = f"/api/events/{eid}"
            st, detail, err = paced.get_json(path)
            if err or not isinstance(detail, dict):
                http_errors.append({"path": path, "status": st, "error": err or "non-dict payload"})
                continue
            games_verified += 1
            is_live_detail = str(detail.get("status") or "").lower() in {"live", "in_progress"}
            detail_sport = str(detail.get("sport") or "")
            for (card_eid, surface), card in sorted(surface_cards.items(), key=lambda x: (x[0][0], x[0][1])):
                if card_eid != eid:
                    continue
                surface_comparisons += 1
                card_diffs = compare_card_against_detail(surface=surface, card=card, detail=detail)
                if not card_diffs:
                    continue
                prob_only = all(
                    d["field"] == "headline_percent" or str(d["field"]).startswith("source.")
                    for d in card_diffs
                )
                if prob_only:
                    # Back-to-back re-read on ALL games (scheduled and live) so
                    # ordinary line movement between list read and page read is not
                    # filed as a disagreement.
                    re_card = _refetch_surface_card(eid, surface, detail_sport or str(card.get("sport") or ""))
                    _, re_detail, re_err = paced.get_json(path)
                    if (
                        re_card is not None
                        and not re_err
                        and isinstance(re_detail, dict)
                    ):
                        re_diffs = compare_card_against_detail(
                            surface=surface, card=re_card, detail=re_detail
                        )
                        if not re_diffs:
                            live_tick_drifts.append(
                                {
                                    "event_id": eid,
                                    "sport_key": detail_sport,
                                    "matchup": _matchup_label(detail),
                                    "surface": surface,
                                    "is_live": is_live_detail,
                                    "initial_diffs": card_diffs,
                                }
                            )
                            continue
                        card_diffs = re_diffs
                disagreements.extend(card_diffs)

    has_real_findings = bool(disagreements) or census["stale_over_threshold_count"] > 0
    if has_real_findings or (games_verified == 0 and not http_errors):
        status = "FAIL"
        parts: list[str] = []
        if disagreements:
            parts.append(f"{len(disagreements)} list-vs-page disagreement(s)")
        if census["stale_over_threshold_count"] > 0:
            parts.append(
                f"{census['stale_over_threshold_count']} scheduled game(s) over "
                f"{census['stale_threshold_hours']:.0f}h stale"
            )
        if games_verified == 0 and not http_errors:
            parts.append("0 games verified")
        if http_errors:
            parts.append(f"{len(http_errors)} read(s) failed")
        status_summary = "; ".join(parts) + f" across {games_verified} game(s) read."
    elif http_errors:
        status = "INCOMPLETE"
        status_summary = (
            f"{len(http_errors)} read(s) failed; no disagreement found in the "
            f"{games_verified} game(s) read."
        )
    else:
        status = "PASS"
        status_summary = (
            f"All {games_verified} game(s) agreed; 0 disagreements and 0 scheduled "
            f"games over {census['stale_threshold_hours']:.0f}h stale."
        )

    return {
        "schema_version": 1,
        "date": date_str,
        "generated_at": clock_now.isoformat(),
        "base_url": base_url.rstrip("/"),
        "live_commit": live_commit,
        "pace_seconds": pace,
        "requests_made": paced.request_count,
        "overall_status": status,
        "status_summary": status_summary,
        "list_vs_page": {
            "games_selected": len(selected_games),
            "games_verified": games_verified,
            "sports_covered": sports_covered,
            "surface_comparisons": surface_comparisons,
            "disagreements_count": len(disagreements),
            "disagreements": disagreements,
            "live_tick_drifts_count": len(live_tick_drifts),
            "live_tick_drifts": live_tick_drifts,
        },
        "stale_sportsbook_census": census,
        "http_errors_count": len(http_errors),
        "http_errors": http_errors,
    }


def render_markdown_report(result: dict[str, Any]) -> str:
    lvp = result["list_vs_page"]
    census = result["stale_sportsbook_census"]
    lines = [
        f"# Nightly Standing Scores — {result['date']}",
        "",
        f"- **Status:** `{result['overall_status']}`",
        *(
            [f"- **Summary:** {result['status_summary']}"]
            if result.get("status_summary")
            else []
        ),
        f"- **Live Commit:** `{result['live_commit'] or 'unknown'}`",
        f"- **Generated (UTC):** `{result['generated_at']}`",
        f"- **Games Checked:** `{lvp['games_verified']}/{lvp['games_selected']}` across `{len(lvp['sports_covered'])}` sport(s)",
        f"- **Surface Comparisons:** `{lvp['surface_comparisons']}`",
        f"- **List vs Page Disagreements:** `{lvp['disagreements_count']}`",
        f"- **Live Tick Drifts (re-verified equal):** `{lvp.get('live_tick_drifts_count', 0)}`",
        (
            f"- **Scheduled > {census['stale_threshold_hours']:.0f}h Sportsbook Census:** "
            f"`{census['stale_over_threshold_count']} / {census['scheduled_total']}` scheduled "
            f"(`{census['scheduled_with_betting']}` with betting timestamp)"
        ),
        f"- **HTTP Errors:** `{result['http_errors_count']}`",
        "",
    ]

    if lvp["disagreements"]:
        lines.extend(
            [
                "## List vs Page Disagreements",
                "",
                "| Event | Sport | Matchup | Surface | Field | Surface Val | Detail Val |",
                "|---|---|---|---|---|---|---|",
            ]
        )
        for d in lvp["disagreements"][:50]:
            lines.append(
                f"| `{d['event_id']}` | `{d['sport_key']}` | {d['matchup']} | `{d['surface']}` | "
                f"`{d['field']}` | `{d['surface_value']}` | `{d['detail_value']}` |"
            )
        lines.append("")

    if census["stale_games"]:
        lines.extend(
            [
                f"## Scheduled Games With Sportsbook Reading > {census['stale_threshold_hours']:.0f}h Old",
                "",
                "| Event | Sport | Matchup | Commence (UTC) | Betting Updated (UTC) | Age (h) | Books |",
                "|---|---|---|---|---|---|---|",
            ]
        )
        for g in census["stale_games"][:50]:
            lines.append(
                f"| `{g['id']}` | `{g['sport_key']}` | {g['matchup']} | `{g['commence_time']}` | "
                f"`{g['betting_updated_at']}` | `{g['age_hours']}` | `{g['bookmaker_count']}` |"
            )
        lines.append("")

    if result["http_errors"]:
        lines.extend(["## HTTP Errors", ""])
        for err in result["http_errors"][:30]:
            lines.append(f"- `{err.get('path')}` (`{err.get('status')}`): {err.get('error')}")
        lines.append("")

    return "\n".join(lines)


def write_artifacts(result: dict[str, Any], out_dir: Path) -> tuple[Path, Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = str(result["date"])
    dated_json = out_dir / f"{date_str}.json"
    latest_json = out_dir / "latest.json"
    dated_md = out_dir / f"{date_str}.md"

    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    dated_json.write_text(payload, encoding="utf-8")
    latest_json.write_text(payload, encoding="utf-8")
    dated_md.write_text(render_markdown_report(result), encoding="utf-8")
    return dated_json, latest_json, dated_md


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nightly list-vs-page parity and >72h sportsbook census")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--pace-seconds", type=float, default=3.6)
    parser.add_argument("--max-games", type=int, default=60)
    parser.add_argument("--max-leagues", type=int, default=12)
    parser.add_argument("--max-searches", type=int, default=10)
    parser.add_argument("--stale-hours", type=float, default=72.0)
    parser.add_argument("--date", default=None, help="Override UTC YYYY-MM-DD date label")
    parser.add_argument("--out-dir", type=Path, default=Path("standing_scores"))
    parser.add_argument("--fail-on-findings", action="store_true")
    args = parser.parse_args(argv)

    result = run_standing_scores(
        base_url=args.base_url,
        pace_seconds=args.pace_seconds,
        max_games=args.max_games,
        max_leagues=args.max_leagues,
        max_searches=args.max_searches,
        stale_hours=args.stale_hours,
        run_date=args.date,
    )
    dated_json, latest_json, dated_md = write_artifacts(result, args.out_dir)
    print(
        f"standing_scores status={result['overall_status']} "
        f"games={result['list_vs_page']['games_verified']}/{result['list_vs_page']['games_selected']} "
        f"disagreements={result['list_vs_page']['disagreements_count']} "
        f"stale={result['stale_sportsbook_census']['stale_over_threshold_count']}/"
        f"{result['stale_sportsbook_census']['scheduled_total']} "
        f"errors={result['http_errors_count']} "
        f"artifacts=[{dated_json}, {latest_json}, {dated_md}]"
    )
    if args.fail_on_findings:
        if result["overall_status"] == "FAIL":
            return 1
        if result["overall_status"] == "INCOMPLETE":
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
