"""
Super Bowl LX Contest API

Manages a prop bet contest for a Super Bowl watch party.
- Fetches entries from a published Google Sheet CSV
- Defines all 24 props with odds from sportsbook research
- Tracks resolution state in Redis
- Computes leaderboard with forecasted points
- Generates AI commentary via OpenAI
"""

import csv
import io
import json
import logging
import os
import ssl
from datetime import datetime, timezone
from typing import Optional

import httpx
import redis
from fastapi import APIRouter, Query

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
# Column headers from the Google Form response sheet (abbreviated).
# The CSV columns are: Timestamp, Name, then one column per question.
# We map each prop to the column header substring that identifies it.

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

# Category display order for the frontend
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
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vS-5ILxaFfHVRe6E3W0ZcFkVxO_9XrE1Ocu_1EG6FawCAROl-JOye7pvc4-S8797vGJV-nttDnMsBP8/pub?gid=0&single=true&output=csv",
)


async def _fetch_sheet_entries() -> list[dict]:
    """Fetch and parse the Google Sheet CSV into a list of entries."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(SHEET_CSV_URL)
            resp.raise_for_status()

        text = resp.text
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)

        entries = []
        for row in rows:
            entry = _parse_entry(row)
            if entry:
                entries.append(entry)
        return entries

    except Exception as e:
        logger.error(f"Failed to fetch Google Sheet: {e}")
        return []


def _parse_entry(row: dict) -> Optional[dict]:
    """Parse a single CSV row into a contest entry."""
    # Find the name column (usually second column after Timestamp)
    name = None
    picks = {}
    tiebreaker = None

    for col, val in row.items():
        col_lower = col.lower().strip()
        val = (val or "").strip()

        if not val:
            continue

        # Name column detection
        if "name" in col_lower or "your name" in col_lower or "who are you" in col_lower:
            name = val
            continue

        # Match to props by column_match
        for prop in PROPS:
            if prop.get("is_tiebreaker"):
                if prop["column_match"].lower() in col_lower:
                    try:
                        tiebreaker = float(val)
                    except (ValueError, TypeError):
                        tiebreaker = None
                    break
            elif prop["column_match"].lower() in col_lower:
                picks[prop["id"]] = val
                break

    if not name:
        # Try first non-Timestamp column as name
        cols = list(row.keys())
        if len(cols) >= 2:
            name = (row[cols[1]] or "").strip()

    if not name:
        return None

    return {
        "name": name,
        "picks": picks,
        "tiebreaker": tiebreaker,
        "submitted_at": row.get("Timestamp", ""),
    }


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

    # Handle "Other" answers - if correct answer is "Other" and the pick
    # doesn't match any predefined choice, it's an "Other" pick
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
    override_key = f"{prop_id}"
    if override_key in overrides:
        override_choices = overrides[override_key]
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
        # Apply overrides
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

        # Max possible = actual + all remaining open props they picked
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

    # Compute "key props" – open props with highest impact on ranking
    _compute_key_props(leaderboard, open_ids, overrides)

    # Compute best possible finish for each entrant
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

        # For each pending pick, how much would landing it change their ranking?
        key_props = []
        for pending in entry["pending_picks"]:
            # Impact = probability that this prop lands * how much it would help
            # A high-probability pick that others also have = less impactful
            # A low-probability pick that few others have = more impactful
            prob = pending["probability"]

            # Count how many other people picked the same thing
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

            # Impact score: higher when the pick is unique and probable
            impact = prob * (0.5 + 0.5 * uniqueness)

            key_props.append({
                "prop_id": pending["prop_id"],
                "question": pending["question"],
                "pick": pending["pick"],
                "probability": pending["probability"],
                "impact_score": round(impact, 3),
                "uniqueness": round(uniqueness, 2),
            })

        # Sort by impact score descending, take top 3
        key_props.sort(key=lambda x: -x["impact_score"])
        entry["key_props"] = key_props[:3]


def _compute_best_possible_finish(leaderboard: list, open_ids: list, overrides: dict):
    """For each entrant, compute their best possible final rank."""
    n = len(leaderboard)

    for entry in leaderboard:
        # Best case: this entrant gets ALL their open picks correct
        my_best = entry["actual_points"] + len(entry["pending_picks"])

        # For every OTHER entrant, what's the WORST they could do?
        # (all their remaining picks incorrect)
        better_count = 0
        for other in leaderboard:
            if other["name"] == entry["name"]:
                continue
            # Other's best case (for computing if they can still beat us)
            other_best = other["actual_points"] + len(other["pending_picks"])

            # Can this other person definitely beat us?
            # They beat us if their MINIMUM score > our MAXIMUM score
            # Other's minimum = their actual_points (all remaining wrong)
            other_min = other["actual_points"]

            if other_min > my_best:
                # They're already ahead even if we max out
                better_count += 1
            elif other_min == my_best and other["actual_points"] > entry["actual_points"] + len(entry["pending_picks"]):
                better_count += 1

        # But we also need to check: even among people who COULD beat us,
        # do they have the same picks as us on remaining props?
        # If two people have identical remaining picks, the one behind can never pass.
        can_never_pass = 0
        for other in leaderboard:
            if other["name"] == entry["name"]:
                continue
            if other["actual_points"] <= entry["actual_points"]:
                continue

            # They're currently ahead in actual points.
            # Check if we have any different open picks that could help us catch up.
            my_open = {p["prop_id"]: p["pick"] for p in entry["pending_picks"]}
            their_open = {p["prop_id"]: p["pick"] for p in other["pending_picks"]}

            # Find props where our picks differ
            differing_props = []
            for pid in set(list(my_open.keys()) + list(their_open.keys())):
                my_pick = my_open.get(pid, "")
                their_pick = their_open.get(pid, "")
                if _normalize_answer(my_pick) != _normalize_answer(their_pick):
                    differing_props.append(pid)

            # Points we can gain on different props - their losses on different props
            max_swing = 0
            for pid in differing_props:
                if pid in my_open:
                    max_swing += 1  # We could gain a point they don't
                if pid in their_open and pid not in my_open:
                    pass  # They could gain or lose, doesn't help us directly

            gap = other["actual_points"] - entry["actual_points"]
            # Account for resolved props difference
            gap_with_forecasted = other["forecasted_points"] - entry["forecasted_points"]

            if max_swing < gap and len(differing_props) == 0:
                can_never_pass += 1

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

        # Build context
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

        # Fun upsets / notable situations
        notable = []
        for e in lb:
            if e.get("eliminated"):
                notable.append(f"{e['name']} has been mathematically eliminated!")
            if e.get("best_possible_finish") == 1 and e["rank"] > 3:
                notable.append(f"{e['name']} is in {e['rank']}th but could still WIN!")

        notable_text = "\n".join(notable) if notable else "No major drama yet."

        prompt = f"""You are the world's funniest Super Bowl party host providing commentary on a prop bet contest.
The contest is for Super Bowl LX: Seattle Seahawks vs New England Patriots.

Current state:
- {summary['resolved_count']} of {summary['total_props']} props resolved
- {summary['entrant_count']} contestants

Standings:
{standings}

Recently resolved props:
{resolved_text}

Notable situations:
{notable_text}

Write 2-3 sentences of hilarious, entertaining commentary about the current state of the contest. Be playful and roast people who are losing, hype up people who are winning. Reference specific names and picks when possible. Keep it PG-rated (safe for kids). Be creative and funny - think sportscaster meets comedian. Don't use hashtags. Keep it short and punchy."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a hilarious Super Bowl party host. Keep commentary PG-rated, short, and funny."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=200,
            temperature=0.9,
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"Commentary generation failed: {e}")
        return "The AI commentator spilled Gatorade on its keyboard. Stand by!"


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@router.get("/leaderboard")
async def get_leaderboard():
    """
    Main endpoint: fetches entries, computes scores, returns full leaderboard.
    Designed to be polled every 15-30 seconds by the frontend.
    """
    entries = await _fetch_sheet_entries()
    resolutions = _get_resolution_state()
    overrides = _get_odds_overrides()

    result = _compute_leaderboard(entries, resolutions, overrides)
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
async def get_commentary():
    """Generate AI commentary about the current contest state."""
    entries = await _fetch_sheet_entries()
    resolutions = _get_resolution_state()
    overrides = _get_odds_overrides()

    leaderboard_data = _compute_leaderboard(entries, resolutions, overrides)
    commentary = await _generate_commentary(leaderboard_data)

    return {"commentary": commentary, "generated_at": datetime.now(timezone.utc).isoformat()}


@router.get("/entries")
async def get_entries():
    """Debug: view all parsed entries from the Google Sheet."""
    entries = await _fetch_sheet_entries()
    return {"entries": entries, "count": len(entries)}


@router.post("/reset")
async def reset_contest(secret: str = Query("", description="Admin secret")):
    """Admin: reset all resolutions and overrides."""
    try:
        r = _redis()
        r.delete(f"{REDIS_KEY_PREFIX}resolutions")
        r.delete(f"{REDIS_KEY_PREFIX}odds_overrides")
        return {"status": "reset", "message": "All resolutions and overrides cleared"}
    except Exception as e:
        return {"error": str(e)}
