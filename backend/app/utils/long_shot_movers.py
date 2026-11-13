"""Dynamic ``long_shot_movers`` grouped-card producer (#12288 Wave 1, Idea #15).

PILLAR: DISCOVER · TRUTH
SHIP: Guarded 24-hour waking-long-shot container selecting open markets that sat
at ``<= 12%`` 24 hours ago, now trade at ``>= 8%``, and climbed at least
``+6 points`` (``>= +0.06``), with freshness and liquidity guards so un-traded
quotes never trigger a false move. Every shift is formatted in points (never
``%``), with a dynamic ``context_line`` explaining the exact filter.

Publication gate: candidate definition lives in ``backend/data/discover/candidates/``
and is NOT registered in ``ROUNDUP_PRODUCERS`` until licensed via the Discover
exam and ``/grade/groupings``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
from app.utils.tonights_games import _parse_dt

__all__ = [
    "CANDIDATE_LONG_SHOT_MOVERS_PATH",
    "PRODUCER_KIND_LONG_SHOT_MOVERS",
    "LongShotMover",
    "build_long_shot_movers_grading_candidate",
    "build_long_shot_movers_producer",
    "compose_long_shot_movers_card_and_container",
    "load_candidate_definition",
    "produce_long_shot_movers",
    "select_long_shot_movers",
]

PRODUCER_KIND_LONG_SHOT_MOVERS = "long_shot_movers"

CANDIDATE_LONG_SHOT_MOVERS_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "discover"
    / "candidates"
    / "roundup-long-shot-movers.json"
)

_FORBIDDEN_COPY_RE = re.compile(
    r"\b(?:questions?|stale|venues?|kalshi|polymarket|opened)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class LongShotMover:
    market_id: int
    label: str
    outcome_name: str
    prior_prob: float
    current_prob: float
    gain_points: int
    card: dict[str, Any]


def _assert_clean_copy(text: str) -> str:
    cleaned = " ".join(str(text or "").split())
    if _FORBIDDEN_COPY_RE.search(cleaned):
        raise ValueError(f"Forbidden copy token in reader text: {cleaned!r}")
    return cleaned


def _is_recent_quote(
    market: Mapping[str, Any],
    now: datetime,
    max_quote_age_hours: float,
) -> bool:
    raw_ts = (
        market.get("prices_updated_at")
        or market.get("last_traded_at")
        or market.get("updated_at")
    )
    if raw_ts is None:
        return False
    dt = _parse_dt(raw_ts)
    if dt is None:
        return False
    age = now - dt.astimezone(timezone.utc)
    return timedelta(seconds=-300) <= age <= timedelta(hours=max_quote_age_hours)


def _extract_best_mover_from_market(
    market: Mapping[str, Any],
    *,
    now: datetime,
    max_prior_prob: float,
    min_current_prob: float,
    min_gain_points: int,
    max_quote_age_hours: float,
    min_volume: float,
) -> Optional[LongShotMover]:
    if not isinstance(market, Mapping) or not isinstance(market.get("id"), int):
        return None
    if str(market.get("status") or "").strip().lower() != "open":
        return None
    if not _is_recent_quote(market, now, max_quote_age_hours):
        return None

    vol_raw = market.get("volume")
    if vol_raw is not None:
        try:
            if float(vol_raw) < min_volume:
                return None
        except (TypeError, ValueError):
            return None

    title = str(market.get("name") or market.get("title") or "").strip()
    if not title or _FORBIDDEN_COPY_RE.search(title):
        return None

    outcomes = market.get("outcomes") or ()
    best: Optional[LongShotMover] = None
    for out in outcomes:
        if not isinstance(out, Mapping):
            continue
        out_name = str(out.get("name") or "").strip()
        if not out_name or out_name.lower() in {"no", "other", "none", "field"}:
            continue
        cur_raw = out.get("probability")
        prior_raw = (
            out.get("prior_24h_probability")
            if out.get("prior_24h_probability") is not None
            else out.get("probability_24h_ago")
        )
        if cur_raw is None or prior_raw is None:
            continue
        try:
            cur_p = float(cur_raw)
            prior_p = float(prior_raw)
        except (TypeError, ValueError):
            continue
        if not (0.0 < prior_p <= max_prior_prob and min_current_prob <= cur_p < 1.0):
            continue
        gain_pts = int(round((cur_p - prior_p) * 100))
        if gain_pts < min_gain_points:
            continue

        row_label = (
            title
            if out_name.lower() == "yes"
            else f"{out_name} · {title}"
        )
        candidate = LongShotMover(
            market_id=int(market["id"]),
            label=_assert_clean_copy(row_label),
            outcome_name=_assert_clean_copy(out_name),
            prior_prob=prior_p,
            current_prob=cur_p,
            gain_points=gain_pts,
            card=dict(market),
        )
        if best is None or candidate.gain_points > best.gain_points:
            best = candidate
    return best


def select_long_shot_movers(
    markets: Sequence[Mapping[str, Any]],
    *,
    now: Optional[datetime] = None,
    max_prior_prob: float = 0.12,
    min_current_prob: float = 0.08,
    min_gain_points: int = 6,
    max_quote_age_hours: float = 6.0,
    min_volume: float = 1000.0,
    min_members: int = 3,
    max_card_rows: int = 4,
) -> RoundupMembers | RoundupRefusal:
    effective_now = (
        now.astimezone(timezone.utc)
        if isinstance(now, datetime) and now.tzinfo is not None
        else datetime.now(timezone.utc)
    )
    movers: list[LongShotMover] = []
    seen_groups: set[str] = set()
    for m in markets:
        mover = _extract_best_mover_from_market(
            m,
            now=effective_now,
            max_prior_prob=max_prior_prob,
            min_current_prob=min_current_prob,
            min_gain_points=min_gain_points,
            max_quote_age_hours=max_quote_age_hours,
            min_volume=min_volume,
        )
        if mover is None:
            continue
        grp = str(m.get("group_id") or f"id:{mover.market_id}")
        if grp in seen_groups:
            continue
        seen_groups.add(grp)
        movers.append(mover)

    if len(movers) < max(2, int(min_members)):
        return RoundupRefusal([("insufficient_long_shot_movers", len(movers), int(min_members))])

    movers.sort(key=lambda mv: (-mv.gain_points, -mv.current_prob, mv.market_id))
    shown = movers[: max(2, int(max_card_rows))]
    cap_pct = int(round(max_prior_prob * 100))
    top = shown[0]
    context_line = _assert_clean_copy(
        f"Markets that sat at {cap_pct}% or lower a day ago and climbed at least "
        f"{min_gain_points} points on recent trading — led by +{top.gain_points} pts today."
    )
    footer = _assert_clean_copy(
        f"24h change in points · started at {cap_pct}% or lower · recent trading verified"
    )

    rows: list[dict[str, Any]] = []
    for mv in shown:
        prior_pct = int(round(mv.prior_prob * 100))
        cur_pct = int(round(mv.current_prob * 100))
        rows.append(
            {
                "market_id": mv.market_id,
                "label": mv.label,
                "outcome": mv.outcome_name,
                "prior_percent": prior_pct,
                "probability": round(mv.current_prob, 4),
                "rendered_percent": cur_pct,
                "delta_points": mv.gain_points,
                "delta_label": _assert_clean_copy(f"+{mv.gain_points} pts from {prior_pct}%"),
                "destination": market_destination(mv.market_id),
            }
        )

    members = [
        {"id": mv.market_id, "type": "futures", "card": dict(mv.card)}
        for mv in movers
    ]
    return RoundupMembers(
        members=members,
        rows=rows,
        footer=footer,
        count_line=f"{len(movers)} movers",
        title="Long shots that moved",
        kicker="MOVERS · LAST 24 HOURS",
        revision_ids=[mv.market_id for mv in movers],
        sections=(
            {
                "title": "Long shots waking up over the last 24 hours",
                "context_line": context_line,
                "member_ids": [mv.market_id for mv in movers],
            },
        ),
    )


async def produce_long_shot_movers(
    db: Any,
    *,
    rule: Optional[Mapping[str, Any]] = None,
    now: Optional[datetime] = None,
) -> RoundupMembers | RoundupRefusal:
    cfg_rule = dict(rule or {})
    if isinstance(db, (list, tuple)):
        return select_long_shot_movers(
            db,
            now=now,
            max_prior_prob=float(cfg_rule.get("max_prior_prob") or 0.12),
            min_current_prob=float(cfg_rule.get("min_current_prob") or 0.08),
            min_gain_points=int(cfg_rule.get("min_gain_points") or 6),
            max_quote_age_hours=float(cfg_rule.get("max_quote_age_hours") or 6.0),
            min_volume=float(cfg_rule.get("min_volume") or 1000.0),
            min_members=int(cfg_rule.get("min_members") or 3),
            max_card_rows=int(cfg_rule.get("max_card_rows") or 4),
        )
    return RoundupRefusal([("live_session_requires_history_bank", type(db).__name__)])


def load_candidate_definition(path: Path = CANDIDATE_LONG_SHOT_MOVERS_PATH) -> dict[str, Any]:
    defn = json.loads(path.read_text(encoding="utf-8"))
    validate_roundup_definition(defn)
    return defn


def build_long_shot_movers_producer(
    defn: Optional[Mapping[str, Any]] = None,
) -> RoundupProducer:
    resolved = dict(defn) if defn is not None else load_candidate_definition()
    validate_roundup_definition(resolved)
    rule = dict(resolved.get("rule") or {})

    async def _produce(db: Any) -> RoundupMembers | RoundupRefusal:
        return await produce_long_shot_movers(db, rule=rule)

    return RoundupProducer(
        slug=str(resolved["slug"]),
        name=str(resolved["name"]),
        kind=str(resolved.get("kind") or "roundup"),
        category=str(resolved["category"]),
        section_title=str(resolved["section_title"]),
        footer=str(resolved["footer"]),
        produce=_produce,
        membership=str(resolved.get("membership") or PRODUCER_KIND_LONG_SHOT_MOVERS),
        relations=tuple(resolved["relations"]),
        level=str(resolved["level"]),
        rule=rule,
        tag=resolved.get("tag"),
        kicker=str(resolved.get("kicker") or "MOVERS · LAST 24 HOURS"),
        score=float(resolved.get("score") or 91.0),
    )


def compose_long_shot_movers_card_and_container(
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


def build_long_shot_movers_grading_candidate(
    producer: RoundupProducer,
    members: RoundupMembers,
) -> dict[str, Any]:
    feed_item, _ = compose_long_shot_movers_card_and_container(producer, members)
    roundup = feed_item["data"]["roundup"]
    rows = list(roundup["rows"])
    best_row = min(rows, key=lambda r: abs(float(r["probability"]) - 0.5))
    return {
        "item_key": producer.slug,
        "kind": PRODUCER_KIND_LONG_SHOT_MOVERS,
        "kind_verdict": "serve",
        "licence_status": "HELD",
        "reader_reachable": False,
        "proposed_card": {
            "slug": producer.slug,
            "title": feed_item["data"]["title"],
            "kicker": roundup["kicker"],
            "context_line": roundup["context_line"],
            "rows": rows,
            "footer": roundup["footer"],
        },
        "best_single": {
            "id": int(best_row["market_id"]),
            "name": str(best_row["label"]),
            "subject": str(best_row["outcome"]),
            "rendered_percent": int(best_row["rendered_percent"]),
        },
    }
