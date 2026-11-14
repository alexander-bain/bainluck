"""Dynamic ``big_movers_today`` grouped-card producer (#12288 Wave 2, Idea #14).

PILLAR: DISCOVER · MATCHING · TRUTH
SHIP: Cross-category "Big movers today" container surfacing actively trading
markets whose leading contender or Yes outcome shifted by 6+ percentage points
over the past 24 hours, deduplicated by market family so one ladder never takes
two rows, strictly excluding untraded/quiet markets, and stating in plain
English how members were chosen and what moved most.

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

from app.utils.container_presentation import market_destination
from app.utils.roundup_containers import (
    RoundupMembers,
    RoundupProducer,
    RoundupRefusal,
    compose_roundup_container,
    compose_roundup_feed_item,
    validate_roundup_definition,
)

__all__ = [
    "CANDIDATE_BIG_MOVERS_TODAY_PATH",
    "CANDIDATE_BIG_MOVERS_TODAY_ROWS_PATH",
    "MoverCandidate",
    "PRODUCER_KIND_BIG_MOVERS_TODAY",
    "build_big_movers_today_CandidatePack",
    "build_big_movers_today_producer",
    "compose_big_movers_card_and_container",
    "is_actively_trading_market",
    "load_candidate_definition",
    "load_candidate_eval_rows",
    "produce_big_movers_today",
    "select_big_movers_today",
]

PRODUCER_KIND_BIG_MOVERS_TODAY = "big_movers_today"

_CANDIDATES_DIR = Path(__file__).resolve().parents[2] / "data" / "discover" / "candidates"
CANDIDATE_BIG_MOVERS_TODAY_PATH = _CANDIDATES_DIR / "roundup-big-movers-today.json"
CANDIDATE_BIG_MOVERS_TODAY_ROWS_PATH = _CANDIDATES_DIR / "roundup-big-movers-today-rows.json"

_FORBIDDEN_COPY_RE = re.compile(
    r"\b(?:questions?|stale|venues?|kalshi|polymarket|opened)\b",
    re.IGNORECASE,
)

_CRYPTO_TICKER_RE = re.compile(
    r"\b(?:bitcoin|btc|ethereum|eth|solana|dogecoin|xrp|crypto)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MoverCandidate:
    market_id: int
    family_key: str
    market_name: str
    outcome_name: str
    display_label: str
    probability: float
    delta: float
    abs_delta_pts: int
    signed_delta_pts: int
    category: str
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


def is_actively_trading_market(
    market: Mapping[str, Any],
    *,
    now: Optional[datetime] = None,
    max_quote_age_hours: float = 24.0,
    max_trade_age_days: float = 7.0,
    min_volume_24h: float = 100.0,
) -> bool:
    """Return True only if the market is open and actively trading."""
    status = str(market.get("status") or "open").strip().lower()
    if status not in {"open", "active"}:
        return False
    if market.get("prices_withheld") or market.get("is_trading") is False:
        return False

    quiet_days = market.get("quiet_days")
    if quiet_days is None:
        quiet_days = market.get("quiet_since_days")
    if quiet_days is not None:
        try:
            if float(quiet_days) >= 6.0:
                return False
        except (TypeError, ValueError):
            return False

    vol_total = market.get("volume")
    if vol_total is not None:
        try:
            if float(vol_total) <= 0.0:
                return False
        except (TypeError, ValueError):
            return False

    vol_24h = market.get("volume_24h")
    if vol_24h is None:
        vol_24h = market.get("volume24hr")
    if vol_24h is not None:
        try:
            if float(vol_24h) < float(min_volume_24h):
                return False
        except (TypeError, ValueError):
            return False

    ref_now = _parse_iso_utc(now) if now is not None else None
    if ref_now is not None:
        last_trade = _parse_iso_utc(
            market.get("last_trade_at") or market.get("last_traded_at")
        )
        if last_trade is not None:
            age_days = (ref_now - last_trade).total_seconds() / 86400.0
            if age_days > float(max_trade_age_days):
                return False

        quote_ts = _parse_iso_utc(
            market.get("price_observed_at")
            or market.get("updated_at")
            or market.get("last_updated")
        )
        if quote_ts is not None:
            age_hours = (ref_now - quote_ts).total_seconds() / 3600.0
            if age_hours > float(max_quote_age_hours):
                return False

    return True


def _clean_market_subject(market_name: str, outcome_name: str) -> Optional[str]:
    m_clean = re.sub(r"\s+", " ", str(market_name or "").strip()).rstrip("?")
    o_clean = re.sub(r"\s+", " ", str(outcome_name or "").strip())
    if not m_clean or not o_clean:
        return None
    if _FORBIDDEN_COPY_RE.search(m_clean) or _FORBIDDEN_COPY_RE.search(o_clean):
        return None
    low_out = o_clean.lower()
    if low_out in {"no", "other", "none", "field"} or low_out.startswith("not "):
        return None
    if low_out == "yes" or low_out == m_clean.lower():
        return m_clean
    return f"{m_clean} — {o_clean}"


def _extract_delta(outcome: Mapping[str, Any], market: Mapping[str, Any]) -> Optional[float]:
    for key in ("movement", "change_24h", "price_change_24h", "delta_24h", "oneDayPriceChange"):
        raw = outcome.get(key)
        if raw is not None:
            try:
                return float(raw)
            except (TypeError, ValueError):
                pass
    for key in ("movement", "change_24h", "price_change_24h", "delta_24h"):
        raw = market.get(key)
        if raw is not None:
            try:
                return float(raw)
            except (TypeError, ValueError):
                pass
    return None


def select_big_movers_today(
    markets: Sequence[Mapping[str, Any]],
    *,
    now: Optional[datetime] = None,
    min_abs_delta: float = 0.06,
    min_members: int = 3,
    max_card_rows: int = 5,
    min_prob: float = 0.03,
    max_prob: float = 0.97,
    max_quote_age_hours: float = 24.0,
    max_trade_age_days: float = 7.0,
    min_volume_24h: float = 100.0,
) -> RoundupMembers | RoundupRefusal:
    best_by_family: dict[str, MoverCandidate] = {}

    for m in markets:
        if not isinstance(m, Mapping) or not isinstance(m.get("id"), int):
            continue
        title = str(m.get("name") or m.get("title") or "").strip()
        if not title or _CRYPTO_TICKER_RE.search(title):
            continue
        if not is_actively_trading_market(
            m,
            now=now,
            max_quote_age_hours=max_quote_age_hours,
            max_trade_age_days=max_trade_age_days,
            min_volume_24h=min_volume_24h,
        ):
            continue

        outcomes = m.get("outcomes") or m.get("top_outcomes") or ()
        if not isinstance(outcomes, Sequence):
            continue

        family_key = str(
            m.get("group_id") or m.get("canonical_market_key") or f"market:{int(m['id'])}"
        )
        cat = str(m.get("category") or m.get("sport_name") or "general").strip().lower()

        for out in outcomes:
            if not isinstance(out, Mapping):
                continue
            p_raw = out.get("probability")
            if p_raw is None:
                continue
            try:
                prob = float(p_raw)
            except (TypeError, ValueError):
                continue
            if not (min_prob <= prob <= max_prob):
                continue

            delta = _extract_delta(out, m)
            if delta is None or abs(delta) < float(min_abs_delta):
                continue

            signed_pts = int(round(delta * 100))
            abs_pts = abs(signed_pts)
            if abs_pts < int(round(min_abs_delta * 100)):
                continue

            label = _clean_market_subject(title, str(out.get("name") or ""))
            if not label:
                continue

            cand = MoverCandidate(
                market_id=int(m["id"]),
                family_key=family_key,
                market_name=title,
                outcome_name=str(out.get("name") or "").strip(),
                display_label=label,
                probability=prob,
                delta=delta,
                abs_delta_pts=abs_pts,
                signed_delta_pts=signed_pts,
                category=cat,
                card=dict(m),
            )
            prev = best_by_family.get(family_key)
            if prev is None or (abs(cand.delta), cand.probability) > (
                abs(prev.delta),
                prev.probability,
            ):
                best_by_family[family_key] = cand

    if len(best_by_family) < max(2, int(min_members)):
        return RoundupRefusal(
            [("insufficient_trading_movers", len(best_by_family), int(min_members))]
        )

    ordered = sorted(
        best_by_family.values(),
        key=lambda c: (-abs(c.delta), -c.abs_delta_pts, c.market_id),
    )
    shown = ordered[: max(2, int(max_card_rows))]
    top = shown[0]
    top_sign = f"+{top.signed_delta_pts}" if top.signed_delta_pts > 0 else f"{top.signed_delta_pts}"
    min_pts_int = int(round(min_abs_delta * 100))

    context_line = _assert_clean_copy(
        f"Actively trading markets with the sharpest 24-hour shifts ({min_pts_int}+ points), "
        f"ordered by size of move — led by {top.display_label} "
        f"({top_sign} pts to {int(round(top.probability * 100))}%)."
    )
    footer = _assert_clean_copy(
        "24-hour shift in percentage points · actively trading markets only"
    )

    rows = []
    for c in shown:
        pts_text = f"+{c.signed_delta_pts} pts" if c.signed_delta_pts > 0 else f"{c.signed_delta_pts} pts"
        rows.append(
            {
                "market_id": c.market_id,
                "label": _assert_clean_copy(c.display_label),
                "outcome": c.outcome_name,
                "category": c.category,
                "probability": round(c.probability, 4),
                "rendered_percent": int(round(c.probability * 100)),
                "delta_points": c.signed_delta_pts,
                "delta_label": _assert_clean_copy(pts_text),
                "destination": market_destination(c.market_id),
            }
        )

    members = [{"id": c.market_id, "type": "futures", "card": dict(c.card)} for c in shown]
    contrib_ids = [c.market_id for c in shown]

    return RoundupMembers(
        members=members,
        rows=rows,
        footer=footer,
        count_line=f"{len(ordered)} active movers",
        title="Big movers today",
        kicker="PULSE · BIGGEST 24H SHIFTS",
        revision_ids=contrib_ids,
        sections=(
            {
                "title": "Biggest 24-hour market shifts",
                "context_line": context_line,
                "member_ids": contrib_ids,
            },
        ),
    )


async def produce_big_movers_today(
    db: Any,
    *,
    rule: Optional[Mapping[str, Any]] = None,
    now: Optional[datetime] = None,
) -> RoundupMembers | RoundupRefusal:
    cfg = dict(rule or {})
    if isinstance(db, (list, tuple)):
        return select_big_movers_today(
            db,
            now=now,
            min_abs_delta=float(cfg.get("min_abs_delta") or 0.06),
            min_members=int(cfg.get("min_members") or 3),
            max_card_rows=int(cfg.get("max_card_rows") or 5),
            min_prob=float(cfg.get("min_prob") or 0.03),
            max_prob=float(cfg.get("max_prob") or 0.97),
            max_quote_age_hours=float(cfg.get("max_quote_age_hours") or 24.0),
            max_trade_age_days=float(cfg.get("max_trade_age_days") or 7.0),
            min_volume_24h=float(cfg.get("min_volume_24h") or 100.0),
        )
    return RoundupRefusal([("unsupported_session", type(db).__name__)])


def load_candidate_definition(
    path: Path = CANDIDATE_BIG_MOVERS_TODAY_PATH,
) -> dict[str, Any]:
    defn = json.loads(path.read_text(encoding="utf-8"))
    validate_roundup_definition(defn)
    return defn


def load_candidate_eval_rows(
    path: Path = CANDIDATE_BIG_MOVERS_TODAY_ROWS_PATH,
) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_big_movers_today_producer(
    defn: Optional[Mapping[str, Any]] = None,
) -> RoundupProducer:
    resolved = dict(defn) if defn is not None else load_candidate_definition()
    validate_roundup_definition(resolved)
    rule = dict(resolved.get("rule") or {})

    async def _produce(db: Any) -> RoundupMembers | RoundupRefusal:
        return await produce_big_movers_today(db, rule=rule)

    return RoundupProducer(
        slug=str(resolved["slug"]),
        name=str(resolved["name"]),
        kind=str(resolved.get("kind") or "roundup"),
        category=str(resolved["category"]),
        section_title=str(resolved["section_title"]),
        footer=str(resolved["footer"]),
        produce=_produce,
        membership=str(resolved.get("membership") or PRODUCER_KIND_BIG_MOVERS_TODAY),
        relations=tuple(resolved["relations"]),
        level=str(resolved["level"]),
        rule=rule,
        tag=resolved.get("tag"),
        kicker=str(resolved.get("kicker") or "PULSE · BIGGEST 24H SHIFTS"),
        score=float(resolved.get("score") or 93.0),
    )


def compose_big_movers_card_and_container(
    producer: RoundupProducer,
    members: RoundupMembers,
) -> tuple[dict[str, Any], dict[str, Any]]:
    feed_item = compose_roundup_feed_item(producer, members)
    container = compose_roundup_container(producer, members)
    if feed_item is None:
        raise ValueError("Expected non-empty RoundupMembers")
    context_line = _assert_clean_copy(str(members.sections[0].get("context_line") or ""))
    feed_item["context_summary"] = context_line
    feed_item["data"]["roundup"]["context_line"] = context_line
    container["context_line"] = context_line
    return feed_item, container


def build_big_movers_today_CandidatePack(
    producer: RoundupProducer,
    members: RoundupMembers,
) -> dict[str, Any]:
    feed_item, _ = compose_big_movers_card_and_container(producer, members)
    roundup = feed_item["data"]["roundup"]
    rows = list(roundup["rows"])
    best_row = max(rows, key=lambda r: abs(int(r["delta_points"])))
    return {
        "item_key": producer.slug,
        "kind": PRODUCER_KIND_BIG_MOVERS_TODAY,
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
            "market_id": best_row["market_id"],
            "subject": best_row["label"],
            "probability": best_row["probability"],
            "delta_points": best_row["delta_points"],
        },
    }
