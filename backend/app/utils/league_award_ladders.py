"""Dynamic ``league_award_ladders`` grouped-card producer (#12288 Wave 1, Idea #4).

PILLAR: DISCOVER · MATCHING · TRUTH
SHIP: Sports major-trophy ladder dynamically grouping an active league's major
player and coach trophies (MVP, Defensive Player of the Year, Rookie of the
Year / Offensive ROY / Defensive ROY, Coach of the Year) into one
leader-per-trophy card, blending cross-source twins via
``futures_source_merge.blend_with_verdict`` (refusing 40+ pt divergence),
ordering from tightest trophy race to clearest favorite, and emitting a clear
``context_line`` explaining the selection and ordering rule.

Publication gate: candidate definition lives in ``backend/data/discover/candidates/``
and is NOT registered in ``ROUNDUP_PRODUCERS`` until licensed via the Discover
exam and ``/grade/groupings`` (live DB ``AsyncSession`` query wiring lands in the
activation PR once licensed).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from app.utils.container_presentation import market_destination
from app.utils.futures_source_merge import blend_with_verdict
from app.utils.roundup_containers import (
    RoundupMembers,
    RoundupProducer,
    RoundupRefusal,
    compose_roundup_container,
    compose_roundup_feed_item,
    validate_roundup_definition,
)

__all__ = [
    "CANDIDATE_NBA_AWARD_LADDERS_PATH",
    "CANDIDATE_NBA_AWARD_LADDERS_ROWS_PATH",
    "LEAGUE_AWARD_SLOTS",
    "PRODUCER_KIND_LEAGUE_AWARD_LADDERS",
    "AwardStanding",
    "build_award_ladders_grading_candidate",
    "build_league_award_ladders_producer",
    "compose_award_ladders_card_and_container",
    "load_candidate_definition",
    "load_candidate_eval_rows",
    "produce_league_award_ladders",
    "select_league_award_ladders",
]

PRODUCER_KIND_LEAGUE_AWARD_LADDERS = "league_award_ladders"

CANDIDATE_NBA_AWARD_LADDERS_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "discover"
    / "candidates"
    / "roundup-nba-award-ladders.json"
)

CANDIDATE_NBA_AWARD_LADDERS_ROWS_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "discover"
    / "candidates"
    / "roundup-nba-award-ladders-rows.json"
)

_FORBIDDEN_COPY_RE = re.compile(
    r"\b(?:questions?|stale|venues?|kalshi|polymarket|opened)\b",
    re.IGNORECASE,
)

_EXCLUDED_AWARD_SUBTYPE_RE = re.compile(
    r"\b(?:finalists?|age\s+of|conference\s+of|class\s+of|position\s+of|"
    r"cup\s+mvp|finals\s+mvp|all[- ]star|and\s+dpoy|combo)\b",
    re.IGNORECASE,
)

LEAGUE_AWARD_SLOTS: dict[str, dict[str, Any]] = {
    "basketball_nba": {
        "label": "NBA",
        "sport_tokens": ("nba", "pro basketball", "basketball_nba"),
        "slots": (
            ("mvp", "MVP", re.compile(r"\bmvp\b", re.IGNORECASE)),
            (
                "dpoy",
                "Defensive Player",
                re.compile(r"\b(?:defensive\s+player\s+of\s+the\s+year|dpoy)\b", re.IGNORECASE),
            ),
            (
                "roy",
                "Rookie of the Year",
                re.compile(r"\brookie\s+of\s+the\s+year\b", re.IGNORECASE),
            ),
            (
                "coy",
                "Coach of the Year",
                re.compile(r"\bcoach\s+of\s+the\s+year\b", re.IGNORECASE),
            ),
        ),
    },
    "americanfootball_nfl": {
        "label": "NFL",
        "sport_tokens": ("nfl", "pro football", "americanfootball_nfl"),
        "slots": (
            ("mvp", "MVP", re.compile(r"\bmvp\b", re.IGNORECASE)),
            (
                "dpoy",
                "Defensive Player",
                re.compile(r"\bdefensive\s+player\s+of\s+the\s+year\b", re.IGNORECASE),
            ),
            (
                "oroy",
                "Offensive Rookie",
                re.compile(r"\boffensive\s+rookie\s+of\s+the\s+year\b", re.IGNORECASE),
            ),
            (
                "droy",
                "Defensive Rookie",
                re.compile(r"\bdefensive\s+rookie\s+of\s+the\s+year\b", re.IGNORECASE),
            ),
            (
                "coy",
                "Coach of the Year",
                re.compile(r"\bcoach\s+of\s+the\s+year\b", re.IGNORECASE),
            ),
        ),
    },
}


@dataclass(frozen=True)
class AwardStanding:
    slot_key: str
    award_label: str
    leader_name: str
    leader_probability: float
    runner_up_name: Optional[str]
    runner_up_probability: Optional[float]
    gap_points: float
    primary_market_id: int
    contributing_market_ids: tuple[int, ...]
    primary_card: dict[str, Any]


def _assert_clean_copy(text: str) -> str:
    cleaned = " ".join(str(text or "").split())
    if _FORBIDDEN_COPY_RE.search(cleaned):
        raise ValueError(f"Forbidden copy token in reader text: {cleaned!r}")
    return cleaned


def _norm_person(raw: Any) -> Optional[str]:
    text = re.sub(r"\s+", " ", str(raw or "").strip())
    if not text or text.lower() in {"other", "field", "none", "tie", "yes", "no"}:
        return None
    if _FORBIDDEN_COPY_RE.search(text):
        return None
    return text


def _classify_award(market: Mapping[str, Any], sport: str) -> Optional[tuple[str, str]]:
    cfg = LEAGUE_AWARD_SLOTS.get(sport)
    if cfg is None:
        return None
    title = str(market.get("name") or market.get("title") or "").strip()
    if not title or _EXCLUDED_AWARD_SUBTYPE_RE.search(title):
        return None
    sport_col = str(
        market.get("sport") or market.get("llm_sport_category") or market.get("category") or ""
    ).lower()
    hay = f"{title.lower()} {sport_col}"
    if not any(tok in hay for tok in cfg["sport_tokens"]):
        return None
    for slot_key, label, pat in cfg["slots"]:
        if pat.search(title):
            return slot_key, label
    return None


def _extract_candidates(
    market: Mapping[str, Any],
    *,
    now: Optional[datetime] = None,
    max_quote_age_hours: float = 48.0,
    min_volume_24h: float = 100.0,
) -> dict[str, float]:
    if str(market.get("status") or "open").strip().lower() != "open":
        return {}
    if market.get("is_trading") is False:
        return {}
    quiet_days = market.get("quiet_days")
    if quiet_days is not None:
        try:
            if float(quiet_days) > 7.0:
                return {}
        except (TypeError, ValueError):
            return {}
    vol_24h = market.get("volume_24h")
    if vol_24h is None:
        vol_24h = market.get("volume24hr")
    if vol_24h is not None:
        try:
            if float(vol_24h) < float(min_volume_24h):
                return {}
        except (TypeError, ValueError):
            return {}
    if now is not None:
        raw_ts = market.get("price_observed_at") or market.get("updated_at")
        if isinstance(raw_ts, str) and raw_ts.strip():
            try:
                parsed = datetime.fromisoformat(raw_ts.strip().replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                ref = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
                if (ref - parsed).total_seconds() / 3600.0 > float(max_quote_age_hours):
                    return {}
            except ValueError:
                return {}
    people: dict[str, float] = {}
    for out in market.get("outcomes") or ():
        if not isinstance(out, Mapping):
            continue
        person = _norm_person(out.get("name"))
        if not person:
            continue
        p_raw = out.get("probability")
        if p_raw is None:
            continue
        try:
            p = float(p_raw)
        except (TypeError, ValueError):
            continue
        if not (0.0 < p < 1.0):
            continue
        if person not in people or p > people[person]:
            people[person] = p
    return people


def _resolve_award_slot(
    slot_key: str,
    award_label: str,
    slot_markets: Sequence[Mapping[str, Any]],
    *,
    now: Optional[datetime] = None,
    max_quote_age_hours: float = 48.0,
    min_volume_24h: float = 100.0,
) -> tuple[Optional[AwardStanding], Optional[tuple[Any, ...]]]:
    by_source: dict[str, tuple[Mapping[str, Any], dict[str, float]]] = {}
    for m in slot_markets:
        src = str(m.get("source") or "").strip().lower()
        if not src:
            continue
        cands = _extract_candidates(
            m,
            now=now,
            max_quote_age_hours=max_quote_age_hours,
            min_volume_24h=min_volume_24h,
        )
        if len(cands) < 2:
            continue
        if src not in by_source or len(cands) > len(by_source[src][1]):
            by_source[src] = (m, cands)
    if not by_source:
        return None, None

    sources_sorted = sorted(by_source.keys())
    all_names: set[str] = set()
    for _, cands in by_source.values():
        all_names.update(cands.keys())

    blended: list[tuple[str, float]] = []
    for name in sorted(all_names):
        rows_for_blend = [
            {"source": s, "probability": by_source[s][1][name]}
            for s in sources_sorted
            if name in by_source[s][1]
        ]
        if len(rows_for_blend) >= 2:
            val, divergence, rule_name = blend_with_verdict(rows_for_blend)
            if divergence is not None or rule_name == "divergence_gate" or val is None:
                return None, ("award_divergence_gate", slot_key, name)
            blended.append((name, float(val)))
        elif len(rows_for_blend) == 1:
            # Preserve single-source contenders in multi-source award slots so an
            # incomplete book never erases the true front-runner.
            blended.append((name, float(rows_for_blend[0]["probability"])))

    if len(blended) < 2:
        return None, None
    blended.sort(key=lambda x: (-x[1], x[0]))
    leader_name, leader_prob = blended[0]
    runner_name, runner_prob = blended[1]
    gap_pts = round((leader_prob - runner_prob) * 100.0, 1)

    # row["market_id"] links the primary market quoting leader_name (preferring Kalshi
    # when both quote the leader), while revision_ids tracks all contributing twins.
    sources_with_leader = [s for s in sources_sorted if leader_name in by_source[s][1]]
    primary_src = (
        "kalshi"
        if "kalshi" in sources_with_leader
        else (sources_with_leader[0] if sources_with_leader else sources_sorted[0])
    )
    primary_card = dict(by_source[primary_src][0])
    contrib_ids = tuple(sorted(int(by_source[s][0]["id"]) for s in sources_sorted))

    return (
        AwardStanding(
            slot_key=slot_key,
            award_label=award_label,
            leader_name=leader_name,
            leader_probability=leader_prob,
            runner_up_name=runner_name,
            runner_up_probability=runner_prob,
            gap_points=gap_pts,
            primary_market_id=int(primary_card["id"]),
            contributing_market_ids=contrib_ids,
            primary_card=primary_card,
        ),
        None,
    )


def select_league_award_ladders(
    markets: Sequence[Mapping[str, Any]],
    *,
    now: Optional[datetime] = None,
    sport: str = "basketball_nba",
    min_awards: int = 3,
    max_card_rows: int = 4,
    max_quote_age_hours: float = 48.0,
    min_volume_24h: float = 100.0,
) -> RoundupMembers | RoundupRefusal:
    cfg = LEAGUE_AWARD_SLOTS.get(sport)
    if cfg is None:
        return RoundupRefusal([("unsupported_sport", sport)])

    buckets: dict[str, tuple[str, list[Mapping[str, Any]]]] = {}
    for m in markets:
        if not isinstance(m, Mapping) or not isinstance(m.get("id"), int):
            continue
        classified = _classify_award(m, sport)
        if classified is None:
            continue
        slot_key, label = classified
        if slot_key not in buckets:
            buckets[slot_key] = (label, [])
        buckets[slot_key][1].append(m)

    standings: list[AwardStanding] = []
    drop_reasons: list[tuple[Any, ...]] = []
    for slot_key, label, _ in cfg["slots"]:
        if slot_key not in buckets:
            continue
        resolved, drop_reason = _resolve_award_slot(
            slot_key,
            label,
            buckets[slot_key][1],
            now=now,
            max_quote_age_hours=max_quote_age_hours,
            min_volume_24h=min_volume_24h,
        )
        if resolved is not None:
            standings.append(resolved)
        elif drop_reason is not None:
            drop_reasons.append(drop_reason)

    if len(standings) < max(2, int(min_awards)):
        return RoundupRefusal(
            [
                ("insufficient_awards", sport, len(standings), int(min_awards)),
                *drop_reasons,
            ]
        )

    standings.sort(key=lambda s: (s.gap_points, abs(s.leader_probability - 0.5), s.award_label))
    shown = standings[: max(2, int(max_card_rows))]
    league_label = str(cfg["label"])
    first = shown[0]
    last = shown[-1]
    first_pct = int(round(first.leader_probability * 100))
    last_pct = int(round(last.leader_probability * 100))
    first_gap = int(round(first.gap_points))
    last_gap = int(round(last.gap_points))

    awards_by_leader: dict[str, list[AwardStanding]] = {}
    for s in shown:
        awards_by_leader.setdefault(s.leader_name, []).append(s)
    multi_leader = next((item for item in awards_by_leader.items() if len(item[1]) >= 2), None)

    if multi_leader is not None:
        m_name, m_awards = multi_leader
        card_title = _assert_clean_copy(
            f"{m_name} leads {len(m_awards)} {league_label} trophies at once"
        )
        m_parts = [
            f"{a.award_label}: {a.leader_name} {int(round(a.leader_probability * 100))}%"
            + (f", +{int(round(a.gap_points))} pts over {a.runner_up_name}" if a.runner_up_name else "")
            for a in m_awards
        ]
        if first.award_label not in {a.award_label for a in m_awards}:
            first_runner = f" vs {first.runner_up_name}" if first.runner_up_name else ""
            context_line = _assert_clean_copy(
                f"{m_name} leads {len(m_awards)} {league_label} trophies ({' · '.join(m_parts)}), "
                f"while {first.award_label} sits within {first_gap} pts "
                f"({first.award_label}: {first.leader_name} {first_pct}%{first_runner})."
            )
        else:
            context_line = _assert_clean_copy(
                f"{m_name} leads {len(m_awards)} {league_label} trophies across {len(shown)} "
                f"season boards ({' · '.join(m_parts)})."
            )
    else:
        card_title = _assert_clean_copy(
            f"{league_label} award races — tightest within {first_gap} pts"
        )
        first_runner = f", +{first_gap} pts over {first.runner_up_name}" if first.runner_up_name else ""
        last_runner = f", +{last_gap} pts over {last.runner_up_name}" if last.runner_up_name else ""
        context_line = _assert_clean_copy(
            f"Front-runner in {len(shown)} major {league_label} season awards, ordered from "
            f"closest race ({first.award_label}: {first.leader_name} {first_pct}%{first_runner}) "
            f"to clearest favorite ({last.award_label}: {last.leader_name} {last_pct}%{last_runner})."
        )
    footer = _assert_clean_copy(
        f"One winner per trophy · {len(shown)} major {league_label} awards"
    )

    rows: list[dict[str, Any]] = []
    for s in shown:
        pct = int(round(s.leader_probability * 100))
        # market_id links the primary (Kalshi-preferred) market that quotes s.leader_name
        row: dict[str, Any] = {
            "market_id": s.primary_market_id,
            "label": _assert_clean_copy(f"{s.award_label} · {s.leader_name}"),
            "award": s.award_label,
            "leader": s.leader_name,
            "probability": round(s.leader_probability, 4),
            "rendered_percent": pct,
            "gap_points": s.gap_points,
            "destination": market_destination(s.primary_market_id),
        }
        if s.runner_up_name and s.runner_up_probability is not None:
            row["runner_up_label"] = _assert_clean_copy(
                f"{s.runner_up_name} {int(round(s.runner_up_probability * 100))}%"
            )
        rows.append(row)

    members = [
        {"id": s.primary_market_id, "type": "futures", "card": dict(s.primary_card)}
        for s in standings
    ]
    rev_ids: list[int] = []
    for s in standings:
        for mid in s.contributing_market_ids:
            if mid not in rev_ids:
                rev_ids.append(mid)

    return RoundupMembers(
        members=members,
        rows=rows,
        footer=footer,
        count_line=f"{len(standings)} awards",
        title=card_title,
        kicker=f"{league_label} · SEASON AWARDS",
        revision_ids=rev_ids,
        sections=(
            {
                "title": f"All {league_label} season award leaders",
                "context_line": context_line,
                "member_ids": [s.primary_market_id for s in standings],
            },
        ),
    )


async def produce_league_award_ladders(
    db: Any,
    *,
    rule: Optional[Mapping[str, Any]] = None,
    now: Optional[datetime] = None,
) -> RoundupMembers | RoundupRefusal:
    cfg_rule = dict(rule or {})
    sport = str(cfg_rule.get("sport") or "basketball_nba")
    min_a = int(cfg_rule.get("min_awards") or 3)
    max_r = int(cfg_rule.get("max_card_rows") or 4)
    max_q = float(cfg_rule.get("max_quote_age_hours") or 48.0)
    min_v = float(cfg_rule.get("min_volume_24h") or 100.0)
    if isinstance(db, (list, tuple)):
        return select_league_award_ladders(
            db,
            now=now,
            sport=sport,
            min_awards=min_a,
            max_card_rows=max_r,
            max_quote_age_hours=max_q,
            min_volume_24h=min_v,
        )
    from sqlalchemy import or_, select
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import selectinload

    if not isinstance(db, AsyncSession):
        return RoundupRefusal([("unsupported_session", type(db).__name__)])

    from app.models.models import FuturesMarket

    effective_now = now or datetime.now(timezone.utc)
    stmt = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(
            FuturesMarket.status == "open",
            or_(
                FuturesMarket.name.ilike("%MVP%"),
                FuturesMarket.name.ilike("%Defensive Player%"),
                FuturesMarket.name.ilike("%Rookie of the Year%"),
                FuturesMarket.name.ilike("%Coach of the Year%"),
            ),
        )
    )
    res = await db.execute(stmt)
    orm_rows = res.scalars().all()
    serialized = [
        {
            "id": int(m.id),
            "name": m.name,
            "status": m.status,
            "source": m.source,
            "category": m.category,
            "llm_sport_category": getattr(m, "llm_sport_category", None),
            "volume_24h": getattr(m, "volume_24h", None),
            "updated_at": (
                m.updated_at.isoformat()
                if getattr(m, "updated_at", None) is not None
                else None
            ),
            "outcomes": [
                {
                    "name": o.name,
                    "probability": (
                        getattr(o, "current_probability", None)
                        if getattr(o, "current_probability", None) is not None
                        else getattr(o, "probability", None)
                    ),
                }
                for o in (m.outcomes or [])
            ],
        }
        for m in orm_rows
    ]
    return select_league_award_ladders(
        serialized,
        now=effective_now,
        sport=sport,
        min_awards=min_a,
        max_card_rows=max_r,
        max_quote_age_hours=max_q,
        min_volume_24h=min_v,
    )


def load_candidate_definition(path: Path = CANDIDATE_NBA_AWARD_LADDERS_PATH) -> dict[str, Any]:
    defn = json.loads(path.read_text(encoding="utf-8"))
    validate_roundup_definition(defn)
    return defn


def load_candidate_eval_rows(
    path: Path = CANDIDATE_NBA_AWARD_LADDERS_ROWS_PATH,
) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_league_award_ladders_producer(
    defn: Optional[Mapping[str, Any]] = None,
) -> RoundupProducer:
    resolved = dict(defn) if defn is not None else load_candidate_definition()
    validate_roundup_definition(resolved)
    rule = dict(resolved.get("rule") or {})

    async def _produce(db: Any) -> RoundupMembers | RoundupRefusal:
        return await produce_league_award_ladders(db, rule=rule)

    return RoundupProducer(
        slug=str(resolved["slug"]),
        name=str(resolved["name"]),
        kind=str(resolved.get("kind") or "roundup"),
        category=str(resolved["category"]),
        section_title=str(resolved["section_title"]),
        footer=str(resolved["footer"]),
        produce=_produce,
        membership=str(resolved.get("membership") or PRODUCER_KIND_LEAGUE_AWARD_LADDERS),
        relations=tuple(resolved["relations"]),
        level=str(resolved["level"]),
        rule=rule,
        tag=resolved.get("tag"),
        kicker=str(resolved.get("kicker") or "NBA · SEASON AWARDS"),
        order=str(resolved.get("order") or "sequence"),
        score=float(resolved.get("score") or 91.5),
        enabled=(lambda: bool(resolved["enabled"])) if "enabled" in resolved else None,
    )


def compose_award_ladders_card_and_container(
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
    feed_item["data"]["roundup"]["subtitle"] = context_line
    feed_item["data"]["roundup"]["order"] = "sequence"
    container["context_line"] = context_line
    return feed_item, container


def build_award_ladders_grading_candidate(
    producer: RoundupProducer,
    members: RoundupMembers,
) -> dict[str, Any]:
    feed_item, _ = compose_award_ladders_card_and_container(producer, members)
    roundup = feed_item["data"]["roundup"]
    rows = list(roundup["rows"])
    best_row = min(rows, key=lambda r: abs(float(r["probability"]) - 0.5))
    return {
        "item_key": producer.slug,
        "kind": PRODUCER_KIND_LEAGUE_AWARD_LADDERS,
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
            "subject": str(best_row["leader"]),
            "rendered_percent": int(best_row["rendered_percent"]),
        },
    }
