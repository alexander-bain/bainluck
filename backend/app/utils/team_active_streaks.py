"""Dynamic ``team_active_streaks`` ("The streak") grouped-card producer (#12288 Wave 2, Idea #16).

PILLAR: DISCOVER · MATCHING · TRUTH
SHIP: Sports "Longest active winning streaks on the line" container pairing
teams on verified 4+ game winning streaks across NBA, NHL, NFL, and MLB with
their next priced upcoming game, showing the exact chance each streak survives
its next test, deduplicating head-to-head streak matchups by ``event_id``,
refusing unpriced or untraded games ("nothing is drawn without odds"), and
explaining in ``context_line`` how the streaks were selected.

Publication gate: candidate definition lives in ``backend/data/discover/candidates/``
and is NOT registered in ``ROUNDUP_PRODUCERS`` until turned on by Fable.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from app.utils.container_presentation import MEMBER_EVENT, event_destination
from app.utils.roundup_containers import (
    RoundupMembers,
    RoundupProducer,
    RoundupRefusal,
    compose_roundup_container,
    compose_roundup_feed_item,
    validate_roundup_definition,
)

__all__ = [
    "CANDIDATE_TEAM_ACTIVE_STREAKS_PATH",
    "CANDIDATE_TEAM_ACTIVE_STREAKS_ROWS_PATH",
    "PRODUCER_KIND_TEAM_ACTIVE_STREAKS",
    "StreakEntry",
    "build_team_active_streaks_CandidatePack",
    "build_team_active_streaks_producer",
    "compose_team_streaks_card_and_container",
    "load_candidate_definition",
    "load_candidate_eval_rows",
    "produce_team_active_streaks",
    "select_team_active_streaks",
]

PRODUCER_KIND_TEAM_ACTIVE_STREAKS = "team_active_streaks"

_CANDIDATES_DIR = Path(__file__).resolve().parents[2] / "data" / "discover" / "candidates"
CANDIDATE_TEAM_ACTIVE_STREAKS_PATH = _CANDIDATES_DIR / "roundup-team-active-streaks.json"
CANDIDATE_TEAM_ACTIVE_STREAKS_ROWS_PATH = (
    _CANDIDATES_DIR / "roundup-team-active-streaks-rows.json"
)

_FORBIDDEN_COPY_RE = re.compile(
    r"\b(?:questions?|stale|venues?|kalshi|polymarket|opened)\b",
    re.IGNORECASE,
)

_LEAGUE_BADGE: dict[str, str] = {
    "basketball_nba": "NBA",
    "americanfootball_nfl": "NFL",
    "icehockey_nhl": "NHL",
    "baseball_mlb": "MLB",
}


@dataclass(frozen=True)
class StreakEntry:
    event_id: int
    sport: str
    league_label: str
    team: str
    opponent_phrase: str
    streak_kind: str
    streak_length: int
    survival_probability: float
    commence_time: str
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


def _derive_streaks_from_completed(
    completed_events: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str], tuple[str, int]]:
    history: dict[tuple[str, str], list[str]] = defaultdict(list)
    ordered = sorted(
        (e for e in completed_events if isinstance(e, Mapping)),
        key=lambda e: str(e.get("commence_time") or ""),
    )
    for ev in ordered:
        sp = str(ev.get("sport") or "").strip()
        ht = str(ev.get("home_team") or "").strip()
        at = str(ev.get("away_team") or "").strip()
        hs = ev.get("home_score")
        aws = ev.get("away_score")
        if not sp or not ht or not at or hs is None or aws is None:
            continue
        try:
            hs_f, aws_f = float(hs), float(aws)
        except (TypeError, ValueError):
            continue
        if hs_f == aws_f:
            continue
        home_won = hs_f > aws_f
        history[(sp, ht)].append("W" if home_won else "L")
        history[(sp, at)].append("L" if home_won else "W")

    streaks: dict[tuple[str, str], tuple[str, int]] = {}
    for key, seq in history.items():
        if not seq:
            continue
        last = seq[-1]
        count = 0
        for res in reversed(seq):
            if res == last:
                count += 1
            else:
                break
        streaks[key] = (last, count)
    return streaks


def _is_priced_trading_game(
    ev: Mapping[str, Any],
    *,
    now: Optional[datetime],
    max_quote_age_hours: float,
) -> Optional[tuple[float, float]]:
    status = str(ev.get("status") or "").strip().lower()
    if status not in {"scheduled", "upcoming"}:
        return None
    if ev.get("prices_withheld") or ev.get("is_trading") is False:
        return None

    odds = ev.get("current_odds") if isinstance(ev.get("current_odds"), Mapping) else {}
    hp = ev.get("hero_probability")
    if hp is None:
        hp = odds.get("home_probability")
    ap = ev.get("hero_probability_away")
    if ap is None:
        ap = odds.get("away_probability")
    if hp is None:
        return None

    try:
        hp_f = float(hp)
        ap_f = float(ap) if ap is not None else (1.0 - hp_f)
    except (TypeError, ValueError):
        return None

    if not (0.01 <= hp_f <= 0.99 and 0.01 <= ap_f <= 0.99):
        return None

    ref_now = _parse_iso_utc(now) if now is not None else None
    if ref_now is not None:
        captured = _parse_iso_utc(
            ev.get("odds_updated_at")
            or odds.get("captured_at")
            or ev.get("updated_at")
        )
        if captured is not None:
            if (ref_now - captured).total_seconds() / 3600.0 > float(max_quote_age_hours):
                return None

    return hp_f, ap_f


def select_team_active_streaks(
    payload: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    now: Optional[datetime] = None,
    streak_kind: str = "W",
    min_streak: int = 4,
    min_members: int = 3,
    max_card_rows: int = 5,
    max_quote_age_hours: float = 24.0,
) -> RoundupMembers | RoundupRefusal:
    target_kind = streak_kind.strip().upper()
    streaks_map: dict[tuple[str, str], tuple[str, int]] = {}
    upcoming_games: Sequence[Mapping[str, Any]] = ()

    if isinstance(payload, Mapping):
        completed = payload.get("completed_events") or ()
        if isinstance(completed, Sequence) and completed:
            streaks_map.update(_derive_streaks_from_completed(completed))
        for row in payload.get("team_streaks") or ():
            if not isinstance(row, Mapping):
                continue
            sp = str(row.get("sport") or "").strip()
            tm = str(row.get("team") or "").strip()
            sk = str(row.get("streak_kind") or "").strip().upper()
            slen = int(row.get("streak_length") or 0)
            if sp and tm and sk in {"W", "L"} and slen > 0:
                streaks_map[(sp, tm)] = (sk, slen)
        upcoming_games = payload.get("upcoming_events") or ()
    elif isinstance(payload, Sequence):
        # Support flat list of pre-enriched upcoming event dicts carrying home_streak / away_streak
        upcoming_games = payload

    next_game_by_team: dict[tuple[str, str], tuple[Mapping[str, Any], str, float]] = {}
    ordered_upcoming = sorted(
        (e for e in upcoming_games if isinstance(e, Mapping) and isinstance(e.get("id"), int)),
        key=lambda e: str(e.get("commence_time") or ""),
    )

    for ev in ordered_upcoming:
        probs = _is_priced_trading_game(ev, now=now, max_quote_age_hours=max_quote_age_hours)
        if probs is None:
            continue
        hp_f, ap_f = probs
        sp = str(ev.get("sport") or "").strip()
        ht = str(ev.get("home_team") or "").strip()
        at = str(ev.get("away_team") or "").strip()
        if not sp or not ht or not at:
            continue
        if _FORBIDDEN_COPY_RE.search(ht) or _FORBIDDEN_COPY_RE.search(at):
            continue

        # Allow inline streak metadata on event dicts too
        for side_team, inline_key in ((ht, "home_streak"), (at, "away_streak")):
            raw_st = ev.get(inline_key)
            if (
                isinstance(raw_st, str)
                and len(raw_st) >= 2
                and raw_st[0].upper() in {"W", "L"}
                and raw_st[1:].isdigit()
            ):
                streaks_map.setdefault((sp, side_team), (raw_st[0].upper(), int(raw_st[1:])))

        if (sp, ht) not in next_game_by_team:
            next_game_by_team[(sp, ht)] = (ev, f"vs {at}", hp_f)
        if (sp, at) not in next_game_by_team:
            next_game_by_team[(sp, at)] = (ev, f"at {ht}", ap_f)

    candidates: list[StreakEntry] = []
    for (sp, team), (sk, slen) in streaks_map.items():
        if sk != target_kind or slen < int(min_streak):
            continue
        nxt = next_game_by_team.get((sp, team))
        if nxt is None:
            continue
        ev, opp_phrase, team_win_prob = nxt
        # For a winning streak ("W"), survival = team wins next game; for losing ("L"), survival = 1 - win
        survival = team_win_prob if target_kind == "W" else (1.0 - team_win_prob)
        league_label = _LEAGUE_BADGE.get(sp, sp.upper())
        candidates.append(
            StreakEntry(
                event_id=int(ev["id"]),
                sport=sp,
                league_label=league_label,
                team=team,
                opponent_phrase=opp_phrase,
                streak_kind=sk,
                streak_length=slen,
                survival_probability=survival,
                commence_time=str(ev.get("commence_time") or ""),
                card=dict(ev),
            )
        )

    # Deduplicate by event_id (keep the longer streak if two streaking teams face each other)
    candidates.sort(
        key=lambda c: (-c.streak_length, abs(c.survival_probability - 0.5), c.commence_time, c.team)
    )
    deduped: list[StreakEntry] = []
    seen_event_ids: set[int] = set()
    for c in candidates:
        if c.event_id in seen_event_ids:
            continue
        seen_event_ids.add(c.event_id)
        deduped.append(c)

    if len(deduped) < max(2, int(min_members)):
        return RoundupRefusal(
            [("insufficient_priced_streaks", len(deduped), int(min_members))]
        )

    shown = deduped[: max(2, int(max_card_rows))]
    lead = shown[0]
    next_target = lead.streak_length + 1

    context_line = _assert_clean_copy(
        f"Teams on active {min_streak}+ game winning streaks with a priced next game, "
        f"showing each streak's chance to survive — led by {lead.team} "
        f"({lead.streak_kind}{lead.streak_length}, {int(round(lead.survival_probability * 100))}% "
        f"to reach {lead.streak_kind}{next_target} {lead.opponent_phrase})."
    )
    footer = _assert_clean_copy(
        f"Active {min_streak}+ game winning streaks · next-game win chance"
    )

    rows = [
        {
            "event_id": c.event_id,
            "sport": c.sport,
            "league": c.league_label,
            "team": _assert_clean_copy(c.team),
            "streak": f"{c.streak_kind}{c.streak_length}",
            "next_matchup": _assert_clean_copy(c.opponent_phrase),
            "label": _assert_clean_copy(
                f"{c.team} ({c.streak_kind}{c.streak_length}) · {c.opponent_phrase}"
            ),
            "probability": round(c.survival_probability, 4),
            "rendered_percent": int(round(c.survival_probability * 100)),
            "destination": event_destination(c.event_id),
        }
        for c in shown
    ]

    members = [
        {
            "id": c.event_id,
            "type": MEMBER_EVENT,
            "destination": event_destination(c.event_id),
            "card": dict(c.card),
        }
        for c in shown
    ]
    contrib_ids = [c.event_id for c in shown]

    return RoundupMembers(
        members=members,
        rows=rows,
        footer=footer,
        count_line=f"{len(deduped)} active streaks",
        title="Longest active winning streaks on the line",
        kicker="SPORTS · THE STREAK",
        revision_ids=contrib_ids,
        sections=(
            {
                "title": "Active winning streaks and each team's chance to keep it alive",
                "context_line": context_line,
                "member_ids": contrib_ids,
                "members": members,
            },
        ),
    )


async def produce_team_active_streaks(
    db: Any,
    *,
    rule: Optional[Mapping[str, Any]] = None,
    now: Optional[datetime] = None,
) -> RoundupMembers | RoundupRefusal:
    cfg = dict(rule or {})
    if isinstance(db, (Mapping, list, tuple)):
        return select_team_active_streaks(
            db,
            now=now,
            streak_kind=str(cfg.get("streak_kind") or "W"),
            min_streak=int(cfg.get("min_streak") or 4),
            min_members=int(cfg.get("min_members") or 3),
            max_card_rows=int(cfg.get("max_card_rows") or 5),
            max_quote_age_hours=float(cfg.get("max_quote_age_hours") or 24.0),
        )
    return RoundupRefusal([("unsupported_session", type(db).__name__)])


def load_candidate_definition(
    path: Path = CANDIDATE_TEAM_ACTIVE_STREAKS_PATH,
) -> dict[str, Any]:
    defn = json.loads(path.read_text(encoding="utf-8"))
    validate_roundup_definition(defn)
    return defn


def load_candidate_eval_rows(
    path: Path = CANDIDATE_TEAM_ACTIVE_STREAKS_ROWS_PATH,
) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_team_active_streaks_producer(
    defn: Optional[Mapping[str, Any]] = None,
) -> RoundupProducer:
    resolved = dict(defn) if defn is not None else load_candidate_definition()
    validate_roundup_definition(resolved)
    rule = dict(resolved.get("rule") or {})

    async def _produce(db: Any) -> RoundupMembers | RoundupRefusal:
        return await produce_team_active_streaks(db, rule=rule)

    return RoundupProducer(
        slug=str(resolved["slug"]),
        name=str(resolved["name"]),
        kind=str(resolved.get("kind") or "roundup"),
        category=str(resolved["category"]),
        section_title=str(resolved["section_title"]),
        footer=str(resolved["footer"]),
        produce=_produce,
        membership=str(resolved.get("membership") or PRODUCER_KIND_TEAM_ACTIVE_STREAKS),
        relations=tuple(resolved["relations"]),
        level=str(resolved["level"]),
        rule=rule,
        tag=resolved.get("tag"),
        kicker=str(resolved.get("kicker") or "SPORTS · THE STREAK"),
        score=float(resolved.get("score") or 92.0),
    )


def compose_team_streaks_card_and_container(
    producer: RoundupProducer,
    members: RoundupMembers,
) -> tuple[dict[str, Any], dict[str, Any]]:
    feed_item = compose_roundup_feed_item(producer, members)
    container = compose_roundup_container(producer, members)
    if feed_item is None or container is None:
        raise ValueError("Expected non-empty RoundupMembers")
    context_line = _assert_clean_copy(str(members.sections[0].get("context_line") or ""))
    feed_item["context_summary"] = context_line
    feed_item["data"]["roundup"]["context_line"] = context_line
    container["context_line"] = context_line
    return feed_item, container


def build_team_active_streaks_CandidatePack(
    producer: RoundupProducer,
    members: RoundupMembers,
) -> dict[str, Any]:
    feed_item, _ = compose_team_streaks_card_and_container(producer, members)
    roundup = feed_item["data"]["roundup"]
    rows = list(roundup["rows"])
    best_row = min(rows, key=lambda r: abs(float(r["probability"]) - 0.5))
    return {
        "item_key": producer.slug,
        "kind": PRODUCER_KIND_TEAM_ACTIVE_STREAKS,
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
            "event_id": best_row["event_id"],
            "subject": best_row["label"],
            "probability": best_row["probability"],
        },
    }
