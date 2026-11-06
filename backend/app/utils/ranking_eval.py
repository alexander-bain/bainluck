"""#12095 Decide 37-B: the ranking eval harness — slate snapshots and event fields.

PILLAR: DISCOVER. SHIP: every ranking change is scored against Alex's grades
before it ships, and real readers' swipes slot in on day one with no rework.
Nothing here changes what a reader sees.

THE SLATE. Once a night the Discover deck is read exactly as an anonymous
``GET /api/feed`` serves it (same function, same cache) and stored as one row of
``ranking_slate_snapshots``: the served order plus a candidate pool — every
served card, then the scored-but-unserved futures behind them — capped at
:data:`MAX_CANDIDATES`, each with the features the ranker had and the truth-gate
flags. The slate id is the deck's ``edition`` token (a content hash of the
ordered deck, already on every feed response), so an impression that carries it
joins to the exact list it was shown in.

THE RANKER VERSION is the deploy's git sha (:func:`ranker_version`). It rides
the feed response, the events, and the snapshot.

UNKNOWN STAYS UNKNOWN. A feature the system does not hold is ``None``, never a
zero: 1h and 7d movement are not stored on any market (only
``probability_change_24h``), so they are always ``None`` here; a flag that does
not apply to a card type (a bundle has no single probability) is ``None``, and
only ``True`` counts as a truth-gate failure.

SWITCH. ``RANKING_SNAPSHOTS`` (read per call): unset/``0`` = off, the default.
Off means no snapshot is taken, the feed response carries no
``ranker_version``, and an event's ``slate_id``/``ranker_version`` are not
stored — every payload and row is exactly as before.
"""

from __future__ import annotations

import logging
import os
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

RANKING_SNAPSHOTS_ENV = "RANKING_SNAPSHOTS"
#: The feed response field (only when the switch is on).
RANKER_VERSION_FIELD = "ranker_version"
#: Goal cap: never more than this many candidates in one slate.
MAX_CANDIDATES = 500
RETENTION_DAYS = 90
SURFACE_DISCOVER = "discover"
#: The harness's declared staleness rule, stored on every slate: a card whose
#: freshest price is older than this is ``stale``. Unknown age = ``None``.
STALE_PRICE_AGE_S = 24 * 3600
#: The opening cards also keep their full served payload (``card``), so a
#: grader sees the real card exactly as it was served.
OPENING_CARDS = 10
#: Width of the event/version columns (the edition token is 16 hex chars).
SLATE_ID_MAX = 64
RANKER_VERSION_MAX = 64

_SETTLED_STATUSES = frozenset(
    {"resolved", "closed", "settled", "finalized", "final", "completed", "complete", "finished"}
)
# Concept domains → the category a reader would file them under; mirrors
# `conceptDomainToCategory` in frontend/lib/discoverInteractions.ts.
_CONCEPT_DOMAIN_CATEGORY = {"ufc": "mma", "f1": "motorsports", "cycling": "cycling"}


def ranking_snapshots_enabled(environ: Mapping[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return (env.get(RANKING_SNAPSHOTS_ENV) or "").strip().lower() in ("1", "on", "true", "yes")


def ranker_version(environ: Mapping[str, str] | None = None) -> str:
    """The deploy's git sha (12 chars); the release version when no sha is set;
    ``"unknown"`` when the platform states neither — never an invented value."""
    env = os.environ if environ is None else environ
    sha = (env.get("HEROKU_SLUG_COMMIT") or env.get("GIT_COMMIT") or "").strip()
    if sha:
        return sha[:12]
    release = (env.get("HEROKU_RELEASE_VERSION") or "").strip()
    return release[:RANKER_VERSION_MAX] if release else "unknown"


def clip_event_field(value: Optional[str], width: int) -> Optional[str]:
    """An event's slate_id/ranker_version as stored: trimmed, bounded, blank→None."""
    if value is None:
        return None
    text = str(value).strip()
    return text[:width] or None


# ── features ────────────────────────────────────────────────────────────────


def _num(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    return None


def _json_safe(value: Any) -> Any:
    """A served payload as plain JSON (Decimal → float, datetime → ISO)."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _ts(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _iso(value: Any) -> Optional[str]:
    parsed = _ts(value)
    return parsed.isoformat() if parsed else None


def _latest(*values: Any) -> Optional[datetime]:
    stamps = [s for s in (_ts(v) for v in values) if s is not None]
    return max(stamps) if stamps else None


def _status_settled(status: Any) -> Optional[bool]:
    if not status:
        return None
    return str(status).strip().lower() in _SETTLED_STATUSES


#: Outcome labels that name no entity: a "Yes" on two cards is not a repeat.
_GENERIC_OUTCOMES = frozenset({"yes", "no", "other", "field", "none", "tie", "draw"})


def _is_entity(name: str) -> bool:
    text = name.strip()
    if not text or text.lower() in _GENERIC_OUTCOMES:
        return False
    # Thresholds and ranges ("$175", "<2.5%", "40+") are rungs, not entities.
    return not (text[0].isdigit() or text[0] in "$<>≥≤+-~")


def _names(rows: Any, key: str = "name", limit: int = 3) -> list[str]:
    out = []
    for row in rows or ():
        if isinstance(row, dict) and row.get(key) and _is_entity(str(row[key])):
            out.append(str(row[key]))
        if len(out) >= limit:
            break
    return out


def item_key(item: Mapping[str, Any]) -> Optional[str]:
    """``<type>:<id>`` — one card's identity in a slate."""
    data = item.get("data") or {}
    ident = data.get("id") if data.get("id") is not None else data.get("key")
    if ident is None:
        return None
    return f"{item.get('type') or 'unknown'}:{ident}"


def card_features(
    item: Mapping[str, Any],
    *,
    now: datetime,
    market_facts: Mapping[int, Mapping[str, Any]] | None = None,
) -> Optional[dict[str, Any]]:
    """The features of one served (or scored) card, in one shape for every type.

    ``market_facts``: futures id → facts read from the market row
    (``movement_24h``, ``updated_at``), used where the card payload is silent.
    """
    key = item_key(item)
    if key is None:
        return None
    kind = item.get("type") or "unknown"
    data = item.get("data") or {}
    out: dict[str, Any] = {
        "item_key": key,
        "type": kind,
        "item_id": str(data.get("id") if data.get("id") is not None else data.get("key")),
        "title": None,
        "category": None,
        "entities": [],
        "container": None,
        "probability": None,
        "movement_1h": None,  # not stored on any market (UNKNOWN, not zero)
        "movement_24h": None,
        "movement_7d": None,  # not stored on any market (UNKNOWN, not zero)
        "source_count": _num(data.get("source_count")),
        "sources": None,
        "source_spread": None,
        "start_time": None,
        "resolution_time": None,
        "price_observed_at": None,
        "score": _num(item.get("score")),
        "headline": item.get("headline"),
        "settled": None,
        "blend_missing": None,
    }
    observed: Optional[datetime] = None

    if kind == "futures":
        facts = (market_facts or {}).get(data.get("id")) or {}
        outcomes = data.get("top_outcomes") or []
        out["title"] = data.get("name")
        out["category"] = data.get("llm_sport_category")
        out["entities"] = _names(outcomes)
        out["container"] = data.get("group_id") or data.get("canonical_market_key")
        out["probability"] = _num(outcomes[0].get("probability")) if outcomes else None
        out["movement_24h"] = _num(facts.get("movement_24h"))
        if out["movement_24h"] is None:
            moves = [abs(m) for m in (_num(o.get("movement")) for o in outcomes) if m is not None]
            out["movement_24h"] = max(moves) if moves else None
        out["sources"] = list(data.get("sources") or []) or None
        out["resolution_time"] = _iso(data.get("resolution_date"))
        observed = _latest(data.get("price_observed_at")) or _latest(facts.get("updated_at"))
        out["settled"] = _status_settled(data.get("status"))
        out["blend_missing"] = out["probability"] is None
    elif kind == "event":
        home, away = data.get("home_team"), data.get("away_team")
        out["title"] = f"{away} @ {home}" if home and away else (home or away)
        out["category"] = data.get("sport_label") or data.get("sport_name") or data.get("sport")
        out["entities"] = [n for n in (home, away) if n]
        out["container"] = data.get("sport")
        out["probability"] = _num(data.get("hero_probability"))
        sources = data.get("win_probability_sources") or {}
        values, stamps, names = [], [], []
        if isinstance(sources, dict):
            for name, src in sources.items():
                if isinstance(src, dict) and _num(src.get("value")) is not None:
                    names.append(name)
                    values.append(_num(src.get("value")))
                    stamps.append(src.get("updated_at"))
        out["sources"] = names or None
        out["source_count"] = float(len(names)) if names else out["source_count"]
        out["source_spread"] = round(max(values) - min(values), 6) if len(values) >= 2 else None
        out["start_time"] = _iso(data.get("commence_time"))
        observed = _latest(*stamps)
        out["settled"] = _status_settled(data.get("status"))
        out["blend_missing"] = out["probability"] is None
    elif kind == "bundle":
        members = data.get("items") or []
        cats = Counter(
            (m.get("data") or {}).get("llm_sport_category")
            for m in members
            if isinstance(m, dict) and (m.get("data") or {}).get("llm_sport_category")
        )
        out["title"] = data.get("title")
        out["category"] = cats.most_common(1)[0][0] if cats else None
        out["entities"] = [data["story_key"]] if data.get("story_key") else []
        out["container"] = data.get("story_key")
        observed = _latest(*((m.get("data") or {}).get("price_observed_at") for m in members if isinstance(m, dict)))
        # A bundle shows its members' numbers, not one of its own: n/a, not missing.
    elif kind == "tournament":
        golfers = data.get("golfers") or []
        out["title"] = data.get("name")
        out["category"] = "golf"
        out["entities"] = _names(golfers)
        out["container"] = data.get("key")
        if golfers and isinstance(golfers[0], dict):
            out["probability"] = _num(golfers[0].get("probability") or golfers[0].get("win_probability"))
        out["start_time"] = _iso(data.get("start_date") or data.get("commence_time"))
        out["resolution_time"] = _iso(data.get("end_date") or data.get("resolution_date"))
        status = str(data.get("schedule_status") or "").lower()
        out["settled"] = bool(data.get("champion")) or status in _SETTLED_STATUSES
        observed = _latest(data.get("price_observed_at"))
    elif kind == "concept":
        leader = data.get("leader") or {}
        domain = str(data.get("domain") or "").lower()
        out["title"] = data.get("name")
        out["category"] = _CONCEPT_DOMAIN_CATEGORY.get(domain, domain or None)
        bout = data.get("headline_bout") or {}
        out["entities"] = [str(v) for k, v in bout.items() if isinstance(v, str) and k != "id"][:2] if isinstance(bout, dict) else []
        out["container"] = data.get("key")
        out["probability"] = _num(leader.get("probability")) if isinstance(leader, dict) else None
        out["start_time"] = _iso(data.get("start_date"))
        out["settled"] = _status_settled(data.get("status"))
        observed = _latest(data.get("price_observed_at"))

    out["price_observed_at"] = observed.isoformat() if observed else None
    age = (now - observed).total_seconds() if observed else None
    out["price_age_s"] = round(age, 1) if age is not None else None
    out["stale"] = (age > STALE_PRICE_AGE_S) if age is not None else None
    return out


def build_slate(
    served_items: list[Mapping[str, Any]],
    scored_futures: list[Mapping[str, Any]],
    *,
    now: datetime,
    market_facts: Mapping[int, Mapping[str, Any]] | None = None,
    cap: int = MAX_CANDIDATES,
) -> tuple[list[str], list[dict[str, Any]]]:
    """(served order, candidates): every served card first, in served order,
    with ``served_position`` 1..n; then unserved scored futures with
    ``served_position`` None; never more than ``cap`` candidates in total. The
    first :data:`OPENING_CARDS` also carry their served payload as ``card``."""
    served_order: list[str] = []
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in served_items:
        feats = card_features(item, now=now, market_facts=market_facts)
        if feats is None or feats["item_key"] in seen:
            continue
        seen.add(feats["item_key"])
        served_order.append(feats["item_key"])
        if len(candidates) < cap:
            position = len(served_order)
            extra = {"card": _json_safe(dict(item))} if position <= OPENING_CARDS else {}
            candidates.append({**feats, "served_position": position, **extra})
    for item in scored_futures:
        if len(candidates) >= cap:
            break
        feats = card_features(item, now=now, market_facts=market_facts)
        if feats is None or feats["item_key"] in seen:
            continue
        seen.add(feats["item_key"])
        candidates.append({**feats, "served_position": None})
    return served_order, candidates


# ── the nightly capture ─────────────────────────────────────────────────────


def _anonymous_request():
    from starlette.requests import Request

    return Request(
        {"type": "http", "method": "GET", "path": "/api/feed", "headers": [], "query_string": b""}
    )


async def read_served_discover_deck(db: Any) -> dict:
    """The Discover deck exactly as an anonymous reader's ``GET /api/feed`` gets
    it: the route function itself, anonymous, no pin, first page wide enough to
    hold the whole deck."""
    from fastapi import Response

    from app.routes.feed import get_feed

    return await get_feed(
        response=Response(),
        request=_anonymous_request(),
        limit=MAX_CANDIDATES,
        offset=0,
        sport=None,
        category=None,
        include_events=True,
        include_futures=True,
        my_teams_only=False,
        mode=None,
        tags=None,
        event_pct=None,
        edition=None,
        debug=False,
        debug_ground_truth=False,
        debug_personalization=False,
        exclude_reviewed=False,
        reviewer=None,
        reviewed_surface=None,
        secret=None,
        db=db,
        user=None,
    )


async def read_scored_futures(db: Any, now: datetime) -> list[dict]:
    """The anonymous futures pool in the ranker's own order (#142's read)."""
    from app.routes.feed import _rank_key, _score_futures
    from app.utils.personalization import PersonalizationContext

    scored = await _score_futures(db, now, None, PersonalizationContext())
    scored.sort(key=_rank_key, reverse=True)
    return scored


async def read_market_facts(db: Any, futures_ids: list[int]) -> dict[int, dict]:
    """Per futures id: the largest |24h move| across its outcomes and the
    market's ``updated_at``. One indexed read by primary key."""
    if not futures_ids:
        return {}
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.models import FuturesMarket

    rows = await db.execute(
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(FuturesMarket.id.in_(futures_ids))
    )
    facts: dict[int, dict] = {}
    for market in rows.scalars().all():
        moves = [
            abs(float(o.probability_change_24h))
            for o in market.outcomes
            if o.probability_change_24h is not None
        ]
        facts[market.id] = {
            "movement_24h": max(moves) if moves else None,
            "updated_at": market.updated_at,
        }
    return facts


async def snapshot_ranking_slate(
    db: Any,
    *,
    now: datetime | None = None,
    surface: str = SURFACE_DISCOVER,
    read_deck=read_served_discover_deck,
    read_pool=read_scored_futures,
    read_facts=read_market_facts,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Take one slate snapshot. Returns a run summary; never raises past a
    failed read (the summary says what failed). Off unless the switch is on."""
    if not ranking_snapshots_enabled(environ):
        return {"status": "disabled"}
    from sqlalchemy import delete

    from app.models.models import RankingSlateSnapshot

    now = now or datetime.now(timezone.utc)
    try:
        payload = await read_deck(db)
    except Exception as exc:  # noqa: BLE001 — a failed capture is reported, not raised
        logger.warning("ranking slate: deck read failed: %s", str(exc)[:200])
        return {"status": "deck_read_failed", "error": str(exc)[:200]}
    if not isinstance(payload, dict) or payload.get("build_quality", "complete") != "complete":
        reason = payload.get("degraded_reason") if isinstance(payload, dict) else "no_payload"
        return {"status": "degraded_deck", "reason": reason}
    served = list(payload.get("items") or [])
    edition = payload.get("edition")
    if not served or not edition:
        return {"status": "empty_deck", "served": len(served)}

    try:
        pool = await read_pool(db, now)
    except Exception as exc:  # noqa: BLE001 — the served order alone is still a slate
        logger.warning("ranking slate: candidate pool read failed: %s", str(exc)[:200])
        pool = []
    futures_ids = sorted(
        {
            int((it.get("data") or {})["id"])
            for it in [*served, *pool]
            if it.get("type") == "futures" and isinstance((it.get("data") or {}).get("id"), int)
        }
    )
    try:
        facts = await read_facts(db, futures_ids)
    except Exception as exc:  # noqa: BLE001 — card payload features still stand
        logger.warning("ranking slate: market facts read failed: %s", str(exc)[:200])
        facts = {}

    served_order, candidates = build_slate(served, pool, now=now, market_facts=facts)
    version = ranker_version(environ)
    summary = {
        "served_count": len(served_order),
        "candidate_count": len(candidates),
        "pool_scored": len(pool),
        "deck_total": payload.get("total"),
        "deck_cache_status": (payload.get("cache") or {}).get("status")
        if isinstance(payload.get("cache"), dict)
        else None,
        "stale_rule_s": STALE_PRICE_AGE_S,
        "not_stored": ["movement_1h", "movement_7d"],
    }
    row_id = str(uuid4())
    db.add(
        RankingSlateSnapshot(
            id=row_id,
            surface=surface,
            slate_id=str(edition)[:SLATE_ID_MAX],
            captured_at=now,
            ranker_version=version,
            served_order=served_order,
            candidates=candidates,
            summary=summary,
        )
    )
    await db.execute(
        delete(RankingSlateSnapshot).where(
            RankingSlateSnapshot.captured_at < now - timedelta(days=RETENTION_DAYS)
        )
    )
    await db.commit()
    return {
        "status": "ok",
        "id": row_id,
        "slate_id": str(edition)[:SLATE_ID_MAX],
        "ranker_version": version,
        **summary,
    }


def slate_row_dict(row: Any) -> dict[str, Any]:
    """One stored slate as the JSON the tools read (and the admin GET returns)."""
    return {
        "id": row.id,
        "surface": row.surface,
        "slate_id": row.slate_id,
        "captured_at": row.captured_at.isoformat() if row.captured_at else None,
        "ranker_version": row.ranker_version,
        "served_order": list(row.served_order or []),
        "candidates": list(row.candidates or []),
        "summary": dict(row.summary or {}),
    }


def grading_sheet(slate: Mapping[str, Any], *, top: int = 10) -> dict[str, Any]:
    """A slate's opening ``top`` as a grading sheet: position, title,
    probability, and an empty grade per card."""
    by_key = {c.get("item_key"): c for c in slate.get("candidates") or []}
    items = []
    for position, key in enumerate((slate.get("served_order") or [])[:top], start=1):
        cand = by_key.get(key) or {}
        items.append(
            {
                "position": position,
                "item_key": key,
                "title": cand.get("title"),
                "probability": cand.get("probability"),
                "grade": None,
                "note": "",
            }
        )
    return {
        "slate_id": slate.get("slate_id"),
        "surface": slate.get("surface"),
        "captured_at": slate.get("captured_at"),
        "ranker_version": slate.get("ranker_version"),
        "grades_allowed": ["shareable", "interesting", "neither"],
        "items": items,
    }
