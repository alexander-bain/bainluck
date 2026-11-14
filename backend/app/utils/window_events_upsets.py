"""Dynamic ``window_events_upsets`` grouped-card producer (#12288 Wave 1, Idea #3).

PILLAR: DISCOVER · TRUTH
SHIP: Live game upset-watch container over ``sports-day`` live ``Event`` rows
where a pregame underdog (``pregame <= 40%``) either leads on the scoreboard or
holds ``>= 50%`` live blended win probability. Auto-withholds whenever fewer
than ``min_members`` (default 3) live games qualify, prints swings strictly in
points (never ``%``), uses ``Pregame`` (never ``Opened``), and emits a clear
``context_line`` stating the exact ``<=40%`` pregame rule.

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

from app.utils.container_presentation import event_destination
from app.utils.roundup_containers import (
    RoundupMembers,
    RoundupProducer,
    RoundupRefusal,
    compose_roundup_container,
    compose_roundup_feed_item,
    validate_roundup_definition,
)
from app.utils.window_events_closest import resolve_window

__all__ = [
    "CANDIDATE_UPSETS_BREWING_PATH",
    "CANDIDATE_UPSETS_BREWING_ROWS_PATH",
    "PRODUCER_KIND_WINDOW_EVENTS_UPSETS",
    "UpsetStanding",
    "build_upsets_brewing_grading_candidate",
    "build_window_events_upsets_producer",
    "compose_upsets_brewing_card_and_container",
    "load_candidate_definition",
    "load_candidate_eval_rows",
    "produce_window_events_upsets",
    "select_window_events_upsets",
]

PRODUCER_KIND_WINDOW_EVENTS_UPSETS = "window_events_upsets"

CANDIDATE_UPSETS_BREWING_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "discover"
    / "candidates"
    / "roundup-upsets-brewing.json"
)

CANDIDATE_UPSETS_BREWING_ROWS_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "discover"
    / "candidates"
    / "roundup-upsets-brewing-rows.json"
)

_FORBIDDEN_COPY_RE = re.compile(
    r"\b(?:questions?|stale|venues?|kalshi|polymarket|opened)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class UpsetStanding:
    event_id: int
    underdog_team: str
    favorite_team: str
    underdog_score: Optional[int]
    favorite_score: Optional[int]
    period_label: Optional[str]
    pregame_prob: float
    live_prob: float
    swing_points: int
    leads_score: bool
    card: dict[str, Any]


def _assert_clean_copy(text: str) -> str:
    cleaned = " ".join(str(text or "").split())
    if _FORBIDDEN_COPY_RE.search(cleaned):
        raise ValueError(f"Forbidden copy token in reader text: {cleaned!r}")
    return cleaned


def _team_label(team_obj: Any, fallback: Any) -> str:
    if isinstance(team_obj, Mapping):
        for k in ("short_name", "display_name", "name"):
            v = team_obj.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return str(fallback or "").strip()


def _extract_upset_candidate(
    card: Mapping[str, Any],
    *,
    max_pregame_prob: float = 0.40,
    min_live_prob_if_not_leading: float = 0.50,
) -> Optional[UpsetStanding]:
    if not isinstance(card, Mapping) or not isinstance(card.get("id"), int):
        return None
    if str(card.get("status") or "").strip().lower() != "live":
        return None

    home_name = _team_label(card.get("home_team_data"), card.get("home_team"))
    away_name = _team_label(card.get("away_team_data"), card.get("away_team"))
    if not home_name or not away_name:
        return None

    live_home_raw = card.get("home_win_probability")
    pre_home_raw = card.get("pregame_home_win_probability")
    if live_home_raw is None:
        agg = card.get("aggregate_probability")
        if isinstance(agg, Mapping):
            live_home_raw = agg.get("home_win_prob")
    if pre_home_raw is None:
        pre_home_raw = card.get("opening_home_win_probability")

    if live_home_raw is None or pre_home_raw is None:
        return None
    try:
        live_home = float(live_home_raw)
        pre_home = float(pre_home_raw)
    except (TypeError, ValueError):
        return None
    if not (0.0 < live_home < 1.0 and 0.0 < pre_home < 1.0):
        return None

    home_score = card.get("home_score")
    away_score = card.get("away_score")
    hs = int(home_score) if isinstance(home_score, (int, float)) else None
    as_ = int(away_score) if isinstance(away_score, (int, float)) else None

    if pre_home <= max_pregame_prob:
        dog_team, fav_team = home_name, away_name
        dog_pre, dog_live = pre_home, live_home
        dog_score, fav_score = hs, as_
    elif (1.0 - pre_home) <= max_pregame_prob:
        dog_team, fav_team = away_name, home_name
        dog_pre, dog_live = 1.0 - pre_home, 1.0 - live_home
        dog_score, fav_score = as_, hs
    else:
        return None

    leads_score = (
        dog_score is not None and fav_score is not None and dog_score > fav_score
    )
    if not leads_score and dog_live < min_live_prob_if_not_leading:
        return None

    swing_pts = int(round((dog_live - dog_pre) * 100))
    if swing_pts <= 0:
        return None

    period_raw = str(card.get("status_detail") or card.get("period") or "").strip()
    return UpsetStanding(
        event_id=int(card["id"]),
        underdog_team=dog_team,
        favorite_team=fav_team,
        underdog_score=dog_score,
        favorite_score=fav_score,
        period_label=period_raw or None,
        pregame_prob=dog_pre,
        live_prob=dog_live,
        swing_points=swing_pts,
        leads_score=leads_score,
        card=dict(card),
    )


def select_window_events_upsets(
    events: Sequence[Mapping[str, Any]],
    *,
    max_pregame_prob: float = 0.40,
    min_live_prob: float = 0.50,
    min_members: int = 3,
    max_card_rows: int = 4,
) -> RoundupMembers | RoundupRefusal:
    candidates: list[UpsetStanding] = []
    seen_ids: set[int] = set()
    for ev in events:
        c = _extract_upset_candidate(
            ev,
            max_pregame_prob=max_pregame_prob,
            min_live_prob_if_not_leading=min_live_prob,
        )
        if c is not None and c.event_id not in seen_ids:
            seen_ids.add(c.event_id)
            candidates.append(c)

    if len(candidates) < max(2, int(min_members)):
        return RoundupRefusal([("insufficient_live_upsets", len(candidates), int(min_members))])

    candidates.sort(key=lambda c: (-c.swing_points, -c.live_prob, c.event_id))
    shown = candidates[: max(2, int(max_card_rows))]

    pre_cap_pct = int(round(max_pregame_prob * 100))
    top = shown[0]
    top_pre_pct = int(round(top.pregame_prob * 100))
    top_live_pct = int(round(top.live_prob * 100))
    card_title = _assert_clean_copy(
        f"{len(candidates)} live underdogs flipping pregame odds"
    )
    context_line = _assert_clean_copy(
        f"{len(candidates)} live games where an underdog at {pre_cap_pct}% or lower pregame "
        f"now leads or holds at least a 50% win chance — {top.underdog_team} leads the slate "
        f"at +{top.swing_points} pts from pregame ({top_pre_pct}% to {top_live_pct}%)."
    )
    footer = _assert_clean_copy(
        f"Live win chance · swings in points from pregame · {len(shown)} of {len(candidates)} live upsets"
        if len(shown) < len(candidates)
        else f"Live win chance · swings in points from pregame · all {len(candidates)} live upsets"
    )

    rows: list[dict[str, Any]] = []
    for c in shown:
        score_part = (
            f" {c.underdog_score}–{c.favorite_score}"
            if c.underdog_score is not None and c.favorite_score is not None
            else ""
        )
        pre_pct = int(round(c.pregame_prob * 100))
        live_pct = int(round(c.live_prob * 100))
        row: dict[str, Any] = {
            "event_id": c.event_id,
            "label": _assert_clean_copy(
                f"{c.underdog_team}{score_part} vs {c.favorite_team} (+{c.swing_points} pts from {pre_pct}% pregame)"
            ),
            "underdog": c.underdog_team,
            "favorite": c.favorite_team,
            "pregame_percent": pre_pct,
            "probability": round(c.live_prob, 4),
            "rendered_percent": live_pct,
            "swing_label": _assert_clean_copy(f"+{c.swing_points} pts · {pre_pct}% pregame"),
            "swing_points": c.swing_points,
            "destination": event_destination(c.event_id),
        }
        if c.period_label:
            row["period_label"] = _assert_clean_copy(c.period_label)
        rows.append(row)

    members = [
        {"id": c.event_id, "type": "event", "card": dict(c.card)}
        for c in candidates
    ]
    return RoundupMembers(
        members=members,
        rows=rows,
        footer=footer,
        count_line=f"{len(candidates)} live upsets",
        title=card_title,
        kicker="LIVE · UPSET WATCH",
        revision_ids=[c.event_id for c in candidates],
        sections=(
            {
                "title": "Live games on upset watch",
                "context_line": context_line,
                "member_ids": [c.event_id for c in candidates],
            },
        ),
    )


async def produce_window_events_upsets(
    db: Any,
    *,
    rule: Optional[Mapping[str, Any]] = None,
    now: Optional[datetime] = None,
) -> RoundupMembers | RoundupRefusal:
    effective_now = now or datetime.now(timezone.utc)
    cfg_rule = dict(rule or {})
    max_pre = float(cfg_rule.get("max_pregame_prob") or 0.40)
    min_live = float(cfg_rule.get("min_live_prob") or 0.50)
    min_m = int(cfg_rule.get("min_members") or 3)
    max_r = int(cfg_rule.get("max_card_rows") or 4)
    _ = resolve_window(cfg_rule.get("window", "sports-day"), effective_now)

    if isinstance(db, (list, tuple)):
        return select_window_events_upsets(
            db,
            max_pregame_prob=max_pre,
            min_live_prob=min_live,
            min_members=min_m,
            max_card_rows=max_r,
        )

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    if not isinstance(db, AsyncSession):
        return RoundupRefusal([("live_session_requires_feed_hydration", type(db).__name__)])

    from app.models.models import Event
    from app.routes.containers import _hydrate_event_cards

    ev_res = await db.execute(
        select(Event.id)
        .where(Event.status == "live")
        .order_by(Event.commence_time.asc(), Event.id.asc())
    )
    live_ids = [int(r[0]) for r in ev_res.all()]
    if len(live_ids) < min_m:
        return RoundupRefusal([("insufficient_live_upsets", len(live_ids), min_m)])
    cards_by_id, _ = await _hydrate_event_cards(db, live_ids)
    hydrated = [dict(cards_by_id[eid]) for eid in live_ids if eid in cards_by_id]
    return select_window_events_upsets(
        hydrated,
        max_pregame_prob=max_pre,
        min_live_prob=min_live,
        min_members=min_m,
        max_card_rows=max_r,
    )


def load_candidate_definition(path: Path = CANDIDATE_UPSETS_BREWING_PATH) -> dict[str, Any]:
    defn = json.loads(path.read_text(encoding="utf-8"))
    validate_roundup_definition(defn)
    return defn


def load_candidate_eval_rows(
    path: Path = CANDIDATE_UPSETS_BREWING_ROWS_PATH,
) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_window_events_upsets_producer(
    defn: Optional[Mapping[str, Any]] = None,
) -> RoundupProducer:
    resolved = dict(defn) if defn is not None else load_candidate_definition()
    validate_roundup_definition(resolved)
    rule = dict(resolved.get("rule") or {})

    async def _produce(db: Any) -> RoundupMembers | RoundupRefusal:
        return await produce_window_events_upsets(db, rule=rule)

    return RoundupProducer(
        slug=str(resolved["slug"]),
        name=str(resolved["name"]),
        kind=str(resolved.get("kind") or "roundup"),
        category=str(resolved["category"]),
        section_title=str(resolved["section_title"]),
        footer=str(resolved["footer"]),
        produce=_produce,
        membership=str(resolved.get("membership") or PRODUCER_KIND_WINDOW_EVENTS_UPSETS),
        relations=tuple(resolved["relations"]),
        level=str(resolved["level"]),
        rule=rule,
        tag=resolved.get("tag"),
        kicker=str(resolved.get("kicker") or "LIVE · UPSET WATCH"),
        order=str(resolved.get("order") or "sequence"),
        score=float(resolved.get("score") or 96.0),
        enabled=(lambda: bool(resolved["enabled"])) if "enabled" in resolved else None,
    )


def compose_upsets_brewing_card_and_container(
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


def build_upsets_brewing_grading_candidate(
    producer: RoundupProducer,
    members: RoundupMembers,
) -> dict[str, Any]:
    feed_item, _ = compose_upsets_brewing_card_and_container(producer, members)
    roundup = feed_item["data"]["roundup"]
    rows = list(roundup["rows"])
    best_row = min(rows, key=lambda r: abs(float(r["probability"]) - 0.5))
    return {
        "item_key": producer.slug,
        "kind": PRODUCER_KIND_WINDOW_EVENTS_UPSETS,
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
            "id": int(best_row["event_id"]),
            "name": str(best_row["label"]),
            "subject": str(best_row["underdog"]),
            "rendered_percent": int(best_row["rendered_percent"]),
        },
    }
