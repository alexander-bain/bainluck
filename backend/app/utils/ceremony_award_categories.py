"""Dynamic ``ceremony_award_categories`` grouped-card producer (#12288 Wave 2, Idea #7).

PILLAR: DISCOVER · MATCHING · TRUTH
SHIP: Ceremony award-category slate (Grammys, Oscars, Emmys, Golden Globes) that
groups actively trading single-winner categories for the same ceremony and stage
(never mixing Winner markets with Nominations markets), blends cross-source
category twins via ``futures_source_merge.blend_with_verdict`` (refusing 40+ pt
disagreements), drops quiet/untraded categories (e.g. Record of the Year and
Song of the Year when 24h volume is $0), and writes a clear ``context_line``
naming the ceremony, stage, and leading frontrunner.

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
    "CANDIDATE_CEREMONY_AWARD_CATEGORIES_PATH",
    "CANDIDATE_CEREMONY_AWARD_CATEGORIES_ROWS_PATH",
    "CeremonyCategoryRow",
    "PRODUCER_KIND_CEREMONY_AWARD_CATEGORIES",
    "build_ceremony_award_categories_CandidatePack",
    "build_ceremony_award_categories_producer",
    "compose_ceremony_award_card_and_container",
    "is_actively_trading_award_market",
    "load_candidate_definition",
    "load_candidate_eval_rows",
    "produce_ceremony_award_categories",
    "select_ceremony_award_categories",
]

PRODUCER_KIND_CEREMONY_AWARD_CATEGORIES = "ceremony_award_categories"

_CANDIDATES_DIR = Path(__file__).resolve().parents[2] / "data" / "discover" / "candidates"
CANDIDATE_CEREMONY_AWARD_CATEGORIES_PATH = (
    _CANDIDATES_DIR / "roundup-ceremony-award-categories.json"
)
CANDIDATE_CEREMONY_AWARD_CATEGORIES_ROWS_PATH = (
    _CANDIDATES_DIR / "roundup-ceremony-award-categories-rows.json"
)

_FORBIDDEN_COPY_RE = re.compile(
    r"\b(?:questions?|stale|venues?|kalshi|polymarket|opened)\b",
    re.IGNORECASE,
)

_EXCLUDED_NON_CATEGORY_RE = re.compile(
    r"\b(?:host|halftime|ratings|viewers|how\s+many|speech|length|outfit|perform)\b",
    re.IGNORECASE,
)

_CEREMONY_LABELS: dict[str, tuple[str, re.Pattern[str]]] = {
    "grammys": (
        "2027 Grammy Awards",
        re.compile(r"\bgrammys?(?:\s+\d{4})?\b", re.IGNORECASE),
    ),
    "oscars": (
        "2027 Oscars",
        re.compile(r"\b(?:oscars?|academy\s+awards?)(?:\s+\d{4})?\b", re.IGNORECASE),
    ),
    "emmys": (
        "Emmys",
        re.compile(r"\bemmys?(?:\s+\d{4})?\b", re.IGNORECASE),
    ),
    "golden_globes": (
        "Golden Globes",
        re.compile(r"\bgolden\s+globes?(?:\s+\d{4})?\b", re.IGNORECASE),
    ),
}

_CATEGORY_PRIORITY: dict[str, int] = {
    "best picture": 1,
    "album of the year": 1,
    "record of the year": 2,
    "song of the year": 3,
    "best director": 4,
    "best actor": 5,
    "best actress": 6,
    "best new artist": 7,
    "best rap album": 8,
}


@dataclass(frozen=True)
class CeremonyCategoryRow:
    category_key: str
    category_label: str
    leader_name: str
    probability: float
    primary_market_id: int
    contributing_ids: tuple[int, ...]
    priority: int


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


def is_actively_trading_award_market(
    market: Mapping[str, Any],
    *,
    now: Optional[datetime] = None,
    max_quote_age_hours: float = 36.0,
    max_trade_age_days: float = 7.0,
    min_volume_24h: float = 100.0,
) -> bool:
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
            if (ref_now - last_trade).total_seconds() / 86400.0 > float(max_trade_age_days):
                return False

        quote_ts = _parse_iso_utc(
            market.get("price_observed_at")
            or market.get("updated_at")
            or market.get("last_updated")
        )
        if quote_ts is not None:
            if (ref_now - quote_ts).total_seconds() / 3600.0 > float(max_quote_age_hours):
                return False

    return True


def _detect_stage(title: str) -> str:
    if re.search(r"\bnominat(?:ion|ions|ed|ee|ees)\b", title, re.IGNORECASE):
        return "nominations"
    return "winner"


def _extract_category_label(title: str, ceremony_pat: re.Pattern[str]) -> Optional[str]:
    if _EXCLUDED_NON_CATEGORY_RE.search(title):
        return None
    cleaned = ceremony_pat.sub("", title)
    cleaned = re.sub(r"\b(?:winner|winners|nominations?|nominees?)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^[\s:\-·—]+|[\s:\-·—?]+$", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned or len(cleaned) < 4 or _FORBIDDEN_COPY_RE.search(cleaned):
        return None
    return cleaned


def _clean_contender_name(raw: Any) -> Optional[str]:
    text = re.sub(r"\s+", " ", str(raw or "").strip())
    low = text.lower()
    if not low or low in {"yes", "no", "other", "field", "none"}:
        return None
    if _FORBIDDEN_COPY_RE.search(text):
        return None
    return text


def _normalize_contender_key(name: str) -> str:
    # Match "you seem pretty sad for a girl so in love - Olivia Rodrigo" with
    # "you seem pretty sad for a girl so in love"
    base = name.split(" - ")[0].strip().lower()
    return re.sub(r"[^a-z0-9]+", " ", base).strip()


def select_ceremony_award_categories(
    markets: Sequence[Mapping[str, Any]],
    *,
    now: Optional[datetime] = None,
    ceremony: str = "grammys",
    stage: str = "winner",
    min_categories: int = 3,
    max_card_rows: int = 5,
    min_contenders_per_category: int = 3,
    max_quote_age_hours: float = 36.0,
    max_trade_age_days: float = 7.0,
    min_volume_24h: float = 100.0,
) -> RoundupMembers | RoundupRefusal:
    ceremony_key = ceremony.strip().lower()
    if ceremony_key not in _CEREMONY_LABELS:
        return RoundupRefusal([("unknown_ceremony", ceremony_key)])
    ceremony_title, ceremony_pat = _CEREMONY_LABELS[ceremony_key]
    target_stage = stage.strip().lower()

    grouped: dict[str, dict[str, tuple[Mapping[str, Any], str, dict[str, tuple[str, float]]]]] = {}

    for m in markets:
        if not isinstance(m, Mapping) or not isinstance(m.get("id"), int):
            continue
        title = str(m.get("name") or m.get("title") or "").strip()
        if not title or not ceremony_pat.search(title):
            continue
        if _detect_stage(title) != target_stage:
            continue
        if not is_actively_trading_award_market(
            m,
            now=now,
            max_quote_age_hours=max_quote_age_hours,
            max_trade_age_days=max_trade_age_days,
            min_volume_24h=min_volume_24h,
        ):
            continue

        cat_label = _extract_category_label(title, ceremony_pat)
        if not cat_label:
            continue
        cat_key = cat_label.lower()
        src = str(m.get("source") or "primary").strip().lower()

        outcomes = m.get("outcomes") or m.get("top_outcomes") or ()
        contenders: dict[str, tuple[str, float]] = {}
        for out in outcomes:
            if not isinstance(out, Mapping):
                continue
            cname = _clean_contender_name(out.get("name"))
            if not cname:
                continue
            p_raw = out.get("probability")
            if p_raw is None:
                continue
            try:
                p = float(p_raw)
            except (TypeError, ValueError):
                continue
            if not (0.01 <= p <= 0.995):
                continue
            ckey = _normalize_contender_key(cname)
            if not ckey:
                continue
            prev = contenders.get(ckey)
            if prev is None or p > prev[1]:
                contenders[ckey] = (cname, p)

        if len(contenders) < max(2, int(min_contenders_per_category)):
            continue

        by_src = grouped.setdefault(cat_key, {})
        if src not in by_src or len(contenders) > len(by_src[src][2]):
            by_src[src] = (m, cat_label, contenders)

    if not grouped:
        return RoundupRefusal([("no_trading_ceremony_categories", ceremony_key, target_stage)])

    category_rows: list[CeremonyCategoryRow] = []
    divergence_reasons: list[tuple[Any, ...]] = []
    by_market_id: dict[int, Mapping[str, Any]] = {}

    for cat_key, by_src in sorted(grouped.items()):
        sources_sorted = sorted(by_src.keys())
        primary_src = "kalshi" if "kalshi" in by_src else sources_sorted[0]
        primary_mkt, display_cat, _ = by_src[primary_src]
        primary_id = int(primary_mkt["id"])
        contrib_ids = tuple(int(by_src[s][0]["id"]) for s in sources_sorted)
        for s in sources_sorted:
            by_market_id[int(by_src[s][0]["id"])] = by_src[s][0]

        all_ckeys: set[str] = set()
        for _, _, cmap in by_src.values():
            all_ckeys.update(cmap.keys())

        blended_contenders: list[tuple[str, float]] = []
        cat_diverged = False
        for ckey in sorted(all_ckeys):
            rows_for_blend = [
                {"source": s, "probability": by_src[s][2][ckey][1]}
                for s in sources_sorted
                if ckey in by_src[s][2]
            ]
            # Prefer richest display label (e.g. "Song - Artist")
            best_display = max(
                (by_src[s][2][ckey][0] for s in sources_sorted if ckey in by_src[s][2]),
                key=len,
            )
            if len(rows_for_blend) >= 2:
                val, divergence, rule_name = blend_with_verdict(rows_for_blend)
                if divergence is not None or rule_name == "divergence_gate" or val is None:
                    divergence_reasons.append(("category_divergence_gate", cat_key, best_display))
                    cat_diverged = True
                    break
                blended_contenders.append((best_display, float(val)))
            else:
                blended_contenders.append((best_display, float(rows_for_blend[0]["probability"])))

        if cat_diverged or not blended_contenders:
            continue

        blended_contenders.sort(key=lambda item: (-item[1], item[0]))
        leader_name, leader_prob = blended_contenders[0]
        prio = _CATEGORY_PRIORITY.get(cat_key, 50)
        category_rows.append(
            CeremonyCategoryRow(
                category_key=cat_key,
                category_label=display_cat,
                leader_name=leader_name,
                probability=leader_prob,
                primary_market_id=primary_id,
                contributing_ids=contrib_ids,
                priority=prio,
            )
        )

    if divergence_reasons:
        return RoundupRefusal(divergence_reasons)

    if len(category_rows) < max(2, int(min_categories)):
        return RoundupRefusal(
            [("insufficient_trading_categories", len(category_rows), int(min_categories))]
        )

    category_rows.sort(key=lambda r: (r.priority, -abs(0.5 - abs(r.probability - 0.5)), r.category_label))
    shown = category_rows[: max(2, int(max_card_rows))]
    lead = shown[0]

    stage_word = "Winner" if target_stage == "winner" else "Nomination"
    card_title = f"{ceremony_title} — active categories"
    context_line = _assert_clean_copy(
        f"Actively trading {ceremony_title} {stage_word} categories (quiet and untraded "
        f"categories excluded), showing each category's frontrunner — led by "
        f"{lead.category_label} ({lead.leader_name}, {int(round(lead.probability * 100))}%)."
    )
    footer = _assert_clean_copy(
        f"Single-winner {ceremony_title} categories · frontrunner chance per category"
    )

    rows = [
        {
            "market_id": r.primary_market_id,
            "category_label": _assert_clean_copy(r.category_label),
            "leader": _assert_clean_copy(r.leader_name),
            "label": _assert_clean_copy(f"{r.category_label} — {r.leader_name}"),
            "probability": round(r.probability, 4),
            "rendered_percent": int(round(r.probability * 100)),
            "destination": market_destination(r.primary_market_id),
        }
        for r in shown
    ]

    seen_ids: list[int] = []
    for r in shown:
        for mid in r.contributing_ids:
            if mid not in seen_ids:
                seen_ids.append(mid)

    members = [{"id": mid, "type": "futures", "card": dict(by_market_id[mid])} for mid in seen_ids]

    return RoundupMembers(
        members=members,
        rows=rows,
        footer=footer,
        count_line=f"{len(category_rows)} active categories",
        title=_assert_clean_copy(card_title),
        kicker="CULTURE · AWARDS SLATE",
        revision_ids=seen_ids,
        sections=(
            {
                "title": f"Active {ceremony_title} {stage_word} categories",
                "context_line": context_line,
                "member_ids": seen_ids,
            },
        ),
    )


async def produce_ceremony_award_categories(
    db: Any,
    *,
    rule: Optional[Mapping[str, Any]] = None,
    now: Optional[datetime] = None,
) -> RoundupMembers | RoundupRefusal:
    cfg = dict(rule or {})
    if isinstance(db, (list, tuple)):
        return select_ceremony_award_categories(
            db,
            now=now,
            ceremony=str(cfg.get("ceremony") or "grammys"),
            stage=str(cfg.get("stage") or "winner"),
            min_categories=int(cfg.get("min_categories") or 3),
            max_card_rows=int(cfg.get("max_card_rows") or 5),
            min_contenders_per_category=int(cfg.get("min_contenders_per_category") or 3),
            max_quote_age_hours=float(cfg.get("max_quote_age_hours") or 36.0),
            max_trade_age_days=float(cfg.get("max_trade_age_days") or 7.0),
            min_volume_24h=float(cfg.get("min_volume_24h") or 100.0),
        )
    return RoundupRefusal([("unsupported_session", type(db).__name__)])


def load_candidate_definition(
    path: Path = CANDIDATE_CEREMONY_AWARD_CATEGORIES_PATH,
) -> dict[str, Any]:
    defn = json.loads(path.read_text(encoding="utf-8"))
    validate_roundup_definition(defn)
    return defn


def load_candidate_eval_rows(
    path: Path = CANDIDATE_CEREMONY_AWARD_CATEGORIES_ROWS_PATH,
) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_ceremony_award_categories_producer(
    defn: Optional[Mapping[str, Any]] = None,
) -> RoundupProducer:
    resolved = dict(defn) if defn is not None else load_candidate_definition()
    validate_roundup_definition(resolved)
    rule = dict(resolved.get("rule") or {})

    async def _produce(db: Any) -> RoundupMembers | RoundupRefusal:
        return await produce_ceremony_award_categories(db, rule=rule)

    return RoundupProducer(
        slug=str(resolved["slug"]),
        name=str(resolved["name"]),
        kind=str(resolved.get("kind") or "roundup"),
        category=str(resolved["category"]),
        section_title=str(resolved["section_title"]),
        footer=str(resolved["footer"]),
        produce=_produce,
        membership=str(resolved.get("membership") or PRODUCER_KIND_CEREMONY_AWARD_CATEGORIES),
        relations=tuple(resolved["relations"]),
        level=str(resolved["level"]),
        rule=rule,
        tag=resolved.get("tag"),
        kicker=str(resolved.get("kicker") or "CULTURE · AWARDS SLATE"),
        score=float(resolved.get("score") or 92.0),
    )


def compose_ceremony_award_card_and_container(
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


def build_ceremony_award_categories_CandidatePack(
    producer: RoundupProducer,
    members: RoundupMembers,
) -> dict[str, Any]:
    feed_item, _ = compose_ceremony_award_card_and_container(producer, members)
    roundup = feed_item["data"]["roundup"]
    rows = list(roundup["rows"])
    best_row = min(rows, key=lambda r: abs(float(r["probability"]) - 0.5))
    return {
        "item_key": producer.slug,
        "kind": PRODUCER_KIND_CEREMONY_AWARD_CATEGORIES,
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
        },
    }
