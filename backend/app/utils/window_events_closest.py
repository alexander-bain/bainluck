"""Reusable ``window_events_closest`` producer kind and the ``roundup-closest-games-tonight`` definition (#6 in ``docs/containers/catalog-2026-11.md``).

PILLAR: DISCOVER / TRUTH · SHIP: a reusable ``window_events_closest`` producer
kind driven by a stored container definition (``membership: "time-boxed-tonight"``,
``kind: "roundup"``), with ``roundup-closest-games-tonight`` ("The closest games
tonight") as its first definition over the sports day (6 AM–6 AM ET, Alex rulings
B, C, D on NOW #11852).
"""

from __future__ import annotations

import importlib
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from app.utils.container_presentation import MEMBER_EVENT, event_destination
from app.utils.field_band import _validate_narrative_copy
from app.utils.tonights_games import _is_eligible, _parse_dt


def _rc() -> Any:
    return importlib.import_module("app.utils.roundup_containers")

__all__ = [
    "CLOSEST_GAMES_TONIGHT_DEFINITION",
    "CLOSEST_GAMES_TONIGHT_DEFINITION_PATH",
    "CLOSEST_GAMES_TONIGHT_ID",
    "CLOSEST_GAMES_TONIGHT_PRODUCER",
    "CLOSEST_GAMES_TONIGHT_SLUG",
    "PRODUCER_KIND_WINDOW_EVENTS_CLOSEST",
    "SPORTS_DAY_CUTOFF_HOUR_ET",
    "SPORTS_DAY_TZ",
    "build_window_events_closest_producer",
    "closest_games_tonight",
    "closest_games_tonight_enabled",
    "is_event_eligible_for_window",
    "load_container_definition",
    "produce_window_events_closest",
    "resolve_window",
    "select_closest_window_events",
    "sports_day_window",
]

PRODUCER_KIND_WINDOW_EVENTS_CLOSEST = "window_events_closest"
SPORTS_DAY_TZ = ZoneInfo("America/New_York")
SPORTS_DAY_CUTOFF_HOUR_ET = 6

CLOSEST_GAMES_TONIGHT_SLUG = "roundup-closest-games-tonight"
CLOSEST_GAMES_TONIGHT_ID = "roundup:closest-games-tonight"
CLOSEST_GAMES_TONIGHT_DEFINITION_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "containers"
    / f"{CLOSEST_GAMES_TONIGHT_SLUG}.json"
)


def closest_games_tonight_enabled() -> bool:
    """One setting turns the closest-games-tonight card and container on or off together."""
    return os.getenv("CLOSEST_GAMES_TONIGHT_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def sports_day_window(now: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """Return ``(window_start_utc, window_end_utc)`` for the 6 AM–6 AM ET sports day (Alex ruling C)."""
    effective_now = (
        now
        if isinstance(now, datetime) and now.tzinfo is not None
        else (
            now.replace(tzinfo=timezone.utc)
            if isinstance(now, datetime)
            else datetime.now(timezone.utc)
        )
    )
    et_now = effective_now.astimezone(SPORTS_DAY_TZ)
    start_date = (
        (et_now - timedelta(days=1)).date()
        if et_now.hour < SPORTS_DAY_CUTOFF_HOUR_ET
        else et_now.date()
    )
    end_date = start_date + timedelta(days=1)
    start_et = datetime.combine(
        start_date, dt_time(SPORTS_DAY_CUTOFF_HOUR_ET, 0), tzinfo=SPORTS_DAY_TZ
    )
    end_et = datetime.combine(
        end_date, dt_time(SPORTS_DAY_CUTOFF_HOUR_ET, 0), tzinfo=SPORTS_DAY_TZ
    )
    return start_et.astimezone(timezone.utc), end_et.astimezone(timezone.utc)


def resolve_window(
    window_spec: Any,
    now: Optional[datetime] = None,
) -> tuple[datetime, datetime]:
    """Resolve a definition's ``rule.window`` specification into UTC ``(start, end)``."""
    if window_spec is None or window_spec == "sports-day":
        return sports_day_window(now)
    if isinstance(window_spec, Mapping):
        start = _parse_dt(window_spec.get("start"))
        end = _parse_dt(window_spec.get("end"))
        if start is not None and end is not None and end > start:
            return start.astimezone(timezone.utc), end.astimezone(timezone.utc)
        raise ValueError(f"Invalid window mapping: {window_spec!r}")
    if isinstance(window_spec, str) and "/" in window_spec:
        left, right = [part.strip() for part in window_spec.split("/", 1)]
        start = _parse_dt(left)
        end = _parse_dt(right)
        if start is not None and end is not None and end > start:
            return start.astimezone(timezone.utc), end.astimezone(timezone.utc)
        raise ValueError(f"Invalid window range string: {window_spec!r}")
    raise ValueError(f"Unsupported window specification: {window_spec!r}")


def _matches_league_filter(sport_value: Any, league_filter: Optional[str]) -> bool:
    if not league_filter:
        return True
    sport_str = str(sport_value or "").strip().lower()
    target = str(league_filter).strip().lower()
    if not sport_str:
        return False
    if sport_str == target or sport_str.endswith(f"_{target}") or sport_str.startswith(f"{target}_"):
        return True
    return False


def is_event_eligible_for_window(
    card: Mapping[str, Any],
    now: datetime,
    window_start: datetime,
    window_end: datetime,
    *,
    league: Optional[str] = None,
) -> bool:
    """Whether a serialized event card is eligible for the window under ``tonights_games._is_eligible``."""
    if not isinstance(card, Mapping):
        return False
    if not _matches_league_filter(card.get("sport"), league):
        return False

    status = str(card.get("status") or "").strip().lower()
    commence = _parse_dt(card.get("commence_time"))
    if commence is None:
        return False

    if status == "live":
        # A live game belongs to the window if it kicked off before window_end
        # and not before the sports-day's live carry-in slack (6h before window_start).
        if commence >= window_end or commence < (window_start - timedelta(hours=6)):
            return False
    else:
        if commence < window_start or commence >= window_end:
            return False

    remaining_seconds = max(0.0, (window_end - now).total_seconds())
    # Subtract a tiny epsilon so a game at window_end is excluded by `< window_end`
    # above while every game inside `[max(now, window_start), window_end)` is admitted.
    remaining_hours = max(1, int(math.ceil(remaining_seconds / 3600.0)))
    return _is_eligible(
        {"type": "event", "data": dict(card)},
        now,
        soon_window_hours=remaining_hours,
    )


def _team_short_label(team_data: Any, fallback_name: Any) -> str:
    if isinstance(team_data, Mapping):
        for key in ("short_name", "display_name", "name"):
            val = team_data.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return str(fallback_name or "").strip()


def _extract_blended_leader(
    card: Mapping[str, Any],
) -> Optional[tuple[float, str, str, Optional[str]]]:
    """Extract ``(leader_prob, leader_label, row_label, observed_at)`` from an event card's hero blend.

    Reads ONLY ``hero_probability`` and ``hero_probability_away`` — the fields
    produced by ``resolve_hero`` in ``_format_event_with_aggregated_odds`` and
    ``get_event`` (`app/routes/events.py`). Accepts ONLY
    ``hero_probability_source == "blend"`` and refuses everything else
    (``opening``, ``final_unresolved``, ``settled``, absent). Reads the row's
    ``observed_at`` from ``hero_probability_observed_at``, never from
    ``current_odds.captured_at``.
    """
    if card.get("hero_probability_source") != "blend":
        return None
    home_prob = card.get("hero_probability")
    away_prob = card.get("hero_probability_away")
    if home_prob is None or away_prob is None:
        return None
    try:
        hp = float(home_prob)
        ap = float(away_prob)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(hp) and math.isfinite(ap)):
        return None
    if not (0.0 < hp < 1.0 and 0.0 < ap < 1.0):
        return None

    home_name = card.get("home_team") or card.get("home_team_name")
    away_name = card.get("away_team") or card.get("away_team_name")
    if not (isinstance(home_name, str) and home_name.strip() and isinstance(away_name, str) and away_name.strip()):
        return None

    from app.utils.graded_card import rendered_percent

    home_label = _team_short_label(card.get("home_team_data"), home_name)
    away_label = _team_short_label(card.get("away_team_data"), away_name)
    home_pct = rendered_percent(hp)
    away_pct = rendered_percent(ap)
    tied = home_pct is not None and away_pct is not None and home_pct == away_pct
    if tied:
        leader_prob = max(hp, ap)
        leader_label = f"{away_label} and {home_label}"
        row_label = f"{away_label} at {home_label}"
    elif hp > ap:
        leader_prob = hp
        leader_label = home_label
        row_label = f"{away_label} at {home_label}: {leader_label}"
    else:
        leader_prob = ap
        leader_label = away_label
        row_label = f"{away_label} at {home_label}: {leader_label}"

    observed_at = card.get("hero_probability_observed_at")
    observed_str = str(observed_at) if isinstance(observed_at, str) and observed_at.strip() else None
    return leader_prob, leader_label, row_label, observed_str


@dataclass(frozen=True)
class _CandidateGame:
    event_id: int
    commence_iso: str
    leader_prob: float
    row_label: str
    observed_at: Optional[str]
    card: dict[str, Any]


def select_closest_window_events(
    event_cards: Sequence[Mapping[str, Any]],
    *,
    now: datetime,
    window_start: datetime,
    window_end: datetime,
    count: int = 4,
    minimum: int = 4,
    league: Optional[str] = None,
    footer_template: str = "Combined probability · the 4 closest of {n} games tonight",
) -> RoundupMembers | RoundupRefusal:
    """Pure selector for ``window_events_closest``.

    Filters ``event_cards`` to games in ``[window_start, window_end)`` passing
    ``tonights_games._is_eligible`` and carrying a two-sided blended win
    probability. Requires at least ``minimum`` eligible games (refusing with
    ``RoundupRefusal`` otherwise), selects the ``count`` games with the lowest
    blended leader probability, and orders them highest leader first.
    """
    if footer_template:
        _validate_narrative_copy(footer_template)
    required = max(1, int(minimum), int(count))
    eligible: list[_CandidateGame] = []
    seen_ids: set[int] = set()

    for raw_card in event_cards:
        if not isinstance(raw_card, Mapping):
            continue
        raw_id = raw_card.get("id")
        if not isinstance(raw_id, int) or isinstance(raw_id, bool) or raw_id <= 0:
            continue
        if raw_id in seen_ids:
            continue
        if not is_event_eligible_for_window(
            raw_card, now, window_start, window_end, league=league
        ):
            continue
        leader = _extract_blended_leader(raw_card)
        if leader is None:
            continue
        leader_prob, _leader_label, row_label, observed_at = leader
        seen_ids.add(raw_id)

        card_dict = dict(raw_card)
        if "home_team" not in card_dict and card_dict.get("home_team_name"):
            card_dict["home_team"] = card_dict["home_team_name"]
        if "away_team" not in card_dict and card_dict.get("away_team_name"):
            card_dict["away_team"] = card_dict["away_team_name"]

        commence_dt = _parse_dt(card_dict.get("commence_time"))
        commence_iso = (
            commence_dt.astimezone(timezone.utc).isoformat()
            if commence_dt is not None
            else str(card_dict.get("commence_time") or "")
        )
        eligible.append(
            _CandidateGame(
                event_id=int(raw_id),
                commence_iso=commence_iso,
                leader_prob=leader_prob,
                row_label=row_label,
                observed_at=observed_at,
                card=card_dict,
            )
        )

    total_eligible = len(eligible)
    if total_eligible < required:
        return _rc().RoundupRefusal(
            (("window", f"eligible_{total_eligible}_below_minimum_{required}"),)
        )

    closest = sorted(
        eligible,
        key=lambda g: (g.leader_prob, g.commence_iso, g.event_id),
    )[: int(count)]
    shown = sorted(
        closest,
        key=lambda g: (-g.leader_prob, g.commence_iso, g.event_id),
    )

    members = [
        {
            "type": MEMBER_EVENT,
            "id": g.event_id,
            "destination": event_destination(g.event_id),
            "card": g.card,
            "event_id": g.event_id,
        }
        for g in shown
    ]
    rows = [
        {
            "event_id": g.event_id,
            "label": g.row_label,
            "probability": g.leader_prob,
            "observed_at": g.observed_at,
        }
        for g in shown
    ]
    footer = (
        footer_template.replace("{n}", str(total_eligible))
        if footer_template
        else ""
    )
    return _rc().RoundupMembers(members=members, rows=rows, footer=footer)


CardLoader = Callable[
    [Any, datetime, datetime], Awaitable[Sequence[Mapping[str, Any]]]
]


async def produce_window_events_closest(
    definition: Mapping[str, Any],
    db: Any,
    *,
    now: Optional[datetime] = None,
    load_cards: Optional[CardLoader] = None,
) -> Any:
    """Execute a ``window_events_closest`` container definition against ``db``."""
    effective_now = (
        now
        if isinstance(now, datetime) and now.tzinfo is not None
        else (
            now.replace(tzinfo=timezone.utc)
            if isinstance(now, datetime)
            else datetime.now(timezone.utc)
        )
    )
    rule = definition.get("rule") if isinstance(definition.get("rule"), Mapping) else {}
    try:
        window_start, window_end = resolve_window(rule.get("window"), effective_now)
    except ValueError as err:
        return _rc().RoundupRefusal((("window", str(err)),))

    count = int(rule.get("count", 4))
    minimum = int(rule.get("minimum", count))
    league = rule.get("league")
    footer_template = str(definition.get("footer") or "")

    if load_cards is not None:
        ordered_cards = list(await load_cards(db, window_start, window_end))
    else:
        from sqlalchemy import and_, or_, select
        from app.models import Event
        from app.routes.containers import _hydrate_event_cards
        from app.utils.aggregation import newest_source_reading_time
        from app.utils.proven_duplicates import (
            FoldedBlendView,
            folded_card_numbers_batch,
        )

        if not hasattr(db, "execute") or not callable(db.execute):
            return _rc().RoundupRefusal((("window", "unsupported_session"),))
        res = await db.execute(
            select(Event)
            .where(
                Event.status.notin_(
                    (
                        "completed",
                        "closed",
                        "final",
                        "finished",
                        "suspended",
                        "postponed",
                        "cancelled",
                        "canceled",
                    )
                ),
                or_(
                    and_(
                        Event.commence_time >= window_start,
                        Event.commence_time < window_end,
                    ),
                    and_(
                        Event.status == "live",
                        Event.commence_time >= (window_start - timedelta(hours=6)),
                        Event.commence_time < window_end,
                    ),
                ),
            )
            .order_by(Event.commence_time, Event.id)
        )
        raw_rows = res.scalars().all() if hasattr(res, "scalars") else []
        events_by_id: dict[int, Any] = {}
        candidate_ids: list[int] = []
        for row in raw_rows:
            if isinstance(row, int) and not isinstance(row, bool) and row > 0:
                candidate_ids.append(row)
            else:
                ev_id = getattr(row, "id", None)
                if isinstance(ev_id, int) and not isinstance(ev_id, bool) and ev_id > 0:
                    candidate_ids.append(ev_id)
                    events_by_id[ev_id] = row
        if len(candidate_ids) < max(minimum, count):
            return _rc().RoundupRefusal(
                (("window", f"candidates_{len(candidate_ids)}_below_minimum_{max(minimum, count)}"),)
            )

        cards_by_id, _failed = await _hydrate_event_cards(db, candidate_ids)
        if _failed:
            return _rc().RoundupRefusal(
                (("window", f"hydrate_failed_{len(_failed)}"),)
            )
        folded_map = (
            await folded_card_numbers_batch(db, list(events_by_id.values()))
            if events_by_id
            else {}
        )
        ordered_cards = []
        for i in candidate_ids:
            if i not in cards_by_id:
                continue
            card = dict(cards_by_id[i])
            if (
                "hero_probability_observed_at" not in card
                and card.get("hero_probability_source") == "blend"
                and i in events_by_id
            ):
                ev = events_by_id[i]
                folded = folded_map.get(i)
                blend_view = (
                    FoldedBlendView(ev, folded.win_probability_sources)
                    if folded is not None and folded.win_probability_sources is not None
                    else ev
                )
                observed_at = newest_source_reading_time(
                    blend_view, require_complete=True
                )
                card["hero_probability_observed_at"] = (
                    observed_at.isoformat() if observed_at is not None else None
                )
            ordered_cards.append(card)
    return select_closest_window_events(
        ordered_cards,
        now=effective_now,
        window_start=window_start,
        window_end=window_end,
        count=count,
        minimum=minimum,
        league=league,
        footer_template=footer_template,
    )


def load_container_definition(path: Path | str) -> dict[str, Any]:
    """Load and validate a stored container definition JSON file."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Container definition at {path} must be a JSON object")
    _validate_narrative_copy(
        str(raw.get("name") or ""),
        str(raw.get("footer") or ""),
        str(raw.get("kicker") or ""),
        str(raw.get("section_title") or ""),
    )
    return raw


def build_window_events_closest_producer(
    definition: Mapping[str, Any],
    *,
    enabled: Optional[Callable[[], bool]] = None,
    now_fn: Optional[Callable[[], datetime]] = None,
    load_cards: Optional[CardLoader] = None,
) -> Any:
    """Build a ``RoundupProducer`` from a declarative ``window_events_closest`` definition."""
    rule = definition.get("rule")
    if not isinstance(rule, Mapping) or rule.get("producer") != PRODUCER_KIND_WINDOW_EVENTS_CLOSEST:
        raise ValueError(
            f"Definition {definition.get('slug')!r} requires rule.producer={PRODUCER_KIND_WINDOW_EVENTS_CLOSEST!r}"
        )
    slug = str(definition["slug"])
    name = str(definition["name"])
    kind = str(definition.get("kind") or "roundup")
    membership = str(definition.get("membership") or "time-boxed-tonight")
    category = str(definition.get("category") or "sports")
    section_title = str(definition.get("section_title") or "The 4 closest games")
    footer = str(definition.get("footer") or "")
    _validate_narrative_copy(
        name,
        footer,
        str(definition.get("kicker") or ""),
        section_title,
    )
    tag = str(definition.get("tag") or category.upper())
    story_key = f"roundup:{slug.removeprefix('roundup-')}"
    frozen_def = dict(definition)
    frozen_def["rule"] = dict(rule)

    async def _produce(db: Any) -> Any:
        current_now = now_fn() if now_fn is not None else None
        return await produce_window_events_closest(
            frozen_def, db, now=current_now, load_cards=load_cards
        )

    return _rc().RoundupProducer(
        slug=slug,
        name=name,
        kind=kind,
        category=category,
        section_title=section_title,
        footer=footer,
        produce=_produce,
        membership=membership,
        rule=frozen_def["rule"],
        tag=tag,
        story_key=story_key,
        enabled=enabled,
    )


CLOSEST_GAMES_TONIGHT_DEFINITION: dict[str, Any] = load_container_definition(
    CLOSEST_GAMES_TONIGHT_DEFINITION_PATH
)

CLOSEST_GAMES_TONIGHT_PRODUCER: Any = build_window_events_closest_producer(
    CLOSEST_GAMES_TONIGHT_DEFINITION,
    enabled=closest_games_tonight_enabled,
)
_rc().register_roundup_producer(CLOSEST_GAMES_TONIGHT_PRODUCER)


async def closest_games_tonight(
    db: Any,
    *,
    score: float = 0.0,
    now: Optional[float] = None,
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """Evaluate ``CLOSEST_GAMES_TONIGHT_PRODUCER`` and return ``(feed_item, container_payload)``."""
    feed_item, container_payload = await _rc().evaluate_roundup_producer(
        CLOSEST_GAMES_TONIGHT_PRODUCER, db, now=now
    )
    if feed_item is not None and score:
        feed_item["score"] = float(score)
    return feed_item, container_payload
