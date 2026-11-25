"""Blind Morning Scout Deck (#13102, Decision 385: A).

Builds the equal-mix blind review deck served at ``GET /api/admin/ranking/scout-deck``
and graded on ``/grade/scout``:
* Reads staged sets from durable Redis (``bainluck:fun_scout:run:<date>`` or
  ``bainluck:fun_scout:latest``), capped at ``SCOUT_MAX_NEW_SETS_PER_DAY``.
* Mixes all ``K`` staged sets with an equal count (``K``) of live public sets
  so the grader cannot tell staged scout sets from already-public sets.
* Hydrates both origins into the exact same anonymized schema, stripping ``slug``,
  ``stage``, ``origin``, ``scout``, ``requires_fable_look``, ``source``,
  ``provider``, and ``market_id`` plus any provider names.
* Persists the sealed answer key strictly in Redis
  (``bainluck:fun_scout:deck_key:<deck_date>``) and never sends it to the browser.
* Zero auto-promotion: grading ``Keep`` writes only a ``ranking_judgments`` row.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import FuturesMarket
from app.utils.container_machinery import discover_machinery_candidate_paths, load_machinery_definition
from app.utils.discover_fun_scout import (
    SCOUT_MAX_NEW_SETS_PER_DAY,
    SCOUT_RETIRED_SETS_PATH,
    load_retired_scout_sets,
)
from app.utils.roundup_containers import (
    CONTAINERS_DATA_DIR,
    _redis_cache_key,
    load_roundup_definitions_from_dir,
)

logger = logging.getLogger(__name__)

PACIFIC_TZ = ZoneInfo("America/Los_Angeles")
SCOUT_DECK_SURFACE = "grade_scout_morning_deck"
SCOUT_DECK_ITEM_TYPE = "scout_morning_deck"
SCOUT_RUN_REDIS_PREFIX = "bainluck:fun_scout:run"
SCOUT_LATEST_REDIS_KEY = "bainluck:fun_scout:latest"
SCOUT_DECK_KEY_REDIS_PREFIX = "bainluck:fun_scout:deck_key"
SCOUT_DECK_KEY_TTL_S = 45 * 24 * 3600
DATE_PARAM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_OPEN_STATUS = "open"
_ALLOWED_LOOKS = frozenset({"bars", "map", "faces"})
_PROVIDER_WORD_RE = re.compile(r"\b(?:kalshi|polymarket)\b", re.IGNORECASE)


def _today_pt_date(now: Optional[datetime] = None) -> str:
    ref = now or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return ref.astimezone(PACIFIC_TZ).strftime("%Y-%m-%d")


def _clean_blind_text(text: Any) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    cleaned = _PROVIDER_WORD_RE.sub("", raw)
    return " ".join(cleaned.split())


def _safe_float(val: Any) -> Optional[float]:
    if isinstance(val, bool) or val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _deck_hmac_bytes() -> bytes:
    secret = os.environ.get("ADMIN_TOKEN", "scout-morning-deck-salt")
    return hashlib.sha256(f"{secret}|scout-morning-deck|13102".encode("utf-8")).digest()


def _decode_redis_json(raw: Any) -> Optional[dict[str, Any]]:
    if raw is None:
        return None
    try:
        txt = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
        parsed = json.loads(txt)
        return parsed if isinstance(parsed, dict) else None
    except (UnicodeDecodeError, ValueError):
        return None


def read_nightly_scout_artifact(
    deck_date: Optional[str] = None,
    *,
    redis_client: Any = None,
    now: Optional[datetime] = None,
) -> tuple[str, Optional[dict[str, Any]]]:
    """Read staged sets from Redis ``bainluck:fun_scout:run:<date>`` (fallback ``:latest``)."""
    resolved_date = deck_date.strip() if isinstance(deck_date, str) and deck_date.strip() else _today_pt_date(now)
    client = redis_client
    if client is None:
        try:
            from app.tasks.redis_state import get_redis_client

            client = get_redis_client(fast_fail=True)
        except Exception as exc:
            logger.debug("scout_deck: redis unavailable reading nightly run: %s", type(exc).__name__)
            return resolved_date, None

    if client is None:
        return resolved_date, None

    try:
        artifact = _decode_redis_json(client.get(f"{SCOUT_RUN_REDIS_PREFIX}:{resolved_date}"))
        if artifact is not None:
            return resolved_date, artifact
        if not deck_date:
            latest = _decode_redis_json(client.get(SCOUT_LATEST_REDIS_KEY))
            if latest is not None:
                latest_date = str(latest.get("run_date") or "").strip()
                if DATE_PARAM_RE.match(latest_date):
                    return latest_date, latest
                return resolved_date, latest
    except Exception as exc:
        logger.debug("scout_deck: failed reading nightly artifact: %s", type(exc).__name__)
    return resolved_date, None


def _serialize_market_row_member(market: Any) -> dict[str, Any]:
    outcomes = sorted(
        list(getattr(market, "outcomes", None) or ()),
        key=lambda o: (getattr(o, "rank", None) or 9999, -(float(getattr(o, "current_probability", None) or 0.0))),
    )
    leading = outcomes[0] if outcomes else None
    prob = _safe_float(getattr(leading, "current_probability", None)) if leading else None
    delta = _safe_float(getattr(leading, "probability_change_24h", None)) if leading else None
    lead_name = _clean_blind_text(getattr(leading, "name", None) or "Yes") if leading else "Yes"
    image_url = getattr(market, "image_url", None)
    return {
        "title": _clean_blind_text(getattr(market, "question", None) or getattr(market, "name", None) or ""),
        "leading_outcome": lead_name,
        "probability": round(prob, 4) if prob is not None else None,
        "change_24h": round(delta, 4) if delta is not None else None,
        "image_url": str(image_url).strip() if isinstance(image_url, str) and image_url.strip() else None,
    }


def _members_from_cached_feed_item(entry: Mapping[str, Any]) -> list[dict[str, Any]]:
    feed_item = entry.get("feed_item")
    if not isinstance(feed_item, Mapping):
        return []
    data = feed_item.get("data")
    if not isinstance(data, Mapping):
        return []
    raw_items = data.get("items")
    if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
        return []

    members: list[dict[str, Any]] = []
    for child in raw_items:
        if not isinstance(child, Mapping):
            continue
        cdata = child.get("data")
        if not isinstance(cdata, Mapping):
            continue
        title = _clean_blind_text(
            cdata.get("name") or cdata.get("question") or cdata.get("title") or ""
        )
        if not title:
            continue
        outcomes = cdata.get("top_outcomes") or ()
        lead = outcomes[0] if outcomes and isinstance(outcomes[0], Mapping) else None
        prob = _safe_float(lead.get("probability")) if lead else _safe_float(cdata.get("hero_probability"))
        delta = _safe_float(lead.get("movement")) if lead else None
        lead_name = _clean_blind_text((lead.get("name") if lead else None) or "Yes")
        img = cdata.get("image_url")
        members.append(
            {
                "title": title,
                "leading_outcome": lead_name,
                "probability": round(prob, 4) if prob is not None else None,
                "change_24h": round(delta, 4) if delta is not None else None,
                "image_url": str(img).strip() if isinstance(img, str) and img.strip() else None,
            }
        )
    return members


def _sanitize_card_entry(
    *,
    title: Any,
    kicker: Any,
    category: Any,
    summary: Any,
    look: Any,
    members: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    clean_look = str(look or "bars").strip().lower()
    if clean_look not in _ALLOWED_LOOKS:
        clean_look = "bars"
    clean_members = [
        {
            "title": _clean_blind_text(m.get("title")),
            "leading_outcome": _clean_blind_text(m.get("leading_outcome") or "Yes"),
            "probability": _safe_float(m.get("probability")),
            "change_24h": _safe_float(m.get("change_24h")),
            "image_url": (
                str(m.get("image_url")).strip()
                if isinstance(m.get("image_url"), str) and str(m.get("image_url")).strip()
                else None
            ),
        }
        for m in members
        if _clean_blind_text(m.get("title"))
    ][:8]
    return {
        "title": _clean_blind_text(title) or "Untitled set",
        "kicker": _clean_blind_text(kicker) or "DISCOVER SET",
        "category": _clean_blind_text(category or "other").lower() or "other",
        "summary": _clean_blind_text(summary),
        "look": clean_look,
        "member_count": len(clean_members),
        "members": clean_members,
    }


def _collect_public_definitions(retired_slugs: set[str]) -> list[dict[str, Any]]:
    defs: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()
    for path in discover_machinery_candidate_paths():
        try:
            defn = load_machinery_definition(path)
        except Exception:
            continue
        slug = str(defn.get("slug") or "").strip().lower()
        if not slug or slug in seen_slugs or slug in retired_slugs:
            continue
        if defn.get("stage", "public") != "public" or "scout" in defn:
            continue
        seen_slugs.add(slug)
        defs.append(defn)

    for defn in load_roundup_definitions_from_dir(CONTAINERS_DATA_DIR):
        slug = str(defn.get("slug") or "").strip().lower()
        if not slug or slug in seen_slugs or slug in retired_slugs:
            continue
        if defn.get("stage", "public") != "public" or "scout" in defn:
            continue
        seen_slugs.add(slug)
        defs.append(defn)
    return defs


async def _load_markets_by_id(
    db: AsyncSession,
    market_ids: Iterable[int],
) -> dict[int, FuturesMarket]:
    wanted = sorted({int(mid) for mid in market_ids if isinstance(mid, int) and mid > 0})
    if not wanted:
        return {}
    rows = (
        await db.execute(
            select(FuturesMarket)
            .options(selectinload(FuturesMarket.outcomes))
            .where(FuturesMarket.id.in_(wanted))
        )
    ).scalars().all()
    return {
        int(row.id): row
        for row in rows
        if str(getattr(row, "status", "") or "").lower() == _OPEN_STATUS
    }


async def load_public_decoy_entries(
    needed: int,
    deck_date: str,
    *,
    db: AsyncSession,
    redis_client: Any = None,
    retired_slugs: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
    """Select ``<= needed`` live public sets hydrated into the blind card shape."""
    if needed <= 0:
        return []
    retired: set[str] = (
        {str(s).strip().lower() for s in retired_slugs if str(s).strip()}
        if retired_slugs is not None
        else {
            str(entry.get("slug") or "").strip().lower()
            for entry in load_retired_scout_sets(SCOUT_RETIRED_SETS_PATH)
            if isinstance(entry, Mapping) and str(entry.get("slug") or "").strip()
        }
    )
    defs = _collect_public_definitions(retired)
    if not defs:
        return []

    hmac_key = _deck_hmac_bytes()
    defs.sort(
        key=lambda d: hmac.new(
            hmac_key,
            f"decoy|{deck_date}|{d.get('slug')}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    )

    cached_by_slug: dict[str, dict[str, Any]] = {}
    rc = redis_client
    if rc is None:
        try:
            from app.tasks.redis_state import get_redis_client

            rc = get_redis_client(fast_fail=True)
        except Exception:
            rc = None

    if rc is not None and hasattr(rc, "mget"):
        try:
            keys = [_redis_cache_key(str(d["slug"])) for d in defs]
            raw_vals = rc.mget(keys)
            for defn, raw in zip(defs, raw_vals):
                parsed = _decode_redis_json(raw)
                if parsed is not None:
                    cached_by_slug[str(defn["slug"])] = parsed
        except Exception as exc:
            logger.debug("scout_deck: redis mget decoys failed: %s", type(exc).__name__)

    picked: list[dict[str, Any]] = []
    fallback_defs: list[tuple[dict[str, Any], list[int]]] = []

    for defn in defs:
        slug = str(defn["slug"])
        entry = cached_by_slug.get(slug)
        members = _members_from_cached_feed_item(entry) if entry else []
        if len(members) >= 3:
            feed_item = entry.get("feed_item") if isinstance(entry, Mapping) else {}
            data = feed_item.get("data") if isinstance(feed_item, Mapping) else {}
            roundup = data.get("roundup") if isinstance(data, Mapping) else {}
            card = _sanitize_card_entry(
                title=defn.get("name") or (data.get("title") if isinstance(data, Mapping) else None),
                kicker=(roundup.get("kicker") if isinstance(roundup, Mapping) else None) or defn.get("kicker"),
                category=defn.get("category"),
                summary=defn.get("why_better_together") or defn.get("footer") or defn.get("section_title") or "",
                look=defn.get("look") or (roundup.get("look") if isinstance(roundup, Mapping) else None) or "bars",
                members=members,
            )
            picked.append(
                {
                    "origin": "public",
                    "slug": slug,
                    "name": card["title"],
                    "category": card["category"],
                    "rule_definition": defn,
                    "card": card,
                }
            )
            if len(picked) >= needed:
                return picked
        else:
            raw_cands = (defn.get("rule") or {}).get("candidates") or ()
            num_ids = [int(x) for x in raw_cands if isinstance(x, int)]
            if len(num_ids) >= 3:
                fallback_defs.append((defn, num_ids))

    if len(picked) < needed and fallback_defs:
        all_ids = [mid for _, mids in fallback_defs for mid in mids]
        by_id = await _load_markets_by_id(db, all_ids)
        for defn, mids in fallback_defs:
            rows = [by_id[mid] for mid in mids if mid in by_id]
            if len(rows) < 3:
                continue
            members = [_serialize_market_row_member(row) for row in rows]
            card = _sanitize_card_entry(
                title=defn.get("name"),
                kicker=defn.get("kicker"),
                category=defn.get("category"),
                summary=defn.get("why_better_together") or defn.get("footer") or defn.get("section_title") or "",
                look=defn.get("look") or "bars",
                members=members,
            )
            picked.append(
                {
                    "origin": "public",
                    "slug": str(defn["slug"]),
                    "name": card["title"],
                    "category": card["category"],
                    "rule_definition": defn,
                    "card": card,
                }
            )
            if len(picked) >= needed:
                break

    return picked


def _persist_sealed_key(
    deck_date: str,
    sealed_payload: Mapping[str, Any],
    *,
    redis_client: Any = None,
) -> bool:
    rc = redis_client
    if rc is None:
        try:
            from app.tasks.redis_state import get_redis_client

            rc = get_redis_client(fast_fail=True)
        except Exception:
            rc = None
    if rc is None or not hasattr(rc, "set"):
        return False
    key = f"{SCOUT_DECK_KEY_REDIS_PREFIX}:{deck_date}"
    encoded = json.dumps(dict(sealed_payload), separators=(",", ":"), sort_keys=True)
    try:
        rc.set(key, encoded, ex=SCOUT_DECK_KEY_TTL_S)
    except TypeError:
        rc.set(key, encoded)
    return True


async def build_scout_morning_deck(
    db: AsyncSession,
    *,
    deck_date: Optional[str] = None,
    redis_client: Any = None,
    staged_override: Optional[Sequence[Mapping[str, Any]]] = None,
    public_override: Optional[Sequence[Mapping[str, Any]]] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Assemble and cache the blind morning deck (staged + equal public decoys)."""
    if staged_override is not None:
        resolved_date = deck_date or _today_pt_date(now)
        raw_staged = list(staged_override)
    else:
        resolved_date, artifact = read_nightly_scout_artifact(
            deck_date,
            redis_client=redis_client,
            now=now,
        )
        raw_staged = list((artifact or {}).get("staged_sets") or [])

    raw_staged = [s for s in raw_staged if isinstance(s, Mapping)][:SCOUT_MAX_NEW_SETS_PER_DAY]

    if not raw_staged:
        return {
            "status": "empty",
            "deck_date": resolved_date,
            "staged_count": 0,
            "decoy_count": 0,
            "total_count": 0,
            "sealed_key_sha256": None,
            "items": [],
            "message": "No staged scout sets yet for this date.",
        }

    # Batch-hydrate staged set member prices/outcomes in ONE indexed DB query.
    staged_market_ids = [
        int(m["market_id"])
        for s in raw_staged
        for m in (s.get("members") or ())
        if isinstance(m, Mapping) and isinstance(m.get("market_id"), int)
    ]
    live_markets = await _load_markets_by_id(db, staged_market_ids) if staged_market_ids else {}

    staged_entries: list[dict[str, Any]] = []
    for s in raw_staged:
        members: list[dict[str, Any]] = []
        for m in s.get("members") or ():
            if not isinstance(m, Mapping):
                continue
            mid = m.get("market_id")
            if isinstance(mid, int) and mid in live_markets:
                members.append(_serialize_market_row_member(live_markets[mid]))
            elif m.get("title"):
                members.append(
                    {
                        "title": _clean_blind_text(m.get("title")),
                        "leading_outcome": _clean_blind_text(m.get("leading_outcome") or "Yes"),
                        "probability": _safe_float(m.get("probability")),
                        "change_24h": _safe_float(m.get("change_24h")),
                        "image_url": m.get("image_url"),
                    }
                )
        card = _sanitize_card_entry(
            title=s.get("name"),
            kicker=s.get("kicker"),
            category=s.get("category"),
            summary=s.get("why_better_together") or "",
            look=s.get("look") or "bars",
            members=members,
        )
        staged_entries.append(
            {
                "origin": "scout",
                "slug": str(s.get("slug") or ""),
                "name": card["title"],
                "category": card["category"],
                "rule_definition": dict(s.get("rule_definition") or {}),
                "card": card,
            }
        )

    needed_decoys = len(staged_entries)
    if public_override is not None:
        decoy_entries = [
            {
                "origin": "public",
                "slug": str(p.get("slug") or ""),
                "name": _clean_blind_text(p.get("name")),
                "category": _clean_blind_text(p.get("category") or "other").lower(),
                "rule_definition": dict(p.get("rule_definition") or {}),
                "card": _sanitize_card_entry(
                    title=p.get("name"),
                    kicker=p.get("kicker"),
                    category=p.get("category"),
                    summary=p.get("summary") or "",
                    look=p.get("look") or "bars",
                    members=p.get("members") or (),
                ),
            }
            for p in list(public_override)[:needed_decoys]
        ]
    else:
        decoy_entries = await load_public_decoy_entries(
            needed_decoys,
            resolved_date,
            db=db,
            redis_client=redis_client,
        )

    combined = staged_entries + decoy_entries
    hmac_key = _deck_hmac_bytes()
    combined.sort(
        key=lambda entry: hmac.new(
            hmac_key,
            f"{resolved_date}|{entry['slug']}|{entry['name']}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    )

    items: list[dict[str, Any]] = []
    key_entries: dict[str, dict[str, Any]] = {}
    for idx, entry in enumerate(combined, start=1):
        item_id = f"s{idx:02d}"
        card = dict(entry["card"])
        card["item_id"] = item_id
        items.append(card)
        key_entries[item_id] = {
            "origin": entry["origin"],
            "slug": entry["slug"],
            "name": entry["name"],
            "category": entry["category"],
            "rule_definition": entry["rule_definition"],
        }

    canonical_entries = json.dumps(key_entries, separators=(",", ":"), sort_keys=True)
    sealed_sha256 = hashlib.sha256(canonical_entries.encode("utf-8")).hexdigest()
    sealed_doc = {
        "deck_date": resolved_date,
        "created_at": (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        "sealed_key_sha256": sealed_sha256,
        "entries": key_entries,
    }
    _persist_sealed_key(resolved_date, sealed_doc, redis_client=redis_client)

    return {
        "status": "ready",
        "deck_date": resolved_date,
        "staged_count": len(staged_entries),
        "decoy_count": len(decoy_entries),
        "total_count": len(items),
        "sealed_key_sha256": sealed_sha256,
        "items": items,
        "message": None,
    }
