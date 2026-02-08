"""
Super Bowl LX Contest API

Manages a prop bet contest for a Super Bowl watch party.
- Fetches entries from a published Google Sheet CSV
- Defines all 24 props with odds from sportsbook research
- Tracks resolution state in Redis
- Computes leaderboard with forecasted points
- Auto-resolves props from game state when possible
- Updates live odds from current event data
- Generates AI commentary via OpenAI
"""

import csv
import io
import json
import logging
import os
import re
import ssl
import time
from datetime import datetime, timezone
from statistics import median
from typing import Optional

import httpx
import redis
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.sb_fun_facts import SB_FUN_FACTS
from app.services.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_KEY_PREFIX = "sb_contest:"


def _redis():
    if REDIS_URL.startswith("rediss://"):
        return redis.from_url(REDIS_URL, ssl_cert_reqs=ssl.CERT_NONE)
    return redis.from_url(REDIS_URL)


def _get_resolution_state() -> dict:
    """Get all prop resolutions from Redis."""
    try:
        r = _redis()
        data = r.get(f"{REDIS_KEY_PREFIX}resolutions")
        if data:
            return json.loads(data)
    except Exception as e:
        logger.error(f"Redis read error: {e}")
    return {}


def _save_resolution_state(state: dict):
    """Save prop resolutions to Redis."""
    try:
        r = _redis()
        r.set(f"{REDIS_KEY_PREFIX}resolutions", json.dumps(state))
    except Exception as e:
        logger.error(f"Redis write error: {e}")


def _get_odds_overrides() -> dict:
    """Get admin odds overrides from Redis."""
    try:
        r = _redis()
        data = r.get(f"{REDIS_KEY_PREFIX}odds_overrides")
        if data:
            return json.loads(data)
    except Exception as e:
        logger.error(f"Redis read error: {e}")
    return {}


def _save_odds_overrides(overrides: dict):
    try:
        r = _redis()
        r.set(f"{REDIS_KEY_PREFIX}odds_overrides", json.dumps(overrides))
    except Exception as e:
        logger.error(f"Redis write error: {e}")


# ---------------------------------------------------------------------------
# Prop definitions – 24 props with sportsbook-researched odds
# ---------------------------------------------------------------------------

PROPS = [
    {
        "id": "anthem_length",
        "question": "How long will the national anthem be?",
        "column_match": "national anthem",
        "category": "pregame",
        "choices": {
            "Under 120.5 seconds": 0.49,
            "Over 120.5 seconds": 0.51,
        },
    },
    {
        "id": "coin_toss_result",
        "question": "What will be the result of the coin toss?",
        "column_match": "result of the coin toss",
        "category": "pregame",
        "choices": {
            "Heads": 0.50,
            "Tails": 0.50,
        },
    },
    {
        "id": "coin_toss_winner",
        "question": "Who will win the coin toss?",
        "column_match": "win the coin toss",
        "category": "pregame",
        "choices": {
            "Seahawks": 0.50,
            "Patriots": 0.50,
        },
    },
    {
        "id": "opening_kickoff",
        "question": "What will the result of the opening kickoff be?",
        "column_match": "opening kickoff",
        "category": "pregame",
        "choices": {
            "Touchback": 0.65,
            "Return": 0.28,
            "Out of bounds/other": 0.07,
        },
    },
    {
        "id": "first_play",
        "question": "Will a pass or run be attempted on the first offensive play?",
        "column_match": "first offensive play",
        "category": "first_quarter",
        "choices": {
            "Pass": 0.57,
            "Run": 0.43,
        },
    },
    {
        "id": "first_drive",
        "question": "What will the result of the first drive be?",
        "column_match": "first drive",
        "category": "first_quarter",
        "choices": {
            "Punt": 0.48,
            "Turnover": 0.10,
            "Field goal": 0.15,
            "Touchdown": 0.18,
            "Safety": 0.005,
            "Turnover on downs": 0.04,
            "Missed field goal": 0.03,
        },
    },
    {
        "id": "darnold_first_pass",
        "question": "What will Sam Darnold's first pass be?",
        "column_match": "Sam Darnold",
        "category": "first_quarter",
        "choices": {
            "Completion": 0.62,
            "Incompletion": 0.33,
            "Interception": 0.03,
            "Touchdown": 0.02,
        },
    },
    {
        "id": "maye_first_pass",
        "question": "What will Drake Maye's first pass be?",
        "column_match": "Drake Maye",
        "category": "first_quarter",
        "choices": {
            "Completion": 0.55,
            "Incompletion": 0.39,
            "Interception": 0.04,
            "Touchdown": 0.02,
        },
    },
    {
        "id": "first_commercial",
        "question": "What commercial will air first?",
        "column_match": "commercial",
        "category": "first_quarter",
        "choices": {
            "Budweiser": 0.55,
            "Uber Eats": 0.45,
        },
    },
    {
        "id": "first_td_jersey",
        "question": "Jersey number of first touchdown scorer",
        "column_match": "Jersey number",
        "category": "first_quarter",
        "choices": {
            "Over 19.5": 0.28,
            "Under 19.5": 0.71,
            "No touchdowns scored in the game": 0.01,
        },
    },
    {
        "id": "longest_fg",
        "question": "What distance will the longest successful field goal of the game be?",
        "column_match": "longest successful field goal",
        "category": "game",
        "choices": {
            "Over 49.5 yards": 0.45,
            "Under 49.5 yards": 0.53,
            "No field goals made in the game": 0.02,
        },
    },
    {
        "id": "two_min_warning",
        "question": "Will the 2-minute warning at the end of the first half be exactly at 2:00?",
        "column_match": "2-minute warning",
        "category": "second_quarter",
        "choices": {
            "Yes": 0.08,
            "No": 0.92,
        },
    },
    {
        "id": "first_penalty_team",
        "question": "First team to commit a penalty",
        "column_match": "First team to commit",
        "category": "game",
        "choices": {
            "Seahawks": 0.48,
            "Patriots": 0.52,
        },
    },
    {
        "id": "first_penalty_type",
        "question": "What type of penalty will the first penalty be?",
        "column_match": "type of penalty",
        "category": "game",
        "choices": {
            "Holding/Pass Interference": 0.44,
            "False Start/Encroachment/Offsides": 0.33,
            "Horse collar/Face mask": 0.03,
            "Roughing the passer/kicker/unnessecary roughness": 0.05,
        },
        "has_other": True,
        "other_probability": 0.15,
    },
    {
        "id": "bad_bunny_dtmf",
        "question": "In what part of the show Bad Bunny sing \"DtMF\"?",
        "column_match": "Bad Bunny",
        "category": "halftime",
        "choices": {
            "First song": 0.12,
            "Last song": 0.44,
            "In between the first and last song": 0.19,
            "He will not play \"DtMF\"": 0.25,
        },
    },
    {
        "id": "halftime_leader",
        "question": "Who will lead going into halftime?",
        "column_match": "lead going into halftime",
        "category": "halftime",
        "choices": {
            "Seahawks": 0.42,
            "Patriots": 0.33,
        },
        "note": "Tied at halftime = no one wins this prop (25% chance of tie)",
    },
    {
        "id": "first_challenge_who",
        "question": "Who will call the first coach's challenge?",
        "column_match": "first coach",
        "category": "game",
        "choices": {
            "Mike Macdonald": 0.30,
            "Mike Vrabel": 0.30,
            "No coach's challenge will be called in the game": 0.40,
        },
    },
    {
        "id": "first_challenge_result",
        "question": "What will be the result of the first coach's challenge?",
        "column_match": "result of the first coach",
        "category": "game",
        "choices": {
            "Call stands/confirmed": 0.25,
            "Call overturned": 0.35,
            "No coach's challenge will be called in the game": 0.40,
        },
    },
    {
        "id": "pass_attempters",
        "question": "How many players will attempt a pass?",
        "column_match": "players will attempt a pass",
        "category": "game",
        "choices": {
            "Under 2.5": 0.70,
            "Over 2.5": 0.30,
        },
    },
    {
        "id": "bitcoin",
        "question": "What will happen to the price of bitcoin during the game?",
        "column_match": "bitcoin",
        "category": "game",
        "choices": {
            "Goes up": 0.52,
            "Goes down": 0.48,
        },
    },
    {
        "id": "gatorade_color",
        "question": "What color will the Gatorade bath be?",
        "column_match": "Gatorade",
        "category": "postgame",
        "choices": {
            "Blue": 0.248,
            "Green": 0.12,
            "Yellow": 0.12,
            "Red": 0.082,
            "Orange": 0.248,
            "Purple": 0.108,
        },
        "has_other": True,
        "other_probability": 0.074,
    },
    {
        "id": "mvp_position",
        "question": "What position will win Super Bowl MVP?",
        "column_match": "MVP",
        "category": "postgame",
        "choices": {
            "QB": 0.63,
            "WR": 0.20,
            "RB": 0.07,
            "TE": 0.03,
            "Any Defense": 0.04,
        },
        "has_other": True,
        "other_probability": 0.03,
    },
    {
        "id": "game_winner",
        "question": "Who will win Super Bowl 60?",
        "column_match": "win Super Bowl",
        "category": "postgame",
        "choices": {
            "Seahawks (-4.5)": 0.675,
            "Patriots": 0.325,
        },
        "live_odds": True,
    },
    {
        "id": "total_points",
        "question": "Tiebreaker: How many points will be scored in Super Bowl 60?",
        "column_match": "Tiebreaker",
        "category": "postgame",
        "is_tiebreaker": True,
        "choices": {},
    },
]

PROP_BY_ID = {p["id"]: p for p in PROPS}

CATEGORY_ORDER = [
    "pregame", "first_quarter", "second_quarter",
    "halftime", "game", "postgame",
]

CATEGORY_LABELS = {
    "pregame": "Pre-Game",
    "first_quarter": "1st Quarter",
    "second_quarter": "2nd Quarter",
    "halftime": "Halftime",
    "game": "Full Game",
    "postgame": "Post-Game",
}

# ---------------------------------------------------------------------------
# Google Sheet helpers
# ---------------------------------------------------------------------------
SHEET_CSV_URL = os.getenv(
    "CONTEST_SHEET_URL",
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-5ILxaFfHVRe6E3W0ZcFkVxO_9XrE1Ocu_1EG6FawCAROl-JOye7pvc4-S8797vGJV-nttDnMsBP8/pub?output=csv",
)


def _detect_name_column(headers: list[str]) -> Optional[str]:
    """Detect which column contains entrant names."""
    # Priority 1: Explicit name keywords (short columns only)
    name_keywords = ["your name", "full name", "first name", "nickname", "who are you", "what is your name", "what's your name"]
    for h in headers:
        h_lower = h.lower().strip()
        for kw in name_keywords:
            if kw in h_lower and len(h.strip()) < 120:
                return h

    # Priority 2: Column header that is just "Name" or similar
    for h in headers:
        h_lower = h.lower().strip()
        if h_lower in ("name", "player", "player name", "contestant", "your name"):
            return h

    # Priority 2b: Column that contains "name" as a word
    for h in headers:
        h_lower = h.lower().strip()
        if h_lower in ("timestamp", "email address"):
            continue
        if re.search(r'\bname\b', h_lower) and len(h.strip()) < 120:
            return h

    # Priority 3: Second column (first after Timestamp) — Google Forms
    # always puts Timestamp first, then optional email, then questions.
    # If a name field was added it's usually right after Timestamp.
    non_skip = [h for h in headers if h.lower().strip() not in ("timestamp", "email address")]
    if non_skip:
        first_col = non_skip[0]
        # If the first non-Timestamp/Email column is relatively short,
        # it's likely a name or identifier field
        if len(first_col.strip()) < 80:
            # Check it's not matching one of our props (question text)
            is_prop = any(
                p["column_match"].lower() in first_col.lower()
                for p in PROPS
            )
            if not is_prop:
                return first_col

    # Priority 4: Just use second column regardless
    if len(headers) >= 2:
        second = headers[1]
        if second.lower().strip() != "timestamp":
            return second

    return None


async def _fetch_sheet_entries() -> tuple[list[dict], list[str]]:
    """Fetch and parse the Google Sheet CSV. Returns (entries, headers)."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(SHEET_CSV_URL)
            resp.raise_for_status()

        text = resp.text
        logger.info(f"CSV fetched: {len(text)} bytes")

        reader = csv.DictReader(io.StringIO(text))
        headers = list(reader.fieldnames or [])
        logger.info(f"CSV headers ({len(headers)}): {headers[:5]}...")

        rows = list(reader)
        logger.info(f"CSV rows: {len(rows)}")

        name_col = _detect_name_column(headers)
        logger.info(f"Detected name column: {name_col!r}")

        entries = []
        for i, row in enumerate(rows):
            entry = _parse_entry(row, name_col)
            if entry:
                entries.append(entry)
            else:
                # Never skip entries — assign fallback name
                fallback = _parse_entry_fallback(row, name_col, i + 1)
                if fallback:
                    entries.append(fallback)
                    logger.warning(f"Row {i} used fallback name '{fallback['name']}': first values = {list(row.values())[:3]}")
                else:
                    logger.warning(f"Row {i} skipped (empty row): first values = {list(row.values())[:3]}")

        logger.info(f"Parsed {len(entries)} entries from {len(rows)} rows, headers={headers[:5]}, name_col={name_col!r}")

        # Cache successful parse in Redis (5 min TTL)
        if entries:
            try:
                r = _redis()
                r.setex(
                    f"{REDIS_KEY_PREFIX}entries_cache",
                    300,
                    json.dumps({"entries": entries, "headers": headers}),
                )
            except Exception:
                pass

        return entries, headers

    except Exception as e:
        logger.error(f"Failed to fetch Google Sheet: {e}")
        # Fall back to cached entries on failure
        try:
            r = _redis()
            cached = r.get(f"{REDIS_KEY_PREFIX}entries_cache")
            if cached:
                data = json.loads(cached)
                logger.info(f"Using {len(data['entries'])} cached entries (sheet fetch failed)")
                return data["entries"], data.get("headers", [])
        except Exception:
            pass
        return [], []


def _parse_entry(row: dict, name_col: Optional[str]) -> Optional[dict]:
    """Parse a single CSV row into a contest entry."""
    name = None
    picks = {}
    tiebreaker = None

    # Get name from detected column
    if name_col and name_col in row:
        name = (row[name_col] or "").strip()

    # Match remaining columns to props
    for col, val in row.items():
        col_lower = col.lower().strip()
        val = (val or "").strip()

        if not val:
            continue

        # Skip name/timestamp/email columns
        if col == name_col or col_lower == "timestamp" or col_lower == "email address":
            continue

        # Match to props by column_match
        for prop in PROPS:
            if prop.get("is_tiebreaker"):
                if prop["column_match"].lower() in col_lower:
                    try:
                        tiebreaker = float(val.replace(",", ""))
                    except (ValueError, TypeError):
                        tiebreaker = None
                    break
            elif prop["column_match"].lower() in col_lower:
                picks[prop["id"]] = val
                break

    # Fallback: try second column if name still empty
    if not name:
        cols = list(row.keys())
        for c in cols:
            if c.lower().strip() not in ("timestamp", "email address"):
                candidate = (row[c] or "").strip()
                if candidate and len(candidate) < 50:
                    name = candidate
                    break

    if not name:
        return None

    return {
        "name": name,
        "picks": picks,
        "tiebreaker": tiebreaker,
        "submitted_at": row.get("Timestamp", ""),
    }


def _parse_entry_fallback(row: dict, name_col: Optional[str], row_num: int) -> Optional[dict]:
    """Parse an entry even when name detection fails. Uses email or 'Player N' fallback."""
    picks = {}
    tiebreaker = None

    # Try to find ANY identifying info for the name
    name = None

    # Try email address as name
    for col in row:
        if col.lower().strip() == "email address":
            email = (row[col] or "").strip()
            if email:
                # Use part before @ as display name
                name = email.split("@")[0].replace(".", " ").title()
                break

    # Try any short non-prop value as a name
    if not name:
        for col, val in row.items():
            col_lower = col.lower().strip()
            if col_lower in ("timestamp", "email address"):
                continue
            val = (val or "").strip()
            if not val or len(val) > 50:
                continue
            # Check if this column matches a prop
            is_prop = any(
                p["column_match"].lower() in col_lower
                for p in PROPS
            )
            if not is_prop:
                name = val
                break

    # Ultimate fallback
    if not name:
        name = f"Player {row_num}"

    # Match columns to props (same logic as _parse_entry)
    for col, val in row.items():
        col_lower = col.lower().strip()
        val = (val or "").strip()
        if not val:
            continue
        if col == name_col or col_lower == "timestamp" or col_lower == "email address":
            continue

        for prop in PROPS:
            if prop.get("is_tiebreaker"):
                if prop["column_match"].lower() in col_lower:
                    try:
                        tiebreaker = float(val.replace(",", ""))
                    except (ValueError, TypeError):
                        tiebreaker = None
                    break
            elif prop["column_match"].lower() in col_lower:
                picks[prop["id"]] = val
                break

    # Only return if they have at least some picks (not a totally empty row)
    if not picks and tiebreaker is None:
        return None

    return {
        "name": name,
        "picks": picks,
        "tiebreaker": tiebreaker,
        "submitted_at": row.get("Timestamp", ""),
    }


# ---------------------------------------------------------------------------
# Database integration – live odds & auto-resolution
# ---------------------------------------------------------------------------

async def _find_super_bowl_event(db: AsyncSession):
    """Find the Super Bowl LX event in the database."""
    from app.models.models import Event

    result = await db.execute(
        select(Event).where(
            Event.home_team_name.ilike("%seahawks%"),
            Event.away_team_name.ilike("%patriots%"),
        )
    )
    event = result.scalar_one_or_none()

    if not event:
        result = await db.execute(
            select(Event).where(
                Event.home_team_name.ilike("%patriots%"),
                Event.away_team_name.ilike("%seahawks%"),
            )
        )
        event = result.scalar_one_or_none()

    return event


async def _get_live_odds_updates(db: AsyncSession, event) -> dict:
    """Get current live odds from latest bookmaker snapshots."""
    from app.models.models import OddsSnapshot

    # Get latest snapshot per bookmaker
    subq = (
        select(
            OddsSnapshot.bookmaker,
            func.max(OddsSnapshot.captured_at).label("max_time"),
        )
        .where(OddsSnapshot.event_id == event.id)
        .group_by(OddsSnapshot.bookmaker)
        .subquery()
    )

    result = await db.execute(
        select(OddsSnapshot).join(
            subq,
            and_(
                OddsSnapshot.bookmaker == subq.c.bookmaker,
                OddsSnapshot.captured_at == subq.c.max_time,
                OddsSnapshot.event_id == event.id,
            ),
        )
    )
    snapshots = result.scalars().all()

    if not snapshots:
        return {}

    probs = [
        float(s.home_win_probability)
        for s in snapshots
        if s.home_win_probability is not None
    ]
    if not probs:
        return {}

    home_prob = median(probs)
    away_prob = 1.0 - home_prob

    is_seahawks_home = "seahawks" in event.home_team_name.lower()
    seahawks_prob = home_prob if is_seahawks_home else away_prob
    patriots_prob = 1.0 - seahawks_prob

    updates = {
        "game_winner": {
            "Seahawks (-4.5)": round(seahawks_prob, 3),
            "Patriots": round(patriots_prob, 3),
        },
    }

    return updates


async def _get_halftime_scores(db: AsyncSession, event) -> Optional[dict]:
    """Get halftime scores from ESPN snapshots or Redis cache."""
    # Check Redis cache first
    try:
        r = _redis()
        cached = r.get(f"{REDIS_KEY_PREFIX}halftime_scores")
        if cached:
            return json.loads(cached)
    except Exception:
        pass

    # Look at ESPN snapshots for period transition to find halftime score
    from app.models.models import ESPNSnapshot

    result = await db.execute(
        select(ESPNSnapshot)
        .where(ESPNSnapshot.event_id == event.id)
        .order_by(ESPNSnapshot.captured_at)
    )
    snapshots = result.scalars().all()

    if not snapshots:
        return None

    # Find the last snapshot before the 3rd quarter started
    halftime_snap = None
    for snap in snapshots:
        period = (snap.period or "").lower()
        # Capture every Q2 / 2nd quarter snapshot we see
        if any(x in period for x in ["2nd", "q2"]):
            halftime_snap = snap
        elif any(x in period for x in ["half", "3rd", "q3", "3", "4th", "q4", "ot"]):
            # Past halftime — use the last Q2 snapshot we found
            if halftime_snap:
                break

    if halftime_snap and halftime_snap.home_score is not None and halftime_snap.away_score is not None:
        scores = {
            "home": halftime_snap.home_score,
            "away": halftime_snap.away_score,
        }
        # Cache in Redis so we don't re-query
        try:
            r = _redis()
            r.set(f"{REDIS_KEY_PREFIX}halftime_scores", json.dumps(scores))
        except Exception:
            pass
        return scores

    return None


async def _auto_resolve_from_game_state(db: AsyncSession) -> list[str]:
    """Check game state and auto-resolve determinable props. Returns list of newly resolved prop IDs."""
    event = await _find_super_bowl_event(db)
    if not event:
        return []

    resolutions = _get_resolution_state()
    newly_resolved = []

    is_seahawks_home = "seahawks" in event.home_team_name.lower()

    def _seahawks_score():
        return event.home_score if is_seahawks_home else event.away_score

    def _patriots_score():
        return event.away_score if is_seahawks_home else event.home_score

    # --- game_winner: when game is completed/closed ---
    if event.status in ("completed", "closed") and "game_winner" not in resolutions:
        s_score = _seahawks_score()
        p_score = _patriots_score()
        if s_score is not None and p_score is not None:
            if s_score > p_score:
                resolutions["game_winner"] = {
                    "correct_answer": "Seahawks (-4.5)",
                    "resolved_at": datetime.now(timezone.utc).isoformat(),
                    "auto_resolved": True,
                }
                newly_resolved.append("game_winner")
            elif p_score > s_score:
                resolutions["game_winner"] = {
                    "correct_answer": "Patriots",
                    "resolved_at": datetime.now(timezone.utc).isoformat(),
                    "auto_resolved": True,
                }
                newly_resolved.append("game_winner")

    # --- halftime_leader: when past halftime ---
    if "halftime_leader" not in resolutions:
        period = (event.period or "").lower()
        past_halftime = event.status in ("completed", "closed") or any(
            x in period for x in ["3rd", "4th", "q3", "q4", "ot", "overtime", "final"]
        )

        if past_halftime:
            scores = await _get_halftime_scores(db, event)
            if scores:
                h_score = scores["home"]
                a_score = scores["away"]
                sea_ht = h_score if is_seahawks_home else a_score
                ne_ht = a_score if is_seahawks_home else h_score

                if sea_ht > ne_ht:
                    resolutions["halftime_leader"] = {
                        "correct_answer": "Seahawks",
                        "resolved_at": datetime.now(timezone.utc).isoformat(),
                        "auto_resolved": True,
                    }
                    newly_resolved.append("halftime_leader")
                elif ne_ht > sea_ht:
                    resolutions["halftime_leader"] = {
                        "correct_answer": "Patriots",
                        "resolved_at": datetime.now(timezone.utc).isoformat(),
                        "auto_resolved": True,
                    }
                    newly_resolved.append("halftime_leader")
                # Tied = no one wins (not resolved as "no winner")

    # --- ESPN play-by-play auto-resolution ---
    if event.espn_id and event.status in ("live", "completed", "closed"):
        espn_resolved = await _auto_resolve_from_espn(event, resolutions, is_seahawks_home)
        newly_resolved.extend(espn_resolved)

    # --- Bitcoin price auto-capture and resolution ---
    # Auto-capture start price when game goes live (no manual curl needed)
    if event.status in ("live", "completed", "closed"):
        await _ensure_bitcoin_start_price()
    if "bitcoin" not in resolutions and event.status in ("completed", "closed"):
        btc_answer = await _resolve_bitcoin()
        if btc_answer:
            resolutions["bitcoin"] = {
                "correct_answer": btc_answer,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "auto_resolved": True,
            }
            newly_resolved.append("bitcoin")

    # --- Claude web search for remaining props (anthem, coin toss result, etc.) ---
    if event.status in ("live", "completed", "closed"):
        try:
            ws_resolved = await _auto_resolve_via_web_search(resolutions)
            newly_resolved.extend(ws_resolved)
        except Exception as e:
            logger.error(f"Web search auto-resolve error: {e}")

    if newly_resolved:
        _save_resolution_state(resolutions)
        logger.info(f"Auto-resolved props: {newly_resolved}")

    return newly_resolved


# ---------------------------------------------------------------------------
# ESPN play-by-play auto-resolution
# ---------------------------------------------------------------------------

ESPN_API_BASE = "https://site.api.espn.com/apis/site/v2/sports"
ESPN_CACHE_TTL = 30  # Cache ESPN summary for 30 seconds


async def _fetch_espn_summary(espn_id: str) -> Optional[dict]:
    """Fetch ESPN game summary with Redis caching."""
    cache_key = f"{REDIS_KEY_PREFIX}espn_summary"

    # Check cache
    try:
        r = _redis()
        cached = r.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        pass

    # Fetch from ESPN
    try:
        url = f"{ESPN_API_BASE}/football/nfl/summary?event={espn_id}"
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(url, headers={"User-Agent": "OddsTracker/1.0"})
            if resp.status_code != 200:
                logger.warning(f"ESPN summary returned {resp.status_code}")
                return None
            data = resp.json()

        # Cache for 30 seconds
        try:
            r = _redis()
            r.setex(cache_key, ESPN_CACHE_TTL, json.dumps(data))
        except Exception:
            pass

        return data
    except Exception as e:
        logger.error(f"ESPN summary fetch error: {e}")
        return None


def _get_all_plays(data: dict) -> list[dict]:
    """Extract all plays in order from ESPN drives data."""
    plays = []
    drives = data.get("drives", {})

    for drive in drives.get("previous", []):
        for play in drive.get("plays", []):
            plays.append(play)

    # Include current drive plays
    current = drives.get("current", {})
    for play in current.get("plays", []):
        plays.append(play)

    return plays


def _team_abbr_to_name(abbr: str) -> Optional[str]:
    """Map ESPN team abbreviation to contest team name."""
    abbr_upper = abbr.upper()
    if abbr_upper in ("SEA",):
        return "Seahawks"
    elif abbr_upper in ("NE", "NWE"):
        return "Patriots"
    return None


def _play_team(play: dict) -> Optional[str]:
    """Get which team (Seahawks/Patriots) made a play."""
    start = play.get("start", {})
    team = start.get("team", {})
    abbr = team.get("abbreviation", "")
    if abbr:
        return _team_abbr_to_name(abbr)

    # Fallback: check end.team
    end = play.get("end", {})
    team = end.get("team", {})
    abbr = team.get("abbreviation", "")
    return _team_abbr_to_name(abbr) if abbr else None


async def _auto_resolve_from_espn(event, resolutions: dict, is_seahawks_home: bool) -> list[str]:
    """Parse ESPN play-by-play data to auto-resolve contest props."""
    data = await _fetch_espn_summary(event.espn_id)
    if not data:
        return []

    newly_resolved = []
    plays = _get_all_plays(data)
    if not plays:
        return []

    def _resolve(prop_id: str, answer: str):
        if prop_id not in resolutions:
            resolutions[prop_id] = {
                "correct_answer": answer,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "auto_resolved": True,
            }
            newly_resolved.append(prop_id)

    # --- coin_toss_winner: from first drive receiving team ---
    if "coin_toss_winner" not in resolutions:
        # The team that receives the opening kickoff won the toss (or deferred)
        # ESPN's first drive data shows which team had the first possession
        for play in plays:
            play_type = play.get("type", {}).get("text", "").lower()
            if "kickoff" in play_type:
                # The team kicking off LOST the toss (or chose to kick)
                # The receiving team chose to receive
                # This isn't a perfect mapping but for our prop, it's the receiving team
                kick_team = _play_team(play)
                if kick_team == "Seahawks":
                    _resolve("coin_toss_winner", "Patriots")
                elif kick_team == "Patriots":
                    _resolve("coin_toss_winner", "Seahawks")
                break

    # --- opening_kickoff: touchback/return/OOB ---
    if "opening_kickoff" not in resolutions:
        for play in plays:
            play_type = play.get("type", {}).get("text", "").lower()
            text = play.get("text", "").lower()
            if "kickoff" in play_type:
                if "touchback" in text:
                    _resolve("opening_kickoff", "Touchback")
                elif "out of bounds" in text or "out-of-bounds" in text:
                    _resolve("opening_kickoff", "Out of bounds/other")
                elif "return" in text or "returned" in text or "to the" in text:
                    _resolve("opening_kickoff", "Return")
                break

    # --- first_play: pass or run on first offensive play ---
    if "first_play" not in resolutions:
        for play in plays:
            play_type = play.get("type", {}).get("text", "").lower()
            text = play.get("text", "").lower()
            # Skip kickoffs, coin toss, etc.
            if "kickoff" in play_type or "kick" in play_type or "timeout" in play_type:
                continue
            if "pass" in play_type or "pass" in text or "sack" in play_type:
                _resolve("first_play", "Pass")
                break
            elif "rush" in play_type or "run" in text or "rush" in text:
                _resolve("first_play", "Run")
                break

    # --- first_drive: result of the first offensive drive ---
    if "first_drive" not in resolutions:
        drives = data.get("drives", {}).get("previous", [])
        for drive in drives:
            result = (drive.get("result") or "").lower()
            desc = (drive.get("description") or "").lower()

            # Skip kickoff-only "drives"
            drive_plays = drive.get("plays", [])
            if len(drive_plays) <= 1:
                play_type = drive_plays[0].get("type", {}).get("text", "").lower() if drive_plays else ""
                if "kickoff" in play_type:
                    continue

            if "touchdown" in result:
                _resolve("first_drive", "Touchdown")
            elif "punt" in result:
                _resolve("first_drive", "Punt")
            elif "field goal" in result and "missed" not in result:
                _resolve("first_drive", "Field goal")
            elif "missed" in result and "field goal" in result:
                _resolve("first_drive", "Missed field goal")
            elif "fumble" in result or "interception" in result or "turnover" in result:
                _resolve("first_drive", "Turnover")
            elif "downs" in result:
                _resolve("first_drive", "Turnover on downs")
            elif "safety" in result:
                _resolve("first_drive", "Safety")
            break

    # --- darnold_first_pass: Sam Darnold's first pass ---
    if "darnold_first_pass" not in resolutions:
        for play in plays:
            text = play.get("text", "").lower()
            play_type = play.get("type", {}).get("text", "").lower()
            if "darnold" not in text:
                continue
            if "pass" not in text and "sack" not in play_type:
                continue

            if "touchdown" in text and ("pass" in text or "complete" in text):
                _resolve("darnold_first_pass", "Touchdown")
            elif "intercept" in text:
                _resolve("darnold_first_pass", "Interception")
            elif "incomplete" in text or "incompletion" in play_type:
                _resolve("darnold_first_pass", "Incompletion")
            elif "complete" in text or "reception" in play_type:
                _resolve("darnold_first_pass", "Completion")
            elif "sack" in text or "sack" in play_type:
                _resolve("darnold_first_pass", "Incompletion")  # Sack counts as incompletion
            break

    # --- maye_first_pass: Drake Maye's first pass ---
    if "maye_first_pass" not in resolutions:
        for play in plays:
            text = play.get("text", "").lower()
            play_type = play.get("type", {}).get("text", "").lower()
            if "maye" not in text:
                continue
            if "pass" not in text and "sack" not in play_type:
                continue

            if "touchdown" in text and ("pass" in text or "complete" in text):
                _resolve("maye_first_pass", "Touchdown")
            elif "intercept" in text:
                _resolve("maye_first_pass", "Interception")
            elif "incomplete" in text or "incompletion" in play_type:
                _resolve("maye_first_pass", "Incompletion")
            elif "complete" in text or "reception" in play_type:
                _resolve("maye_first_pass", "Completion")
            elif "sack" in text or "sack" in play_type:
                _resolve("maye_first_pass", "Incompletion")
            break

    # --- first_td_jersey: Jersey number of first TD scorer ---
    if "first_td_jersey" not in resolutions:
        scoring_plays = data.get("scoringPlays", [])
        for sp in scoring_plays:
            sp_type = sp.get("type", {}).get("text", "").lower()
            if "touchdown" not in sp_type and "td" not in sp_type:
                # Also check if it's a TD via the scoring type
                if sp.get("scoringType", {}).get("name", "").lower() not in ("touchdown",):
                    continue

            # Look for the athlete who scored
            athletes = sp.get("participants", []) or []
            for athlete_entry in athletes:
                jersey = None
                athlete = athlete_entry.get("athlete", {})
                jersey = athlete.get("jersey")
                if jersey:
                    try:
                        jersey_num = int(jersey)
                        if jersey_num > 19:
                            _resolve("first_td_jersey", "Over 19.5")
                        else:
                            _resolve("first_td_jersey", "Under 19.5")
                    except ValueError:
                        pass
                    break
            if "first_td_jersey" in resolutions:
                break

        # If no TDs found and game is over, resolve as "No touchdowns"
        if "first_td_jersey" not in resolutions and event.status in ("completed", "closed"):
            if not scoring_plays or not any(
                "touchdown" in (sp.get("type", {}).get("text", "") or sp.get("scoringType", {}).get("name", "")).lower()
                for sp in scoring_plays
            ):
                _resolve("first_td_jersey", "No touchdowns scored in the game")

    # --- longest_fg: longest field goal distance ---
    if "longest_fg" not in resolutions and event.status in ("completed", "closed"):
        max_fg = 0
        any_fg = False
        for play in plays:
            text = play.get("text", "").lower()
            play_type = play.get("type", {}).get("text", "").lower()
            if "field goal" in play_type and "good" in play_type or "field goal" in text and ("good" in text or "made" in text):
                any_fg = True
                # Try to extract yardage from text like "40 Yd Field Goal"
                yd_match = re.search(r"(\d+)\s*(?:yd|yard)", text)
                if yd_match:
                    yds = int(yd_match.group(1))
                    max_fg = max(max_fg, yds)
                # Also check statYardage
                stat_yds = play.get("statYardage")
                if stat_yds:
                    try:
                        max_fg = max(max_fg, int(stat_yds))
                    except (ValueError, TypeError):
                        pass

        if any_fg and max_fg > 0:
            if max_fg > 49:
                _resolve("longest_fg", "Over 49.5 yards")
            else:
                _resolve("longest_fg", "Under 49.5 yards")
        elif not any_fg:
            _resolve("longest_fg", "No field goals made in the game")

    # --- first_penalty_team and first_penalty_type ---
    if "first_penalty_team" not in resolutions or "first_penalty_type" not in resolutions:
        for play in plays:
            play_type = play.get("type", {}).get("text", "").lower()
            text = play.get("text", "").lower()

            if "penalty" not in play_type and "penalty" not in text:
                continue

            # Which team committed the penalty
            if "first_penalty_team" not in resolutions:
                team = _play_team(play)
                if team:
                    # ESPN penalty plays: the team shown is the penalized team
                    # But penalty on offense vs defense matters. Check text.
                    # The text usually says "Penalty on SEA" or "PENALTY on NE"
                    if "seahawk" in text or ("sea" in text and "penalty" in text):
                        _resolve("first_penalty_team", "Seahawks")
                    elif "patriot" in text or ("ne " in text and "penalty" in text) or "new england" in text:
                        _resolve("first_penalty_team", "Patriots")
                    elif team:
                        _resolve("first_penalty_team", team)

            # Penalty type
            if "first_penalty_type" not in resolutions:
                text_lower = text
                if "holding" in text_lower or "pass interference" in text_lower:
                    _resolve("first_penalty_type", "Holding/Pass Interference")
                elif "false start" in text_lower or "encroachment" in text_lower or "offsides" in text_lower or "offside" in text_lower:
                    _resolve("first_penalty_type", "False Start/Encroachment/Offsides")
                elif "horse collar" in text_lower or "face mask" in text_lower or "facemask" in text_lower:
                    _resolve("first_penalty_type", "Horse collar/Face mask")
                elif "roughing" in text_lower or "unnecessary roughness" in text_lower:
                    _resolve("first_penalty_type", "Roughing the passer/kicker/unnessecary roughness")
                else:
                    # It's an "other" type - resolve as the actual penalty text
                    _resolve("first_penalty_type", "Other")

            if "first_penalty_team" in resolutions and "first_penalty_type" in resolutions:
                break

    # --- first_challenge_who / first_challenge_result ---
    if "first_challenge_who" not in resolutions or "first_challenge_result" not in resolutions:
        found_challenge = False
        for play in plays:
            text = play.get("text", "").lower()
            play_type = play.get("type", {}).get("text", "").lower()

            if "challenge" not in text and "challenge" not in play_type:
                continue

            found_challenge = True

            if "first_challenge_who" not in resolutions:
                if "macdonald" in text or "seahawk" in text:
                    _resolve("first_challenge_who", "Mike Macdonald")
                elif "vrabel" in text or "patriot" in text or "new england" in text:
                    _resolve("first_challenge_who", "Mike Vrabel")

            if "first_challenge_result" not in resolutions:
                if "overturn" in text or "reversed" in text:
                    _resolve("first_challenge_result", "Call overturned")
                elif "confirmed" in text or "stands" in text or "upheld" in text:
                    _resolve("first_challenge_result", "Call stands/confirmed")
            break

        # If game is over and no challenge was found
        if not found_challenge and event.status in ("completed", "closed"):
            _resolve("first_challenge_who", "No coach's challenge will be called in the game")
            _resolve("first_challenge_result", "No coach's challenge will be called in the game")

    # --- pass_attempters: count unique passers from box score ---
    if "pass_attempters" not in resolutions and event.status in ("completed", "closed"):
        boxscore = data.get("boxscore", {})
        unique_passers = set()

        for team_players in boxscore.get("players", []):
            for stat_group in team_players.get("statistics", []):
                if stat_group.get("name", "").lower() == "passing":
                    for athlete_entry in stat_group.get("athletes", []):
                        name = athlete_entry.get("athlete", {}).get("displayName", "")
                        stats = athlete_entry.get("stats", [])
                        # First stat is usually C/ATT (completions/attempts)
                        if stats and name:
                            # Check if they actually attempted a pass (not just 0/0)
                            c_att = stats[0] if stats else ""
                            if "/" in str(c_att):
                                att = c_att.split("/")[1]
                                if int(att) > 0:
                                    unique_passers.add(name)

        if unique_passers:
            if len(unique_passers) > 2:
                _resolve("pass_attempters", "Over 2.5")
            else:
                _resolve("pass_attempters", "Under 2.5")

    # --- mvp_position: from ESPN game data (usually in header or article) ---
    if "mvp_position" not in resolutions and event.status in ("completed", "closed"):
        # ESPN sometimes includes MVP in the header or news section
        news = data.get("news", {})
        articles = news.get("articles", []) if isinstance(news, dict) else []
        header = data.get("header", {})

        # Check game notes or article headlines for MVP mention
        for article in articles:
            headline = (article.get("headline") or "").lower()
            desc = (article.get("description") or "").lower()
            text = headline + " " + desc

            if "mvp" in text:
                # Try to determine position from the MVP name
                # This is best-effort — if we can't determine position, skip
                boxscore = data.get("boxscore", {})
                for team_players in boxscore.get("players", []):
                    for stat_group in team_players.get("statistics", []):
                        for athlete_entry in stat_group.get("athletes", []):
                            player_name = athlete_entry.get("athlete", {}).get("displayName", "").lower()
                            position = athlete_entry.get("athlete", {}).get("position", {}).get("abbreviation", "")
                            if player_name and player_name in text:
                                pos_upper = position.upper()
                                if pos_upper == "QB":
                                    _resolve("mvp_position", "QB")
                                elif pos_upper == "WR":
                                    _resolve("mvp_position", "WR")
                                elif pos_upper == "RB":
                                    _resolve("mvp_position", "RB")
                                elif pos_upper == "TE":
                                    _resolve("mvp_position", "TE")
                                elif pos_upper in ("CB", "LB", "DE", "DT", "S", "SS", "FS", "OLB", "ILB", "MLB", "DB", "DL"):
                                    _resolve("mvp_position", "Any Defense")
                                else:
                                    _resolve("mvp_position", "Other")
                                break
                    if "mvp_position" in resolutions:
                        break
            if "mvp_position" in resolutions:
                break

    return newly_resolved


# ---------------------------------------------------------------------------
# Bitcoin price auto-resolution
# ---------------------------------------------------------------------------

async def _ensure_bitcoin_start_price():
    """Auto-capture bitcoin price at kickoff if not already captured."""
    try:
        r = _redis()
        existing = r.get(f"{REDIS_KEY_PREFIX}btc_start_price")
        if existing:
            return  # Already captured

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
            )
            if resp.status_code != 200:
                return
            price = resp.json().get("bitcoin", {}).get("usd")

        if price:
            r.set(f"{REDIS_KEY_PREFIX}btc_start_price", str(price))
            logger.info(f"Auto-captured Bitcoin start price: ${price}")
    except Exception as e:
        logger.error(f"Bitcoin start price capture error: {e}")


async def _resolve_bitcoin() -> Optional[str]:
    """Check bitcoin price change during the game. Returns 'Goes up' or 'Goes down'."""
    try:
        r = _redis()
        # We need start and end prices stored in Redis
        start_price = r.get(f"{REDIS_KEY_PREFIX}btc_start_price")
        if not start_price:
            return None

        start_price = float(start_price)

        # Fetch current price from CoinGecko
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            current_price = data.get("bitcoin", {}).get("usd")

        if current_price is None:
            return None

        if current_price > start_price:
            return "Goes up"
        else:
            return "Goes down"
    except Exception as e:
        logger.error(f"Bitcoin price check error: {e}")
        return None


# ---------------------------------------------------------------------------
# Claude web search auto-resolution (for props without data feeds)
# ---------------------------------------------------------------------------

WEB_SEARCH_CACHE_TTL = 300  # 5 minutes between web search checks

WEB_SEARCH_PROPS = {
    "anthem_length": {
        "instruction": (
            "Super Bowl LX (60) 2026, Seahawks vs Patriots: "
            "How long was the national anthem? Report the exact duration. "
            "Was it UNDER or OVER 120.5 seconds (2 minutes 0.5 seconds)? "
            "Respond with EXACTLY one of: Under 120.5 seconds | Over 120.5 seconds"
        ),
    },
    "coin_toss_result": {
        "instruction": (
            "Super Bowl LX (60) 2026, Seahawks vs Patriots: "
            "What was the coin toss result — heads or tails? "
            "Respond with EXACTLY one of: Heads | Tails"
        ),
    },
    "first_commercial": {
        "instruction": (
            "Super Bowl LX (60) 2026: Which brand aired a commercial first during the "
            "broadcast — Budweiser or Uber Eats? Search for Super Bowl LX ad order/tracker. "
            "Respond with EXACTLY one of: Budweiser | Uber Eats"
        ),
    },
    "bad_bunny_dtmf": {
        "instruction": (
            "Super Bowl LX (60) 2026 halftime show: Did Bad Bunny perform the song 'DtMF'? "
            "If so, was it the first song, the last song, or somewhere in between? "
            "Search for the Super Bowl LX halftime show setlist. "
            "Respond with EXACTLY one of: First song | Last song | In between the first and last song | He will not play \"DtMF\""
        ),
    },
    "gatorade_color": {
        "instruction": (
            "Super Bowl LX (60) 2026: What color was the Gatorade (or liquid) dumped on "
            "the winning head coach at the end of the game? "
            "Respond with EXACTLY one of: Blue | Green | Yellow | Red | Orange | Purple | Other"
        ),
    },
}


def _get_anthropic_client():
    """Get async Anthropic client if API key is available."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
        return anthropic.AsyncAnthropic(api_key=api_key)
    except ImportError:
        logger.warning("anthropic package not installed")
        return None


async def _auto_resolve_via_web_search(resolutions: dict) -> list[str]:
    """Use Claude with web search to resolve props that have no data feed."""
    # Check which web-search props still need resolution
    unresolved = [pid for pid in WEB_SEARCH_PROPS if pid not in resolutions]
    if not unresolved:
        return []

    # Rate limit: only run web search every 5 minutes
    try:
        r = _redis()
        last_check = r.get(f"{REDIS_KEY_PREFIX}web_search_last_check")
        if last_check:
            elapsed = time.time() - float(last_check)
            if elapsed < WEB_SEARCH_CACHE_TTL:
                return []
        r.set(f"{REDIS_KEY_PREFIX}web_search_last_check", str(time.time()))
    except Exception:
        pass

    client = _get_anthropic_client()
    if not client:
        return []

    newly_resolved = []

    for prop_id in unresolved:
        ws_prop = WEB_SEARCH_PROPS[prop_id]
        prop_def = PROP_BY_ID.get(prop_id)
        if not prop_def:
            continue

        # Check if we have a cached result
        cache_key = f"{REDIS_KEY_PREFIX}ws_{prop_id}"
        try:
            r = _redis()
            cached = r.get(cache_key)
            if cached:
                cached_data = json.loads(cached)
                if cached_data.get("answer") == "__NOT_AVAILABLE__":
                    continue
                # Use cached answer
                answer = cached_data["answer"]
                if answer and prop_id not in resolutions:
                    resolutions[prop_id] = {
                        "correct_answer": answer,
                        "resolved_at": datetime.now(timezone.utc).isoformat(),
                        "auto_resolved": True,
                        "source": "web_search",
                    }
                    newly_resolved.append(prop_id)
                continue
        except Exception:
            pass

        # Call Claude with web search
        try:
            choices_list = list(prop_def.get("choices", {}).keys())
            if prop_def.get("has_other"):
                choices_list.append("Other")

            system_prompt = (
                "You are resolving a Super Bowl prop bet. Use web search to find the definitive answer. "
                "You MUST respond with ONLY the exact answer text matching one of the provided choices. "
                "If the event hasn't happened yet or no definitive result is available, respond with: NOT_AVAILABLE"
            )

            user_msg = (
                f"{ws_prop['instruction']}\n\n"
                f"Valid choices are: {' | '.join(choices_list)}\n\n"
                f"Respond with ONLY the exact choice text, nothing else. "
                f"If no result is available yet, respond with: NOT_AVAILABLE"
            )

            response = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=256,
                system=system_prompt,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
                messages=[{"role": "user", "content": user_msg}],
            )

            # Extract text from response
            answer_text = ""
            for block in response.content:
                if block.type == "text":
                    answer_text += block.text

            answer_text = answer_text.strip().strip('"').strip("'")

            if "NOT_AVAILABLE" in answer_text.upper() or not answer_text:
                # Cache the "not available" result for 5 minutes
                try:
                    r = _redis()
                    r.setex(cache_key, WEB_SEARCH_CACHE_TTL, json.dumps({"answer": "__NOT_AVAILABLE__"}))
                except Exception:
                    pass
                logger.info(f"Web search: {prop_id} = NOT_AVAILABLE")
                continue

            # Try to match to a valid choice
            matched = _match_web_search_answer(answer_text, choices_list, prop_def)
            if matched:
                resolutions[prop_id] = {
                    "correct_answer": matched,
                    "resolved_at": datetime.now(timezone.utc).isoformat(),
                    "auto_resolved": True,
                    "source": "web_search",
                }
                newly_resolved.append(prop_id)
                logger.info(f"Web search resolved: {prop_id} = {matched}")

                # Cache the result
                try:
                    r = _redis()
                    r.setex(cache_key, WEB_SEARCH_CACHE_TTL, json.dumps({"answer": matched}))
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Web search error for {prop_id}: {e}")

    return newly_resolved


def _match_web_search_answer(answer: str, choices: list[str], prop_def: dict) -> Optional[str]:
    """Match a web search answer to one of the valid prop choices."""
    answer_lower = answer.lower().strip()

    # Exact match
    for choice in choices:
        if answer_lower == choice.lower().strip():
            return choice

    # Fuzzy match: check if the answer contains a choice keyword
    for choice in choices:
        choice_lower = choice.lower()
        # For short choices like "Heads", "Tails", check containment
        if len(choice) <= 20 and choice_lower in answer_lower:
            return choice

    # Special handling per prop
    prop_id = prop_def.get("id", "")

    if prop_id == "anthem_length":
        if "under" in answer_lower:
            return "Under 120.5 seconds"
        elif "over" in answer_lower:
            return "Over 120.5 seconds"
        # Try to parse a duration
        duration_match = re.search(r"(\d+)\s*(?:minutes?|min)\s*(?:and\s*)?(\d+)\s*(?:seconds?|sec)", answer_lower)
        if duration_match:
            mins = int(duration_match.group(1))
            secs = int(duration_match.group(2))
            total_secs = mins * 60 + secs
            return "Under 120.5 seconds" if total_secs < 120.5 else "Over 120.5 seconds"
        secs_match = re.search(r"(\d+\.?\d*)\s*seconds", answer_lower)
        if secs_match:
            total_secs = float(secs_match.group(1))
            return "Under 120.5 seconds" if total_secs < 120.5 else "Over 120.5 seconds"

    elif prop_id == "coin_toss_result":
        if "heads" in answer_lower:
            return "Heads"
        elif "tails" in answer_lower:
            return "Tails"

    elif prop_id == "first_commercial":
        if "budweiser" in answer_lower or "bud" in answer_lower:
            return "Budweiser"
        elif "uber" in answer_lower:
            return "Uber Eats"

    elif prop_id == "bad_bunny_dtmf":
        if "first song" in answer_lower or "opened with" in answer_lower or "opener" in answer_lower:
            return "First song"
        elif "last song" in answer_lower or "closed with" in answer_lower or "closer" in answer_lower or "finale" in answer_lower:
            return "Last song"
        elif "did not" in answer_lower or "will not" in answer_lower or "didn't" in answer_lower or "not play" in answer_lower:
            return 'He will not play "DtMF"'
        elif "between" in answer_lower or "middle" in answer_lower:
            return "In between the first and last song"

    elif prop_id == "gatorade_color":
        colors = {"blue": "Blue", "green": "Green", "yellow": "Yellow",
                  "red": "Red", "orange": "Orange", "purple": "Purple"}
        for color_key, color_val in colors.items():
            if color_key in answer_lower:
                return color_val
        # If a color was mentioned but not in our list
        if any(c in answer_lower for c in ["clear", "water", "white", "pink"]):
            return "Other"

    return None


# ---------------------------------------------------------------------------
# Scoring logic
# ---------------------------------------------------------------------------

def _normalize_answer(answer: str) -> str:
    """Normalize an answer for comparison."""
    return answer.strip().lower().rstrip(".")


def _pick_matches(pick: str, correct: str, prop: dict) -> bool:
    """Check if a pick matches the correct answer."""
    pick_norm = _normalize_answer(pick)
    correct_norm = _normalize_answer(correct)

    if pick_norm == correct_norm:
        return True

    # Handle "Other" answers
    if prop.get("has_other"):
        predefined = [_normalize_answer(c) for c in prop["choices"]]
        pick_is_other = pick_norm not in predefined
        correct_is_other = correct_norm == "other" or correct_norm not in predefined
        if pick_is_other and correct_is_other:
            return True

    return False


def _get_pick_probability(prop_id: str, pick: str, overrides: dict) -> float:
    """Get the probability for a specific pick on a prop."""
    prop = PROP_BY_ID.get(prop_id)
    if not prop or prop.get("is_tiebreaker"):
        return 0.0

    # Check for admin odds override
    if prop_id in overrides:
        override_choices = overrides[prop_id]
        for choice, prob in override_choices.items():
            if _normalize_answer(pick) == _normalize_answer(choice):
                return prob

    # Check predefined choices
    for choice, prob in prop["choices"].items():
        if _normalize_answer(pick) == _normalize_answer(choice):
            return prob

    # If the pick doesn't match any choice, it's an "Other" pick
    if prop.get("has_other"):
        return prop.get("other_probability", 0.05)

    return 0.0


def _compute_leaderboard(entries: list[dict], resolutions: dict, overrides: dict) -> dict:
    """Compute the full leaderboard with scores and forecasts."""
    scorable_props = [p for p in PROPS if not p.get("is_tiebreaker")]
    total_props = len(scorable_props)
    resolved_ids = set(resolutions.keys())
    resolved_count = len(resolved_ids)
    open_ids = [p["id"] for p in scorable_props if p["id"] not in resolved_ids]

    # Build prop status list
    props_status = []
    for prop in PROPS:
        if prop.get("is_tiebreaker"):
            continue

        resolution = resolutions.get(prop["id"])
        current_odds = {}

        for choice, prob in prop["choices"].items():
            current_odds[choice] = prob
        # Apply overrides (live odds updates)
        if prop["id"] in overrides:
            current_odds.update(overrides[prop["id"]])

        # If resolved, slam odds to 1.0 / 0.0
        if resolution:
            for choice in current_odds:
                if _normalize_answer(choice) == _normalize_answer(resolution["correct_answer"]):
                    current_odds[choice] = 1.0
                else:
                    current_odds[choice] = 0.0

        props_status.append({
            "id": prop["id"],
            "question": prop["question"],
            "category": prop["category"],
            "choices": current_odds,
            "resolved": resolution is not None,
            "correct_answer": resolution["correct_answer"] if resolution else None,
            "resolved_at": resolution.get("resolved_at") if resolution else None,
            "has_other": prop.get("has_other", False),
            "other_probability": prop.get("other_probability", 0.0),
            "auto_resolved": resolution.get("auto_resolved", False) if resolution else False,
        })

    # Score each entrant
    leaderboard = []
    for entry in entries:
        actual_points = 0
        forecasted_points = 0.0
        correct_picks = []
        incorrect_picks = []
        pending_picks = []

        for prop in scorable_props:
            pick = entry["picks"].get(prop["id"])
            if not pick:
                continue

            if prop["id"] in resolved_ids:
                correct_answer = resolutions[prop["id"]]["correct_answer"]
                if _pick_matches(pick, correct_answer, prop):
                    actual_points += 1
                    forecasted_points += 1.0
                    correct_picks.append({
                        "prop_id": prop["id"],
                        "question": prop["question"],
                        "pick": pick,
                    })
                else:
                    incorrect_picks.append({
                        "prop_id": prop["id"],
                        "question": prop["question"],
                        "pick": pick,
                        "correct_answer": correct_answer,
                    })
            else:
                prob = _get_pick_probability(prop["id"], pick, overrides)
                forecasted_points += prob
                pending_picks.append({
                    "prop_id": prop["id"],
                    "question": prop["question"],
                    "pick": pick,
                    "probability": round(prob, 3),
                })

        max_possible = actual_points + len(pending_picks)

        leaderboard.append({
            "name": entry["name"],
            "actual_points": actual_points,
            "forecasted_points": round(forecasted_points, 2),
            "max_possible": max_possible,
            "correct_picks": correct_picks,
            "incorrect_picks": incorrect_picks,
            "pending_picks": pending_picks,
            "tiebreaker": entry.get("tiebreaker"),
            "submitted_at": entry.get("submitted_at", ""),
            "total_picks": len(correct_picks) + len(incorrect_picks) + len(pending_picks),
        })

    # Sort by forecasted points desc, then actual desc, then tiebreaker proximity to 45.5
    leaderboard.sort(key=lambda x: (
        -x["forecasted_points"],
        -x["actual_points"],
        abs((x["tiebreaker"] or 45.5) - 45.5),
    ))

    # Assign ranks
    for i, entry in enumerate(leaderboard):
        entry["rank"] = i + 1

    # Compute "key props" and best possible finish
    _compute_key_props(leaderboard, open_ids, overrides)
    _compute_best_possible_finish(leaderboard, open_ids, overrides)

    return {
        "leaderboard": leaderboard,
        "props": props_status,
        "summary": {
            "total_props": total_props,
            "resolved_count": resolved_count,
            "open_count": total_props - resolved_count,
            "entrant_count": len(entries),
            "categories": CATEGORY_LABELS,
            "category_order": CATEGORY_ORDER,
        },
    }


def _compute_key_props(leaderboard: list, open_ids: list, overrides: dict):
    """For each entrant, find which open props matter most for their ranking."""
    for entry in leaderboard:
        if not entry["pending_picks"]:
            entry["key_props"] = []
            continue

        key_props = []
        for pending in entry["pending_picks"]:
            prob = pending["probability"]

            same_pick_count = sum(
                1 for other in leaderboard
                if other["name"] != entry["name"]
                and any(
                    p["prop_id"] == pending["prop_id"]
                    and _normalize_answer(p["pick"]) == _normalize_answer(pending["pick"])
                    for p in other["pending_picks"]
                )
            )
            total_others = len(leaderboard) - 1
            uniqueness = 1.0 - (same_pick_count / max(total_others, 1))

            impact = prob * (0.5 + 0.5 * uniqueness)

            key_props.append({
                "prop_id": pending["prop_id"],
                "question": pending["question"],
                "pick": pending["pick"],
                "probability": pending["probability"],
                "impact_score": round(impact, 3),
                "uniqueness": round(uniqueness, 2),
            })

        key_props.sort(key=lambda x: -x["impact_score"])
        entry["key_props"] = key_props[:3]


def _compute_best_possible_finish(leaderboard: list, open_ids: list, overrides: dict):
    """For each entrant, compute their best possible final rank."""
    for entry in leaderboard:
        my_best = entry["actual_points"] + len(entry["pending_picks"])

        better_count = 0
        for other in leaderboard:
            if other["name"] == entry["name"]:
                continue
            other_min = other["actual_points"]
            if other_min > my_best:
                better_count += 1

        best_rank = better_count + 1
        entry["best_possible_finish"] = best_rank
        entry["can_still_win"] = best_rank == 1
        entry["eliminated"] = best_rank > 1 and my_best < max(
            (o["actual_points"] for o in leaderboard if o["name"] != entry["name"]),
            default=0,
        )


# ---------------------------------------------------------------------------
# AI Commentary
# ---------------------------------------------------------------------------

async def _generate_commentary(leaderboard_data: dict) -> str:
    """Generate funny AI commentary about the current contest state."""
    try:
        from app.services.llm import _get_client
        client = _get_client()
        if not client:
            return "Commentary unavailable - OpenAI not configured."

        summary = leaderboard_data["summary"]
        lb = leaderboard_data["leaderboard"]

        leader = lb[0] if lb else None
        last = lb[-1] if lb else None

        recently_resolved = []
        for prop in leaderboard_data["props"]:
            if prop["resolved"]:
                recently_resolved.append(f"- {prop['question']}: {prop['correct_answer']}")

        resolved_text = "\n".join(recently_resolved[-5:]) if recently_resolved else "None yet"

        standings = "\n".join(
            f"  {e['rank']}. {e['name']} - {e['actual_points']} pts ({e['forecasted_points']} forecast)"
            for e in lb[:10]
        )

        notable = []
        for e in lb:
            if e.get("eliminated"):
                notable.append(f"{e['name']} has been mathematically eliminated!")
            if e.get("best_possible_finish") == 1 and e["rank"] > 3:
                notable.append(f"{e['name']} is in {e['rank']}th but could still WIN!")

        notable_text = "\n".join(notable) if notable else "No major drama yet."

        prompt = f"""Super Bowl LX prop bet contest — Seahawks vs Patriots.

State: {summary['resolved_count']}/{summary['total_props']} props resolved, {summary['entrant_count']} contestants.

Standings:
{standings}

Resolved: {resolved_text}

Drama: {notable_text}

Write ONE punchy sentence (max 20 words) of hilarious commentary. Roast losers, hype winners. Use specific names. Think comedian, not sportscaster. No hashtags."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a ruthlessly funny Super Bowl party roast comedian. One devastating sentence only. PG-rated."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=80,
            temperature=1.0,
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"Commentary generation failed: {e}")
        return "The AI commentator spilled Gatorade on its keyboard. Stand by!"


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@router.get("/leaderboard")
async def get_leaderboard(db: AsyncSession = Depends(get_db)):
    """
    Main endpoint: fetches entries, computes scores, returns full leaderboard.
    Also runs auto-resolution and live odds updates from the database.
    Designed to be polled every 15-30 seconds by the frontend.
    """
    # 1. Auto-resolve any props determinable from game state
    try:
        auto_resolved = await _auto_resolve_from_game_state(db)
        if auto_resolved:
            logger.info(f"Auto-resolved during leaderboard: {auto_resolved}")
    except Exception as e:
        logger.error(f"Auto-resolve error: {e}")

    # 2. Get live odds updates from DB
    live_odds = {}
    try:
        sb_event = await _find_super_bowl_event(db)
        if sb_event:
            live_odds = await _get_live_odds_updates(db, sb_event)
    except Exception as e:
        logger.error(f"Live odds error: {e}")

    # 3. Merge live odds into overrides (live odds take priority)
    overrides = _get_odds_overrides()
    merged_overrides = {**overrides}
    for prop_id, choices in live_odds.items():
        if not prop_id.startswith("_"):
            # Only override if there's no manual admin override for this prop
            if prop_id not in overrides:
                merged_overrides[prop_id] = choices

    # 4. Fetch entries and compute
    entries, _headers = await _fetch_sheet_entries()
    resolutions = _get_resolution_state()

    result = _compute_leaderboard(entries, resolutions, merged_overrides)
    return result


@router.get("/props")
async def get_props():
    """Get all prop definitions with current odds and resolution status."""
    resolutions = _get_resolution_state()
    overrides = _get_odds_overrides()

    props = []
    for prop in PROPS:
        if prop.get("is_tiebreaker"):
            props.append({
                "id": prop["id"],
                "question": prop["question"],
                "category": prop["category"],
                "is_tiebreaker": True,
                "resolved": False,
            })
            continue

        resolution = resolutions.get(prop["id"])
        choices = dict(prop["choices"])

        if prop["id"] in overrides:
            choices.update(overrides[prop["id"]])

        props.append({
            "id": prop["id"],
            "question": prop["question"],
            "category": prop["category"],
            "choices": choices,
            "resolved": resolution is not None,
            "correct_answer": resolution["correct_answer"] if resolution else None,
            "resolved_at": resolution.get("resolved_at") if resolution else None,
            "has_other": prop.get("has_other", False),
            "other_probability": prop.get("other_probability", 0.0),
        })

    return {"props": props, "categories": CATEGORY_LABELS}


@router.post("/resolve")
async def resolve_prop(
    prop_id: str = Query(..., description="Prop ID to resolve"),
    correct_answer: str = Query(..., description="The correct answer"),
    secret: str = Query("", description="Admin secret"),
):
    """Admin: resolve a prop with the correct answer."""
    if prop_id not in PROP_BY_ID:
        return {"error": f"Unknown prop_id: {prop_id}"}

    prop = PROP_BY_ID[prop_id]
    if prop.get("is_tiebreaker"):
        return {"error": "Cannot resolve tiebreaker prop"}

    resolutions = _get_resolution_state()
    resolutions[prop_id] = {
        "correct_answer": correct_answer,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_resolution_state(resolutions)

    return {
        "status": "resolved",
        "prop_id": prop_id,
        "correct_answer": correct_answer,
        "total_resolved": len(resolutions),
    }


@router.post("/unresolve")
async def unresolve_prop(
    prop_id: str = Query(..., description="Prop ID to unresolve"),
    secret: str = Query("", description="Admin secret"),
):
    """Admin: unresolve a prop (undo a resolution)."""
    resolutions = _get_resolution_state()
    if prop_id in resolutions:
        del resolutions[prop_id]
        _save_resolution_state(resolutions)
        return {"status": "unresolved", "prop_id": prop_id}
    return {"error": f"Prop {prop_id} was not resolved"}


@router.post("/update-odds")
async def update_odds(
    prop_id: str = Query(..., description="Prop ID"),
    choice: str = Query(..., description="Choice to update"),
    probability: float = Query(..., description="New probability (0.0-1.0)"),
    secret: str = Query("", description="Admin secret"),
):
    """Admin: override odds for a specific prop choice."""
    if prop_id not in PROP_BY_ID:
        return {"error": f"Unknown prop_id: {prop_id}"}

    overrides = _get_odds_overrides()
    if prop_id not in overrides:
        overrides[prop_id] = {}
    overrides[prop_id][choice] = probability
    _save_odds_overrides(overrides)

    return {"status": "updated", "prop_id": prop_id, "choice": choice, "probability": probability}


@router.get("/commentary")
async def get_commentary(db: AsyncSession = Depends(get_db)):
    """Generate AI commentary or fun fact, alternating each request."""
    # Also run auto-resolve so commentary reflects latest state
    try:
        await _auto_resolve_from_game_state(db)
    except Exception:
        pass

    # Alternate between AI roast and fun fact using Redis counter
    show_fun_fact = False
    try:
        r = _redis()
        counter = int(r.get(f"{REDIS_KEY_PREFIX}commentary_counter") or 0)
        show_fun_fact = counter % 3 != 0  # 2 out of 3 = fun fact/trivia, every 3rd = roast
        r.set(f"{REDIS_KEY_PREFIX}commentary_counter", counter + 1)
    except Exception:
        pass

    if show_fun_fact and SB_FUN_FACTS:
        # Pick a random fun fact (use counter as seed for variety)
        import random as _rng
        fact_data = _rng.choice(SB_FUN_FACTS)

        # If fact has trivia fields, return as interactive trivia question
        if fact_data.get("trivia_question"):
            return {
                "commentary": fact_data["fact"],
                "type": "trivia",
                "category": fact_data.get("category", ""),
                "trivia_question": fact_data["trivia_question"],
                "trivia_answer": fact_data["trivia_answer"],
                "trivia_wrong": fact_data["trivia_wrong"],
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        return {
            "commentary": fact_data["fact"],
            "type": "fun_fact",
            "category": fact_data.get("category", ""),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    entries, _headers = await _fetch_sheet_entries()
    resolutions = _get_resolution_state()
    overrides = _get_odds_overrides()

    leaderboard_data = _compute_leaderboard(entries, resolutions, overrides)
    commentary = await _generate_commentary(leaderboard_data)

    return {
        "commentary": commentary,
        "type": "roast",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/entries")
async def get_entries():
    """Debug: view all parsed entries from the Google Sheet."""
    entries, headers = await _fetch_sheet_entries()
    return {
        "entries": entries,
        "count": len(entries),
        "csv_headers": headers,
        "detected_name_column": _detect_name_column(headers) if headers else None,
        "sheet_url": SHEET_CSV_URL,
    }


@router.get("/debug")
async def debug_contest(db: AsyncSession = Depends(get_db)):
    """Debug: full diagnostic of contest state."""
    entries, headers = await _fetch_sheet_entries()
    resolutions = _get_resolution_state()
    overrides = _get_odds_overrides()

    sb_event = None
    live_odds = {}
    event_info = None
    try:
        sb_event = await _find_super_bowl_event(db)
        if sb_event:
            live_odds = await _get_live_odds_updates(db, sb_event)
            event_info = {
                "id": sb_event.id,
                "status": sb_event.status,
                "home_team": sb_event.home_team_name,
                "away_team": sb_event.away_team_name,
                "home_score": sb_event.home_score,
                "away_score": sb_event.away_score,
                "period": sb_event.period,
                "game_clock": sb_event.game_clock,
            }
    except Exception as e:
        event_info = {"error": str(e)}

    # Show all entries with their pick counts for debugging
    entries_debug = []
    for e in entries:
        entries_debug.append({
            "name": e["name"],
            "picks_count": len(e.get("picks", {})),
            "picks": e.get("picks", {}),
            "tiebreaker": e.get("tiebreaker"),
        })

    # Check Redis cache status
    redis_cache = None
    try:
        r = _redis()
        cached = r.get(f"{REDIS_KEY_PREFIX}entries_cache")
        if cached:
            cdata = json.loads(cached)
            redis_cache = f"{len(cdata.get('entries', []))} entries cached"
        else:
            redis_cache = "no cache"
    except Exception as ex:
        redis_cache = f"error: {ex}"

    return {
        "csv": {
            "url": SHEET_CSV_URL,
            "headers": headers,
            "header_count": len(headers),
            "detected_name_column": _detect_name_column(headers) if headers else None,
            "entry_count": len(entries),
            "entries": entries_debug,
            "redis_cache": redis_cache,
        },
        "resolutions": resolutions,
        "overrides": overrides,
        "live_odds": live_odds,
        "super_bowl_event": event_info,
        "prop_ids": [p["id"] for p in PROPS if not p.get("is_tiebreaker")],
    }


@router.post("/set-halftime-score")
async def set_halftime_score(
    home_score: int = Query(..., description="Home team halftime score"),
    away_score: int = Query(..., description="Away team halftime score"),
    secret: str = Query("", description="Admin secret"),
):
    """Admin: manually set halftime scores (triggers halftime_leader resolution)."""
    try:
        r = _redis()
        scores = {"home": home_score, "away": away_score}
        r.set(f"{REDIS_KEY_PREFIX}halftime_scores", json.dumps(scores))
        return {"status": "set", "scores": scores, "message": "Halftime scores saved. Auto-resolution will pick this up on next leaderboard poll."}
    except Exception as e:
        return {"error": str(e)}


@router.post("/capture-bitcoin-start")
async def capture_bitcoin_start(secret: str = Query("", description="Admin secret")):
    """Admin: capture bitcoin price at kickoff. Call this when the game starts."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
            )
            resp.raise_for_status()
            price = resp.json().get("bitcoin", {}).get("usd")

        if price is None:
            return {"error": "Could not fetch bitcoin price"}

        r = _redis()
        r.set(f"{REDIS_KEY_PREFIX}btc_start_price", str(price))
        return {"status": "captured", "price": price, "message": "Bitcoin start price saved. Will auto-resolve when game ends."}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# YouTube Super Bowl Ad Leaderboard
# ---------------------------------------------------------------------------

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

# Game day: Feb 8, 2026 (Super Bowl LX).
# Schedule:
#   Morning-2PM Pacific: 45 min cache, budget quota (~600 units)
#   2PM Pacific: auto-reset baseline so view deltas track game-time growth
#   2PM-8PM Pacific: 7 min cache, maximize freshness (~7.7K units)
#   Post-game: 30 min cache
#   Total worst case: ~8.3K / 10K quota budget
#
# 2PM Pacific = 22:00 UTC.  8PM Pacific = 04:00 UTC next day.

PREGAME_START_UTC = datetime(2026, 2, 8, 16, 0, 0, tzinfo=timezone.utc)  # 8 AM Pacific
GAME_START_UTC = datetime(2026, 2, 8, 22, 0, 0, tzinfo=timezone.utc)     # 2 PM Pacific
GAME_END_UTC = datetime(2026, 2, 9, 4, 0, 0, tzinfo=timezone.utc)        # 8 PM Pacific


def _youtube_cache_ttl() -> int:
    """Dynamic cache TTL based on game time.

    Returns (ttl_seconds).  Mode is derived separately in _youtube_mode().
    """
    now = datetime.now(timezone.utc)
    # Game window (2PM-8PM Pacific) — most aggressive
    if GAME_START_UTC <= now <= GAME_END_UTC:
        return 420   # 7 minutes
    # Pre-game morning (8AM-2PM Pacific) — conservative, save quota
    if PREGAME_START_UTC <= now < GAME_START_UTC:
        return 2700  # 45 minutes
    return 1800      # 30 minutes otherwise


def _youtube_mode() -> str:
    """Current operational mode for the ad leaderboard."""
    now = datetime.now(timezone.utc)
    if GAME_START_UTC <= now <= GAME_END_UTC:
        return "game"
    if PREGAME_START_UTC <= now < GAME_START_UTC:
        return "pregame"
    return "idle"

# Hardcoded Super Bowl LX ads — always available even without YouTube API.
# When the YouTube API is configured, live view counts replace these.
SB_ADS_CURATED = [
    {"brand": "Budweiser", "title": '"American Icons" — Clydesdale foal + bald eagle, set to Free Bird', "celebrity": "Clydesdale", "search": "Budweiser Super Bowl LX American Icons"},
    {"brand": "Uber Eats", "title": '"Foodball" — Football was invented to sell food', "celebrity": "Matthew McConaughey, Bradley Cooper", "search": "Uber Eats Super Bowl 2026 McConaughey"},
    {"brand": "Google Gemini", "title": '"New Home" — Mom + son using Gemini AI', "celebrity": "Randy Newman song", "search": "Google Gemini New Home Super Bowl 2026"},
    {"brand": "Pepsi Zero Sugar", "title": '"The Choice" — Polar bear blind taste test', "celebrity": "Directed by Taika Waititi", "search": "Pepsi Zero Sugar Super Bowl 2026"},
    {"brand": "Bud Light", "title": '"Keg" — Post Malone at a wedding', "celebrity": "Post Malone, Shane Gillis, Peyton Manning", "search": "Bud Light Super Bowl 2026 Keg"},
    {"brand": "Instacart", "title": '"Bananas" — Directed by Spike Jonze', "celebrity": "Ben Stiller, Benson Boone", "search": "Instacart Bananas Super Bowl 2026"},
    {"brand": "DoorDash", "title": '"Beef" — 50 Cent settles the beef', "celebrity": "50 Cent", "search": "DoorDash Super Bowl 2026 50 Cent"},
    {"brand": "Pringles", "title": 'Sabrina Carpenter builds a man out of Pringles', "celebrity": "Sabrina Carpenter", "search": "Pringles Sabrina Carpenter Super Bowl 2026"},
    {"brand": "Hellmann's", "title": '"Meal Diamond" — Andy Samberg condiment hero', "celebrity": "Andy Samberg, Elle Fanning", "search": "Hellmanns Super Bowl 2026 Andy Samberg"},
    {"brand": "Dunkin'", "title": 'Ben Affleck + Friends cast reunion', "celebrity": "Ben Affleck, Jennifer Aniston, Jason Alexander", "search": "Dunkin Super Bowl 2026 Affleck"},
    {"brand": "Squarespace", "title": '"Unavailable" — Directed by Yorgos Lanthimos', "celebrity": "Emma Stone", "search": "Squarespace Super Bowl 2026 Emma Stone"},
    {"brand": "Ritz", "title": '"Ritz Island" — Celebrity island escape', "celebrity": "Jon Hamm, Scarlett Johansson, Bowen Yang", "search": "Ritz Super Bowl 2026 Jon Hamm"},
    {"brand": "State Farm", "title": '"Halfway There" — Insurance agents gone wild', "celebrity": "Danny McBride, Keegan-Michael Key", "search": "State Farm Super Bowl 2026 McBride"},
    {"brand": "Amazon Alexa+", "title": 'AI assistant horror comedy', "celebrity": "Chris Hemsworth, Elsa Pataky", "search": "Amazon Alexa Super Bowl 2026 Hemsworth"},
    {"brand": "Xfinity", "title": '"Jurassic Park...Works" — Original cast reunion', "celebrity": "Sam Neill, Laura Dern, Jeff Goldblum", "search": "Xfinity Jurassic Park Super Bowl 2026"},
    {"brand": "Toyota", "title": '"Superhero Belt" — RAV4 30th anniversary', "celebrity": "Grandfather-grandson story", "search": "Toyota Superhero Belt Super Bowl 2026"},
    {"brand": "T-Mobile", "title": 'Backstreet Boys comeback', "celebrity": "Backstreet Boys, Druski", "search": "T-Mobile Super Bowl 2026 Backstreet Boys"},
    {"brand": "Meta/Oakley", "title": '"Athletic Intelligence Is Here" — AI glasses', "celebrity": "Spike Lee, Marshawn Lynch", "search": "Meta Oakley Super Bowl 2026"},
    {"brand": "Rocket/Redfin", "title": 'Mr. Rogers tribute, 60 seconds', "celebrity": "Lady Gaga", "search": "Rocket Redfin Super Bowl 2026 Lady Gaga"},
    {"brand": "Dove", "title": '"The Game Is Ours" — Body positivity for girls in sports', "celebrity": "", "search": "Dove Super Bowl 2026"},
    {"brand": "Michelob Ultra", "title": 'Skiing adventure', "celebrity": "Kurt Russell, Chloe Kim", "search": "Michelob Ultra Super Bowl 2026"},
    {"brand": "Novartis", "title": '"Relax Your Tight End" — Prostate cancer screening', "celebrity": "Rob Gronkowski, George Kittle", "search": "Novartis Super Bowl 2026"},
    {"brand": "TurboTax", "title": '"The Expert" — Noir-style tax drama', "celebrity": "Adrien Brody", "search": "TurboTax Super Bowl 2026 Adrien Brody"},
    {"brand": "Oikos", "title": '"The Big Hill" — SF cable car', "celebrity": "Kathryn Hahn, Derrick Henry", "search": "Oikos Super Bowl 2026"},
    {"brand": "Nerds", "title": '"Taste Buds" — Gummy character', "celebrity": "Andy Cohen", "search": "Nerds Taste Buds Super Bowl 2026"},
    {"brand": "e.l.f. Cosmetics", "title": '"Melisa" — Telenovela parody', "celebrity": "Melissa McCarthy", "search": "elf Cosmetics Super Bowl 2026"},
    {"brand": "Anthropic", "title": '"Can I Get a Six Pack Quickly?"', "celebrity": "Dr. Dre music", "search": "Anthropic Claude Super Bowl 2026"},
    {"brand": "Salesforce", "title": 'Cash giveaway concept', "celebrity": "MrBeast", "search": "Salesforce Super Bowl 2026 MrBeast"},
    {"brand": "Frank's RedHot", "title": '"Eat the GOAT"', "celebrity": "Ludacris, Chingy", "search": "Franks RedHot Super Bowl 2026"},
    {"brand": "Lay's", "title": '"The Last Harvest" — Family potato farm', "celebrity": "", "search": "Lays Super Bowl 2026 Last Harvest"},
]

# Brand matching list (extracted from curated + extras)
SB_AD_BRANDS = [ad["brand"].split("/")[0] for ad in SB_ADS_CURATED] + [
    "Coca-Cola", "Mountain Dew", "Nike", "BMW", "Hyundai", "Kia",
    "FanDuel", "DraftKings", "Disney", "Paramount", "Netflix", "Tubi",
    "Crown Royal", "GoDaddy", "Homes.com", "Skechers", "Jeep", "Bosch",
    "GrubHub", "Wells Fargo", "Ramp", "Fanatics", "Ring", "Ro",
]

# Map short/alternate names → curated brand name.  Checked BEFORE SB_AD_BRANDS.
BRAND_ALIASES: dict[str, str] = {
    "pepsi": "Pepsi Zero Sugar",
    "google": "Google Gemini",
    "gemini": "Google Gemini",
    "amazon": "Amazon Alexa+",
    "alexa": "Amazon Alexa+",
    "alexa+": "Amazon Alexa+",
    "meta": "Meta/Oakley",
    "oakley": "Meta/Oakley",
    "rocket": "Rocket/Redfin",
    "redfin": "Rocket/Redfin",
    "rocket mortgage": "Rocket/Redfin",
    "mrbeast": "Salesforce",
    "franks": "Frank's RedHot",
    "frank's": "Frank's RedHot",
    "redhot": "Frank's RedHot",
    "elf": "e.l.f. Cosmetics",
    "e.l.f.": "e.l.f. Cosmetics",
    "elf cosmetics": "e.l.f. Cosmetics",
    "t-mobile": "T-Mobile",
    "tmobile": "T-Mobile",
    "michelob": "Michelob Ultra",
    "bud light": "Bud Light",
    "budweiser": "Budweiser",
    "uber eats": "Uber Eats",
    "uber": "Uber Eats",
    "doordash": "DoorDash",
    "door dash": "DoorDash",
    "turbotax": "TurboTax",
    "turbo tax": "TurboTax",
    "hellmanns": "Hellmann's",
    "hellmann's": "Hellmann's",
    "dunkin": "Dunkin'",
    "dunkin'": "Dunkin'",
    "squarespace": "Squarespace",
    "lay's": "Lay's",
    "lays": "Lay's",
    "frito-lay": "Lay's",
    "anthropic": "Anthropic",
    "claude": "Anthropic",
}


async def _fetch_youtube_ads() -> list[dict]:
    """Fetch Super Bowl LX ad leaderboard.

    Strategy:
    1. Broad searches with varied queries (100 quota units each)
    2. Targeted per-brand searches for curated ads not found (100 units each)
    3. Batch stats fetch for all discovered videos (1 unit per video)

    Quota budget varies by mode:
    - idle:    2 broad + up to 5 targeted (~700 units per miss, 30 min cache)
    - pregame: 2 broad + up to 5 targeted (~700 units per miss, 45 min cache)
    - game:    2 broad + up to 15 targeted (~1,700 units per miss, 7 min cache)
    """
    cache_key = f"{REDIS_KEY_PREFIX}youtube_ads"

    # Check Redis cache
    try:
        r = _redis()
        cached = r.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        pass

    ads: list[dict] = []
    found_brands: set[str] = set()
    mode = _youtube_mode()

    if YOUTUBE_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                all_video_ids: list[str] = []
                video_snippets: dict[str, dict] = {}

                # --- Phase 1: Broad searches ---
                broad_queries = [
                    "Super Bowl LX 2026 commercial ad",
                    "Super Bowl 2026 ad official",
                ]

                search_url = "https://www.googleapis.com/youtube/v3/search"
                for query in broad_queries:
                    search_params = {
                        "key": YOUTUBE_API_KEY,
                        "q": query,
                        "type": "video",
                        "part": "snippet",
                        "maxResults": 50,
                        "order": "viewCount",
                        "publishedAfter": "2025-11-01T00:00:00Z",
                    }
                    resp = await client.get(search_url, params=search_params)
                    if resp.status_code == 200:
                        items = resp.json().get("items", [])
                        before = len(all_video_ids)
                        for item in items:
                            vid_id = item.get("id", {}).get("videoId", "")
                            if vid_id and vid_id not in video_snippets:
                                all_video_ids.append(vid_id)
                                video_snippets[vid_id] = item.get("snippet", {})
                        logger.info(
                            f"YouTube broad search '{query}': "
                            f"{len(items)} results, {len(all_video_ids) - before} new videos"
                        )
                    elif resp.status_code == 403:
                        logger.error("YouTube quota exceeded during broad search")
                        break  # stop searching, use what we have
                    else:
                        logger.warning(f"YouTube search '{query}': HTTP {resp.status_code}")

                # --- Phase 2: Identify which brands we found so far ---
                preliminary_brands: set[str] = set()
                for vid_id in all_video_ids:
                    snippet = video_snippets.get(vid_id, {})
                    title = snippet.get("title", "")
                    channel = snippet.get("channelTitle", "")
                    brand = _identify_brand(title, channel)
                    if brand:
                        preliminary_brands.add(brand)

                # --- Phase 3: Targeted searches for missing curated brands ---
                missing = [
                    c for c in SB_ADS_CURATED
                    if c["brand"] not in preliminary_brands and c.get("search")
                ]
                if missing:
                    # Pregame: up to 15 targeted (1,500 units, 45 min cache = ~8 misses/6h).
                    # Game: up to 20 targeted (2,000 units, 7 min cache — but most brands
                    # are already cached so only missing ones are searched).
                    max_targeted = 20 if mode == "game" else 15
                    for curated in missing[:max_targeted]:
                        resp = await client.get(search_url, params={
                            "key": YOUTUBE_API_KEY,
                            "q": curated["search"],
                            "type": "video",
                            "part": "snippet",
                            "maxResults": 3,
                            "order": "relevance",
                            "publishedAfter": "2025-11-01T00:00:00Z",
                        })
                        if resp.status_code == 200:
                            for item in resp.json().get("items", []):
                                vid_id = item.get("id", {}).get("videoId", "")
                                if vid_id and vid_id not in video_snippets:
                                    all_video_ids.append(vid_id)
                                    video_snippets[vid_id] = item.get("snippet", {})
                        elif resp.status_code == 403:
                            logger.error("YouTube quota exceeded during targeted search")
                            break

                # --- Phase 4: Batch fetch stats ---
                stats_map: dict[str, dict] = {}
                for i in range(0, len(all_video_ids), 50):
                    batch = all_video_ids[i:i+50]
                    stats_url = "https://www.googleapis.com/youtube/v3/videos"
                    stats_params = {
                        "key": YOUTUBE_API_KEY,
                        "id": ",".join(batch),
                        "part": "statistics",
                    }
                    resp = await client.get(stats_url, params=stats_params)
                    if resp.status_code == 200:
                        for item in resp.json().get("items", []):
                            stats_map[item["id"]] = item.get("statistics", {})

                # --- Phase 5: Build ad list ---
                for vid_id in all_video_ids:
                    snippet = video_snippets.get(vid_id, {})
                    stats = stats_map.get(vid_id, {})
                    title = snippet.get("title", "")
                    channel = snippet.get("channelTitle", "")
                    brand = _identify_brand(title, channel)

                    if not brand:
                        brand = channel or title.split(" - ")[0][:30] or "Unknown"

                    if brand not in found_brands:
                        curated_match = next(
                            (c for c in SB_ADS_CURATED if c["brand"] == brand), None
                        )
                        found_brands.add(brand)
                        ads.append({
                            "brand": brand,
                            "title": curated_match["title"] if curated_match else title,
                            "video_id": vid_id,
                            "channel": channel,
                            "celebrity": curated_match.get("celebrity", "") if curated_match else "",
                            "thumbnail": snippet.get("thumbnails", {}).get("medium", {}).get("url", ""),
                            "views": int(stats.get("viewCount", 0)),
                            "likes": int(stats.get("likeCount", 0)),
                            "comments": int(stats.get("commentCount", 0)),
                            "published_at": snippet.get("publishedAt", ""),
                        })

                ads.sort(key=lambda x: -x["views"])
                logger.info(
                    f"YouTube ads: {len(ads)} found via API, "
                    f"{len(found_brands & {c['brand'] for c in SB_ADS_CURATED})} curated matched, "
                    f"mode={mode}"
                )
        except Exception as e:
            logger.error(f"YouTube API error: {e}")

    # Append curated ads not found via YouTube (no video, shown at bottom)
    for curated in SB_ADS_CURATED:
        if curated["brand"] not in found_brands:
            ads.append({
                "brand": curated["brand"],
                "title": curated["title"],
                "video_id": "",
                "channel": "",
                "celebrity": curated.get("celebrity", ""),
                "thumbnail": "",
                "views": 0,
                "likes": 0,
                "comments": 0,
                "published_at": "",
            })

    # Cache result — only cache with full TTL if we got real YouTube data.
    # If YouTube API failed (all ads have views=0), use a short TTL so the
    # next request retries quickly instead of serving stale zero-view data.
    has_real_data = any(ad.get("video_id") for ad in ads)
    try:
        r = _redis()
        ttl = _youtube_cache_ttl() if has_real_data else 30  # 30s retry on failure
        r.setex(cache_key, ttl, json.dumps(ads))
    except Exception:
        pass

    return ads


def _identify_brand(title: str, channel: str) -> Optional[str]:
    """Identify the advertiser brand from a YouTube video title/channel."""
    title_lower = title.lower()
    channel_lower = channel.lower()
    combined = title_lower + " " + channel_lower

    # 1. Check aliases first (maps short names → canonical curated brand)
    for alias, canonical in BRAND_ALIASES.items():
        if re.search(r'\b' + re.escape(alias) + r'\b', combined):
            return canonical

    # 2. Check against known brands (exact word boundary)
    for brand in SB_AD_BRANDS:
        brand_lower = brand.lower()
        if re.search(r'\b' + re.escape(brand_lower) + r'\b', combined):
            # Map back to curated brand if this is a substring (e.g., "Rocket" → "Rocket/Redfin")
            curated = next((c["brand"] for c in SB_ADS_CURATED if brand_lower in c["brand"].lower()), None)
            return curated or brand

    # 3. Check if the channel name IS the brand (official uploads)
    for brand in SB_AD_BRANDS:
        if brand.lower() in channel_lower:
            curated = next((c["brand"] for c in SB_ADS_CURATED if brand.lower() in c["brand"].lower()), None)
            return curated or brand

    # 4. Title parsing fallback — check each segment for known brands
    if ("super bowl" in title_lower or "sb " in title_lower) and \
       any(w in title_lower for w in ["ad", "commercial", "spot", "teaser", "trailer"]):
        # Check pipe/dash segments for brand matches before blind extraction
        for sep in [" | ", " - "]:
            for segment in title.split(sep):
                seg = segment.strip().lower()
                for alias, canonical in BRAND_ALIASES.items():
                    if re.search(r'\b' + re.escape(alias) + r'\b', seg):
                        return canonical
                for brand in SB_AD_BRANDS:
                    if re.search(r'\b' + re.escape(brand.lower()) + r'\b', seg):
                        curated = next((c["brand"] for c in SB_ADS_CURATED if brand.lower() in c["brand"].lower()), None)
                        return curated or brand
        # Last resort: use first segment as brand name
        dash_split = title.split(" - ")
        if len(dash_split) >= 2 and len(dash_split[0].strip()) < 30:
            return dash_split[0].strip()
        pipe_split = title.split(" | ")
        if len(pipe_split) >= 2 and len(pipe_split[0].strip()) < 30:
            return pipe_split[0].strip()

    return None


def _format_view_count(views: int) -> str:
    """Format a view count for display: 1234567 -> '1.2M'"""
    if views >= 1_000_000:
        return f"{views / 1_000_000:.1f}M"
    elif views >= 1_000:
        return f"{views / 1_000:.1f}K"
    return str(views)


@router.get("/ads/debug")
async def debug_youtube_search():
    """Debug: run a fresh YouTube search and show raw results + brand matching.

    Does NOT update the cache. Costs ~500 quota units (2 broad + 3 targeted).
    """
    if not YOUTUBE_API_KEY:
        return {"error": "YOUTUBE_API_KEY not set"}

    results = []
    matched_brands: list[str] = []
    unmatched_titles: list[str] = []

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            search_url = "https://www.googleapis.com/youtube/v3/search"
            for query in ["Super Bowl LX 2026 commercial ad", "Super Bowl 2026 ad official"]:
                resp = await client.get(search_url, params={
                    "key": YOUTUBE_API_KEY,
                    "q": query,
                    "type": "video",
                    "part": "snippet",
                    "maxResults": 20,
                    "order": "viewCount",
                    "publishedAfter": "2025-11-01T00:00:00Z",
                })
                if resp.status_code != 200:
                    results.append({"query": query, "error": resp.status_code, "body": resp.text[:500]})
                    continue
                items = resp.json().get("items", [])
                for item in items:
                    vid_id = item.get("id", {}).get("videoId", "")
                    snippet = item.get("snippet", {})
                    title = snippet.get("title", "")
                    channel = snippet.get("channelTitle", "")
                    brand = _identify_brand(title, channel)
                    entry = {
                        "query": query,
                        "video_id": vid_id,
                        "title": title,
                        "channel": channel,
                        "brand_match": brand,
                    }
                    results.append(entry)
                    if brand and brand not in matched_brands:
                        matched_brands.append(brand)
                    elif not brand:
                        unmatched_titles.append(f"{title} [{channel}]")

            # Also test 3 targeted searches
            targeted_results = []
            for curated in SB_ADS_CURATED[:3]:
                resp = await client.get(search_url, params={
                    "key": YOUTUBE_API_KEY,
                    "q": curated["search"],
                    "type": "video",
                    "part": "snippet",
                    "maxResults": 3,
                    "order": "relevance",
                    "publishedAfter": "2025-11-01T00:00:00Z",
                })
                if resp.status_code == 200:
                    for item in resp.json().get("items", []):
                        snippet = item.get("snippet", {})
                        targeted_results.append({
                            "search_query": curated["search"],
                            "brand": curated["brand"],
                            "video_title": snippet.get("title", ""),
                            "channel": snippet.get("channelTitle", ""),
                            "brand_match": _identify_brand(
                                snippet.get("title", ""), snippet.get("channelTitle", "")
                            ),
                        })

    except Exception as e:
        return {"error": str(e)}

    curated_brands = [c["brand"] for c in SB_ADS_CURATED]
    return {
        "mode": _youtube_mode(),
        "broad_search_results": len(results),
        "matched_brands": matched_brands,
        "matched_count": len(matched_brands),
        "curated_brands_found": [b for b in matched_brands if b in curated_brands],
        "unmatched_sample": unmatched_titles[:10],
        "targeted_search_sample": targeted_results,
        "raw_results": results[:30],
    }


@router.get("/ads/status")
async def get_ad_status():
    """Debug: show ad leaderboard status without fetching YouTube."""
    mode = _youtube_mode()
    ttl = _youtube_cache_ttl()
    now = datetime.now(timezone.utc)

    status: dict = {
        "mode": mode,
        "cache_ttl_seconds": ttl,
        "youtube_configured": bool(YOUTUBE_API_KEY),
        "utc_now": now.isoformat(),
        "time_windows": {
            "pregame": f"{PREGAME_START_UTC.isoformat()} to {GAME_START_UTC.isoformat()}",
            "game": f"{GAME_START_UTC.isoformat()} to {GAME_END_UTC.isoformat()}",
        },
    }

    try:
        r = _redis()
        cache_exists = r.exists(f"{REDIS_KEY_PREFIX}youtube_ads")
        cache_ttl_remaining = r.ttl(f"{REDIS_KEY_PREFIX}youtube_ads")
        baseline_exists = r.exists(f"{REDIS_KEY_PREFIX}ad_baseline")
        game_reset = r.exists(f"{REDIS_KEY_PREFIX}ad_auto_reset:game")

        status["redis"] = {
            "cache_exists": bool(cache_exists),
            "cache_ttl_remaining": cache_ttl_remaining,
            "baseline_exists": bool(baseline_exists),
            "auto_reset_game_done": bool(game_reset),
        }

        if cache_exists:
            cached = json.loads(r.get(f"{REDIS_KEY_PREFIX}youtube_ads"))
            with_video = sum(1 for ad in cached if ad.get("video_id"))
            status["cached_ads"] = {
                "total": len(cached),
                "with_video": with_video,
                "brands_with_video": [ad["brand"] for ad in cached if ad.get("video_id")][:15],
            }
    except Exception as e:
        status["redis_error"] = str(e)

    return status


@router.get("/ads")
async def get_ad_leaderboard():
    """Get Super Bowl ad leaderboard ranked by YouTube views."""
    ads = await _fetch_youtube_ads()
    mode = _youtube_mode()

    # --- Auto-reset baseline at 2PM Pacific (game start) ---
    # Automatically reset the baseline so view deltas track game-time growth.
    baseline_key = f"{REDIS_KEY_PREFIX}ad_baseline"
    auto_reset_key = f"{REDIS_KEY_PREFIX}ad_auto_reset:game"
    baseline: dict[str, int] = {}
    try:
        r = _redis()

        # Check if we need to auto-reset for game mode transition
        if mode == "game" and not r.get(auto_reset_key):
            # Save old data as fallback before clearing cache
            old_cache = r.get(f"{REDIS_KEY_PREFIX}youtube_ads")
            r.delete(f"{REDIS_KEY_PREFIX}youtube_ads")  # clear cache to force fresh fetch
            logger.info(f"Auto-reset ad baseline for mode={mode}")
            # Re-fetch with fresh cache
            ads = await _fetch_youtube_ads()

            has_real_data = any(ad.get("video_id") for ad in ads)
            if has_real_data:
                # Fresh fetch succeeded — reset baseline and mark reset done
                r.delete(baseline_key)
                r.setex(auto_reset_key, 43200, "1")
            else:
                # YouTube API failed — restore old cache so we don't lose data.
                # Don't set auto_reset_key so we retry on next request.
                logger.warning("Auto-reset: YouTube fetch returned no real data, restoring old cache")
                if old_cache:
                    r.setex(f"{REDIS_KEY_PREFIX}youtube_ads", _youtube_cache_ttl(), old_cache)
                    ads = json.loads(old_cache)

        cached_baseline = r.get(baseline_key)
        if cached_baseline:
            baseline = json.loads(cached_baseline)
        elif ads:
            # First fetch — snapshot current view counts as baseline (expires in 24h).
            # Only include ads with real video data.
            real_ads = {ad["video_id"]: ad["views"] for ad in ads if ad["video_id"] and ad["views"] > 0}
            if real_ads:
                baseline = real_ads
                r.setex(baseline_key, 86400, json.dumps(baseline))
    except Exception:
        pass

    # Compute deltas from baseline
    has_any_delta = False
    for ad in ads:
        ad["views_formatted"] = _format_view_count(ad["views"])
        ad["likes_formatted"] = _format_view_count(ad["likes"])
        base_views = baseline.get(ad["video_id"], ad["views"])
        delta = max(0, ad["views"] - base_views)
        ad["views_delta"] = delta
        ad["views_delta_formatted"] = f"+{_format_view_count(delta)}" if delta > 0 else ""
        if delta > 0:
            has_any_delta = True

    # Once deltas exist, rank by views gained
    if has_any_delta:
        ads.sort(key=lambda x: -x["views_delta"])

    for i, ad in enumerate(ads):
        ad["rank"] = i + 1

    with_video = sum(1 for ad in ads if ad.get("video_id"))
    ttl = _youtube_cache_ttl()
    return {
        "ads": ads,
        "count": len(ads),
        "with_video": with_video,
        "youtube_configured": bool(YOUTUBE_API_KEY),
        "cache_ttl_seconds": ttl,
        "mode": mode,
    }


@router.post("/reset-ad-baseline")
async def reset_ad_baseline(secret: str = Query("", description="Admin secret")):
    """Admin: reset the ad view baseline so deltas restart from NOW.

    Call this at kickoff so the +/- movement shows views gained during the game.
    """
    try:
        r = _redis()
        # Delete baseline AND cache so next fetch snapshots fresh counts
        r.delete(f"{REDIS_KEY_PREFIX}ad_baseline")
        r.delete(f"{REDIS_KEY_PREFIX}youtube_ads")
        return {"status": "reset", "message": "Ad baseline cleared — next fetch will snapshot new baseline"}
    except Exception as e:
        return {"error": str(e)}


@router.post("/reset")
async def reset_contest(secret: str = Query("", description="Admin secret")):
    """Admin: reset all resolutions and overrides."""
    try:
        r = _redis()
        r.delete(f"{REDIS_KEY_PREFIX}resolutions")
        r.delete(f"{REDIS_KEY_PREFIX}odds_overrides")
        r.delete(f"{REDIS_KEY_PREFIX}halftime_scores")
        r.delete(f"{REDIS_KEY_PREFIX}btc_start_price")
        r.delete(f"{REDIS_KEY_PREFIX}espn_summary")
        r.delete(f"{REDIS_KEY_PREFIX}ad_baseline")
        return {"status": "reset", "message": "All resolutions, overrides, and cached data cleared"}
    except Exception as e:
        return {"error": str(e)}
