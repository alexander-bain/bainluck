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
from email.utils import parsedate_to_datetime
import json
import math
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
from app.utils.graded_card import rendered_duel_percents, rendered_percent  # noqa: E402

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


def _parse_timestamp_utc(raw: Any) -> datetime | None:
    """Parse an ISO timestamp string or numeric Unix epoch (seconds) into UTC datetime."""
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        val = float(raw)
        if val > 0:
            try:
                return datetime.fromtimestamp(val, tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                return None
        return None
    return _parse_iso_utc(raw)


def _parse_http_date_utc(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        dt = parsedate_to_datetime(raw.strip())
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_age_duration(seconds: float | None) -> str:
    """Compact human duration for Markdown copy/reading age columns."""
    if seconds is None:
        return "?"
    s = max(0.0, float(seconds))
    if s < 120.0:
        return f"{int(round(s))}s"
    if s < 7200.0:
        return f"{s / 60.0:.1f}m"
    return f"{s / 3600.0:.1f}h"


def _extract_envelope_meta(body: Any, response_meta: dict[str, Any] | None) -> dict[str, Any]:
    """Combine HTTP response metadata with any cache/build timestamp on the enclosing body."""
    merged = dict(response_meta or {})
    if not isinstance(body, dict):
        return merged
    candidates: list[Any] = []
    cache_block = body.get("cache")
    if isinstance(cache_block, dict):
        candidates.extend(
            cache_block.get(k) for k in ("built_at", "cached_at", "generated_at", "computed_at")
        )
    candidates.extend(body.get(k) for k in ("built_at", "cached_at", "generated_at", "computed_at"))
    for cand in candidates:
        parsed = _parse_timestamp_utc(cand)
        if parsed is not None:
            merged["envelope_built_at"] = parsed.isoformat()
            break
    if not merged.get("cache_header") and isinstance(cache_block, dict):
        hit_status = cache_block.get("status")
        if isinstance(hit_status, str) and hit_status.strip():
            merged["cache_header"] = hit_status.strip()
    return merged


def _newest_reading_timestamp(card: dict[str, Any]) -> tuple[datetime | None, str | None]:
    """Return ``(timestamp, source_field)`` for the payload's newest price reading clock."""
    hero_obs = _parse_iso_utc(card.get("hero_probability_observed_at"))
    if hero_obs is not None:
        return hero_obs, "hero_probability_observed_at"

    newest: datetime | None = None
    sm = card.get("source_mark")
    if isinstance(sm, dict):
        for entry in sm.get("sources") or ():
            if not isinstance(entry, dict):
                continue
            obs = _parse_iso_utc(entry.get("observed_at")) or _parse_iso_utc(entry.get("updated_at"))
            if obs is not None and (newest is None or obs > newest):
                newest = obs
    wps = card.get("win_probability_sources")
    if isinstance(wps, dict):
        for key, entry in wps.items():
            if key == "betting_book_count" or not isinstance(entry, dict):
                continue
            obs = _parse_iso_utc(entry.get("updated_at")) or _parse_iso_utc(entry.get("observed_at"))
            if obs is not None and (newest is None or obs > newest):
                newest = obs
    if newest is not None:
        return newest, "newest_source_updated_at"
    return None, None


def extract_copy_age(
    payload: dict[str, Any],
    *,
    response_meta: dict[str, Any] | None = None,
    fallback_now: datetime | None = None,
) -> dict[str, Any]:
    """Extract both cache/build copy age and underlying probability reading age."""
    meta = response_meta or {}
    server_date = _parse_iso_utc(meta.get("server_date"))
    fetched_at = _parse_iso_utc(meta.get("fetched_at"))
    ref_now = server_date or fetched_at or fallback_now
    if ref_now is not None and ref_now.tzinfo is None:
        ref_now = ref_now.replace(tzinfo=timezone.utc)

    cache_header = str(meta.get("cache_header") or "").strip() or None
    state_fresh = payload.get("state_read_fresh")
    state_not_after = _parse_iso_utc(payload.get("state_read_not_after")) or _parse_iso_utc(
        payload.get("state_read_not_before")
    )
    envelope_built = _parse_timestamp_utc(meta.get("envelope_built_at"))
    card_built = None
    for k in ("built_at", "cached_at", "generated_at", "computed_at"):
        card_built = _parse_timestamp_utc(payload.get(k))
        if card_built is not None:
            break
    age_header = meta.get("age_header_seconds")

    copy_age_s: float | None = None
    copy_age_source: str | None = None
    cache_status: str | None = None
    if isinstance(state_fresh, bool):
        cache_status = "fresh" if state_fresh else "cached"
    elif cache_header:
        cache_status = cache_header

    if state_not_after is not None and ref_now is not None:
        copy_age_s = round(max(0.0, (ref_now - state_not_after).total_seconds()), 1)
        copy_age_source = "state_read"
    elif envelope_built is not None and ref_now is not None:
        copy_age_s = round(max(0.0, (ref_now - envelope_built).total_seconds()), 1)
        copy_age_source = "envelope_built_at"
    elif card_built is not None and ref_now is not None:
        copy_age_s = round(max(0.0, (ref_now - card_built).total_seconds()), 1)
        copy_age_source = "payload_built_at"
    elif isinstance(age_header, (int, float)) and not isinstance(age_header, bool):
        copy_age_s = round(max(0.0, float(age_header)), 1)
        copy_age_source = "http_age_header"

    reading_dt, reading_src = _newest_reading_timestamp(payload)
    reading_age_s: float | None = None
    if reading_dt is not None and ref_now is not None:
        reading_age_s = round(max(0.0, (ref_now - reading_dt).total_seconds()), 1)

    info: dict[str, Any] = {
        "copy_age_seconds": copy_age_s,
        "copy_age_source": copy_age_source,
        "cache_status": cache_status,
        "reading_age_seconds": reading_age_s,
        "reading_age_source": reading_src,
        "reading_observed_at": reading_dt.isoformat() if reading_dt is not None else None,
        "fetched_at": fetched_at.isoformat() if fetched_at is not None else None,
    }
    info["summary"] = format_copy_age(info)
    return info


def format_copy_age(age_info: dict[str, Any] | None) -> str:
    """Format a compact list/page copy age string for the nightly report."""
    if not isinstance(age_info, dict):
        return "copy ?, read ?"
    copy_s = age_info.get("copy_age_seconds")
    cache_status = age_info.get("cache_status")
    reading_s = age_info.get("reading_age_seconds")

    if copy_s is not None:
        copy_part = f"copy {format_age_duration(copy_s)}"
        if cache_status:
            copy_part += f" ({cache_status})"
    elif cache_status:
        copy_part = f"copy ? ({cache_status})"
    else:
        copy_part = "copy ?"

    read_part = f"read {format_age_duration(reading_s)}"
    return f"{copy_part}, {read_part}"


def _fetch_gap_seconds(card_age: dict[str, Any] | None, detail_age: dict[str, Any] | None) -> float | None:
    if not isinstance(card_age, dict) or not isinstance(detail_age, dict):
        return None
    t_card = _parse_iso_utc(card_age.get("fetched_at"))
    t_detail = _parse_iso_utc(detail_age.get("fetched_at"))
    if t_card is None or t_detail is None:
        return None
    return round(abs((t_detail - t_card).total_seconds()), 1)


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
    if not math.isfinite(f):
        return None
    if 0.0 <= f <= 1.0:
        return rendered_percent(f)
    return int(math.floor(f + 0.5))


def _first_finite_number(*vals: Any) -> float | None:
    for v in vals:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        f = float(v)
        if math.isfinite(f):
            return f
    return None


def extract_headline_percent(card: dict[str, Any]) -> int | None:
    """Return rendered integer headline probability [0..100] from any event payload."""
    co = card.get("current_odds")
    if isinstance(co, dict):
        hrp = co.get("home_rendered_percent")
        if isinstance(hrp, int) and not isinstance(hrp, bool):
            return hrp
    home_prob = _first_finite_number(
        card.get("hero_probability"),
        card.get("home_win_probability"),
        co.get("home_probability") if isinstance(co, dict) else None,
    )
    if home_prob is None:
        return None
    away_prob = _first_finite_number(
        card.get("hero_probability_away"),
        card.get("away_win_probability"),
        co.get("away_probability") if isinstance(co, dict) else None,
    )
    if (
        away_prob is not None
        and 0.0 <= home_prob <= 1.0
        and 0.0 <= away_prob <= 1.0
    ):
        _, home_pct = rendered_duel_percents(away_prob, home_prob)
        if home_pct is not None:
            return home_pct
    return _as_percent(home_prob)


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
    card_age: dict[str, Any] | None = None,
    detail_age: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Compare one surface event card against its canonical `/api/events/{id}` detail."""
    diffs: list[dict[str, Any]] = []
    event_id = detail.get("id") or card.get("id")
    matchup = _matchup_label(detail)
    sport_key = str(detail.get("sport") or card.get("sport") or "")
    extra_age: dict[str, Any] = {}
    if card_age is not None:
        extra_age["surface_copy_age"] = card_age
    if detail_age is not None:
        extra_age["detail_copy_age"] = detail_age
    gap = _fetch_gap_seconds(card_age, detail_age)
    if gap is not None:
        extra_age["fetch_gap_seconds"] = gap

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
                **extra_age,
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
                    **extra_age,
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
                    **extra_age,
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
                **extra_age,
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
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self.client = client
        self.pace_seconds = max(0.0, float(pace_seconds))
        self._sleep = sleep_fn
        self._monotonic = monotonic_fn
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self._last_request_at: float | None = None
        self.request_count = 0

    def get_json_with_meta(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
        retries: int = 0,
    ) -> tuple[int | None, Any | None, str | None, dict[str, Any]]:
        last_result: tuple[int | None, Any | None, str | None, dict[str, Any]] = (
            None,
            None,
            "no attempts",
            {},
        )
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
                last_result = (None, None, f"{type(exc).__name__}: {exc}", {})
                continue
            if resp.status_code != 200:
                last_result = (resp.status_code, None, f"HTTP {resp.status_code} on {path}", {})
                continue
            fetched_at = self._now_fn().astimezone(timezone.utc)
            server_date = _parse_http_date_utc(resp.headers.get("date"))
            age_header_s: float | None = None
            raw_age = resp.headers.get("age")
            if raw_age is not None:
                try:
                    parsed_age = float(str(raw_age).strip())
                    if parsed_age >= 0:
                        age_header_s = round(parsed_age, 1)
                except ValueError:
                    # Non-numeric Age header is ignored; body timestamps still provide copy age.
                    pass
            cache_hdr: str | None = None
            for hdr_name in (
                "x-feed-cache",
                "x-search-cache",
                "x-cache",
                "x-vercel-cache",
                "cf-cache-status",
            ):
                val = str(resp.headers.get(hdr_name) or "").strip()
                if val:
                    cache_hdr = val
                    break
            meta: dict[str, Any] = {
                "fetched_at": fetched_at.isoformat(),
                "server_date": server_date.isoformat() if server_date is not None else None,
                "age_header_seconds": age_header_s,
                "cache_header": cache_hdr,
            }
            try:
                return resp.status_code, resp.json(), None, meta
            except Exception as exc:
                last_result = (resp.status_code, None, f"JSONDecodeError on {path}: {exc}", meta)
        return last_result

    def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
        retries: int = 0,
    ) -> tuple[int | None, Any | None, str | None]:
        st, body, err, _meta = self.get_json_with_meta(
            path,
            params=params,
            timeout=timeout,
            retries=retries,
        )
        return st, body, err


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
        paced = PacedClient(raw_client, pace_seconds=pace, sleep_fn=sleep_fn, now_fn=now_fn)

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

        # 2. Item 7: Standing >72h sportsbook census (ALL scheduled games, including untwinned)
        scheduled_events: list[dict[str, Any]] = []
        scheduled_meta_by_id: dict[int, dict[str, Any]] = {}
        seen_sched_ids: set[int] = set()
        for page_idx in range(4):
            offset = page_idx * 500
            st_s, sched_body, err_s, meta_s = paced.get_json_with_meta(
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
            sched_env_meta = _extract_envelope_meta(sched_body, meta_s)
            batch = [e for e in (sched_body.get("events") or ()) if isinstance(e, dict)]
            for row in batch:
                rid = row.get("id")
                if isinstance(rid, int):
                    if rid in seen_sched_ids:
                        continue
                    seen_sched_ids.add(rid)
                    scheduled_meta_by_id[rid] = sched_env_meta
                scheduled_events.append(row)
            if len(batch) < 500:
                break

        census = compute_stale_sportsbook_census(scheduled_events, now=clock_now, stale_hours=stale_hours)

        # 3. Live games (/api/events?status=live&limit=50); avoid unfiltered /api/events?days=3
        st_l, live_body, err_l, meta_l = paced.get_json_with_meta(
            "/api/events",
            params={"status": "live", "limit": 50},
            timeout=30.0,
            retries=1,
        )
        live_env_meta: dict[str, Any] = {}
        if err_l or not isinstance(live_body, dict):
            http_errors.append({"path": "/api/events?status=live", "status": st_l, "error": err_l or "non-dict payload"})
            live_events: list[dict[str, Any]] = []
        else:
            live_events = [e for e in (live_body.get("events") or ()) if isinstance(e, dict)]
            live_env_meta = _extract_envelope_meta(live_body, meta_l)

        window_end = clock_now + timedelta(days=3)
        scheduled_3d: list[dict[str, Any]] = []
        for ev in scheduled_events:
            ct = _parse_iso_utc(ev.get("commence_time"))
            if ct is None or ct <= window_end:
                scheduled_3d.append(ev)

        # 4. Select up to max_games live / <=48h scheduled games across all represented sports
        combined_by_id: dict[int, dict[str, Any]] = {}
        list_surface_by_id: dict[int, str] = {}
        list_meta_by_id: dict[int, dict[str, Any]] = {}
        for ev in live_events:
            eid = ev.get("id")
            if isinstance(eid, int) and eid not in combined_by_id:
                combined_by_id[eid] = ev
                list_surface_by_id[eid] = "GET /api/events?status=live"
                list_meta_by_id[eid] = live_env_meta
        for ev in scheduled_3d:
            eid = ev.get("id")
            if isinstance(eid, int) and eid not in combined_by_id:
                combined_by_id[eid] = ev
                list_surface_by_id[eid] = "GET /api/events?status=scheduled"
                list_meta_by_id[eid] = scheduled_meta_by_id.get(eid, {})
        selected_games = select_audit_games(list(combined_by_id.values()), now=clock_now, max_games=max_games)
        selected_by_id = {int(g["id"]): g for g in selected_games if isinstance(g.get("id"), int)}
        sports_covered = sorted({str(g.get("sport") or "") for g in selected_games if g.get("sport")})

        surface_cards: dict[tuple[int, str], dict[str, Any]] = {}
        surface_meta: dict[tuple[int, str], dict[str, Any]] = {}
        for g in selected_games:
            gid = g.get("id")
            if isinstance(gid, int):
                surf = list_surface_by_id.get(gid, "GET /api/events?status=scheduled")
                surface_cards[(gid, surf)] = g
                surface_meta[(gid, surf)] = list_meta_by_id.get(gid, {})

        # 5. Sports feed (/api/feed?mode=sports&limit=200)
        st, feed_body, err, meta_f = paced.get_json_with_meta("/api/feed", params={"mode": "sports", "limit": 200})
        if err or not isinstance(feed_body, dict):
            http_errors.append({"path": "/api/feed?mode=sports", "status": st, "error": err or "non-dict payload"})
        else:
            feed_env_meta = _extract_envelope_meta(feed_body, meta_f)
            for item in feed_body.get("items") or ():
                if isinstance(item, dict) and item.get("type") == "event":
                    data = item.get("data")
                    if isinstance(data, dict) and isinstance(data.get("id"), int):
                        eid = int(data["id"])
                        if eid in selected_by_id:
                            surface_cards[(eid, "GET /api/feed?mode=sports")] = data
                            surface_meta[(eid, "GET /api/feed?mode=sports")] = feed_env_meta

        # 6. League pages (/api/leagues/{sport_key})
        for sk in sports_covered[:max_leagues]:
            path = f"/api/leagues/{sk}"
            st, lg_body, err, meta_lg = paced.get_json_with_meta(path)
            if err or not isinstance(lg_body, dict):
                http_errors.append({"path": path, "status": st, "error": err or "non-dict payload"})
                continue
            lg_env_meta = _extract_envelope_meta(lg_body, meta_lg)
            for key in ("upcoming_games", "recent_results", "unreported_games", "events", "live_events"):
                rows = lg_body.get(key)
                if isinstance(rows, list):
                    for ev in rows:
                        if isinstance(ev, dict) and isinstance(ev.get("id"), int):
                            eid = int(ev["id"])
                            if eid in selected_by_id:
                                surface_cards[(eid, f"GET {path}")] = ev
                                surface_meta[(eid, f"GET {path}")] = lg_env_meta

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
            st, sr_body, err, meta_sr = paced.get_json_with_meta(
                "/api/events/search", params={"q": q, "per_page": 15}
            )
            if err or not isinstance(sr_body, dict):
                http_errors.append({"path": f"/api/events/search?q={q}", "status": st, "error": err or "non-dict payload"})
                continue
            sr_env_meta = _extract_envelope_meta(sr_body, meta_sr)
            for ev in sr_body.get("results") or ():
                if isinstance(ev, dict) and isinstance(ev.get("id"), int):
                    eid = int(ev["id"])
                    if eid in selected_by_id:
                        surface_cards[(eid, "GET /api/events/search")] = ev
                        surface_meta[(eid, "GET /api/events/search")] = sr_env_meta
                        search_query_by_id[eid] = q

        def _refetch_surface_card(
            eid: int,
            surface: str,
            sport_key: str,
        ) -> tuple[dict[str, Any], dict[str, Any]] | None:
            if surface == "GET /api/events?status=live":
                params: dict[str, Any] = {"status": "live", "limit": 50}
                if sport_key:
                    params["sport"] = sport_key
                _, b, e, m = paced.get_json_with_meta("/api/events", params=params)
                if e or not isinstance(b, dict):
                    return None
                env_m = _extract_envelope_meta(b, m)
                for row in b.get("events") or ():
                    if isinstance(row, dict) and row.get("id") == eid:
                        return row, env_m
                return None
            if surface == "GET /api/events?status=scheduled":
                params = {"status": "scheduled", "days": 3, "past_days": 0, "limit": 200}
                if sport_key:
                    params["sport"] = sport_key
                _, b, e, m = paced.get_json_with_meta("/api/events", params=params)
                if e or not isinstance(b, dict):
                    return None
                env_m = _extract_envelope_meta(b, m)
                for row in b.get("events") or ():
                    if isinstance(row, dict) and row.get("id") == eid:
                        return row, env_m
                return None
            if surface == "GET /api/feed?mode=sports":
                _, b, e, m = paced.get_json_with_meta("/api/feed", params={"mode": "sports", "limit": 200})
                if e or not isinstance(b, dict):
                    return None
                env_m = _extract_envelope_meta(b, m)
                for item in b.get("items") or ():
                    if isinstance(item, dict) and item.get("type") == "event":
                        data = item.get("data")
                        if isinstance(data, dict) and data.get("id") == eid:
                            return data, env_m
                return None
            if surface.startswith("GET /api/leagues/"):
                path = surface[len("GET ") :]
                _, b, e, m = paced.get_json_with_meta(path)
                if e or not isinstance(b, dict):
                    return None
                env_m = _extract_envelope_meta(b, m)
                for k in ("upcoming_games", "recent_results", "unreported_games", "events", "live_events"):
                    for row in b.get(k) or ():
                        if isinstance(row, dict) and row.get("id") == eid:
                            return row, env_m
                return None
            if surface == "GET /api/events/search":
                q = search_query_by_id.get(eid)
                if not q:
                    return None
                _, b, e, m = paced.get_json_with_meta("/api/events/search", params={"q": q, "per_page": 15})
                if e or not isinstance(b, dict):
                    return None
                env_m = _extract_envelope_meta(b, m)
                for row in b.get("results") or ():
                    if isinstance(row, dict) and row.get("id") == eid:
                        return row, env_m
                return None
            return None

        # 8. Game detail reads (/api/events/{id}) + comparisons
        disagreements: list[dict[str, Any]] = []
        live_tick_drifts: list[dict[str, Any]] = []
        unconfirmed_disagreements: list[dict[str, Any]] = []
        surface_comparisons = 0
        games_verified = 0
        for eid in [int(g["id"]) for g in selected_games if isinstance(g.get("id"), int)]:
            path = f"/api/events/{eid}"
            st, detail, err, detail_meta = paced.get_json_with_meta(path)
            if err or not isinstance(detail, dict):
                http_errors.append({"path": path, "status": st, "error": err or "non-dict payload"})
                continue
            games_verified += 1
            detail_age = extract_copy_age(detail, response_meta=detail_meta, fallback_now=clock_now)
            is_live_detail = str(detail.get("status") or "").lower() in {"live", "in_progress"}
            detail_sport = str(detail.get("sport") or "")
            for (card_eid, surface), card in sorted(surface_cards.items(), key=lambda x: (x[0][0], x[0][1])):
                if card_eid != eid:
                    continue
                surface_comparisons += 1
                card_age = extract_copy_age(
                    card,
                    response_meta=surface_meta.get((card_eid, surface)),
                    fallback_now=clock_now,
                )
                card_diffs = compare_card_against_detail(
                    surface=surface,
                    card=card,
                    detail=detail,
                    card_age=card_age,
                    detail_age=detail_age,
                )
                if not card_diffs:
                    continue
                # Back-to-back re-read on ALL diffs (headline, sources, source_keys,
                # bookmaker_count; scheduled and live) so ordinary state/line changes
                # across the multi-minute Step-1-to-Step-8 fetch window are not filed
                # as persistent disagreements. If either re-read fails, record it as
                # unconfirmed (-> INCOMPLETE) rather than a confirmed diff.
                refetched = _refetch_surface_card(eid, surface, detail_sport or str(card.get("sport") or ""))
                if refetched is None:
                    unconfirmed_disagreements.append(
                        {
                            "event_id": eid,
                            "sport_key": detail_sport,
                            "matchup": _matchup_label(detail),
                            "surface": surface,
                            "is_live": is_live_detail,
                            "reason": "list_reread_failed",
                            "surface_copy_age": card_age,
                            "detail_copy_age": detail_age,
                            "initial_diffs": card_diffs,
                        }
                    )
                    continue
                re_card, re_card_meta = refetched
                re_card_age = extract_copy_age(re_card, response_meta=re_card_meta, fallback_now=clock_now)
                _, re_detail, re_err, re_detail_meta = paced.get_json_with_meta(path)
                if re_err or not isinstance(re_detail, dict):
                    unconfirmed_disagreements.append(
                        {
                            "event_id": eid,
                            "sport_key": detail_sport,
                            "matchup": _matchup_label(detail),
                            "surface": surface,
                            "is_live": is_live_detail,
                            "reason": f"detail_reread_failed:{re_err or 'non-dict payload'}",
                            "surface_copy_age": re_card_age,
                            "detail_copy_age": detail_age,
                            "initial_diffs": card_diffs,
                        }
                    )
                    continue
                re_detail_age = extract_copy_age(
                    re_detail, response_meta=re_detail_meta, fallback_now=clock_now
                )
                re_diffs = compare_card_against_detail(
                    surface=surface,
                    card=re_card,
                    detail=re_detail,
                    card_age=re_card_age,
                    detail_age=re_detail_age,
                )
                if not re_diffs:
                    live_tick_drifts.append(
                        {
                            "event_id": eid,
                            "sport_key": detail_sport,
                            "matchup": _matchup_label(detail),
                            "surface": surface,
                            "is_live": is_live_detail,
                            "surface_copy_age": re_card_age,
                            "detail_copy_age": re_detail_age,
                            "fetch_gap_seconds": _fetch_gap_seconds(re_card_age, re_detail_age),
                            "initial_diffs": card_diffs,
                        }
                    )
                    continue
                card_diffs = re_diffs
                disagreements.extend(card_diffs)

    has_real_findings = bool(disagreements) or census["stale_over_threshold_count"] > 0
    incomplete_count = len(http_errors) + len(unconfirmed_disagreements)
    if has_real_findings or (games_verified == 0 and incomplete_count == 0):
        status = "FAIL"
        parts: list[str] = []
        if disagreements:
            parts.append(f"{len(disagreements)} list-vs-page disagreement(s)")
        if census["stale_over_threshold_count"] > 0:
            parts.append(
                f"{census['stale_over_threshold_count']} scheduled game(s) over "
                f"{census['stale_threshold_hours']:.0f}h stale"
            )
        if games_verified == 0 and incomplete_count == 0:
            parts.append("0 games verified")
        if http_errors:
            parts.append(f"{len(http_errors)} read(s) failed")
        if unconfirmed_disagreements:
            parts.append(f"{len(unconfirmed_disagreements)} re-read(s) unconfirmed")
        status_summary = "; ".join(parts) + f" across {games_verified} game(s) read."
    elif incomplete_count > 0:
        status = "INCOMPLETE"
        inc_parts: list[str] = []
        if http_errors:
            inc_parts.append(f"{len(http_errors)} read(s) failed")
        if unconfirmed_disagreements:
            inc_parts.append(f"{len(unconfirmed_disagreements)} re-read(s) unconfirmed")
        status_summary = (
            "; ".join(inc_parts)
            + f"; no disagreement found in the {games_verified} game(s) read."
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
            "unconfirmed_disagreements_count": len(unconfirmed_disagreements),
            "unconfirmed_disagreements": unconfirmed_disagreements,
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
        f"- **Unconfirmed Initial Diffs (re-read failed):** `{lvp.get('unconfirmed_disagreements_count', 0)}`",
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
                "| Event | Sport | Matchup | Surface | Field | Surface Val | Detail Val | List Copy Age | Page Copy Age |",
                "|---|---|---|---|---|---|---|---|---|",
            ]
        )
        for d in lvp["disagreements"][:50]:
            list_age_str = format_copy_age(d.get("surface_copy_age")) if d.get("surface_copy_age") else "copy ?, read ?"
            page_age_str = format_copy_age(d.get("detail_copy_age")) if d.get("detail_copy_age") else "copy ?, read ?"
            gap = d.get("fetch_gap_seconds")
            if gap is not None:
                page_age_str += f" (gap {format_age_duration(gap)})"
            lines.append(
                f"| `{d['event_id']}` | `{d['sport_key']}` | {d['matchup']} | `{d['surface']}` | "
                f"`{d['field']}` | `{d['surface_value']}` | `{d['detail_value']}` | "
                f"`{list_age_str}` | `{page_age_str}` |"
            )
        lines.append("")

    if lvp.get("unconfirmed_disagreements"):
        lines.extend(
            [
                "## Unconfirmed Initial Diffs (Re-Read Failed)",
                "",
                "| Event | Sport | Matchup | Surface | Reason |",
                "|---|---|---|---|---|",
            ]
        )
        for u in lvp["unconfirmed_disagreements"][:50]:
            lines.append(
                f"| `{u['event_id']}` | `{u['sport_key']}` | {u['matchup']} | `{u['surface']}` | `{u['reason']}` |"
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
