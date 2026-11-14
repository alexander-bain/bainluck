"""Dynamic ``opening_weekend_slate`` grouped-card producer (#12288 Wave 2, Idea #8).

PILLAR: DISCOVER · MATCHING · TRUTH
SHIP: Opening-weekend box office slate grouping actively trading domestic
opening-weekend bracket markets across upcoming theatrical releases, formatting
each film's modal gross range cleanly (e.g. ``$16M–$19M``, ``$400M+``,
``$110M–$130M``), rejecting trivial cumulative floor brackets (``Above $2.5M``
at 98%) and untraded Rotten Tomatoes / stale markets, and keeping 2nd-weekend
holdovers out of opening-weekend slates unless explicitly requested.

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
    "CANDIDATE_OPENING_WEEKEND_SLATE_PATH",
    "CANDIDATE_OPENING_WEEKEND_SLATE_ROWS_PATH",
    "OpeningWeekendFilm",
    "PRODUCER_KIND_OPENING_WEEKEND_SLATE",
    "build_opening_weekend_slate_CandidatePack",
    "build_opening_weekend_slate_producer",
    "compose_opening_weekend_card_and_container",
    "format_box_office_bracket",
    "is_actively_trading_box_office_market",
    "load_candidate_definition",
    "load_candidate_eval_rows",
    "produce_opening_weekend_slate",
    "select_opening_weekend_slate",
]

PRODUCER_KIND_OPENING_WEEKEND_SLATE = "opening_weekend_slate"

_CANDIDATES_DIR = Path(__file__).resolve().parents[2] / "data" / "discover" / "candidates"
CANDIDATE_OPENING_WEEKEND_SLATE_PATH = _CANDIDATES_DIR / "roundup-opening-weekend-slate.json"
CANDIDATE_OPENING_WEEKEND_SLATE_ROWS_PATH = (
    _CANDIDATES_DIR / "roundup-opening-weekend-slate-rows.json"
)

_FORBIDDEN_COPY_RE = re.compile(
    r"\b(?:questions?|stale|venues?|kalshi|polymarket|opened)\b",
    re.IGNORECASE,
)

_OPENING_BOX_OFFICE_RE = re.compile(
    r'^\s*["“]?([^"”]+?)["”]?\s+opening\s+weekend\s+box\s+office\b',
    re.IGNORECASE,
)
_HOLDOVER_WEEKEND_RE = re.compile(
    r"\b(?:2nd|3rd|second|third)\s+weekend\s+box\s+office\b",
    re.IGNORECASE,
)
_ROTTEN_TOMATOES_RE = re.compile(r"\brotten\s+tomatoes\b", re.IGNORECASE)


@dataclass(frozen=True)
class OpeningWeekendFilm:
    market_id: int
    film_title: str
    bracket_label: str
    probability: float
    volume_24h: float
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


def is_actively_trading_box_office_market(
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


def format_box_office_bracket(raw: str) -> Optional[str]:
    """Normalize '16m-19m' -> '$16M–$19M', '400m+' -> '$400M+', '<16m' -> 'Under $16M'."""
    txt = re.sub(r"\s+", " ", str(raw or "").strip())
    if not txt or _FORBIDDEN_COPY_RE.search(txt):
        return None
    # Reject cumulative floor/ceiling threshold phrasing when >=95% floor traps occur
    if re.match(r"^(?:above|over|at\s+least)\s+", txt, re.IGNORECASE):
        return None

    m_range = re.match(
        r"^\$?(\d+(?:\.\d+)?)\s*([mMbB])\s*[-–—to]+\s*\$?(\d+(?:\.\d+)?)\s*([mMbB])$",
        txt,
    )
    if m_range:
        lo, u1, hi, u2 = m_range.groups()
        return f"${lo}{u1.upper()}–${hi}{u2.upper()}"

    m_plus = re.match(r"^\$?(\d+(?:\.\d+)?)\s*([mMbB])\+$", txt)
    if m_plus:
        val, u = m_plus.groups()
        return f"${val}{u.upper()}+"

    m_under = re.match(r"^(?:<|under\s+)\$?(\d+(?:\.\d+)?)\s*([mMbB])$", txt, re.IGNORECASE)
    if m_under:
        val, u = m_under.groups()
        return f"Under ${val}{u.upper()}"

    return txt


def _select_modal_bracket(outcomes: Sequence[Mapping[str, Any]]) -> Optional[tuple[str, float]]:
    valid: list[tuple[str, float, str]] = []
    raw_sum = 0.0
    for out in outcomes:
        if not isinstance(out, Mapping):
            continue
        raw_name = str(out.get("name") or "").strip()
        p_raw = out.get("probability")
        if not raw_name or p_raw is None:
            continue
        try:
            p = float(p_raw)
        except (TypeError, ValueError):
            continue
        if p <= 0.0 or p > 1.0:
            continue
        raw_sum += p
        formatted = format_box_office_bracket(raw_name)
        if formatted is not None:
            valid.append((formatted, p, raw_name))

    if len(valid) < 3:
        return None
    # Guard against cumulative non-exclusive ladders summing > 1.35 (e.g. Above $2.5M = 98%)
    if raw_sum > 1.35:
        return None

    valid.sort(key=lambda item: (-item[1], item[0]))
    best_label, best_prob, raw_best = valid[0]
    # Never headline a trivial `<$2.5M (92%)` micro-floor trap if it is an 'Under' ceiling > 90%
    if best_label.startswith("Under ") and best_prob >= 0.90:
        return None
    del raw_best
    return best_label, best_prob


def select_opening_weekend_slate(
    markets: Sequence[Mapping[str, Any]],
    *,
    now: Optional[datetime] = None,
    opening_only: bool = True,
    min_films: int = 3,
    max_card_rows: int = 5,
    max_quote_age_hours: float = 36.0,
    max_trade_age_days: float = 7.0,
    min_volume_24h: float = 100.0,
) -> RoundupMembers | RoundupRefusal:
    films_by_key: dict[str, OpeningWeekendFilm] = {}

    for m in markets:
        if not isinstance(m, Mapping) or not isinstance(m.get("id"), int):
            continue
        title = str(m.get("name") or m.get("title") or "").strip()
        if not title or _ROTTEN_TOMATOES_RE.search(title):
            continue
        if opening_only and _HOLDOVER_WEEKEND_RE.search(title):
            continue

        m_open = _OPENING_BOX_OFFICE_RE.search(title)
        if not m_open:
            continue
        film_title = re.sub(r"\s+", " ", m_open.group(1)).strip()
        if not film_title or _FORBIDDEN_COPY_RE.search(film_title):
            continue

        if not is_actively_trading_box_office_market(
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
        modal = _select_modal_bracket(outcomes)
        if modal is None:
            continue
        bracket_label, prob = modal
        vol24 = float(m.get("volume_24h") or m.get("volume24hr") or 0.0)
        fkey = film_title.lower()

        cand = OpeningWeekendFilm(
            market_id=int(m["id"]),
            film_title=film_title,
            bracket_label=bracket_label,
            probability=prob,
            volume_24h=vol24,
            card=dict(m),
        )
        prev = films_by_key.get(fkey)
        if prev is None or cand.volume_24h > prev.volume_24h:
            films_by_key[fkey] = cand

    if len(films_by_key) < max(2, int(min_films)):
        return RoundupRefusal(
            [("insufficient_trading_opening_films", len(films_by_key), int(min_films))]
        )

    # Order by sharpest contested bracket near 50% (tie-breaking by 24h trading activity)
    ordered = sorted(
        films_by_key.values(),
        key=lambda f: (-f.volume_24h, abs(f.probability - 0.5), f.film_title),
    )
    shown = ordered[: max(2, int(max_card_rows))]
    lead = shown[0]
    blockbuster = next(
        (f for f in shown if "$400M+" in f.bracket_label or "$360M" in f.bracket_label),
        None,
    )
    if blockbuster is not None and blockbuster.market_id != lead.market_id:
        card_title = _assert_clean_copy(
            f"Box office openings — {lead.bracket_label} to {blockbuster.bracket_label}"
        )
        context_line = _assert_clean_copy(
            f"{len(shown)} upcoming wide releases with active opening-weekend brackets "
            f"(2nd-weekend holdovers excluded) — led by {lead.film_title} "
            f"({lead.bracket_label} at {int(round(lead.probability * 100))}%) up to "
            f"{blockbuster.film_title} ({blockbuster.bracket_label} at "
            f"{int(round(blockbuster.probability * 100))}%, above the $357M all-time domestic opening record)."
        )
    else:
        card_title = "Opening-weekend box office forecasts"
        context_line = _assert_clean_copy(
            f"Actively trading domestic opening-weekend box office brackets across {len(shown)} "
            f"upcoming releases (2nd-weekend holdovers excluded), showing each film's likeliest "
            f"gross range — led by {lead.film_title} ({lead.bracket_label} at "
            f"{int(round(lead.probability * 100))}%)."
        )
    footer = _assert_clean_copy(
        "Most likely domestic opening-weekend bracket · actively trading film markets"
    )

    rows = [
        {
            "market_id": f.market_id,
            "film": _assert_clean_copy(f.film_title),
            "bracket": _assert_clean_copy(f.bracket_label),
            "label": _assert_clean_copy(f"{f.film_title} — {f.bracket_label}"),
            "probability": round(f.probability, 4),
            "rendered_percent": int(round(f.probability * 100)),
            "destination": market_destination(f.market_id),
        }
        for f in shown
    ]

    contrib_ids = [f.market_id for f in shown]
    members = [{"id": f.market_id, "type": "futures", "card": dict(f.card)} for f in shown]

    return RoundupMembers(
        members=members,
        rows=rows,
        footer=footer,
        count_line=f"{len(ordered)} upcoming releases",
        title=card_title,
        kicker="CULTURE · BOX OFFICE",
        revision_ids=contrib_ids,
        sections=(
            {
                "title": "Active opening-weekend box office forecasts",
                "context_line": context_line,
                "member_ids": contrib_ids,
            },
        ),
    )


async def produce_opening_weekend_slate(
    db: Any,
    *,
    rule: Optional[Mapping[str, Any]] = None,
    now: Optional[datetime] = None,
) -> RoundupMembers | RoundupRefusal:
    cfg = dict(rule or {})
    opening_only = bool(cfg.get("opening_only", True))
    min_f = int(cfg.get("min_films") or 3)
    max_r = int(cfg.get("max_card_rows") or 5)
    max_q = float(cfg.get("max_quote_age_hours") or 36.0)
    max_t = float(cfg.get("max_trade_age_days") or 7.0)
    min_v = float(cfg.get("min_volume_24h") or 100.0)
    if isinstance(db, (list, tuple)):
        return select_opening_weekend_slate(
            db,
            now=now,
            opening_only=opening_only,
            min_films=min_f,
            max_card_rows=max_r,
            max_quote_age_hours=max_q,
            max_trade_age_days=max_t,
            min_volume_24h=min_v,
        )
    from datetime import timezone
    from sqlalchemy import select
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
            FuturesMarket.name.ilike("%box office%"),
        )
    )
    res = await db.execute(stmt)
    orm_rows = res.scalars().all()
    serialized = [
        {
            "id": int(m.id),
            "source": m.source,
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
        for m in orm_rows
    ]
    return select_opening_weekend_slate(
        serialized,
        now=effective_now,
        opening_only=opening_only,
        min_films=min_f,
        max_card_rows=max_r,
        max_quote_age_hours=max_q,
        max_trade_age_days=max_t,
        min_volume_24h=min_v,
    )


def load_candidate_definition(
    path: Path = CANDIDATE_OPENING_WEEKEND_SLATE_PATH,
) -> dict[str, Any]:
    defn = json.loads(path.read_text(encoding="utf-8"))
    validate_roundup_definition(defn)
    return defn


def load_candidate_eval_rows(
    path: Path = CANDIDATE_OPENING_WEEKEND_SLATE_ROWS_PATH,
) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_opening_weekend_slate_producer(
    defn: Optional[Mapping[str, Any]] = None,
) -> RoundupProducer:
    resolved = dict(defn) if defn is not None else load_candidate_definition()
    validate_roundup_definition(resolved)
    rule = dict(resolved.get("rule") or {})

    async def _produce(db: Any) -> RoundupMembers | RoundupRefusal:
        return await produce_opening_weekend_slate(db, rule=rule)

    return RoundupProducer(
        slug=str(resolved["slug"]),
        name=str(resolved["name"]),
        kind=str(resolved.get("kind") or "roundup"),
        category=str(resolved["category"]),
        section_title=str(resolved["section_title"]),
        footer=str(resolved["footer"]),
        produce=_produce,
        membership=str(resolved.get("membership") or PRODUCER_KIND_OPENING_WEEKEND_SLATE),
        relations=tuple(resolved["relations"]),
        level=str(resolved["level"]),
        rule=rule,
        tag=resolved.get("tag"),
        kicker=str(resolved.get("kicker") or "CULTURE · BOX OFFICE"),
        order=str(resolved.get("order") or "sequence"),
        score=float(resolved.get("score") or 91.5),
        enabled=(lambda: bool(resolved["enabled"])) if "enabled" in resolved else None,
    )


def compose_opening_weekend_card_and_container(
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


def build_opening_weekend_slate_CandidatePack(
    producer: RoundupProducer,
    members: RoundupMembers,
) -> dict[str, Any]:
    feed_item, _ = compose_opening_weekend_card_and_container(producer, members)
    roundup = feed_item["data"]["roundup"]
    rows = list(roundup["rows"])
    best_row = min(rows, key=lambda r: abs(float(r["probability"]) - 0.5))
    return {
        "item_key": producer.slug,
        "kind": PRODUCER_KIND_OPENING_WEEKEND_SLATE,
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
