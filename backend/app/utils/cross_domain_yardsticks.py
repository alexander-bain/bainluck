"""Dynamic ``cross_domain_yardsticks`` ("As likely as") grouped-card producer (#12288 Wave 2, Idea #13).

PILLAR: DISCOVER · MATCHING · TRUTH
SHIP: Cross-domain yardstick container ("Around a 46% chance right now") that
discovers the tightest contested probability band (±1.5 points inside 22%–78%)
containing at least 3 distinct domains (e.g., NBA/NFL game, Economics IPO cap,
Tech AI milestone, Culture Grammy race), seating at most one item per domain,
routing game rows to ``/events/{id}`` and market rows to ``/futures/{id}``,
strictly excluding untraded/quiet markets and unpriced games, and writing a
plain-English ``context_line`` naming the shared percentage band.

Publication gate: candidate definition lives in ``backend/data/discover/candidates/``
and is NOT registered in ``ROUNDUP_PRODUCERS`` until turned on by Fable.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from app.utils.container_presentation import (
    MEMBER_EVENT,
    MEMBER_MARKET,
    event_destination,
    market_destination,
)
from app.utils.roundup_containers import (
    RoundupMembers,
    RoundupProducer,
    RoundupRefusal,
    compose_roundup_container,
    compose_roundup_feed_item,
    validate_roundup_definition,
)

__all__ = [
    "CANDIDATE_AS_LIKELY_AS_PATH",
    "CANDIDATE_AS_LIKELY_AS_ROWS_PATH",
    "PRODUCER_KIND_CROSS_DOMAIN_YARDSTICKS",
    "YardstickItem",
    "build_cross_domain_yardsticks_CandidatePack",
    "build_cross_domain_yardsticks_producer",
    "compose_yardsticks_card_and_container",
    "load_candidate_definition",
    "load_candidate_eval_rows",
    "produce_cross_domain_yardsticks",
    "select_cross_domain_yardsticks",
]

PRODUCER_KIND_CROSS_DOMAIN_YARDSTICKS = "cross_domain_yardsticks"

_CANDIDATES_DIR = Path(__file__).resolve().parents[2] / "data" / "discover" / "candidates"
CANDIDATE_AS_LIKELY_AS_PATH = _CANDIDATES_DIR / "roundup-as-likely-as.json"
CANDIDATE_AS_LIKELY_AS_ROWS_PATH = _CANDIDATES_DIR / "roundup-as-likely-as-rows.json"

_FORBIDDEN_COPY_RE = re.compile(
    r"\b(?:questions?|stale|venues?|kalshi|polymarket|opened)\b",
    re.IGNORECASE,
)

_CRYPTO_RE = re.compile(
    r"\b(?:bitcoin|btc|ethereum|eth|solana|dogecoin|xrp|crypto)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class YardstickItem:
    item_id: int
    member_type: str  # "event" or "market"
    domain: str
    domain_badge: str
    label: str
    probability: float
    activity_weight: float
    destination: dict[str, Any]
    card: Mapping[str, Any]


def _assert_clean_copy(text: str) -> str:
    cleaned = " ".join(str(text or "").split())
    if _FORBIDDEN_COPY_RE.search(cleaned):
        raise ValueError(f"Forbidden copy token in reader text: {cleaned!r}")
    return cleaned


def _parse_iso_utc(raw: Any) -> Optional[datetime]:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo is not None else raw.replace(tzinfo=timezone.utc)
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _normalize_domain(raw_cat: str) -> tuple[str, str]:
    low = str(raw_cat or "").strip().lower()
    if low.startswith(("basketball", "americanfootball", "icehockey", "baseball", "soccer", "mma", "tennis")) or low == "sports":
        return "sports", "Sports"
    if low in {"economics", "economy", "finance", "business"}:
        return "economics", "Economy"
    if low in {"tech", "technology", "science", "ai"}:
        return "tech", "Tech"
    if low in {"entertainment", "culture", "music", "movies", "awards"}:
        return "entertainment", "Culture"
    if low in {"politics", "geopolitics", "elections", "world"}:
        return "politics", "World"
    if low in {"weather", "climate"}:
        return "weather", "Weather"
    return low or "general", (low.capitalize() if low else "General")


def _is_trading_market(
    item: Mapping[str, Any],
    *,
    now: Optional[datetime],
    max_quote_age_hours: float,
    max_trade_age_days: float,
    min_volume_24h: float,
) -> bool:
    status = str(item.get("status") or "open").strip().lower()
    if status not in {"open", "active"}:
        return False
    if item.get("prices_withheld") or item.get("is_trading") is False:
        return False
    quiet = item.get("quiet_days") if item.get("quiet_days") is not None else item.get("quiet_since_days")
    if quiet is not None and float(quiet) >= 6.0:
        return False
    if item.get("volume") is not None and float(item["volume"]) <= 0.0:
        return False
    v24 = item.get("volume_24h") if item.get("volume_24h") is not None else item.get("volume24hr")
    if v24 is not None and float(v24) < float(min_volume_24h):
        return False

    ref_now = _parse_iso_utc(now) if now is not None else None
    if ref_now is not None:
        lt = _parse_iso_utc(item.get("last_trade_at") or item.get("last_traded_at"))
        if lt is not None and (ref_now - lt).total_seconds() / 86400.0 > float(max_trade_age_days):
            return False
        qt = _parse_iso_utc(
            item.get("price_observed_at") or item.get("updated_at") or item.get("last_updated")
        )
        if qt is not None and (ref_now - qt).total_seconds() / 3600.0 > float(max_quote_age_hours):
            return False
    return True


def _extract_yardstick_candidates(
    items: Sequence[Mapping[str, Any]],
    *,
    now: Optional[datetime],
    min_prob: float,
    max_prob: float,
    max_quote_age_hours: float,
    max_trade_age_days: float,
    min_volume_24h: float,
) -> list[YardstickItem]:
    pool: list[YardstickItem] = []
    for raw in items:
        if not isinstance(raw, Mapping) or not isinstance(raw.get("id"), int):
            continue
        item_id = int(raw["id"])
        kind = str(raw.get("item_type") or ("event" if raw.get("home_team") else "market")).lower()

        if kind == "event":
            status = str(raw.get("status") or "").strip().lower()
            if status not in {"scheduled", "upcoming", "live"}:
                continue
            if raw.get("prices_withheld") or raw.get("is_trading") is False:
                continue
            ht = str(raw.get("home_team") or "").strip()
            at = str(raw.get("away_team") or "").strip()
            if not ht or not at or _FORBIDDEN_COPY_RE.search(ht) or _FORBIDDEN_COPY_RE.search(at):
                continue
            odds = raw.get("current_odds") or {}
            hp = raw.get("hero_probability")
            if hp is None and isinstance(odds, Mapping):
                hp = odds.get("home_probability")
            ap = raw.get("hero_probability_away")
            if ap is None and isinstance(odds, Mapping):
                ap = odds.get("away_probability")
            if hp is None:
                continue
            hp_f = float(hp)
            ap_f = float(ap) if ap is not None else (1.0 - hp_f)
            dom_key, dom_badge = _normalize_domain(str(raw.get("sport") or "sports"))
            for side_label, p_val in ((f"{ht} beat {at}", hp_f), (f"{at} win at {ht}", ap_f)):
                if min_prob <= p_val <= max_prob:
                    pool.append(
                        YardstickItem(
                            item_id=item_id,
                            member_type=MEMBER_EVENT,
                            domain=dom_key,
                            domain_badge=dom_badge,
                            label=side_label,
                            probability=p_val,
                            activity_weight=5000.0,
                            destination=event_destination(item_id),
                            card=dict(raw),
                        )
                    )
        else:
            title = str(raw.get("name") or raw.get("title") or "").strip().rstrip("?")
            if not title or _CRYPTO_RE.search(title) or _FORBIDDEN_COPY_RE.search(title):
                continue
            if not _is_trading_market(
                raw,
                now=now,
                max_quote_age_hours=max_quote_age_hours,
                max_trade_age_days=max_trade_age_days,
                min_volume_24h=min_volume_24h,
            ):
                continue
            dom_key, dom_badge = _normalize_domain(
                str(raw.get("category") or raw.get("sport") or "general")
            )
            v24 = float(raw.get("volume_24h") or raw.get("volume24hr") or 250.0)
            outcomes = raw.get("outcomes") or raw.get("top_outcomes") or ()
            if not isinstance(outcomes, Sequence) or not outcomes:
                continue
            # Use leading/featured contender so tail outcomes don't manufacture fake ties
            top_out = outcomes[0]
            if not isinstance(top_out, Mapping) or top_out.get("probability") is None:
                continue
            p_val = float(top_out["probability"])
            if not (min_prob <= p_val <= max_prob):
                continue
            oname = str(top_out.get("name") or "").strip()
            if not oname or oname.lower() in {"no", "other", "none", "field"} or _FORBIDDEN_COPY_RE.search(oname):
                continue
            label = title if oname.lower() == "yes" else f"{title} — {oname}"
            pool.append(
                YardstickItem(
                    item_id=item_id,
                    member_type=MEMBER_MARKET,
                    domain=dom_key,
                    domain_badge=dom_badge,
                    label=label,
                    probability=p_val,
                    activity_weight=v24,
                    destination=market_destination(item_id),
                    card=dict(raw),
                )
            )
    return pool


def select_cross_domain_yardsticks(
    items: Sequence[Mapping[str, Any]],
    *,
    now: Optional[datetime] = None,
    band_half_width: float = 0.015,
    min_domains: int = 3,
    max_card_rows: int = 4,
    min_prob: float = 0.22,
    max_prob: float = 0.78,
    max_quote_age_hours: float = 24.0,
    max_trade_age_days: float = 7.0,
    min_volume_24h: float = 100.0,
) -> RoundupMembers | RoundupRefusal:
    pool = _extract_yardstick_candidates(
        items,
        now=now,
        min_prob=min_prob,
        max_prob=max_prob,
        max_quote_age_hours=max_quote_age_hours,
        max_trade_age_days=max_trade_age_days,
        min_volume_24h=min_volume_24h,
    )
    if not pool:
        return RoundupRefusal([("no_trading_yardstick_candidates", 0)])

    best_center: Optional[int] = None
    best_band: list[YardstickItem] = []
    best_score_tuple: tuple[int, float, float] = (-1, -1.0, -1.0)

    # Scan integer percentage centers from 25% to 75%, preferring centers near 50%
    for pct in range(25, 76):
        center = pct / 100.0
        by_domain: dict[str, YardstickItem] = {}
        for cand in pool:
            diff = abs(cand.probability - center)
            if diff > float(band_half_width):
                continue
            prev = by_domain.get(cand.domain)
            if prev is None or (diff, -cand.activity_weight) < (
                abs(prev.probability - center),
                -prev.activity_weight,
            ):
                by_domain[cand.domain] = cand

        if len(by_domain) < max(3, int(min_domains)):
            continue

        chosen = sorted(
            by_domain.values(),
            key=lambda c: (abs(c.probability - center), -c.activity_weight, c.domain),
        )[: max(3, int(max_card_rows))]
        spread = max(c.probability for c in chosen) - min(c.probability for c in chosen)
        centrality = 1.0 - abs(center - 0.5)
        rank_tuple = (len(chosen), round(centrality, 3), -round(spread, 4))
        if rank_tuple > best_score_tuple:
            best_score_tuple = rank_tuple
            best_center = pct
            best_band = chosen

    if best_center is None or len(best_band) < max(3, int(min_domains)):
        return RoundupRefusal([("no_multi_domain_band_found", int(min_domains))])

    domains_str = ", ".join(c.domain_badge for c in best_band[:-1]) + f", and {best_band[-1].domain_badge}"
    half_pts = round(band_half_width * 100, 1)
    half_txt = str(int(half_pts)) if half_pts.is_integer() else f"{half_pts:.1f}"
    spread_pts = round(
        (max(c.probability for c in best_band) - min(c.probability for c in best_band)) * 100,
        1,
    )
    spread_txt = str(int(spread_pts)) if spread_pts.is_integer() else f"{spread_pts:.1f}"

    card_title = f"Around a {best_center}% chance right now"
    context_line = _assert_clean_copy(
        f"{len(best_band)} unrelated events across {domains_str} trading within ±{half_txt} points "
        f"of {best_center}% ({spread_txt}-pt spread across all {len(best_band)} boards) — "
        f"pairing familiar game odds with unfamiliar forecasts."
    )
    footer = _assert_clean_copy(
        f"Independent markets across {len(best_band)} domains · matched within ±{half_txt} points"
    )

    rows = [
        {
            "id": c.item_id,
            **({"event_id": c.item_id} if c.member_type == "event" else {"market_id": c.item_id}),
            "member_type": c.member_type,
            "domain": c.domain_badge,
            "label": _assert_clean_copy(f"{c.domain_badge}: {c.label}"),
            "subject": _assert_clean_copy(c.label),
            "probability": round(c.probability, 4),
            "rendered_percent": int(round(c.probability * 100)),
            "destination": c.destination,
        }
        for c in best_band
    ]

    members = [
        {
            "id": c.item_id,
            "type": c.member_type,
            "destination": c.destination,
            "card": dict(c.card),
        }
        for c in best_band
    ]
    contrib_ids = [c.item_id for c in best_band]

    return RoundupMembers(
        members=members,
        rows=rows,
        footer=footer,
        count_line=f"{len(best_band)} domains at ~{best_center}%",
        title=_assert_clean_copy(card_title),
        kicker="PERSPECTIVE · AS LIKELY AS",
        revision_ids=contrib_ids,
        sections=(
            {
                "title": f"Events priced near {best_center}%",
                "context_line": context_line,
                "member_ids": contrib_ids,
                "members": members,
            },
        ),
    )


async def produce_cross_domain_yardsticks(
    db: Any,
    *,
    rule: Optional[Mapping[str, Any]] = None,
    now: Optional[datetime] = None,
) -> RoundupMembers | RoundupRefusal:
    cfg = dict(rule or {})
    band_hw = float(cfg.get("band_half_width") or 0.015)
    min_d = int(cfg.get("min_domains") or 3)
    max_r = int(cfg.get("max_card_rows") or 4)
    min_p = float(cfg.get("min_prob") or 0.22)
    max_p = float(cfg.get("max_prob") or 0.78)
    max_q = float(cfg.get("max_quote_age_hours") or 24.0)
    max_t = float(cfg.get("max_trade_age_days") or 7.0)
    min_v = float(cfg.get("min_volume_24h") or 100.0)
    if isinstance(db, (list, tuple)):
        return select_cross_domain_yardsticks(
            db,
            now=now,
            band_half_width=band_hw,
            min_domains=min_d,
            max_card_rows=max_r,
            min_prob=min_p,
            max_prob=max_p,
            max_quote_age_hours=max_q,
            max_trade_age_days=max_t,
            min_volume_24h=min_v,
        )
    from datetime import timedelta, timezone
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import selectinload

    if not isinstance(db, AsyncSession):
        return RoundupRefusal([("unsupported_session", type(db).__name__)])

    from app.models.models import Event, FuturesMarket
    from app.routes.containers import _hydrate_event_cards

    effective_now = now or datetime.now(timezone.utc)
    pool_items: list[dict[str, Any]] = []

    ev_res = await db.execute(
        select(Event.id)
        .where(
            Event.status.in_(("scheduled", "upcoming")),
            Event.commence_time >= effective_now,
            Event.commence_time <= effective_now + timedelta(days=5),
        )
        .order_by(Event.commence_time.asc())
        .limit(40)
    )
    ev_ids = [int(r[0]) for r in ev_res.all()]
    cards_by_id, _ = await _hydrate_event_cards(db, ev_ids) if ev_ids else ({}, set())
    for eid in ev_ids:
        if eid in cards_by_id:
            card_d = dict(cards_by_id[eid])
            card_d["item_type"] = "event"
            pool_items.append(card_d)

    mkt_res = await db.execute(
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(
            FuturesMarket.status == "open",
            FuturesMarket.sport_id.is_(None),
            FuturesMarket.volume_24h >= min_v,
        )
        .order_by(FuturesMarket.volume_24h.desc().nullslast())
        .limit(60)
    )
    for m in mkt_res.scalars().all():
        pool_items.append(
            {
                "id": int(m.id),
                "item_type": "market",
                "source": m.source,
                "category": m.category,
                "status": m.status,
                "name": m.name,
                "volume": m.volume,
                "volume_24h": m.volume_24h,
                "updated_at": m.updated_at.isoformat() if m.updated_at else None,
                "outcomes": [
                    {"id": int(o.id), "name": o.name, "probability": o.current_probability}
                    for o in (m.outcomes or [])
                ],
            }
        )

    return select_cross_domain_yardsticks(
        pool_items,
        now=effective_now,
        band_half_width=band_hw,
        min_domains=min_d,
        max_card_rows=max_r,
        min_prob=min_p,
        max_prob=max_p,
        max_quote_age_hours=max_q,
        max_trade_age_days=max_t,
        min_volume_24h=min_v,
    )


def load_candidate_definition(
    path: Path = CANDIDATE_AS_LIKELY_AS_PATH,
) -> dict[str, Any]:
    defn = json.loads(path.read_text(encoding="utf-8"))
    validate_roundup_definition(defn)
    return defn


def load_candidate_eval_rows(
    path: Path = CANDIDATE_AS_LIKELY_AS_ROWS_PATH,
) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_cross_domain_yardsticks_producer(
    defn: Optional[Mapping[str, Any]] = None,
) -> RoundupProducer:
    resolved = dict(defn) if defn is not None else load_candidate_definition()
    validate_roundup_definition(resolved)
    rule = dict(resolved.get("rule") or {})

    async def _produce(db: Any) -> RoundupMembers | RoundupRefusal:
        return await produce_cross_domain_yardsticks(db, rule=rule)

    return RoundupProducer(
        slug=str(resolved["slug"]),
        name=str(resolved["name"]),
        kind=str(resolved.get("kind") or "roundup"),
        category=str(resolved["category"]),
        section_title=str(resolved["section_title"]),
        footer=str(resolved["footer"]),
        produce=_produce,
        membership=str(resolved.get("membership") or PRODUCER_KIND_CROSS_DOMAIN_YARDSTICKS),
        relations=tuple(resolved["relations"]),
        level=str(resolved["level"]),
        rule=rule,
        tag=resolved.get("tag"),
        kicker=str(resolved.get("kicker") or "PERSPECTIVE · AS LIKELY AS"),
        order=str(resolved.get("order") or "sequence"),
        score=float(resolved.get("score") or 92.5),
        enabled=(lambda: bool(resolved["enabled"])) if "enabled" in resolved else None,
    )


def compose_yardsticks_card_and_container(
    producer: RoundupProducer,
    members: RoundupMembers,
) -> tuple[dict[str, Any], dict[str, Any]]:
    feed_item = compose_roundup_feed_item(producer, members)
    container = compose_roundup_container(producer, members)
    if feed_item is None or container is None:
        raise ValueError("Expected non-empty RoundupMembers")
    context_line = _assert_clean_copy(str(members.sections[0].get("context_line") or ""))
    feed_item["context_summary"] = context_line
    feed_item["data"]["roundup"]["context_line"] = context_line
    feed_item["data"]["roundup"]["subtitle"] = context_line
    feed_item["data"]["roundup"]["order"] = "sequence"
    container["context_line"] = context_line
    return feed_item, container


def build_cross_domain_yardsticks_CandidatePack(
    producer: RoundupProducer,
    members: RoundupMembers,
) -> dict[str, Any]:
    feed_item, _ = compose_yardsticks_card_and_container(producer, members)
    roundup = feed_item["data"]["roundup"]
    rows = list(roundup["rows"])
    best_row = min(rows, key=lambda r: abs(float(r["probability"]) - 0.5))
    return {
        "item_key": producer.slug,
        "kind": PRODUCER_KIND_CROSS_DOMAIN_YARDSTICKS,
        "kind_verdict": "serve",
        "reader_reachable": False,
        "proposed_card": {
            "slug": producer.slug,
            "kicker": roundup["kicker"],
            "title": feed_item["data"]["title"],
            "context_line": roundup["context_line"],
            "footer": roundup["footer"],
            "rows": rows,
        },
        "best_single": {
            "id": best_row["id"],
            "member_type": best_row["member_type"],
            "subject": best_row["subject"],
            "probability": best_row["probability"],
        },
    }
