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
(The capture itself is ``app/utils/ranking_slate_capture.py``; this module
holds the shape, so the feed route can import it with no import cycle.)

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
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

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
    key: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """The features of one served (or scored) card, in one shape for every type.

    ``market_facts``: futures id → facts read from the market row
    (``movement_24h``, ``updated_at``), used where the card payload is silent.
    ``key`` overrides the card's own identity (``build_slate`` uses it for a
    served card with no id, or one served twice); otherwise a card with no id
    and no key yields None.
    """
    key = key or item_key(item)
    if key is None:
        return None
    kind = item.get("type") or "unknown"
    data = item.get("data") or {}
    out: dict[str, Any] = {
        "item_key": key,
        "type": kind,
        "item_id": (
            str(data["id"]) if data.get("id") is not None
            else (str(data["key"]) if data.get("key") is not None else None)
        ),
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
        # Whether the card itself shows the settled result (a final score, a
        # winner at 100%, a champion). A settled card shown WITH its result is a
        # legitimate seat; only settled-without-result is a truth-gate failure.
        "shows_result": None,
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
        out["shows_result"] = any(
            isinstance(o, dict)
            and (o.get("is_winner") is True or (_num(o.get("probability")) or 0) >= 0.9995)
            for o in outcomes
        )
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
        out["shows_result"] = data.get("home_score") is not None and data.get("away_score") is not None
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
        if data.get("champion"):
            out["settled"], out["shows_result"] = True, True
        elif status:
            out["settled"] = status in _SETTLED_STATUSES
            out["shows_result"] = False if out["settled"] else None
        # No champion and no schedule status: settled stays None (UNKNOWN).
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
    # True only when settled AND the card is known to show no result; an
    # unknown on either side stays None (never a pass, never a failure).
    if out["settled"] is False:
        out["settled_without_result"] = False
    elif out["settled"] is True and out["shows_result"] is not None:
        out["settled_without_result"] = not out["shows_result"]
    else:
        out["settled_without_result"] = None
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
    with ``served_position`` = served index + 1 (no card is skipped); then unserved scored futures with
    ``served_position`` None; never more than ``cap`` candidates in total. The
    first :data:`OPENING_CARDS` also carry their served payload as ``card``."""
    served_order: list[str] = []
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(served_items):
        # Every served card keeps its seat: position is the served index + 1, so
        # the grading sheet's positions are the ones the reader saw. A card with
        # no id is still counted (``unknown:<index>``); a card served twice gets
        # a second key for its second seat.
        position = index + 1
        key = item_key(item) or f"unknown:{index}"
        if key in seen:
            key = f"{key}#{position}"
        feats = card_features(item, now=now, market_facts=market_facts, key=key)
        seen.add(key)
        served_order.append(key)
        if len(candidates) < cap:
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
