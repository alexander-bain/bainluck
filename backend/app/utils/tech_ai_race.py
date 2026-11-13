"""Dynamic ``tech_ai_race`` grouped-card producer (#12288 Wave 1, Idea #12).

PILLAR: DISCOVER · MATCHING · TRUTH
SHIP: Dynamic AI leaderboard container selecting open single-winner AI model
benchmark races (month-end overall Arena, year-end overall Arena, Coding Arena,
LiveBench Coding), blending identical benchmark twins via
``futures_source_merge.blend_with_verdict`` while keeping distinct benchmarks
separate so different settlement rules are never conflated, and emitting a
clear ``context_line`` naming the settlement benchmark behind each row.

Publication gate: candidate definition lives in ``backend/data/discover/candidates/``
and is NOT registered in ``ROUNDUP_PRODUCERS`` until licensed via the Discover
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
    "PRODUCER_KIND_TECH_AI_RACE",
    "BenchmarkStanding",
    "build_ai_race_grading_candidate",
    "build_tech_ai_race_producer",
    "compose_ai_race_card_and_container",
    "load_candidate_definition",
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

_FORBIDDEN_COPY_RE = re.compile(
    r"\b(?:questions?|stale|venues?|kalshi|polymarket|opened)\b",
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
    return _LAB_ALIASES.get(low, cleaned)


def _classify_ai_benchmark(market: Mapping[str, Any]) -> Optional[tuple[str, str, str]]:
    title = str(market.get("name") or market.get("title") or "").strip()
    if not title or _EXCLUDED_AI_SHAPE_RE.search(title):
        return None
    for slot_key, label, track, pat in _AI_BENCHMARK_SLOTS:
        if "livebench" in title.lower() and slot_key != "livebench_coding":
            continue
        if pat.search(title):
            # Refine month label if month-end
            if slot_key == "arena_month_end":
                m = re.search(
                    r"\bend\s+of\s+(january|february|march|april|may|june|july|august|september|october|november|december)\b",
                    title,
                    re.IGNORECASE,
                )
                if m:
                    mon = m.group(1).capitalize()[:3]
                    return slot_key, f"Overall Arena · End of {mon}", track
            return slot_key, label, track
    return None


def _extract_labs(market: Mapping[str, Any]) -> dict[str, float]:
    if str(market.get("status") or "open").strip().lower() != "open":
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
) -> Optional[BenchmarkStanding]:
    by_source: dict[str, tuple[Mapping[str, Any], dict[str, float]]] = {}
    for m in slot_markets:
        src = str(m.get("source") or "").strip().lower()
        if not src:
            continue
        labs = _extract_labs(m)
        if len(labs) < 2:
            continue
        if src not in by_source or len(labs) > len(by_source[src][1]):
            by_source[src] = (m, labs)
    if not by_source:
        return None

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
                return None
            blended.append((lab, float(val)))
        elif len(by_source) == 1:
            blended.append((lab, float(rows_for_blend[0]["probability"])))

    if len(blended) < 2:
        return None
    blended.sort(key=lambda x: (-x[1], x[0]))
    leader_lab, leader_prob = blended[0]
    runner_lab, runner_prob = blended[1]
    primary_src = "kalshi" if "kalshi" in by_source else sources_sorted[0]
    primary_card = dict(by_source[primary_src][0])
    contrib_ids = tuple(sorted(int(by_source[s][0]["id"]) for s in sources_sorted))

    return BenchmarkStanding(
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
    )


def _compose_context_line(standings: Sequence[BenchmarkStanding]) -> str:
    overall_leaders = {s.leader_lab for s in standings if s.track == "overall"}
    coding_leaders = {s.leader_lab for s in standings if s.track == "coding"}
    n = len(standings)
    if len(overall_leaders) == 1 and len(coding_leaders) == 1:
        ov_lab = next(iter(overall_leaders))
        cd_lab = next(iter(coding_leaders))
        if ov_lab != cd_lab:
            return _assert_clean_copy(
                f"{n} live AI model leaderboards side by side — {ov_lab} leads overall "
                f"evaluations while {cd_lab} leads coding; each row settles on its named benchmark."
            )
    top = standings[0]
    return _assert_clean_copy(
        f"{n} live AI model leaderboards across overall and coding evaluations — "
        f"{top.leader_lab} leads {top.benchmark_label} at {int(round(top.leader_probability * 100))}%; "
        f"each row settles on its own named benchmark."
    )


def select_tech_ai_race(
    markets: Sequence[Mapping[str, Any]],
    *,
    min_benchmarks: int = 3,
    max_card_rows: int = 4,
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

    ordered_keys = [s[0] for s in _AI_BENCHMARK_SLOTS]
    standings: list[BenchmarkStanding] = []
    for key in ordered_keys:
        if key not in slot_buckets:
            continue
        label, track, bucket = slot_buckets[key]
        resolved = _resolve_slot(key, label, track, bucket)
        if resolved is not None:
            standings.append(resolved)

    if len(standings) < max(2, int(min_benchmarks)):
        return RoundupRefusal([("insufficient_ai_benchmarks", len(standings), int(min_benchmarks))])

    card_standings = standings[: max(2, int(max_card_rows))]
    context_line = _compose_context_line(card_standings)
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
        title="The AI model race",
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
    _ = now or datetime.now(timezone.utc)
    cfg_rule = dict(rule or {})
    min_b = int(cfg_rule.get("min_benchmarks") or 3)
    max_r = int(cfg_rule.get("max_card_rows") or 4)

    if isinstance(db, (list, tuple)):
        return select_tech_ai_race(db, min_benchmarks=min_b, max_card_rows=max_r)

    from sqlalchemy import or_, select
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import selectinload

    if not isinstance(db, AsyncSession):
        return RoundupRefusal([("unsupported_session", type(db).__name__)])

    from app.models.models import FuturesMarket

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
            "outcomes": [
                {"name": o.name, "probability": o.probability}
                for o in (m.outcomes or [])
            ],
        }
        for m in orm_rows
    ]
    return select_tech_ai_race(serialized, min_benchmarks=min_b, max_card_rows=max_r)


def load_candidate_definition(path: Path = CANDIDATE_AI_RACE_PATH) -> dict[str, Any]:
    defn = json.loads(path.read_text(encoding="utf-8"))
    validate_roundup_definition(defn)
    return defn


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
        score=float(resolved.get("score") or 93.0),
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
