"""Reusable ``subject_sequence`` producer kind and its stored definitions (Decide 74-A, #12232).

PILLAR: DISCOVER / FORMATTING / TRUTH · SHIP: a team's next three games as a
Discover card (three-game strip, time order, within a window) that opens the
team page (``/team/<slug>``, Decide 62-A "the page wins").

Built to ``docs/design/grouping-primitives.md`` (#12221):
1. **Atoms**: scheduled upcoming games for one subject team within the window.
2. **Relations**: ``("same_subject", "same_measure", "same_window")`` at permission
   level ``"member"`` (Decide 71-A).
3. **Sets**: pure selector ``select_subject_sequence`` returning ``RoundupMembers``
   in chronological schedule order or ``RoundupRefusal`` when fewer than ``count``
   games carry fresh two-sided blended win probabilities.
4. **Presentations**: 390 px Discover three-game strip (``presentation: "strip"``,
   ``order: "sequence"``) whose card tap opens ``/team/<slug>``.
5. **Triggers / Folder Loading**: definitions in ``backend/data/containers/*.json``
   with ``rule.producer == "subject_sequence"`` are loaded automatically by kind
   (Decide 60-A).
"""

from __future__ import annotations

import importlib
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from app.utils.container_presentation import MEMBER_EVENT, event_destination
from app.utils.field_band import _validate_narrative_copy
from app.utils.tonights_games import _parse_dt

__all__ = [
    "CELTICS_NEXT_3_GAMES_DEFINITION",
    "CELTICS_NEXT_3_GAMES_DEFINITION_PATH",
    "CELTICS_NEXT_3_GAMES_ID",
    "CELTICS_NEXT_3_GAMES_PRODUCER",
    "CELTICS_NEXT_3_GAMES_SLUG",
    "PRODUCER_KIND_SUBJECT_SEQUENCE",
    "SPORTS_DAY_TZ",
    "build_subject_sequence_producer",
    "celtics_next_3_games",
    "load_subject_sequence_definition",
    "produce_subject_sequence",
    "select_subject_sequence",
    "subject_sequence_enabled",
]


def _rc() -> Any:
    return importlib.import_module("app.utils.roundup_containers")


PRODUCER_KIND_SUBJECT_SEQUENCE = "subject_sequence"
SPORTS_DAY_TZ = ZoneInfo("America/New_York")

CELTICS_NEXT_3_GAMES_SLUG = "celtics-next-3-games"
CELTICS_NEXT_3_GAMES_ID = "roundup:celtics-next-3-games"
CELTICS_NEXT_3_GAMES_DEFINITION_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "containers"
    / f"{CELTICS_NEXT_3_GAMES_SLUG}.json"
)

_EXCLUDED_STATUSES: frozenset[str] = frozenset(
    {
        "completed",
        "closed",
        "final",
        "finished",
        "settled",
        "suspended",
        "postponed",
        "cancelled",
        "canceled",
        "live",
        "in_progress",
    }
)

_MONTH_SHORT_NAMES: dict[int, str] = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}

_WEEKDAY_SHORT_NAMES: tuple[str, ...] = (
    "Mon",
    "Tue",
    "Wed",
    "Thu",
    "Fri",
    "Sat",
    "Sun",
)

_MULTI_WORD_NICKNAMES: tuple[str, ...] = (
    "Trail Blazers",
    "Blue Jackets",
    "Golden Knights",
    "Maple Leafs",
    "Red Wings",
    "Red Sox",
    "White Sox",
    "Blue Jays",
    "Tar Heels",
    "Blue Devils",
    "Fighting Irish",
    "Crimson Tide",
    "Nittany Lions",
    "Sun Devils",
    "Golden Bears",
    "Yellow Jackets",
    "Horned Frogs",
    "Red Raiders",
)


def subject_sequence_enabled() -> bool:
    """One setting turns subject_sequence cards and containers on or off together."""
    return os.getenv("SUBJECT_SEQUENCE_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def _extract_short_name(
    team_name: str,
    team_data: Optional[Mapping[str, Any]] = None,
) -> str:
    if isinstance(team_data, Mapping):
        raw_short = str(team_data.get("short_name") or "").strip()
        if raw_short:
            return raw_short
    cleaned = str(team_name or "").strip()
    if not cleaned:
        return ""
    lower_cleaned = cleaned.lower()
    for multi in _MULTI_WORD_NICKNAMES:
        if lower_cleaned.endswith(multi.lower()):
            return multi
    parts = cleaned.split()
    return parts[-1] if parts else cleaned


def _team_matches_side(
    side_name: str,
    side_data: Optional[Mapping[str, Any]],
    *,
    team_slug: str,
    team_name: str,
    team_short_name: str,
) -> bool:
    candidates: list[str] = []
    cleaned_side = side_name.strip() if side_name else ""
    if cleaned_side:
        candidates.append(cleaned_side)
    if isinstance(side_data, Mapping):
        data_name = str(side_data.get("name") or "").strip()
        if not cleaned_side or (
            data_name and data_name.lower() == cleaned_side.lower()
        ):
            for k in ("name", "short_name", "slug"):
                val = str(side_data.get(k) or "").strip()
                if val:
                    candidates.append(val)
    if not candidates:
        return False

    norm_team_name = team_name.strip().lower()
    norm_short = team_short_name.strip().lower()
    norm_slug = team_slug.strip().lower()

    for cand in candidates:
        cand_lower = cand.lower()
        cand_slug = _slugify(cand)
        if norm_team_name and cand_lower == norm_team_name:
            return True
        if norm_slug and cand_slug == norm_slug:
            return True
        if norm_short and (
            cand_lower == norm_short
            or cand_lower.endswith(f" {norm_short}")
        ):
            return True
    return False


def _matches_sport_filter(sport_value: Any, target_sport: Optional[str]) -> bool:
    if not target_sport:
        return True
    sport_str = str(sport_value or "").strip().lower()
    target = str(target_sport).strip().lower()
    if not sport_str:
        return False
    return (
        sport_str == target
        or sport_str.endswith(f"_{target}")
        or sport_str.startswith(f"{target}_")
    )


def _extract_two_sided_blend(
    card: Mapping[str, Any],
    *,
    now: datetime,
    max_prob_age_hours: float = 48.0,
) -> Optional[tuple[float, float, str]]:
    """Return ``(home_prob, away_prob, observed_iso)`` when ``card`` has a fresh two-sided blend."""
    if card.get("hero_probability_source") != "blend":
        return None

    home_p = card.get("hero_probability")
    away_p = card.get("hero_probability_away")
    if (
        not isinstance(home_p, (int, float))
        or isinstance(home_p, bool)
        or not isinstance(away_p, (int, float))
        or isinstance(away_p, bool)
    ):
        return None

    hp = float(home_p)
    ap = float(away_p)
    if (
        not math.isfinite(hp)
        or not math.isfinite(ap)
        or hp <= 0.0
        or hp >= 1.0
        or ap <= 0.0
        or ap >= 1.0
    ):
        return None
    if abs((hp + ap) - 1.0) > 0.05:
        return None

    raw_obs = card.get("hero_probability_observed_at") or card.get("observed_at")
    obs_dt = _parse_dt(raw_obs)
    if obs_dt is None:
        return None
    obs_utc = obs_dt.astimezone(timezone.utc)
    if max_prob_age_hours > 0:
        age_s = (now - obs_utc).total_seconds()
        if age_s > max_prob_age_hours * 3600.0:
            return None

    return hp, ap, obs_utc.isoformat()


def _format_et_day_label(commence_utc: datetime) -> str:
    et_dt = commence_utc.astimezone(SPORTS_DAY_TZ)
    weekday = _WEEKDAY_SHORT_NAMES[et_dt.weekday()]
    month = _MONTH_SHORT_NAMES[et_dt.month]
    return f"{weekday} {month} {et_dt.day}"


@dataclass(frozen=True)
class _SequenceGame:
    event_id: int
    commence_utc: datetime
    commence_iso: str
    team_prob: float
    rendered_percent: int
    row_label: str
    opponent_label: str
    date_label: str
    observed_at: str
    card: dict[str, Any]


@dataclass(frozen=True)
class _CandidateTeamGame:
    event_id: int
    commence_utc: datetime
    commence_iso: str
    et_date_key: str
    opp_short_key: str
    opp_label: str
    date_label: str
    row_label: str
    blend: Optional[tuple[float, float, str]]
    is_home: bool
    card: dict[str, Any]


def select_subject_sequence(
    event_cards: Sequence[Mapping[str, Any]],
    *,
    now: datetime,
    team_slug: str,
    team_name: str,
    team_short_name: str = "",
    sport: Optional[str] = None,
    count: int = 3,
    window_days: int = 21,
    max_prob_age_hours: float = 48.0,
    footer: str = "Combined win probability · next 3 games in schedule order",
) -> Any:
    """Pure selector for ``subject_sequence`` (Decide 74-A).

    Finds the subject team's next ``count`` scheduled upcoming games within
    ``window_days`` in chronological kickoff order (deduplicated by matchup date
    so an unpriced twin row never shadows a priced game), and requires every one
    of those ``count`` games to carry a fresh two-sided blended win probability.
    Refuses cleanly when fewer than ``count`` upcoming games exist or when any
    of the next ``count`` scheduled games is unpriced or stale.
    """
    if footer:
        _validate_narrative_copy(footer)

    effective_now = (
        now.astimezone(timezone.utc)
        if now.tzinfo is not None
        else now.replace(tzinfo=timezone.utc)
    )
    window_end = effective_now + timedelta(days=max(1, int(window_days)))
    required = max(1, int(count))
    effective_short = team_short_name or _extract_short_name(team_name)

    candidates_by_matchup: dict[tuple[str, str], _CandidateTeamGame] = {}
    seen_ids: set[int] = set()

    for raw_card in event_cards:
        if not isinstance(raw_card, Mapping):
            continue
        raw_id = raw_card.get("id")
        if not isinstance(raw_id, int) or isinstance(raw_id, bool) or raw_id <= 0:
            continue
        if raw_id in seen_ids:
            continue
        if sport and not _matches_sport_filter(raw_card.get("sport"), sport):
            continue

        status = str(raw_card.get("status") or "scheduled").strip().lower()
        if status in _EXCLUDED_STATUSES:
            continue
        if bool(raw_card.get("start_is_tbd")):
            continue

        commence_dt = _parse_dt(raw_card.get("commence_time"))
        if commence_dt is None:
            continue
        commence_utc = commence_dt.astimezone(timezone.utc)
        if commence_utc < effective_now or commence_utc > window_end:
            continue

        home_name = str(
            raw_card.get("home_team") or raw_card.get("home_team_name") or ""
        ).strip()
        away_name = str(
            raw_card.get("away_team") or raw_card.get("away_team_name") or ""
        ).strip()
        home_data = (
            raw_card.get("home_team_data")
            if isinstance(raw_card.get("home_team_data"), Mapping)
            else None
        )
        away_data = (
            raw_card.get("away_team_data")
            if isinstance(raw_card.get("away_team_data"), Mapping)
            else None
        )

        is_home = _team_matches_side(
            home_name,
            home_data,
            team_slug=team_slug,
            team_name=team_name,
            team_short_name=effective_short,
        )
        is_away = _team_matches_side(
            away_name,
            away_data,
            team_slug=team_slug,
            team_name=team_name,
            team_short_name=effective_short,
        )
        if is_home == is_away:
            continue

        seen_ids.add(raw_id)
        blend = _extract_two_sided_blend(
            raw_card,
            now=effective_now,
            max_prob_age_hours=max_prob_age_hours,
        )
        if is_home:
            opp_short = _extract_short_name(away_name, away_data)
            opp_label = f"vs {opp_short}"
        else:
            opp_short = _extract_short_name(home_name, home_data)
            opp_label = f"at {opp_short}"

        et_date_key = commence_utc.astimezone(SPORTS_DAY_TZ).date().isoformat()
        opp_short_key = opp_short.strip().lower()
        date_label = _format_et_day_label(commence_utc)
        row_label = f"{opp_label} \u00b7 {date_label}"

        card_dict = dict(raw_card)
        if "home_team" not in card_dict and home_name:
            card_dict["home_team"] = home_name
        if "away_team" not in card_dict and away_name:
            card_dict["away_team"] = away_name

        cand = _CandidateTeamGame(
            event_id=int(raw_id),
            commence_utc=commence_utc,
            commence_iso=commence_utc.isoformat(),
            et_date_key=et_date_key,
            opp_short_key=opp_short_key,
            opp_label=opp_label,
            date_label=date_label,
            row_label=row_label,
            blend=blend,
            is_home=is_home,
            card=card_dict,
        )
        matchup_key = (et_date_key, opp_short_key)
        existing = candidates_by_matchup.get(matchup_key)
        if existing is None:
            candidates_by_matchup[matchup_key] = cand
        else:
            # Prefer a priced row over an unpriced twin; tie-break by (commence_utc, event_id).
            existing_rank = (
                0 if existing.blend is not None else 1,
                existing.commence_utc,
                existing.event_id,
            )
            cand_rank = (
                0 if cand.blend is not None else 1,
                cand.commence_utc,
                cand.event_id,
            )
            if cand_rank < existing_rank:
                candidates_by_matchup[matchup_key] = cand

    chronological = sorted(
        candidates_by_matchup.values(),
        key=lambda g: (g.commence_utc, g.event_id),
    )
    if len(chronological) < required:
        return _rc().RoundupRefusal(
            (("sequence", f"eligible_{len(chronological)}_below_count_{required}"),)
        )

    next_games = chronological[:required]
    ordered: list[_SequenceGame] = []
    unpriced_reasons: list[tuple[str, str]] = []
    for g in next_games:
        if g.blend is None:
            unpriced_reasons.append(("sequence", f"unpriced_game_{g.event_id}"))
            continue
        home_prob, away_prob, observed_iso = g.blend
        team_prob = home_prob if g.is_home else away_prob
        rendered_pct = int(math.floor(team_prob * 100.0 + 0.5))
        ordered.append(
            _SequenceGame(
                event_id=g.event_id,
                commence_utc=g.commence_utc,
                commence_iso=g.commence_iso,
                team_prob=team_prob,
                rendered_percent=rendered_pct,
                row_label=g.row_label,
                opponent_label=g.opp_label,
                date_label=g.date_label,
                observed_at=observed_iso,
                card=g.card,
            )
        )

    if unpriced_reasons:
        return _rc().RoundupRefusal(
            (
                ("sequence", f"eligible_{len(ordered)}_below_count_{required}"),
                *unpriced_reasons,
            )
        )

    members = [
        {
            "type": MEMBER_EVENT,
            "id": g.event_id,
            "destination": event_destination(g.event_id),
            "card": g.card,
            "event_id": g.event_id,
        }
        for g in ordered
    ]
    rows = [
        {
            "event_id": g.event_id,
            "label": g.row_label,
            "opponent_label": g.opponent_label,
            "date_label": g.date_label,
            "commence_time": g.commence_iso,
            "probability": g.team_prob,
            "rendered_percent": g.rendered_percent,
            "observed_at": g.observed_at,
        }
        for g in ordered
    ]
    return _rc().RoundupMembers(
        members=members,
        rows=rows,
        footer=footer,
        destination_href=f"/team/{team_slug}",
    )


CardLoader = Callable[
    [Any, datetime, datetime, Mapping[str, Any]],
    Awaitable[Sequence[Mapping[str, Any]]],
]


async def _load_team_events_from_db(
    db: Any,
    window_start: datetime,
    window_end: datetime,
    rule: Mapping[str, Any],
) -> Any:
    """Load and hydrate upcoming scheduled events for the subject team via ``_hydrate_event_cards`` + ``folded_card_numbers_batch``."""
    from sqlalchemy import or_, select
    from app.models import Event
    from app.routes.containers import _hydrate_event_cards
    from app.utils.aggregation import newest_source_reading_time
    from app.utils.proven_duplicates import (
        FoldedBlendView,
        folded_card_numbers_batch,
    )

    if not hasattr(db, "execute") or not callable(db.execute):
        return _rc().RoundupRefusal((("sequence", "unsupported_session"),))

    team_name = str(rule.get("team_name") or "").strip()
    team_short = str(rule.get("team_short_name") or "").strip()
    sport = str(rule.get("sport") or "").strip()
    count = max(1, int(rule.get("count") or rule.get("sequence_length") or 3))

    filters = [
        Event.status.notin_(tuple(_EXCLUDED_STATUSES)),
        Event.commence_time >= window_start,
        Event.commence_time <= window_end,
    ]
    name_clauses = []
    if team_name:
        name_clauses.append(Event.home_team_name.ilike(team_name))
        name_clauses.append(Event.away_team_name.ilike(team_name))
    if team_short:
        name_clauses.append(Event.home_team_name.ilike(f"%{team_short}"))
        name_clauses.append(Event.away_team_name.ilike(f"%{team_short}"))
    if name_clauses:
        filters.append(or_(*name_clauses))

    res = await db.execute(
        select(Event)
        .where(*filters)
        .order_by(Event.commence_time.asc(), Event.id.asc())
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

    if len(candidate_ids) < count:
        return _rc().RoundupRefusal(
            (("sequence", f"candidates_{len(candidate_ids)}_below_count_{count}"),)
        )

    cards_by_id, _failed = await _hydrate_event_cards(db, candidate_ids)
    if _failed:
        return _rc().RoundupRefusal(
            (("sequence", f"hydrate_failed_{len(_failed)}"),)
        )
    folded_map = (
        await folded_card_numbers_batch(db, list(events_by_id.values()))
        if events_by_id
        else {}
    )
    ordered_cards: list[dict[str, Any]] = []
    for i in candidate_ids:
        if i not in cards_by_id:
            continue
        card = dict(cards_by_id[i])
        if sport and not _matches_sport_filter(card.get("sport"), sport):
            continue
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
    return ordered_cards


async def produce_subject_sequence(
    definition: Mapping[str, Any],
    db: Any,
    *,
    now: Optional[datetime] = None,
    load_cards: Optional[CardLoader] = None,
) -> Any:
    """Execute a ``subject_sequence`` container definition against ``db`` or a fixture sequence."""
    effective_now = (
        now.astimezone(timezone.utc)
        if isinstance(now, datetime) and now.tzinfo is not None
        else (
            now.replace(tzinfo=timezone.utc)
            if isinstance(now, datetime)
            else datetime.now(timezone.utc)
        )
    )
    rule = (
        definition.get("rule")
        if isinstance(definition.get("rule"), Mapping)
        else {}
    )
    team_slug = str(rule.get("team_slug") or "").strip()
    team_name = str(rule.get("team_name") or definition.get("name") or "").strip()
    team_short_name = str(rule.get("team_short_name") or "").strip()
    sport = str(rule.get("sport") or "").strip() or None
    count = int(rule.get("count") or rule.get("sequence_length") or 3)
    window_days = int(rule.get("window_days") or 21)
    max_prob_age_hours = float(rule.get("max_prob_age_hours") or 48.0)
    footer = str(definition.get("footer") or "")

    window_start = effective_now
    window_end = effective_now + timedelta(days=max(1, window_days))

    if isinstance(db, (list, tuple)):
        ordered_cards: Sequence[Mapping[str, Any]] = [
            c for c in db if isinstance(c, Mapping)
        ]
    elif load_cards is not None:
        ordered_cards = list(await load_cards(db, window_start, window_end, rule))
    else:
        loaded = await _load_team_events_from_db(db, window_start, window_end, rule)
        if not isinstance(loaded, list):
            return loaded
        ordered_cards = loaded

    return select_subject_sequence(
        ordered_cards,
        now=effective_now,
        team_slug=team_slug,
        team_name=team_name,
        team_short_name=team_short_name,
        sport=sport,
        count=count,
        window_days=window_days,
        max_prob_age_hours=max_prob_age_hours,
        footer=footer,
    )


def load_subject_sequence_definition(path: Path | str) -> dict[str, Any]:
    """Load and validate a stored ``subject_sequence`` definition JSON file."""
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


def build_subject_sequence_producer(
    definition: Mapping[str, Any],
    *,
    enabled: Optional[Callable[[], bool]] = None,
    now_fn: Optional[Callable[[], datetime]] = None,
    load_cards: Optional[CardLoader] = None,
) -> Any:
    """Build a ``RoundupProducer`` from a declarative ``subject_sequence`` definition."""
    rule = definition.get("rule")
    if (
        not isinstance(rule, Mapping)
        or rule.get("producer") != PRODUCER_KIND_SUBJECT_SEQUENCE
    ):
        raise ValueError(
            f"Definition {definition.get('slug')!r} requires rule.producer={PRODUCER_KIND_SUBJECT_SEQUENCE!r}"
        )
    slug = str(definition["slug"])
    name = str(definition["name"])
    kind = str(definition.get("kind") or "roundup")
    membership = str(definition.get("membership") or PRODUCER_KIND_SUBJECT_SEQUENCE)
    category = str(definition.get("category") or "nba")
    section_title = str(definition.get("section_title") or "Next 3 games")
    footer = str(definition.get("footer") or "")
    kicker = str(definition.get("kicker") or "NEXT 3 GAMES")
    _validate_narrative_copy(name, footer, kicker, section_title)
    tag = str(definition.get("tag") or category.upper())
    team_slug = str(rule.get("team_slug") or "").strip()
    destination_href = str(
        rule.get("destination_href")
        or definition.get("destination_href")
        or (f"/team/{team_slug}" if team_slug else f"/collections/{slug}")
    )
    order = str(rule.get("order") or "sequence")
    presentation = str(rule.get("presentation") or "strip")
    story_key = f"roundup:{slug.removeprefix('roundup-')}"
    frozen_def = dict(definition)
    frozen_def["rule"] = dict(rule)

    async def _produce(db: Any) -> Any:
        current_now = now_fn() if now_fn is not None else None
        return await produce_subject_sequence(
            frozen_def, db, now=current_now, load_cards=load_cards
        )

    return _rc().RoundupProducer(
        slug=slug,
        name=name,
        kind=kind,
        membership=membership,
        relations=definition.get("relations"),
        level=definition.get("level"),
        rule=frozen_def["rule"],
        category=category,
        tag=tag,
        kicker=kicker,
        section_title=section_title,
        footer=footer,
        story_key=story_key,
        destination_href=destination_href,
        order=order,
        presentation=presentation,
        produce=_produce,
        enabled=enabled if enabled is not None else subject_sequence_enabled,
    )


async def celtics_next_3_games(
    db: Any,
    *,
    now: Optional[datetime] = None,
    load_cards: Optional[CardLoader] = None,
) -> Any:
    """Convenience entry point for the ``celtics-next-3-games`` producer."""
    return await produce_subject_sequence(
        CELTICS_NEXT_3_GAMES_DEFINITION,
        db,
        now=now,
        load_cards=load_cards,
    )


CELTICS_NEXT_3_GAMES_DEFINITION: dict[str, Any] = load_subject_sequence_definition(
    CELTICS_NEXT_3_GAMES_DEFINITION_PATH
)

CELTICS_NEXT_3_GAMES_PRODUCER = build_subject_sequence_producer(
    CELTICS_NEXT_3_GAMES_DEFINITION
)

_rc().register_roundup_producer(CELTICS_NEXT_3_GAMES_PRODUCER)
