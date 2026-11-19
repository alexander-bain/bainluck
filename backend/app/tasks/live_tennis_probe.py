"""#13000 (Ruling 257: B) — read-only Live Tennis API coverage probe.

Measures whether ``livetennisapi.com``'s free tier (100 requests/day) carries
live scores for our live Challenger and ITF tennis matches, singles and doubles
apart, before any spending decision is brought back to Alex.

STRICTLY READ-ONLY AND OFF BY DEFAULT:
- Returns immediately with zero DB reads and zero HTTP calls when
  ``LIVE_TENNIS_API_KEY`` is unset or blank.
- Never writes to ``events``, ``score_snapshots``, or any reader-facing table,
  and never exposes anything to readers.
- Hard-capped at ``DAILY_REQUEST_CAP = 96`` requests per UTC day (under the
  100/day free-tier ceiling) with a 15-minute minimum interval between calls,
  and skips the HTTP call when we have 0 live tennis matches.
- Never logs, prints, or forwards ``LIVE_TENNIS_API_KEY`` (``follow_redirects=False``).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import logging
import os
import re
import time
from typing import Any, Mapping, Sequence
import unicodedata

import httpx
from sqlalchemy import select

from app.models.models import Event, Sport
from app.tasks.base import get_task_session

logger = logging.getLogger(__name__)

LIVE_TENNIS_API_KEY_ENV = "LIVE_TENNIS_API_KEY"
LIVE_TENNIS_API_URL = "https://api.livetennisapi.com/api/public/v1/matches?status=live"
DAILY_REQUEST_CAP = 96
MIN_INTERVAL_SECONDS = 900
_MIN_INTERVAL_GUARD_SECONDS = MIN_INTERVAL_SECONDS - 30
HTTP_TIMEOUT_SECONDS = 10.0

REDIS_DAILY_KEY_PREFIX = "live_tennis_probe:calls:"
REDIS_LAST_FETCH_KEY = "live_tennis_probe:last_fetch_ts"
_REDIS_DAILY_TTL_SECONDS = 90_000

_LIVE_EVENT_STATUS = "live"

# In-process fallback budget state if Redis is momentarily unavailable.
_fallback_day: str | None = None
_fallback_count: int = 0
_fallback_last_mono: float = 0.0


def _reset_fallback_budget_for_tests() -> None:
    global _fallback_day, _fallback_count, _fallback_last_mono
    _fallback_day = None
    _fallback_count = 0
    _fallback_last_mono = 0.0


def _api_key() -> str:
    return os.getenv(LIVE_TENNIS_API_KEY_ENV, "").strip()


def live_tennis_probe_enabled() -> bool:
    """True only when LIVE_TENNIS_API_KEY is present in the environment."""
    return bool(_api_key())


def is_doubles_match(home_name: str | None, away_name: str | None) -> bool:
    """Doubles entries separate partners with '/' (e.g. 'Hsieh C-P / Smith')."""
    return "/" in (home_name or "") or "/" in (away_name or "")


def classify_tennis_tier(
    *,
    sport_key: str | None,
    external_id: str | None = None,
    event_tags: Sequence[Any] | None = None,
    box_score_data: Mapping[str, Any] | None = None,
) -> str:
    """Classify one of our live tennis events as challenger, itf, tour, or other."""
    parts: list[str] = []
    if sport_key:
        parts.append(str(sport_key))
    if external_id:
        parts.append(str(external_id))
    if event_tags:
        parts.extend(str(tag) for tag in event_tags if tag)
    if isinstance(box_score_data, Mapping):
        for key in ("tournament", "tournament_name", "league", "tour", "category"):
            val = box_score_data.get(key)
            if isinstance(val, str) and val:
                parts.append(val)
    haystack = " ".join(parts).lower()
    if "challenger" in haystack:
        return "challenger"
    if re.search(r"(?:^|[^a-z])itf(?:[^a-z]|$)", haystack) or "kxitf" in haystack:
        return "itf"
    if any(
        token in haystack
        for token in (
            "grand_slam",
            "us_open",
            "french_open",
            "wimbledon",
            "aus_open",
            "australian_open",
            "tennis_atp",
            "tennis_wta",
        )
    ):
        return "tour"
    return "other"


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _person_tokens(raw: str) -> list[str]:
    """Extract lowercase surname/name tokens (>=2 alpha chars) for one player."""
    cleaned = _strip_accents(raw or "").lower()
    # Drop hyphenated initials like "c-p" or single-letter initials like "j."
    tokens = [tok for tok in re.findall(r"[a-z]{2,}", cleaned)]
    return tokens


def _side_partner_tokens(side_name: str) -> list[list[str]]:
    """Split a side into 1 (singles) or 2+ (doubles) partner token lists."""
    partners = [part.strip() for part in (side_name or "").split("/") if part.strip()]
    return [_person_tokens(p) for p in partners if _person_tokens(p)]


def _partner_matches(our_tokens: list[str], feed_tokens: list[str]) -> bool:
    """True when one player's surname/tokens match across our DB and the feed."""
    if not our_tokens or not feed_tokens:
        return False
    our_set = set(our_tokens)
    feed_set = set(feed_tokens)
    # Full subset match covers "Hsu" <-> "Yu Hsiou Hsu" and "Hsieh" <-> "Cheng-Peng Hsieh".
    if our_set.issubset(feed_set) or feed_set.issubset(our_set):
        return True
    # Surname match (last token of each name) covers "A. Boyer" <-> "Tristan Boyer".
    if our_tokens[-1] == feed_tokens[-1] and len(our_tokens[-1]) >= 3:
        return True
    # Also handle "Last First" vs "First Last" where first token is surname.
    if our_tokens[0] == feed_tokens[-1] and len(our_tokens[0]) >= 3:
        return True
    if our_tokens[-1] == feed_tokens[0] and len(our_tokens[-1]) >= 3:
        return True
    return False


def _side_matches(our_side: str, feed_side: str) -> bool:
    our_partners = _side_partner_tokens(our_side)
    feed_partners = _side_partner_tokens(feed_side)
    if not our_partners or not feed_partners:
        return False
    if len(our_partners) != len(feed_partners):
        return False
    if len(our_partners) == 1:
        return _partner_matches(our_partners[0], feed_partners[0])
    # Doubles: match partners in either order (A/B vs B/A).
    if len(our_partners) == 2:
        return (
            _partner_matches(our_partners[0], feed_partners[0])
            and _partner_matches(our_partners[1], feed_partners[1])
        ) or (
            _partner_matches(our_partners[0], feed_partners[1])
            and _partner_matches(our_partners[1], feed_partners[0])
        )
    return all(
        any(_partner_matches(op, fp) for fp in feed_partners) for op in our_partners
    )


def _extract_player_name(raw: Any) -> str:
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, Mapping):
        for key in ("name", "full_name", "display_name", "short_name"):
            val = raw.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return ""


def _feed_match_has_score(score: Any) -> bool:
    """True when the vendor match payload carries at least one live score field."""
    if not isinstance(score, Mapping) or not score:
        return False
    sets = score.get("sets")
    if isinstance(sets, list) and len(sets) >= 2 and all(
        isinstance(x, (int, float)) and not isinstance(x, bool) for x in sets[:2]
    ):
        # Accept sets once non-zero or accompanied by games/points.
        if any(x > 0 for x in sets[:2]):
            return True
    games = score.get("games")
    if isinstance(games, list) and any(
        isinstance(pair, (list, tuple))
        and len(pair) >= 2
        and all(
            isinstance(x, (int, float)) and not isinstance(x, bool)
            for x in pair[:2]
        )
        for pair in games
    ):
        return True
    points = score.get("points")
    if isinstance(points, list) and len(points) >= 2 and any(
        str(p).strip() not in {"", "None", "null"} for p in points[:2]
    ):
        return True
    return False


def extract_feed_matches(payload: Any) -> list[dict[str, Any]]:
    """Normalize ``livetennisapi.com`` /matches?status=live JSON into flat records."""
    if isinstance(payload, Mapping):
        rows = payload.get("data")
        if not isinstance(rows, list):
            rows = payload.get("matches")
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = None
    if not isinstance(rows, list):
        return []

    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        players = row.get("players")
        if isinstance(players, Mapping):
            p1 = _extract_player_name(players.get("p1") or players.get("player1"))
            p2 = _extract_player_name(players.get("p2") or players.get("player2"))
        else:
            p1 = _extract_player_name(row.get("player1") or row.get("home") or row.get("p1"))
            p2 = _extract_player_name(row.get("player2") or row.get("away") or row.get("p2"))
        if not p1 or not p2:
            continue
        tournament_raw = row.get("tournament")
        if isinstance(tournament_raw, Mapping):
            tournament = str(tournament_raw.get("name") or "").strip()
        else:
            tournament = str(tournament_raw or "").strip()
        tour = str(row.get("tour") or row.get("category") or row.get("level") or "").strip().lower()
        out.append(
            {
                "id": row.get("id"),
                "p1": p1,
                "p2": p2,
                "tour": tour,
                "tournament": tournament,
                "status": str(row.get("status") or "").strip().lower(),
                "has_score": _feed_match_has_score(row.get("score")),
            }
        )
    return out


def match_event_to_feed(
    home_name: str,
    away_name: str,
    feed_matches: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    """Find the live feed match corresponding to one of our live tennis events."""
    for candidate in feed_matches:
        p1 = str(candidate.get("p1") or "")
        p2 = str(candidate.get("p2") or "")
        if (_side_matches(home_name, p1) and _side_matches(away_name, p2)) or (
            _side_matches(home_name, p2) and _side_matches(away_name, p1)
        ):
            return candidate
    return None


def summarize_probe(
    our_events: Sequence[Mapping[str, Any]],
    feed_matches: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compare our live tennis events against the vendor feed (pure, read-only)."""
    buckets: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "our_live": 0,
            "our_scoreless": 0,
            "carried": 0,
            "carried_with_score": 0,
            "missing": 0,
        }
    )
    details: list[dict[str, Any]] = []
    totals = {
        "our_live": 0,
        "our_scoreless": 0,
        "feed_total": len(feed_matches),
        "carried": 0,
        "carried_with_score": 0,
        "missing": 0,
    }

    for ev in our_events:
        home = str(ev.get("home_team_name") or "")
        away = str(ev.get("away_team_name") or "")
        match_format = "doubles" if is_doubles_match(home, away) else "singles"
        tier = classify_tennis_tier(
            sport_key=ev.get("sport_key"),
            external_id=ev.get("external_id"),
            event_tags=ev.get("event_tags"),
            box_score_data=ev.get("box_score_data"),
        )
        matched = match_event_to_feed(home, away, feed_matches)
        # If our row only had generic tennis_atp/wta metadata, refine tour->challenger/itf
        # from the vendor's own tour tag when present so reporting stays accurate.
        if matched is not None and tier == "tour":
            feed_tour = str(matched.get("tour") or "").lower()
            if "challenger" in feed_tour:
                tier = "challenger"
            elif "itf" in feed_tour:
                tier = "itf"

        bucket_key = f"{tier}_{match_format}"
        our_has_score = (
            ev.get("home_score") is not None
            or ev.get("away_score") is not None
            or bool(ev.get("period"))
        )
        carried = matched is not None
        feed_has_score = bool(matched and matched.get("has_score"))

        totals["our_live"] += 1
        buckets[bucket_key]["our_live"] += 1
        if not our_has_score:
            totals["our_scoreless"] += 1
            buckets[bucket_key]["our_scoreless"] += 1
        if carried:
            totals["carried"] += 1
            buckets[bucket_key]["carried"] += 1
            if feed_has_score:
                totals["carried_with_score"] += 1
                buckets[bucket_key]["carried_with_score"] += 1
        else:
            totals["missing"] += 1
            buckets[bucket_key]["missing"] += 1

        details.append(
            {
                "event_id": ev.get("id"),
                "bucket": bucket_key,
                "tier": tier,
                "format": match_format,
                "our_match": f"{away} vs {home}",
                "our_has_score": our_has_score,
                "carried": carried,
                "feed_has_score": feed_has_score,
                "feed_tour": matched.get("tour") if matched else None,
                "feed_tournament": matched.get("tournament") if matched else None,
            }
        )

    return {
        "totals": totals,
        "by_bucket": dict(sorted(buckets.items())),
        "matches": details,
    }


def _redis_client():
    from app.tasks.redis_state import get_redis_client

    return get_redis_client(socket_timeout=0.5, fast_fail=True)


def _reserve_daily_budget(now: datetime) -> tuple[bool, int, str]:
    """Reserve 1 slot under DAILY_REQUEST_CAP (96/day) and MIN_INTERVAL_SECONDS (15m)."""
    global _fallback_day, _fallback_count, _fallback_last_mono

    day = now.astimezone(timezone.utc).strftime("%Y-%m-%d")
    daily_key = f"{REDIS_DAILY_KEY_PREFIX}{day}"
    try:
        client = _redis_client()
    except Exception:
        client = None

    if client is not None:
        try:
            current_raw = client.get(daily_key)
            current = int(current_raw) if current_raw is not None else 0
            if current >= DAILY_REQUEST_CAP:
                return False, current, "daily_cap_reached"
            acquired = client.set(
                REDIS_LAST_FETCH_KEY,
                str(int(now.timestamp())),
                ex=_MIN_INTERVAL_GUARD_SECONDS,
                nx=True,
            )
            if not acquired:
                return False, current, "min_interval_guard"
            new_count = int(client.incr(daily_key))
            client.expire(daily_key, _REDIS_DAILY_TTL_SECONDS)
            if new_count > DAILY_REQUEST_CAP:
                return False, new_count, "daily_cap_reached"
            return True, new_count, "ok"
        except Exception:
            logger.debug("live_tennis_probe: Redis budget check fallback", exc_info=True)

    # In-process fallback when Redis is unavailable.
    now_mono = time.monotonic()
    if _fallback_day != day:
        _fallback_day = day
        _fallback_count = 0
    if _fallback_count >= DAILY_REQUEST_CAP:
        return False, _fallback_count, "daily_cap_reached"
    if _fallback_last_mono and (now_mono - _fallback_last_mono) < _MIN_INTERVAL_GUARD_SECONDS:
        return False, _fallback_count, "min_interval_guard"
    _fallback_last_mono = now_mono
    _fallback_count += 1
    return True, _fallback_count, "ok"


async def _load_live_tennis_events() -> list[dict[str, Any]]:
    """Read-only SELECT of our currently live tennis events."""
    async with get_task_session() as db:
        rows = (
            await db.execute(
                select(
                    Event.id,
                    Event.home_team_name,
                    Event.away_team_name,
                    Event.external_id,
                    Event.home_score,
                    Event.away_score,
                    Event.period,
                    Event.event_tags,
                    Event.box_score_data,
                    Sport.key.label("sport_key"),
                )
                .join(Sport, Sport.id == Event.sport_id)
                .where(
                    Sport.key.like("tennis_%"),
                    Event.status == _LIVE_EVENT_STATUS,
                )
                .order_by(Event.id.asc())
            )
        ).all()
    return [
        {
            "id": r.id,
            "home_team_name": r.home_team_name,
            "away_team_name": r.away_team_name,
            "external_id": r.external_id,
            "home_score": r.home_score,
            "away_score": r.away_score,
            "period": r.period,
            "event_tags": r.event_tags,
            "box_score_data": r.box_score_data,
            "sport_key": r.sport_key,
        }
        for r in rows
    ]


async def _fetch_live_tennis_payload(api_key: str) -> Any:
    """Read-only GET to livetennisapi.com. Never follows redirects or logs the key."""
    async with httpx.AsyncClient(
        timeout=HTTP_TIMEOUT_SECONDS,
        follow_redirects=False,
    ) as client:
        resp = await client.get(
            LIVE_TENNIS_API_URL,
            headers={
                "X-API-Key": api_key,
                "Accept": "application/json",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def run_live_tennis_probe(*, now: datetime | None = None) -> dict[str, Any]:
    """Run one read-only coverage check against livetennisapi.com (#13000 / 257: B)."""
    api_key = _api_key()
    if not api_key:
        return {
            "status": "disabled",
            "reason": "LIVE_TENNIS_API_KEY_unset",
            "terminal": "skipped",
        }

    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    our_events = await _load_live_tennis_events()
    if not our_events:
        return {
            "status": "skipped",
            "reason": "no_live_tennis_events",
            "our_live": 0,
            "terminal": "complete",
        }

    allowed, daily_calls, reason = _reserve_daily_budget(now_utc)
    if not allowed:
        logger.info(
            "live_tennis_probe skipped: reason=%s daily_calls=%d/%d our_live=%d",
            reason,
            daily_calls,
            DAILY_REQUEST_CAP,
            len(our_events),
        )
        return {
            "status": "skipped",
            "reason": reason,
            "daily_calls": daily_calls,
            "our_live": len(our_events),
            "terminal": "complete",
        }

    try:
        payload = await _fetch_live_tennis_payload(api_key)
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "live_tennis_probe fetch failed: http_status=%d daily_calls=%d/%d",
            exc.response.status_code,
            daily_calls,
            DAILY_REQUEST_CAP,
        )
        return {
            "status": "error",
            "reason": f"http_{exc.response.status_code}",
            "daily_calls": daily_calls,
            "terminal": "complete",
        }
    except Exception as exc:
        # Never log exc with headers/request details; exception class only.
        logger.warning(
            "live_tennis_probe fetch failed: error_type=%s daily_calls=%d/%d",
            type(exc).__name__,
            daily_calls,
            DAILY_REQUEST_CAP,
        )
        return {
            "status": "error",
            "reason": type(exc).__name__,
            "daily_calls": daily_calls,
            "terminal": "complete",
        }

    feed_matches = extract_feed_matches(payload)
    summary = summarize_probe(our_events, feed_matches)
    logger.info(
        "live_tennis_probe summary: daily_calls=%d/%d totals=%s by_bucket=%s",
        daily_calls,
        DAILY_REQUEST_CAP,
        summary["totals"],
        summary["by_bucket"],
    )
    for row in summary["matches"]:
        logger.info(
            "live_tennis_probe match: event_id=%s bucket=%s our_has_score=%s "
            "carried=%s feed_has_score=%s feed_tour=%s feed_tournament=%r match=%r",
            row["event_id"],
            row["bucket"],
            row["our_has_score"],
            row["carried"],
            row["feed_has_score"],
            row["feed_tour"],
            row["feed_tournament"],
            row["our_match"],
        )

    return {
        "status": "ok",
        "daily_calls": daily_calls,
        "totals": summary["totals"],
        "by_bucket": summary["by_bucket"],
        "terminal": "complete",
    }
