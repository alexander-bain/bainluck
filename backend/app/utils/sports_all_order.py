"""Rulings 256: B & 267: A (#13013) — Sports "All" four-block order and major/minor league list.

Applies ONLY to the Sports ``"All"`` view (``mode=sports``, ``sport=None``,
``my_teams_only=False``). Individual sport pills, search, league pages, and
My Stuff are untouched and always show every match directly.

Four-block order (256: B, no league guarantee or per-league cap):
1. **Live games** — major leagues first, then minor leagues. Within each group,
   games still in doubt (priced, favorite < 95%) rank strictly above decided
   games (>= 95%) and unpriced games, ordered purely by game interestingness.
2. **Starting within 6 hours** — major leagues first, then minor leagues.
3. **Recent finals** — major leagues first, then minor leagues.
4. **One futures & tournaments shelf** — leads ``"All"`` ONLY on a quiet day
   when there are zero live games and zero games starting within 6 hours.

Approved major vs minor league list (267: A, Alex 10:21 AM PT Thu Nov 19):
- Major leagues stay on the main ``"All"`` view (including regular ATP and WTA
  Tour main-draw stops, while ATP Challenger / ITF / qualifiers tuck away).
- Minor/niche leagues get a present-only ``data["sports_all_tucked"] = True``
  marker on ``"All"`` so website and iPhone render them behind Builder C's
  ``"and more"`` control (268: A). Any game involving a team a signed-in reader
  follows, or an event the reader pinned, stays in the main block.
"""

from __future__ import annotations

from collections.abc import Mapping, Set
from datetime import datetime, timedelta, timezone
import re

from app.utils.sports_first_page_rails import client_deletes_finished_card

#: Upcoming games starting within this window belong to Block 2 ("Starting within 6 hours").
IMMINENT_UPCOMING_WINDOW = timedelta(hours=6)
#: Small grace window for a game still marked scheduled just past nominal tip-off.
IMMINENT_PAST_GRACE = timedelta(minutes=15)
#: Live games with favorite probability at or above this threshold are "decided" (256: B).
DECIDED_FAVORITE_THRESHOLD = 0.95
#: Quiet-clock shelf lead cap (#13095): bounds the non-game lead so page 1 (20
#: cards on web, 50 on iPhone) still carries at least 12 games.
QUIET_SHELF_LEAD_CAP = 8
#: Game-night iPhone Sports page window and shelf lead size (#13887): iPhone's
#: Sports tab reads one page of 50 cards from `mode=sports` with no paging, so
#: keeping the first 8 shelf cards inside seats 43..50 preserves both the web
#: first page (20 games) / finished backfill and the iPhone Futures shelf.
GAME_NIGHT_SHELF_WINDOW = 50
GAME_NIGHT_SHELF_COUNT = QUIET_SHELF_LEAD_CAP
#: Quiet-clock recent-finals lead cap when upcoming games exist (#13095): leaves
#: at least 4 seats inside the first 20 for the next upcoming games by start time.
QUIET_RECENT_FINALS_LEAD_CAP = 8

_LIVE_STATUSES = frozenset({"live", "in_progress"})
_UPCOMING_STATUSES = frozenset({"scheduled", "upcoming", "pregame"})
_FINISHED_STATUSES = frozenset({"completed", "closed", "final"})

#: Exact sport keys that stay on the main Sports "All" view (Ruling 267: A).
SPORTS_ALL_MAJOR_LEAGUE_KEYS: frozenset[str] = frozenset(
    {
        # Football
        "americanfootball_nfl",
        "americanfootball_ncaaf",
        # Basketball
        "basketball_nba",
        "basketball_wnba",
        "basketball_ncaab",
        "basketball_wncaab",
        # Baseball
        "baseball_mlb",
        # Hockey
        "icehockey_nhl",
        # Soccer
        "soccer_epl",
        "soccer_uefa_champs_league",
        "soccer_spain_la_liga",
        "soccer_germany_bundesliga",
        "soccer_italy_serie_a",
        "soccer_france_ligue_one",
        "soccer_uefa_europa_league",
        "soccer_usa_mls",
        "soccer_fifa_world_cup",
        "soccer_conmebol_copa_libertadores",
        "soccer_uefa_nations_league",
        # Tennis — Grand Slams (bare + tour-qualified) & regular ATP/WTA Tour
        "tennis_us_open",
        "tennis_french_open",
        "tennis_wimbledon",
        "tennis_australian_open",
        "tennis_aus_open",
        "tennis_atp",
        "tennis_wta",
        # Golf — PGA Tour, LPGA Tour, and Majors
        "golf_pga",
        "golf_lpga",
        "golf_masters",
        "golf_masters_tournament_winner",
        "golf_pga_championship",
        "golf_pga_championship_winner",
        "golf_us_open",
        "golf_us_open_winner",
        "golf_open",
        "golf_the_open_championship_winner",
        # Combat
        "mma_ufc",
        "mma_mixed_martial_arts",
        # Cricket World Cups (regular T20s / Test matches tuck away)
        "cricket_t20_world_cup",
        "cricket_icc_world_cup",
        # Olympics
        "icehockey_olympics",
        "basketball_olympics",
        "soccer_olympics",
        "fieldhockey_olympics",
        "curling_olympics",
    }
)

_TENNIS_MINOR_RE = re.compile(
    r"(?:challenger|\bitf\b|qualif|futures|utr|exhibition|tennis_other)",
    re.IGNORECASE,
)


def _extract_event_team_ids(data: Mapping[str, object]) -> set[int]:
    ids: set[int] = set()
    for side in ("home_team_data", "away_team_data"):
        td = data.get(side)
        if isinstance(td, Mapping):
            tid = td.get("team_id")
            if isinstance(tid, int) and not isinstance(tid, bool):
                ids.add(tid)
    for key in ("home_team_id", "away_team_id"):
        tid = data.get(key)
        if isinstance(tid, int) and not isinstance(tid, bool):
            ids.add(tid)
    return ids


def is_sports_all_major_league(
    sport_key: str | None,
    *,
    event_data: Mapping[str, object] | None = None,
    followed_team_ids: Set[int] | None = None,
    pinned_event_ids: Set[int] | None = None,
) -> bool:
    """True when an event belongs on the main Sports "All" view (Ruling 267: A).

    Any game involving a team a signed-in reader follows, or an event they
    pinned, always stays on the main view even if its league is minor.
    """
    if event_data is not None:
        if pinned_event_ids:
            eid = event_data.get("id")
            if isinstance(eid, int) and not isinstance(eid, bool) and eid in pinned_event_ids:
                return True
        if followed_team_ids:
            if _extract_event_team_ids(event_data) & set(followed_team_ids):
                return True

    key = (sport_key or "").strip().lower()
    if not key:
        return False

    # Check tennis minor markers (Challenger, ITF, qualifiers) BEFORE accepting
    # `tennis_atp*` / `tennis_wta*` tour stops.
    if key.startswith("tennis_"):
        if _TENNIS_MINOR_RE.search(key):
            return False
        if event_data is not None:
            for field in ("league", "tournament_name", "sport_name", "name"):
                val = event_data.get(field)
                if isinstance(val, str) and _TENNIS_MINOR_RE.search(val):
                    return False
        if key in SPORTS_ALL_MAJOR_LEAGUE_KEYS:
            return True
        # Regular ATP / WTA Tour main-draw stops stay on main "All" (267: A).
        if key.startswith("tennis_atp_") or key.startswith("tennis_wta_"):
            return True
        return False

    return key in SPORTS_ALL_MAJOR_LEAGUE_KEYS


def _parse_commence_time(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _favorite_probability(data: Mapping[str, object]) -> float | None:
    """Return the leading outcome probability in [0, 1], or None if unpriced."""
    candidates: list[float] = []
    odds = data.get("current_odds")
    if isinstance(odds, Mapping):
        for field in ("home_probability", "away_probability", "draw_probability"):
            v = odds.get(field)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and 0.0 <= float(v) <= 1.0:
                candidates.append(float(v))
    if not candidates:
        for field in ("hero_probability", "hero_probability_away"):
            v = data.get(field)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and 0.0 <= float(v) <= 1.0:
                candidates.append(float(v))
        if len(candidates) == 1:
            candidates.append(1.0 - candidates[0])
    return max(candidates) if candidates else None


def _item_score(item: Mapping[str, object]) -> float:
    raw = item.get("_rank_score")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    raw = item.get("score")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    return 0.0


def _live_sort_key(entry: tuple[int, dict]) -> tuple[int, float, int]:
    """Order live games: in-doubt (< 95%) strictly above decided (>= 95%) and unpriced."""
    idx, item = entry
    data = item.get("data")
    fav = _favorite_probability(data) if isinstance(data, Mapping) else None
    if fav is None:
        # Unpriced live games sort after decided priced games.
        doubt_band = 2
    elif fav < DECIDED_FAVORITE_THRESHOLD:
        doubt_band = 0
    else:
        doubt_band = 1
    return (doubt_band, -_item_score(item), idx)


def _interest_sort_key(entry: tuple[int, dict]) -> tuple[float, int]:
    """Order games purely by interestingness descending, breaking ties stably."""
    idx, item = entry
    return (-_item_score(item), idx)


def _start_time_sort_key(entry: tuple[int, dict]) -> tuple[int, float, float, int]:
    """Order upcoming games by start time ascending, then interest descending."""
    idx, item = entry
    data = item.get("data")
    ct = _parse_commence_time(data.get("commence_time")) if isinstance(data, Mapping) else None
    if ct is None:
        return (1, float("inf"), -_item_score(item), idx)
    return (0, ct.timestamp(), -_item_score(item), idx)


def _with_tucked_marker(item: dict, *, tucked: bool) -> dict:
    """Copy item + data and stamp present-only ``sports_all_tucked: True`` when minor."""
    data = item.get("data")
    if not isinstance(data, Mapping):
        return item
    if not tucked:
        if "sports_all_tucked" not in data:
            return item
        new_data = dict(data)
        new_data.pop("sports_all_tucked", None)
        return {**item, "data": new_data}
    new_data = dict(data)
    new_data["sports_all_tucked"] = True
    return {**item, "data": new_data}


def mark_sports_all_tucked(
    items: list[dict],
    *,
    followed_team_ids: Set[int] | None = None,
    pinned_event_ids: Set[int] | None = None,
) -> list[dict]:
    """Stamp present-only ``sports_all_tucked: True`` on minor events without reordering."""
    if not items:
        return []
    out: list[dict] = []
    for item in items:
        if item.get("type") != "event":
            out.append(item)
            continue
        data = item.get("data")
        if not isinstance(data, Mapping):
            out.append(item)
            continue
        sport_key = data.get("sport") if isinstance(data.get("sport"), str) else None
        is_major = is_sports_all_major_league(
            sport_key,
            event_data=data,
            followed_team_ids=followed_team_ids,
            pinned_event_ids=pinned_event_ids,
        )
        out.append(_with_tucked_marker(item, tucked=not is_major))
    return out


def order_sports_all_feed(
    items: list[dict],
    *,
    now: datetime | None = None,
    followed_team_ids: Set[int] | None = None,
    pinned_event_ids: Set[int] | None = None,
) -> list[dict]:
    """Apply Rulings 256: B + 267: A to a Sports ``"All"`` feed item list.

    Never drops items, never mutates input dicts in place, and returns input
    unchanged if empty.
    """
    if not items:
        return []
    clock = now if now is not None else datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)

    live_major: list[tuple[int, dict]] = []
    live_minor: list[tuple[int, dict]] = []
    imminent_major: list[tuple[int, dict]] = []
    imminent_minor: list[tuple[int, dict]] = []
    recent_finals_major: list[tuple[int, dict]] = []
    recent_finals_minor: list[tuple[int, dict]] = []
    later_upcoming_major: list[tuple[int, dict]] = []
    later_upcoming_minor: list[tuple[int, dict]] = []
    older_finals: list[tuple[int, dict]] = []
    shelf_items: list[tuple[int, dict]] = []

    for idx, item in enumerate(items):
        if item.get("type") != "event":
            shelf_items.append((idx, item))
            continue

        data = item.get("data")
        if not isinstance(data, Mapping):
            shelf_items.append((idx, item))
            continue

        sport_key = data.get("sport") if isinstance(data.get("sport"), str) else None
        is_major = is_sports_all_major_league(
            sport_key,
            event_data=data,
            followed_team_ids=followed_team_ids,
            pinned_event_ids=pinned_event_ids,
        )
        tagged = _with_tucked_marker(item, tucked=not is_major)
        status = str(data.get("status") or "").strip().lower()

        if status in _LIVE_STATUSES:
            (live_major if is_major else live_minor).append((idx, tagged))
        elif status in _UPCOMING_STATUSES:
            ct = _parse_commence_time(data.get("commence_time"))
            is_imminent = (
                ct is not None
                and (clock - IMMINENT_PAST_GRACE) <= ct <= (clock + IMMINENT_UPCOMING_WINDOW)
            )
            if is_imminent:
                (imminent_major if is_major else imminent_minor).append((idx, tagged))
            else:
                (later_upcoming_major if is_major else later_upcoming_minor).append(
                    (idx, tagged)
                )
        elif status in _FINISHED_STATUSES:
            if client_deletes_finished_card(item, now=clock):
                older_finals.append((idx, tagged))
            else:
                (recent_finals_major if is_major else recent_finals_minor).append(
                    (idx, tagged)
                )
        else:
            # Suspended or unknown status sits with recent finals (major then minor).
            (recent_finals_major if is_major else recent_finals_minor).append(
                (idx, tagged)
            )

    live_major.sort(key=_live_sort_key)
    live_minor.sort(key=_live_sort_key)
    imminent_major.sort(key=_interest_sort_key)
    imminent_minor.sort(key=_interest_sort_key)
    recent_finals_major.sort(key=_interest_sort_key)
    recent_finals_minor.sort(key=_interest_sort_key)
    later_upcoming_major.sort(key=_interest_sort_key)
    later_upcoming_minor.sort(key=_interest_sort_key)

    live_block = [item for _, item in live_major] + [item for _, item in live_minor]
    imminent_block = [item for _, item in imminent_major] + [
        item for _, item in imminent_minor
    ]
    recent_finals_block = [item for _, item in recent_finals_major] + [
        item for _, item in recent_finals_minor
    ]
    later_upcoming_block = [item for _, item in later_upcoming_major] + [
        item for _, item in later_upcoming_minor
    ]
    shelf_block = [item for _, item in shelf_items]
    older_finals_block = [item for _, item in older_finals]

    quiet_day = not live_block and not imminent_block
    if quiet_day:
        quiet_upcoming_major = sorted(later_upcoming_major, key=_start_time_sort_key)
        quiet_upcoming_minor = sorted(later_upcoming_minor, key=_start_time_sort_key)
        quiet_upcoming = [item for _, item in quiet_upcoming_major] + [
            item for _, item in quiet_upcoming_minor
        ]
        shelf_lead = shelf_block[:QUIET_SHELF_LEAD_CAP]
        shelf_tail = shelf_block[QUIET_SHELF_LEAD_CAP:]
        if quiet_upcoming and len(recent_finals_block) > QUIET_RECENT_FINALS_LEAD_CAP:
            finals_lead = recent_finals_block[:QUIET_RECENT_FINALS_LEAD_CAP]
            finals_tail = recent_finals_block[QUIET_RECENT_FINALS_LEAD_CAP:]
        else:
            finals_lead = recent_finals_block
            finals_tail = []
        return (
            shelf_lead
            + finals_lead
            + quiet_upcoming
            + finals_tail
            + shelf_tail
            + older_finals_block
        )

    games_before_shelf = live_block + imminent_block + recent_finals_block
    shelf_lead = shelf_block[:GAME_NIGHT_SHELF_COUNT]
    shelf_tail = shelf_block[GAME_NIGHT_SHELF_COUNT:]
    insert_at = GAME_NIGHT_SHELF_WINDOW - len(shelf_lead)
    if shelf_lead and len(games_before_shelf) > insert_at:
        return (
            games_before_shelf[:insert_at]
            + shelf_lead
            + games_before_shelf[insert_at:]
            + shelf_tail
            + later_upcoming_block
            + older_finals_block
        )

    return (
        games_before_shelf
        + shelf_block
        + later_upcoming_block
        + older_finals_block
    )
