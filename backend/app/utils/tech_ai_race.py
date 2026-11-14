"""Dynamic ``tech_ai_race`` grouped-card producer (#12288 Wave 1, Idea #12).

PILLAR: DISCOVER · MATCHING · TRUTH
SHIP: Dynamic AI leaderboard container selecting open single-winner AI model
benchmark races (month-end overall Arena keyed per month, year-end overall Arena,
Coding Arena, LiveBench Coding), blending identical benchmark twins via
``futures_source_merge.blend_with_verdict`` while keeping distinct benchmarks and
distinct months separate so different settlement rules are never conflated, and
emitting a clear ``context_line`` naming the settlement benchmark behind each row.

Publication gate: candidate definition lives in ``backend/data/discover/candidates/``
and are NOT registered in ``ROUNDUP_PRODUCERS`` until licensed via the Discover
exam and ``/grade/groupings``.
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
    "CANDIDATE_AI_RACE_PATH",
    "CANDIDATE_AI_RACE_ROWS_PATH",
    "PRODUCER_KIND_TECH_AI_RACE",
    "BenchmarkStanding",
    "build_ai_race_grading_candidate",
    "build_tech_ai_race_producer",
    "compose_ai_race_card_and_container",
    "load_candidate_definition",
    "load_candidate_eval_rows",
    "produce_tech_ai_race",
    "select_tech_ai_race",
]

PRODUCER_KIND_TECH_AI_RACE = "tech_ai_race"

CANDIDATE_AI_RACE_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "discover"
    / "candidates"
    / "roundup-ai-race.json"
)

CANDIDATE_AI_RACE_ROWS_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "discover"
    / "candidates"
    / "roundup-ai-race-rows.json"
)

_FORBIDDEN_COPY_RE = re.compile(
    r"\b(?:questions?|stale|venues?|kalshi|polymarket|opened)\b",
    re.IGNORECASE,
)

_MONTH_INDEX: dict[str, tuple[int, str]] = {
    "january": (1, "Jan"),
    "february": (2, "Feb"),
    "march": (3, "Mar"),
    "april": (4, "Apr"),
    "may": (5, "May"),
    "june": (6, "Jun"),
    "july": (7, "Jul"),
    "august": (8, "Aug"),
    "september": (9, "Sep"),
    "october": (10, "Oct"),
    "november": (11, "Nov"),
    "december": (12, "Dec"),
}

_MONTH_END_RE = re.compile(
    r"\bend\s+of\s+"
    r"(january|february|march|april|may|june|july|august|september|october|november|december)"
    r"(?:\s+(202[6-9]))?\b",
    re.IGNORECASE,
)

_AI_BENCHMARK_SLOTS: tuple[tuple[str, str, str, re.Pattern[str]], ...] = (
    (
        "arena_month_end",
        "Overall · Month-end",
        "overall",
        re.compile(
            r"best\s+ai\s+model\b.*?\bend\s+of\s+"
            r"(?:january|february|march|april|may|june|july|august|september|october|november|december)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "arena_year_end",
        "Overall · Year-end",
        "overall",
        re.compile(
            r"best\s+ai\s+model\b.*?\bend\s+of\s+202[6-9]\b",
            re.IGNORECASE,
        ),
    ),
    (
        "coding_arena_year_end",
        "Coding Arena · Year-end",
        "coding",
        re.compile(
            r"best\s+coding\s+model\b.*?\bend\s+of\s+202[6-9]\b",
            re.IGNORECASE,
        ),
    ),
    (
        "livebench_coding",
        "LiveBench Coding",
        "coding",
        re.compile(
            r"best\s+ai\s+model\s+on\s+livebench\s*\(\s*coding\s*\)",
            re.IGNORECASE,
        ),
    ),
)

_STATIC_SLOT_ORDER: dict[str, int] = {
    "arena_year_end": 1,
    "coding_arena_year_end": 2,
    "livebench_coding": 3,
}

_EXCLUDED_AI_SHAPE_RE = re.compile(
    r"(?:___|reach\b.*\bscore\b|which\s+companies\s+will\s+have\s+a\s+top[- ]ranked)",
    re.IGNORECASE,
)

_LAB_ALIASES: dict[str, str] = {
    "google": "Google",
    "google deepmind": "Google",
    "alphabet": "Google",
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "xai": "xAI",
    "meta": "Meta",
    "deepseek": "DeepSeek",
    "alibaba": "Alibaba",
    "mistral": "Mistral",
}


@dataclass(frozen=True)
class BenchmarkStanding:
    slot_key: str
    benchmark_label: str
    track: str
    leader_lab: str
    leader_probability: float
    runner_up_lab: Optional[str]
    runner_up_probability: Optional[float]
    primary_market_id: int
    contributing_market_ids: tuple[int, ...]
    primary_card: dict[str, Any]
    blended_labs: tuple[tuple[str, float], ...] = ()


def _assert_clean_copy(text: str) -> str:
    cleaned = " ".join(str(text or "").split())
    if _FORBIDDEN_COPY_RE.search(cleaned):
        raise ValueError(f"Forbidden copy token in reader text: {cleaned!r}")
    return cleaned


def _canonical_lab(raw_name: Any) -> Optional[str]:
    cleaned = re.sub(r"\s+", " ", str(raw_name or "").strip())
    low = cleaned.lower()
    if not low or low in {"other", "none", "tie", "field"} or low.startswith("#"):
        return None
    resolved = _LAB_ALIASES.get(low, cleaned)
    if _FORBIDDEN_COPY_RE.search(resolved):
        return None
    return resolved


def _classify_ai_benchmark(market: Mapping[str, Any]) -> Optional[tuple[str, str, str]]:
    title = str(market.get("name") or market.get("title") or "").strip()
    if not title or _EXCLUDED_AI_SHAPE_RE.search(title):
        return None
    for slot_key, label, track, pat in _AI_BENCHMARK_SLOTS:
        if "livebench" in title.lower() and slot_key != "livebench_coding":
            continue
        if pat.search(title):
            if slot_key == "arena_month_end":
                m = _MONTH_END_RE.search(title)
                if m:
                    mon_low = m.group(1).lower()
                    year_tok = m.group(2)
                    mon_idx, mon_abbr = _MONTH_INDEX[mon_low]
                    year_key = f"{year_tok}:" if year_tok else ""
                    label_suffix = f"{mon_abbr} {year_tok}" if year_tok else mon_abbr
                    # Key by month (and explicit year if present) so rolling November and
                    # December month-end markets never merge or mislabel one another.
                    return (
                        f"arena_month_end:{year_key}{mon_idx:02d}:{mon_low}",
                        f"Overall Arena · End of {label_suffix}",
                        track,
                    )
            return slot_key, label, track
    return None


def _slot_sort_key(slot_key: str) -> tuple[int, str]:
    if slot_key.startswith("arena_month_end:"):
        return (0, slot_key)
    return (_STATIC_SLOT_ORDER.get(slot_key, 99), slot_key)


def _extract_labs(
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
    labs: dict[str, float] = {}
    raw_sum = 0.0
    for out in market.get("outcomes") or ():
        if not isinstance(out, Mapping):
            continue
        lab = _canonical_lab(out.get("name"))
        if not lab:
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
        raw_sum += p
        if lab not in labs or p > labs[lab]:
            labs[lab] = p
    # Single-winner company leaderboard sum must sit in a plausible mutually-exclusive band
    if len(labs) < 2 or raw_sum > 1.35:
        return {}
    return labs


def _resolve_slot(
    slot_key: str,
    label: str,
    track: str,
    slot_markets: Sequence[Mapping[str, Any]],
    *,
    now: Optional[datetime] = None,
    max_quote_age_hours: float = 48.0,
    min_volume_24h: float = 100.0,
) -> tuple[Optional[BenchmarkStanding], Optional[tuple[Any, ...]]]:
    by_source: dict[str, tuple[Mapping[str, Any], dict[str, float]]] = {}
    for m in slot_markets:
        src = str(m.get("source") or "").strip().lower()
        if not src:
            continue
        labs = _extract_labs(
            m,
            now=now,
            max_quote_age_hours=max_quote_age_hours,
            min_volume_24h=min_volume_24h,
        )
        if len(labs) < 2:
            continue
        if src not in by_source or len(labs) > len(by_source[src][1]):
            by_source[src] = (m, labs)
    if not by_source:
        return None, None

    sources_sorted = sorted(by_source.keys())
    all_labs: set[str] = set()
    for _, labs in by_source.values():
        all_labs.update(labs.keys())

    blended: list[tuple[str, float]] = []
    for lab in sorted(all_labs):
        rows_for_blend = [
            {"source": s, "probability": by_source[s][1][lab]}
            for s in sources_sorted
            if lab in by_source[s][1]
        ]
        if len(rows_for_blend) >= 2:
            val, divergence, rule_name = blend_with_verdict(rows_for_blend)
            if divergence is not None or rule_name == "divergence_gate" or val is None:
                return None, ("benchmark_divergence_gate", slot_key, lab)
            blended.append((lab, float(val)))
        elif len(rows_for_blend) == 1:
            # Keep single-source labs in multi-source slots so a partial book never
            # drops the true benchmark leader.
            blended.append((lab, float(rows_for_blend[0]["probability"])))

    if len(blended) < 2:
        return None, None
    blended.sort(key=lambda x: (-x[1], x[0]))
    leader_lab, leader_prob = blended[0]
    runner_lab, runner_prob = blended[1]

    sources_with_leader = [s for s in sources_sorted if leader_lab in by_source[s][1]]
    primary_src = (
        "kalshi"
        if "kalshi" in sources_with_leader
        else (sources_with_leader[0] if sources_with_leader else sources_sorted[0])
    )
    primary_card = dict(by_source[primary_src][0])
    contrib_ids = tuple(sorted(int(by_source[s][0]["id"]) for s in sources_sorted))

    return (
        BenchmarkStanding(
            slot_key=slot_key,
            benchmark_label=label,
            track=track,
            leader_lab=leader_lab,
            leader_probability=leader_prob,
            runner_up_lab=runner_lab,
            runner_up_probability=runner_prob,
            primary_market_id=int(primary_card["id"]),
            contributing_market_ids=contrib_ids,
            primary_card=primary_card,
            blended_labs=tuple(blended),
        ),
        None,
    )


def _compose_title_and_context_line(standings: Sequence[BenchmarkStanding]) -> tuple[str, str]:
    overall_leaders = {s.leader_lab for s in standings if s.track == "overall"}
    coding_leaders = {s.leader_lab for s in standings if s.track == "coding"}
    n = len(standings)
    if len(overall_leaders) == 1 and len(coding_leaders) == 1:
        ov_lab = next(iter(overall_leaders))
        cd_lab = next(iter(coding_leaders))
        if ov_lab != cd_lab:
            third_clause = ""
            common_third: Optional[str] = None
            third_probs: list[int] = []
            for s in standings:
                if len(s.blended_labs) >= 3:
                    lab3, prob3 = s.blended_labs[2]
                    if common_third is None:
                        common_third = lab3
                    elif common_third != lab3:
                        common_third = ""
                    third_probs.append(max(1, int(round(prob3 * 100))))
                else:
                    common_third = ""
            if common_third and common_third not in {ov_lab, cd_lab} and third_probs:
                lo_p, hi_p = min(third_probs), max(third_probs)
                span_txt = f"{lo_p}%" if lo_p == hi_p else f"{lo_p}% to {hi_p}%"
                third_clause = f", leaving {common_third} in third on all {n} boards ({span_txt})"
            card_title = _assert_clean_copy(f"{ov_lab} leads overall AI; {cd_lab} leads coding")
            ctx = _assert_clean_copy(
                f"{n} live AI model leaderboards side by side — {ov_lab} leads overall "
                f"evaluations while {cd_lab} leads coding{third_clause}; each row settles on its named benchmark."
            )
            return card_title, ctx
    top = standings[0]
    return (
        "The AI model race",
        _assert_clean_copy(
            f"{n} live AI model leaderboards across overall and coding evaluations — "
            f"{top.leader_lab} leads {top.benchmark_label} at {int(round(top.leader_probability * 100))}%; "
            f"each row settles on its own named benchmark."
        ),
    )


def select_tech_ai_race(
    markets: Sequence[Mapping[str, Any]],
    *,
    now: Optional[datetime] = None,
    min_benchmarks: int = 3,
    max_card_rows: int = 4,
    max_quote_age_hours: float = 48.0,
    min_volume_24h: float = 100.0,
) -> RoundupMembers | RoundupRefusal:
    slot_buckets: dict[str, tuple[str, str, list[Mapping[str, Any]]]] = {}
    for m in markets:
        if not isinstance(m, Mapping) or not isinstance(m.get("id"), int):
            continue
        classified = _classify_ai_benchmark(m)
        if classified is None:
            continue
        slot_key, label, track = classified
        if slot_key not in slot_buckets:
            slot_buckets[slot_key] = (label, track, [])
        slot_buckets[slot_key][2].append(m)

    ordered_keys = sorted(slot_buckets.keys(), key=_slot_sort_key)
    standings: list[BenchmarkStanding] = []
    drop_reasons: list[tuple[Any, ...]] = []
    for key in ordered_keys:
        label, track, bucket = slot_buckets[key]
        resolved, drop_reason = _resolve_slot(
            key,
            label,
            track,
            bucket,
            now=now,
            max_quote_age_hours=max_quote_age_hours,
            min_volume_24h=min_volume_24h,
        )
        if resolved is not None:
            standings.append(resolved)
        elif drop_reason is not None:
            drop_reasons.append(drop_reason)

    if len(standings) < max(2, int(min_benchmarks)):
        return RoundupRefusal(
            [
                ("insufficient_ai_benchmarks", len(standings), int(min_benchmarks)),
                *drop_reasons,
            ]
        )

    card_standings = standings[: max(2, int(max_card_rows))]
    card_title, context_line = _compose_title_and_context_line(card_standings)
    footer = _assert_clean_copy(
        f"One winning lab per benchmark · {len(card_standings)} distinct AI leaderboards"
    )

    rows: list[dict[str, Any]] = []
    for s in card_standings:
        pct = int(round(s.leader_probability * 100))
        row: dict[str, Any] = {
            "market_id": s.primary_market_id,
            "label": _assert_clean_copy(f"{s.benchmark_label} · {s.leader_lab}"),
            "benchmark": s.benchmark_label,
            "leader": s.leader_lab,
            "probability": round(s.leader_probability, 4),
            "rendered_percent": pct,
            "destination": market_destination(s.primary_market_id),
        }
        if s.runner_up_lab and s.runner_up_probability is not None:
            row["runner_up_label"] = _assert_clean_copy(
                f"{s.runner_up_lab} {int(round(s.runner_up_probability * 100))}%"
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
        count_line=f"{len(standings)} benchmarks",
        title=card_title,
        kicker="TECH · AI BENCHMARKS",
        revision_ids=rev_ids,
        sections=(
            {
                "title": "Active AI model leaderboards",
                "context_line": context_line,
                "member_ids": [s.primary_market_id for s in standings],
            },
        ),
    )


async def produce_tech_ai_race(
    db: Any,
    *,
    rule: Optional[Mapping[str, Any]] = None,
    now: Optional[datetime] = None,
) -> RoundupMembers | RoundupRefusal:
    cfg_rule = dict(rule or {})
    min_b = int(cfg_rule.get("min_benchmarks") or 3)
    max_r = int(cfg_rule.get("max_card_rows") or 4)
    max_q = float(cfg_rule.get("max_quote_age_hours") or 48.0)
    min_v = float(cfg_rule.get("min_volume_24h") or 100.0)

    if isinstance(db, (list, tuple)):
        return select_tech_ai_race(
            db,
            now=now,
            min_benchmarks=min_b,
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
                FuturesMarket.name.ilike("%best AI model%"),
                FuturesMarket.name.ilike("%best coding model%"),
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
    return select_tech_ai_race(
        serialized,
        now=effective_now,
        min_benchmarks=min_b,
        max_card_rows=max_r,
        max_quote_age_hours=max_q,
        min_volume_24h=min_v,
    )


def load_candidate_definition(path: Path = CANDIDATE_AI_RACE_PATH) -> dict[str, Any]:
    defn = json.loads(path.read_text(encoding="utf-8"))
    validate_roundup_definition(defn)
    return defn


def load_candidate_eval_rows(
    path: Path = CANDIDATE_AI_RACE_ROWS_PATH,
) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_tech_ai_race_producer(
    defn: Optional[Mapping[str, Any]] = None,
) -> RoundupProducer:
    resolved = dict(defn) if defn is not None else load_candidate_definition()
    validate_roundup_definition(resolved)
    rule = dict(resolved.get("rule") or {})

    async def _produce(db: Any) -> RoundupMembers | RoundupRefusal:
        return await produce_tech_ai_race(db, rule=rule)

    return RoundupProducer(
        slug=str(resolved["slug"]),
        name=str(resolved["name"]),
        kind=str(resolved.get("kind") or "roundup"),
        category=str(resolved["category"]),
        section_title=str(resolved["section_title"]),
        footer=str(resolved["footer"]),
        produce=_produce,
        membership=str(resolved.get("membership") or PRODUCER_KIND_TECH_AI_RACE),
        relations=tuple(resolved["relations"]),
        level=str(resolved["level"]),
        rule=rule,
        tag=resolved.get("tag"),
        kicker=str(resolved.get("kicker") or "TECH · AI BENCHMARKS"),
        order=str(resolved.get("order") or "sequence"),
        score=float(resolved.get("score") or 93.0),
        enabled=(lambda: bool(resolved["enabled"])) if "enabled" in resolved else None,
    )


def compose_ai_race_card_and_container(
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


def build_ai_race_grading_candidate(
    producer: RoundupProducer,
    members: RoundupMembers,
) -> dict[str, Any]:
    feed_item, _ = compose_ai_race_card_and_container(producer, members)
    roundup = feed_item["data"]["roundup"]
    rows = list(roundup["rows"])
    best_row = min(rows, key=lambda r: abs(float(r["probability"]) - 0.5))
    return {
        "item_key": producer.slug,
        "kind": PRODUCER_KIND_TECH_AI_RACE,
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
